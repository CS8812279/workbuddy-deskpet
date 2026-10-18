"""用 Qwen-Image-2.1 的「局部编辑」流做表情：裁头部 → 自然语言改表情 → 羽化贴回。

与 Krea2 的 img2img 相比，Qwen 2.1 的指令跟随更稳，不会把纯黑复眼改成棕色虹膜。
只贴回裁切区域，边界羽化，因此角色其余部分逐像素不变。

    python tools/qwen_faces.py --name moth-girl --image D:/art/base.png --crop 700,200,1180,620
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.make_skin import (  # noqa: E402
    PAD, TARGET_H, clean_alpha, cut_graph, fetch_output, submit, upload, wait,
)

API_URL = "http://127.0.0.1:8188"
ROOT = Path(__file__).resolve().parent.parent

UNET = "Qwen\\qwen_image_2.1_int8_convrot.safetensors"
CLIP = "qwen3vl_8b_int8_convrot.safetensors"
VAE = "qwen_image_2.1_vae_bf16.safetensors"

# 陈述式、不带质量词与画幅词（Qwen 官方规则）
PROMPTS = {
    "blink": "图片是同一人物的面部特写。人物的双眼轻轻闭合，上眼睑自然下垂，睫毛贴合，神情平静。"
             "除眼睑以外，五官、发丝、肤色、光照和构图中其它内容保持完全不变。",
    "alert": "图片是同一人物的面部特写。人物的双眼睁得更大，眼睛依然是纯黑色的圆眼，没有眼白也没有虹膜颜色，"
             "眉毛微微上扬，嘴唇保持闭合。除眉眼以外，五官、发丝、肤色、光照和构图中其它内容保持完全不变。",
    "done": "图片是同一人物的面部特写。人物的双眼弯成笑眼并自然闭合，嘴角微微上扬露出笑意。"
            "除眉眼与嘴角以外，五官、发丝、肤色、光照和构图中其它内容保持完全不变。",
    "sleep": "图片是同一人物的面部特写。人物的双眼闭合，眼睑放松下垂，神情困倦柔和。"
             "除眼睑以外，五官、发丝、肤色、光照和构图中其它内容保持完全不变。",
}


def edit_graph(image: str, prompt: str, seed: int, steps: int = 20) -> dict:
    return {
        "476": {"class_type": "UNETLoader",
                "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "477": {"class_type": "CLIPLoader",
                "inputs": {"clip_name": CLIP, "type": "qwen_image", "device": "default"}},
        "478": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "479": {"class_type": "LoadImage", "inputs": {"image": image}},
        "497": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["477", 0], "vae": ["478", 0],
            "prompt": prompt, "negative_prompt": "",
            "resolution": 0, "images.image_1": ["479", 0]}},
        "481": {"class_type": "KSampler", "inputs": {
            "model": ["476", 0], "positive": ["497", 0], "negative": ["497", 1],
            "latent_image": ["497", 2], "seed": seed, "steps": steps, "cfg": 1.0,
            "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "480": {"class_type": "VAEDecode", "inputs": {"samples": ["481", 0], "vae": ["478", 0]}},
        "487": {"class_type": "SaveImage",
                "inputs": {"filename_prefix": f"qwen-{uuid.uuid4().hex[:6]}", "images": ["480", 0]}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--image", required=True, help="母图本地路径")
    ap.add_argument("--crop", required=True, help="头部裁切 x1,y1,x2,y2")
    ap.add_argument("--feather", type=int, default=28)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--only", default="", help="只跑某个状态，调试用")
    args = ap.parse_args()

    base = Image.open(args.image).convert("RGB")
    crop_box = tuple(int(v) for v in args.crop.split(","))
    head = base.crop(crop_box)

    tmp = ROOT / "data" / "skin-build"
    tmp.mkdir(parents=True, exist_ok=True)

    states = [args.only] if args.only else list(PROMPTS)
    results: dict[str, Image.Image] = {"idle": base}

    for i, state in enumerate(states):
        print(f"[qwen] {state} …", flush=True)
        src = tmp / f"{args.name}-{state}-crop.png"
        head.save(src)
        name = upload(src, f"{args.name}-{state}-crop.png")
        pid = submit(edit_graph(name, PROMPTS[state], 4400 + i * 37, args.steps))
        wait(pid)
        edited = Image.open(io.BytesIO(fetch_output(pid))).convert("RGB")
        if edited.size != head.size:
            edited = edited.resize(head.size, Image.LANCZOS)

        # 羽化贴回，边界不留缝
        mask = Image.new("L", head.size, 255)
        d = ImageDraw.Draw(mask)
        d.rectangle((0, 0, head.size[0] - 1, head.size[1] - 1), fill=255)
        inner = Image.new("L", head.size, 0)
        ImageDraw.Draw(inner).rectangle(
            (args.feather, args.feather,
             head.size[0] - args.feather, head.size[1] - args.feather), fill=255)
        soft = inner.filter(ImageFilter.GaussianBlur(args.feather * 0.6))

        canvas = base.copy()
        canvas.paste(edited, (crop_box[0], crop_box[1]), soft)
        out = tmp / f"{args.name}-{state}.png"
        canvas.save(out)
        results[state] = canvas
        print(f"   saved {out.name}", flush=True)

    if args.only:
        return 0

    print("[cut] 抠图对齐 …", flush=True)
    cut_ids = {}
    for state, im in results.items():
        p = tmp / f"{args.name}-q-{state}.png"
        im.save(p)
        cut_ids[state] = submit(cut_graph(upload(p, f"{args.name}-q-{state}.png"),
                                          f"{args.name}-qcut-{state}"))
    cut_img = {}
    for state, pid in cut_ids.items():
        wait(pid)
        raw = tmp / f"{args.name}-qcut-{state}.png"
        raw.write_bytes(fetch_output(pid))
        cut_img[state] = clean_alpha(Image.open(raw))

    boxes = [c.getchannel("A").getbbox() for c in cut_img.values()]
    box_all = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
    scale = TARGET_H / (box_all[3] - box_all[1])
    outdir = ROOT / "assets" / args.name / "frames"
    outdir.mkdir(parents=True, exist_ok=True)
    for state, im in cut_img.items():
        c = im.crop(box_all)
        size = (max(1, round(c.width * scale)), TARGET_H)
        c = c.resize(size, Image.LANCZOS)
        canvas = Image.new("RGBA", (size[0] + PAD * 2, size[1] + PAD * 2), (0, 0, 0, 0))
        canvas.paste(c, (PAD, PAD), c)
        canvas.save(outdir / f"{state}.png")
        print("   saved", state, canvas.size, flush=True)
    print("完成 ->", outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
