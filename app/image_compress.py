"""In-memory JPEG compression for web preview (no disk writes)."""

from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image

from app.jpeg_resize import resize_rgb_to_jpeg_bytes


def compress_image_bytes(
    data: bytes,
    max_width: int = 768,
    quality: int = 85,
) -> dict[str, Any]:
    pil_image = Image.open(io.BytesIO(data))
    orig_width, orig_height = pil_image.size
    _, jpeg_bytes, final_width, final_height = resize_rgb_to_jpeg_bytes(
        pil_image,
        max_width=max_width,
        quality=quality,
    )
    b64 = base64.b64encode(jpeg_bytes).decode("utf-8")

    return {
        "orig_w": orig_width,
        "orig_h": orig_height,
        "out_w": final_width,
        "out_h": final_height,
        "jpeg_bytes": len(jpeg_bytes),
        "base64_kb": len(b64) / 1024,
        "preview_data_url": f"data:image/jpeg;base64,{b64}",
    }
