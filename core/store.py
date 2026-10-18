"""本地账本：积分事件、提醒去重、历史记录。"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

MAX_DAYS = 60


def today_str(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d")


class Store:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.data = {
            "credits": {},   # requestId -> {"at": ts, "amount": float, "sid": str}
            "fired": {},     # dedupeKey -> ts
            "history": [],   # 最近事件（用于面板/日志）
            "baseline_at": time.time(),
        }
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data.update(raw)
                self.data.setdefault("baseline_at", time.time())
        except Exception:
            pass

    def save(self) -> None:
        with self._lock:
            self._prune()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.data, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    def _prune(self) -> None:
        cutoff = (datetime.now() - timedelta(days=MAX_DAYS)).timestamp()
        credits = {k: v for k, v in self.data["credits"].items()
                   if float(v.get("at", 0)) >= cutoff}
        self.data["credits"] = credits
        fired = {k: v for k, v in self.data["fired"].items() if v >= cutoff}
        self.data["fired"] = fired
        self.data["history"] = self.data.get("history", [])[-200:]

    # ---------- 积分 ----------
    def add_credit(self, request_id: str, amount: float, sid: str, at: float | None = None) -> bool:
        """记录一笔积分消耗；已存在则返回 False。"""
        with self._lock:
            if request_id in self.data["credits"]:
                return False
            self.data["credits"][request_id] = {
                "at": at or time.time(),
                "amount": float(amount),
                "sid": sid,
            }
            return True

    def credits_total(self) -> float:
        return sum(float(v["amount"]) for v in self.data["credits"].values())

    def credits_today(self) -> float:
        day = today_str()
        return sum(float(v["amount"]) for v in self.data["credits"].values()
                   if today_str(float(v["at"])) == day)

    def credits_by_day(self, days: int = 7) -> list[tuple[str, float]]:
        buckets: dict[str, float] = {}
        for v in self.data["credits"].values():
            buckets[today_str(float(v["at"]))] = buckets.get(today_str(float(v["at"])), 0.0) + float(v["amount"])
        out = []
        for i in range(days - 1, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            out.append((d, round(buckets.get(d, 0.0), 2)))
        return out

    def credits_for_session(self, sid: str) -> float:
        return sum(float(v["amount"]) for v in self.data["credits"].values()
                   if v.get("sid") == sid)

    # ---------- 去重 ----------
    def should_fire(self, key: str) -> bool:
        with self._lock:
            if key in self.data["fired"]:
                return False
            self.data["fired"][key] = time.time()
            return True

    # ---------- 历史 ----------
    def push_history(self, kind: str, text: str, ts: float | None = None) -> None:
        with self._lock:
            self.data["history"].append(
                {"kind": kind, "text": text, "at": ts or time.time()}
            )
            self.data["history"] = self.data["history"][-200:]

    def recent_history(self, n: int = 6) -> list[dict]:
        return list(reversed(self.data.get("history", [])[-n:]))
