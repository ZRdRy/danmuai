# Changelog

## 2026-05-16

- Added a standard GPL-compatible `LICENSE`
- Reworked `README.md` to cover installation, running, privacy notes, FAQ, contribution flow, and licensing
- Added `CONTRIBUTING.md`, `SECURITY.md`, `.gitignore`, and `.env.example`
- Added `docs/PRIVACY.md`, `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, and `docs/OPEN_SOURCE_AUDIT.md`
- Fixed default capture behavior so the configured region is used instead of always grabbing the full screen
- Added first-run guidance, shutdown cleanup, retry scheduling for failed captures, and queue clearing during pause
- Introduced AI reply parsing and normalized fixed 5-comment output
- Added pytest coverage for reply normalization, first-run prompts, cleanup flow, and stale reply dropping
