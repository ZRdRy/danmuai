# DanmuAI

DanmuAI is a PyQt6-based desktop danmu tool for Windows. It captures a configured screen region, sends it to a vision-capable model, generates five danmu comments, and renders them as a transparent always-on-top overlay.

## Project Status

This project is in active early development. APIs and configuration details may still change.

## Features

- Always generates exactly 5 danmu comments: the first 2 must stay tightly aligned with the current frame, while the remaining 3 are general live-stream style comments.
- Screenshots are taken on the main thread, while image compression and AI requests run in a thread pool to avoid blocking the UI.
- Replies tied to stale `screenshot_id` values or outdated scene generations are dropped automatically, so old frames do not overwrite new ones.
- Includes failure backoff, timeout handling, and sanitized logs.
- Captures only the configured region by default instead of the full screen.
- Does not save screenshots by default. Only danmu text history is stored.

## Requirements

- **Python**: 3.12 or newer
- **Platform**: Windows only, primary-screen workflow only
- Dependencies: see [requirements.txt](requirements.txt)

## Installation

```bash
pip install -r requirements.txt
```

If you want to run tests as well:

```bash
pip install pytest pytest-qt Pillow
```

## Run

```bash
python main.py
```

On first launch, if no local configuration exists, the app creates a default config store and prompts you to review the API key and capture region first.

> **Limitation**: the current version supports only primary-screen capture and primary-screen overlay rendering. Multi-screen setups and non-100% scaling still need explicit validation.

## Configure the API Key

1. Launch the app and open the **Settings** page.
2. Fill in `API Endpoint`, `API Key`, and `Model`.
3. Review the capture settings in **Capture & Privacy**.
4. Save the configuration, then start danmu generation.

The project also provides an example file: [`.env.example`](.env.example).

**Note**: the desktop app does not automatically read `.env`. It stores settings through the UI in `%APPDATA%/DanmuAI/config.db`. The example file is meant as a reference for local notes or wrapper scripts.

## Privacy Notes

- The tool captures the region you configure and sends the screenshot to the AI provider you choose.
- Screenshots are not saved by default, and raw screenshot contents are not written to logs.
- Do not select regions that contain passwords, chat logs, payment data, internal documents, or other sensitive information.
- The API key is stored in `%APPDATA%/DanmuAI/config.db`. The app prefers `cryptography` + Fernet encryption; if the encryption dependency is missing, it falls back to base64 with an explicit warning.

See [docs/PRIVACY.md](docs/PRIVACY.md) for more detail.

## FAQ

### Why does no danmu appear after startup?

- The most common causes are a missing API key, an invalid capture region, or repeated request failures that triggered backoff.
- Check the API settings first, then inspect the log panel for the most recent error.

### Why are danmu comments from an older frame not shown?

- The current implementation intentionally drops replies with stale `screenshot_id` values, replies that exceed the freshness threshold, and cached replies from older scene generations. This prevents stale content from overriding the latest frame.

### Does the app save screenshots?

- No, not by default. The current implementation stores only danmu text history and does not write screenshots to disk.

## Known Limitations

- The current version supports only primary-screen capture and primary-screen overlay rendering.
- In-flight network requests cannot be force-cancelled. They are released naturally after timeout. During shutdown, the app marks the pipeline as stopping and waits briefly for the thread pool to settle.

## Contributing

- Read [SECURITY.md](SECURITY.md) and [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md) before opening an issue.
- Run the minimal test set before submitting code.
- See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution details.

## Repository Layout

```text
.
├─ app/               Core logic
├─ ui/                Qt UI
├─ tests/             pytest tests
├─ docs/              Documentation (architecture, privacy, licensing, roadmap, changelog)
├─ prototype/         HTML prototypes
├─ .github/           Issue and PR templates
└─ main.py            Application entry point
```

## License

This project is open sourced under the [GNU General Public License v3.0 or later](LICENSE).

Third-party components keep their own original licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md) for details.
