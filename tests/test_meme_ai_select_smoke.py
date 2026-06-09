"""Smoke test: meme AI select with a real project image."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.ai_client_support import AiProbeResult
from app.config_store import ConfigStore
from app.meme_barrage.ai_select import parse_meme_ai_selection
from app.meme_barrage.runnable import MemeAiSelectRunnable
from app.meme_barrage.service import MemeBarrageService
from app.screenshot_compress import compress_screenshot
from main import DanmuApp
from PyQt6.QtGui import QPixmap

ROOT = Path(__file__).resolve().parent.parent


def _pick_project_image() -> Path:
    for rel in (
        "web/static/image/qrcode_1779738450536.jpg",
        "image/qrcode_1779738450536.jpg",
        "data/pet/default/spritesheet.webp",
    ):
        path = ROOT / rel
        if path.is_file():
            return path
    pytest.skip("no project test image found")


@pytest.fixture
def project_pixmap(qapp):
    path = _pick_project_image()
    pixmap = QPixmap(str(path))
    if pixmap.isNull() or pixmap.width() <= 0:
        pytest.skip(f"invalid pixmap from {path}")
    return pixmap


def test_meme_ai_select_with_project_image(project_pixmap, tmp_path):
    uri = compress_screenshot(project_pixmap)
    assert uri.startswith("data:image/jpeg;base64,")

    candidates = [
        "扫码加群领福利",
        "这画面有个二维码",
        "完全无关的烂梗",
        "瓦批的一天启动",
    ]
    pick_count = 2

    worker = MagicMock()
    worker._stopping = MagicMock()
    worker._stopping.is_set.return_value = False
    worker.resolve_request_credentials.return_value = (
        "https://example.com/v1",
        "sk-test",
        "test-model",
        "openai",
    )
    worker._request_openai.return_value = AiProbeResult(
        signal="finished",
        message=json.dumps(["这画面有个二维码"], ensure_ascii=False),
    )

    cfg = ConfigStore(db_path=tmp_path / "meme_smoke.db")
    selected_holder: list[list[str]] = []
    error_holder: list[str] = []

    MemeAiSelectRunnable(
        worker=worker,
        config=cfg,
        image_data_uri=uri,
        candidates=candidates,
        pick_count=pick_count,
        on_success=selected_holder.append,
        on_error=error_holder.append,
    ).run()

    assert not error_holder, error_holder
    assert selected_holder == [["这画面有个二维码"]]

    parsed = parse_meme_ai_selection(
        json.dumps(["这画面有个二维码", "编造的"], ensure_ascii=False),
        candidates,
    )
    assert parsed == ["这画面有个二维码"]


def test_meme_ai_select_done_enqueues_filtered_only(project_pixmap, tmp_path):
    """入队路径：AI 成功时只写入筛选结果，不是全量 candidates。"""
    candidates = [
        "扫码加群领福利",
        "这画面有个二维码",
        "完全无关的烂梗",
        "瓦批的一天启动",
    ]
    cfg = ConfigStore(db_path=tmp_path / "meme_enqueue.db")
    danmu = DanmuApp.__new__(DanmuApp)
    danmu.config = cfg
    danmu.logger = MagicMock()
    service = MemeBarrageService(cfg)
    danmu._meme_barrage_service = service

    danmu._on_meme_ai_select_done(
        ["这画面有个二维码"],
        fallback_candidates=candidates,
        fallback_n=2,
    )

    batch = service.pop_display_batch(10)
    assert batch == ["这画面有个二维码"]
    assert len(batch) < len(candidates)


def test_meme_ai_select_live_api_if_configured(project_pixmap):
    import os

    from app.ai_client import AiWorker
    from app.meme_barrage.ai_select import (
        build_meme_select_system_prompt,
        build_meme_select_user_prompt,
    )
    from app.model_providers import resolve_api_transport

    appdata = os.environ.get("APPDATA", "")
    real_db = Path(appdata) / "DanmuAI" / "config.db"
    if not real_db.is_file():
        pytest.skip("no user DanmuAI config.db")

    uri = compress_screenshot(project_pixmap)
    candidates = [
        "扫码加群领福利",
        "这画面有个二维码",
        "完全无关的烂梗",
    ]

    real_cfg = ConfigStore(db_path=real_db)
    real_worker = AiWorker(real_cfg)
    creds = real_worker.resolve_request_credentials()
    if creds is None:
        pytest.skip("incomplete API credentials")

    sys_pt = build_meme_select_system_prompt(real_cfg)
    user_pt = build_meme_select_user_prompt(candidates, 2)
    endpoint, _, _, api_mode = creds
    transport = resolve_api_transport(endpoint, api_mode)

    if transport == "doubao":
        res = real_worker._request_doubao(
            uri, sys_pt, user_pt, "meme_select", 0, 0, 0.0, 0, resolved=creds, emit=False
        )
    else:
        res = real_worker._request_openai(
            uri, sys_pt, user_pt, "meme_select", 0, 0, 0.0, 0, resolved=creds, emit=False
        )

    assert res is not None and res.signal == "finished", res
    selected = parse_meme_ai_selection(res.message, candidates)
    assert selected, f"empty parse from: {res.message[:400]!r}"
    print(f"\n[live meme AI] image={_pick_project_image().name}")
    print(f"[live meme AI] raw={res.message[:400]!r}")
    print(f"[live meme AI] selected={selected}")
    print(f"[live meme AI] tokens in/out={res.input_tokens}/{res.output_tokens}")
