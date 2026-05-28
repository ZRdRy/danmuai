# Token 消耗点审计报告

**项目**：DanmuAI（`e:\test\danmu`）  
**审计日期**：2026-05-28  
**复核日期**：2026-05-29（W-002 收尾：库存预取死链已删、`ProbeRunnable` 已删、截图退避已接 `screenshot_interval_ms`）  
**范围**：只读代码分析，未修改任何源码（复核为对已落地改动的文档同步）  
**方法**：静态检索 + 主链路 `main.py` / `app/ai_client.py` / Web API / 记忆与 prompt 模块通读

---

## 1. 总览结论

1. **主成本集中在运行中的视觉弹幕链路**：`screenshot_timer` → 截图 JPEG Base64 → `AiWorker._request_*` 流式调用；默认约每 `normal_recognition_interval_sec`（默认 5s）一发，且每次请求**必带整帧截图**（`main.py` `DanmuApp._on_normal_capture_tick` / `_trigger_api_call`）。
2. **输出 Token 有硬下限**：`resolve_danmu_max_output_tokens` 将 `max_tokens` / `max_output_tokens` 下限钳在 **512**（`app/ai_client.py`），即使用户在 Web 配置更小值仍按 512 计费上限请求。
3. **输入 Token 主要来自**：压缩后截图（`max_width` 默认 768、`quality` 85）、`system_pt`（人格 + JSON 输出契约）、`user_pt`（用户模板 + 记忆/活动行 + 麦克风块）、可选 **WAV Base64 音频**（豆包麦克风轨）。
4. **并发视觉请求被限制为 1**（`MAX_IN_FLIGHT = 1`，`RequestScheduler.block_reason` 的 `in_flight`），但 **麦克风轨与视觉轨独立计数**（`mic_in_flight` / `ai_in_flight`），理论上可同时各 1 路 HTTP，形成 **双路扣费**（`main.py` `_trigger_mic_api_call` 不经过 `_api_schedule_block_reason`）。
5. **画面无变化时仍会请求 AI**：`_capture_frame_hash` / `_last_scene_hash` 存在，但当前主链路**未**在触发 API 前做 hash 跳过；`tests/test_p0_main_flow.py` 亦断言截图不推进 `scene_generation`。静态画面与动态画面请求频率相同。
6. **截图退避已接入主链路（W-002）**：`_record_stale_drop` 突发时 `_apply_screenshot_interval_backoff` 调用 `live_freshness.screenshot_interval_ms`，结构化日志 `screenshot_interval_backoff`（`backoff_level` / `old_interval_ms` / `new_interval_ms`）。**本地 fallback 仍未接 main**：`is_model_slow` / `build_local_fallback_batch` 无 `main.py` 调用（ISSUE-003 / 后续 W-003）。库存预取（`_should_request_new_batch` / `_schedule_next_screenshot`）与 `ProbeRunnable` 已删除。
7. **用户显式触发的额外扣费**：Web `POST /api/probe`、`/api/custom-models/probe`（`max_tokens: 1`）、`POST /api/mic/test-send`（真实模型 + 占位图 + 音频）、设置页压缩预览 `POST /api/preview/compress`（**不调用模型**，仅本地 PIL）。
8. **失败重试**：`AiWorker._request_doubao` / `_request_openai` 对超时/未知异常最多 **2 次**尝试（`for attempt in range(2)`），HTTP 4xx/5xx **不重试**；超时一次可能产生 **双倍** 输入侧计费（视厂商是否对未完成流计费）。

---

## 2. Token 消耗点清单

| 编号 | 文件路径 | 函数/类/位置 | 消耗类型 | 触发条件 | 消耗内容 | 风险等级 | 说明 |
|------|----------|--------------|----------|----------|----------|----------|------|
| T01 | `main.py` | `DanmuApp._on_normal_capture_tick` → `_trigger_api_call` | 视觉 LLM + 图片 | `screenshot_timer` 超时且 `engine.running`、无视觉 in-flight、未 `failure_backoff_paused` | JPEG 截图 + system/user prompt + 最多 512 output tokens | **P1** | 产品主路径；默认 5s 间隔（`normal_recognition_interval_sec`） |
| T02 | `main.py` | `DanmuApp.start` → `_on_normal_capture_tick` | 同上 | 用户启动弹幕 | 立即额外 1 次 API（与定时器叠加） | **P1** | `start()` 末尾直接调用 `_on_normal_capture_tick()` |
| T03 | `app/runnable.py` | `AiRunnable.run` | 同上（工作线程） | `QThreadPool` 执行 | `compress_fn(pixmap)` → `AiWorker._request` | **P1** | 压缩失败 emit error，不计成功 tokens |
| T04 | `app/ai_client.py` | `AiWorker._request` → `_request_doubao` / `_request_openai` | HTTP 流式 API | `AiRunnable` / `send_mic_probe` 调用 | 多模态 body + stream usage | **P1** | 唯一生产级 HTTP 客户端 |
| T05 | `main.py` | `compress_screenshot` | 图片编码（影响输入 token） | 每次 AI 请求前 | 缩放到 `image_max_width`（默认 768）、JPEG `image_quality`（默认 85） | **P1** | 分辨率/质量直接决定 vision token |
| T06 | `app/personae.py` | `PersonaManager.get_prompt` + `ensure_reply_contract` | Prompt 文本 | 每次 `_trigger_api_call` / `_trigger_mic_api_call` | `system_pt`：输出契约 + 人格；`user_pt`：模板句 | **P1** | 「测试」人格 `system_zh` 极长（数百字），显著抬高 input |
| T07 | `main.py` | `DanmuApp._append_scene_memory_to_user_pt` | Prompt 注入 | `memory_mode != off` 且活动摘要为空 | `SceneMemoryStore.format_prompt_for_generation` 块 | **P1** | 预算 220–700 字符（`memory_prompt_builder.py`） |
| T08 | `app/memory/activity_prompt.py` | `format_activity_prompt_line` | Prompt 注入 | `memory_mode != off` 且 `activity_summary` 非空 | 单行「近期状态：…」（最长 60 字，`activity.py`） | **P2** | 优先于场景记忆块（`main.py` 1200–1202 行） |
| T09 | `main.py` | `DanmuApp._trigger_mic_api_call` | 视觉 + 音频 LLM | 麦克风端点检测 `_on_mic_utterance_end` | 最新截图 + `MIC_INSERT_BLOCK` + WAV data URI | **P1** | 仅豆包 Responses；与定时视觉轨并行可能双扣费 |
| T10 | `app/mic_prompt.py` | `build_mic_insert_user_pt` | Prompt 注入 | 麦克风插入 | 固定 6 条 JSON 指令块 | **P1** | 增加 user_pt 长度 |
| T11 | `app/mic_test_send.py` | `send_mic_probe` / `run_mic_test_send` | 探测 API | Web `POST /api/mic/test-send` | 占位 64×64 图 + 录音 WAV + 短 user 句 | **P1** | 用户手动；`ai_worker._request_doubao` 同步调用 |
| T12 | `app/api_probe.py` | `probe_connection` / `_probe_*` | 连通性探测 | Web `POST /api/probe`、`/api/custom-models/probe` | `ping` 文本，`max_tokens`/`max_output_tokens`=1 | **P2** | 用户点击测试连接；HTTP 线程同步 |
| T13 | `app/web_api/routes.py` | `probe_api_connection` 等 | 路由入口 | 设置页保存前测试 | 委托 T12 | **P2** | |
| T14 | `app/ai_client.py` | `_request_*` 内 `for attempt in range(2)` | 重试 | 超时或未知异常 | 可能重复整次请求 body | **P0** | HTTP 错误不重试；超时重试有双倍风险 |
| T15 | `app/application/request_scheduler.py` | `RequestScheduler.block_reason` | 节流（防调用） | `_trigger_api_call` 前 | `min_api_interval` 默认 800ms（`DANMU_MIN_API_INTERVAL_MS`） | **P2** | 仅视觉轨；与截图周期相比通常不是主瓶颈 |
| T16 | `main.py` | `DanmuApp._on_normal_capture_tick` | 跳过截图（省 API） | `_has_visual_request_in_flight()` | 无 | **P2** | in-flight 期间不截图、不触发；**不**比较画面 hash |
| T17 | `main.py` | `DanmuApp._on_ai_error` | 暂停 API | 连续失败 ≥ `MAX_CONSECUTIVE_FAILURES`（5）或 fatal 401/403/余额 | 停 `screenshot_timer` | **P2** | 降本保护；fatal 立即停 |
| T18 | `app/reply_parser.py` | `normalize_reply_batch` | **不**调用模型 | AI 回复条数不足 | 本地 `danmu_pool` 抽样补齐 | **P2** | 仅影响展示，不增 API；但抬高 T01 的 output 目标条数间接促长生成 |
| T19 | `app/danmu_pool.py` + `main.py` | `_maybe_pool_topup` | **不**调用模型 | 屏上弹幕低于 `min_on_screen` | 本地池 | **P2** | 500ms 定时器，零 API |
| T20 | `app/web_api/routes.py` | `preview_compress` | **不**调用模型 | 设置页压缩预览 | 本地 JPEG | **P2** | `app/image_compress.py` |
| T21 | ~~`app/probe_runnable.py`~~ | ~~`ProbeRunnable`~~ | **已删除** | W-002 移除 | — | **P2** | 连通性探测走 T12 `api_probe` 同步 |
| T22 | `app/live_freshness.py` | `build_local_fallback_batch` / `is_model_slow` | **未接 main** | `main.py` 无调用 | 设计为慢模型本地句 | **P2** | 单测覆盖；上屏见 ISSUE-003 / W-003 |
| T23 | `main.py` | `_scene_generation` 相关 | 代际/丢弃 | 全程多为 0 | 记忆 `on_scene_change` 未触发 | **P2** | `grep` 显示 main 内无 `+= 1`；场景记忆代际切换逻辑**待确认**是否在其他提交/分支 |
| T24 | `app/ai_client.py` | `resolve_danmu_max_output_tokens(..., use_thinking=False)` | 输出上限 | 所有弹幕请求 | 下限 512 output | **P1** | `use_thinking` 配置项在运行时**固定 False** |
| T25 | `main.py` | `personae.pick_random` | 人格随机 | 每 API 次 | 不同长度 system_pt | **P2** | 激活人格越多，平均 prompt 长度波动 |

---

## 3. AI 调用链路图

### 3.1 视觉弹幕主链路（运行中，持续扣费）

```text
用户 start() / 热键 toggle
  → main.py DanmuApp.start()
  → screenshot_timer（间隔 DanmuApp._normal_recognition_interval_ms，默认 5000ms）
  → DanmuApp._on_screenshot_timer → _on_normal_capture_tick
       ├─ 若 _has_visual_request_in_flight() → return（跳过本 tick）
       ├─ DanmuApp._capture_screenshot()（ScreenCapturer.grab，main.py）
       └─ DanmuApp._trigger_api_call(source="normal_interval")
            ├─ RequestScheduler.block_reason（app/application/request_scheduler.py）
            │    └─ in_flight | min_api_interval(800ms) | scene_block(当前恒 "")
            ├─ PersonaManager.pick_random / get_prompt（app/personae.py）
            ├─ user_pt += {current_time},{round} + _append_scene_memory_to_user_pt（main.py）
            │    └─ memory: app/memory/store.py → app/memory_prompt_builder.py
            │    └─ activity: app/memory/activity_prompt.py
            └─ QThreadPool → app/runnable.py AiRunnable.run
                 ├─ compress_screenshot（main.py，或 config image_max_width/quality）
                 └─ app/ai_client.py AiWorker._request
                      ├─ doubao: POST {endpoint}/responses（input_image + input_text [+无音频]）
                      └─ openai: POST {endpoint}/chat/completions（messages + image_url）
  → 信号 finished → main.py DanmuApp._on_ai_reply
       ├─ parse_ai_reply_with_memory（app/reply_parser.py）
       ├─ normalize_reply_batch（不足则从 danmu_pool 本地补，不再请求）
       └─ _enqueue_reply_batch → reply_timer → _consume_reply_queue → overlay
```

### 3.2 麦克风插入链路（叠加扣费）

```text
MicUtteranceDetector 端点（main.py _on_mic_utterance_end）
  → DanmuApp._trigger_mic_api_call(pcm)
       ├─ mic_in_flight += 1（不阻塞 screenshot_timer 的 ai_in_flight 判断）
       ├─ get_prompt + build_mic_insert_user_pt（app/mic_prompt.py）
       ├─ pcm_to_wav_data_uri（app/mic_encode.py）
       └─ AiRunnable(..., mic_pcm, mic_attach_audio=True)
            → AiWorker._request_doubao（+ input_audio）
  → _handle_mic_ai_reply → 入队优先 prepend_batch
```

### 3.3 用户手动 / 设置页链路

```text
web/static/app.js
  → POST /api/probe 或 /api/custom-models/probe
       → app/web_api/routes.py → app/api_probe.py probe_connection（max 1 token）

  → POST /api/mic/test-send
       → main.py DanmuApp.run_mic_test(send_to_ai=True)
       → app/mic_test_send.py run_mic_test_send → send_mic_probe → AiWorker._request_doubao

  → POST /api/preview/compress
       → app/image_compress.py compress_image_bytes（无 LLM）
```

---

## 4. Prompt 拼接来源清单

| 来源 | 文件路径 | 是否可控 | 是否可能过长 | 说明 |
|------|----------|----------|--------------|------|
| JSON 输出契约（条数、字数、格式） | `app/personae.py` `get_reply_contract` / `ensure_reply_contract` | 是（`normal_reply_count`、`danmu_max_chars`） | 中 | 随 `normal_reply_count` 1–20 条线性变长 |
| 内置/自定义人格 system | `app/personae.py` `BUILTIN_PERSONAE` / `custom_personae` | 是（Web 人格编辑） | **是**（「测试」人格极长） | 拼在 system 侧（豆包 `instructions`） |
| 用户 prompt 模板 | `app/personae.py` `user_zh`/`user_en` 或自定义 `user_pt` | 是 | 低 | 默认一句截图指令 |
| `{current_time}` / `{round}` | `main.py` `_trigger_api_call` | 否（运行时替换） | 低 | 个位数字符 |
| 场景记忆块 | `app/memory_prompt_builder.py` `build_memory_prompt_block` | 是（`memory_mode`） | 有预算封顶 | off/dedup_only/scene_card/strong；220–700 字符 |
| 活动摘要行 | `app/memory/activity.py` + `activity_prompt.py` | 间接（`memory_mode`） | 低（≤60 字） | 有摘要时**替代**记忆块注入 |
| 麦克风插入块 | `app/mic_prompt.py` `MIC_INSERT_BLOCK` | 否（固定文案） | 中 | 仅麦克风轨 |
| 截图（多模态） | `main.py` `compress_screenshot` | 是（`image_max_width`、`image_quality`、捕获区域） | **是** | 全屏高分辨率仍缩到 768 宽；区域裁剪可减 token |
| 音频（多模态） | `app/mic_encode.py` | 是（`mic_window_sec` 等） | **是** | 豆包 `input_audio`；视觉轨无音频 |
| AI 返回中的 scene_memory | `app/reply_parser.py` `parse_ai_reply_with_memory` | 否（模型输出） | 影响**下一轮** input | 写入 `SceneMemoryStore`，非当次请求 |

**不进入 prompt 但相关的配置**：`temperature`（`app/ai_client.py`）、`max_tokens`（下限 512）、`model` / 自定义模型（`AiWorker._resolve_request_credentials`）。

---

## 5. 高频/重复消耗风险

| 风险点 | 结论 | 证据 |
|--------|------|------|
| 画面无变化仍请求 | **是** | `_on_normal_capture_tick` 截图后直接 `_trigger_api_call`；无 hash 门控；`tests/test_p0_main_flow.py` `test_capture_does_not_advance_scene_generation` |
| 并发多视觉请求 | **否**（视觉轨） | `MAX_IN_FLIGHT=1`，in-flight 时跳过 tick；`RequestScheduler` `in_flight` |
| 视觉 + 麦克风并发 | **可能** | `mic_in_flight` 与 `ai_in_flight` 独立；`_trigger_api_call` 不检查 mic in-flight |
| 失败重试重复扣费 | **可能**（超时/网络） | `ai_client.py` `attempt in range(2)`；HTTP 错误不重试 |
| 重复注入同一段上下文 | **部分** | 每请求重新拼 prompt；记忆块随代际更新，但 `_scene_generation` 在 main 中恒 0 时记忆代际切换弱 |
| 过长历史/热梗/记忆 | **有界** | `memory_prompt_builder` 字符预算；活动摘要 60 字；**热梗库不进 prompt**（仅 `reply_parser` 本地补齐） |
| 用户不知情的后台调用 | **运行弹幕时自动** | `screenshot_timer`；非 probe；停止 `stop()` 后 timer 停 |
| 本地 fallback 减 API | **当前未生效** | `build_local_fallback_batch` 无 main 调用（ISSUE-003） |
| 截图退避减频 | **是**（W-002） | `_apply_screenshot_interval_backoff` → `screenshot_interval_ms`；成功回复后 level 递减 |
| 库存预取额外 API | **否** | 库存预取死链已删（W-002） |
| start 瞬间双请求 | **可能** | `start()` 立即 `_on_normal_capture_tick` + timer 后续 tick |
| empty_parse 仍扣费 | **是** | API 成功但解析无弹幕时仍累计 `input_tokens`/`output_tokens`（`_on_ai_reply` 1682 行 return 前已记账） |

**待确认（需运行时日志）**：

- 设置 `DANMU_API_SCHEDULE_DEBUG=1` 观察 `decision=block|fire` 与 `block_reason`（`app/api_schedule.py`）。
- 对比 `screenshot_id` 递增与 API 日志条数，验证 in-flight 跳过是否按预期。
- 开麦时同时运行视觉弹幕，抓包或日志是否出现两路并发 HTTP。

---

## 6. 成本优化建议

### P0 必须关注

| 问题 | 涉及文件 | 为何消耗 token | 可验证的优化方向 |
|------|----------|----------------|------------------|
| 静态画面仍按固定间隔全量识图 | `main.py` `_on_normal_capture_tick`、`_trigger_api_call`；`app/scene_fingerprint.py` | 每 tick 发送 JPEG + 长 prompt，与画面变化无关 | 触发前比较 `_capture_frame_hash` 与 `_last_scene_hash`，未变则跳过 API（保留截图缓存供 mic）；用日志统计「skipped_unchanged」比例 |
| 超时重试可能导致双倍请求 | `app/ai_client.py` `_request_doubao` / `_request_openai` | 每次重试重新 POST 全 body（含图） | 区分可重试错误；或仅重试无图 ping；对比厂商账单与 `attempt` 日志 |
| 视觉 + 麦克风双路并发 | `main.py` `_trigger_api_call`、`_trigger_mic_api_call` | 两路同时 multimodal | mic 触发时延迟视觉或共用 `in_flight` 总闸；压测同时开麦 + 弹幕 |

### P1 建议优化

| 问题 | 涉及文件 | 为何消耗 token | 可验证的优化方向 |
|------|----------|----------------|------------------|
| 输出下限 512 偏高 | `app/ai_client.py` `resolve_danmu_max_output_tokens` | 5 条短弹幕往往用不满 512 output | 按 `normal_reply_count` 动态下限；A/B 对比 parse 失败率与账单 |
| 默认 5s 间隔 × 全屏图 | `main.py` `_normal_recognition_interval_ms`；`config_defaults.py` | 高频 vision input | 用户可调间隔；stale 突发时退避已接 `screenshot_interval_ms`（W-002） |
| 长人格 system（如「测试」） | `app/personae.py` `BUILTIN_PERSONAE` | 每次请求复制大段 system | 缩短内置文案；Web 提示人格长度；默认激活集排除测试人格 |
| `memory_mode` 非 off 时增量 prompt | `app/memory_prompt_builder.py` | 每请求 +数百字符 | 默认 off 已合理；strong 模式成本更高，文档标明 |
| mic test-send 真实调用 | `app/mic_test_send.py`、`routes.py` | 用户误点即发音频+图 | UI 二次确认；展示预估；与 probe 一样限流 |
| start 立即 + timer 首轮 | `main.py` `start()` | 短时间 2 次 API | start 仅 timer 不立即 tick，或合并 |
| empty_parse 仍付 input+output | `main.py` `_on_ai_reply` | 模型有返回但 JSON 不合格 | 监控 `reason=empty_parse` 率；调 prompt/模型 |

### P2 可后续优化

| 问题 | 涉及文件 | 为何消耗 token | 可验证的优化方向 |
|------|----------|----------------|------------------|
| 接线本地 fallback | `app/live_freshness.py`、`main.py` | 慢模型时可用零 API 句顶屏 | `is_model_slow` 为真时 `build_local_fallback_batch` + 推迟 `_trigger_api_call`（W-003） |
| ~~截图退避未放大间隔~~ | — | — | **已完成**（W-002） |
| ~~删除或接入死代码~~ | — | — | **已完成**（W-002：库存预取、`ProbeRunnable`） |
| `scene_generation` 不递增 | `main.py`（`_scene_generation` 仅复位） | 记忆代际、丢弃逻辑弱化 | 恢复场景探测 bump 或文档标明已禁用 |
| probe 频繁点击 | `app/api_probe.py`、Web | 每次 1 token 仍计费 | 前端节流；合并探测与保存 |
| `use_thinking` 配置闲置 | `config_defaults.py`、`ai_client.py` | UI 可能误导用户以为可关 thinking 省钱 | 文档说明运行时固定 disabled |
| 压缩预览误认 API | `app/image_compress.py` | 无 token，但占带宽 | 保持与 LLM 路径隔离即可 |

---

## 附录 A：成本控制机制速查

| 机制 | 位置 | 作用 |
|------|------|------|
| `normal_recognition_interval_sec` 1–60s | `main.py` `_normal_recognition_interval_ms` | 截图/API 主节奏 |
| `DANMU_MIN_API_INTERVAL_MS`（默认 800） | `app/api_schedule.py` | 两次视觉触发最小间隔 |
| `MAX_IN_FLIGHT=1` | `main.py` | 视觉并发上限 |
| `MAX_MIC_IN_FLIGHT=1` | `main.py` | 麦克风并发上限（不与视觉互斥） |
| `failure_backoff_paused` + 连续 5 失败 | `main.py` `_on_ai_error` | 停 timer |
| fatal 401/403/余额 | `main.py` `_on_ai_error` | 立即停 timer |
| `resolve_danmu_max_output_tokens` floor 512 | `app/ai_client.py` | 输出 token 下限 |
| `THINKING_DISABLED` | `app/ai_client.py` | 避免 reasoning 占 output |
| JPEG max width / quality | `main.py`、`config_defaults.py` | 输入 vision 大小 |
| `memory_prompt_builder` 预算 | `app/memory_prompt_builder.py` | 记忆 injection 上限 |
| 流式 `usage` 统计 | `app/ai_client.py` `parse_stream_usage` | 会话 token 累计 |

---

## 附录 B：建议的验证命令（不修改代码）

```bash
# 全量单测（含 ai_client、main flow）
python -m pytest tests/test_ai_client.py tests/test_p0_main_flow.py tests/test_api_schedule.py -q

# 开调试日志后手动跑一轮（需 API Key）
set DANMU_API_SCHEDULE_DEBUG=1
python main.py
# 观察 app 日志中 api_schedule decision= 与 app.api_triggered
```

---

*本报告由静态代码审计生成；若与 `docs/MAIN_PIPELINE.md` 或 archive 文档冲突，以 `main.py` 与 `app/` 源码为准。*
