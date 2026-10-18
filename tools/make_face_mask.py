"""生成人脸局部编辑用的羽化蒙版，并做一张叠加预览。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SRC = Path(r"G:\ComfyUI\ComfyUI\ComfyUI\input\whale_v3.png")
OUT = Path(r"G:\ComfyUI\ComfyUI\ComfyUI\input\face_mask.png")
PREVIEW = Path(r"D:\AI Work\workbuddy-deskpet\assets\whale-girl\_face_mask_check.png")

# 覆盖眉、眼、嘴的脸部椭圆（768×1024 底图实测位置）
BOX = (318, 92, 486, 208)
FEATHER = 14


def main() -> None:
    img = Image.open(SRC).convert("RGB")
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse(BOX, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(FEATHER))
    mask.save(OUT)

    overlay = img.copy()
    red = Image.new("RGB", (w, h), (255, 70, 70))
    overlay = Image.composite(red, overlay, mask.point(lambda v: int(v * 0.45)))
    overlay.save(PREVIEW)
    print("mask", OUT, "feather", FEATHER)


if __name__ == "__main__":
    main()
