# Changelog

## 2026-05-17

- 项目许可证从 MIT 更改为 GPL-3.0+，与 PyQt6 (GPL-3.0) 和 python-Levenshtein (GPL-2.0+) 的 copyleft 要求一致
- `LICENSE` 更新为 GPL v3 摘要 + 第三方依赖许可证声明
- `README.md` 补充项目状态、环境要求（Python ≥ 3.12、Windows）、已知限制；修复所有本地绝对路径为仓库相对路径
- `CONTRIBUTING.md` 修复本地绝对路径
- `docs/OPEN_SOURCE_AUDIT.md` 补充第三方依赖许可证审计表，更新许可证口径为 GPL-3.0+
- `.env.example` 明确标注为参考模板，桌面应用不自动加载
- `.gitignore` 补齐 `.agents/`、`.trae/`、`skills-lock.json`、`test_icon.png`
- 移除 `log/`、`.coverage`、`__pycache__/`、`.pytest_cache/`、`.npmcache/`、`scratchpad.md`、`skills-lock.json`、`test_icon.png` 等无关文件
- 初始化 Git 仓库
- 整理 `docs/`：移除 9 个内部过程文档（ISSUE_TRACKER、OPTIMIZATION_PLAN、产品需求文档、技术架构文档、技术问题解决方案、测试用例文档、需求文档、项目决策框架、项目管理文档），保留 5 个公开文档
- 新增 `.github/ISSUE_TEMPLATE/bug_report.md`、`.github/ISSUE_TEMPLATE/feature_request.md`、`.github/PULL_REQUEST_TEMPLATE.md`
- 新增 `THIRD_PARTY_NOTICES.md` 第三方依赖许可证声明
- 新增 `docs/RELEASE_CHECKLIST.md` 发布检查清单

## 2026-05-16

- 新增标准 MIT `LICENSE`
- 重写 `README.md`，补齐安装、运行、隐私、FAQ、贡献和许可证说明
- 新增 `CONTRIBUTING.md`、`SECURITY.md`、`.gitignore`、`.env.example`
- 新增 `docs/PRIVACY.md`、`docs/ROADMAP.md`、`docs/ARCHITECTURE.md`、`docs/OPEN_SOURCE_AUDIT.md`
- 修复默认截图逻辑，改为使用配置区域而非全屏
- 增加首启配置提示、退出清理、截图失败重调度、暂停时队列清理
- 引入 AI 回复解析与固定 5 条标准化逻辑
- 增补 pytest 测试覆盖回复约束、首启提示、异常释放和过期丢弃
