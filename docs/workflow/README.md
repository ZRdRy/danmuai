# Codex 工作流

本目录说明 DanmuAI 仓库中 **Codex / IDE Agent 单工单协作** 的文档体系。业务代码规范仍以 [ai-project-context.md](../agent/ai-project-context.md) 与 [AGENTS.md](../../AGENTS.md) 为准。

## 推荐使用顺序

```text
1. 负责人在 docs/workflow/工单列表.md 登记小工单（可复制 templates/工单/工单模板.md）
2. 复制 templates/Codex执行提示词/Codex执行提示词模板.md 或 docs/agent/Codex工单交接模板.md → 交给 Codex
3. Codex 执行：只改允许区域 → 跑测试（若适用）→ 手动验证
4. Codex 输出：templates/Codex完成报告/Codex完成报告模板.md → 归档至 docs/archive/completion-reports/
5. 更新 docs/workflow/当前仓库状态.md、工单列表状态
6. 负责人用手动验收模板或 docs/agent/手动验收指南.md 复核
```

## 目录关系

| 位置 | 内容 |
|------|------|
| [AGENTS.md](../../AGENTS.md) §1–§10 | 仓库级 Codex 规则（强制） |
| [docs/templates/](../templates/) | 空白模板（8 子目录），见 [templates/README.md](../templates/README.md) |
| [工单列表.md](工单列表.md) | 正式 backlog |
| [当前仓库状态.md](当前仓库状态.md) | 活文档：分支、测试、最近变更 |
| [已知问题与后续事项.md](已知问题与后续事项.md) | 范围外问题，不修只记 |
| [agent/Codex提示词手册.md](../agent/Codex提示词手册.md) | 提示词写法与常见错误 |
| [agent/提示词上下文包.md](../agent/提示词上下文包.md) | 给 AI 的上下文快照 |
| [archive/completion-reports/](../archive/completion-reports/) | 历史完成报告归档 |
| [archive/workorders/](../archive/workorders/) | 历史工单正文归档 |

## 与 ROADMAP 的区别

- [operations/ROADMAP.md](../operations/ROADMAP.md) — 产品方向与已完成大项  
- [工单列表.md](工单列表.md) — **可执行、可验收** 的小工单（W-xxx），由负责人从 ROADMAP 拆分

## 首次使用

1. 阅读 [AGENTS.md](../../AGENTS.md) §1–§10  
2. 打开 [当前仓库状态.md](当前仓库状态.md)  
3. 从 [工单列表.md](工单列表.md) 取当前工单或新建 W-xxx  
