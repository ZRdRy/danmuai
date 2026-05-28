"""Single host registry: endpoint guess and API transport from PROVIDERS."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.model_providers import (
    DEFAULT_PROVIDER_ID,
    PROVIDERS,
    is_doubao_mode,
    normalize_endpoint,
    normalize_mode,
)


@dataclass(frozen=True)
class HostEntry:
    fragment: str
    provider_id: str
    transport: str  # "doubao" | "openai"


def _mode_to_transport(mode: str) -> str:
    return "doubao" if mode == "doubao" else "openai"


def _endpoint_netloc_fragment(url: str) -> str:
    parsed = urlparse(normalize_endpoint(url))
    return (parsed.netloc or "").lower()


def _build_host_entries() -> tuple[HostEntry, ...]:
    entries: list[HostEntry] = []
    seen: set[str] = set()
    for spec in PROVIDERS:
        if not spec.default_endpoint:
            continue
        fragment = _endpoint_netloc_fragment(spec.default_endpoint)
        if not fragment or fragment in seen:
            continue
        seen.add(fragment)
        entries.append(
            HostEntry(
                fragment=fragment,
                provider_id=spec.id,
                transport=_mode_to_transport(spec.mode),
            )
        )
    return tuple(sorted(entries, key=lambda e: -len(e.fragment)))


HOST_ENTRIES: tuple[HostEntry, ...] = _build_host_entries()


def match_host_entry(endpoint: str) -> HostEntry | None:
    normalized = normalize_endpoint(endpoint).lower() if endpoint else ""
    if not normalized:
        return None
    for entry in HOST_ENTRIES:
        if entry.fragment in normalized:
            return entry
    return None


def guess_provider_from_endpoint(endpoint: str, mode: str = "") -> str:
    entry = match_host_entry(endpoint)
    if entry is not None:
        return entry.provider_id
    if normalize_mode(mode) == "doubao":
        return "custom_doubao"
    return DEFAULT_PROVIDER_ID


def resolve_api_transport(endpoint: str, api_mode: str) -> str:
    """Choose Responses (``doubao``) vs Chat Completions (``openai``)."""
    entry = match_host_entry(endpoint)
    if entry is not None:
        return entry.transport
    if is_doubao_mode(api_mode):
        return "doubao"
    return "openai"
