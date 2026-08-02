"""ComfyUI custom node: Pollinations.ai free image generation.

Calls the Pollinations.ai GET endpoint (no auth required) to generate
images from text prompts. Returns a ComfyUI IMAGE tensor + status string.

Endpoint: GET https://image.pollinations.ai/prompt/{prompt}?width=...&height=...&model=...&seed=...&nologo=true
Response: JPEG image data directly (not JSON).
"""

import urllib.request
import urllib.parse
import io
import torch
import numpy as np
from PIL import Image


class PollinationsImage:
    """Generate images via Pollinations.ai free API (no auth, no rate limit)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                "model": ([
                    "sana",
                    "flux",
                    "turbo",
                ], {
                    "default": "sana",
                }),
                "width": ("INT", {
                    "default": 1024,
                    "min": 256,
                    "max": 2048,
                    "step": 64,
                }),
                "height": ("INT", {
                    "default": 576,
                    "min": 256,
                    "max": 2048,
                    "step": 64,
                }),
                "seed": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 2**32 - 1,
                }),
                "nologo": ("BOOLEAN", {
                    "default": True,
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "status")
    FUNCTION = "generate"
    CATEGORY = "pollinations"

    def generate(self, prompt, model, width, height, seed, nologo):
        # URL-encode the prompt
        encoded_prompt = urllib.parse.quote(prompt, safe="")

        # Build query params
        params = {
            "model": model,
            "width": str(width),
            "height": str(height),
            "nologo": "true" if nologo else "false",
        }
        if seed >= 0:
            params["seed"] = str(seed)

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{query_string}"

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "ComfyUI-Pollinations/1.0",
                "Accept": "image/*",
            })
            resp = urllib.request.urlopen(req, timeout=120)
            img_bytes = resp.read()

            if len(img_bytes) < 100:
                raise ValueError(f"Response too small ({len(img_bytes)} bytes) — likely an error page")

            pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            arr = np.array(pil_img).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(arr).unsqueeze(0)

            status = f"image: {pil_img.size[0]}x{pil_img.size[1]} JPEG {len(img_bytes)}B | model={model}"
            return (image_tensor, status)

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            print(f"[PollinationsImage] HTTP {e.code}:\n{err_body}")
            raise RuntimeError(f"Pollinations HTTP {e.code}: {err_body}")
        except Exception as e:
            print(f"[PollinationsImage] Exception: {str(e)[:500]}")
            raise RuntimeError(f"Pollinations error: {str(e)[:500]}")


import urllib.error

NODE_CLASS_MAPPINGS = {
    "PollinationsImage": PollinationsImage,
}

__all__ = ["NODE_CLASS_MAPPINGS"]
