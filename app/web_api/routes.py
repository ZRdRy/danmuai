"""扩展 FastAPI 路由：协议适配层，委托 DanmuApp 公开 façade 与 web_api 子模块。

- /api/status 在 web_console 内注册，本文件不重复
- /api/diagnostics 必须 build_diagnostic_snapshot()，与 status 分离
- 写操作需 Bearer；勿在路由内直接改 DanmuApp 私有字段或 QTimer
"""

import re
from typing import TYPE_CHECKING, Callable
from urllib.parse import unquote

from fastapi import File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

ANNOUNCEMENTS_READ_STATE_KEY = "announcements_read_state"
ANNOUNCEMENTS_READ_IDS_MAX = 200
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _empty_announcements_read_state() -> dict[str, object]:
    return {"readIds": [], "lastSeenMs": 0}


def _normalize_announcements_read_state(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return _empty_announcements_read_state()
    read_ids = raw.get("readIds")
    if not isinstance(read_ids, list):
        read_ids = []
    cleaned: list[str] = []
    for item in read_ids:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if item and item not in cleaned:
            cleaned.append(item)
    last_seen_ms = raw.get("lastSeenMs", 0)
    try:
        last_seen_ms = int(last_seen_ms)
    except (TypeError, ValueError):
        last_seen_ms = 0
    if last_seen_ms < 0:
        last_seen_ms = 0
    return {
        "readIds": cleaned[:ANNOUNCEMENTS_READ_IDS_MAX],
        "lastSeenMs": last_seen_ms,
    }


def _get_announcements_read_state_from_config(config) -> dict[str, object]:
    raw = config.get_json(ANNOUNCEMENTS_READ_STATE_KEY, default=_empty_announcements_read_state())
    return _normalize_announcements_read_state(raw)


def _validate_announcements_read_state_payload(body: dict) -> dict[str, object]:
    read_ids = body.get("readIds")
    if read_ids is None:
        read_ids = []
    if not isinstance(read_ids, list):
        raise HTTPException(status_code=400, detail="readIds 必须为数组")
    cleaned: list[str] = []
    for item in read_ids:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail="readIds 元素必须为字符串")
        item = item.strip()
        if not item:
            continue
        if not _UUID_RE.match(item):
            raise HTTPException(status_code=400, detail="readIds 包含无效的公告 ID")
        if item not in cleaned:
            cleaned.append(item)
    if len(cleaned) > ANNOUNCEMENTS_READ_IDS_MAX:
        cleaned = cleaned[-ANNOUNCEMENTS_READ_IDS_MAX:]
    last_seen_ms = body.get("lastSeenMs", 0)
    try:
        last_seen_ms = int(last_seen_ms)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="lastSeenMs 必须为整数") from exc
    if last_seen_ms < 0:
        raise HTTPException(status_code=400, detail="lastSeenMs 不能为负数")
    return {"readIds": cleaned, "lastSeenMs": last_seen_ms}

from app.image_compress import compress_image_bytes
from app.web_api import custom_models as cm_api
from app.web_api import danmu_pool as pool_api
from app.web_api import persona as persona_api

if TYPE_CHECKING:
    from app.web_console import WebConsoleBridge


def register_preview_compress_route(app, check_token: Callable) -> None:
    """Module-level registration so UploadFile resolves under Python 3.14 + Pydantic v2."""

    @app.post("/api/preview/compress")
    async def preview_compress(
        file: UploadFile = File(...),
        max_width: int = Form(768),
        quality: int = Form(85),
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="图片太大了，请换一张小一点的~")
        try:
            return compress_image_bytes(data, max_width=max_width, quality=quality)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"小助手读不懂这张图：{exc}") from exc


def register_web_routes(app, bridge: "WebConsoleBridge", check_token: Callable) -> None:
    register_preview_compress_route(app, check_token)

    class PersonaCreatePayload(BaseModel):
        name: str

    class PersonaSavePayload(BaseModel):
        system_custom: str = ""
        user_pt: str = ""

    class PersonaRollbackPayload(BaseModel):
        version: int

    class CustomModelPayload(BaseModel):
        name: str = ""
        modelId: str = ""
        mode: str = "doubao"
        endpoint: str = ""
        apiKey: str = ""
        description: str = ""
        provider: str = ""

    class ActivePersonaePayload(BaseModel):
        active: list[str]

    class MicTestPayload(BaseModel):
        duration_sec: float = 3.0
        send_to_ai: bool = False

    class ProbePayload(BaseModel):
        api_endpoint: str = ""
        api_key: str = ""
        model: str = ""
        api_mode: str = "doubao"

    class DanmuPoolSettingsPayload(BaseModel):
        builtin_enabled: bool | None = None
        custom_enabled: bool | None = None
        min_on_screen: int | None = None

    class DanmuPoolCustomAppendPayload(BaseModel):
        text: str = ""
        items: list[str] | None = None

    class DanmuPoolCustomDeletePayload(BaseModel):
        texts: list[str]

    class AnnouncementsReadStatePayload(BaseModel):
        readIds: list[str] = []
        lastSeenMs: int = 0

    def _danmu():
        return bridge.danmu_app

    def _run_main(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/diagnostics")
    def get_diagnostics():
        # 只读诊断；调度/timing 数据经 DanmuApp 公开入口，不读 _last_api_trigger_at 等私有字段
        return {
            "ok": True,
            "diagnostics": _danmu().build_diagnostic_snapshot(),
        }

    @app.get("/api/announcements-read-state")
    def get_announcements_read_state():
        return _get_announcements_read_state_from_config(_danmu().config)

    @app.put("/api/announcements-read-state")
    def put_announcements_read_state(
        body: AnnouncementsReadStatePayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        state = _validate_announcements_read_state_payload(body.model_dump())
        _danmu().config.set_json(ANNOUNCEMENTS_READ_STATE_KEY, state)
        return {"ok": True}

    @app.get("/api/personae/{name}/template")
    def get_persona_template(name: str):
        return _run_main(persona_api.get_template_detail, _danmu(), unquote(name))

    @app.get("/api/personae/{name}/versions")
    def get_persona_versions(name: str):
        return _run_main(persona_api.list_versions, _danmu(), unquote(name))

    @app.put("/api/personae/{name}/template")
    def put_persona_template(
        name: str,
        body: PersonaSavePayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        _run_main(
            persona_api.save_template,
            _danmu(),
            unquote(name),
            body.system_custom,
            body.user_pt,
        )
        return {"ok": True}

    @app.post("/api/personae/{name}/rollback")
    def post_persona_rollback(
        name: str,
        body: PersonaRollbackPayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        return _run_main(persona_api.rollback_preview, _danmu(), unquote(name), body.version)

    @app.post("/api/personae")
    def post_persona(body: PersonaCreatePayload, authorization: str | None = Header(default=None)):
        check_token(authorization)
        return _run_main(persona_api.create_persona, _danmu(), body.name)

    @app.delete("/api/personae/{name}")
    def delete_persona(name: str, authorization: str | None = Header(default=None)):
        check_token(authorization)
        _run_main(persona_api.delete_persona, _danmu(), unquote(name))
        return {"ok": True}

    @app.post("/api/personae/{name}/restore")
    def restore_persona(name: str, authorization: str | None = Header(default=None)):
        check_token(authorization)
        return _run_main(persona_api.restore_builtin_default, _danmu(), unquote(name))

    # 活跃人格：委托 DanmuApp.set_active_personae（主线程由 bridge 槽保证）
    @app.put("/api/personae/active")
    def put_active_personae(
        body: ActivePersonaePayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        if not body.active:
            raise HTTPException(status_code=400, detail="请至少选择一个人格")
        _danmu().set_active_personae(body.active)
        return {"ok": True}

    @app.get("/api/danmu-pool/meta")
    def get_danmu_pool_meta():
        return pool_api.get_meta(_danmu())

    @app.put("/api/danmu-pool/settings")
    def put_danmu_pool_settings(
        body: DanmuPoolSettingsPayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        return _run_main(pool_api.save_settings, _danmu(), body.model_dump(exclude_none=True))

    @app.get("/api/danmu-pool/custom")
    def get_danmu_pool_custom():
        return pool_api.list_custom(_danmu())

    @app.post("/api/danmu-pool/custom")
    def post_danmu_pool_custom(
        body: DanmuPoolCustomAppendPayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        return _run_main(pool_api.append_custom, _danmu(), body.model_dump(exclude_none=True))

    @app.delete("/api/danmu-pool/custom")
    def delete_danmu_pool_custom(
        body: DanmuPoolCustomDeletePayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        return _run_main(pool_api.delete_custom, _danmu(), body.model_dump())

    @app.get("/api/custom-models")
    def get_custom_models():
        return cm_api.list_custom_models(_danmu())

    @app.post("/api/custom-models")
    def post_custom_model(
        body: CustomModelPayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        return _run_main(cm_api.create_custom_model, _danmu(), body.model_dump())

    @app.put("/api/custom-models/{index}")
    def put_custom_model(
        index: int,
        body: CustomModelPayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        return _run_main(cm_api.update_custom_model, _danmu(), index, body.model_dump())

    @app.delete("/api/custom-models/{index}")
    def delete_custom_model_route(
        index: int,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        _run_main(cm_api.delete_custom_model, _danmu(), index)
        return {"ok": True}

    @app.post("/api/custom-models/{index}/default")
    def set_default_custom_model(
        index: int,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        return _run_main(cm_api.set_default_custom_model, _danmu(), index)

    @app.post("/api/probe")
    def probe_api_connection(
        body: ProbePayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        from app.api_probe import probe_connection

        config = _danmu().config
        api_key = body.api_key or ""
        if api_key == cm_api.MASKED_KEY:
            api_key = config.get_api_key()
        result = probe_connection(
            body.api_endpoint or config.get("api_endpoint", ""),
            api_key,
            body.model or config.get("model", ""),
            body.api_mode or config.get("api_mode", "doubao"),
        )
        return {
            "ok": result.ok,
            "message": result.message,
            "status_code": result.status_code,
        }

    @app.post("/api/custom-models/probe")
    def probe_custom_model(
        body: CustomModelPayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        from app.api_probe import probe_connection

        config = _danmu().config
        payload = body.model_dump()
        api_key = payload.get("apiKey") or ""
        if api_key == cm_api.MASKED_KEY:
            api_key = config.get_api_key()
        result = probe_connection(
            payload.get("endpoint") or config.get("api_endpoint", ""),
            api_key,
            payload.get("modelId") or config.get("model", ""),
            payload.get("mode") or config.get("api_mode", "doubao"),
        )
        return {
            "ok": result.ok,
            "message": result.message,
            "status_code": result.status_code,
        }

    def _mic_test_response(body: MicTestPayload):
        danmu_app = _danmu()
        return danmu_app.run_mic_test(body.duration_sec, send_to_ai=body.send_to_ai)

    @app.post("/api/mic/test")
    def mic_test(
        body: MicTestPayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        return _mic_test_response(body)

    @app.post("/api/mic/test-send")
    def mic_test_send(
        body: MicTestPayload,
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        body = MicTestPayload(duration_sec=body.duration_sec, send_to_ai=True)
        return _mic_test_response(body)

    @app.get("/api/capture-region")
    def get_capture_region():
        return _danmu().get_capture_region_status()

    @app.post("/api/capture-region/select")
    def post_capture_region_select(
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        current = _danmu().get_capture_region_status()
        if current.get("selection_state") == "selecting":
            return {"ok": True, "selection_state": "selecting"}
        bridge.region_select_requested.emit()
        return {"ok": True, "selection_state": "selecting"}

    @app.post("/api/capture-region/reset")
    def post_capture_region_reset(
        authorization: str | None = Header(default=None),
    ):
        check_token(authorization)
        bridge.region_reset_requested.emit()
        return {"ok": True}
