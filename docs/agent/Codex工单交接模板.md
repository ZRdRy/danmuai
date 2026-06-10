# Codex 工单交接模板

> 以下为 **W-000 示例**（建立工作流文档）。新工单请复制 [templates/Codex执行提示词/Codex执行提示词模板.md](templates/Codex执行提示词/Codex执行提示词模板.md) 并替换全部 `（待填）` 内容。

---

## 示例：W-000（已完成，仅供参考）

### 当前工单

- **工单 ID**：W-000  
- **标题**：建立 Codex 工作流文档与模板  

### 执行前必须阅读

1. [AGENTS.md](../AGENTS.md)  
2. 用户提供的《Codex 工作流》计划（仅文档范围）  

### 允许修改的区域

```
AGENTS.md
docs/
docs/templates/
docs/workflow/
docs/工单列表.md
docs/当前仓库状态.md
docs/手动验收指南.md
docs/Codex提示词手册.md
docs/Codex工单交接模板.md
docs/已知问题与后续事项.md
docs/设计更新说明.md
docs/提示词上下文包.md
docs/README.md（索引小节）
docs/ai-project-context.md（可选一行链接）
```

### 禁止修改的区域

```
app/
web/
main.py
tests/
scripts/
requirements.txt
package.json
锁文件
配置文件
```

### 具体需求

1. 重构 `AGENTS.md`：§1–§10 Codex 规则 + 附录技术速查  
2. 创建 `docs/templates/` 下 8 个子目录（各含 1 模板）  
3. 创建 8 份正式工作文档（初始占位 + 可核实事实）  
4. 创建 `docs/workflow/README.md`  
5. 更新 `docs/README.md` 工作流索引  

### 非目标

- 不修改任何业务代码  
- 不实现 ROADMAP 功能  
- 不猜测并填写具体业务需求  

### 验收标准

- [ ] `AGENTS.md` 含 §1–§10 与 14 条可执行约束  
- [ ] 8 个模板可直接复制使用  
- [ ] 8 份正式文档存在且标明「待负责人补充」处  
- [ ] `git diff` 仅含 `AGENTS.md` 与 `docs/**`  

### 手动验证步骤

1. 打开 `AGENTS.md`，确认 §1–§10 与附录 A 存在  
2. 打开 `docs/templates/`，确认 8 个子目录  
3. 从 `docs/README.md` 点击 Codex 工作流链接，确认可打开  
4. 确认未修改 `app/`、`web/`、`main.py`  

### 完成后报告格式

见 [templates/Codex完成报告/Codex完成报告模板.md](templates/Codex完成报告/Codex完成报告模板.md)。

### 如果发现范围外问题

不要修复；记入 [已知问题与后续事项.md](已知问题与后续事项.md)。

---

## 新工单交接（空白）

请使用：[templates/Codex执行提示词/Codex执行提示词模板.md](templates/Codex执行提示词/Codex执行提示词模板.md)

并在 [工单列表.md](工单列表.md) 登记工单 ID。
