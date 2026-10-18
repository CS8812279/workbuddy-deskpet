"""用局部重绘（SetLatentNoiseMask）只改脸，身体像素保持不变。"""
import json
import time
import urllib.request
import uuid
from pathlib import Path

API = "http://127.0.0.1:8188"
UNET = "Krea2\\Krea2-18+卡通krea2Anime_v15_int8_convrot.safetensors"
BASE_IMG = "whale_v3.png"
MASK_IMG = "face_mask.png"

VARIANTS = {
    "face-blink": "her eyes gently closed in a peaceful blink, relaxed closed lips, calm serene expression",
    "face-alert": "wide startled eyes with raised eyebrows, small open mouth, surprised expression",
    "face-done": "bright joyful open-mouth smile, sparkling happy eyes, cheerful expression",
    "face-sleep": "sleepy half-lidded eyes, small yawn, drowsy relaxed expression",
}


def graph(prompt: str, prefix: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors",
                         "type": "krea2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": BASE_IMG}},
        "5": {"class_type": "LoadImageMask",
              "inputs": {"image": MASK_IMG, "channel": "red"}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["3", 0]}},
        "7": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["6", 0], "mask": ["5", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "9": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": "blurry, distorted face, extra eyes, watermark"}},
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


def submit(g: dict) -> str:
    body = json.dumps({"prompt": g, "client_id": uuid.uuid4().hex}).encode()
    req = urllib.request.Request(f"{API}/prompt", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["prompt_id"]


def wait(pid: str, timeout: float = 300) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with urllib.request.urlopen(f"{API}/history/{pid}", timeout=10) as r:
            if pid in json.loads(r.read()):
                return
        time.sleep(1.0)
    raise TimeoutError(pid)


def main() -> None:
    jobs = []
    for i, (name, prompt) in enumerate(VARIANTS.items()):
        jobs.append((name, submit(graph(prompt, name, 910300 + i))))
        print("submitted", name, flush=True)
    for name, pid in jobs:
        wait(pid)
        print("done", name, flush=True)


if __name__ == "__main__":
    main()
