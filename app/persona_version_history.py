"""Persona template version history facade over TemplateManager."""

from __future__ import annotations

from app.templates import TemplateManager


def list_versions(templates: TemplateManager, name: str) -> list[dict]:
    return templates.versions(name)
