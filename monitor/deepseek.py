"""DeepSeek 余额：优先复用本机小鲸鱼挂件的账本，零配置。

账本路径：%USERPROFILE%\\.dsh\\.dshw-usage.json
字段：date / lastBalance / todayUsage / history
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

LEDGER = Path(os.path.expanduser("~")) / ".dsh" / ".dshw-usage.json"


class DeepSeekMonitor:
    def __init__(self, refresh_seconds: int = 60):
        self.refresh = refresh_seconds
        self._last_at = 0.0
        self._cache = {"ok": False, "balance": None, "today": None, "date": "",
                       "source": "小鲸鱼账本", "updated_at": 0, "error": ""}

    def poll(self, force: bool = False) -> dict:
        now = time.time()
        if not force and now - self._last_at < self.refresh:
            return self._cache
        self._last_at = now

        if not LEDGER.exists():
            self._cache = {"ok": False, "balance": None, "today": None, "date": "",
                           "source": "小鲸鱼账本", "updated_at": 0,
                           "error": "未找到 .dshw-usage.json（小鲸鱼挂件未运行？）"}
            return self._cache
        try:
            data = json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception as exc:
            self._cache.update(ok=False, error=f"账本读取失败: {exc}")
            return self._cache

        today = datetime.now().strftime("%Y-%m-%d")
        hist = data.get("history") or {}
        used_today = hist.get(today)
        if used_today is None and data.get("date") == today:
            used_today = data.get("todayUsage")
        self._cache = {
            "ok": True,
            "balance": data.get("lastBalance"),
            "today": used_today,
            "date": data.get("date") or "",
            "source": "小鲸鱼账本",
            "updated_at": LEDGER.stat().st_mtime,
            "error": "" if data.get("date") == today else "账本非今日数据",
        }
        return self._cache
