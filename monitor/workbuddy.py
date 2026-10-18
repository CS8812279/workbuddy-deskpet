"""监控 WorkBuddy 本地库：会话状态 + 积分消耗。

只读访问 %USERPROFILE%\\.workbuddy\\workbuddy.db（WAL），不做任何写入。
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~")) / ".workbuddy" / "workbuddy.db"

ACTIVE = {"working"}
DONE = "completed"
FAIL = "error"
STOPPED = "terminated"


def _day(ts_ms: float | None) -> str:
    if not ts_ms:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")


class WorkBuddyMonitor:
    def __init__(self, store, lookback_minutes: int = 30):
        self.store = store
        self.lookback = lookback_minutes
        self._prev: dict[str, dict] = {}
        self._known_credits: set[str] = set()
        self._primed = False
        self.last_error = ""

    # ---------------- 读取 ----------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=1500")
        return conn

    def _read_sessions(self, conn) -> list[sqlite3.Row]:
        return conn.execute(
            """
            SELECT id, title, custom_title, cwd, status, model, expert_id,
                   created_at, updated_at, last_activity_at
            FROM sessions
            WHERE deleted_at IS NULL
            ORDER BY updated_at DESC
            LIMIT 60
            """
        ).fetchall()

    def _read_credits(self, conn) -> list[tuple[str, dict]]:
        out = []
        for row in conn.execute("SELECT session_id, credit_json FROM session_usage"):
            raw = row["credit_json"]
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if isinstance(data, dict):
                out.append((row["session_id"], data))
        return out

    # ---------------- 采集 ----------------
    def poll(self) -> dict:
        result = {"tasks": [], "events": [], "credits": [], "ok": False, "error": ""}
        if not DB_PATH.exists():
            result["error"] = "找不到 workbuddy.db"
            self.last_error = result["error"]
            return result

        try:
            conn = self._connect()
            try:
                rows = self._read_sessions(conn)
                credit_rows = self._read_credits(conn)
            finally:
                conn.close()
        except Exception as exc:  # 库被锁/结构变动都不该让桌宠崩
            result["error"] = f"读取失败: {exc}"
            self.last_error = result["error"]
            return result

        result["ok"] = True
        tasks: dict[str, dict] = {}
        for row in rows:
            title = (row["custom_title"] or row["title"] or "").strip() or "未命名会话"
            tasks[row["id"]] = {
                "id": row["id"],
                "title": title,
                "cwd": row["cwd"] or "",
                "status": row["status"] or "",
                "model": row["model"] or "",
                "expert": row["expert_id"] or "",
                "created_at": row["created_at"] or 0,
                "updated_at": row["updated_at"] or 0,
            }

        # ---- 积分：新请求 ID 才记账 ----
        new_credits: list[dict] = []
        for sid, mapping in credit_rows:
            for rid, amount in mapping.items():
                if rid in self._known_credits:
                    continue
                self._known_credits.add(rid)
                if not self._primed:
                    continue
                if self.store.add_credit(str(rid), float(amount or 0), sid):
                    new_credits.append({
                        "sid": sid,
                        "amount": float(amount or 0),
                        "title": tasks.get(sid, {}).get("title", ""),
                    })
        result["credits"] = new_credits

        # ---- 会话状态迁移 ----
        events: list[dict] = []
        if not self._primed:
            # 首次运行：只把「当天开、当天结束」的会话积分归到今天，
            # 跨天会话无法拆分，宁可少算也不虚高。
            if not self.store.data.get("baseline_done"):
                for sid, mapping in credit_rows:
                    info = tasks.get(sid)
                    if not info:
                        continue
                    c_day, u_day = _day(info["created_at"]), _day(info["updated_at"])
                    if not c_day or c_day != u_day:
                        continue
                    at = (info["updated_at"] or 0) / 1000 or None
                    for rid, amount in mapping.items():
                        self.store.add_credit(str(rid), float(amount or 0), sid, at=at)
                self.store.data["baseline_done"] = True
                self.store.data["baseline_estimated"] = True
                self.store.save()
            self._primed = True
            for sid, info in tasks.items():
                self._prev[sid] = info
            result["tasks"] = list(tasks.values())
            return result

        for sid, info in tasks.items():
            old = self._prev.get(sid)
            if old is None:
                # 只关心最近还活着的会话，避免把几十个历史会话当新任务播报
                age_min = (datetime.now().timestamp() * 1000 - info["updated_at"]) / 60000
                if info["status"] in ACTIVE and age_min <= self.lookback:
                    events.append({
                        "kind": "session_started",
                        "sid": sid,
                        "title": info["title"],
                        "cwd": info["cwd"],
                        "ts": info["updated_at"] / 1000,
                    })
            else:
                if old["status"] != info["status"]:
                    if info["status"] == DONE and old["status"] in ACTIVE:
                        events.append({
                            "kind": "session_completed", "sid": sid,
                            "title": info["title"], "cwd": info["cwd"],
                            "ts": info["updated_at"] / 1000,
                        })
                    elif info["status"] == FAIL and old["status"] != FAIL:
                        events.append({
                            "kind": "session_error", "sid": sid,
                            "title": info["title"], "cwd": info["cwd"],
                            "ts": info["updated_at"] / 1000,
                        })
                    elif info["status"] == STOPPED and old["status"] in ACTIVE:
                        events.append({
                            "kind": "session_stopped", "sid": sid,
                            "title": info["title"], "cwd": info["cwd"],
                            "ts": info["updated_at"] / 1000,
                        })
                elif info["title"] != old["title"]:
                    old["title"] = info["title"]

        self._prev = tasks
        result["tasks"] = list(tasks.values())
        result["events"] = events
        return result

    # ---------------- 查询 ----------------
    def running(self) -> list[dict]:
        return [t for t in self._prev.values() if t["status"] in ACTIVE]
