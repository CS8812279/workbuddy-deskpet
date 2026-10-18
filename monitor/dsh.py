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

    def _read_new(self, path: Path, offset: int) -> tuple[list[str], int]:
        try:
            size = path.stat().st_size
            if size <= offset:
                return [], size
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
                        "title": head.get("title", ""),
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
                    "title": head.get("title", ""),
                    "origin": head.get("origin", ""),
                    "mtime": st.st_mtime,
                }
                self._state[key] = state
                seen.add(key)
                continue
            seen.add(key)
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
        out["active"] = [
            {
                "sid": s["sid"],
                "cwd": s["cwd"],
                "title": s["title"] or "会话",
                "idle_min": round((now - s["mtime"]) / 60, 1),
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
                "kind": "turn_start", "sid": state["sid"], "title": state["title"],
                "cwd": state["cwd"], "ts": ts, "source": "dsh",
            }

        if typ == "turn/end":
            reason = (data.get("reason") or {}).get("kind", "completed")
            if state.get("origin") == "subagent":
                return None   # 子代理回合结束不打扰用户
            return {
                "kind": "turn_end", "sid": state["sid"], "title": state["title"],
                "cwd": state["cwd"], "ts": ts, "source": "dsh",
                "reason": reason,
            }

        if typ == "approval/asked":
            alert = {
                "kind": "approval", "sid": state["sid"], "title": state["title"],
                "cwd": state["cwd"], "ts": ts, "source": "dsh",
                "approval_id": str(data.get("id") or ""),
                "tool": data.get("toolName") or "",
                "reason": (data.get("reason") or "").strip(),
            }
            self._pending[alert["approval_id"]] = alert
            return alert

        if typ == "approval/decided":
            aid = str(data.get("id") or "")
            self._pending.pop(aid, None)
            return {"kind": "approval_cleared", "approval_id": aid, "ts": ts,
                    "sid": state["sid"], "source": "dsh"}

        return None

    def pending_alerts(self) -> list[dict]:
        return list(self._pending.values())
