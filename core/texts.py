"""台词库：默认内置一份，用户可用项目根目录的 lines.json 覆盖。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINES_FILE = ROOT / "lines.json"

DEFAULT_LINES: dict[str, list[str]] = {
    "happy": ["嘿嘿…", "好舒服～", "再来一下嘛", "唔…喜欢"],
    "shy": ["别、别摸了…", "脸要烧起来了", "诶…突然这样"],
    "angry": ["别戳了！", "再点真要生气了", "哼——"],
    "surprise": ["哇啊——", "放我下来！"],
    "sad": ["呜…", "今天有点累"],
    "idle": ["在呢", "嗯？"],
}

DEFAULT_FONT = {"family": "Microsoft YaHei UI", "size": 10, "title_size": 10}


def load_lines(path: Path | None = None) -> dict[str, list[str]]:
    """默认台词 + lines.json 覆盖（同名键整组替换，不追加）。"""
    out = {k: list(v) for k, v in DEFAULT_LINES.items()}
    target = Path(path) if path else LINES_FILE
    if not target.exists():
        return out
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    for key, val in data.items():
        if isinstance(val, str):
            val = [val]
        if isinstance(val, list):
            lines = [str(x).strip() for x in val if str(x).strip()]
            if lines:
                out[str(key)] = lines
    return out


def write_example(path: Path | None = None, force: bool = False) -> Path:
    """首次运行写一份可编辑的 lines.json（已存在则不覆盖）。"""
    target = Path(path) if path else LINES_FILE
    if target.exists() and not force:
        return target
    target.write_text(
        json.dumps(DEFAULT_LINES, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target
