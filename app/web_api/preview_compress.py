"""图像压缩预览路由：POST /api/preview/compress。"""

from __future__ import annotations

from typing import Callable

from fastapi import File, Form, Header, HTTPException, UploadFile

from app.image_compress import compress_image_bytes


def register_preview_compress_route(app, check_token: Callable) -> None:
    """Module-level registration so UploadFile resolves under Python 3.14 + Pydantic v2."""

    @app.post("/api/preview/compress")
    async def preview_compress(
        file: UploadFile = File(...),
        max_width: int = Form(768),
        quality: int = Form(85),
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="图片太大了，请换一张小一点的~")
        try:
            return compress_image_bytes(data, max_width=max_width, quality=quality)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"小助手读不懂这张图：{exc}") from exc
