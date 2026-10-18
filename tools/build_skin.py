"""一键重建皮肤帧：抠图 → 清边 → 统一裁切 → 输出 frames/。

输入：ComfyUI input 里的 whale_v3.png（底图）与 face-* 局部重绘结果。
"""
import json
import shutil
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, ImageFilter

API = "http://127.0.0.1:8188"
COMFY = Path(r"G:\ComfyUI\ComfyUI\ComfyUI")
INPUT = COMFY / "input"
ARCHIVE = COMFY / "asset_archive"
OUT = Path(r"D:\AI Work\workbuddy-deskpet\assets\whale-girl\frames")

TARGET_H = 900
ALPHA_FLOOR = 12          # 低于此值直接判为全透明，去掉抠图残留的灰雾
PAD = 2

SOURCES = {
    "idle": ("whale_v3.png", None),
    "blink": (None, "face-blink"),
    "alert": (None, "face-alert"),
    "done": (None, "face-done"),
    "sleep": (None, "face-sleep"),
}


def newest(prefix: str, wait_s: float = 15.0) -> Path:
    """ComfyUI 的 history 会先于落盘返回，这里给文件一点时间。"""
    deadline = time.time() + wait_s
    while True:
        hits = sorted(ARCHIVE.rglob(f"{prefix}_*.png"), key=lambda p: p.stat().st_mtime)
        if hits:
            return hits[-1]
        if time.time() > deadline:
            raise FileNotFoundError(prefix)
        time.sleep(0.5)


def cut_graph(src: str, prefix: str) -> dict:
    return {
        "1": {"class_type": "LoadBackgroundRemovalModel",
              "inputs": {"bg_removal_name": "birefnet.safetensors"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": src}},
        "3": {"class_type": "RemoveBackground",
              "inputs": {"bg_removal_model": ["1", 0], "image": ["2", 0]}},
        "4": {"class_type": "InvertMask", "inputs": {"mask": ["3", 0]}},
        "5": {"class_type": "JoinImageWithAlpha",
              "inputs": {"image": ["2", 0], "alpha": ["4", 0]}},
        "6": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["5", 0]}},
    }


def submit(g: dict) -> str:
    body = json.dumps({"prompt": g, "client_id": uuid.uuid4().hex}).encode()
    req = urllib.request.Request(f"{API}/prompt", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["prompt_id"]


def wait(pid: str) -> None:
    for _ in range(300):
        with urllib.request.urlopen(f"{API}/history/{pid}", timeout=10) as r:
            if pid in json.loads(r.read()):
                return
        time.sleep(0.6)
    raise TimeoutError(pid)


def clean_alpha(im: Image.Image) -> Image.Image:
    """压掉半透明灰雾并轻微收边，避免深色背景上出现方形光晕。"""
    im = im.convert("RGBA")
    alpha = im.getchannel("A").point(lambda v: 0 if v < ALPHA_FLOOR else v)
    alpha = alpha.filter(ImageFilter.MinFilter(3))       # 收 1px，去毛边
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))  # 再柔化，避免锯齿
    im.putalpha(alpha)
    return im


def main() -> None:
    jobs = {}
    for name, (fixed, prefix) in SOURCES.items():
        if fixed:
            src = fixed
        else:
            src = f"cut_{name}.png"
            shutil.copyfile(newest(prefix), INPUT / src)
        jobs[name] = submit(cut_graph(src, f"skin_{name}"))
        print("cut", name, flush=True)
    for name, pid in jobs.items():
        wait(pid)
        print("cut done", name, flush=True)

    crops = {}
    for name in SOURCES:
        p = newest(f"skin_{name}")
        im = clean_alpha(Image.open(p))
        crops[name] = im
        print(name, "alpha bbox", im.getchannel("A").getbbox())

    # 五帧共用同一裁剪框，保证切换不位移
    boxes = [c.getchannel("A").getbbox() for c in crops.values()]
    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    right = max(b[2] for b in boxes)
    bottom = max(b[3] for b in boxes)
    print("union bbox", (left, top, right, bottom))

    scale = TARGET_H / (bottom - top)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, im in crops.items():
        c = im.crop((left, top, right, bottom))
        size = (max(1, round(c.width * scale)), TARGET_H)
        c = c.resize(size, Image.LANCZOS)
        canvas = Image.new("RGBA", (size[0] + PAD * 2, size[1] + PAD * 2), (0, 0, 0, 0))
        canvas.paste(c, (PAD, PAD), c)
        canvas.save(OUT / f"{name}.png")
        print("saved", name, canvas.size)


if __name__ == "__main__":
    main()
