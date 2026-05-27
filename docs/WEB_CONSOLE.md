# Web 控制台

DanmuAI 默认通过 **本地 Web UI + pywebview 桌面壳** 运行，Qt 仅保留弹幕 Overlay 与托盘。

> 遗留 Qt 主窗（`--qt-ui` / `ui/`）已移除；传入 `--qt-ui`、`DANMU_QT_UI`、`DANMU_WEB_CONSOLE=0` 将报错退出。

## 启动

```bash
pip install -r requirements.txt
python main.py                  # pywebview + http://127.0.0.1:18765
python main.py --web-browser    # 系统浏览器
```

| 环境变量 | 说明 |
|----------|------|
| `DANMU_WEB_LAUNCH=browser` | 系统浏览器打开控制台 |
| `DANMU_DEDUP_PROFILE=1` | `/api/status` 含 `dedup_profile`，日志周期性汇总 |
| `DANMU_IMAGE_METRICS=1` | 运行时压缩 debug 指标 |
| `DANMU_SCENE_DEBUG=1` | 场景指纹探测日志 |

详见 [README.md](../README.md)、[AGENTS.md](../AGENTS.md)。

## 架构

| 组件 | 路径 | 说明 |
|------|------|------|
| HTTP API | `app/web_console.py` | FastAPI，`127.0.0.1:18765`，Bearer 鉴权 |
| 扩展路由 | `app/web_api/routes.py` | 人格、自定义模型、公式化弹幕库、压缩预览 |
| 静态页 | `web/static/` | Qwen 温馨风格 |
| 桌面壳 | `app/webview_shell.py` | pywebview（Windows WebView2） |
| Overlay | `app/overlay.py` | Qt 透明置顶弹幕 |

## 页面地图

| 侧栏 | 能力 |
|------|------|
| 运行概览 | 启停、状态、会话统计与持久累计（生成总弹幕、运行总时长、消耗总 Token） |
| 助手设置 | 全局配置、节奏/截图、图像压缩预览、自定义模型 |
| 公式化弹幕库 | 内置/自定义公式化短句开关、最小同屏补足、自定义句增删 |
| 人格工坊 | 提示词编辑、版本回滚预览、新建/删除自定义人格 |
| 弹幕日记 | 多级别过滤、复制可见、自动滚动 |
| 教程 | 飞书文档外链 |
| 问题反馈 | 社群说明、QQ 群二维码、赞赏码弹窗 |

## API 摘要

### 会话与核心

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/session` | 否 | 返回 `token`、`base_url` |
| GET | `/api/status` | 否 | 运行态与统计（含 `lifetime_danmu_count`、`lifetime_runtime_sec`、`lifetime_total_tokens`）；`DANMU_DEDUP_PROFILE=1` 时额外含 `dedup_profile` |
| GET/PUT | `/api/config` | PUT 需 Bearer | `WEB_CONFIG_KEYS` 子集；GET 返回掩码后的 `api_key` 与 `custom_models[].apiKey` |
| GET | `/api/screens` | 否 | 显示器列表 |
| GET | `/api/providers` | 否 | 服务商预设 |
| GET | `/api/model-catalog` | 否 | 视觉模型平台目录（模型 ID、价格、最便宜/麦克风标记） |
| GET | `/api/meta` | 否 | UI 模式、快捷键等 |

**视觉模型（助手设置 · API 页）**：选择带目录的服务商（火山方舟、阿里云百炼/DashScope、硅基流动/SiliconFlow 等）后，列表仅展示模型 ID；「本平台最便宜」「支持麦克风」等标识显示在 info 图标左侧，悬停 info 可查看名称与价格详情。切换服务商预设时会重置为该平台默认视觉模型（目录中最便宜项）并清空 API 密钥输入框；无目录或自选 ID 时使用「自定义模型」。扩展新平台时只需在 `app/model_catalog.py` 追加数据。
| GET | `/api/personae` | 否 | 人格列表与激活状态 |
| POST | `/api/start` `/api/stop` `/api/toggle` | Bearer | 生成/停止弹幕 |
| POST | `/api/probe` | Bearer | 全局 API 连接测试 |
| WS | `/ws/logs` `/ws/status` | Query `ws_token` | 日志与状态推送（与 session token 相同） |

### 人格与提示词（`app/web_api/persona.py`）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/personae/{name}/template` | 否 | 契约、system/user、builtin 标志 |
| GET | `/api/personae/{name}/versions` | 否 | 历史版本列表 |
| PUT | `/api/personae/{name}/template` | Bearer | 保存；内置人格仅更新 user 提示 |
| POST | `/api/personae/{name}/rollback` | 否 | body `{version}`，加载到编辑器预览 |
| POST | `/api/personae/{name}/restore` | Bearer | 内置人格恢复默认 |
| POST | `/api/personae` | Bearer | body `{name}`，创建自定义人格 |
| DELETE | `/api/personae/{name}` | Bearer | 删除非内置人格 |
| PUT | `/api/personae/active` | Bearer | body `{active: string[]}` |

### 自定义模型（`app/web_api/custom_models.py`）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/custom-models` | 否 | 列表（`apiKey` 掩码，`complete` 标志） |
| POST | `/api/custom-models` | Bearer | 新增 |
| PUT | `/api/custom-models/{index}` | Bearer | 按列表下标更新；掩码 key 保留原值 |
| DELETE | `/api/custom-models/{index}` | Bearer | 删除；默认模型自动回退 |
| POST | `/api/custom-models/{index}/default` | Bearer | 设为默认并写入全局 `model` |
| POST | `/api/custom-models/probe` | Bearer | 单模型连接测试 |

### 公式化弹幕库（`app/web_api/danmu_pool.py`）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/danmu-pool/meta` | 否 | 内置/自定义开关、`min_on_screen`、库条数、`effective_pool_enabled` |
| PUT | `/api/danmu-pool/settings` | Bearer | body `{builtin_enabled, custom_enabled, min_on_screen}` → `danmu_pool_enabled` / `danmu_pool_use_custom` / `min_on_screen` |
| GET | `/api/danmu-pool/custom` | 否 | 自定义句列表 |
| POST | `/api/danmu-pool/custom` | Bearer | 批量追加（`text` 多行或 `items`）；返回 `added` / `skipped` |
| DELETE | `/api/danmu-pool/custom` | Bearer | body `{texts: string[]}` 按文本删除 |

自定义句存 SQLite `custom_danmu_pool`（JSON），**不**经 `PUT /api/config`。补足条件：内置库 **或** 自定义库任一开启时 `min_on_screen` 生效；合并池见 `app/danmu_pool.py`。

**行为说明**

- **双来源 OR**：内置库（`data/danmu_pool_zh.json`，Web 只读开关）与自定义库可独立开启；运行时合并为同一抽样池。
- **同屏补足**：`min_on_screen` 默认 **5**；设为 **0** 关闭补足。任一库开启且 `min_on_screen > 0` 时，当屏上弹幕不足则从合并池随机补位（`main._maybe_pool_topup`）。
- **自定义句**：侧栏页批量追加/多选删除；不在 Web 中编辑内置 JSON 全文。
- **与助手设置分离**：`danmu_pool_*` / `min_on_screen` 仅通过 `/api/danmu-pool/*` 读写，勿写入 `PUT /api/config`。

### 图像压缩预览

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/preview/compress` | Bearer | `multipart/form-data`：`file`、`max_width`、`quality`；返回尺寸与 `preview_data_url`（不落盘，上限 10MB） |

**实现（双入口，参数一致）**

- 运行时：`main.compress_screenshot()`（`QPixmap` → JPEG Base64 data URI）
- Web 预览：`app/image_compress.compress_image_bytes()`（上传字节 → 同 scale/quality 逻辑）

本地调 JPEG 质量（不调用 AI、不写仓库图片）：[`scripts/bench_jpeg_quality.py`](../scripts/bench_jpeg_quality.py)，说明见 [scripts/README.md](../scripts/README.md)。

## 配置字段（Web 表单）

除 `WEB_CONFIG_KEYS` 外，表单还通过 `PUT /api/config` 提交 `api_key`（掩码不覆盖）、`active_personae`。

图像相关键：`eviction_mode`、`image_max_width`、`image_quality`（默认 **85**，未写入 config 时生效），以及 `empty_accel` 复选框。

公式化弹幕库（专用 API，不在 `WEB_CONFIG_KEYS`）：`danmu_pool_enabled`（内置库）、`danmu_pool_use_custom`（自定义库）、`min_on_screen`（默认 **5**，任一库开启且值 **>0** 时从合并池补足；两库都关则运行时不补足）。

弹幕生成 · `normal_recognition_interval_sec`（识图间隔，默认 **5** 秒，范围 1–60；截图后**立即**触发 AI）、`normal_reply_count`（每批弹幕条数，默认 **5**，范围 1–20）。上一请求 in-flight 时跳过本轮截图；回复入队为 append。

记忆（助手设置 · API 页，**简化/全面模式均显示**）：`memory_mode`（`off` / `dedup_only` / `scene_card` / `strong`，默认 `off`）、`memory_window`（1–20，默认 **10**）。进程内短记忆，不持久化；详见 [ARCHITECTURE.md](ARCHITECTURE.md#memory-modes)。

保存后更新人格工坊「输出契约」与运行时 AI 批次条数；`GET /api/config` 另返回只读 `reply_batch_total`（等于 `normal_reply_count`）。数据库中遗留的 `danmu_display_mode=realtime` 会在启动或 Web 保存时规范为普通模式行为。

## 视觉规范

- 原型 HTML：`prototype/Qwen_html_20260524_481u8vlmv.html`
- 设计系统：`prototype/Qwen_markdown_20260525_4vyxmv819.md`
- 令牌 CSS：`web/static/warm-tokens.css`

## 测试

```bash
python -m pytest tests/test_web_console.py tests/test_web_persona_api.py tests/test_web_custom_models.py tests/test_image_compress.py tests/test_ui_mode.py -v
```
