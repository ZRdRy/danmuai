# Codex 提示词手册

本手册说明如何向 Codex / IDE Agent 下达**有边界**的工单，避免 scope creep 与架构漂移。

---

## 1. 最小提示词结构

每次开工至少包含：

1. **工单 ID + 标题**  
2. **允许修改的区域**（路径列表）  
3. **禁止修改的区域**  
4. **具体需求**（编号）  
5. **非目标**  
6. **验收标准**  
7. **手动验证步骤**  

直接复制 [templates/Codex执行提示词/Codex执行提示词模板.md](templates/Codex执行提示词/Codex执行提示词模板.md) 最省事。

---

## 2. 执行前阅读顺序

| 顺序 | 文件 |
|------|------|
| 1 | [AGENTS.md](../AGENTS.md) §1–§10 |
| 2 | [当前仓库状态.md](当前仓库状态.md) |
| 3 | [ai-project-context.md](ai-project-context.md)（改代码时） |
| 4 | 工单正文 + 本手册 |

---

## 3. 写好「允许 / 禁止」区

**允许区宜小**：例如只写 `web/static/app.js`，不要写整个 `web/` 除非必要。

**禁止区宜全**：默认包含：

```text
app/
web/
main.py
tests/
requirements.txt
.github/
scripts/（除非工单明确）
```

文档工单允许区示例：`AGENTS.md`、`docs/**`。

---

## 4. 常见错误（勿这样对 Codex 说）

| 错误说法 | 后果 | 应改为 |
|----------|------|--------|
| 「把 ROADMAP 下一步都做了」 | 超大 scope | 拆 W-001、W-002… |
| 「顺便重构一下 main.py」 | 架构漂移 | 单独 refactoring 工单 |
| 「参考 archive 里的设计实现」 | 恢复已删除功能 | 指明以 `main.py` 为准 |
| 「测试过了就行」 | 漏 UI/Overlay 问题 | 列出 3–5 步手动步骤 |
| 「有问题就修」 | 范围外顺手改 | 「只记录到已知问题文档」 |

---

## 5. 完成时要求 Codex 输出什么

必须索要 [templates/Codex完成报告/Codex完成报告模板.md](templates/Codex完成报告/Codex完成报告模板.md) 格式报告，并确认：

- [ ] 修改文件完整列表  
- [ ] 已更新 [当前仓库状态.md](当前仓库状态.md)  
- [ ] 范围外问题已写入 [已知问题与后续事项.md](已知问题与后续事项.md)（若有）  

---

## 6. 长对话 / ChatGPT 备用

将 [提示词上下文包.md](提示词上下文包.md) 整段粘贴到对话开头，可快速恢复项目边界。更新该文件由负责人在阶段切换时进行。

---

## 7. 相关文档

- [workflow/README.md](workflow/README.md) — 流程索引  
- [Codex工单交接模板.md](Codex工单交接模板.md) — 填好的交接示例  
- [工单列表.md](工单列表.md) — 当前 backlog  
