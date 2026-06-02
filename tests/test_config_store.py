import sqlite3

import pytest
from app.config_store import ConfigStore


def test_set_batch_writes_all_keys(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    items = {"key_a": "val_a", "key_b": "val_b", "key_c": "val_c"}
    store.set_batch(items)

    assert store.get("key_a") == "val_a"
    assert store.get("key_b") == "val_b"
    assert store.get("key_c") == "val_c"

    store.close()


def test_set_batch_updates_cache(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("key_x", "old")
    store.set_batch({"key_x": "new", "key_y": "fresh"})

    assert store.get("key_x") == "new"
    assert store.get("key_y") == "fresh"

    store.close()


def test_set_batch_persists_to_db(tmp_path):
    db = tmp_path / "config.db"
    store1 = ConfigStore(db_path=db)
    store1.set_batch({"persist_a": "hello", "persist_b": "world"})
    store1.close()

    store2 = ConfigStore(db_path=db)
    assert store2.get("persist_a") == "hello"
    assert store2.get("persist_b") == "world"
    store2.close()


def test_first_run_seeds_config_defaults(tmp_path):
    store = ConfigStore(db_path=tmp_path / "new.db")
    assert store.get("danmu_speed") == "2"
    assert store.get("normal_reply_count") == "5"
    assert store.get("freshness") == ""
    assert store.get("eviction_mode") == "natural"
    assert store.get("hotkey") == "Ctrl+Shift+B"
    assert store.get("language") == "zh"
    assert store.get("danmu_pool_enabled") == "1"
    store.close()


def test_set_batch_single_commit(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    items = {f"key_{i}": f"value_{i}" for i in range(25)}
    store.set_batch(items)

    for i in range(25):
        assert store.get(f"key_{i}") == f"value_{i}"

    store.close()


def test_set_batch_overwrites_existing(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("shared", "original")
    store.set_batch({"shared": "updated"})

    assert store.get("shared") == "updated"

    store.close()


def test_set_batch_empty_dict(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("existing", "kept")
    store.set_batch({})

    assert store.get("existing") == "kept"

    store.close()


def test_set_does_not_pollute_cache_on_write_failure(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("stable_key", "original")
    inner = store.conn

    class _FailingConn:
        def execute(self, sql, params=()):
            raise sqlite3.OperationalError("database is locked")

        def commit(self):
            return inner.commit()

        def rollback(self):
            return inner.rollback()

        def close(self):
            return inner.close()

    store.conn = _FailingConn()

    with pytest.raises(sqlite3.OperationalError):
        store.set("stable_key", "new_value")

    assert store.get("stable_key") == "original"
    store.close()


def test_missing_config_file_has_friendly_notice(tmp_path):
    db_path = tmp_path / "fresh" / "config.db"
    store = ConfigStore(db_path=db_path)

    assert store.is_first_run is True
    assert "未找到配置文件" in store.get_startup_notice()
    assert store.get("normal_reply_count") == "5"

    store.close()

    store2 = ConfigStore(db_path=db_path)
    assert store2.is_first_run is False
    assert store2.get_startup_notice() == ""
    store2.close()


def test_config_value_with_default_language(tmp_path):
    from app.config_defaults import DEFAULT_LANGUAGE, config_value_with_default

    store = ConfigStore(db_path=tmp_path / "config.db")
    assert config_value_with_default(store, "language") == DEFAULT_LANGUAGE

    store.set("language", "")
    assert config_value_with_default(store, "language") == DEFAULT_LANGUAGE

    store.set("language", "en")
    assert config_value_with_default(store, "language") == "en"

    store.close()


def test_set_region_zeros_all_keys_when_size_non_positive(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set_region(10, 20, 100, 80)
    store.set_region(100, 200, 0, 0)

    assert store.get_region() == (0, 0, 0, 0)
    assert store.get("region_x") == "0"
    assert store.get("region_y") == "0"
    assert store.get("region_w") == "0"
    assert store.get("region_h") == "0"

    store.close()


def test_set_region_clear_persists_after_reopen(tmp_path):
    db = tmp_path / "config.db"
    store1 = ConfigStore(db_path=db)
    store1.set_region(50, 60, 320, 180)
    store1.set_region(0, 0, 0, 0)
    store1.close()

    store2 = ConfigStore(db_path=db)
    assert store2.get_region() == (0, 0, 0, 0)
    assert store2.get("region_x") == "0"
    assert store2.get("region_y") == "0"
    assert store2.get("region_w") == "0"
    assert store2.get("region_h") == "0"
    store2.close()


def test_config_store_repairs_stale_region_on_init(tmp_path):
    db = tmp_path / "config.db"
    store1 = ConfigStore(db_path=db)
    store1.set_batch({
        "region_x": "100",
        "region_y": "200",
        "region_w": "0",
        "region_h": "0",
    })
    store1.close()

    store2 = ConfigStore(db_path=db)
    assert store2.get_region() == (0, 0, 0, 0)
    assert store2.get("region_x") == "0"
    assert store2.get("region_y") == "0"
    assert store2.get("region_w") == "0"
    assert store2.get("region_h") == "0"
    store2.close()
