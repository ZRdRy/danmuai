# 内置人格：测试1

> 登记日期：2026-05-30（W-025）  
> 状态：试验中（内置，默认未勾选，**人格工坊列表置顶第 1 项**）

## 概要

| 项 | 值 |
|----|-----|
| 人格 ID | `测试1` |
| 翻译键 | `persona.test1` |
| 主题 | 真实直播间五人弹幕（玩梗/复读/大惊小怪/键盘侠/路人） |
| 推荐 `normal_reply_count` | **5** |

## 代码落点

`app/personae.py` → `BUILTIN_PERSONAE["测试1"]`；列表顺序由 `BUILTIN_PERSONA_PINNED_FIRST` 置顶。

## system_zh（人格段，运行时前部自动拼接输出契约）

见 `app/personae.py` 中 `BUILTIN_PERSONAE["测试1"]["system_zh"]`。

## user

`看图发弹幕：` / `Danmu for screenshot:`
