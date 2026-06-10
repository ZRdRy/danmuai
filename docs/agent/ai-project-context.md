# DanmuAI — AI / IDE Agent 项目上下文

> 读者：Codex、Cursor、Copilot 类 IDE Agent，以及需要在本仓库内改代码或改文档的维护者。  
> 权威性：文档与实现冲突时，以 `main.py` 与 `app/` 源码为准。

---

## 1. 一句话说明

DanmuAI 是一个 **Windows 桌面 AI 弹幕助手**：按固定间隔截图，调用视觉模型生成短弹幕，解析后进入回复队列，再通过 **Qt 透明 Overlay** 上屏；控制与配置走 **本地 Web 控制台**，默认由 **pywebview 桌面壳**承载。

---

## 2. 当前产品事实

- 默认启动：`python main.py`
  - 本地 Web 控制台
  - pywebview 桌面壳
  - Qt Overlay + 托盘
- 浏览器模式：`python main.py --web-browser`
- 已移除遗留 Qt 主窗；`--qt-ui` / `--legacy-ui` / `DANMU_QT_UI` / `DANMU_WEB_CONSOLE=0` 都应 `sys.exit(2)`。
- Overlay 始终独立存在，不依赖控制台是否可见。

---

## 3. 当前架构总览

```text
python main.py
├─ DanmuApp（main.py + app/main_*mixin.py）
│  ├─ 主链路：截图 -> AI -> 回复解析 -> 入队 -> 上屏
│  ├─ 生命周期：start / stop / quit
│  ├─ Web façade：status / diagnostics / config / start-stop / probe
│  └─ 主线程持有：QTimer / QPixmap / reply_buffer / in-flight 状态
├─ uvicorn 线程
│  └─ app/web_console.py（127.0.0.1:18765）
├─ pywebview 子进程
│  └─ app/webview_shell.py
├─ web/static/
│  └─ 默认控制台 UI（index.html、app.js、modules/*、warm-tokens*.css）
├─ app/web_api/
│  └─ 人格、模型、识图区域、读弹幕、诊断、直播弹幕层等 HTTP 路由
└─ app/overlay.py + app/danmu_engine.py
   └─ 透明置顶弹幕渲染
```

### `DanmuApp` 的当前拆分事实

`DanmuApp` 仍是单一运行态宿主，但代码已按职责拆到 mixin：

- `main.py`
  - 类定义
  - `_trigger_api_call`
  - `_on_ai_reply`
  - `_consume_reply_queue`
  - 入口 `main()`
- `app/main_mic_mixin.py`
  - 麦克风链路与读弹幕 probe/config façade
- `app/main_display_mixin.py`
  - live status、overlay/floating panel 显隐、测试弹幕注入
- `app/main_request_context_mixin.py`
  - request meta、timing、memory、密度/队列辅助
- `app/main_lifecycle_mixin.py`
  - 生命周期、错误处理、启动编排、`start/stop/quit`
- `app/main_web_facade_mixin.py`
  - Web/API 公开 façade
- `app/main_state_mixin.py`
  - `StatsState` / `WebRuntimeState` / 调度服务代理
- `app/main_launch_mixin.py`
  - Web 控制台打开与 pywebview attach 调度

---

## 4. 线程 / 进程模型

### 主线程（Qt GUI 线程）

- `screenshot_timer`
- `reply_timer`
- `_pool_topup_timer`
- `_mic_poll_timer`
- `_live_status_timer`
- `_lifetime_flush_timer`
- `DanmuOverlay`
- `QPixmap` 最新截图缓存
- `_trigger_api_call` / `_on_ai_reply` / `_consume_reply_queue`

### `QThreadPool`

- 视觉 AI 请求
- 麦克风插入 AI 请求
- 部分 probe / test-send 任务

### uvicorn 线程

- FastAPI 路由
- WebSocket / SSE
- 不得直接修改 Qt 对象

### pywebview 子进程

- `app/webview_shell.py`
- 子进程内部主线程拥有 `webview.start()`
- 通过 `ready_queue` / `nav_queue` 与主进程协作

### 线程边界结论

- **HTTP 线程写 Qt**：必须经 `WebConsoleBridge` 或 `QTimer.singleShot(0, ...)`
- **不要新增平行调度器**：`RequestScheduler` / `RequestTimingService` 是唯一调度/RTT 归属
- **不要随意增删 `QTimer` / `QThreadPool` / 新线程入口**

---

## 5. 主链路（当前唯一视觉主流程）

```text
DanmuApp.start()
  -> screenshot_timer.start()
  -> _on_normal_capture_tick()               [立即首 tick]

screenshot_timer.timeout
  -> _on_screenshot_timer()
  -> _on_normal_capture_tick()
       -> _capture_screenshot()
       -> _trigger_api_call()
            -> RequestScheduler / RequestTimingService
            -> QThreadPool.start(AiRunnable)
                 -> AiWorker._request()
            -> _on_ai_reply()
                 -> parse_ai_reply_with_memory()
                 -> normalize_reply_batch()
                 -> _enqueue_reply_batch()
                 -> _consume_reply_queue()   [直接或经 reply_timer]

reply_timer.timeout
  -> _consume_reply_queue()
       -> DanmuEngine.add_text()
       -> HistoryWriter.enqueue()
       -> Overlay render loop
```

### 这三个入口当前冻结

- `_trigger_api_call`
- `_on_ai_reply`
- `_consume_reply_queue`

可以在周边做辅助拆分，但不应把它们迁出 `main.py`，也不应绕过它们再造并行主流程。

---

## 6. 当前运行态边界

### 仍由 `DanmuApp` 直接持有

- `QTimer`
- `QPixmap`
- `reply_buffer`
- `ai_in_flight`
- `mic_in_flight`
- `_pending_request_meta`
- `_scene_generation`
- `_latest_screenshot*`
- `_inflight_*`

### 已迁移到服务对象 / 状态对象

| 归属 | 当前所有权 |
|------|------------|
| 调度节流 | `RequestScheduler` |
| RTT / started map / rtt_history | `RequestTimingService` |
| 会话计数 / token / start_time | `StatsState` |
| Web 错误与 display cache | `WebRuntimeState` |

### Web 只能经公开 façade 读取

- `build_status_snapshot()`
- `build_diagnostic_snapshot()`
- `build_live_status_snapshot()`
- `apply_web_config_payload()`
- `get_request_scheduler()`
- `get_request_timing_service()`
- `api_schedule_block_reason()`
- `start()` / `stop()` / `toggle()`
- `request_capture_region_selection()` / `reset_capture_region()`

---

## 7. Web 控制台事实

### 前端入口

- 运行骨架：`web/static/index.html`
- 主入口：`web/static/app.js`
- 主要模块：`web/static/modules/*`
- 样式入口：`web/static/warm-tokens.css`

### 路由注册

- `app/web_console.py`
  - `/api/status`
  - 会话 token
  - WebSocket / 基础运行态
- `app/web_api/routes.py`
  - 人格
  - 自定义模型
  - 识图区域
  - 公式化弹幕库
  - 读弹幕配置 / probe
  - 诊断
  - 直播弹幕层
  - 公告已读状态等

### Web 层禁止事项

- 禁止直接读 `danmu_app._*`
- 禁止直接读 `ai_worker._*`
- 禁止把 `/api/status` 逻辑拆成路由内 ad-hoc dict
- 禁止在 HTTP 线程直接改 Qt 对象

---

## 8. 当前高风险边界

1. 主链路顺序必须保持：`截图 -> AI -> 回复解析 -> 入队 -> 上屏`
2. `RequestScheduler` / `RequestTimingService` 不能被绕开
3. `DanmuEngine` 与 `Overlay` 的耦合方式不能顺手重写
4. `reply_buffer`、`ai_in_flight`、`QPixmap`、`QTimer` 所有权不能随意迁走
5. `app/web_api/*` 只能走公开 façade
6. 历史文档 `docs/archive/` 仅作背景，不能当成当前行为

---

## 9. 修改落点决策

| 需求类型 | 优先落点 |
|----------|----------|
| 控制台页面 / 交互 / 文案 | `web/static/` |
| 新 Web API / 现有接口扩展 | `app/web_api/` |
| 主链路 / 截图 / AI / 回复队列 | `main.py` + `app/main_*mixin.py` |
| Overlay / 轨道 / 渲染性能 | `app/overlay.py`、`app/danmu_engine.py` |
| 麦克风 / 语音 | `app/mic_*` |
| 状态投影 / 快照 / 调度服务 | `app/application/` |

---

## 10. 改动前建议阅读顺序

### 一律先读

1. `AGENTS.md`
2. `docs/当前仓库状态.md`
3. 当前工单正文

### 改代码时再读

1. `docs/CONTRIBUTING_ARCHITECTURE.md`
2. `docs/MAIN_PIPELINE.md`
3. `docs/RUNTIME_STATE.md`
4. `docs/WEB_CONSOLE.md`
5. `docs/BOUNDARY_GUARD.md`

---

## 11. 一句话结论

如果你不确定某个改动应不应该做，默认答案是：**先不要改主链路、不要新开线程、不要让 Web 读私有字段，先把需求收束到已有 façade 与现有边界里。**
