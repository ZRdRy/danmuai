"""Boundary guard: architecture boundary checks for DanmuAI."""

from .cli import main
from .models import Finding
from .reporters import format_findings
from .runner import run_boundary_guard

__all__ = ["Finding", "format_findings", "main", "run_boundary_guard"]
