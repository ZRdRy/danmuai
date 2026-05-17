import random
from dataclasses import dataclass, field
from collections import deque
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from app.translations import Translator


@dataclass
class DanmuItem:
    content: str
    persona: str = ""
    color: QColor = field(default_factory=lambda: QColor(255, 255, 255))
    x: float = 0.0
    y: float = 0.0
    speed: float = 3.0
    width: float = 0.0
    batch_id: int = 0
    _pixmap: QPixmap | None = field(default=None, repr=False, compare=False)


class Track:
    def __init__(self, y: float):
        self.y = y
        self.items: list[DanmuItem] = []

    def can_accept(self, item: DanmuItem, screen_width: float, min_gap: float = 150.0) -> bool:
        if not self.items:
            return True
        last = self.items[-1]
        w = last.width if last.width > 0 else (len(last.content) * 25.0)
        return last.x + w + min_gap < screen_width

    def rightmost_edge(self) -> float:
        if not self.items:
            return float('-inf')
        return max(it.x + (it.width if it.width > 0 else len(it.content) * 25.0) for it in self.items)

    def add(self, item: DanmuItem):
        item.y = self.y
        self.items.append(item)

    def update(self, speed_factor: float):
        i = 0
        while i < len(self.items):
            self.items[i].x -= self.items[i].speed * speed_factor
            if self.items[i].x + self.items[i].width <= 0:
                self.items[i]._pixmap = None
                self.items.pop(i)
            else:
                i += 1

    def drop_pending(self, screen_width: float) -> int:
        kept: list[DanmuItem] = []
        dropped = 0
        for item in self.items:
            if item.x >= screen_width:
                item._pixmap = None
                dropped += 1
            else:
                kept.append(item)
        self.items = kept
        return dropped


class DanmuEngine(QObject):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = False
        self.overlay = None
        self.recent: deque[str] = deque(maxlen=30)
        self.recent_exact_set: set[str] = set()
        self.tracks: list[Track] = []
        self.screen_width: float = 1920.0
        self.screen_height: float = 1080.0
        self._accel_peak = 2.0
        self._accel_total = 0
        self._accel_remaining = 0
        self._init_tracks()
        self._load_recent_from_history()

    def _load_recent_from_history(self):
        try:
            rows = self.config.conn.execute(
                "SELECT content FROM history ORDER BY id DESC LIMIT 30"
            ).fetchall()
            for row in reversed(rows):
                self.recent.append(row[0])
                self.recent_exact_set.add(row[0])
        except Exception:
            pass

    def _init_tracks(self):
        line_height = 40
        top_margin = 50
        bottom_margin = 80
        configured = self.config.get_int("danmu_lines", 0)
        try:
            val = int(configured)
        except Exception:
            val = 0
            
        if val > 0:
            line_count = val
        else:
            usable = self.screen_height - top_margin - bottom_margin
            line_count = max(4, min(15, int(usable / line_height)))
        start_y = top_margin
        self.tracks = [Track(float(start_y + i * line_height)) for i in range(line_count)]

    def set_screen_width(self, w: float):
        self.screen_width = w

    def set_screen_height(self, h: float):
        self.screen_height = h

    def add_item(self, item: DanmuItem) -> bool:
        if self._is_duplicate(item.content):
            return False
        self.recent.append(item.content)
        self.recent_exact_set.add(item.content)

        track = self._pick_track(item)
        if track is None:
            return False
        track.add(item)
        return True

    def add_text(self, content: str, persona: str = "", batch_id: int = 0) -> DanmuItem | None:
        MAX_LEN = 40 if Translator.get_language() == "en" else 15
        if len(content) > MAX_LEN:
            content = content[:MAX_LEN] + "..."

        if self._is_duplicate(content):
            return None

        if not self._can_accept_more():
            return None

        self.recent.append(content)
        self.recent_exact_set.add(content)

        item = DanmuItem(content=content, persona=persona, batch_id=batch_id)

        item.x = float(self.screen_width) + random.uniform(20.0, 90.0)
        item.speed = self.config.get_float("danmu_speed", 2.2)
        item.width = float(len(content) * 25.0)

        track = self._pick_track(item)
        if track is None:
            return None
        track.add(item)
        if self.overlay is not None:
            self.overlay.measure_item_width(item)
        return item

    def _calc_min_gap(self, item: DanmuItem) -> float:
        return max(80.0, item.width * 0.5)

    def _pick_track(self, item: DanmuItem) -> Track | None:
        if not self.tracks:
            return None

        min_gap = self._calc_min_gap(item)

        # 1. 空闲轨道优先
        idle = [t for t in self.tracks if not t.items]
        if idle:
            return random.choice(idle)

        # 2. 可接受轨道：按逆密度加权随机（items 越少权重越高）
        acceptable = [t for t in self.tracks if t.can_accept(item, self.screen_width, min_gap)]
        if acceptable:
            weights = [1.0 / (1 + len(t.items)) for t in acceptable]
            total = sum(weights)
            weights = [w / total for w in weights]
            return random.choices(acceptable, weights=weights, k=1)[0]

        # 3. 全满 fallback：选 rightmost_edge 最小的轨道
        best_track = min(self.tracks, key=lambda t: t.rightmost_edge())
        item.x = max(item.x, best_track.rightmost_edge() + random.uniform(50.0, 250.0))
        return best_track

    def max_on_screen(self) -> int:
        return self.config.get_int("max_on_screen", 0)
    def current_display_count(self) -> int:
        count = 0
        for track in self.tracks:
            count += len(track.items)
        return count

    def right_zone_count(self) -> int:
        threshold = self.screen_width * 2 / 3
        count = 0
        for track in self.tracks:
            for item in track.items:
                if item.x >= threshold:
                    count += 1
        return count

    def visible_display_count(self) -> int:
        count = 0
        for track in self.tracks:
            for item in track.items:
                if item.x < self.screen_width and item.x + item.width > 0:
                    count += 1
        return count

    def right_visible_count(self) -> int:
        threshold = self.screen_width * 2 / 3
        count = 0
        for track in self.tracks:
            for item in track.items:
                if threshold <= item.x < self.screen_width and item.x + item.width > 0:
                    count += 1
        return count

    def drop_pending_items(self) -> int:
        dropped = 0
        for track in self.tracks:
            dropped += track.drop_pending(self.screen_width)
        return dropped

    def _can_accept_more(self) -> bool:
        limit = self.max_on_screen()
        if limit <= 0:
            return True
        visible_total = self.visible_display_count()
        if visible_total < limit:
            return True
        right_target = max(1, limit // 3)
        return self.right_visible_count() < right_target

    def needs_refill(self) -> bool:
        limit = self.max_on_screen()
        if limit <= 0:
            return True
        total = self.visible_display_count()
        right_target = max(1, limit // 3)
        if total >= limit and self.right_visible_count() >= right_target:
            return False
        return True

    def trigger_acceleration(self, duration_frames: int = 60, peak: float = 2.0):
        self._accel_peak = peak
        self._accel_total = duration_frames
        self._accel_remaining = duration_frames

    def is_duplicate(self, text: str) -> bool:
        return self._is_duplicate(text)

    def _is_duplicate(self, content: str) -> bool:
        if content in self.recent_exact_set:
            return True
        if not self.recent:
            return False
        threshold = self.config.get_float("dedup_threshold", 0.85)
        for prev in self.recent:
            # 快速路径：完全相同
            if content == prev:
                return True
            # 快速跳过：长度差异太大时不需要计算相似度
            if threshold >= 1.0:
                continue
            len_diff = abs(len(content) - len(prev))
            max_len = max(len(content), len(prev))
            if max_len > 0 and len_diff / max_len > (1 - threshold):
                continue
            if self._similarity(content, prev) > threshold:
                return True
        return False

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        try:
            from Levenshtein import ratio
            return ratio(a, b)
        except ImportError:
            pass
        m, n = len(a), len(b)
        if m > n:
            a, b = b, a
            m, n = n, m
        prev = list(range(n + 1))
        for i in range(1, m + 1):
            curr = [i] + [0] * n
            for j in range(1, n + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
            prev = curr
        dist = prev[n]
        return 1 - dist / max(len(a), len(b))

    def update(self, speed_factor: float = 1.0):
        if self._accel_remaining > 0:
            progress = 1.0 - (self._accel_remaining / self._accel_total)
            if progress < 0.33:
                factor = 1.0 + (self._accel_peak - 1.0) * (progress / 0.33)
            else:
                factor = self._accel_peak - (self._accel_peak - 1.0) * ((progress - 0.33) / 0.67)
            speed_factor *= factor
            self._accel_remaining -= 1
        for track in self.tracks:
            track.update(speed_factor)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def reload_tracks(self):
        self._init_tracks()

    def track_count(self) -> int:
        return len(self.tracks)
    
    def get_display_count(self) -> int:
        return self.current_display_count()
