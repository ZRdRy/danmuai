import { API, apiFetch } from './transport.js';
import { buildDiagnosticReportText } from './diagnostics.js';
import {
  formatLogLine,
  logBuffer,
  logEntryKey,
  mergeLogItemsUnique,
} from './logs.js';

const ERROR_REPORT_DISMISS_STORAGE = 'danmu_error_report_dismiss';
const ERROR_REPORT_DEDUP_MS = 24 * 60 * 60 * 1000;
const ERROR_REPORT_LOG_WINDOW_SEC = 90;
const ERROR_REPORT_LOG_LINE_RADIUS = 40;

let errorReportAnchor = null;
let errorReportSubmitting = false;
let toast = () => {};
let handlersBound = false;

function showToast(message, isError = false) {
  toast(message, isError);
}

function loadErrorReportDismissMap() {
  try {
    let raw = localStorage.getItem(ERROR_REPORT_DISMISS_STORAGE);
    if (!raw) {
      raw = sessionStorage.getItem(ERROR_REPORT_DISMISS_STORAGE);
      if (raw) {
        localStorage.setItem(ERROR_REPORT_DISMISS_STORAGE, raw);
        sessionStorage.removeItem(ERROR_REPORT_DISMISS_STORAGE);
      }
    }
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveErrorReportDismissMap(map) {
  try {
    const now = Date.now();
    const pruned = {};
    Object.entries(map).forEach(([key, entry]) => {
      if (entry && now - Number(entry.at || 0) < ERROR_REPORT_DEDUP_MS) {
        pruned[key] = entry;
      }
    });
    localStorage.setItem(ERROR_REPORT_DISMISS_STORAGE, JSON.stringify(pruned));
  } catch {
    /* ignore */
  }
}

function isErrorReportSuppressed(fingerprint) {
  const entry = loadErrorReportDismissMap()[fingerprint];
  if (!entry) return false;
  return Date.now() - Number(entry.at || 0) < ERROR_REPORT_DEDUP_MS;
}

function markErrorReportHandled(fingerprint, kind) {
  const map = loadErrorReportDismissMap();
  map[fingerprint] = { at: Date.now(), kind };
  saveErrorReportDismissMap(map);
}

async function hashErrorFingerprint(message) {
  const text = String(message || '');
  if (globalThis.crypto?.subtle) {
    const data = new TextEncoder().encode(text);
    const buf = await crypto.subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(buf))
      .map((item) => item.toString(16).padStart(2, '0'))
      .join('');
  }
  let h = 0;
  for (let i = 0; i < text.length; i += 1) {
    h = ((h << 5) - h + text.charCodeAt(i)) | 0;
  }
  return `fallback_${(h >>> 0).toString(16)}`;
}

function extractErrorReportSearchTerms(errorMessage) {
  const msg = String(errorMessage || '').trim();
  const terms = [];
  if (!msg) return terms;
  const inner = msg.match(/recent error[:\]]\s*(.+)$/i);
  if (inner && inner[1]) {
    terms.push(String(inner[1]).trim().slice(0, 120));
  }
  terms.push(msg.slice(0, 120));
  const httpMatch = msg.match(/HTTP\s+(\d{3})/i);
  if (httpMatch) terms.push(`HTTP ${httpMatch[1]}`);
  return [...new Set(terms.filter(Boolean))];
}

function findErrorLogAnchorIndex(merged, anchorMsg, anchorTs) {
  const terms = extractErrorReportSearchTerms(anchorMsg);
  for (const term of terms) {
    const idx = merged.findIndex(
      (item) =>
        (item.level === 'ERROR' || item.level === 'WARNING') &&
        String(item.message || '').includes(term),
    );
    if (idx >= 0) return idx;
  }
  const httpMatch = String(anchorMsg || '').match(/HTTP\s+(\d{3})/i);
  if (httpMatch) {
    const code = httpMatch[1];
    const codeRe = new RegExp(`HTTP\\s+${code}\\b|status[=:]\\s*${code}\\b`, 'i');
    const idx = merged.findIndex(
      (item) => item.level === 'ERROR' && codeRe.test(String(item.message || '')),
    );
    if (idx >= 0) return idx;
  }
  const nearestError = merged.reduce(
    (best, item, idx) => {
      if (item.level !== 'ERROR' && item.level !== 'WARNING') return best;
      const delta = Math.abs((Number(item.ts) || 0) - anchorTs);
      if (best.idx < 0 || delta < best.delta) return { idx, delta };
      return best;
    },
    { idx: -1, delta: Infinity },
  );
  if (nearestError.idx >= 0) return nearestError.idx;
  return merged.reduce(
    (best, item, idx) => {
      const delta = Math.abs((Number(item.ts) || 0) - anchorTs);
      if (best.idx < 0 || delta < best.delta) return { idx, delta };
      return best;
    },
    { idx: -1, delta: Infinity },
  ).idx;
}

function pickErrorLogExcerpt(merged, anchor) {
  const anchorTs = Number(anchor.ts) || Date.now() / 1000;
  const anchorMsg = String(anchor.errorMessage || '');

  let anchorIdx = findErrorLogAnchorIndex(merged, anchorMsg, anchorTs);
  if (anchorIdx < 0) anchorIdx = Math.max(0, merged.length - 1);

  const windowStart = anchorTs - ERROR_REPORT_LOG_WINDOW_SEC;
  const windowEnd = anchorTs + ERROR_REPORT_LOG_WINDOW_SEC;
  const byTime = merged.filter((item) => {
    const ts = Number(item.ts) || 0;
    return ts >= windowStart && ts <= windowEnd;
  });
  const errorsInWindow = merged.filter((item) => {
    const ts = Number(item.ts) || 0;
    return (
      ts >= windowStart &&
      ts <= windowEnd &&
      (item.level === 'ERROR' || item.level === 'WARNING')
    );
  });
  const lineStart = Math.max(0, anchorIdx - ERROR_REPORT_LOG_LINE_RADIUS);
  const lineEnd = Math.min(merged.length, anchorIdx + ERROR_REPORT_LOG_LINE_RADIUS + 1);
  const byLines = merged.slice(lineStart, lineEnd);
  const picked = mergeLogItemsUnique([...byTime, ...byLines, ...errorsInWindow]);
  const structuredKeys = new Set();
  const structured = picked.filter((item) => {
    const match = /reason=|screenshot_id|scene_generation/i.test(item.message || '');
    if (match) structuredKeys.add(logEntryKey(item));
    return match;
  });
  const rest = picked.filter((item) => !structuredKeys.has(logEntryKey(item)));
  return [...structured, ...rest].map(formatLogLine).join('\n');
}

async function collectErrorReportContext(anchor) {
  const anchorTs = Number(anchor.ts) || Date.now() / 1000;
  const sinceTs = Math.max(0, anchorTs - ERROR_REPORT_LOG_WINDOW_SEC);

  let serverItems = [];
  try {
    const base = API.base || window.location.origin.replace(/\/$/, '');
    const res = await fetch(
      `${base}/api/logs/recent?since_ts=${encodeURIComponent(sinceTs)}`,
      { cache: 'no-store' },
    );
    if (res.ok) {
      const data = await res.json();
      serverItems = data.items || [];
    }
  } catch (error) {
    console.warn('[error-report] logs/recent failed', error);
  }

  const merged = mergeLogItemsUnique([...logBuffer, ...serverItems]);
  let logsExcerpt = pickErrorLogExcerpt(merged, { ...anchor, ts: anchorTs });

  let diagnosticsJson = null;
  try {
    const diagRes = await apiFetch('/api/diagnostics');
    diagnosticsJson = diagRes.diagnostics || diagRes;
    const diagText = buildDiagnosticReportText(diagnosticsJson);
    if (diagText) {
      logsExcerpt = `${logsExcerpt}\n\n--- diagnostics ---\n${diagText}`;
    }
  } catch (error) {
    console.warn('[error-report] diagnostics failed', error);
  }

  if (anchor.statusSnapshot) {
    const snap = anchor.statusSnapshot;
    const meta = [
      `active_model_id: ${snap.active_model_id || '-'}`,
      `personae: ${(snap.persona_names || []).join(' | ') || '-'}`,
    ].join('\n');
    logsExcerpt = `${logsExcerpt}\n\n--- status ---\n${meta}`;
  }

  if (logsExcerpt.length > 8000) {
    logsExcerpt = `${logsExcerpt.slice(0, 7990)}\n...[truncated]`;
  }

  const summary = String(anchor.errorMessage || 'unknown error').trim().slice(0, 500);
  const errorFingerprint = anchor.fingerprint || (await hashErrorFingerprint(summary));
  return { summary, logsExcerpt, diagnosticsJson, errorFingerprint };
}

function showErrorReportModal(anchor) {
  const modal = document.getElementById('errorReportModal');
  const messageEl = document.getElementById('errorReportModalMessage');
  if (!modal || !messageEl) return;
  const preview = String(anchor.errorMessage || '').trim();
  messageEl.textContent = preview.length > 200 ? `${preview.slice(0, 200)}...` : preview;
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  const submitBtn = document.getElementById('btnErrorReportSubmit');
  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.textContent = '发送反馈';
  }
}

function closeErrorReportModal() {
  const modal = document.getElementById('errorReportModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.classList.remove('flex');
}

export async function maybePromptErrorReport(status) {
  if (!window.DanmuSupabase?.isConfigured?.()) return;
  const message = String(status.error_message || '').trim();
  if (!message) return;
  const fingerprint = await hashErrorFingerprint(message);
  if (isErrorReportSuppressed(fingerprint)) return;
  errorReportAnchor = {
    errorMessage: message,
    ts: Date.now() / 1000,
    fingerprint,
    statusSnapshot: {
      active_model_id: status.active_model_id,
      persona_names: status.persona_names,
    },
  };
  showErrorReportModal(errorReportAnchor);
}

async function submitErrorReportFromModal() {
  if (!errorReportAnchor || errorReportSubmitting) return;
  if (!window.DanmuSupabase?.isConfigured?.()) {
    showToast('未配置云端反馈服务', true);
    return;
  }
  const submitBtn = document.getElementById('btnErrorReportSubmit');
  errorReportSubmitting = true;
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = '发送中...';
  }
  try {
    const payload = await collectErrorReportContext(errorReportAnchor);
    await window.DanmuSupabase.submitErrorReport(payload);
    markErrorReportHandled(errorReportAnchor.fingerprint, 'sent');
    closeErrorReportModal();
    showToast('错误反馈已发送，感谢', false);
    errorReportAnchor = null;
  } catch (error) {
    showToast(error.message || '发送失败', true);
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = '发送反馈';
    }
  } finally {
    errorReportSubmitting = false;
  }
}

function dismissErrorReportModal() {
  if (errorReportAnchor?.fingerprint) {
    markErrorReportHandled(errorReportAnchor.fingerprint, 'dismiss');
  }
  errorReportAnchor = null;
  closeErrorReportModal();
}

export function initErrorReporting(deps = {}) {
  toast = deps.showToast || toast;
  if (handlersBound) return;
  handlersBound = true;
  document
    .getElementById('btnErrorReportDismiss')
    ?.addEventListener('click', dismissErrorReportModal);
  document.getElementById('btnErrorReportSubmit')?.addEventListener('click', () => {
    submitErrorReportFromModal().catch((error) => {
      showToast(error.message || '发送失败', true);
    });
  });
  document.getElementById('errorReportModal')?.addEventListener('click', (event) => {
    if (event.target.id === 'errorReportModal') dismissErrorReportModal();
  });
}
