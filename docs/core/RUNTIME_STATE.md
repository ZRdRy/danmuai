# Runtime State

DanmuAI 当前仍以 `DanmuApp` 作为主要运行态宿主，但已经把一部分状态所有权收敛到独立服务或状态对象中。Web 和诊断层只能读取这些状态的**公开投影**，不能直接翻私有字段。

---

## 1. 当前层次

```text
DanmuApp（main.py + app/main_*mixin.py）
├─ 主线程对象与冻结字段
├─ StatsState
├─ WebRuntimeState
├─ RequestScheduler
├─ RequestTimingService
├─ StatusSnapshotBuilder
└─ DiagnosticSnapshotBuilder
```

---

## 2. `DanmuApp` 继续持有的状态

这些状态仍属于主线程编排层：

- `QTimer`
- `QPixmap`
- `reply_buffer`
- `ai_in_flight`
- `mic_in_flight`
- `_pending_request_meta`
- `_scene_generation`
- `_latest_screenshot*`
- `_inflight_*`
- `_mic_service`
- `_mic_orchestrator`
- `web_server` / `web_bridge` / `webview_shell`

原因不是“它们永远不能拆”，而是它们当前与 Qt 生命周期、主链路顺序或现有 façade 深度绑定。

---

## 3. 已明确迁移出去的所有权

| 归属对象 | 负责内容 |
|----------|----------|
| `StatsState` | 会话弹幕数、token 总量、会话开始时间 |
| `WebRuntimeState` | Web 错误提示、layout/danmu_lines cache |
| `RequestScheduler` | `last_api_trigger_at`、调度阻塞判断 |
| `RequestTimingService` | `request_started_at_by_id`、`rtt_history`、RTT 消费 |

`DanmuApp` 可以保留兼容 façade 或 property，但不应再创建这些字段的平行副本。

---

## 4. Web / Diagnostics 只能读什么

### `/api/status`

只能通过：

```text
DanmuApp.build_status_snapshot()
-> StatusSnapshotBuilder
```

### `/api/diagnostics`

只能通过：

```text
DanmuApp.build_diagnostic_snapshot()
-> DiagnosticSnapshotBuilder
```

### 明确禁止

- 路由层直接读 `danmu_app._*`
- 路由层自己拼 ad-hoc status dict
- Web 前端通过隐式字段名推断运行态内部结构

---

## 5. 新增运行态字段时怎么做

1. 先判断字段该不该属于 `DanmuApp`
2. 如果它更像统计、显示缓存、RTT、调度信息，优先放到现有状态对象 / 服务对象
3. 在 [runtime-state-map.md](runtime-state-map.md) 中登记
4. 如果要对 Web 可见，走 snapshot builder，不要让路由直接读取
5. 运行 `python scripts/boundary_guard.py`

---

## 6. 当前运行态设计的原则

### 原则一：所有权优先

先回答“谁拥有这份状态”，再回答“谁要读取它”。

### 原则二：投影优先

Web 要看的不是原始私有字段，而是：

- `StatusSnapshotBuilder`
- `DiagnosticSnapshotBuilder`
- 公开 façade

### 原则三：不要为了减少行数打散状态

把字段从 `main.py` 拆到 mixin，不等于把它的所有权迁走。  
当前 mixin 拆分主要是**代码职责拆分**，不是**运行态归属重写**。

---

## 7. 当前风险提醒

1. `runtime-state-map.md` 必须跟随运行态字段变化一起更新
2. `main-pipeline-sequence.md` 必须跟随线程/定时器入口变化一起更新
3. 不要把 `reply_buffer`、`ai_in_flight`、`QPixmap`、`QTimer` 迁到 `app/application/`
4. 不要把 `RequestScheduler` / `RequestTimingService` 再包装成第二套调度系统

---

## 8. 相关文档

- [runtime-state-map.md](runtime-state-map.md)
- [MAIN_PIPELINE.md](MAIN_PIPELINE.md)
- [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md)
- [final-architecture-baseline.md](final-architecture-baseline.md)
