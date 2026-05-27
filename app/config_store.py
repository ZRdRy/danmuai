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
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

from base64 import b64decode, b64encode

from app.translations import tr

logger = logging.getLogger(__name__)

_SENSITIVE_CONFIG_KEYS = frozenset({"api_key_encrypted", "custom_models", "api_key"})


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
        self.conn.execute("PRAGMA journal_mode=WAL")
        # 写冲突时等待最多 5s 而非立即失败（与 _write_lock 双保险）
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_db()
        self._cache: dict[str, str] = {}
        self._load_cache()
        # 所有 REPLACE/commit 串行化，保证 _cache 与 DB 同事务一致
        self._write_lock = threading.Lock()
        if self.is_first_run or not self.get("danmu_speed"):
            from app.config_defaults import seed_config_defaults

            seed_config_defaults(self)
            self._load_cache()
        self._fernet = self._init_fernet()

    def get_startup_notice(self) -> str:
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
                # Start explicit transaction
                for k, v in items.items():
                    self.conn.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (k, v))
                self.conn.commit()
                # Only update cache after successful commit
                for k, v in items.items():
                    self._cache[k] = v
            except sqlite3.OperationalError as e:
                self.conn.rollback()
                logger.error(tr("config.batch_write_failed").format(error=e))
                raise

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

    def get_api_key(self) -> str:
        """读取明文 API Key：优先 Fernet 解密 api_key_encrypted，否则回退 base64 的 api_key_encoded。"""
        encrypted = self.get("api_key_encrypted", "")
        if encrypted and _HAS_CRYPTO and self._fernet:
            try:
                return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
            except Exception:
                logger.warning(tr("config.decrypt_failed"))
                return ""
        # Legacy base64 fallback (not secure - only encoded, not encrypted)
        encoded = self.get("api_key_encoded", "")
        if not encoded:
            return ""
        if _HAS_CRYPTO and self._fernet is None:
            logger.warning(tr("config.insecure_read"))
        try:
            return b64decode(encoded).decode("utf-8")
        except Exception:
            return ""

    def set_api_key(self, key: str):
        """写入 API Key：有 Fernet 则加密存 api_key_encrypted 并清除旧 base64 行。

        无 cryptography 时仅 base64（不安全），日志会警告；生产环境应安装 cryptography。
        """
        if _HAS_CRYPTO and self._fernet:
            encrypted = self._fernet.encrypt(key.encode("utf-8")).decode("utf-8")
            with self._write_lock:
                try:
                    self.conn.execute("REPLACE INTO config (key, value) VALUES (?, ?)", ("api_key_encrypted", encrypted))
                    if "api_key_encoded" in self._cache:
                        self.conn.execute("DELETE FROM config WHERE key=?", ("api_key_encoded",))
                        self._cache.pop("api_key_encoded", None)
                    self.conn.commit()
                    self._cache["api_key_encrypted"] = encrypted
                except sqlite3.OperationalError as e:
                    self.conn.rollback()
                    logger.error(tr("config.api_key_write_failed").format(error=e))
                    raise
        else:
            logger.warning(tr("config.insecure_store"))
            encoded = b64encode(key.encode("utf-8")).decode("utf-8")
            self.set("api_key_encoded", encoded)

    # --- 选区持久化 ---

    def get_region(self) -> tuple[int, int, int, int]:
        x = self.get_int("region_x", 0)
        y = self.get_int("region_y", 0)
        w = self.get_int("region_w", 0)
        h = self.get_int("region_h", 0)
        return x, y, w, h

    def set_region(self, x: int, y: int, w: int, h: int):
        self.set_batch({
            "region_x": str(x),
            "region_y": str(y),
            "region_w": str(w),
            "region_h": str(h),
        })

    def get_custom_models(self) -> list:
        return self.get_json("custom_models", [])

    def set_custom_models(self, models: list):
        self.set_json("custom_models", models)

    def get_custom_danmu_pool(self) -> list[str]:
        raw = self.get_json("custom_danmu_pool", [])
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    def set_custom_danmu_pool(self, items: list[str]) -> None:
        self.set_json("custom_danmu_pool", items)

    def get_default_model_id(self) -> str:
        model_id = self.get("default_model_id", "")
        if model_id:
            return model_id
        return self.get("model", "")

    def set_default_model_id(self, model_id: str):
        self.set("default_model_id", model_id)

    def close(self):
        try:
            self.conn.close()
        except sqlite3.ProgrammingError:
            pass
