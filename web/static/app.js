/** DanmuAI Web Console — 温馨 Qwen 原型 */

const API = { token: null, base: '' };
const MASKED_API_KEY = '********';

const CONFIG_FIELDS = [
  'api_endpoint', 'api_mode', 'model', 'temperature', 'max_tokens',
  'danmu_speed', 'danmu_lines', 'danmu_max_chars', 'dedup_threshold',
  'screen_index', 'layout_mode', 'opacity', 'font_size', 'hotkey',
  'eviction_mode',
  'image_max_width', 'image_quality',
  'mic_window_sec', 'memory_mode', 'memory_window',
  'normal_recognition_interval_sec', 'normal_reply_count',
];

const NORMAL_REPLY_COUNT_MIN = 1;
const NORMAL_REPLY_COUNT_MAX = 20;
const DEFAULT_NORMAL_REPLY_COUNT = 5;

const REPLY_COUNT_MIN = 2;
const REPLY_COUNT_MAX = 7;
const DANMU_MAX_CHARS_MIN = 5;
const DANMU_MAX_CHARS_MAX = 80;
const DEFAULT_DANMU_MAX_CHARS_ZH = 15;
const DEFAULT_DANMU_MAX_CHARS_EN = 40;

let providersCache = [];
let catalogCache = { platforms: [] };
const VISION_MODEL_CUSTOM_VALUE = '__custom__';
const logBuffer = [];
let logLevelFilters = new Set(['INFO', 'WARNING', 'ERROR']);
let logAutoScroll = true;
let currentPersonaId = '';

function authHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (API.token) headers.Authorization = `Bearer ${API.token}`;
  return headers;
}

/** Re-fetch session token (required after each `python main.py` restart). */
async function refreshSession() {
  const sessionUrl = new URL('/api/session', window.location.origin).href;
  const res = await fetch(sessionUrl, { cache: 'no-store' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = formatApiError(err.detail, res.statusText);
    throw new Error(
      `无法获取控制台会话（HTTP ${res.status}）: ${detail}。`
      + '请确认终端有「Web 控制台 HTTP/WS 已监听」，且地址栏为 http://127.0.0.1:18765 后刷新页面。',
    );
  }
  const session = await res.json();
  if (!session?.token) {
    throw new Error('会话接口未返回 token，请重启 python main.py 并刷新页面');
  }
  API.token = session.token;
  API.base = (session.base_url || window.location.origin).replace(/\/$/, '');
  REALTIME.lastLogsPollTs = 0;
  return session;
}

function logEntryKey(item) {
  return `${item.ts}|${item.level}|${item.message}`;
}

function enc(name) {
  return encodeURIComponent(name);
}

function showToast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast show ${isError ? 'text-red-700' : 'text-warmText'}`;
  setTimeout(() => el.classList.remove('show'), 3200);
}

function formatApiError(detail, fallback = '请求失败') {
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join('.') : '';
        const msg = d.msg || d.message || JSON.stringify(d);
        return loc ? `${loc}: ${msg}` : msg;
      })
      .join('；');
  }
  return String(detail);
}

async function apiFetch(path, options = {}, retried = false) {
  if (!API.base) await refreshSession();
  const res = await fetch(`${API.base}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if ((res.status === 401 || res.status === 403) && !retried) {
    await refreshSession();
    return apiFetch(path, options, true);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const fallback =
      res.status === 404
        ? '接口不存在，请完全退出并重新运行 python main.py 后再试'
        : res.statusText;
    throw new Error(formatApiError(err.detail, fallback));
  }
  return res.json();
}

async function apiFormFetch(path, formData) {
  const res = await fetch(`${API.base}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${API.token}` },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err.detail, res.statusText));
  }
  return res.json();
}

let _previewOrigUrl = null;
let _previewCompressedUrl = null;

function revokePreviewUrls() {
  if (_previewOrigUrl) {
    URL.revokeObjectURL(_previewOrigUrl);
    _previewOrigUrl = null;
  }
  if (_previewCompressedUrl) {
    URL.revokeObjectURL(_previewCompressedUrl);
    _previewCompressedUrl = null;
  }
}

function blobUrlFromDataUrl(dataUrl) {
  const comma = dataUrl.indexOf(',');
  if (comma < 0) return null;
  const header = dataUrl.slice(0, comma);
  const mime = header.match(/data:([^;]+)/)?.[1] || 'image/jpeg';
  const b64 = dataUrl.slice(comma + 1);
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: mime }));
}

function setPreviewSlot(img, placeholder, src, onBlobUrl) {
  if (!img) return;
  img.classList.remove('hidden');
  if (placeholder) placeholder.classList.add('hidden');
  img.onerror = () => {
    if (src.startsWith('data:') && onBlobUrl) {
      const blobUrl = blobUrlFromDataUrl(src);
      if (blobUrl) {
        onBlobUrl(blobUrl);
        img.onerror = null;
        img.src = blobUrl;
      }
    }
  };
  img.src = src;
}

function resetCompressedPreview() {
  const compressed = document.getElementById('previewImageCompressed');
  const pending = document.getElementById('previewCompressedPlaceholder');
  if (compressed) {
    compressed.classList.add('hidden');
    compressed.removeAttribute('src');
  }
  if (pending) {
    pending.classList.remove('hidden');
    pending.textContent = '正在压缩…';
  }
}

function formatRuntime(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, '0')}`;
}

/** Single 1s tick for session/lifetime runtime; avoids skip when status WS/poll is irregular. */
const RUNTIME_CLOCK = {
  tickTimer: null,
  session: null,
  lifetime: null,
};

const DIAGNOSTICS = {
  pollTimer: null,
  inFlight: false,
  last: null,
};

function stopRuntimeTick() {
  if (RUNTIME_CLOCK.tickTimer) {
    clearInterval(RUNTIME_CLOCK.tickTimer);
    RUNTIME_CLOCK.tickTimer = null;
  }
}

function currentAnchoredSec(anchor) {
  if (!anchor) return 0;
  if (!anchor.running) return anchor.baseSec;
  const elapsed = Math.floor((Date.now() - anchor.anchorMs) / 1000);
  return anchor.baseSec + Math.max(0, elapsed);
}

function paintRuntimeDisplays() {
  const runtimeEl = document.getElementById('statRuntime');
  if (runtimeEl) {
    runtimeEl.textContent = formatRuntime(currentAnchoredSec(RUNTIME_CLOCK.session));
  }
  const lifetimeEl = document.getElementById('statLifetimeRuntime');
  if (lifetimeEl) {
    lifetimeEl.textContent = formatRuntimeLong(currentAnchoredSec(RUNTIME_CLOCK.lifetime));
  }
}

function startRuntimeTick() {
  stopRuntimeTick();
  paintRuntimeDisplays();
  RUNTIME_CLOCK.tickTimer = setInterval(() => {
    if (!RUNTIME_CLOCK.session?.running) {
      stopRuntimeTick();
      return;
    }
    paintRuntimeDisplays();
  }, 1000);
}

/**
 * Anchor runtime to last server snapshot; while running, advance locally every 1s.
 * Re-anchors only on start/stop or when server drifts ahead by >1s (clock correction).
 */
function syncRuntimeClocks(st) {
  const running = !!st.running;
  const serverSessionSec = Math.max(0, Math.floor(st.runtime_sec || 0));
  const serverLifetimeSec = Math.max(0, Math.floor(st.lifetime_runtime_sec || 0));
  const now = Date.now();
  const wasRunning = !!RUNTIME_CLOCK.session?.running;

  if (running) {
    if (!wasRunning) {
      RUNTIME_CLOCK.session = { baseSec: serverSessionSec, anchorMs: now, running: true };
      RUNTIME_CLOCK.lifetime = { baseSec: serverLifetimeSec, anchorMs: now, running: true };
      startRuntimeTick();
      return;
    }
    const localSession = currentAnchoredSec(RUNTIME_CLOCK.session);
    const localLifetime = currentAnchoredSec(RUNTIME_CLOCK.lifetime);
    if (serverSessionSec > localSession + 1) {
      RUNTIME_CLOCK.session = { baseSec: serverSessionSec, anchorMs: now, running: true };
    }
    if (serverLifetimeSec > localLifetime + 1) {
      RUNTIME_CLOCK.lifetime = { baseSec: serverLifetimeSec, anchorMs: now, running: true };
    }
    if (!RUNTIME_CLOCK.tickTimer) startRuntimeTick();
    return;
  }

  stopRuntimeTick();
  RUNTIME_CLOCK.session = { baseSec: serverSessionSec, anchorMs: now, running: false };
  RUNTIME_CLOCK.lifetime = { baseSec: serverLifetimeSec, anchorMs: now, running: false };
  paintRuntimeDisplays();
}

function formatRuntimeLong(sec) {
  const s = Math.floor(sec || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}小时${m}分`;
  if (m > 0) return `${m}:${String(r).padStart(2, '0')}`;
  return `${r}秒`;
}

function formatSessionTimestamp(unixSec) {
  if (!unixSec) return '—';
  const d = new Date(unixSec * 1000);
  const pad = (x) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function formatSessionRunLine(run) {
  const start = formatSessionTimestamp(run.started_at);
  const end = formatSessionTimestamp(run.ended_at);
  const model = run.model || '—';
  const input = run.input_tokens ?? 0;
  const output = run.output_tokens ?? 0;
  const total = run.total_tokens ?? (input + output);
  return `${start} - ${end}  ${model}  输入 ${input}  输出 ${output}  总 ${total}`;
}

function renderSessionRuns(runs) {
  const container = document.getElementById('sessionRunLog');
  const empty = document.getElementById('sessionRunLogEmpty');
  if (!container) return;
  const list = Array.isArray(runs) ? runs : [];
  container.querySelectorAll('.session-run-line').forEach((el) => el.remove());
  if (!list.length) {
    if (empty) empty.classList.remove('hidden');
    return;
  }
  if (empty) empty.classList.add('hidden');
  list.forEach((run) => {
    const line = document.createElement('p');
    line.className = 'session-run-line';
    line.textContent = formatSessionRunLine(run);
    container.appendChild(line);
  });
}

function formatTokenCount(n) {
  const v = Number(n) || 0;
  return v >= 10000 ? v.toLocaleString('zh-CN') : String(v);
}

function applyStatus(st) {
  const running = st.running;
  const dot = document.getElementById('statusDot');
  const pill = document.getElementById('statusPill');
  const sub = document.getElementById('statusSub');
  const btn = document.getElementById('btnToggle');

  if (running) {
    dot.className = 'w-3 h-3 bg-green-400 rounded-full animate-pulse';
    pill.textContent = '生成中';
    sub.textContent = st.live_message || '小助手正在为你生成暖心弹幕~';
    btn.textContent = '停止弹幕';
    btn.classList.remove('btn-primary', 'text-white');
    btn.classList.add('bg-white', 'border', 'border-gray-200', 'text-warmText');
  } else {
    dot.className = 'w-3 h-3 bg-gray-300 rounded-full';
    pill.textContent = '待命';
    sub.textContent = '小助手正在待命，随时为你生成暖心弹幕~';
    btn.textContent = '生成弹幕';
    btn.classList.remove('bg-white', 'border', 'border-gray-200', 'text-warmText');
    btn.classList.add('btn-primary', 'text-white');
  }

  document.getElementById('statDanmu').textContent = String(st.danmu_count ?? 0);
  document.getElementById('statQueue').textContent = String(st.queue_count ?? 0);
  syncRuntimeClocks(st);
  const displayEl = document.getElementById('statDisplay');
  if (displayEl) displayEl.textContent = String(st.display_count ?? 0);
  const lifetimeDanmuEl = document.getElementById('statLifetimeDanmu');
  const lifetimeInputEl = document.getElementById('statLifetimeInputTokens');
  const lifetimeOutputEl = document.getElementById('statLifetimeOutputTokens');
  if (lifetimeDanmuEl) lifetimeDanmuEl.textContent = String(st.lifetime_danmu_count ?? 0);
  if (lifetimeInputEl) {
    lifetimeInputEl.textContent = formatTokenCount(st.lifetime_input_tokens ?? 0);
  }
  if (lifetimeOutputEl) {
    lifetimeOutputEl.textContent = formatTokenCount(st.lifetime_output_tokens ?? 0);
  }
  const lifetimeNoteEl = document.getElementById('statLifetimeTokenNote');
  if (lifetimeNoteEl) {
    const lifetimeTotal = Number(st.lifetime_total_tokens) || 0;
    const lifetimeIn = Number(st.lifetime_input_tokens) || 0;
    const lifetimeOut = Number(st.lifetime_output_tokens) || 0;
    const legacyExtra = lifetimeTotal - lifetimeIn - lifetimeOut;
    if (legacyExtra > 0) {
      lifetimeNoteEl.textContent =
        `另有升级前累计 ${formatTokenCount(legacyExtra)} Token（尚未区分输入/输出，已计入历史合计）`;
      lifetimeNoteEl.classList.remove('hidden');
    } else {
      lifetimeNoteEl.textContent = '';
      lifetimeNoteEl.classList.add('hidden');
    }
  }
  document.getElementById('activePersonae').textContent =
    (st.persona_names && st.persona_names.length) ? st.persona_names.join(' · ') : '—';
  document.getElementById('liveStatusLine').textContent = st.live_message || '';
  renderSessionRuns(st.session_runs);

  const banner = document.getElementById('errorBanner');
  if (st.error_message) {
    banner.textContent = st.error_message;
    banner.classList.remove('hidden');
    banner.classList.toggle('text-red-700', st.is_error);
  } else {
    banner.classList.add('hidden');
  }
}

function formatDiagSeconds(value) {
  const num = Number(value) || 0;
  return `${num.toFixed(2)}s`;
}

function formatDiagMs(value) {
  return `${Math.max(0, Math.round(Number(value) || 0))}ms`;
}

function buildDiagnosticReportText(diag) {
  if (!diag) return '等待诊断数据...';
  const scheduler = diag.scheduler || {};
  const timing = diag.timing || {};
  const runtimeState = diag.runtime_state || {};
  const diagnosis = diag.diagnosis || {};
  const webRuntime = runtimeState.web_runtime || {};
  const stats = runtimeState.stats || {};
  const generation = runtimeState.generation_pipeline || {};
  const suggestions = [];
  if (diagnosis.scheduler_blocked) {
    suggestions.push(`- 检查调度阻塞原因：${scheduler.block_reason || 'unknown'}`);
  }
  if (diagnosis.high_rtt) {
    suggestions.push('- 检查弱网、上游模型响应时间或过慢的视觉请求');
  }
  if (diagnosis.has_pending_timing) {
    suggestions.push('- 检查请求 timing 是否长时间未消费，重点看 reply/error 清理路径');
  }
  if (!suggestions.length) {
    suggestions.push('- 当前快照未发现明显调度或 timing 异常');
  }
  return [
    'DanmuAI Diagnostic Report',
    '',
    '[scheduler]',
    `scheduler_blocked: ${!!diagnosis.scheduler_blocked}`,
    `block_reason: ${scheduler.block_reason || ''}`,
    `seconds_since_last_trigger: ${scheduler.seconds_since_last_trigger ?? 0}`,
    '',
    '[timing]',
    `request_started_count: ${timing.request_started_count ?? 0}`,
    `avg_rtt: ${timing.avg_rtt ?? 0}`,
    `smart_cooldown_ms: ${timing.smart_cooldown_ms ?? 0}`,
    `recent_rtt_samples: ${(timing.recent_rtt_samples || []).join(', ') || '[]'}`,
    '',
    '[runtime]',
    `danmu_count: ${stats.danmu_count ?? 0}`,
    `runtime_sec: ${stats.runtime_sec ?? 0}`,
    `cached_layout_mode: ${webRuntime.cached_layout_mode || 'fullscreen'}`,
    `latest_displayed_round: ${generation.latest_displayed_round ?? 0}`,
    '',
    '[next_steps]',
    ...suggestions,
  ].join('\n');
}

function renderDiagnostics(diag) {
  DIAGNOSTICS.last = diag || null;
  const scheduler = diag?.scheduler || {};
  const timing = diag?.timing || {};
  const diagnosis = diag?.diagnosis || {};
  const stats = diag?.runtime_state?.stats || {};

  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };

  setText('diagSchedulerBlocked', diagnosis.scheduler_blocked ? '是' : '否');
  setText('diagBlockReason', scheduler.block_reason || '-');
  setText('diagTriggerGap', formatDiagSeconds(scheduler.seconds_since_last_trigger));
  setText('diagPendingTiming', String(timing.request_started_count ?? 0));
  setText('diagAvgRtt', formatDiagSeconds(timing.avg_rtt));
  setText('diagCooldown', formatDiagMs(timing.smart_cooldown_ms));
  setText('diagHighRtt', diagnosis.high_rtt ? '是' : '否');
  setText('diagRttHistoryLen', String(timing.rtt_history_len ?? 0));
  setText(
    'diagRecentRttSamples',
    JSON.stringify(timing.recent_rtt_samples || []),
  );
  setText(
    'diagRuntimeStats',
    `danmu=${stats.danmu_count ?? 0} · input=${stats.total_input_tokens ?? 0} · output=${stats.total_output_tokens ?? 0} · runtime=${formatDiagSeconds(stats.runtime_sec)}`,
  );
  setText('diagnosticReportPreview', buildDiagnosticReportText(diag));
}

async function refreshDiagnostics() {
  if (DIAGNOSTICS.inFlight || !API.base) return;
  DIAGNOSTICS.inFlight = true;
  try {
    const payload = await apiFetch('/api/diagnostics', { method: 'GET' });
    if (payload?.ok && payload.diagnostics) {
      renderDiagnostics(payload.diagnostics);
    }
  } catch (err) {
    console.warn('[diagnostics] refresh failed', err);
  } finally {
    DIAGNOSTICS.inFlight = false;
  }
}

function startDiagnosticsPolling() {
  if (DIAGNOSTICS.pollTimer) clearInterval(DIAGNOSTICS.pollTimer);
  refreshDiagnostics();
  DIAGNOSTICS.pollTimer = setInterval(refreshDiagnostics, 2500);
}

function initDiagnosticsPanel() {
  document.getElementById('btnCopyDiagnosticsReport')?.addEventListener('click', async () => {
    const text = buildDiagnosticReportText(DIAGNOSTICS.last);
    try {
      await navigator.clipboard.writeText(text);
      showToast('诊断报告已复制');
    } catch (err) {
      console.warn('[diagnostics] copy failed', err);
      showToast('复制诊断报告失败', true);
    }
  });
}

function updateLogPanelState() {
  const panel = document.querySelector('.log-panel');
  const empty = document.getElementById('logViewEmpty');
  const view = document.getElementById('logView');
  if (!panel || !view) return;
  const visibleCount = view.childElementCount;
  panel.classList.toggle('has-logs', visibleCount > 0);
  if (empty && visibleCount === 0) {
    if (REALTIME.logsOpen) {
      empty.textContent =
        '等待日志… 点击「生成弹幕」后，截图、AI 请求与弹幕事件会在此实时显示。';
    } else if (REALTIME.degradedLogsPolling) {
      empty.textContent =
        '正在通过 HTTP 同步日志… 若长时间仍为空，请确认已点击「生成弹幕」并有截图/AI 活动。';
    } else {
      empty.textContent =
        '日志通道连接中… 若超过数秒仍无内容，请点左侧「温馨控制台」查看顶栏连接状态，或重启 DanmuAI。';
    }
  }
}

function renderLogView() {
  const view = document.getElementById('logView');
  if (!view) return;
  view.innerHTML = '';
  logBuffer
    .filter((x) => logLevelFilters.has(x.level))
    .forEach((item) => {
      const line = document.createElement('div');
      const ts = item.ts ? new Date(item.ts * 1000).toLocaleTimeString() : '';
      line.className = `log-line ${item.level || 'INFO'}`;
      line.textContent = `[${ts}] ${item.message}`;
      view.appendChild(line);
    });
  if (logAutoScroll) view.scrollTop = view.scrollHeight;
  updateLogPanelState();
}

function appendLog(item) {
  const key = logEntryKey(item);
  if (logBuffer.some((x) => logEntryKey(x) === key)) return;
  logBuffer.push(item);
  while (logBuffer.length > 400) logBuffer.shift();
  if (logLevelFilters.has(item.level || 'INFO')) {
    const view = document.getElementById('logView');
    if (!view) return;
    const line = document.createElement('div');
    const ts = item.ts ? new Date(item.ts * 1000).toLocaleTimeString() : '';
    line.className = `log-line ${item.level || 'INFO'}`;
    line.textContent = `[${ts}] ${item.message}`;
    view.appendChild(line);
    while (view.childElementCount > 400) view.removeChild(view.firstChild);
    if (logAutoScroll) view.scrollTop = view.scrollHeight;
    updateLogPanelState();
  }
}

function clampReplyCount(value, fallback = 2) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.max(REPLY_COUNT_MIN, Math.min(REPLY_COUNT_MAX, n));
}

function resolveDanmuMaxCharsPreview(lang = 'zh') {
  const el = document.getElementById('danmu_max_chars');
  const raw = parseInt(el?.value ?? '', 10);
  const fallback = lang === 'en' ? DEFAULT_DANMU_MAX_CHARS_EN : DEFAULT_DANMU_MAX_CHARS_ZH;
  const value = Number.isNaN(raw) || raw <= 0 ? fallback : raw;
  return Math.max(DANMU_MAX_CHARS_MIN, Math.min(value, DANMU_MAX_CHARS_MAX));
}

function clampNormalReplyCount(value, fallback = DEFAULT_NORMAL_REPLY_COUNT) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.max(NORMAL_REPLY_COUNT_MIN, Math.min(NORMAL_REPLY_COUNT_MAX, n));
}

function clampNormalIntervalSec(value, fallback = 5) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.max(1, Math.min(60, n));
}

function buildNormalReplyContractPreviewZh(count, maxChars) {
  const total = clampNormalReplyCount(count, DEFAULT_NORMAL_REPLY_COUNT);
  const limit = maxChars ?? resolveDanmuMaxCharsPreview('zh');
  const examples = Array.from({ length: total }, (_, i) => `弹幕${i + 1}`);
  return (
    '你是直播弹幕评论员。必须且只能返回 JSON 字符串数组，不要解释，不要 Markdown。'
    + `固定返回 ${total} 条弹幕，必须与当前画面或直播氛围相关，避免重复。`
    + `每条不超过 ${limit} 个字，输出格式：`
    + `["${examples.join('", "')}"]。`
  );
}

function updateNormalBatchPreview() {
  const countEl = document.getElementById('normal_reply_count');
  if (!countEl) return;
  const count = clampNormalReplyCount(countEl.value, DEFAULT_NORMAL_REPLY_COUNT);
  countEl.value = String(count);
  const hint = document.getElementById('normalBatchTotalHint');
  if (hint) {
    hint.textContent = `每次固定 ${count} 条 · 保存后会同步到人格工坊的「输出契约」`;
  }
  const maxChars = resolveDanmuMaxCharsPreview('zh');
  const preview = buildNormalReplyContractPreviewZh(count, maxChars);
  const previewEl = document.getElementById('normalBatchContractPreview');
  if (previewEl) previewEl.textContent = preview;
  const contractEl = document.getElementById('personaContract');
  if (contractEl) contractEl.value = preview;
}

let danmuPoolMeta = null;

function poolEffectiveEnabledLocal() {
  const builtin = document.getElementById('poolBuiltinEnabled')?.checked;
  const custom = document.getElementById('poolCustomEnabled')?.checked;
  return Boolean(builtin || custom);
}

function updatePoolMinOnScreenControl() {
  const enabled = danmuPoolMeta?.effective_pool_enabled ?? poolEffectiveEnabledLocal();
  const minEl = document.getElementById('poolMinOnScreen');
  const wrap = document.getElementById('poolMinOnScreenWrap');
  if (minEl) minEl.disabled = !enabled;
  if (wrap) wrap.classList.toggle('is-disabled', !enabled);
  const hint = document.getElementById('poolBothOffHint');
  if (hint) hint.classList.toggle('hidden', Boolean(enabled));
}

function parseCustomDanmuTextarea(value) {
  return String(value || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function renderCustomDanmuPoolList(items) {
  const list = document.getElementById('poolCustomList');
  const countEl = document.getElementById('poolCustomCount');
  if (countEl) countEl.textContent = `共 ${items.length} 条`;
  if (!list) return;
  list.replaceChildren();
  items.forEach((text) => {
    const li = document.createElement('li');
    li.className = 'danmu-pool-custom-item';
    const label = document.createElement('label');
    label.className = 'flex items-start gap-2 text-warmText';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'pool-custom-cb accent-warmPink mt-1';
    const span = document.createElement('span');
    span.textContent = text;
    label.append(cb, span);
    li.append(label);
    list.append(li);
  });
  const selectAll = document.getElementById('poolCustomSelectAll');
  if (selectAll) selectAll.checked = false;
}

async function loadDanmuPoolPage() {
  const [meta, custom] = await Promise.all([
    apiFetch('/api/danmu-pool/meta'),
    apiFetch('/api/danmu-pool/custom'),
  ]);
  danmuPoolMeta = meta;
  const builtinEl = document.getElementById('poolBuiltinEnabled');
  const customEl = document.getElementById('poolCustomEnabled');
  const minEl = document.getElementById('poolMinOnScreen');
  const countHint = document.getElementById('poolBuiltinCountHint');
  if (builtinEl) builtinEl.checked = Boolean(meta.builtin_enabled);
  if (customEl) customEl.checked = Boolean(meta.custom_enabled);
  if (minEl) minEl.value = String(meta.min_on_screen ?? 5);
  if (countHint) countHint.textContent = meta.builtin_count ? `（内置约 ${meta.builtin_count} 条）` : '';
  renderCustomDanmuPoolList(custom.items || []);
  updatePoolMinOnScreenControl();
}

async function saveDanmuPoolSettings() {
  const body = {
    builtin_enabled: Boolean(document.getElementById('poolBuiltinEnabled')?.checked),
    custom_enabled: Boolean(document.getElementById('poolCustomEnabled')?.checked),
    min_on_screen: parseInt(document.getElementById('poolMinOnScreen')?.value, 10) || 0,
  };
  await apiFetch('/api/danmu-pool/settings', {
    method: 'PUT',
    body: JSON.stringify(body),
  });
  danmuPoolMeta = await apiFetch('/api/danmu-pool/meta');
  updatePoolMinOnScreenControl();
  showToast('公式化弹幕库设置已保存~');
}

async function addCustomDanmuPoolItems() {
  const textarea = document.getElementById('poolCustomTextarea');
  const text = textarea?.value || '';
  if (!text.trim()) {
    showToast('请先输入要追加的弹幕句', true);
    return;
  }
  const result = await apiFetch('/api/danmu-pool/custom', {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
  renderCustomDanmuPoolList(result.items || []);
  danmuPoolMeta = await apiFetch('/api/danmu-pool/meta');
  if (textarea) textarea.value = '';
  const skipped = result.skipped || 0;
  if (skipped > 0) {
    showToast(`已追加 ${result.added} 条，跳过 ${skipped} 条`, skipped > 0 && !result.added);
  } else {
    showToast(`已追加 ${result.added} 条~`);
  }
}

async function deleteSelectedCustomDanmuPoolItems() {
  const texts = [...document.querySelectorAll('#poolCustomList .pool-custom-cb:checked')]
    .map((cb) => cb.closest('label')?.querySelector('span')?.textContent)
    .filter(Boolean);
  if (!texts.length) {
    showToast('请先勾选要删除的句子', true);
    return;
  }
  const result = await apiFetch('/api/danmu-pool/custom', {
    method: 'DELETE',
    body: JSON.stringify({ texts }),
  });
  renderCustomDanmuPoolList(result.items || []);
  danmuPoolMeta = await apiFetch('/api/danmu-pool/meta');
  showToast(`已删除 ${result.removed} 条~`);
}

function initDanmuPoolPage() {
  document.getElementById('btnSavePoolSettings')?.addEventListener('click', () => {
    saveDanmuPoolSettings().catch((e) => showToast(e.message, true));
  });
  document.getElementById('btnPoolCustomAppend')?.addEventListener('click', () => {
    addCustomDanmuPoolItems().catch((e) => showToast(e.message, true));
  });
  document.getElementById('btnPoolCustomClearInput')?.addEventListener('click', () => {
    const textarea = document.getElementById('poolCustomTextarea');
    if (textarea) textarea.value = '';
  });
  document.getElementById('btnPoolCustomDelete')?.addEventListener('click', () => {
    deleteSelectedCustomDanmuPoolItems().catch((e) => showToast(e.message, true));
  });
  document.getElementById('poolCustomSelectAll')?.addEventListener('change', (e) => {
    const checked = e.target.checked;
    document.querySelectorAll('#poolCustomList .pool-custom-cb').forEach((cb) => {
      cb.checked = checked;
    });
  });
  ['poolBuiltinEnabled', 'poolCustomEnabled'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', () => {
      if (danmuPoolMeta) {
        danmuPoolMeta.effective_pool_enabled = poolEffectiveEnabledLocal();
      }
      updatePoolMinOnScreenControl();
    });
  });
}

const SETTINGS_UI_MODE_KEY = 'danmu_settings_ui_mode';

function getSettingsUiMode() {
  try {
    const v = localStorage.getItem(SETTINGS_UI_MODE_KEY);
    return v === 'full' ? 'full' : 'simplified';
  } catch {
    return 'simplified';
  }
}

function setSettingsUiMode(mode) {
  const normalized = mode === 'full' ? 'full' : 'simplified';
  try {
    localStorage.setItem(SETTINGS_UI_MODE_KEY, normalized);
  } catch {
    /* ignore quota / private mode */
  }
  applySettingsUiMode();
}

function applySettingsUiMode() {
  const mode = getSettingsUiMode();
  const form = document.getElementById('settingsForm');
  if (form) {
    form.classList.toggle('settings-ui-simplified', mode === 'simplified');
    form.classList.toggle('settings-ui-full', mode === 'full');
  }
  document.querySelectorAll('.settings-ui-mode-btn').forEach((btn) => {
    const active = btn.dataset.settingsUiMode === mode;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}

function initSettingsUiMode() {
  applySettingsUiMode();
  document.querySelectorAll('.settings-ui-mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      setSettingsUiMode(btn.dataset.settingsUiMode);
    });
  });
}

function initNormalBatchControls() {
  ['normal_reply_count', 'normal_recognition_interval_sec', 'danmu_max_chars'].forEach((id) => {
    document.getElementById(id)?.addEventListener('input', updateNormalBatchPreview);
    document.getElementById(id)?.addEventListener('change', updateNormalBatchPreview);
  });
  updateNormalBatchPreview();
}

function collectFormData() {
  syncVisionModelToHidden();
  const data = {};
  CONFIG_FIELDS.forEach((name) => {
    const el = document.getElementById(name);
    if (el) data[name] = el.value;
  });
  data.empty_accel = document.getElementById('empty_accel')?.checked ? '1' : '0';
  data.mic_mode_enabled = document.getElementById('mic_mode_enabled')?.checked ? '1' : '0';
  const key = (document.getElementById('api_key')?.value || '').trim();
  if (key && key !== MASKED_API_KEY) data.api_key = key;
  return data;
}

let micAudioLikelySupported = true;

function catalogModelSupportsMic(modelId) {
  const id = (modelId || '').trim();
  if (!id) return false;
  for (const platform of catalogCache.platforms || []) {
    const hit = (platform.models || []).find((m) => m.id === id);
    if (hit) return Boolean(hit.supports_mic);
  }
  return false;
}

function updateMicModeHint() {
  const hint = document.getElementById('micModeHint');
  const micOn = document.getElementById('mic_mode_enabled')?.checked;
  if (!hint) return;
  if (!micOn) {
    hint.classList.add('hidden');
    hint.textContent = '';
    return;
  }
  const apiMode = document.getElementById('api_mode')?.value || 'doubao';
  const modelId = document.getElementById('model')?.value || '';
  const supported = apiMode === 'doubao'
    && (micAudioLikelySupported || catalogModelSupportsMic(modelId));
  if (supported) {
    hint.classList.add('hidden');
    hint.textContent = '';
    return;
  }
  hint.classList.remove('hidden');
  if (apiMode !== 'doubao') {
    hint.textContent = '麦克风模式需使用火山方舟豆包接口（API 模式选 doubao）。当前为 OpenAI 兼容模式，保存后对着麦克风说话也不会生成接话弹幕。';
    return;
  }
  hint.textContent = `当前模型「${modelId || '未选'}」可能听不懂麦克风。请改选列表里带「支持麦克风」的模型（例如 doubao-seed-2-0-mini），勾选后先点「保存配置」再开始弹幕。使用时对着麦克风说话，句末停顿约半秒；「测试发送」按钮不检测停顿。`;
}

function fillForm(cfg) {
  CONFIG_FIELDS.forEach((name) => {
    const el = document.getElementById(name);
    if (el && cfg[name] !== undefined) el.value = cfg[name];
  });
  const setIfEmpty = (id, fallback) => {
    const el = document.getElementById(id);
    if (el && (cfg[id] === undefined || cfg[id] === '' || cfg[id] === null)) {
      el.value = fallback;
    }
  };
  setIfEmpty('danmu_speed', '2');
  setIfEmpty('danmu_lines', '20');
  setIfEmpty('font_size', '24');
  setIfEmpty('opacity', '100');
  setIfEmpty('dedup_threshold', '0.5');
  setIfEmpty('hotkey', 'Ctrl+Shift+B');
  setIfEmpty('image_max_width', '768');
  setIfEmpty('temperature', '0.7');
  setIfEmpty('max_tokens', '512');
  const imageQuality = document.getElementById('image_quality');
  if (imageQuality && !cfg.image_quality) imageQuality.value = '85';
  const danmuMaxChars = document.getElementById('danmu_max_chars');
  if (danmuMaxChars && !cfg.danmu_max_chars) danmuMaxChars.value = '15';
  const evictionMode = document.getElementById('eviction_mode');
  if (evictionMode && !cfg.eviction_mode) evictionMode.value = 'natural';
  const emptyAccel = document.getElementById('empty_accel');
  if (emptyAccel) emptyAccel.checked = cfg.empty_accel !== '0';
  const memoryMode = document.getElementById('memory_mode');
  if (memoryMode) {
    const allowed = ['off', 'dedup_only', 'scene_card', 'strong'];
    memoryMode.value = allowed.includes(cfg.memory_mode) ? cfg.memory_mode : 'off';
  }
  const memoryWindow = document.getElementById('memory_window');
  if (memoryWindow && !cfg.memory_window) memoryWindow.value = '10';
  micAudioLikelySupported = cfg.mic_audio_likely_supported !== false;
  const micMode = document.getElementById('mic_mode_enabled');
  if (micMode) micMode.checked = cfg.mic_mode_enabled === '1';
  updateMicModeHint();
  const micWindow = document.getElementById('mic_window_sec');
  if (micWindow && !cfg.mic_window_sec) micWindow.value = '5';
  const layoutMode = document.getElementById('layout_mode');
  if (layoutMode) {
    const allowed = ['fullscreen', '3/4', '1/2', '1/4'];
    layoutMode.value = allowed.includes(cfg.layout_mode) ? cfg.layout_mode : 'fullscreen';
  }
  const normalInterval = document.getElementById('normal_recognition_interval_sec');
  if (normalInterval && !cfg.normal_recognition_interval_sec) normalInterval.value = '5';
  const normalCount = document.getElementById('normal_reply_count');
  if (normalCount && !cfg.normal_reply_count) normalCount.value = '5';
  updateNormalBatchPreview();
  const modelId = cfg.active_model_id || cfg.default_model_id || cfg.model || '';
  const modelEl = document.getElementById('model');
  if (modelEl) modelEl.value = modelId;
  syncVisionModelPickerFromForm(modelId);
  document.getElementById('api_key').value = cfg.has_api_key ? MASKED_API_KEY : '';
}

async function reloadConfigFromServer() {
  const cfg = await apiFetch('/api/config');
  fillForm(cfg);
  syncProviderPresetFromEndpoint();
  const modelId = cfg.active_model_id || cfg.default_model_id || cfg.model || '';
  syncVisionModelPickerFromForm(modelId);
  await loadCustomModels();
  return cfg;
}

async function loadScreens() {
  const screens = await fetch(`${API.base}/api/screens`).then((r) => r.json());
  const sel = document.getElementById('screen_index');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '';
  screens.forEach((s) => {
    const opt = document.createElement('option');
    opt.value = String(s.index);
    opt.textContent = s.label;
    sel.appendChild(opt);
  });
  if (current !== '') sel.value = current;
  sel.disabled = screens.length <= 1;
}

async function loadProviders() {
  providersCache = await fetch(`${API.base}/api/providers`).then((r) => r.json());
  const sel = document.getElementById('providerPreset');
  if (!sel) return;
  sel.innerHTML = '<option value="">自定义</option>';
  providersCache.forEach((p) => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.label;
    sel.appendChild(opt);
  });
  const modelProv = document.getElementById('modelProvider');
  if (modelProv) {
    modelProv.innerHTML = '';
    providersCache.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.label;
      modelProv.appendChild(opt);
    });
  }
}

function pickDefaultCatalogModelId(providerId) {
  const platform = resolveCatalogPlatform(providerId);
  if (!platform?.models?.length) return '';
  const cheapest = platform.models.find((m) => m.cheapest);
  return (cheapest || platform.models[0]).id;
}

function syncProviderPresetFromEndpoint() {
  const sel = document.getElementById('providerPreset');
  if (!sel) return;
  const endpoint = document.getElementById('api_endpoint')?.value || '';
  const guessed = guessProviderIdFromEndpoint(endpoint);
  if (!guessed) {
    sel.value = '';
    return;
  }
  const hasOption = Array.from(sel.options).some((opt) => opt.value === guessed);
  sel.value = hasOption ? guessed : '';
}

// 切换服务商预设：填 endpoint/mode、清空 API Key 输入、重置为 catalog 默认视觉模型。
// 仅影响表单；运行中配置以 PUT /api/config 为准，与 Qt Overlay 无关。
function applyProviderPreset(providerId) {
  const p = providersCache.find((x) => x.id === providerId);
  if (!p) return;
  document.getElementById('api_endpoint').value = p.default_endpoint;
  document.getElementById('api_mode').value = p.mode === 'openai-compatible' ? 'openai' : p.mode;
  const apiKeyEl = document.getElementById('api_key');
  if (apiKeyEl) apiKeyEl.value = '';
  const defaultModelId = pickDefaultCatalogModelId(providerId);
  renderVisionModelPicker(providerId, defaultModelId, { providerSwitch: true });
  showToast(`已填入 ${p.label} 的默认地址，请填写对应 API 密钥~`);
}

async function loadModelCatalog() {
  try {
    catalogCache = await fetch(`${API.base}/api/model-catalog`).then((r) => r.json());
  } catch {
    catalogCache = { platforms: [] };
  }
  if (!catalogCache.platforms) catalogCache.platforms = [];
}

function resolveCatalogPlatform(providerId) {
  if (!providerId) return null;
  return catalogCache.platforms.find((p) => p.provider_id === providerId) || null;
}

function guessProviderIdFromEndpoint(endpoint) {
  const value = (endpoint || '').toLowerCase();
  const ordered = [
    ['ark.cn-beijing.volces.com', 'doubao'],
    ['dashscope.aliyuncs.com', 'dashscope'],
    ['open.bigmodel.cn', 'zhipu'],
    ['api.moonshot.cn', 'moonshot'],
    ['api.siliconflow.cn', 'siliconflow'],
    ['api.xiaomimimo.com', 'mimo'],
  ];
  for (const [fragment, id] of ordered) {
    if (value.includes(fragment)) return id;
  }
  const mode = document.getElementById('api_mode')?.value || '';
  if (mode === 'doubao') return 'doubao';
  return '';
}

function formatTokenPrice(value) {
  if (value === null || value === undefined) return '-';
  const num = Number(value);
  if (Number.isNaN(num)) return '-';
  const text = Number.isInteger(num) ? String(num) : String(num);
  return `${text} 元 / M tokens`;
}

function buildModelRowBadges(model) {
  const wrap = document.createElement('span');
  wrap.className = 'vision-model-badges shrink-0';
  const add = (text) => {
    const badge = document.createElement('span');
    badge.className = 'vision-model-badge';
    badge.textContent = text;
    wrap.appendChild(badge);
  };
  if (model.cheapest && model.supports_mic) {
    add('最便宜+麦克风');
    return wrap;
  }
  if (model.cheapest) add('本平台最便宜');
  if (model.supports_mic) add('支持麦克风');
  return wrap.childElementCount ? wrap : null;
}

function buildModelTooltipHtml(model) {
  const price = model.price || {};
  return (
    `<span class="model-tooltip-line">模型名称：${model.name}</span>`
    + `<span class="model-tooltip-line">模型 ID：${model.id}</span>`
    + `<span class="model-tooltip-line">输入价格：${formatTokenPrice(price.input)}</span>`
    + `<span class="model-tooltip-line">音频价格：${formatTokenPrice(price.audio)}</span>`
    + `<span class="model-tooltip-line">输出价格：${formatTokenPrice(price.output)}</span>`
  );
}

let floatingTooltipEl = null;
let floatingTooltipDismissBound = false;

function ensureFloatingTooltip() {
  if (!floatingTooltipEl) {
    floatingTooltipEl = document.createElement('div');
    floatingTooltipEl.id = 'uiTooltipFloat';
    floatingTooltipEl.className = 'ui-tooltip-float';
    floatingTooltipEl.setAttribute('role', 'tooltip');
    document.body.appendChild(floatingTooltipEl);
  }
  return floatingTooltipEl;
}

function bindFloatingTooltipDismiss() {
  if (floatingTooltipDismissBound) return;
  floatingTooltipDismissBound = true;
  const hide = () => hideFloatingTooltip();
  window.addEventListener('scroll', hide, true);
  window.addEventListener('resize', hide);
  document.getElementById('settingsForm')?.addEventListener('scroll', hide, true);
}

function positionFloatingTooltip(anchor) {
  const tip = ensureFloatingTooltip();
  tip.style.visibility = 'hidden';
  tip.style.display = 'block';
  const anchorRect = anchor.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  const margin = 10;
  let top = anchorRect.bottom + margin;
  let left = anchorRect.left + anchorRect.width / 2 - tipRect.width / 2;
  if (top + tipRect.height > window.innerHeight - margin) {
    top = anchorRect.top - tipRect.height - margin;
  }
  left = Math.max(margin, Math.min(left, window.innerWidth - tipRect.width - margin));
  top = Math.max(margin, Math.min(top, window.innerHeight - tipRect.height - margin));
  tip.style.top = `${Math.round(top)}px`;
  tip.style.left = `${Math.round(left)}px`;
  tip.style.visibility = 'visible';
}

function showFloatingTooltip(anchor, content, options = {}) {
  bindFloatingTooltipDismiss();
  const { html = false, wide = false, tipId = '' } = options;
  const tip = ensureFloatingTooltip();
  tip.classList.toggle('ui-tooltip-float--wide', Boolean(wide));
  if (tipId) tip.id = tipId;
  else tip.removeAttribute('id');
  if (html) tip.innerHTML = content;
  else tip.textContent = content;
  positionFloatingTooltip(anchor);
}

function hideFloatingTooltip() {
  if (!floatingTooltipEl) return;
  floatingTooltipEl.style.display = 'none';
  floatingTooltipEl.style.visibility = '';
  floatingTooltipEl.classList.remove('ui-tooltip-float--wide');
}

function wireFloatingTooltipButton(btn, onShow) {
  btn.addEventListener('click', (e) => e.preventDefault());
  btn.addEventListener('mouseenter', onShow);
  btn.addEventListener('mouseleave', hideFloatingTooltip);
  btn.addEventListener('focus', onShow);
  btn.addEventListener('blur', hideFloatingTooltip);
}

function createModelPriceHint(model) {
  const wrap = document.createElement('span');
  wrap.className = 'field-hint-wrap relative shrink-0';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'field-hint-btn';
  btn.setAttribute('aria-label', `查看 ${model.id} 的价格说明`);
  btn.innerHTML = '<svg class="ui-icon" aria-hidden="true"><use href="#i-info"></use></svg>';
  wireFloatingTooltipButton(btn, () => {
    showFloatingTooltip(btn, buildModelTooltipHtml(model), { html: true, wide: true });
  });
  wrap.append(btn);
  return wrap;
}

function appendVisionModelRowMeta(row, model) {
  const badges = buildModelRowBadges(model);
  if (badges) row.appendChild(badges);
  row.appendChild(createModelPriceHint(model));
}

function setVisionModelValue(modelId) {
  const hidden = document.getElementById('model');
  if (hidden) hidden.value = modelId || '';
  updateMicModeHint();
}

function syncVisionModelToHidden() {
  const customWrap = document.getElementById('visionModelCustom');
  const customInput = document.getElementById('modelCustom');
  const checked = document.querySelector('input[name="vision_model_choice"]:checked');
  if (checked?.value === VISION_MODEL_CUSTOM_VALUE) {
    setVisionModelValue(customInput?.value?.trim() || '');
    return;
  }
  if (checked) {
    setVisionModelValue(checked.value);
    return;
  }
  if (customWrap && !customWrap.classList.contains('hidden') && customInput) {
    setVisionModelValue(customInput.value.trim());
  }
}

function showVisionModelCustom(show, initialValue = '') {
  const wrap = document.getElementById('visionModelCustom');
  const input = document.getElementById('modelCustom');
  if (!wrap || !input) return;
  if (show) {
    wrap.classList.remove('hidden');
    if (initialValue !== undefined && initialValue !== null) input.value = initialValue;
    input.oninput = () => setVisionModelValue(input.value.trim());
  } else {
    wrap.classList.add('hidden');
    input.oninput = null;
  }
}

function setVisionModelPickerVisible(visible) {
  const picker = document.getElementById('visionModelPicker');
  if (!picker) return;
  if (visible) picker.classList.remove('hidden');
  else picker.classList.add('hidden');
}

// providerSwitch=true 时强制选平台最便宜模型；否则保留已保存的 model（含「自定义」行）
function renderVisionModelPicker(providerId, selectedModelId, options = {}) {
  const picker = document.getElementById('visionModelPicker');
  if (!picker) return;

  const { providerSwitch = false } = options;
  const platform = resolveCatalogPlatform(providerId);
  if (!platform || !platform.models?.length) {
    picker.innerHTML = '';
    setVisionModelPickerVisible(false);
    const customInitial = providerSwitch ? '' : (selectedModelId || '');
    showVisionModelCustom(true, customInitial);
    setVisionModelValue(customInitial);
    return;
  }

  setVisionModelPickerVisible(true);
  picker.innerHTML = '';
  const knownIds = new Set(platform.models.map((m) => m.id));
  const defaultId = pickDefaultCatalogModelId(providerId);
  let selected;
  let useCustom;
  if (providerSwitch) {
    selected = defaultId || platform.models[0].id;
    useCustom = false;
  } else {
    selected = selectedModelId && knownIds.has(selectedModelId)
      ? selectedModelId
      : (defaultId || platform.models[0].id);
    useCustom = Boolean(selectedModelId && !knownIds.has(selectedModelId));
  }

  platform.models.forEach((model) => {
    const row = document.createElement('label');
    row.className = 'vision-model-row';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'vision_model_choice';
    radio.value = model.id;
    radio.checked = !useCustom && model.id === selected;
    radio.addEventListener('change', () => {
      if (radio.checked) {
        showVisionModelCustom(false);
        setVisionModelValue(model.id);
      }
    });

    const idSpan = document.createElement('span');
    idSpan.className = 'vision-model-id';
    idSpan.textContent = model.id;

    row.append(radio, idSpan);
    appendVisionModelRowMeta(row, model);
    picker.appendChild(row);
  });

  const otherRow = document.createElement('label');
  otherRow.className = 'vision-model-row';
  const otherRadio = document.createElement('input');
  otherRadio.type = 'radio';
  otherRadio.name = 'vision_model_choice';
  otherRadio.value = VISION_MODEL_CUSTOM_VALUE;
  otherRadio.checked = useCustom;
  otherRadio.addEventListener('change', () => {
    const current = document.getElementById('model')?.value || '';
    showVisionModelCustom(true, useCustom ? (selectedModelId || current) : '');
    syncVisionModelToHidden();
  });
  const otherLabel = document.createElement('span');
  otherLabel.className = 'vision-model-id';
  otherLabel.textContent = '自定义模型';
  otherRow.append(otherRadio, otherLabel);
  picker.appendChild(otherRow);

  if (useCustom) {
    showVisionModelCustom(true, selectedModelId);
  } else {
    setVisionModelValue(selected);
  }
}

function syncVisionModelPickerFromForm(selectedModelId) {
  const preset = document.getElementById('providerPreset')?.value;
  const providerId = preset || guessProviderIdFromEndpoint(
    document.getElementById('api_endpoint')?.value || '',
  );
  renderVisionModelPicker(providerId, selectedModelId || '');
}

async function personaFetch(path) {
  if (!API.base) await refreshSession();
  const res = await fetch(`${API.base}${path}`, { cache: 'no-store' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err.detail, res.statusText));
  }
  return res.json();
}

async function deletePersonaByName(name) {
  if (!confirm(`确定删除人格「${name}」吗？`)) return;
  try {
    await apiFetch(`/api/personae/${enc(name)}`, { method: 'DELETE' });
    if (currentPersonaId === name) currentPersonaId = '';
    showToast('已删除~');
    await loadPersonaEditor();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function loadPersonaeCheckboxes(containerId) {
  const data = await personaFetch('/api/personae');
  const box = document.getElementById(containerId);
  if (!box) return data;
  box.innerHTML = '';
  data.items.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'flex items-center gap-2 px-3 py-2 bg-cream rounded-xl text-sm font-semibold text-warmText';
    const label = document.createElement('label');
    label.className = 'flex items-center gap-2 flex-1 min-w-0 cursor-pointer';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = item.id;
    cb.checked = !!item.active;
    cb.className = 'rounded accent-[#FFA5A5] shrink-0';
    const span = document.createElement('span');
    span.className = 'truncate';
    span.textContent = item.label;
    label.append(cb, span);
    row.appendChild(label);
    if (!item.builtin) {
      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'shrink-0 px-2 py-1 border border-red-200 rounded-lg text-xs text-red-600 hover:bg-red-50';
      delBtn.textContent = '删除';
      delBtn.title = `删除人格「${item.label}」`;
      delBtn.addEventListener('click', (e) => {
        e.preventDefault();
        deletePersonaByName(item.id);
      });
      row.appendChild(delBtn);
    }
    box.appendChild(row);
  });
  return data;
}

// 自定义模型 CRUD：掩码 apiKey 在服务端保留；设为默认会同步 global model（ConfigService 双写规则）
async function loadCustomModels() {
  const data = await apiFetch('/api/custom-models');
  const list = document.getElementById('customModelsList');
  if (!list) return;
  list.innerHTML = '';
  if (!data.items.length) {
    list.innerHTML = '<p class="text-sm text-gray-400">暂无自定义模型，点击上方新增~</p>';
    return;
  }
  data.items.forEach((m, index) => {
    const row = document.createElement('div');
    row.className = 'flex flex-wrap items-center gap-2 p-3 bg-cream rounded-xl text-sm';
    const isDefault = m.modelId === data.default_model_id;
    row.innerHTML = `
      <span class="font-semibold text-warmText">${m.name || '未命名'}</span>
      <span class="text-gray-400">${m.modelId}</span>
      ${isDefault ? '<span class="text-green-600 text-xs font-bold">默认</span>' : ''}
      ${m.complete === false ? '<span class="text-amber-600 text-xs font-bold">配置不完整</span>' : ''}
    `;
    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'px-3 py-1 border border-gray-200 rounded-lg text-xs';
    editBtn.textContent = '编辑';
    editBtn.onclick = () => openModelModal(index, m);
    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'px-3 py-1 border border-red-200 rounded-lg text-xs text-red-600';
    delBtn.textContent = '删除';
    delBtn.onclick = async () => {
      if (!confirm(`确定删除模型「${m.name}」吗？`)) return;
      try {
        await apiFetch(`/api/custom-models/${index}`, { method: 'DELETE' });
        showToast('已删除~');
        loadCustomModels();
      } catch (e) {
        showToast(e.message, true);
      }
    };
    row.appendChild(editBtn);
    row.appendChild(delBtn);
    if (!isDefault) {
      const defBtn = document.createElement('button');
      defBtn.type = 'button';
      defBtn.className = 'px-3 py-1 border border-gray-200 rounded-lg text-xs';
      defBtn.textContent = '设为默认';
      defBtn.onclick = async () => {
        const res = await apiFetch(`/api/custom-models/${index}/default`, { method: 'POST' });
        const modelEl = document.getElementById('model');
        if (modelEl && res.default_model_id) {
          modelEl.value = res.default_model_id;
          syncVisionModelPickerFromForm(res.default_model_id);
        }
        showToast(`已设为默认模型：${res.default_model_id || m.modelId}`);
        loadCustomModels();
      };
      row.appendChild(defBtn);
    }
    list.appendChild(row);
  });
}

function openModelModal(index, model = {}) {
  document.getElementById('modelEditIndex').value = String(index);
  document.getElementById('modelModalTitle').textContent = index >= 0 ? '编辑模型' : '新增模型';
  document.getElementById('modelName').value = model.name || '';
  document.getElementById('modelId').value = model.modelId || '';
  document.getElementById('modelMode').value = model.mode || 'doubao';
  document.getElementById('modelEndpoint').value = model.endpoint || '';
  document.getElementById('modelApiKey').value = model.apiKey === '********' ? '********' : (model.apiKey || '');
  document.getElementById('modelDescription').value = model.description || '';
  const modal = document.getElementById('modelModal');
  modal.classList.remove('hidden');
  modal.classList.add('flex');
}

function closeModelModal() {
  const modal = document.getElementById('modelModal');
  modal.classList.add('hidden');
  modal.classList.remove('flex');
}

function openRewardModal() {
  const modal = document.getElementById('rewardModal');
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.classList.add('flex');
}

function closeRewardModal() {
  const modal = document.getElementById('rewardModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.classList.remove('flex');
}

function collectModelForm() {
  return {
    name: document.getElementById('modelName').value,
    modelId: document.getElementById('modelId').value,
    mode: document.getElementById('modelMode').value,
    endpoint: document.getElementById('modelEndpoint').value,
    apiKey: document.getElementById('modelApiKey').value,
    description: document.getElementById('modelDescription').value,
    provider: document.getElementById('modelProvider').value,
  };
}

async function loadPersonaEditor() {
  const data = await personaFetch('/api/personae');
  const sel = document.getElementById('personaSelect');
  sel.innerHTML = '';
  data.items.forEach((item) => {
    const opt = document.createElement('option');
    opt.value = item.id;
    opt.textContent = item.label;
    sel.appendChild(opt);
  });
  if (!currentPersonaId && data.items.length) currentPersonaId = data.items[0].id;
  if (currentPersonaId) sel.value = currentPersonaId;
  await loadPersonaTemplate();
  await loadPersonaeCheckboxes('personaActiveList');
}

async function loadPersonaTemplate() {
  const name = document.getElementById('personaSelect').value;
  if (!name) return;
  currentPersonaId = name;
  const tpl = await personaFetch(`/api/personae/${enc(name)}/template`);
  document.getElementById('personaContract').value = tpl.reply_contract || '';
  document.getElementById('personaSystemCustom').value = tpl.system_custom || '';
  const systemEditable = tpl.system_editable ?? tpl.editable;
  document.getElementById('personaSystemCustom').readOnly = !systemEditable;
  document.getElementById('btnSavePersona').disabled = tpl.can_save === false;
  document.getElementById('btnDeletePersona').style.display = tpl.builtin ? 'none' : '';
}

/** 助手设置表单字段说明（悬停 Label 旁 ⓘ 显示） */
const SETTINGS_FIELD_TIPS = {
  providerPreset:
    '选一个常见 AI 平台，会自动填好接口地址和模式；选「自定义」则需自己逐项设置。',
  api_endpoint:
    '视觉模型服务的网址。火山方舟豆包一般填到 /api/v3；多数 OpenAI 兼容服务填到 /v1。',
  api_mode:
    'doubao：火山方舟豆包。openai：其他兼容 Chat 接口的服务（如部分第三方中转）。麦克风模式需选 doubao。',
  model:
    '实际调用的模型名称或接入点 ID。也可在下方「自定义模型」里保存多套配置。',
  screen_index:
    '截图和弹幕叠在哪块显示器上。编号无效时会自动改用主屏。',
  temperature:
    '创意程度（0–2）。越高弹幕用词越发散，越低越稳定、越像固定话术。',
  max_tokens:
    '单次 AI 回复允许的最长输出。开启「思考」类模型时，程序会自动提高实际下限。',
  memory_mode:
    '关闭：不额外记忆。轻量：只避免重复弹幕。标准：记住画面要点并防重复。强记忆：注入更多上下文，换场景时保留更多内容。',
  memory_window:
    '记住最近几条已成功显示的 AI 弹幕（1–20 条），用来提醒模型别再说同样的话。',
  mic_mode_enabled:
    '实验功能：说完一句话后额外生成几条接话弹幕，插队显示，不影响看屏识图节奏。需豆包接口且模型支持麦克风；默认关，录音仅在内存、不落盘。使用 Windows「设置 → 系统 → 声音 → 输入」里的默认麦克风；换耳机后建议先停弹幕再开或重启应用。',
  mic_window_sec:
    '每次说话时，附带最近多少秒的麦克风录音发给 AI（1–30 秒，默认 5）。',
  btnMicTest:
    '录大约 3 秒，检查麦克风是否有声音。不联网、不上传、不保存文件。',
  btnMicTestSend:
    '录大约 3 秒后，把声音和占位图发给 AI，确认模型能收到你的麦克风输入。',
  api_key:
    '访问 AI 的密钥，保存在本机并加密。留空点「保存配置」不会覆盖已有密钥。',
  normal_recognition_interval_sec:
    '普通模式下，每隔多少秒识图并生成一批弹幕（1–60 秒）。',
  normal_reply_count:
    '普通模式下，每次识图固定生成几条弹幕（1–20 条）。',
  danmu_speed:
    '弹幕横向移动快慢（约 0.5–5）。数字越大滚得越快。',
  danmu_lines:
    '屏幕上最多几行弹幕轨道（12–20 行）。',
  danmu_max_chars:
    '单条弹幕最多显示多少字（5–80），超出会截断并加省略号。未填写时默认中文约 15、英文约 40。',
  font_size:
    '弹幕字号，约 12–72 像素。',
  opacity:
    '弹幕透明度 0–100%，100 为完全不透明。',
  dedup_threshold:
    '和最近弹幕有多像就算重复（0–1）。越高越容易判重复并丢掉，默认约 0.5。',
  layout_mode:
    '弹幕显示区域占整块屏幕的比例（全屏、四分之三、一半、四分之一）。',
  hotkey:
    '全局快捷键，随时开始或停止生成弹幕。首次使用可能需在系统里允许本程序监听键盘。',
  eviction_mode:
    '自然：按正常速度滚出屏幕。加速：换场景或清屏时让旧弹幕更快消失。',
  empty_accel:
    '某行轨道空了时，暂时加快滚动，让新弹幕更快占满空位。',
  image_max_width:
    '发给 AI 前把截图缩到多宽。越小越省流量和费用，越大越清晰。',
  image_quality:
    'JPEG 压缩质量 1–100，默认 85。越高图越清楚、文件越大。',
  btnProbe:
    '用当前填写的地址、模式和密钥试连一次 AI，不开始弹幕，也不改其它设置。',
};

const SETTINGS_HEADING_TIPS = {
  'custom-models':
    '为不同接口地址、模型、密钥保存多套配置，可指定默认；这里的密钥与上方全局密钥分开管理。',
  'compress-preview':
    '上传一张样图，预览当前「最大宽度」和「JPEG 质量」下的压缩效果。图片只在内存里处理，不会保存到硬盘。',
};

function createFieldHintWrap(tipText, tipId) {
  const wrap = document.createElement('span');
  wrap.className = 'field-hint-wrap relative shrink-0';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'field-hint-btn';
  btn.setAttribute('aria-label', '字段说明');
  if (tipId) btn.setAttribute('aria-describedby', tipId);
  btn.innerHTML = '<svg class="ui-icon" aria-hidden="true"><use href="#i-info"></use></svg>';
  wireFloatingTooltipButton(btn, () => {
    showFloatingTooltip(btn, tipText, { tipId });
  });
  wrap.append(btn);
  return wrap;
}

function attachHintToLabel(label, tipText, tipId) {
  if (!label || label.querySelector('.field-hint-wrap')) return;
  const wrap = createFieldHintWrap(tipText, tipId);

  if (label.classList.contains('flex') && label.querySelector('input, select, textarea')) {
    label.appendChild(wrap);
    return;
  }

  const row = document.createElement('div');
  row.className = 'field-label-row flex items-center gap-1';
  const useBlockSpacing =
    label.classList.contains('block') || label.classList.contains('settings-field-label');
  if (useBlockSpacing) {
    row.classList.add('mb-2');
    label.classList.remove('block', 'mb-2');
  }
  if (label.classList.contains('mb-1')) {
    row.classList.add('mb-1');
    label.classList.remove('mb-1');
  }
  label.classList.add('flex-1', 'min-w-0');
  label.parentNode.insertBefore(row, label);
  row.append(label, wrap);
}

function attachHintToHeading(heading, tipText, tipId) {
  if (!heading || heading.querySelector('.field-hint-wrap')) return;
  const row = document.createElement('div');
  row.className = 'field-label-row flex items-center gap-1 mb-4';
  const title = document.createElement('span');
  title.className = `${heading.className} flex-1 min-w-0 mb-0`;
  title.innerHTML = heading.innerHTML;
  heading.replaceWith(row);
  row.append(title, createFieldHintWrap(tipText, tipId));
}

function resolveSettingsLabel(fieldEl) {
  if (!fieldEl) return null;
  const id = fieldEl.id;
  if (id) {
    const byFor = document.querySelector(`#settingsForm label[for="${id}"]`);
    if (byFor) return byFor;
  }
  const inLabel = fieldEl.closest('#settingsForm label');
  if (inLabel) return inLabel;
  const parent = fieldEl.parentElement;
  if (parent) {
    const prev = fieldEl.previousElementSibling;
    if (prev && prev.tagName === 'LABEL') return prev;
    const labelInParent = parent.querySelector(':scope > label');
    if (labelInParent) return labelInParent;
  }
  return null;
}

function initSidebarNavFloatingHints() {
  document.querySelectorAll('.sidebar-nav-hint-wrap').forEach((wrap) => {
    const btn = wrap.querySelector('.sidebar-nav-hint');
    const inlineTip = wrap.querySelector('.warm-tooltip');
    if (!btn || !inlineTip || btn.dataset.floatingTip === '1') return;
    const html = inlineTip.innerHTML;
    const tipId = inlineTip.id || '';
    if (tipId) btn.setAttribute('aria-describedby', tipId);
    inlineTip.remove();
    btn.dataset.floatingTip = '1';
    wireFloatingTooltipButton(btn, () => {
      showFloatingTooltip(btn, html, { html: true, wide: true, tipId });
    });
  });
}

const SETTINGS_CONTROL_HINT_IDS = new Set(['btnMicTest', 'btnMicTestSend', 'btnProbe']);

function attachHintAfterControl(control, tipText, tipId) {
  if (!control || control.dataset.hintAttached === '1') return;
  control.insertAdjacentElement('afterend', createFieldHintWrap(tipText, tipId));
  control.dataset.hintAttached = '1';
}

function initSettingsFieldHints() {
  const form = document.getElementById('settingsForm');
  if (!form) return;

  Object.entries(SETTINGS_FIELD_TIPS).forEach(([fieldId, tip]) => {
    const field = document.getElementById(fieldId);
    if (!field) return;
    if (SETTINGS_CONTROL_HINT_IDS.has(fieldId)) {
      attachHintAfterControl(field, tip, `tip-field-${fieldId}`);
      return;
    }
    const label = resolveSettingsLabel(field);
    if (label) attachHintToLabel(label, tip, `tip-field-${fieldId}`);
  });

  attachHintToHeading(
    document.querySelector('#customModelsSection h4'),
    SETTINGS_HEADING_TIPS['custom-models'],
    'tip-heading-custom-models',
  );
  const compressTitle = document.querySelector('#compressPreviewSection > .settings-section-title');
  if (compressTitle) {
    attachHintToHeading(
      compressTitle,
      SETTINGS_HEADING_TIPS['compress-preview'],
      'tip-heading-compress-preview',
    );
  }
}

function switchSettingsTab(tabId) {
  document.querySelectorAll('.settings-tab').forEach((tab) => {
    const active = tab.dataset.settingsTab === tabId;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  document.querySelectorAll('.settings-tab-panel').forEach((panel) => {
    const active = panel.dataset.settingsPanel === tabId;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  });
}

function initSettingsTabs() {
  document.querySelectorAll('.settings-tab').forEach((tab) => {
    tab.addEventListener('click', () => switchSettingsTab(tab.dataset.settingsTab));
  });
}

function navigate(page) {
  document.querySelectorAll('.page-panel').forEach((p) => p.classList.remove('active'));
  document.querySelectorAll('#nav .sidebar-item').forEach((n) => n.classList.remove('active'));
  const panel = document.getElementById(`page-${page}`);
  if (panel) panel.classList.add('active');
  const btn = document.querySelector(`#nav [data-page="${page}"]`);
  if (btn) btn.classList.add('active');
  if (page === 'settings') {
    loadScreens().catch(console.error);
    loadCustomModels().catch(console.error);
  }
  if (page === 'persona') loadPersonaEditor().catch(console.error);
  if (page === 'danmu-pool') loadDanmuPoolPage().catch((e) => showToast(e.message, true));
  if (page === 'logs') {
    renderLogView();
    updateLogPanelState();
    bootstrapLogsFromServer(REALTIME.lastLogsPollTs).catch((e) => {
      console.warn('[realtime] logs bootstrap on navigate failed', e);
    });
  }
}

/** @typedef {'connecting'|'connected'|'reconnecting'|'polling'|'failed'} RealtimeConnMode */

const REALTIME = {
  statusWs: null,
  logsWs: null,
  statusReconnectTimer: null,
  logsReconnectTimer: null,
  pollingTimer: null,
  pollingGraceTimer: null,
  logsPollingTimer: null,
  logsPollingGraceTimer: null,
  statusAttempt: 0,
  logsAttempt: 0,
  statusOpen: false,
  logsOpen: false,
  degradedPolling: false,
  degradedLogsPolling: false,
  statusWsDownAt: 0,
  logsWsDownAt: 0,
  lastLogsPollTs: 0,
  baseBackoffMs: 1000,
  maxBackoffMs: 16000,
  pollIntervalMs: 1500,
  wsGraceMs: 2500,
  logsWsGraceMs: 800,
};

function wsUrl(path) {
  // 与当前页面同源优先，避免 session 与地址栏 host 不一致时 WS 连错主机。
  const pageOrigin = `${location.protocol}//${location.host}`;
  const base = API.base && new URL(API.base).host === location.host ? API.base : pageOrigin;
  const parsed = new URL(base);
  const proto = parsed.protocol === 'https:' ? 'wss' : 'ws';
  const url = new URL(`${proto}://${parsed.host}${path}`);
  if (API.token) {
    url.searchParams.set('ws_token', API.token);
  }
  return url.toString();
}

/** @param {RealtimeConnMode} mode */
function setRealtimeConnUI(mode) {
  const labels = {
    connecting: '连接中',
    connected: '已连接',
    reconnecting: '重连中',
    polling: '已降级轮询',
    failed: '连接失败',
  };
  const text = labels[mode] || labels.connecting;
  document.querySelectorAll('[data-realtime-conn]').forEach((el) => {
    el.textContent = text;
    el.className = `text-xs font-normal border-l border-gray-200 pl-2 ml-0.5 conn-${mode}`;
    el.setAttribute('data-conn', mode);
  });
}

function setLogsConnUI(mode) {
  const labels = {
    connecting: '连接中',
    connected: '实时',
    reconnecting: '重连中',
    polling: 'HTTP 同步',
    failed: '连接失败',
  };
  const el = document.querySelector('#page-logs [data-realtime-conn]');
  if (!el) return;
  const text = labels[mode] || labels.connecting;
  el.textContent = text;
  el.className = `text-xs font-normal border-l border-gray-200 pl-2 conn-${mode}`;
  el.setAttribute('data-conn', mode);
}

function statusBackoffMs() {
  const exp = Math.min(REALTIME.statusAttempt, 5);
  return Math.min(REALTIME.baseBackoffMs * 2 ** exp, REALTIME.maxBackoffMs);
}

function logsBackoffMs() {
  const exp = Math.min(REALTIME.logsAttempt, 5);
  return Math.min(REALTIME.baseBackoffMs * 2 ** exp, REALTIME.maxBackoffMs);
}

function clearStatusReconnect() {
  if (REALTIME.statusReconnectTimer) {
    clearTimeout(REALTIME.statusReconnectTimer);
    REALTIME.statusReconnectTimer = null;
  }
}

function clearLogsReconnect() {
  if (REALTIME.logsReconnectTimer) {
    clearTimeout(REALTIME.logsReconnectTimer);
    REALTIME.logsReconnectTimer = null;
  }
}

function updateRealtimeConnUI() {
  updateLogPanelState();
  if (REALTIME.logsOpen) {
    setLogsConnUI('connected');
  } else if (REALTIME.degradedLogsPolling) {
    setLogsConnUI('polling');
  } else if (
    REALTIME.logsReconnectTimer
    || (REALTIME.logsWs && REALTIME.logsWs.readyState === WebSocket.CONNECTING)
  ) {
    setLogsConnUI('reconnecting');
  } else if (REALTIME.logsAttempt >= 6) {
    setLogsConnUI('failed');
  } else {
    setLogsConnUI('connecting');
  }

  if (REALTIME.statusOpen && (REALTIME.logsOpen || REALTIME.degradedLogsPolling)) {
    setRealtimeConnUI('connected');
    return;
  }
  if (REALTIME.degradedPolling) {
    setRealtimeConnUI('polling');
    return;
  }
  if (
    REALTIME.statusReconnectTimer
    || REALTIME.logsReconnectTimer
    || (REALTIME.statusWs && REALTIME.statusWs.readyState === WebSocket.CONNECTING)
    || (REALTIME.logsWs && REALTIME.logsWs.readyState === WebSocket.CONNECTING)
  ) {
    setRealtimeConnUI('reconnecting');
    return;
  }
  if (!REALTIME.statusOpen && REALTIME.statusAttempt >= 6) {
    setRealtimeConnUI('failed');
    return;
  }
  setRealtimeConnUI('connecting');
}

function detachWebSocket(ws) {
  if (!ws) return;
  ws.onopen = null;
  ws.onclose = null;
  ws.onerror = null;
  ws.onmessage = null;
  if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
    try {
      ws.close();
    } catch (_) {
      /* ignore */
    }
  }
}

async function pollStatusOnce() {
  const res = await fetch(`${API.base}/api/status`);
  if (!res.ok) throw new Error(res.statusText);
  applyStatus(await res.json());
}

function startStatusPolling() {
  if (REALTIME.pollingTimer) return;
  REALTIME.degradedPolling = true;
  updateRealtimeConnUI();
  const tick = () => {
    pollStatusOnce()
      .then(() => {
        if (REALTIME.statusOpen) stopStatusPolling();
      })
      .catch((e) => console.warn('[realtime] status poll failed', e));
  };
  tick();
  REALTIME.pollingTimer = setInterval(tick, REALTIME.pollIntervalMs);
}

function stopStatusPolling() {
  if (REALTIME.pollingTimer) {
    clearInterval(REALTIME.pollingTimer);
    REALTIME.pollingTimer = null;
  }
  if (REALTIME.pollingGraceTimer) {
    clearTimeout(REALTIME.pollingGraceTimer);
    REALTIME.pollingGraceTimer = null;
  }
  REALTIME.degradedPolling = false;
}

function schedulePollingGraceCheck() {
  if (REALTIME.statusOpen || REALTIME.pollingTimer) return;
  if (!REALTIME.statusWsDownAt) REALTIME.statusWsDownAt = Date.now();
  const elapsed = Date.now() - REALTIME.statusWsDownAt;
  const wait = Math.max(0, REALTIME.wsGraceMs - elapsed);
  if (REALTIME.pollingGraceTimer) clearTimeout(REALTIME.pollingGraceTimer);
  REALTIME.pollingGraceTimer = setTimeout(() => {
    REALTIME.pollingGraceTimer = null;
    if (!REALTIME.statusOpen) startStatusPolling();
    updateRealtimeConnUI();
  }, wait);
}

async function pollLogsOnce() {
  const res = await fetch(
    `${API.base}/api/logs/recent?since_ts=${encodeURIComponent(REALTIME.lastLogsPollTs)}`,
    { cache: 'no-store' },
  );
  if (!res.ok) throw new Error(res.statusText);
  const data = await res.json();
  mergeLogItems(data.items || []);
}

/** Pull ring buffer from server (works when WS is down or page opened after events). */
async function bootstrapLogsFromServer(sinceTs = 0) {
  const base = API.base || window.location.origin.replace(/\/$/, '');
  const res = await fetch(
    `${base}/api/logs/recent?since_ts=${encodeURIComponent(sinceTs)}`,
    { cache: 'no-store' },
  );
  if (!res.ok) throw new Error(res.statusText);
  const data = await res.json();
  mergeLogItems(data.items || []);
  const onLogsPage = document.getElementById('page-logs')?.classList.contains('active');
  if (onLogsPage) renderLogView();
  else updateLogPanelState();
}

function mergeLogItems(items) {
  if (!items.length) return;
  items.forEach((item) => {
    appendLog(item);
    if (item.ts > REALTIME.lastLogsPollTs) REALTIME.lastLogsPollTs = item.ts;
  });
}

function startLogsPolling() {
  if (REALTIME.logsPollingTimer || REALTIME.logsOpen) return;
  REALTIME.degradedLogsPolling = true;
  updateRealtimeConnUI();
  const tick = () => {
    pollLogsOnce()
      .then(() => {
        if (REALTIME.logsOpen) stopLogsPolling();
      })
      .catch((e) => console.warn('[realtime] logs poll failed', e));
  };
  tick();
  REALTIME.logsPollingTimer = setInterval(tick, REALTIME.pollIntervalMs);
}

function stopLogsPolling() {
  if (REALTIME.logsPollingTimer) {
    clearInterval(REALTIME.logsPollingTimer);
    REALTIME.logsPollingTimer = null;
  }
  if (REALTIME.logsPollingGraceTimer) {
    clearTimeout(REALTIME.logsPollingGraceTimer);
    REALTIME.logsPollingGraceTimer = null;
  }
  REALTIME.degradedLogsPolling = false;
}

function scheduleLogsPollingGraceCheck() {
  if (REALTIME.logsOpen || REALTIME.logsPollingTimer) return;
  if (!REALTIME.logsWsDownAt) REALTIME.logsWsDownAt = Date.now();
  const elapsed = Date.now() - REALTIME.logsWsDownAt;
  const wait = Math.max(0, REALTIME.logsWsGraceMs - elapsed);
  if (REALTIME.logsPollingGraceTimer) clearTimeout(REALTIME.logsPollingGraceTimer);
  REALTIME.logsPollingGraceTimer = setTimeout(() => {
    REALTIME.logsPollingGraceTimer = null;
    if (!REALTIME.logsOpen) startLogsPolling();
    updateRealtimeConnUI();
  }, wait);
}

function scheduleStatusReconnect() {
  clearStatusReconnect();
  REALTIME.statusAttempt += 1;
  const delay = statusBackoffMs();
  console.debug(
    `[realtime] status WS reconnect in ${delay}ms (attempt ${REALTIME.statusAttempt})`,
  );
  REALTIME.statusReconnectTimer = setTimeout(() => {
    REALTIME.statusReconnectTimer = null;
    connectStatusWebSocket();
  }, delay);
  schedulePollingGraceCheck();
  updateRealtimeConnUI();
}

function scheduleLogsReconnect() {
  clearLogsReconnect();
  REALTIME.logsAttempt += 1;
  const delay = logsBackoffMs();
  console.debug(
    `[realtime] logs WS reconnect in ${delay}ms (attempt ${REALTIME.logsAttempt})`,
  );
  REALTIME.logsReconnectTimer = setTimeout(() => {
    REALTIME.logsReconnectTimer = null;
    connectLogsWebSocket();
  }, delay);
  scheduleLogsPollingGraceCheck();
  updateRealtimeConnUI();
}

// /ws/status 只驱动控制台统计与运行态 UI，不控制 Overlay 弹幕渲染
function connectStatusWebSocket() {
  clearStatusReconnect();
  detachWebSocket(REALTIME.statusWs);
  const url = wsUrl('/ws/status');
  console.debug('[realtime] status WS connecting', url);
  updateRealtimeConnUI();
  const ws = new WebSocket(url);
  REALTIME.statusWs = ws;

  ws.onopen = () => {
    console.debug('[realtime] status WS open');
    REALTIME.statusAttempt = 0;
    REALTIME.statusOpen = true;
    REALTIME.statusWsDownAt = 0;
    stopStatusPolling();
    updateRealtimeConnUI();
  };

  ws.onmessage = (ev) => {
    try {
      applyStatus(JSON.parse(ev.data));
    } catch (e) {
      console.error('[realtime] status message parse error', e);
    }
  };

  ws.onerror = () => {
    console.warn('[realtime] status WS error');
    if (REALTIME.statusAttempt >= 3) {
      console.warn(
        '[realtime] 无法连接后端 WebSocket。请确认已运行 python main.py，'
        + '终端有「Web 控制台 HTTP/WS 已监听」，且已安装 uvicorn[standard]（含 websockets）。'
        + ' 可刷新页面或重启 DanmuAI。',
      );
    }
  };

  ws.onclose = (ev) => {
    console.debug('[realtime] status WS close', ev.code, ev.reason || '');
    REALTIME.statusOpen = false;
    if (!REALTIME.statusWsDownAt) REALTIME.statusWsDownAt = Date.now();
    scheduleStatusReconnect();
  };
}

function connectLogsWebSocket() {
  clearLogsReconnect();
  detachWebSocket(REALTIME.logsWs);
  const url = wsUrl('/ws/logs');
  console.debug('[realtime] logs WS connecting', url);
  const ws = new WebSocket(url);
  REALTIME.logsWs = ws;

  ws.onopen = () => {
    console.debug('[realtime] logs WS open');
    REALTIME.logsAttempt = 0;
    REALTIME.logsOpen = true;
    REALTIME.logsWsDownAt = 0;
    stopLogsPolling();
    bootstrapLogsFromServer(REALTIME.lastLogsPollTs).catch((e) => {
      console.warn('[realtime] logs bootstrap after WS open failed', e);
    });
    updateRealtimeConnUI();
  };

  ws.onmessage = (ev) => {
    try {
      appendLog(JSON.parse(ev.data));
    } catch (e) {
      console.error('[realtime] log message parse error', e);
    }
  };

  ws.onerror = () => {
    console.warn('[realtime] logs WS error');
    if (REALTIME.logsAttempt >= 3) {
      console.warn(
        '[realtime] 日志 WebSocket 未连接；约 1s 内会改用 HTTP 轮询同步日志。',
      );
    }
    if (!REALTIME.logsWsDownAt) REALTIME.logsWsDownAt = Date.now();
    scheduleLogsPollingGraceCheck();
  };

  ws.onclose = (ev) => {
    console.debug('[realtime] logs WS close', ev.code, ev.reason || '');
    REALTIME.logsOpen = false;
    if (!REALTIME.logsWsDownAt) REALTIME.logsWsDownAt = Date.now();
    scheduleLogsReconnect();
    updateRealtimeConnUI();
  };
}

function startRealtimeTransport() {
  setRealtimeConnUI('connecting');
  setLogsConnUI('connecting');
  REALTIME.logsWsDownAt = Date.now();
  scheduleLogsPollingGraceCheck();
  bootstrapLogsFromServer(0).catch((e) => {
    console.warn('[realtime] initial logs bootstrap failed', e);
  });
  connectStatusWebSocket();
  connectLogsWebSocket();
}

async function init() {
  await refreshSession();

  await loadModelCatalog();
  await loadProviders();
  const cfg = await reloadConfigFromServer();
  await loadScreens();
  if (cfg.screen_index !== undefined) {
    document.getElementById('screen_index').value = String(cfg.screen_index);
  }
  applyStatus(await fetch(`${API.base}/api/status`).then((r) => r.json()));
  initDiagnosticsPanel();
  startDiagnosticsPolling();
  startRealtimeTransport();

  initSettingsTabs();
  initSettingsUiMode();
  initSettingsFieldHints();
  initSidebarNavFloatingHints();
  initNormalBatchControls();
  initDanmuPoolPage();

  document.querySelectorAll('.sidebar-nav-hint').forEach((btn) => {
    btn.addEventListener('click', (e) => e.stopPropagation());
  });

  document.querySelectorAll('#nav [data-page]').forEach((btn) => {
    btn.addEventListener('click', () => navigate(btn.dataset.page));
  });
  const hash = (location.hash || '').replace('#', '');
  if (hash) navigate(hash);

  document.getElementById('providerPreset')?.addEventListener('change', (e) => {
    if (e.target.value) applyProviderPreset(e.target.value);
    else syncVisionModelPickerFromForm(document.getElementById('model')?.value || '');
  });

  document.getElementById('api_endpoint')?.addEventListener('change', () => {
    if (!document.getElementById('providerPreset')?.value) {
      syncVisionModelPickerFromForm(document.getElementById('model')?.value || '');
    }
  });

  document.querySelectorAll('.log-level-cb').forEach((cb) => {
    cb.addEventListener('change', () => {
      logLevelFilters = new Set(
        [...document.querySelectorAll('.log-level-cb:checked')].map((c) => c.value),
      );
      renderLogView();
    });
  });
  document.getElementById('logAutoScroll')?.addEventListener('change', (e) => {
    logAutoScroll = e.target.checked;
  });
  document.getElementById('btnCopyLogs')?.addEventListener('click', () => {
    const text = logBuffer
      .filter((x) => logLevelFilters.has(x.level))
      .map((x) => `[${x.level}] ${x.message}`)
      .join('\n');
    navigator.clipboard.writeText(text).then(() => showToast('已复制到剪贴板~'));
  });
  document.getElementById('btnClearLogs')?.addEventListener('click', () => {
    logBuffer.length = 0;
    document.getElementById('logView').innerHTML = '';
    updateLogPanelState();
    showToast('日志视图已清空~');
  });

  updateLogPanelState();

  document.getElementById('btnToggle').addEventListener('click', async () => {
    try {
      const st = await fetch(`${API.base}/api/status`).then((r) => r.json());
      if (st.running) {
        await apiFetch('/api/stop', { method: 'POST' });
        showToast('小助手已休息~');
      } else {
        await apiFetch('/api/start', { method: 'POST' });
        showToast('弹幕生成已开启！');
      }
    } catch (e) {
      showToast(e.message || '小助手遇到了一点问题', true);
    }
  });

  document.getElementById('mic_mode_enabled')?.addEventListener('change', updateMicModeHint);
  document.getElementById('api_mode')?.addEventListener('change', updateMicModeHint);

  // POST /api/config → bridge.save_config → 主线程 ConfigService（勿期望 HTTP 线程直接改 engine）
  document.getElementById('settingsForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await apiFetch('/api/config', { method: 'POST', body: JSON.stringify({ data: collectFormData() }) });
      const cfg = await reloadConfigFromServer();
      const active = cfg.active_model_id || cfg.model || '';
      showToast(active ? `配置已保存，当前生效模型：${active}` : '配置已保存~');
      if (document.getElementById('personaSelect')?.value) {
        loadPersonaTemplate().catch(console.error);
      }
      const keyInput = document.getElementById('api_key');
      if (keyInput?.value && keyInput.value !== MASKED_API_KEY) {
        keyInput.value = MASKED_API_KEY;
      }
    } catch (err) {
      showToast(err.message || '保存时出了点小状况', true);
    }
  });

  document.getElementById('btnSaveAndStart').addEventListener('click', async () => {
    try {
      await apiFetch('/api/config', { method: 'POST', body: JSON.stringify({ data: collectFormData() }) });
      await apiFetch('/api/start', { method: 'POST' });
      showToast('已保存并开始生成弹幕！');
      navigate('overview');
    } catch (err) {
      showToast(err.message, true);
    }
  });

  document.getElementById('btnProbe').addEventListener('click', async () => {
    const data = collectFormData();
    const keyField = (document.getElementById('api_key')?.value || '').trim();
    try {
      const res = await apiFetch('/api/probe', {
        method: 'POST',
        body: JSON.stringify({
          api_endpoint: data.api_endpoint,
          api_key: keyField === MASKED_API_KEY ? MASKED_API_KEY : (data.api_key || ''),
          model: data.model,
          api_mode: data.api_mode,
        }),
      });
      showToast(res.message || (res.ok ? '连接成功' : '连接失败'), !res.ok);
    } catch (err) {
      showToast(err.message || '网络连接似乎睡着了', true);
    }
  });

  document.getElementById('btnMicTest')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnMicTest');
    const sendBtn = document.getElementById('btnMicTestSend');
    const statusEl = document.getElementById('micTestStatus');
    if (!btn) return;
    btn.disabled = true;
    if (sendBtn) sendBtn.disabled = true;
    if (statusEl) statusEl.textContent = '录音中…请对着麦克风随便念几句话';
    showToast('请对着麦克风随便念几句话（约 3 秒）');
    try {
      const res = await apiFetch('/api/mic/test', {
        method: 'POST',
        body: JSON.stringify({ duration_sec: 3 }),
      });
      const detail = `pcm=${res.pcm_bytes || 0}B · rms=${res.rms ?? 0} · ${res.level || 'unknown'}`;
      if (statusEl) {
        statusEl.textContent = res.default_input
          ? `${res.default_input} · ${detail}`
          : detail;
      }
      showToast(res.message || (res.ok ? '麦克风测试通过' : '麦克风测试未通过'), !res.ok);
    } catch (err) {
      if (statusEl) statusEl.textContent = '测试失败';
      showToast(err.message || '麦克风测试失败', true);
    } finally {
      btn.disabled = false;
      if (sendBtn) sendBtn.disabled = false;
    }
  });

  document.getElementById('btnMicTestSend')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnMicTestSend');
    const micBtn = document.getElementById('btnMicTest');
    const statusEl = document.getElementById('micTestStatus');
    if (!btn) return;
    btn.disabled = true;
    if (micBtn) micBtn.disabled = true;
    if (statusEl) statusEl.textContent = '录音并发送中…请对着麦克风念几句话';
    showToast('录音约 3 秒后将发送到 AI，请对着麦克风说话');
    try {
      const res = await apiFetch('/api/mic/test', {
        method: 'POST',
        body: JSON.stringify({ duration_sec: 3, send_to_ai: true }),
      });
      const detail = `input=${res.input_tokens ?? 0} · output=${res.output_tokens ?? 0} · pcm=${res.pcm_bytes || 0}B`;
      if (statusEl) {
        statusEl.textContent = res.reply_preview
          ? `${detail} · ${res.reply_preview}`
          : detail;
      }
      showToast(res.message || (res.ok ? '测试发送成功' : '测试发送失败'), !res.ok);
    } catch (err) {
      if (statusEl) statusEl.textContent = '测试发送失败';
      showToast(err.message || '测试发送失败', true);
    } finally {
      btn.disabled = false;
      if (micBtn) micBtn.disabled = false;
    }
  });

  document.getElementById('toggleKey').addEventListener('click', () => {
    const inp = document.getElementById('api_key');
    inp.type = inp.type === 'password' ? 'text' : 'password';
  });

  document.getElementById('previewImageFile')?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    const info = document.getElementById('previewImageInfo');
    const origImg = document.getElementById('previewImageOrig');
    const origPh = document.getElementById('previewOrigPlaceholder');
    const compressedImg = document.getElementById('previewImageCompressed');
    const compressedPh = document.getElementById('previewCompressedPlaceholder');
    if (!file || !info || !origImg) return;

    revokePreviewUrls();
    resetCompressedPreview();
    _previewOrigUrl = URL.createObjectURL(file);
    setPreviewSlot(origImg, origPh, _previewOrigUrl);
    info.textContent = `已选择 ${file.name}，正在压缩预览…`;

    const fd = new FormData();
    fd.append('file', file);
    fd.append('max_width', document.getElementById('image_max_width')?.value || '768');
    fd.append('quality', document.getElementById('image_quality')?.value || '85');
    try {
      if (!API.token) {
        throw new Error('未获取会话令牌，请刷新页面或重启 DanmuAI');
      }
      const data = await apiFormFetch('/api/preview/compress', fd);
      info.textContent =
        `原图 ${data.orig_w}×${data.orig_h} → ${data.out_w}×${data.out_h}，JPEG ${(data.jpeg_bytes / 1024).toFixed(1)} KB（Base64 ${data.base64_kb?.toFixed?.(1) ?? '?'} KB）`;
      setPreviewSlot(compressedImg, compressedPh, data.preview_data_url, (blobUrl) => {
        if (_previewCompressedUrl) URL.revokeObjectURL(_previewCompressedUrl);
        _previewCompressedUrl = blobUrl;
      });
    } catch (err) {
      const msg = err.message || '压缩预览失败';
      info.textContent = `${msg}（左侧为原图；请重启 DanmuAI 后重试）`;
      if (compressedPh) {
        compressedPh.classList.remove('hidden');
        compressedPh.textContent = '压缩失败';
      }
      if (compressedImg) compressedImg.classList.add('hidden');
      showToast(msg, true);
    }
  });

  document.getElementById('btnAddCustomModel')?.addEventListener('click', () => openModelModal(-1));
  document.getElementById('btnModelCancel')?.addEventListener('click', closeModelModal);
  document.getElementById('btnFeedbackReward')?.addEventListener('click', openRewardModal);
  document.getElementById('btnRewardClose')?.addEventListener('click', closeRewardModal);
  document.getElementById('rewardModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'rewardModal') closeRewardModal();
  });
  document.getElementById('modelModalForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const index = parseInt(document.getElementById('modelEditIndex').value, 10);
    const body = collectModelForm();
    try {
      if (index >= 0) {
        await apiFetch(`/api/custom-models/${index}`, { method: 'PUT', body: JSON.stringify(body) });
      } else {
        await apiFetch('/api/custom-models', { method: 'POST', body: JSON.stringify(body) });
      }
      closeModelModal();
      showToast('模型已保存~');
      loadCustomModels();
    } catch (err) {
      showToast(err.message, true);
    }
  });
  document.getElementById('btnModelProbe')?.addEventListener('click', async () => {
    try {
      const res = await apiFetch('/api/custom-models/probe', {
        method: 'POST',
        body: JSON.stringify(collectModelForm()),
      });
      showToast(res.message, !res.ok);
    } catch (err) {
      showToast(err.message, true);
    }
  });

  document.getElementById('personaSelect')?.addEventListener('change', () => loadPersonaTemplate());
  document.getElementById('btnSavePersona')?.addEventListener('click', async () => {
    const name = document.getElementById('personaSelect').value;
    try {
      await apiFetch(`/api/personae/${enc(name)}/template`, {
        method: 'PUT',
        body: JSON.stringify({
          system_custom: document.getElementById('personaSystemCustom').value,
        }),
      });
      showToast('人格已保存~');
      loadPersonaTemplate();
    } catch (err) {
      showToast(err.message, true);
    }
  });
  document.getElementById('btnRestorePersona')?.addEventListener('click', async () => {
    const name = document.getElementById('personaSelect').value;
    try {
      const data = await apiFetch(`/api/personae/${enc(name)}/restore`, { method: 'POST' });
      document.getElementById('personaSystemCustom').value = data.system_custom || '';
      showToast('已恢复默认~');
    } catch (err) {
      showToast(err.message, true);
    }
  });
  document.getElementById('btnNewPersona')?.addEventListener('click', async () => {
    const name = prompt('新人格名称：');
    if (!name?.trim()) return;
    try {
      await apiFetch('/api/personae', { method: 'POST', body: JSON.stringify({ name: name.trim() }) });
      currentPersonaId = name.trim();
      showToast('新人格已创建~');
      loadPersonaEditor();
    } catch (err) {
      showToast(err.message, true);
    }
  });
  document.getElementById('btnDeletePersona')?.addEventListener('click', async () => {
    const name = document.getElementById('personaSelect').value;
    if (name) await deletePersonaByName(name);
  });
  document.getElementById('btnSavePersonaActive')?.addEventListener('click', async () => {
    const active = [];
    document.querySelectorAll('#personaActiveList input:checked').forEach((cb) => active.push(cb.value));
    try {
      await apiFetch('/api/personae/active', { method: 'PUT', body: JSON.stringify({ active }) });
      showToast('激活人格已更新~');
    } catch (err) {
      showToast(err.message, true);
    }
  });

}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible' || !API.base) return;
  refreshSession()
    .then(() => {
      REALTIME.statusAttempt = 0;
      REALTIME.logsAttempt = 0;
      startRealtimeTransport();
      refreshDiagnostics();
      return bootstrapLogsFromServer(0);
    })
    .catch((e) => console.warn('[realtime] visibility refresh failed', e));
});

init().catch((e) => {
  console.error(e);
  showToast(e.message || '无法连接小助手，请确认 DanmuAI 已启动', true);
});
