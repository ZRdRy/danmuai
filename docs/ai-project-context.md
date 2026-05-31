# DanmuAI — AI / IDE Agent project context

**Audience:** Conversational AI, Cursor/Codex agents, Copilot-style assistants working in this repo.

**Authority:** When docs disagree with code, **`main.py` and `app/` source win**. This file is an index and boundary guide; detailed traps live in [AGENTS.md](../AGENTS.md). **Codex 单工单流程**（工单列表、当前仓库状态、完成报告）：见 [AGENTS.md](../AGENTS.md) §1–§10 与 [workflow/README.md](workflow/README.md)。

---

## 1. One-line summary

DanmuAI is a **Windows desktop AI danmaku assistant**: it captures the screen on a fixed interval, calls a vision-language model, parses short comments, and renders them on a **transparent Qt overlay**. Control and settings use a **local Web console** (FastAPI + pywebview); Qt is only for overlay and system tray.

---

## 2. Architecture overview

```text
python main.py
├─ DanmuApp (main.py)           bootstrap, Qt lifecycle, screenshot → AI → queue → overlay
├─ uvicorn thread               app/web_console.py — FastAPI 127.0.0.1:18765
├─ pywebview thread             app/webview_shell.py — desktop shell
├─ web/static/                  default control UI (index.html, app.js, warm-tokens.css)
├─ app/web_api/                 REST routes (register in routes.py)
├─ app/application/             read-only projections + scheduling/timing services
└─ DanmuOverlay (app/overlay.py) + DanmuEngine — always-on transparent danmaku
```

**UI facts (do not regress):**

- Default: `python main.py` → Web console + pywebview + Qt overlay/tray.
- Legacy Qt main window and `--qt-ui` / `--legacy-ui` / `DANMU_WEB_CONSOLE=0` → **`sys.exit(2)`**.
- **New product features** → `web/static/` and `app/web_api/` only (see §7).
- Overlay always runs; independent of which control UI is used.

**Thread model (easy to get wrong):**

| Work | Thread |
|------|--------|
| Screenshot timer, reply dequeue, Qt objects | **Main** (`QTimer`) |
| AI HTTP + image compress | `QThreadPool` (`MAX_IN_FLIGHT=1`) |
| HTTP handlers mutating Qt / config | **`WebConsoleBridge.invoke_on_main`** (sync writes) or **`xxx_requested.emit`** (async, e.g. `PUT /api/config`) |
| Global hotkey | `keyboard` callback → `_ToggleBridge` → main |

There is **no** `app/services/` or `app/runtime/` package. State boundaries live under **`app/application/`**.

### `app/application/` roles

| Module | Responsibility |
|--------|----------------|
| `runtime_state.py` | Read-only `RuntimeState.from_app()` |
| `status_snapshot.py` | `StatusSnapshotBuilder` → `GET /api/status` |
| `diagnostic_snapshot.py` | `DiagnosticSnapshotBuilder` → `GET /api/diagnostics` |
| `generation_pipeline_state.py` | Read-only generation fields |
| `request_scheduler.py` | Schedule gates; owns `last_api_trigger_at` |
| `request_timing_service.py` | RTT, `request_started_at_by_id`, `rtt_history` |
| `stats_state.py` | Session counters (danmu count, tokens, runtime) |
| `web_runtime_state.py` | Web error banner + display cache |
| `config_service.py` | Web config apply path |

`DanmuApp` remains bootstrap, lifecycle owner, and thin **façade** for Web/tests. See [final-architecture-baseline.md](final-architecture-baseline.md).

---

## 3. Main pipeline (normal mode only)

**Scope:** `截图 → AI 请求 → 回复解析 → 回复队列 → DanmuEngine → Overlay → HistoryWriter`

Only **normal mode** is active (`danmu_display_mode=realtime` is normalized to `normal` on load). Fixed screenshot interval + one visual API call per successful capture when no visual request is in flight.

**Protected call chain** — do not reorder or bypass casually:

```text
_on_screenshot_timer()
  → _on_normal_capture_tick()
  → _capture_screenshot()
  → _trigger_api_call()
  → [QThreadPool: AiRunnable]
  → _on_ai_reply()
  → _enqueue_reply_batch()
  → _consume_reply_queue()   [reply_timer, adaptive interval]
```

**Identifiers:**

| ID | Meaning |
|----|---------|
| `screenshot_id` | Incremented only after a **valid** capture |
| `scene_generation` | Reset on start/stop; memory metadata |
| `request_round` | Visual: `screenshot_round`; mic: negative seq |
| `request_timing_id` | `{request_round}:{screenshot_id}:{scene_generation}` — RTT and `_pending_request_meta` keys |

**Scheduling (do not bypass):**

- `RequestScheduler` — `min_api_interval`, in-flight gate, `last_api_trigger_at`
- `RequestTimingService` — `mark_started` / `consume_timing` on composite `request_timing_id`

Full narrative: [MAIN_PIPELINE.md](MAIN_PIPELINE.md). Step table for Boundary Guard: [main-pipeline-sequence.md](main-pipeline-sequence.md).

---

## 4. Key directories

| Path | Role |
|------|------|
| [main.py](../main.py) | `DanmuApp` — timers, capture, API trigger, queue, mic |
| [app/web_console.py](../app/web_console.py) | FastAPI app, `WebConsoleBridge`, bearer auth |
| [app/web_api/](../app/web_api/) | REST routes; **must use public `DanmuApp` facades** |
| [web/static/](../web/static/) | Control UI (HTML/JS/CSS) |
| [app/application/](../app/application/) | Snapshots, scheduler, timing, stats (not `app/services/`) |
| [app/overlay.py](../app/overlay.py) | Transparent topmost render (~60 fps when animating) |
| [app/danmu_engine.py](../app/danmu_engine.py) | Tracks, dedup, placement |
| [app/ai_client.py](../app/ai_client.py) | Doubao + OpenAI-compatible SSE; thinking disabled |
| [app/reply_parser.py](../app/reply_parser.py) | JSON parse + batch normalize |
| [app/config_store.py](../app/config_store.py) | SQLite `%APPDATA%/DanmuAI/`, Fernet keys |
| [app/memory/](../app/memory/) | Scene memory + dedup (`memory_mode`) |
| [tests/](../tests/) | pytest; shared fakes in `tests/fakes.py` |
| [scripts/boundary_guard.py](../scripts/boundary_guard.py) | Architecture regression scanner |
| [docs/archive/](../docs/archive/) | **Historical only** — not current behavior |

Config is **not** under `app/config/`; use `app/config_store.py` and `app/config_defaults.py`.

---

## 5. Required reading order

Read in this order when onboarding to a task. Skip sections you do not touch.

### P0 — read first

| File | Why |
|------|-----|
| **This file** | Index, boundaries, commands |
| [AGENTS.md](../AGENTS.md) | Dense module table, traps, env vars, `reason=` logs |
| [final-architecture-baseline.md](final-architecture-baseline.md) | Frozen fields, migrated ownership |
| [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md) | Web/API bans, pipeline protection, checklists |
| [main.py](../main.py) | Runtime source of truth for `DanmuApp` |

### P1 — module understanding

| File | When |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Structured overview |
| [MAIN_PIPELINE.md](MAIN_PIPELINE.md) | Changing capture/AI/queue behavior |
| [main-pipeline-sequence.md](main-pipeline-sequence.md) | Adding timers/threads (**same commit**) |
| [RUNTIME_STATE.md](RUNTIME_STATE.md) | Status vs diagnostics, field ownership |
| [runtime-state-map.md](runtime-state-map.md) | New `DanmuApp.__init__` fields |
| [WEB_CONSOLE.md](WEB_CONSOLE.md) | Web API, pages, Supabase frontend |
| [BOUNDARY_GUARD.md](BOUNDARY_GUARD.md) | Before PRs touching orchestration/Web |

**P1 code (read as needed):** `app/web_api/routes.py`, `app/web_console.py`, `app/application/request_scheduler.py`, `app/application/request_timing_service.py`, `app/application/status_snapshot.py`, `app/application/diagnostic_snapshot.py`, `app/overlay.py`, `app/danmu_engine.py`, `app/ai_client.py`, `app/reply_parser.py`.

### P2 — debugging / deep changes

| File | When |
|------|------|
| [DANMAKU_FORMULA.md](DANMAKU_FORMULA.md) | `empty_parse`, JSON contract |
| [scripts/boundary_guard.py](../scripts/boundary_guard.py) | Understanding Guard FAIL messages |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | ruff, full pytest batches |
| [docs/archive/](../docs/archive/) | **Context only** — may describe removed Qt UI or realtime mode |

**Tests by area:** `test_p0_main_flow.py`, `test_request_scheduling.py`, `test_boundary_guard.py`, `test_web_console.py`, `tests/conftest.py`, `tests/fakes.py`.

---

## 6. Frozen pipeline and ownership

### Do not casually rewrite

- `_trigger_api_call`, `_on_ai_reply`, `_consume_reply_queue`
- Splitting or refactoring `DanmuEngine` / `Overlay` coupling in drive-by PRs
- Second visual trigger paths (old rhythm/realtime) without updating [main-pipeline-sequence.md](main-pipeline-sequence.md)

### Stay on `DanmuApp` (do not move without explicit architecture decision)

`ai_in_flight`, `_pending_request_meta`, `_inflight_screenshot_id`, `_scene_generation`, `reply_buffer`, `_latest_screenshot`, `_latest_screenshot_id`, `QTimer`, `QThreadPool`, `QPixmap`, `_mic_service`.

### Migrated — use services, not new `DanmuApp` fields

| Concern | Owner |
|---------|--------|
| `last_api_trigger_at` | `RequestScheduler` |
| `request_started_at_by_id`, `rtt_history` | `RequestTimingService` |
| `danmu_count`, token totals, session start | `StatsState` |
| Web error + display cache | `WebRuntimeState` |

Do not add parallel throttle or RTT fields on `DanmuApp`.

---

## 7. Where to implement features

| Feature type | Location |
|--------------|----------|
| Web UI, settings, new REST | `web/static/`, register in `app/web_api/routes.py` |
| Personas / templates / models | `app/web_api/`, existing managers |
| Overlay appearance / tracks | `app/overlay.py`, `app/danmu_engine.py` |
| Capture / AI / queue timing | `main.py` — **avoid unless necessary** |

**Web write paths:** `PUT /api/config` → `save_config_requested.emit` (async). Other `routes.py` writes → `WebConsoleBridge.invoke_on_main` (sync, main thread). **Never** mutate Qt / `config_changed` from the HTTP thread without these entry points.

**Capture region:** `POST/GET /api/capture-region/*` — do **not** persist `region_*` via `PUT /api/config`.

**Public facades for Web** (examples): `build_status_snapshot()`, `build_diagnostic_snapshot()`, `apply_web_config_payload()`, `set_active_personae()`, `start()`, `stop()`, `toggle()`, `request_capture_region_selection()`.

Full ban list: [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md).

---

## 8. Runtime, snapshots, scheduling, diagnostics

```text
DanmuApp
  ├─ RequestScheduler / RequestTimingService / StatsState / WebRuntimeState
  ├─ build_status_snapshot() → StatusSnapshotBuilder → GET /api/status
  └─ build_diagnostic_snapshot() → DiagnosticSnapshotBuilder → GET /api/diagnostics
```

**Rules:**

- `/api/status` and `/api/diagnostics` are **separate**; status must not embed diagnostics-only fields.
- Web/API must **not** read `danmu_app._*`, `cached_danmu_lines`, `web_runtime_state`, `_last_api_trigger_at`, `_request_started_at_by_id`, `_rtt_history` directly.
- `GenerationPipelineState` and `RuntimeState` are **read-only** projections — no Qt imports, no calling `_trigger_api_call` / `_consume_reply_queue`.

**New Web-visible field:** extend `StatusSnapshotBuilder` (or add a façade on `DanmuApp`), not ad-hoc dicts in routes.

**New `DanmuApp` field:** register in [runtime-state-map.md](runtime-state-map.md) (backtick name).

Details: [RUNTIME_STATE.md](RUNTIME_STATE.md).

---

## 9. Before changing code — checklist

1. Read P0 docs for your area (§5).
2. If adding `self._…` on `DanmuApp` → [runtime-state-map.md](runtime-state-map.md).
3. If adding `QTimer` / `QThreadPool` / `threading.Thread` / `asyncio.create_task` → [main-pipeline-sequence.md](main-pipeline-sequence.md) **in the same commit**.
4. If exposing state to Web → `StatusSnapshotBuilder` or new public façade.
5. If touching SQLite schema → migration plan; **`config.conn` only in whitelist modules** (see §11).
6. User-visible behavior → [CHANGELOG.md](CHANGELOG.md); API/UI → [WEB_CONSOLE.md](WEB_CONSOLE.md).

---

## 10. Common verification commands

From repo root:

```bash
# Architecture guard (changed lines)
python scripts/boundary_guard.py

# Scheduling + guard tests
python -m pytest tests/test_request_scheduling.py tests/test_boundary_guard.py -q

# Core pipeline batch
python -m pytest tests/test_reply_parser.py tests/test_p0_main_flow.py tests/test_danmu_engine.py tests/test_config_store.py tests/test_ai_client.py -q

# Web batch
python -m pytest tests/test_web_console.py tests/test_web_persona_api.py tests/test_web_custom_models.py tests/test_image_compress.py tests/test_ui_mode.py -q

# Full suite
python -m pytest tests/ -q

# Lint (see CONTRIBUTING.md)
ruff check app main.py tests scripts
```

Run app locally: `pip install -r requirements.txt` then `python main.py`.

---

## 11. Boundary Guard, tests, and storage

**Boundary Guard** (`python scripts/boundary_guard.py`) scans **git-changed** lines for DanmuAI-specific regressions. Not a general linter.

Run when touching: `main.py`, `app/web_console.py`, `app/web_api/`, `app/application/`.

| Area | Rule (summary) |
|------|----------------|
| Web/API | No new `danmu_app._` / `app._` / `ai_worker._`; use `build_status_snapshot()` |
| `config.conn` | Whitelist only: `config_store`, `history_writer`, `session_run_log`, `templates`, `danmu_engine` |
| Timers/threads | Same diff must change `docs/main-pipeline-sequence.md` |
| Runtime fields | New `DanmuApp.__init__` fields → `docs/runtime-state-map.md` |
| Request services | `RequestScheduler` / `RequestTimingService` must not import Qt or call queue/overlay |
| Baseline file | `docs/final-architecture-baseline.md` must exist |

Temporary escape hatch (comment on same/near line):

```python
TODO(phase2-boundary): reason=..., current_private_access=..., target_public_api=...
```

Docs: [BOUNDARY_GUARD.md](BOUNDARY_GUARD.md). Rule implementation: [scripts/boundary_guard.py](../scripts/boundary_guard.py).

**Acceptance gates:** [scripts/run_acceptance_gates.py](../scripts/run_acceptance_gates.py), `tests/test_acceptance_gates.py`.

---

## 12. Rules for AI agents

1. **Minimize scope** — smallest correct diff; do not refactor unrelated code.
2. **Source over docs** — if unsure, read `main.py` / target module; do not trust [docs/archive/](archive/README.md) for current behavior.
3. **Do not** add Qt main window, realtime/rhythm timers, or Web reads of private `DanmuApp` fields.
4. **Do not** bypass `RequestScheduler` / `RequestTimingService` for API spacing or RTT.
5. **Do not** spread `config.conn` outside the whitelist.
6. **Do not** add timers/threads without updating `main-pipeline-sequence.md`.
7. **New Web features** → `web/static/` + `app/web_api/routes.py`; use existing managers (`PersonaManager`, `TemplateManager`, etc.).
8. **Traps and env vars** — see [AGENTS.md](../AGENTS.md) (encryption, dedup, MiMo audio, thinking disabled, `reason=` table).
9. **Run Boundary Guard** before claiming orchestration/Web work is done.
10. **No drive-by** splits of `DanmuEngine`/`Overlay` or rewrites of frozen pipeline functions.

### Common misconceptions

| Wrong assumption | Fact |
|------------------|------|
| `--qt-ui` still works | Removed → `sys.exit(2)` |
| `app/services/` exists | Use `app/application/` |
| Web can read `_last_api_trigger_at` | Use diagnostics snapshot / public APIs |
| Archive phase docs are current | Read [archive/README.md](archive/README.md); use ARCHITECTURE + MAIN_PIPELINE instead |

---

## Related indexes

- Human doc index: [docs/README.md](README.md)
- Agent cheat sheet: [AGENTS.md](../AGENTS.md)
- Product README: [README.md](../README.md)
