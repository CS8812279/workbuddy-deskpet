"""DeepSeek 余额与今日消耗。

不依赖任何 DSH 插件：
1. 优先直连官方 `/user/balance`（需要 API Key，可在设置里填 / 读环境变量 / 读 DSH 凭据）；
2. 今日消耗用本地余额快照的下降量累计（充值不冲抵）；
3. 都没配置时，才回退读小鲸鱼挂件的账本做兜底（可选，不是必需）。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://api.deepseek.com/user/balance"
LEDGER = Path(os.path.expanduser("~")) / ".dsh" / ".dshw-usage.json"
CREDS = Path(os.path.expanduser("~")) / ".dsh" / ".credentials.yaml"
SYMBOL = {"CNY": "¥", "USD": "$"}


class DeepSeekMonitor:
    def __init__(self, refresh_seconds: int = 60, api_key: str = "", store=None,
                 ledger_path: Path | None = None):
        self.refresh = max(15, int(refresh_seconds))
        self._key = (api_key or "").strip()
        self.store = store
        self.ledger = Path(ledger_path) if ledger_path else LEDGER
        self._last_at = 0.0
        self._cache = {
            "ok": False, "balance": None, "today": None, "date": "", "currency": "CNY",
            "source": "未连接", "updated_at": 0, "error": "尚未刷新",
        }

    # ---------------- 对外 ----------------
    def set_key(self, key: str) -> None:
        self._key = (key or "").strip()
        self._last_at = 0.0

    def poll(self, force: bool = False) -> dict:
        now = time.time()
        if not force and now - self._last_at < self.refresh:
            return self._cache
        self._last_at = now

        key = self._resolve_key()
        api_error = ""
        if key:
            try:
                balance, currency = self._fetch(key)
                return self._ok(balance, currency, "DeepSeek API")
            except Exception as exc:
                api_error = str(exc)[:60]

        ledger = self._from_ledger()
        if ledger:
            if api_error:
                ledger["error"] = f"接口失败：{api_error}"
            return ledger

        self._cache = {
            "ok": False, "balance": None, "today": None, "date": "", "currency": "CNY",
            "source": "未连接", "updated_at": 0,
            "error": api_error or "未配置 API Key（右键 → 设置里填）",
        }
        return self._cache

    # ---------------- Key ----------------
    def _resolve_key(self) -> str:
        if self._key:
            return self._key
        for env in ("DEEPSEEK_API_KEY", "DEEPSEEK_KEY"):
            val = (os.environ.get(env) or "").strip()
            if val.startswith("sk-"):
                return val
        # DSH 凭据里偶尔存的是明文 key（多数情况是内部句柄，认不出就跳过）
        try:
            import yaml

            data = yaml.safe_load(CREDS.read_text(encoding="utf-8")) or {}
            val = str((data.get("refs") or {}).get("DEEPSEEK_API_KEY") or "").strip()
            if val.startswith("sk-"):
                return val
        except Exception:
            pass
        return ""

    # ---------------- 官方接口 ----------------
    def _fetch(self, key: str) -> tuple[float, str]:
        req = urllib.request.Request(
            API,
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                     "User-Agent": "workbuddy-deskpet"},
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise RuntimeError("API Key 无效或已过期")
            raise RuntimeError(f"HTTP {exc.code}")

        infos = payload.get("balance_infos") or []
        if not infos:
            raise RuntimeError("接口没有返回余额")
        info = next((i for i in infos if i.get("currency") == "CNY"), infos[0])
        try:
            balance = float(info.get("total_balance"))
        except (TypeError, ValueError):
            raise RuntimeError("余额字段无法解析")
        return balance, str(info.get("currency") or "CNY")

    # ---------------- 结果组装 ----------------
    def _ok(self, balance: float, currency: str, source: str) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        self._cache = {
            "ok": True,
            "balance": balance,
            "today": self._account(balance),
            "date": today,
            "currency": currency,
            "source": source,
            "updated_at": time.time(),
            "error": "",
        }
        return self._cache

    def _account(self, balance: float) -> float:
        """用余额下降量记今日消耗；首次拿不到基线时用挂件账本补一段。"""
        day = datetime.now().strftime("%Y-%m-%d")
        if self.store is None:
            return 0.0
        st = self.store.data.setdefault("deepseek_daily", {})
        if st.get("day") != day:
            st.update(day=day, last=balance, used=0.0)
            seed = self._ledger_today(day)
            if seed:
                st["used"] = seed
        else:
            prev = st.get("last")
            if isinstance(prev, (int, float)) and balance < prev:
                st["used"] = round(float(st.get("used", 0.0)) + (prev - balance), 6)
            st["last"] = balance
        self.store.save()
        return round(float(st.get("used", 0.0)), 4)

    def _ledger_today(self, day: str) -> float:
        data = self._read_ledger()
        if not data:
            return 0.0
        hist = data.get("history") or {}
        if day in hist:
            try:
                return float(hist[day])
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    # ---------------- 兜底：挂件账本 ----------------
    def _read_ledger(self) -> dict | None:
        try:
            return json.loads(self.ledger.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _from_ledger(self) -> dict | None:
        data = self._read_ledger()
        if not data:
            return None
        today = datetime.now().strftime("%Y-%m-%d")
        hist = data.get("history") or {}
        used = hist.get(today)
        if used is None and data.get("date") == today:
            used = data.get("todayUsage")
        self._cache = {
            "ok": True,
            "balance": data.get("lastBalance"),
            "today": used,
            "date": data.get("date") or "",
            "currency": "CNY",
            "source": "小鲸鱼账本",
            "updated_at": self.ledger.stat().st_mtime,
            "error": "" if data.get("date") == today else "账本非今日数据",
        }
        return self._cache
