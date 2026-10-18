"""配置读写：项目根目录 config.json，深合并默认值。"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"

DEFAULTS: dict = {
    "pet": {
        "scale": 1.0,
        "x": None,
        "y": None,
        "always_on_top": True,
        "muted": False,
        "name": "墨团",
        "skin": "auto",
        "skin_id": "whale-girl",
        "skin_file": "",
    },
    "alerts": {
        "complete": True,
        "approval": True,
        "sound": True,
        "tray": True,
        "center_on_alert": True,
        "bubble_seconds": 9,
        "sound_file": "",
    },
    "monitor": {
        "interval_ms": 2000,
        "lookback_minutes": 30,
    },
    "deepseek": {
        "api_key": "",
        "refresh_seconds": 60,
    },
    "credits": {
        "refresh_seconds": 300,
        "exe": "",
    },
    "autostart": False,
}

_lock = threading.Lock()


def _merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    with _lock:
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                return _merge(DEFAULTS, raw)
            except Exception:
                pass
        return copy.deepcopy(DEFAULTS)


def save(cfg: dict) -> None:
    with _lock:
        ROOT.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
