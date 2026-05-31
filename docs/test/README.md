# test — 实验性内置人格登记

本目录用于登记**非默认激活**、便于试验与后续撤回的内置人格。源码以 `app/personae.py` 为准。

| 文件 | 说明 |
|------|------|
| [persona-测试1.md](persona-测试1.md) | 真实直播间五人弹幕（置顶第 1） |
| [persona-测试2.md](persona-测试2.md) | 竞技/操作向五人（置顶第 2） |
| [persona-测试3.md](persona-测试3.md) | 氛围/唠嗑向五人（置顶第 3） |
| [persona-测试4.md](persona-测试4.md) | 阴阳/梗典向五人（置顶第 4） |

## 与产品人格的关系

- 人格工坊列表来自 `PersonaManager.list()`：`BUILTIN_PERSONA_PINNED_FIRST`（测试1–4）+ 其余内置 + 用户自定义。
- 测试1–4 **未**写入 `DEFAULT_ACTIVE`；需在 Web 人格工坊手动勾选后参与随机轮询。
- 旧内置「测试」（单字）已于 **W-025** 移除；`active_personae` / `custom_personae` 中的「测试」由 `_REMOVED_PERSONAE` 自动清理。原登记见 `docs/archive/`（若已归档）或 git 历史。

## 何时更新

- 在 `BUILTIN_PERSONAE` 中新增/修改/删除试验用人格时，同步更新对应 `persona-*.md`。
