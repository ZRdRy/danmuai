# Architecture

## 总体结构

- `main.py`
  - `DanmuApp` 负责状态机、截图调度、回复消费、失败退避和统一退出
  - `MainWindow` 负责设置、日志、模板和控制台四个页面
- `app/snipper.py`
  - `ScreenCapturer` 从主屏幕按配置区域抓图
- `app/ai_client.py`
  - `AiWorker` 在 `QThreadPool` 线程中通过 `httpx` 发起同步请求，并把结果通过 Qt 信号回送主线程
- `app/reply_queue.py`
  - `AIReplyFIFOBuffer` 维护有限长度回复队列，避免内存无限增长
- `app/reply_parser.py`
  - 解析模型输出并标准化为固定 5 条弹幕
- `app/overlay.py` + `app/danmu_engine.py`
  - 负责弹幕布局、轨道调度、碰撞规避和渲染

## 关键时序

1. `DanmuApp.start()` 重置状态并触发下一次截图调度。
2. `DanmuApp._screenshot_loop()` 抓取配置区域，生成新的 `screenshot_id` 和 `scene_generation`。
3. `AiRunnable.run()` 在线程池里压缩截图，再调用 `AiWorker._request()`。
4. `AiWorker` 返回后触发 `finished` 或 `error` 信号。
5. `DanmuApp._on_ai_reply()` 先做过期判定，再把回复标准化为 5 条，放入有限队列。
6. `DanmuApp._consume_reply_queue()` 按右侧密度自适应节奏逐条送入 `DanmuEngine`。

## 稳定性约束

- 每次截图都有单调递增的 `screenshot_id`
- 场景指纹变化时会提升 `scene_generation`，并清空旧回复和待显示弹幕
- 过期回复、旧场景回复、超出新鲜度阈值的回复会被丢弃
- `AiWorker` 使用请求超时和连续失败退避，避免无限挂起
- `quit()` 会先 `stop()`、标记停止、关闭 HTTP 客户端并等待线程池短暂收尾

## 发布边界

- 当前版本只支持主屏幕
- 当前版本只支持坐标配置截图区域，不包含可视化框选
- 历史记录默认只保存弹幕文本，不保存截图原图
