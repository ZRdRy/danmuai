from app.config_defaults import DEFAULT_LANGUAGE, seed_config_defaults
from app.config_store import ConfigStore


def test_seed_includes_language_field_when_added(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("language", "")

    seed_config_defaults(store)

    assert store.get("language") == DEFAULT_LANGUAGE
    store.close()
