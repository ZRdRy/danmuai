"""Tests for scene brief and prompt dedup builders."""

from app.memory.store import SceneBriefStore
from app.memory_prompt_builder import (
    append_blocks_to_user_pt,
    build_prompt_dedup_block,
    build_scene_brief_block,
)


def _store_with_bullets() -> SceneBriefStore:
    store = SceneBriefStore()
    store.set_brief("团战中")
    store.record_displayed_bullet("这波可以", window=10, angle="scene_0")
    return store


def test_build_scene_brief_block_empty():
    assert build_scene_brief_block("") == ""


def test_build_scene_brief_block_contains_conflict_line():
    block = build_scene_brief_block("主播在打团")
    assert "【当前场景】" in block
    assert "主播在打团" in block
    assert "若与当前截图冲突" in block


def test_build_prompt_dedup_block_lists_recent():
    store = _store_with_bullets()
    block = build_prompt_dedup_block(store.dedup)
    assert "【最近弹幕去重】" in block
    assert "这波可以" in block


def test_append_blocks_skips_empty():
    assert append_blocks_to_user_pt("base", "", "  ") == "base"
