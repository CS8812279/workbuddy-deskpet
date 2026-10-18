"""提示音：首次运行用正弦波合成 wav，之后直接播。"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SR = 44100


def _tone(freq: float, dur: float, amp: float = 0.25, glide: float = 0.0) -> bytes:
    n = int(SR * dur)
    buf = bytearray()
    phase = 0.0
    for i in range(n):
        t = i / SR
        f = freq + glide * (i / max(1, n))
        phase += 2 * math.pi * f / SR
        attack = min(1.0, i / (SR * 0.008))
        env = attack * math.exp(-3.4 * t / max(0.05, dur))
        v = int(32767 * amp * env * math.sin(phase))
        buf += struct.pack("<h", max(-32768, min(32767, v)))
    return bytes(buf)


def _write(path: Path, seq) -> None:
    data = b"".join(_tone(*s) for s in seq)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


def ensure(assets_dir: Path) -> dict[str, Path]:
    out_dir = assets_dir / "sounds"
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = {
        "complete": [(784, 0.13, 0.20), (1046, 0.16, 0.22), (1318, 0.22, 0.20)],
        "alert": [(880, 0.10, 0.26), (0, 0.05, 0.0), (880, 0.10, 0.26), (0, 0.05, 0.0), (740, 0.18, 0.24)],
        "error": [(392, 0.18, 0.22, -60.0), (294, 0.26, 0.20, -40.0)],
        "click": [(1240, 0.06, 0.14)],
    }
    paths = {}
    for name, seq in specs.items():
        p = out_dir / f"{name}.wav"
        if not p.exists():
            try:
                _write(p, seq)
            except Exception:
                continue
        paths[name] = p
    return paths


class Player:
    def __init__(self, assets_dir: Path, muted: bool = False, custom: str = ""):
        self.paths = ensure(assets_dir)
        self.muted = muted
        self.custom = custom

    def set_custom(self, path: str) -> None:
        self.custom = path or ""

    def play(self, name: str) -> None:
        if self.muted:
            return
        target = None
        if self.custom and Path(self.custom).exists() and name != "click":
            target = Path(self.custom)
        if target is None:
            target = self.paths.get(name)
        if not target or not target.exists():
            return
        try:
            import winsound

            winsound.PlaySound(
                str(target), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
        except Exception:
            pass
