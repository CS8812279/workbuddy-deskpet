"""监控 DSH / WorkBuddy 会话事件流，用于精确捕获「等待你确认」与「回合结束」。

数据源：%USERPROFILE%\\.dsh\\sessions\\<workspace>\\<session>\\session.v4.jsonl.zstd
格式：多帧 zstd + JSONL。按字节偏移增量读取，不重复解压历史。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

try:
    import zstandard
except Exception:  # 依赖缺失时降级为空监控
    zstandard = None

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
MAX_FRAME = 256 * 1024 * 1024


TOOL_LABEL = {
    "write": "写文件", "edit": "改文件", "read": "读文件", "display_file": "看图片",
    "bash": "跑命令", "shell": "跑命令", "grep": "搜内容", "glob": "找文件",
    "web_search": "搜网页", "fetch": "读网页", "web_fetch": "读网页",
    "task": "开子任务", "todo_write": "理待办", "apply_patch": "打补丁",
}


def _basename(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").split("/")[-1]


def describe_call(name: str, args_json: str) -> str:
    """把一次 tool/call 压成一句人话，例如「写文件 · 笔记.md」。"""
    import json as _json

    label = TOOL_LABEL.get(name, name)
    try:
        args = _json.loads(args_json or "{}")
    except Exception:
        args = {}
    if not isinstance(args, dict):
        args = {}

    detail = ""
    for key in ("file_path", "path", "filename", "target_file", "notebook_path"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            detail = _basename(val.strip())
            break
    if not detail:
        cmd = args.get("command")
        if isinstance(cmd, str) and cmd.strip():
            detail = " ".join(cmd.strip().split())[:32]
    if not detail:
        for key in ("pattern", "query", "task", "description"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                detail = f"「{val.strip()[:18]}」"
                break
    return f"{label} · {detail}" if detail else label


def _decompress(chunk: bytes) -> str | None:
    try:
        return zstandard.ZstdDecompressor().decompress(
            chunk, max_output_size=MAX_FRAME
        ).decode("utf-8", "replace")
    except Exception:
        return None


class DshMonitor:
    def __init__(self, store, lookback_minutes: int = 30):
        self.store = store
        self.base = Path(os.path.expanduser("~")) / ".dsh" / "sessions"
        self.lookback = lookback_minutes
        self._state: dict[str, dict] = {}   # path -> {offset, cwd, sid, title, mtime}
        self._pending: dict[str, dict] = {}  # approval id -> alert
        self._booted = False
        self.last_error = ""

    # ---------------- 文件 ----------------
    def _files(self) -> list[Path]:
        if not self.base.exists():
            return []
        return list(self.base.glob("*/*/session.v4.jsonl.zstd"))

    def _header(self, path: Path) -> dict:
        """流式读文件开头，取 cwd / session id / 标题；一旦拿齐就停。"""
        info: dict = {}
        try:
            with open(path, "rb") as fh:
                reader = zstandard.ZstdDecompressor().stream_reader(fh)
                buf = b""
                total = 0
                while total < 4 * 1024 * 1024:
                    chunk = reader.read(256 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    buf += chunk
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        line = raw.decode("utf-8", "replace").strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        typ = obj.get("type")
                        if typ == "session":
                            sid = str(obj.get("id") or "")
                            if sid.startswith("session-"):
                                sid = sid[len("session-"):]
                            info["sid"] = sid
                            info["cwd"] = obj.get("cwd") or ""
                            info["origin"] = obj.get("origin") or ""
                        elif typ == "session/title" and not info.get("title"):
                            info["title"] = (obj.get("data") or {}).get("title") or ""
                    if info.get("sid") and info.get("title"):
                        break
        except Exception:
            pass
        return info

    def _full_title(self, path: Path, cap: int = 24 * 1024 * 1024) -> str:
        """流式扫完整段，取最后一条 session/title。

        大会话里改名可能发生在中段（16MB 的会话，改名在 44% 处），只扫尾巴会漏。
        每个新会话只做一次，之后靠 _tail_titles 增量刷新。
        """
        title = ""
        try:
            if path.stat().st_size > cap:
                return ""
            with open(path, "rb") as fh:
                reader = zstandard.ZstdDecompressor().stream_reader(fh)
                buf = b""
                while True:
                    chunk = reader.read(512 * 1024)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        if b"session/title" not in raw:
                            continue
                        try:
                            obj = json.loads(raw.decode("utf-8", "replace"))
                        except Exception:
                            continue
                        if obj.get("type") == "session/title":
                            name = ((obj.get("data") or {}).get("title") or "").strip()
                            if name:
                                title = name
        except Exception:
            return title
        return title

    def _tail_titles(self, path: Path, window: int = 768 * 1024) -> str:
        """只扫文件尾部，取最后一条 session/title。

        用户改名会在流里追加一条 source=user 的 title 事件；如果只读文件头，
        拿到的永远是第一次自动生成的名字，这就是"改了名还显示旧名"的原因。
        """
        try:
            size = path.stat().st_size
            start = max(0, size - window)
            with open(path, "rb") as fh:
                fh.seek(start)
                buf = fh.read()
        except OSError:
            return ""
        pos = buf.find(ZSTD_MAGIC)
        if pos < 0:
            return ""
        title = ""
        while pos < len(buf):
            nxt = buf.find(ZSTD_MAGIC, pos + 4)
            chunk = buf[pos:] if nxt < 0 else buf[pos:nxt]
            text = _decompress(chunk)
            if text is None:
                break
            for line in text.splitlines():
                if "session/title" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") == "session/title":
                    name = ((obj.get("data") or {}).get("title") or "").strip()
                    if name:
                        title = name
            if nxt < 0:
                break
            pos = nxt
        return title

    def _read_new(self, path: Path, offset: int) -> tuple[list[str], int]:
        try:
            size = path.stat().st_size
            if size < offset:          # 被重写/压缩过，退回开头重读
                return [], 0
            if size == offset:
                return [], offset
            with open(path, "rb") as fh:
                fh.seek(offset)
                buf = fh.read()
        except OSError:
            return [], offset

        start = buf.find(ZSTD_MAGIC)
        if start < 0:
            return [], offset
        buf = buf[start:]
        base_abs = offset + start
        lines: list[str] = []
        pos = 0
        while pos < len(buf):
            nxt = buf.find(ZSTD_MAGIC, pos + 4)
            chunk = buf[pos:] if nxt < 0 else buf[pos:nxt]
            text = _decompress(chunk)
            if text is None:      # 半帧，等下次写完
                break
            lines.extend(text.splitlines())
            if nxt < 0:
                pos = len(buf)
                break
            pos = nxt
        return lines, base_abs + pos

    # ---------------- 采集 ----------------
    def poll(self) -> dict:
        out = {"events": [], "active": [], "ok": zstandard is not None, "error": ""}
        if zstandard is None:
            out["error"] = "缺少 zstandard 依赖"
            return out
        if not self.base.exists():
            out["error"] = "找不到 .dsh/sessions"
            return out

        now = time.time()
        seen: set[str] = set()
        files = []
        for path in self._files():
            try:
                files.append((path.stat().st_mtime, path))
            except OSError:
                continue
        files.sort(reverse=True)

        # 首次启动：把最近 12 个会话登记进来（标题来自文件头几帧），
        # 否则“最近没动过”的会话在面板里完全看不见。
        if not self._booted:
            for _mtime, path in files[:12]:
                if str(path) not in self._state:
                    head = self._header(path)
                    try:
                        size = path.stat().st_size
                    except OSError:
                        size = 0
                    self._state[str(path)] = {
                        "offset": size,
                        "cwd": head.get("cwd", ""),
                        "sid": head.get("sid", path.parent.name),
                        "title": self._full_title(path) or head.get("title", ""),
                        "origin": head.get("origin", ""),
                        "mtime": _mtime,
                    }
                    seen.add(str(path))
            self._booted = True

        for mtime, path in files:
            key = str(path)
            st_mtime = mtime
            try:
                st = path.stat()
            except OSError:
                continue
            fresh = (now - st.st_mtime) <= self.lookback * 60
            state = self._state.get(key)
            if state is None:
                if not fresh:
                    continue
                head = self._header(path)
                state = {
                    "offset": st.st_size,      # 跳过历史，只跟新事件
                    "cwd": head.get("cwd", ""),
                    "sid": head.get("sid", path.parent.name),
                    "title": self._full_title(path) or head.get("title", ""),
                    "origin": head.get("origin", ""),
                    "mtime": st.st_mtime,
                }
                self._state[key] = state
                seen.add(key)
                continue
            seen.add(key)
            if (st.st_size != state["offset"] or st.st_mtime != state["mtime"]) and                     now - state.get("title_at", 0) > 8:
                latest = self._tail_titles(path)
                if latest and latest != state["title"]:
                    state["title"] = latest
                state["title_at"] = now
            if st.st_size == state["offset"]:
                if now - state["mtime"] > 3 * 3600:
                    self._state.pop(key, None)   # 三小时没动静就不再跟
                continue

            lines, new_offset = self._read_new(path, state["offset"])
            state["offset"] = new_offset
            state["mtime"] = st.st_mtime
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                ev = self._handle(obj, state)
                if ev:
                    out["events"].append(ev)

        # 清理长时间不活跃的文件
        for key in list(self._state):
            if key not in seen and now - self._state[key]["mtime"] > 3 * 3600:
                self._state.pop(key, None)

        # DSH 的事件是成段落盘的（一轮结束才 flush），所以“活跃”按最近活动时间
        # 排序给出，由界面决定怎么展示，而不是硬卡 3 分钟。
        recent = [
            s for s in self._state.values()
            if now - s["mtime"] <= 3 * 3600
        ]
        recent.sort(key=lambda s: s["mtime"], reverse=True)
        def _act(s: dict) -> dict | None:
            act = s.get("act")
            if not act:
                return None
            age = now - float(act.get("ts") or 0)
            if age > 180:            # 三分钟没动静就不算“正在做”
                return None
            return {"kind": act["kind"], "text": act.get("text", ""),
                    "age": round(age)}

        out["active"] = [
            {
                "sid": s["sid"],
                "cwd": s["cwd"],
                "title": s["title"] or "会话",
                "idle_min": round((now - s["mtime"]) / 60, 1),
                "activity": _act(s),
            }
            for s in recent[:5]
        ]
        return out

    def _handle(self, obj: dict, state: dict) -> dict | None:
        typ = obj.get("type")
        data = obj.get("data") or {}
        ts = (obj.get("time") or 0) / 1000 or time.time()

        if typ == "session/title":
            title = (data.get("title") or "").strip()
            if title:
                state["title"] = title
            return None

        if typ == "turn/start":
            return {
                "kind": "turn_start", "sid": state["sid"], "title": state.get("title") or "会话",
                "cwd": state["cwd"], "ts": ts, "source": "dsh",
            }

        if typ == "turn/end":
            state["act"] = None
            reason = (data.get("reason") or {}).get("kind", "completed")
            if state.get("origin") == "subagent":
                return None   # 子代理回合结束不打扰用户
            return {
                "kind": "turn_end", "sid": state["sid"], "title": state.get("title") or "会话",
                "cwd": state["cwd"], "ts": ts, "source": "dsh",
                "reason": reason,
            }

        if typ == "approval/asked":
            alert = {
                "kind": "approval", "sid": state["sid"], "title": state.get("title") or "会话",
                "cwd": state["cwd"], "ts": ts, "source": "dsh",
                "approval_id": str(data.get("id") or ""),
                "tool": data.get("toolName") or "",
                "reason": (data.get("reason") or "").strip(),
            }
            self._pending[alert["approval_id"]] = alert
            return alert

        if typ == "tool/call":
            name = str(data.get("name") or "")
            state["act"] = {
                "kind": "tool",
                "name": name,
                "text": describe_call(name, data.get("arguments") or ""),
                "ts": ts,
            }
            return None

        if typ in ("assistant/message", "assistant/attempt", "step/start"):
            state["act"] = {"kind": "thinking", "name": "", "text": "思考中", "ts": ts}
            return None

        if typ == "approval/decided":
            aid = str(data.get("id") or "")
            self._pending.pop(aid, None)
            return {"kind": "approval_cleared", "approval_id": aid, "ts": ts,
                    "sid": state["sid"], "source": "dsh"}

        return None

    def pending_alerts(self) -> list[dict]:
        return list(self._pending.values())
