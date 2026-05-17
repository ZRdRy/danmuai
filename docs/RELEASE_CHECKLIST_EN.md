# Release Checklist

- [ ] Confirm the working tree contains no API keys, local databases, screenshots, or tray logs
- [ ] Run the minimal regression suite and then the full `tests/` suite
- [ ] Verify the app starts from a clean environment using `python main.py`
- [ ] Verify English and Chinese UI modes both render correctly
- [ ] Confirm `README.md`, `README_EN.md`, `LICENSE`, and `THIRD_PARTY_NOTICES.md` are up to date
- [ ] Confirm `.gitignore` covers logs, caches, local config exports, and IDE metadata
- [ ] Confirm release assets do not include debug-only files or local machine data
