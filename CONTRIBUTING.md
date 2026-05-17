# Contributing

## 开发原则

- 保持现有双窗架构，不做大规模重构。
- 优先修复稳定性、隐私和发布质量问题，再考虑新功能。
- 修改 Qt 页面前，先在 `prototype/` 中完成原型验证。

## 本地开发

```bash
pip install -r requirements.txt
pip install pytest pytest-qt Pillow
python main.py
```

## 提交前检查

```bash
python -m pytest tests/test_reply_parser.py tests/test_p0_main_flow.py tests/test_danmu_engine.py tests/test_config_store.py tests/test_ai_client.py -q
python -m pytest tests/ -q
```

## 提交规范

- 不要提交 API Key、日志、截图、`%APPDATA%/DanmuAI/` 下的本地数据库或 `.key` 文件。
- 不要把调试截图、缓存目录、`.coverage`、`__pycache__`、`.pytest_cache` 带入版本库。
- 新功能或行为变化需要同步更新 `README.md` 和 `docs/CHANGELOG.md`。

## Issue 与 PR

- Bug 报告请附最小复现步骤、实际行为、期望行为和日志摘要。
- 涉及隐私、凭据或安全边界的问题，请不要公开贴出原始截图和密钥，改走 [SECURITY.md](SECURITY.md) 中的私下反馈流程。
