"""极简运行日志：写到 data/pet.log，超过 512KB 自动截断。

桌宠由 DSH 以 pythonw 拉起，没有控制台，出问题只能靠这个文件回溯。
"""
from __future__ import annotations

import time
import traceback
from pathlib import Path

MAX_BYTES = 512 * 1024
LOG = Path(__file__).resolve().parent.parent / "data" / "pet.log"
_last: dict[str, float] = {}


def log(msg: str, key: str = "", dedup_seconds: float = 0.0) -> None:
    """key + dedup_seconds：同类消息在窗口内只记一次，避免刷屏。"""
    now = time.time()
    if key and dedup_seconds:
        prev = _last.get(key, 0)
        if now - prev < dedup_seconds:
            return
        _last[key] = now
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > MAX_BYTES:
            LOG.write_text("", encoding="utf-8")
        stamp = time.strftime("%m-%d %H:%M:%S")
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {msg}\n")
    except Exception:
        pass


def exc(msg: str) -> None:
    log(f"{msg}\n{traceback.format_exc()}")
