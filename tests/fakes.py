"""Shared test doubles for DanmuApp and related components."""

import json
from types import SimpleNamespace


class FakeLogger:
    def __init__(self):
        self.debug_messages = []
        self.info_messages = []
        self.error_messages = []
        self.warning_messages = []

    @staticmethod
    def _format(message, args):
        if not args:
            return message
        try:
            return message % args
        except Exception:
            return f"{message} {args!r}"

    def debug(self, message, *args):
        self.debug_messages.append(self._format(message, args))

    def info(self, message, *args):
        self.info_messages.append(self._format(message, args))

    def error(self, message, *args):
        self.error_messages.append(self._format(message, args))

    def warning(self, message, *args):
        self.warning_messages.append(self._format(message, args))


class FakeConfig:
    def __init__(self, values=None):
        self.values = dict(values or {})
        if values and "_api_key" in values:
            self._api_key = values["_api_key"]
        else:
            self._api_key = self.values.get("api_key", self.values.get("_api_key", ""))

    def get(self, key, default=""):
        return self.values.get(key, default)

    def get_int(self, key, default=0):
        val = self.get(key)
        if val == "" or val is None:
            return int(default)
        return int(val)

    def get_float(self, key, default=0.0):
        val = self.get(key)
        if val == "" or val is None:
            return float(default)
        return float(val)

    def set(self, key, value):
        self.values[key] = value

    def set_batch(self, items):
        self.values.update(items)

    def set_api_key(self, key):
        self._api_key = key
        self.values["api_key_encrypted"] = "enc"

    def set_default_model_id(self, model_id):
        self.values["default_model_id"] = model_id

    def set_custom_models(self, models):
        self.values["custom_models"] = models

    def get_region(self):
        region = self.values.get("region")
        if region is not None:
            return region
        return (
            self.get_int("region_x", 0),
            self.get_int("region_y", 0),
            self.get_int("region_w", 0),
            self.get_int("region_h", 0),
        )

    def set_region(self, x, y, w, h):
        self.values["region_x"] = str(x)
        self.values["region_y"] = str(y)
        self.values["region_w"] = str(w)
        self.values["region_h"] = str(h)

    def get_default_model_id(self):
        return str(self.values.get("default_model_id", self.values.get("model", "")))

    def get_api_key(self):
        if self._api_key:
            return str(self._api_key)
        return str(self.values.get("api_key", ""))

    def get_mic_api_key(self):
        return str(self.values.get("_mic_api_key", self.values.get("mic_api_key", "")))

    def set_mic_api_key(self, key):
        self.values["_mic_api_key"] = key
        self.values["mic_api_key_encrypted"] = "enc"

    def get_custom_models(self):
        return list(self.values.get("custom_models", []))

    def get_json(self, key: str, default=None):
        val = self.get(key)
        if not val:
            return default if default is not None else {}
        return json.loads(val)

    def set_json(self, key: str, value):
        self.values[key] = json.dumps(value, ensure_ascii=False)


class FakeLifetimeStats:
    def add_danmu(self, count: int = 1) -> None:
        pass

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        pass

    def flush_pending(self) -> None:
        pass

    def flush_runtime(self, session_sec: float) -> bool:
        return True

    def snapshot(self, *, session_runtime_sec: float = 0.0) -> dict:
        return {
            "lifetime_danmu_count": 0,
            "lifetime_runtime_sec": 0.0,
            "lifetime_input_tokens": 0,
            "lifetime_output_tokens": 0,
            "lifetime_total_tokens": 0,
        }


class FakeSessionRunLog:
    def begin(self, **_kwargs) -> None:
        pass

    def complete(self, **_kwargs) -> None:
        pass

    def list_dicts_newest_first(self, limit: int = 20) -> list[dict]:
        return []


class FakeTrack:
    def __init__(self):
        self.items = []


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.running = False
        self.dropped_pending = 0
        self.screen_width = 1920.0
        self.screen_height = 1080.0
        self._accel_remaining = 0
        self._accel_peak = 1.0
        self.tracks = []
        self._config_values = {}

    def add_text(self, content, persona, batch_id=0, scene_generation=0, *, skip_dedup=False, **_kwargs):
        self.calls.append((content, persona))
        return SimpleNamespace(
            content=content,
            persona=persona,
            batch_id=batch_id,
            scene_generation=scene_generation,
            x=2000.0,
            y=90.0,
            speed=2.2,
        )

    def clear_dedup_window(self):
        pass

    def drop_pending_below_generation(self, min_generation):
        return 0

    def drop_items_with_batch_id(self, batch_id):
        return 0

    def visible_display_count(self):
        return 0

    def min_on_screen(self):
        return self._config_values.get("min_on_screen", 5)

    def danmu_pool_enabled(self):
        return bool(self._config_values.get("danmu_pool_enabled", False))

    def deficit_below_min(self):
        return 0

    def current_display_count(self):
        return 0

    def get_display_count(self):
        return 0

    def right_zone_count(self):
        return 0

    def needs_refill(self):
        return True

    def drop_pending_items(self):
        self.dropped_pending += 1
        return 1

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


class DedupFakeEngine(FakeEngine):
    def __init__(self, duplicate_text: str):
        super().__init__()
        self.duplicate_text = duplicate_text
        self.running = True

    def add_text(self, content, persona, batch_id=0, scene_generation=0, *, skip_dedup=False, **_kwargs):
        if not skip_dedup and content == self.duplicate_text:
            return None
        return super().add_text(
            content,
            persona,
            batch_id=batch_id,
            scene_generation=scene_generation,
            skip_dedup=skip_dedup,
        )

    def is_duplicate(self, content: str) -> bool:
        return content == self.duplicate_text


class FakeCapturer:
    def __init__(self, pixmap=None):
        self._pixmap = pixmap

    def grab(self):
        return self._pixmap


class FakePixmap:
    def __init__(self, scene_byte, *, is_null: bool = False, width: int = 200, height: int = 200):
        self.scene_byte = scene_byte
        self._is_null = is_null
        self._width = width
        self._height = height

    def isNull(self):
        return self._is_null

    def width(self):
        return self._width

    def height(self):
        return self._height


class FakeHistoryWriter:
    def __init__(self):
        self.calls = []

    def enqueue(self, content, persona, round_num, image_bytes=None):
        self.calls.append((content, persona, round_num, image_bytes))

    def stop(self):
        pass


class FakeTimer:
    def __init__(self):
        self.active = False
        self.started = 0
        self.stopped = 0
        self._interval = 800
        self._single_shot = False

    def isActive(self):
        return self.active

    def start(self, ms=0):
        self.active = True
        self.started += 1

    def stop(self):
        self.active = False
        self.stopped += 1

    def interval(self):
        return self._interval

    def setInterval(self, ms):
        self._interval = ms

    def setSingleShot(self, val):
        self._single_shot = val
