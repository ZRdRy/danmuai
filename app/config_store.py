"""SQLite 配置存储：内存缓存 + WAL 并发读 + Fernet 加密 API Key。

设计要点：
- **%APPDATA%/DanmuAI/config.db** 持久化；**%APPDATA%/DanmuAI/.key** 为 Fernet 对称密钥。
- **密钥丢失或 .key 被删/损坏后重新生成**：旧 api_key_encrypted 无法解密，等同不可恢复（须重新填写 Key）。
- **向后兼容**：无 cryptography 时退化为 base64 存 api_key_encoded（仅编码非加密）；有 Fernet 后写入 encrypted 并删除 encoded。
- **WAL + busy_timeout**：允许多读者与单写者共存，写路径用 _write_lock 串行化避免 cache/DB 不一致。
- **set_batch**：显式事务，commit 成功后才更新 _cache，失败 rollback。

调用方：DanmuApp、ConfigService.apply_web_payload、各模块读配置。

存储边界：新业务模块禁止继续共享 ConfigStore 的 SQLite 连接；历史/模板等应经既有门面访问，见 docs/phase1-boundary-rules.md。
"""
import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

from base64 import b64decode, b64encode

from app.translations import tr

logger = logging.getLogger(__name__)

_SENSITIVE_CONFIG_KEYS = frozenset(
    {
        "api_key_encrypted",
        "mic_api_key_encrypted",
        "tts_api_key_encrypted",
        "custom_models",
        "api_key",
    }
)


def _redact_config_value_for_log(key: str, value: str) -> str:
    if key in _SENSITIVE_CONFIG_KEYS or "encrypted" in key.lower() or key.endswith("_key"):
        return "***"
    if len(value) > 120:
        return f"{value[:40]}…({len(value)} chars)"
    return value


CONFIG_DIR = Path(os.environ.get("APPDATA", ".")) / "DanmuAI"
CONFIG_FILE = CONFIG_DIR / "config.db"
_KEY_FILE = CONFIG_DIR / ".key"


def _restrict_key_file_permissions(path: Path):
    """Set file permissions so only the owner can read/write (best-effort)."""
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


class ConfigStore:
    """应用配置与 API Key 的 SQLite 门面；读走内存 _cache，写持 _write_lock。"""

    def __init__(self, db_path: Path = CONFIG_FILE):
        self.is_first_run = not db_path.exists()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._key_file = db_path.parent / ".key"
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        # WAL：读不阻塞写、写不阻塞读；Web/主线程并发读配置时减少 database is locked
        # 选择原因：主线程读配置 + HTTP 线程写配置并发场景，WAL 比 DELETE 模式更适合
        self.conn.execute("PRAGMA journal_mode=WAL")
        # 写冲突时等待最多 5s 而非立即失败（与 _write_lock 双保险）
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_db()
        self._cache: dict[str, str] = {}
        self._load_cache()
        # 所有 REPLACE/commit 串行化，保证 _cache 与 DB 同事务一致
        self._write_lock = threading.Lock()
        self._closed = False
        # W-FP-V2-002：须在 seed 之前写回，避免 seed 先落 danmu_render_mode=scrolling 盖掉遗留 display_mode
        self._migrate_legacy_display_mode_to_render_mode()
        if self.is_first_run or not self.get("danmu_speed"):
            from app.config_defaults import seed_config_defaults

            seed_config_defaults(self)
            self._load_cache()
        self._fernet = self._init_fernet()
        self._repair_stale_region_if_needed()
        self._normalize_legacy_display_mode()

    def _migrate_legacy_display_mode_to_render_mode(self) -> None:
        # W-FP-V2-002：遗留 display_mode（overlay/floating_panel/both）→ danmu_render_mode 写回
        from app.config_defaults import migrate_legacy_display_mode_to_render_mode

        migrate_legacy_display_mode_to_render_mode(self)

    def _normalize_legacy_display_mode(self) -> None:
        from app.application.config_service import normalize_legacy_display_mode

        legacy_mode = str(self.get("danmu_display_mode", ""))
        items = {"danmu_display_mode": legacy_mode}
        normalize_legacy_display_mode(items)
        normalized_mode = str(items.get("danmu_display_mode", "")).strip().lower()
        if normalized_mode and normalized_mode != legacy_mode.strip().lower():
            self.set("danmu_display_mode", normalized_mode)

    def get_startup_notice(self) -> str:
        """首装会话返回本地化引导文案；config.db 已存在时恒为空（二次启动不误弹）。"""
        if self.is_first_run:
            return tr("config.startup_notice")
        return ""

    def _init_fernet(self):
        """加载或生成 %APPDATA%/DanmuAI/.key；校验失败则换新 key（旧密文永久不可读）。"""
        if not _HAS_CRYPTO:
            logger.warning(tr("config.crypto_missing"))
            return None
        if self._key_file.exists():
            key = self._key_file.read_bytes()
            try:
                f = Fernet(key)
                # Verify key is valid by a dummy round-trip
                f.decrypt(f.encrypt(b"test"))
                return f
            except Exception:
                logger.warning(
                    tr("config.crypto_key_regenerated")
                )
                # Key corrupted, generate a new one (old encrypted data becomes unreadable)
                pass
        key = Fernet.generate_key()
        self._key_file.write_bytes(key)
        _restrict_key_file_permissions(self._key_file)
        return Fernet(key)

    def _init_db(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "time TEXT, persona TEXT, content TEXT, image BLOB, round INT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS templates (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "name TEXT, version INT, system_pt TEXT, user_pt TEXT, created_at TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS session_runs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "started_at REAL NOT NULL, "
            "ended_at REAL NOT NULL, "
            "model TEXT NOT NULL DEFAULT '', "
            "input_tokens INTEGER NOT NULL DEFAULT 0, "
            "output_tokens INTEGER NOT NULL DEFAULT 0, "
            "danmu_count INTEGER NOT NULL DEFAULT 0)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS meme_barrage_library ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "text TEXT NOT NULL UNIQUE, "
            "source_tag TEXT, "
            "remote_id INTEGER, "
            "collected_at REAL NOT NULL)"
        )
        self.conn.commit()

    def _load_cache(self):
        rows = self.conn.execute("SELECT key, value FROM config").fetchall()
        self._cache = {k: v for k, v in rows}

    # --- 通用配置读写 ---

    def get(self, key: str, default: str = "") -> str:
        return self._cache.get(key, default)

    def set(self, key: str, value: str):
        """单键写入：commit 成功后再更新 _cache（与 set_batch 一致，失败不污染缓存）。"""
        with self._write_lock:
            try:
                self.conn.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
                self.conn.commit()
                self._cache[key] = value
            except sqlite3.OperationalError as e:
                safe_value = _redact_config_value_for_log(key, value)
                logger.error(
                    tr("config.write_failed").format(key=key, value=safe_value, error=e)
                )
                raise

    def set_batch(self, items: dict[str, str]):
        """批量写入：单事务内多条 REPLACE，失败 rollback 且不改 _cache。

        Web PUT /api/config 一次提交多键，避免半写入导致 UI 与运行时状态不一致。
        """
        with self._write_lock:
            try:
                pairs = list(items.items())
                if pairs:
                    self.conn.executemany(
                        "REPLACE INTO config (key, value) VALUES (?, ?)",
                        pairs,
                    )
                self.conn.commit()
                # Only update cache after successful commit
                for k, v in items.items():
                    self._cache[k] = v
            except sqlite3.OperationalError as e:
                self.conn.rollback()
                logger.error(tr("config.batch_write_failed").format(error=type(e).__name__))
                raise

    @contextmanager
    def with_write_lock(self):
        """Acquire the SQLite write lock for atomic conn operations (W-CONC-001).

        用于同包模块（``HistoryWriter`` 等）批量 ``executemany`` + ``commit``。
        与 ``set`` / ``set_batch`` 共享同一把 ``self._write_lock``，避免主线程
        持锁时后台线程 ``conn.executemany`` 抛 ``database is locked`` 永久丢数据。

        限制：
            - 仅供同包模块在 SQLite 写入临界区使用；**禁止** HTTP 线程、Web
              路由、其他包模块直接调用（会阻塞主线程 SET 路径）。
            - 进程内临界区（``threading.Lock``），不跨进程；多实例仍受
              ``SingleInstanceGuard`` 串行化。
            - 不可重入：同线程内嵌套调用会死锁。
        """
        with self._write_lock:
            yield self.conn

    def get_int(self, key: str, default: int = 0) -> int:
        val = self.get(key)
        return int(val) if val else default

    def get_float(self, key: str, default: float = 0.0) -> float:
        val = self.get(key)
        return float(val) if val else default

    def get_json(self, key: str, default: list | dict | None = None) -> list | dict:
        val = self.get(key)
        return json.loads(val) if val else (default or {})

    def set_json(self, key: str, value: list | dict):
        self.set(key, json.dumps(value, ensure_ascii=False))

    # --- API Key (Fernet encrypted) ---

    def _encrypted_get(self, encrypted_key: str, encoded_key: str) -> str:
        """读取加密或 legacy base64 编码的 API Key 明文。"""
        encrypted = self.get(encrypted_key, "")
        if encrypted and _HAS_CRYPTO and self._fernet:
            try:
                return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
            except Exception:
                logger.warning(tr("config.decrypt_failed"))
        encoded = self.get(encoded_key, "")
        if not encoded:
            return ""
        try:
            plaintext = b64decode(encoded).decode("utf-8")
        except Exception:
            return ""
        # W-MEDLOW-004：安装 cryptography 后首次读取 legacy base64 时自动升级为 Fernet。
        if _HAS_CRYPTO and self._fernet and not encrypted:
            try:
                self._encrypted_set(encrypted_key, encoded_key, plaintext)
            except Exception as exc:
                logger.warning(
                    "config key auto-upgrade failed key=%s error=%s",
                    encrypted_key,
                    type(exc).__name__,
                )
        elif encrypted_key == "api_key_encrypted" and _HAS_CRYPTO and self._fernet is None:
            logger.warning(tr("config.insecure_read"))
        return plaintext

    def _encrypted_set(self, encrypted_key: str, encoded_key: str, key: str) -> None:
        """写入 API Key：Fernet 加密或退化为 base64；持 _write_lock 保证 cache/DB 一致。"""
        with self._write_lock:
            if _HAS_CRYPTO and self._fernet:
                encrypted = self._fernet.encrypt(key.encode("utf-8")).decode("utf-8")
                try:
                    self.conn.execute(
                        "REPLACE INTO config (key, value) VALUES (?, ?)",
                        (encrypted_key, encrypted),
                    )
                    if encoded_key in self._cache:
                        self.conn.execute("DELETE FROM config WHERE key=?", (encoded_key,))
                        self._cache.pop(encoded_key, None)
                    self.conn.commit()
                    self._cache[encrypted_key] = encrypted
                except sqlite3.OperationalError as e:
                    self.conn.rollback()
                    logger.error(tr("config.api_key_write_failed").format(error=type(e).__name__))
                    raise
            else:
                logger.warning(tr("config.insecure_store"))
                encoded = b64encode(key.encode("utf-8")).decode("utf-8")
                # 已持 _write_lock；勿调 self.set()（threading.Lock 会死锁，见 ISSUE-042）
                try:
                    self.conn.execute(
                        "REPLACE INTO config (key, value) VALUES (?, ?)",
                        (encoded_key, encoded),
                    )
                    self.conn.commit()
                    self._cache[encoded_key] = encoded
                except sqlite3.OperationalError as e:
                    self.conn.rollback()
                    logger.error(tr("config.api_key_write_failed").format(error=type(e).__name__))
                    raise

    def get_api_key(self) -> str:
        """读取明文 API Key：优先 Fernet 解密 api_key_encrypted，否则回退 base64 的 api_key_encoded。"""
        return self._encrypted_get("api_key_encrypted", "api_key_encoded")

    def set_api_key(self, key: str):
        """写入 API Key：有 Fernet 则加密存 api_key_encrypted 并清除旧 base64 行。"""
        self._encrypted_set("api_key_encrypted", "api_key_encoded", key)

    def get_tts_api_key(self) -> str:
        """读弹幕专用 TTS API Key（tts_api_key_encrypted）。"""
        return self._encrypted_get("tts_api_key_encrypted", "tts_api_key_encoded")

    def set_tts_api_key(self, key: str) -> None:
        """写入 TTS API Key（加密存储）。"""
        self._encrypted_set("tts_api_key_encrypted", "tts_api_key_encoded", key)

    def get_mic_api_key(self) -> str:
        """读麦克风专用 API Key（mic_api_key_encrypted）。"""
        return self._encrypted_get("mic_api_key_encrypted", "mic_api_key_encoded")

    def set_mic_api_key(self, key: str) -> None:
        """写入麦克风专用 API Key（加密存储）。"""
        self._encrypted_set("mic_api_key_encrypted", "mic_api_key_encoded", key)

    # --- 选区持久化 ---

    @staticmethod
    def _normalize_region(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
        """无有效尺寸时四键一致归零（全屏 / 未选区）。"""
        if w <= 0 or h <= 0:
            return 0, 0, 0, 0
        return x, y, w, h

    def _repair_stale_region_if_needed(self) -> None:
        x = self.get_int("region_x", 0)
        y = self.get_int("region_y", 0)
        w = self.get_int("region_w", 0)
        h = self.get_int("region_h", 0)
        if (w <= 0 or h <= 0) and (x, y, w, h) != (0, 0, 0, 0):
            self.set_region(0, 0, 0, 0)

    def get_region(self) -> tuple[int, int, int, int]:
        x = self.get_int("region_x", 0)
        y = self.get_int("region_y", 0)
        w = self.get_int("region_w", 0)
        h = self.get_int("region_h", 0)
        return self._normalize_region(x, y, w, h)

    def set_region(self, x: int, y: int, w: int, h: int):
        x, y, w, h = self._normalize_region(x, y, w, h)
        self.set_batch({
            "region_x": str(x),
            "region_y": str(y),
            "region_w": str(w),
            "region_h": str(h),
        })

    # --- Custom model profiles (apiKey encrypted inline in JSON) ---

    def _custom_model_key_is_encrypted(self, value: str) -> bool:
        """True when value is a Fernet token decryptable with this store's .key."""
        if not value or not _HAS_CRYPTO or not self._fernet:
            return False
        try:
            self._fernet.decrypt(value.encode("utf-8"))
            return True
        except Exception:
            return False

    def _encrypt_custom_model_api_key(self, key: str) -> str:
        """Encrypt custom-model apiKey with the same Fernet key as api_key_encrypted."""
        if not key:
            return ""
        if _HAS_CRYPTO and self._fernet:
            return self._fernet.encrypt(key.encode("utf-8")).decode("utf-8")
        logger.warning(tr("config.insecure_store"))
        return b64encode(key.encode("utf-8")).decode("utf-8")

    def _decrypt_custom_model_api_key(self, stored: str) -> str:
        """Decrypt Fernet token; legacy plaintext or base64-only values pass through."""
        if not stored:
            return ""
        if self._custom_model_key_is_encrypted(stored):
            return self._fernet.decrypt(stored.encode("utf-8")).decode("utf-8")
        try:
            decoded = b64decode(stored).decode("utf-8")
        except Exception:
            return stored
        if decoded.startswith("sk-") or decoded.startswith("Bearer "):
            return decoded
        return stored

    def get_custom_models(self) -> list:
        """Return custom models with decrypted apiKey; upgrade legacy plaintext on read."""
        raw = self.get_json("custom_models", [])
        if not isinstance(raw, list):
            return []
        result: list[dict] = []
        needs_upgrade = False
        for model in raw:
            if not isinstance(model, dict):
                continue
            entry = dict(model)
            stored_key = (entry.get("apiKey") or "").strip()
            if stored_key:
                entry["apiKey"] = self._decrypt_custom_model_api_key(stored_key)
                if not self._custom_model_key_is_encrypted(stored_key):
                    needs_upgrade = True
            result.append(entry)
        if needs_upgrade:
            self.set_custom_models(result)
        return result

    def set_custom_models(self, models: list):
        """Persist custom models; each apiKey is Fernet-encrypted before JSON serialization."""
        encrypted: list[dict] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            entry = dict(model)
            plain_key = (entry.get("apiKey") or "").strip()
            if plain_key:
                if self._custom_model_key_is_encrypted(plain_key):
                    entry["apiKey"] = plain_key
                else:
                    entry["apiKey"] = self._encrypt_custom_model_api_key(plain_key)
            encrypted.append(entry)
        self.set_json("custom_models", encrypted)

    def get_custom_danmu_pool(self) -> list[str]:
        raw = self.get_json("custom_danmu_pool", [])
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    def set_custom_danmu_pool(self, items: list[str]) -> None:
        self.set_json("custom_danmu_pool", items)
        self._invalidate_formula_text_cache()

    # --- Meme barrage library (meme_barrage_library table) ---

    def _conn_usable(self) -> bool:
        """False after close(); HTTP 退出竞态读库时避免 ProgrammingError。"""
        return not getattr(self, "_closed", False)

    def meme_barrage_library_count(self) -> int:
        if not self._conn_usable():
            return 0
        try:
            row = self.conn.execute("SELECT COUNT(*) FROM meme_barrage_library").fetchone()
        except sqlite3.ProgrammingError:
            return 0
        if not row or row[0] is None:
            return 0
        return int(row[0])

    def meme_barrage_library_clear(self) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM meme_barrage_library")
            self.conn.commit()
        self._invalidate_formula_text_cache()

    def meme_barrage_library_insert_many(
        self,
        items: list[tuple[str, str | None, int | None]],
        *,
        collected_at: float,
        max_rows: int,
    ) -> int:
        if not items:
            return 0
        added = 0
        with self._write_lock:
            for text, source_tag, remote_id in items:
                text = str(text).strip()
                if not text:
                    continue
                try:
                    cur = self.conn.execute(
                        "INSERT OR IGNORE INTO meme_barrage_library "
                        "(text, source_tag, remote_id, collected_at) VALUES (?, ?, ?, ?)",
                        (text, source_tag, remote_id, collected_at),
                    )
                    if cur.rowcount:
                        added += 1
                except sqlite3.Error:
                    continue
            self._trim_meme_barrage_library_locked(max_rows)
            self.conn.commit()
        self._invalidate_formula_text_cache()
        return added

    def meme_barrage_library_all_texts(self) -> list[str]:
        """All meme library lines for formula-text cache warm-up (max LIBRARY_MAX_ROWS)."""
        if not self._conn_usable():
            return []
        try:
            from app.meme_barrage.store import LIBRARY_MAX_ROWS

            rows = self.conn.execute(
                "SELECT text FROM meme_barrage_library ORDER BY id ASC LIMIT ?",
                (LIBRARY_MAX_ROWS,),
            ).fetchall()
        except sqlite3.ProgrammingError:
            return []
        return [str(row[0]).strip() for row in rows if row and row[0] and str(row[0]).strip()]

    def meme_barrage_library_contains_text(self, text: str) -> bool:
        """True when text exactly matches a row in meme_barrage_library."""
        value = str(text).strip()
        if not value:
            return False
        row = self.conn.execute(
            "SELECT 1 FROM meme_barrage_library WHERE text = ? LIMIT 1",
            (value,),
        ).fetchone()
        return row is not None

    def meme_barrage_library_fetch_batch(
        self, offset: int, limit: int
    ) -> tuple[list[str], int]:
        if limit <= 0:
            return [], offset
        total = self.meme_barrage_library_count()
        if total <= 0:
            return [], 0
        offset = int(offset) % total
        rows = self.conn.execute(
            "SELECT text FROM meme_barrage_library ORDER BY id ASC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        texts = [str(row[0]) for row in rows if row and row[0]]
        next_offset = (offset + len(texts)) % total if total else 0
        return texts, next_offset

    def _trim_meme_barrage_library_locked(self, max_rows: int) -> None:
        count = self.conn.execute("SELECT COUNT(*) FROM meme_barrage_library").fetchone()
        total = 0 if not count or count[0] is None else int(count[0])
        if total <= max_rows:
            return
        excess = total - max_rows
        self.conn.execute(
            "DELETE FROM meme_barrage_library WHERE id IN ("
            "SELECT id FROM meme_barrage_library ORDER BY id ASC LIMIT ?"
            ")",
            (excess,),
        )
        self._invalidate_formula_text_cache()

    def _invalidate_formula_text_cache(self) -> None:
        from app.danmu_pool import invalidate_formula_text_cache

        invalidate_formula_text_cache(self)

    def get_default_model_id(self) -> str:
        model_id = self.get("default_model_id", "")
        if model_id:
            return model_id
        return self.get("model", "")

    def set_default_model_id(self, model_id: str):
        self.set("default_model_id", model_id)

    def close(self):
        self._closed = True
        try:
            self.conn.close()
        except sqlite3.ProgrammingError:
            pass
