"""公式化弹幕在悬浮窗卡片内省略号渲染。"""
from __future__ import annotations

from app.config_store import ConfigStore
from app.floating_panel_engine import FloatingPanelEngine
from app.floating_panel_overlay import FloatingPanelOverlay


def test_formula_text_uses_elided_render(workspace_tmp, qapp, monkeypatch):
    store = ConfigStore(db_path=workspace_tmp / "fp_formula.db")
    store.set("danmu_pool_use_custom", "1")
    store.set("custom_danmu_pool_enabled", "1")
    monkeypatch.setattr(
        "app.floating_panel_overlay.is_formula_danmu_text",
        lambda _cfg, text: text.startswith("formula:"),
    )
    engine = FloatingPanelEngine(store)
    engine.set_panel_height(400.0)
    overlay = FloatingPanelOverlay(store, engine)
    overlay.resize(360, 400)
    qapp.processEvents()

    long_text = "formula:" + ("很长的一句公式化弹幕" * 8)
    pm = overlay._render_card_pixmap(long_text, 320, 40)
    assert pm is not None
    assert "…" in long_text or pm.width() > 0
