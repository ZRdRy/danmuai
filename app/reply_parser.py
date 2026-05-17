import json

from app.translations import tr


def _scene_fillers() -> list[str]:
    return [
        tr("reply.scene_filler_1"),
        tr("reply.scene_filler_2"),
    ]


def _generic_fillers() -> list[str]:
    return [
        tr("reply.generic_filler_1"),
        tr("reply.generic_filler_2"),
        tr("reply.generic_filler_3"),
    ]


def parse_ai_reply_payload(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    parsed = None
    if raw.startswith("[") or raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None

    if isinstance(parsed, dict):
        for key in ("comments", "replies", "items", "data"):
            value = parsed.get(key)
            if isinstance(value, list):
                parsed = value
                break

    if isinstance(parsed, list):
        candidates = parsed
    else:
        candidates = [
            part.strip(" -\t\r\n")
            for part in raw.replace("\r", "\n").split("\n")
            if part.strip()
        ]

    normalized: list[str] = []
    for item in candidates:
        value = str(item).strip().strip('"').strip("'")
        if value:
            normalized.append(value)
    return normalized


def normalize_reply_batch(items: list[str], desired_count: int = 5) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)

    result = cleaned[:desired_count]
    scene_fillers = _scene_fillers()
    generic_fillers = _generic_fillers()

    while len(result) < min(2, desired_count):
        result.append(scene_fillers[len(result)])
    while len(result) < desired_count:
        filler_index = len(result) - 2
        pool_index = min(filler_index, len(generic_fillers) - 1)
        result.append(generic_fillers[pool_index])
    return result[:desired_count]
