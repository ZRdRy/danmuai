# Contributing

## Development Principles

- Keep the existing two-window architecture. Do not introduce large-scale refactors without a clear need.
- Prioritize stability, privacy, and release quality issues before adding new features.
- Before changing a Qt page, validate the interaction and visual direction in `prototype/` first.

## Local Development

```bash
pip install -r requirements.txt
pip install pytest pytest-qt Pillow
python main.py
```

## Checks Before Submission

```bash
python -m pytest tests/test_reply_parser.py tests/test_p0_main_flow.py tests/test_danmu_engine.py tests/test_config_store.py tests/test_ai_client.py -q
python -m pytest tests/ -q
```

## Submission Rules

- Do not commit API keys, logs, screenshots, local databases under `%APPDATA%/DanmuAI/`, or `.key` files.
- Do not add debug screenshots, cache directories, `.coverage`, `__pycache__`, or `.pytest_cache` to the repository.
- When behavior changes or new features are added, update `README.md` and `docs/CHANGELOG.md` in the same change set.

## Issues and PRs

- Bug reports should include minimal repro steps, actual behavior, expected behavior, and a short log summary.
- If the issue touches privacy boundaries, credentials, or security-sensitive material, do not post raw screenshots or secrets publicly. Follow the private reporting guidance in [SECURITY.md](SECURITY.md).
