# DanmuAI documentation

Entry point: [README.md](../README.md) (install, quick start).

## Public — start here

| Document | Audience | Description |
|----------|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Everyone | What DanmuAI is, modules, threading, pipeline summary |
| [WEB_CONSOLE.md](WEB_CONSOLE.md) | Users & contributors | Web API, pages, launch modes |
| [MAIN_PIPELINE.md](MAIN_PIPELINE.md) | Contributors | Screenshot → AI → queue → overlay (normal mode) |
| [RUNTIME_STATE.md](RUNTIME_STATE.md) | Contributors | Status, diagnostics, state ownership |
| [PRIVACY.md](PRIVACY.md) | Users | Screenshot, mic, keys, data boundaries |

## Contributing

| Document | Description |
|----------|-------------|
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Dev setup, tests, PR hygiene |
| [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md) | Architecture boundaries and checklist |
| [BOUNDARY_GUARD.md](BOUNDARY_GUARD.md) | `scripts/boundary_guard.py` usage |
| [AGENTS.md](../AGENTS.md) | IDE/agent conventions (dense) |
| [DANMAKU_FORMULA.md](DANMAKU_FORMULA.md) | AI output JSON contract |

## Changelog & roadmap

| Document | Description |
|----------|-------------|
| [ROADMAP.md](ROADMAP.md) | Planned and completed work |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |
| [release/](release/) | GitHub Release 正文（按版本） |

## Release & compliance

| Document | Description |
|----------|-------------|
| [release/2026-05-27.md](release/2026-05-27.md) | 当前版本发布说明 |
| [PACKAGING_WINDOWS.md](PACKAGING_WINDOWS.md) | PyInstaller / exe |
| [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) | Release steps |
| [OPEN_SOURCE_AUDIT.md](OPEN_SOURCE_AUDIT.md) | Licenses & dependencies |
| [SECURITY.md](../SECURITY.md) | Security reporting |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Community norms |
| [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | Third-party licenses |
| [data/ATTRIBUTION.md](../data/ATTRIBUTION.md) | Corpus attribution |

## Engineering reference

| Document | Description |
|----------|-------------|
| [CAPTURE_AND_DANMAKU_REFERENCE.md](CAPTURE_AND_DANMAKU_REFERENCE.md) | External libs (mss, Danmaku.js) |

## Maintainer registry (Boundary Guard)

These paths are **stable filenames**—do not rename without updating `scripts/boundary_guard.py` and tests.

| Document | Purpose |
|----------|---------|
| [runtime-state-map.md](runtime-state-map.md) | Register new `DanmuApp` fields |
| [main-pipeline-sequence.md](main-pipeline-sequence.md) | Pipeline sequence table (sync with [MAIN_PIPELINE.md](MAIN_PIPELINE.md)) |
| [final-architecture-baseline.md](final-architecture-baseline.md) | Short architecture baseline (required to exist) |

## Archive

Read-only history; not for first-time onboarding. Current behavior: [ARCHITECTURE.md](ARCHITECTURE.md), [WEB_CONSOLE.md](WEB_CONSOLE.md).

| Path | Contents |
|------|----------|
| [archive/README.md](archive/README.md) | Archive index |
| [archive/architecture-phases/](archive/architecture-phases/) | Phase 1–5 boundary plans (summaries) |
| [archive/planning/](archive/planning/) | Superseded feature plans (memory, display mode, …) |
| [archive/qt6_ui_redesign_plan.md](archive/qt6_ui_redesign_plan.md) | Removed Qt main window |

## UI prototype

| Document | Description |
|----------|-------------|
| [prototype/README.md](../prototype/README.md) | Prototype folder |
| [prototype/Qwen_html_20260524_481u8vlmv.html](../prototype/Qwen_html_20260524_481u8vlmv.html) | Web UI reference |
| [prototype/Qwen_markdown_20260525_4vyxmv819.md](../prototype/Qwen_markdown_20260525_4vyxmv819.md) | Design tokens |
