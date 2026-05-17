# Open Source Audit

## Licensing Summary

- The repository root uses a standard GPL-compatible [LICENSE](../LICENSE).
- The repository does not claim non-commercial-only, source-available-only, or other incompatible restrictions.
- Public-facing documentation should keep its licensing language aligned with the actual dependency and distribution model.

## Sensitive File Review

The following classes of files are local-only artifacts and should never be published in the open repository:

- Local log output
- Temporary screenshots used during debugging
- Coverage files such as `.coverage`
- Cache directories such as `.pytest_cache/` and `__pycache__/`
- Local package caches such as `.npmcache/`

## Privacy Boundary

- Screenshots are compressed in memory and are not written to disk by default.
- Logs sanitize API keys, bearer tokens, and long base64 payloads.
- Only the configured capture region is sent to the AI provider.
- AI replies tied to stale `screenshot_id` values or outdated `scene_generation` values are discarded.

## Final Manual Checks Before Release

- Confirm the workspace does not include local database exports or copied `%APPDATA%/DanmuAI/` data.
- Confirm sample screenshots, captured content, and local logs are excluded from release artifacts.
- Confirm the final GitHub release bundle does not contain debug caches or machine-local metadata.
