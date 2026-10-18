"""从一张母图做出整套皮肤：局部重绘表情 → 抠图 → 对齐 → 出帧。

    python tools/make_skin.py --name moth-girl --image D:/path/base.png --box 840,300,1100,470

全部走 ComfyUI 的 HTTP 接口（/upload/image、/prompt、/history、/view），
不假设它装在哪个目录——本机就有两套 ComfyUI 在不同路径下。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

API = "http://127.0.0.1:8188"
ROOT = Path(__file__).resolve().parent.parent

UNET = "Krea2\\Krea2-18+卡通krea2Anime_v15_int8_convrot.safetensors"
TARGET_H = 900
ALPHA_FLOOR = 12
PAD = 2

# 只描述眼睑与嘴，别让模型重画瞳孔——这个角色是纯黑复眼，模型会擅自改成棕色虹膜
FACES = {
    "blink": "eyes closed with thick black lashes, calm neutral face, lips closed",
    "alert": "eyes wide open in surprise, eyebrows slightly raised, lips closed",
    "done": "eyes closed in a happy smile, curved lashes, small smiling mouth with closed lips",
    "sleep": "eyes closed softly, sleepy relaxed eyelids, lips closed, calm",
}
# 闭眼要重画眼睑，denoise 得高；睁眼只微调形变，压低避免改色
DENOISE = {"blink": 0.85, "alert": 0.55, "done": 0.8, "sleep": 0.8}
NEGATIVE = ("brown iris, amber iris, hazel eyes, red eyes, realistic eyeball, glossy highlight, "
            "open mouth, teeth, tongue, dark mouth interior, extra eyes, blurry")


# ---------------- HTTP ----------------
def submit(graph: dict) -> str:
    body = json.dumps({"prompt": graph, "client_id": uuid.uuid4().hex}).encode()
    req = urllib.request.Request(f"{API}/prompt", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["prompt_id"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"提交失败 HTTP {exc.code}: {detail[:600]}")


def wait(pid: str, timeout: float = 900) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with urllib.request.urlopen(f"{API}/history/{pid}", timeout=15) as resp:
            if pid in json.loads(resp.read()):
                return
        time.sleep(1.0)
    raise TimeoutError(pid)


def upload(path: Path, name: str) -> str:
    boundary = "----dsh" + uuid.uuid4().hex
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    crlf = b"\r\n"
    payload = b"".join([
        f"--{boundary}".encode() + crlf,
        f'Content-Disposition: form-data; name="image"; filename="{name}"'.encode() + crlf,
        f"Content-Type: {ctype}".encode() + crlf + crlf,
        path.read_bytes(),
        crlf + f"--{boundary}".encode() + crlf,
        b'Content-Disposition: form-data; name="overwrite"' + crlf + crlf + b"true" + crlf,
        f"--{boundary}--".encode() + crlf,
    ])
    req = urllib.request.Request(
        f"{API}/upload/image", data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    sub = data.get("subfolder") or ""
    return f"{sub}/{data['name']}" if sub else data["name"]


def fetch_output(pid: str) -> bytes:
    with urllib.request.urlopen(f"{API}/history/{pid}", timeout=20) as resp:
        hist = json.loads(resp.read())
    for node in (hist[pid].get("outputs") or {}).values():
        for img in node.get("images") or []:
            q = urllib.parse.urlencode({"filename": img["filename"],
                                        "subfolder": img.get("subfolder", ""),
                                        "type": img.get("type", "output")})
            with urllib.request.urlopen(f"{API}/view?{q}", timeout=60) as resp:
                return resp.read()
    raise RuntimeError("任务没有产出图片")


# ---------------- 图 ----------------
def build_mask(base: Path, boxes: list[tuple[int, int, int, int]], feather: int) -> Image.Image:
    im = Image.open(base)
    mask = Image.new("L", im.size, 0)
    draw = ImageDraw.Draw(mask)
    for box in boxes:
        draw.ellipse(box, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(feather))


def inpaint_graph(image: str, mask: str, prompt: str, prefix: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors",
                         "type": "krea2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image}},
        "5": {"class_type": "LoadImageMask", "inputs": {"image": mask, "channel": "red"}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["3", 0]}},
        "7": {"class_type": "SetLatentNoiseMask",
              "inputs": {"samples": ["6", 0], "mask": ["5", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "9": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0],
                         "text": "blurry face, distorted eyes, extra eyes, watermark"}},
        "10": {"class_type": "KSampler", "inputs": {
            "cfg": 1.0, "denoise": 0.9, "latent_image": ["7", 0], "model": ["1", 0],
            "negative": ["9", 0], "positive": ["8", 0], "sampler_name": "euler",
            "scheduler": "simple", "seed": seed, "steps": 8}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
        "12": {"class_type": "ImageCompositeMasked", "inputs": {
            "destination": ["4", 0], "source": ["11", 0],
            "x": 0, "y": 0, "resize_source": False, "mask": ["5", 0]}},
        "13": {"class_type": "SaveImage",
               "inputs": {"filename_prefix": prefix, "images": ["12", 0]}},
    }


def cut_graph(image: str, prefix: str) -> dict:
    return {
        "1": {"class_type": "LoadBackgroundRemovalModel",
              "inputs": {"bg_removal_name": "birefnet.safetensors"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": image}},
        "3": {"class_type": "RemoveBackground",
              "inputs": {"bg_removal_model": ["1", 0], "image": ["2", 0]}},
        "4": {"class_type": "InvertMask", "inputs": {"mask": ["3", 0]}},
        "5": {"class_type": "JoinImageWithAlpha",
              "inputs": {"image": ["2", 0], "alpha": ["4", 0]}},
        "6": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": prefix, "images": ["5", 0]}},
    }


def clean_alpha(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    alpha = im.getchannel("A").point(lambda v: 0 if v < ALPHA_FLOOR else v)
    alpha = alpha.filter(ImageFilter.MinFilter(3))
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
    im.putalpha(alpha)
    return im


# ---------------- 主流程 ----------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="皮肤目录名，如 moth-girl")
    ap.add_argument("--image", required=True, help="母图本地路径")
    ap.add_argument("--box", required=True, help="眼睛区域椭圆 x1,y1,x2,y2")
    ap.add_argument("--mouth", default="", help="嘴部椭圆 x1,y1,x2,y2（可选，只给需要改嘴的状态用）")
    ap.add_argument("--display", default="", help="菜单显示名")
    ap.add_argument("--feather", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--skip-faces", action="store_true", help="只用母图，不做表情差分")
    args = ap.parse_args()

    base = Path(args.image)
    if not base.exists():
        raise SystemExit(f"找不到母图：{base}")
    boxes = [tuple(int(v) for v in args.box.split(","))]
    if args.mouth:
        boxes.append(tuple(int(v) for v in args.mouth.split(",")))
    assert all(len(b) == 4 for b in boxes), "坐标需要 4 个数字"

    tmpdir = ROOT / "data" / "skin-build"
    tmpdir.mkdir(parents=True, exist_ok=True)

    print("[1/4] 上传母图 + 蒙版")
    base_name = upload(base, f"{args.name}-base.png")
    mask_path = tmpdir / f"{args.name}-mask.png"
    build_mask(base, boxes, args.feather).save(mask_path)
    mask_name = upload(mask_path, f"{args.name}-mask.png")
    print("   ", base_name, "|", mask_name)

    sources: dict[str, bytes] = {"idle": base.read_bytes()}
    if not args.skip_faces:
        print("[2/4] 局部重绘四个表情")
        jobs = {}
        for i, (name, prompt) in enumerate(FACES.items()):
            graph = inpaint_graph(base_name, mask_name, prompt,
                                  f"{args.name}-{name}", args.seed + i)
            graph["10"]["inputs"]["denoise"] = DENOISE.get(name, 0.8)
            graph["9"]["inputs"]["text"] = NEGATIVE
            jobs[name] = submit(graph)
            print("    submitted", name, flush=True)
        for name, pid in jobs.items():
            wait(pid)
            sources[name] = fetch_output(pid)
            print("    done", name, flush=True)
    else:
        print("[2/4] 跳过表情差分")

    print("[3/4] 抠图")
    cuts = {}
    for name, data in sources.items():
        blob = tmpdir / f"{args.name}-{name}.png"
        blob.write_bytes(data)
        cuts[name] = submit(cut_graph(upload(blob, f"{args.name}-{name}.png"),
                                      f"{args.name}-cut-{name}"))
    cut_img: dict[str, Image.Image] = {}
    for name, pid in cuts.items():
        wait(pid)
        raw = tmpdir / f"{args.name}-cut-{name}.png"
        raw.write_bytes(fetch_output(pid))
        cut_img[name] = clean_alpha(Image.open(raw))
        print("    cut", name, flush=True)

    print("[4/4] 对齐出帧")
    boxes = [c.getchannel("A").getbbox() for c in cut_img.values()]
    box_all = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
    print("    union bbox", box_all)

    scale = TARGET_H / (box_all[3] - box_all[1])
    out = ROOT / "assets" / args.name / "frames"
    out.mkdir(parents=True, exist_ok=True)
    for name, im in cut_img.items():
        c = im.crop(box_all)
        size = (max(1, round(c.width * scale)), TARGET_H)
        c = c.resize(size, Image.LANCZOS)
        canvas = Image.new("RGBA", (size[0] + PAD * 2, size[1] + PAD * 2), (0, 0, 0, 0))
        canvas.paste(c, (PAD, PAD), c)
        canvas.save(out / f"{name}.png")
        print("    saved", name, canvas.size)

    meta = {"display": args.display or args.name, "frames": sorted(cut_img), "height": TARGET_H}
    (ROOT / "assets" / args.name / "skin.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("完成 ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
