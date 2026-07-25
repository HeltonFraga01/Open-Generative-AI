"""ComfyUI custom node: NexusMind Grok Video generation (text-to-video & image-to-video).

Calls the NexusMind sub2api /v1/videos/generations endpoint (async),
polls /v1/videos/{request_id} until done, then downloads the video content
and saves it to the output folder.

API flow:
  1. POST /v1/videos/generations → {"request_id": "..."}
  2. GET /v1/videos/{request_id} → {"status": "done", "video": {"url": "/v1/videos/{id}/content"}}
  3. GET /v1/videos/{request_id}/content → video/mp4 binary

Image-to-video (I2V):
  - xAI expects "image": {"url": "https://..."} (public HTTP URL)
  - Data URLs and "image_url" string field are silently ignored
  - This node uploads the ComfyUI image tensor to MinIO (S3) and uses the
    public URL. Requires MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
    environment variables. Bucket defaults to "comfyui-images" (public-read).

Models:
  - grok-imagine-video (text-to-video, 8s)
  - grok-imagine-video-1.5 (image-to-video, 5s, accepts image {"url": "..."})
"""

import io
import os
import time
import json
import urllib.request
import urllib.error
importFolder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "output")
try:
    import folder_paths
    output_dir = folder_paths.get_output_directory()
except Exception:
    output_dir = importFolder


class NexusVideoNode:
    """NexusMind Grok Video generation node (async with polling)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {
                    "default": "https://api.nexusmind.digital/v1",
                    "tooltip": "NexusMind API base URL (sub2api endpoint)"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "NexusMind API key (sk-... format)"
                }),
                "model": ([
                    "grok-imagine-video",
                    "grok-imagine-video-1.5",
                ], {
                    "default": "grok-imagine-video-1.5",
                    "tooltip": "grok-imagine-video=8s text-to-video, grok-imagine-video-1.5=5s image-to-video"
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Text prompt describing the video"
                }),
                "resolution": (["540p", "720p"], {
                    "default": "720p"
                }),
                "duration": (["5", "8"], {
                    "default": "5"
                }),
                "auto_poll": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Automatically poll until video is ready"
                }),
                "poll_interval": ("INT", {
                    "default": 5,
                    "min": 2,
                    "max": 30,
                    "tooltip": "Seconds between polls"
                }),
                "max_wait_time": ("INT", {
                    "default": 600,
                    "min": 30,
                    "max": 1200,
                    "tooltip": "Maximum seconds to wait for video"
                }),
            },
            "optional": {
                "image": ("IMAGE", {
                    "tooltip": "Optional input image for image-to-video"
                }),
                "image_url": ("STRING", {
                    "default": "",
                    "tooltip": "Optional image URL for image-to-video (alternative to image input)"
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING",)
    RETURN_NAMES = ("video_url", "video_id", "status", "response_json",)
    FUNCTION = "generate"
    CATEGORY = "NexusMind"

    def _api_request(self, base_url, api_key, method, path, data=None, timeout=30, multipart_fields=None, files=None):
        url = f"{base_url.rstrip('/')}{path}"
        if files:
            # Multipart form-data upload
            import uuid
            boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
            body_parts = []
            # Add regular fields
            for key, value in (multipart_fields or {}).items():
                body_parts.append(f"--{boundary}\r\n".encode())
                body_parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
                body_parts.append(f"{value}\r\n".encode())
            # Add file fields
            for field_name, (filename, file_data, content_type) in files.items():
                body_parts.append(f"--{boundary}\r\n".encode())
                body_parts.append(
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode()
                )
                body_parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
                body_parts.append(file_data)
                body_parts.append(b"\r\n")
            body_parts.append(f"--{boundary}--\r\n".encode())
            body = b"".join(body_parts)
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            }
        elif data is not None:
            body = json.dumps(data).encode()
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        else:
            body = None
            headers = {"Authorization": f"Bearer {api_key}"}
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_msg = e.read().decode()
            raise RuntimeError(f"API Error {e.code}: {error_msg}")

    def _image_to_bytes(self, image_tensor):
        """Convert ComfyUI IMAGE tensor to JPEG bytes."""
        import numpy as np
        from PIL import Image
        import io

        if len(image_tensor.shape) == 4:
            img_np = image_tensor[0].cpu().numpy()
        else:
            img_np = image_tensor.cpu().numpy()
        img_np = (img_np * 255).clip(0, 255).astype(np.uint8)
        img = Image.fromarray(img_np)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=90)
        return buf.getvalue()

    def _upload_to_minio(self, img_bytes, filename="comfyui_input.jpg"):
        """Upload image to MinIO and return a public URL.
        
        MinIO credentials are read from environment variables:
        MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
        Falls back to no upload if MinIO is not configured.
        """
        import os
        import hashlib
        import time

        endpoint = os.environ.get("MINIO_ENDPOINT", "")
        access_key = os.environ.get("MINIO_ACCESS_KEY", "")
        secret_key = os.environ.get("MINIO_SECRET_KEY", "")
        bucket = os.environ.get("MINIO_BUCKET", "comfyui-images")
        secure = os.environ.get("MINIO_SECURE", "true").lower() == "true"

        if not all([endpoint, access_key, secret_key]):
            raise RuntimeError("MinIO not configured (need MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY)")

        from minio import Minio
        from io import BytesIO

        client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

        # Ensure bucket exists
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            import json
            policy = {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"]
                }]
            }
            client.set_bucket_policy(bucket, json.dumps(policy))

        # Generate unique object name
        content_hash = hashlib.md5(img_bytes).hexdigest()[:12]
        object_name = f"comfyui_{int(time.time())}_{content_hash}.jpg"

        buf = BytesIO(img_bytes)
        client.put_object(bucket, object_name, buf, len(img_bytes), content_type="image/jpeg")

        scheme = "https" if secure else "http"
        return f"{scheme}://{endpoint}/{bucket}/{object_name}"

    def generate(self, base_url, api_key, model, prompt, resolution, duration,
                 auto_poll, poll_interval, max_wait_time,
                 image=None, image_url=""):
        # xAI/Grok video generation API:
        # - image-to-video: JSON body with "image": {"url": "https://..."} (public URL)
        # - text-to-video: JSON body with "model" and "prompt" only
        # Data URLs and "image_url" (string) are silently ignored — the image
        # must be a publicly accessible HTTP(S) URL.

        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
        }

        if image is not None:
            # Image-to-video: upload to MinIO, get public URL, send as {"image": {"url": "..."}}
            try:
                img_bytes = self._image_to_bytes(image)
                public_url = self._upload_to_minio(img_bytes)
                payload["image"] = {"url": public_url}
            except Exception as e:
                return ("", "", f"Image upload failed: {e}", "{}")
        elif image_url and image_url.strip():
            # User provided a public image URL directly
            payload["image"] = {"url": image_url.strip()}

        # Step 1: Submit video generation request
        try:
            result = self._api_request(base_url, api_key, "POST", "/videos/generations", payload)
        except Exception as e:
            return ("", "", f"Submit failed: {e}", "{}")

        request_id = result.get("request_id", "")
        if not request_id:
            return ("", "", f"No request_id in response: {json.dumps(result)}", json.dumps(result))

        # If not auto_polling, return immediately
        if not auto_poll:
            return ("", request_id, "submitted", json.dumps(result))

        # Step 2: Poll for completion
        max_polls = max_wait_time // poll_interval
        status_info = {}
        
        for i in range(max_polls):
            time.sleep(poll_interval)
            try:
                status_info = self._api_request(base_url, api_key, "GET", f"/videos/{request_id}")
            except Exception as e:
                continue

            state = status_info.get("status", "unknown")
            progress = status_info.get("progress", 0)

            if state == "done":
                # Step 3: Get video URL and download
                video_meta = status_info.get("video", {})
                video_path = video_meta.get("url", "")
                
                if video_path:
                    # Download the video — video_path is like "/v1/videos/{id}/content"
                    # base_url is like "https://api.nexusmind.digital/v1"
                    # We need to use the root URL, not append to base_url
                    # Extract root from base_url (remove /v1 suffix if present)
                    root_url = base_url.rstrip('/')
                    if root_url.endswith('/v1'):
                        root_url = root_url[:-3]
                    
                    download_url = f"{root_url}{video_path}"
                    try:
                        req = urllib.request.Request(download_url, headers={
                            "Authorization": f"Bearer {api_key}"
                        })
                        resp = urllib.request.urlopen(req, timeout=60)
                        video_data = resp.read()
                        
                        # Save to output folder
                        filename = f"nexusmind_video_{request_id[:8]}.mp4"
                        filepath = os.path.join(output_dir, filename)
                        with open(filepath, "wb") as f:
                            f.write(video_data)
                        
                        return (
                            filepath,
                            request_id,
                            f"done: {len(video_data)} bytes saved to {filename}",
                            json.dumps(status_info)
                        )
                    except Exception as e:
                        return (
                            video_path,
                            request_id,
                            f"Video ready but download failed: {e}",
                            json.dumps(status_info)
                        )
                else:
                    return ("", request_id, "done but no video URL", json.dumps(status_info))
            
            elif state in ("error", "failed", "rejected"):
                return ("", request_id, f"failed: {json.dumps(status_info)[:300]}", json.dumps(status_info))

        # Timed out
        return ("", request_id, f"timeout after {max_wait_time}s", json.dumps(status_info))


# ComfyUI node registration
NODE_CLASS_MAPPINGS = {
    "NexusVideo": NexusVideoNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NexusVideo": "NexusVideo (NexusMind Grok)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
