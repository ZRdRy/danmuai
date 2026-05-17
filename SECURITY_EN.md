# Security Policy

## Supported Scope

The repository currently maintains the desktop mainline version. Security fixes are prioritized for the default active branch.

## How to Report

- Do not post API keys, auth headers, raw screenshots, or logs containing private content in public issues.
- If the issue involves credential leakage, screenshot privacy, or a potentially exploitable vulnerability, contact the maintainers privately.

## Current Security Boundaries

- API keys are stored in `%APPDATA%/DanmuAI/config.db` and use Fernet encryption when available.
- Logs sanitize API keys, `Authorization` headers, long base64 image payloads, and encrypted blobs.
- Screenshots are not saved by default, and raw screenshot contents are not written into logs.
- Stale requests and replies from outdated scene generations are dropped so old content does not overwrite the current frame.

## Usage Recommendations

- Capture only the region that actually needs analysis.
- Avoid regions that include password fields, chat windows, payment pages, or internal company content.
- Before publishing builds or sharing source, confirm the repository does not contain `log/`, `ph/`, local databases, `.key` files, or cache directories.
