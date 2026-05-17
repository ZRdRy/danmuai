# Release Checklist

发布新版本前的检查清单。

## 代码与测试

- [ ] 所有测试通过：`python -m pytest tests/ -q`
- [ ] 无新增 lint 警告
- [ ] 无硬编码的 API Key、Token 或敏感路径

## 文档

- [ ] `README.md` 中的环境要求、已知限制与代码一致
- [ ] `docs/CHANGELOG.md` 已更新本次变更
- [ ] `docs/ARCHITECTURE.md` 与实际代码结构一致
- [ ] `THIRD_PARTY_NOTICES.md` 与 `requirements.txt` 一致

## 许可证与合规

- [ ] `LICENSE` 文件正确
- [ ] 新增依赖已记录在 `THIRD_PARTY_NOTICES.md` 和 `docs/OPEN_SOURCE_AUDIT.md`
- [ ] 无许可证冲突

## 安全与隐私

- [ ] `.gitignore` 覆盖所有本地调试产物
- [ ] `git status` 中无日志、缓存、数据库、密钥文件
- [ ] 日志脱敏规则覆盖 API Key、Token、base64 图片

## Git 与发布

- [ ] `git add -n .` 预演无意外文件
- [ ] Tag 格式：`vX.Y.Z`
- [ ] GitHub Release 描述包含变更摘要和已知问题
