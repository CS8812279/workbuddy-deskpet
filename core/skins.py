"""内置皮肤清单：扫 assets/<id>/skin.json。"""
from __future__ import annotations

import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_ID = "whale-girl"


def available(assets: Path | None = None) -> list[dict]:
    root = assets or ASSETS
    out: list[dict] = []
    for meta in sorted(root.glob("*/skin.json")):
        skin_id = meta.parent.name
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        frames = meta.parent / "frames"
        if not (frames / "idle.png").exists():
            continue
        out.append({
            "id": skin_id,
            "name": data.get("display") or skin_id,
            "frames": frames,
        })
    out.sort(key=lambda s: (s["id"] != DEFAULT_ID, s["name"]))
    return out


def frames_dir(skin_id: str, assets: Path | None = None) -> Path:
    root = assets or ASSETS
    return root / (skin_id or DEFAULT_ID) / "frames"
