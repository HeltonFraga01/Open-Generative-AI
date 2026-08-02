"""ComfyUI custom node: Gemini image generation via NexusMind Antigravity proxy.

Calls the Gemini-native generateContent endpoint (not OpenAI-compatible),
parses inlineData base64, and returns a ComfyUI IMAGE tensor + status string.
"""

import json
import base64
import io
import urllib.request
import urllib.error
import torch
import numpy as np
from PIL import Image


class GeminiAntigravityImage:
    """Generate images via NexusMind Antigravity (Gemini-native API)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {
                    "default": "https://api.nexusmind.digital/antigravity/v1beta",
                    "multiline": False,
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                }),
                "model": ([
                    "gemini-3.1-flash-image",
                    "gemini-3.1-flash-image-preview",
                    "gemini-2.5-flash-image",
                    "gemini-2.5-flash-image-preview",
                    "gemini-3-pro-image",
                    "gemini-3-pro-image-preview",
                ], {
                    "default": "gemini-3.1-flash-image",
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                "aspect_ratio": ([
                    "auto", "1:1", "2:3", "3:2", "3:4", "4:3",
                    "4:5", "5:4", "9:16", "16:9", "21:9",
                ], {
                    "default": "1:1",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "status")
    FUNCTION = "generate"
    CATEGORY = "nexusmind_antigravity"

    def generate(self, base_url, api_key, model, prompt, aspect_ratio):
        url = f"{base_url}/models/{model}:generateContent"

        # Gemini v1beta generateContent does NOT accept aspectRatio in generationConfig.
        # Instead, append aspect ratio as a textual instruction in the prompt.
        effective_prompt = prompt
        if aspect_ratio != "auto":
            effective_prompt = f"{prompt}\n\nAspect ratio: {aspect_ratio}"

        body_dict = {
            "contents": [{
                "role": "user",
                "parts": [{"text": effective_prompt}],
            }],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
            },
        }

        body = json.dumps(body_dict).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })

        try:
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read().decode("utf-8"))

            image_tensor = None
            status_parts = []

            for candidate in result.get("candidates", []):
                parts = candidate.get("content", {}).get("parts", [])
                for part in parts:
                    if "inlineData" in part:
                        mime = part["inlineData"].get("mimeType", "image/jpeg")
                        b64 = part["inlineData"]["data"]
                        img_bytes = base64.b64decode(b64)
                        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                        arr = np.array(pil_img).astype(np.float32) / 255.0
                        image_tensor = torch.from_numpy(arr).unsqueeze(0)
                        status_parts.append(f"image: {pil_img.size[0]}x{pil_img.size[1]} {mime}")
                    elif "text" in part and part["text"]:
                        status_parts.append(f"text: {part['text'][:200]}")

            if image_tensor is not None:
                return (image_tensor, " | ".join(status_parts))

            # No inlineData — log the FULL response for visibility AND raise to surface in UI
            raw = json.dumps(result)[:500]
            print(f"[GeminiAntigravityImage] No image in response:\n{raw}")
            raise ValueError(f"No image in Gemini response (likely 200 with no inlineData): {raw}")

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            print(f"[GeminiAntigravityImage] HTTP {e.code} from upstream:\n{err_body}")
            raise RuntimeError(f"GeminiAntigravity HTTP {e.code}: {err_body}")
        except Exception as e:
            print(f"[GeminiAntigravityImage] Exception: {str(e)[:500]}")
            raise RuntimeError(f"GeminiAntigravity error: {str(e)[:500]}")


NODE_CLASS_MAPPINGS = {
    "GeminiAntigravityImage": GeminiAntigravityImage,
}

__all__ = ["NODE_CLASS_MAPPINGS"]
