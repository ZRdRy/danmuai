# Privacy

## Capture and Transmission

- DanmuAI captures only the region you configure and does not default to full-screen capture.
- The captured image is sent to the AI service endpoint you configure in order to generate danmu text.
- Screenshots are not written to disk by default. The app stores danmu text history only.

## Local Storage

- The configuration database is stored at `%APPDATA%/DanmuAI/config.db`.
- API keys use Fernet encryption when available. If `cryptography` is missing, the app falls back to base64 and emits an explicit warning.
- Repository folders such as `log/`, `ph/`, `.coverage`, and cache directories are local development artifacts and should not be committed.

## Logging Policy

- Logs sanitize API keys, bearer tokens, long base64 image payloads, and encrypted values.
- Logs do not record full screenshot content or raw request bodies.

## Recommended Usage

- Capture only the region that is actually required.
- Avoid selecting areas that contain accounts, passwords, chats, payment details, or private documents.
- If you use the app during streaming, recording, or live demos, verify first that the capture region does not overlap with sensitive windows.
