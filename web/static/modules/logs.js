/** Log ring buffer, diary view rendering, and HTTP bootstrap. */

import { API, REALTIME } from './transport.js';

export const logBuffer = [];
export let logLevelFilters = new Set(['INFO', 'WARNING', 'ERROR']);
export let logAutoScroll = true;

export function replaceLogLevelFilters(next) {
  logLevelFilters = next;
}

export function setLogAutoScroll(value) {
  logAutoScroll = value;
}

export function logEntryKey(item) {
  return `${item.ts}|${item.level}|${item.message}`;
}

export function formatLogLine(item) {
  const ts = Number(item.ts) || 0;
  const iso = ts > 0 ? new Date(ts * 1000).toISOString() : '—';
  return `${iso} [${item.level || 'INFO'}] ${item.message || ''}`;
}

export function mergeLogItemsUnique(items) {
  const map = new Map();
  items.forEach((item) => {
    if (!item || item.message == null) return;
    map.set(logEntryKey(item), item);
  });
  return Array.from(map.values()).sort((a, b) => (Number(a.ts) || 0) - (Number(b.ts) || 0));
}

export function updateLogPanelState() {
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

export function renderLogView() {
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

export function appendLog(item) {
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

export function mergeLogItems(items) {
  if (!items.length) return;
  items.forEach((item) => {
    appendLog(item);
    if (item.ts > REALTIME.lastLogsPollTs) REALTIME.lastLogsPollTs = item.ts;
  });
}

/** Pull ring buffer from server (works when WS is down or page opened after events). */
export async function bootstrapLogsFromServer(sinceTs = 0) {
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
