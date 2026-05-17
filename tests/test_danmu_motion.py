import pytest

from app.config_store import ConfigStore
from app.danmu_engine import DanmuEngine, DanmuItem
from app.reply_queue import AIReplyFIFOBuffer, QueuedReply


@pytest.fixture()
def config_store(tmp_path):
    db_path = tmp_path / "config.db"
    store = ConfigStore(db_path=db_path)
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "2")
    return store


def test_add_text_uses_screen_edge_not_global_queue(config_store, monkeypatch):
    engine = DanmuEngine(config_store)
    engine.set_screen_width(1000.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    engine.tracks[0].add(DanmuItem(content="old", x=120.0, width=260.0))

    monkeypatch.setattr("app.danmu_engine.random.uniform", lambda a, b: 100.0)

    item = engine.add_text("new")

    assert item is not None
    assert item.x == pytest.approx(1100.0)


def test_pick_track_prefers_least_congested_track(config_store):
    engine = DanmuEngine(config_store)
    engine.set_screen_width(1000.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    engine.tracks[0].add(DanmuItem(content="busy", x=100.0, width=780.0))
    engine.tracks[1].add(DanmuItem(content="free", x=100.0, width=10.0))

    track = engine._pick_track(DanmuItem(content="incoming", width=120.0))

    assert track is engine.tracks[1]


def test_max_on_screen_limits_new_danmu(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "5")
    store.set("max_on_screen", "2")

    engine = DanmuEngine(store)
    engine.set_screen_width(900.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    item1 = engine.add_text("first")
    item2 = engine.add_text("second")
    assert item1 is not None
    assert item2 is not None

    assert engine.current_display_count() == 2
    assert engine.right_zone_count() == 2

    for track in engine.tracks:
        for item in track.items:
            item.x = 700.0

    item3 = engine.add_text("third right zone full")
    assert item3 is None

    for track in engine.tracks:
        for item in track.items:
            item.x = 100.0
    item4 = engine.add_text("fourth right zone empty can add")
    assert item4 is not None


def test_max_on_screen_uses_visible_count_for_acceptance(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "5")
    store.set("max_on_screen", "2")

    engine = DanmuEngine(store)
    engine.set_screen_width(900.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    engine.tracks[0].add(DanmuItem(content="pending-a", x=950.0, width=50.0))
    engine.tracks[1].add(DanmuItem(content="pending-b", x=980.0, width=50.0))

    assert engine.current_display_count() == 2
    assert engine.visible_display_count() == 0
    assert engine.add_text("visible slot still open") is not None


def test_max_on_screen_zero_means_unlimited(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "5")
    store.set("max_on_screen", "0")

    engine = DanmuEngine(store)
    engine.set_screen_width(1920.0)
    engine.set_screen_height(1080.0)
    engine.reload_tracks()

    for i in range(10):
        item = engine.add_text(f"danmu{i}")
        assert item is not None


def test_acceleration_speeds_up_update(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "2")

    engine = DanmuEngine(store)
    engine.set_screen_width(1000.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    engine.tracks[0].add(DanmuItem(content="moving", x=500.0, width=100.0, speed=2.0))
    old_x = engine.tracks[0].items[0].x

    engine.trigger_acceleration(1)
    engine.update(1.0)

    new_x = engine.tracks[0].items[0].x
    assert new_x < old_x - 2.0


def test_reply_queue_purge_before_round():
    buf = AIReplyFIFOBuffer()
    buf.push(QueuedReply("p1", 1, 0, "old-a", screenshot_round=5))
    buf.push(QueuedReply("p1", 2, 0, "fresh", screenshot_round=10))
    buf.push(QueuedReply("p1", 3, 0, "old-b", screenshot_round=7))

    buf.purge_before_round(8)

    assert buf.size() == 1
    assert buf.pop().content == "fresh"


def test_right_zone_count(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "5")

    engine = DanmuEngine(store)
    engine.set_screen_width(900.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    engine.tracks[0].add(DanmuItem(content="r1", x=800.0, width=50.0))
    engine.tracks[0].add(DanmuItem(content="r2", x=700.0, width=50.0))
    engine.tracks[1].add(DanmuItem(content="m1", x=400.0, width=50.0))
    engine.tracks[1].add(DanmuItem(content="l1", x=100.0, width=50.0))
    engine.tracks[2].add(DanmuItem(content="pending", x=950.0, width=50.0))

    assert engine.right_zone_count() == 3
    assert engine.right_visible_count() == 2
    assert engine.visible_display_count() == 4
    assert engine.current_display_count() == 5


def test_drop_pending_items_keeps_visible_danmu(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "3")

    engine = DanmuEngine(store)
    engine.set_screen_width(900.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    engine.tracks[0].add(DanmuItem(content="visible-right", x=890.0, width=50.0))
    engine.tracks[1].add(DanmuItem(content="visible-mid", x=400.0, width=50.0))
    engine.tracks[2].add(DanmuItem(content="pending", x=930.0, width=50.0))

    dropped = engine.drop_pending_items()

    assert dropped == 1
    assert engine.current_display_count() == 2
    assert [item.content for track in engine.tracks for item in track.items] == [
        "visible-right",
        "visible-mid",
    ]


def test_needs_refill_allows_when_right_zone_empty(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "5")
    store.set("max_on_screen", "6")

    engine = DanmuEngine(store)
    engine.set_screen_width(900.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    engine.tracks[0].add(DanmuItem(content="l1", x=100.0, width=50.0))
    engine.tracks[1].add(DanmuItem(content="l2", x=150.0, width=50.0))
    engine.tracks[2].add(DanmuItem(content="m1", x=400.0, width=50.0))

    assert engine.current_display_count() == 3
    assert engine.right_zone_count() == 0
    assert engine.needs_refill() is True

    engine.tracks[3].add(DanmuItem(content="r1", x=700.0, width=50.0))
    engine.tracks[4].add(DanmuItem(content="r2", x=750.0, width=50.0))

    assert engine.current_display_count() == 5
    assert engine.right_zone_count() == 2
    assert engine.needs_refill() is True

    engine.tracks[0].add(DanmuItem(content="r3", x=800.0, width=50.0))
    assert engine.current_display_count() == 6
    assert engine.right_zone_count() == 3
    assert engine.needs_refill() is False


def test_needs_refill_ignores_offscreen_pending_right_zone(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "5")
    store.set("max_on_screen", "3")

    engine = DanmuEngine(store)
    engine.set_screen_width(900.0)
    engine.set_screen_height(400.0)
    engine.reload_tracks()

    engine.tracks[0].add(DanmuItem(content="pending-a", x=950.0, width=50.0))
    engine.tracks[1].add(DanmuItem(content="pending-b", x=980.0, width=50.0))
    engine.tracks[2].add(DanmuItem(content="visible", x=100.0, width=50.0))

    assert engine.current_display_count() == 3
    assert engine.right_zone_count() == 2
    assert engine.right_visible_count() == 0
    assert engine.visible_display_count() == 1
    assert engine.needs_refill() is True
