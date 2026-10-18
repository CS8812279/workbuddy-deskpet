"""用 Krea2 生成气泡底图：白色毛绒圆角面板，抠图后存成 assets/bubble/fluff.png。

    python tools/make_bubble_art.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.make_skin import (  # noqa: E402
    UNET, cut_graph, fetch_output, submit, upload, wait,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "bubble" / "fluff.png"

PROMPT = ("一个纯白色的毛绒质感圆角矩形面板，四角圆润，边缘蓬松柔软像绒毛，表面是细密的白色绒毛，"
          "正面平视，居中放置，浅灰色纯色背景，没有文字，没有阴影，没有描边")
NEG = "文字, 字母, 水印, 黑色边框, 硬边, 金属, 反光, 多个物体, 阴影"


def t2i(seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors",
                         "type": "krea2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": PROMPT}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEG}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0],
            "latent_image": ["4", 0], "seed": seed, "steps": 8, "cfg": 1.0,
            "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": f"bubble-{seed}", "images": ["8", 0]}},
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "data" / "skin-build"
    tmp.mkdir(parents=True, exist_ok=True)

    for i, seed in enumerate((771211, 882301)):
        print(f"[krea2] seed {seed} …", flush=True)
        pid = submit(t2i(seed))
        wait(pid)
        raw = tmp / f"bubble-{seed}.png"
        raw.write_bytes(fetch_output(pid))
        print("   saved", raw.name, flush=True)

    # 用第一张：抠图 → 裁边 → 存
    src = tmp / "bubble-771211.png"
    name = upload(src, "bubble-src.png")
    pid = submit(cut_graph(name, "bubble-cut"))
    wait(pid)
    cut = tmp / "bubble-cut.png"
    cut.write_bytes(fetch_output(pid))

    im = Image.open(cut).convert("RGBA")
    alpha = im.getchannel("A").point(lambda v: 0 if v < 24 else v)
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    im.putalpha(alpha)
    box = im.getchannel("A").getbbox()
    if box:
        im = im.crop(box)
    im.thumbnail((512, 512), Image.LANCZOS)
    im.save(OUT)
    print("完成 ->", OUT, im.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
