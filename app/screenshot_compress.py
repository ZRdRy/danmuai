"""QPixmap → JPEG Base64 data URI for visual AI requests (W-REFACTOR-MAIN-001)."""

from __future__ import annotations

import base64
import io

from PIL import Image
from PyQt6.QtGui import QPixmap

IMAGE_MAX_WIDTH = 768
IMAGE_JPEG_QUALITY = 85


def compress_screenshot(
    pixmap: QPixmap,
    max_width: int = IMAGE_MAX_WIDTH,
    quality: int = IMAGE_JPEG_QUALITY,
) -> str:
    qimage = pixmap.toImage()
    width, height = qimage.width(), qimage.height()
    bits = qimage.bits()
    bits.setsize(height * qimage.bytesPerLine())
    pil_image = Image.frombuffer("RGBA", (width, height), bits, "raw", "BGRA", qimage.bytesPerLine(), 1)
    pil_image = pil_image.convert("RGB")
    if width > max_width:
        ratio = max_width / width
        new_height = int(height * ratio)
        pil_image = pil_image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"
