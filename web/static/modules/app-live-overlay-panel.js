import { API, apiFetch } from './transport.js';

let liveOverlayStatusTimer = null;
let toast = () => {};
let handlersBound = false;

function showToast(message, isError = false) {
  toast(message, isError);
}

function formatLiveOverlayLastBroadcast(ts) {
  if (ts == null || Number.isNaN(Number(ts))) return '-';
  const date = new Date(Number(ts) * 1000);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleTimeString();
}

export async function refreshLiveOverlayStatus() {
  const connEl = document.getElementById('liveOverlayConnections');
  const lastEl = document.getElementById('liveOverlayLastBroadcast');
  const urlEl = document.getElementById('liveOverlayUrl');
  if (!connEl || !API.base) return;
  try {
    const status = await fetch(`${API.base}/api/live-overlay/status`, {
      cache: 'no-store',
    }).then((response) => {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    });
    connEl.textContent = String(status.connections ?? 0);
    if (lastEl) {
      lastEl.textContent = formatLiveOverlayLastBroadcast(status.last_broadcast_at);
    }
    if (urlEl && status.overlay_url) {
      urlEl.value = status.overlay_url;
    }
  } catch {
    connEl.textContent = '-';
    if (lastEl) lastEl.textContent = '-';
  }
}

export function initLiveOverlayPanel(deps = {}) {
  toast = deps.showToast || toast;
  const panel = document.getElementById('liveOverlayPanel');
  if (!panel) return;

  if (!handlersBound) {
    handlersBound = true;
    document.getElementById('btnCopyLiveOverlayUrl')?.addEventListener('click', () => {
      const url = document.getElementById('liveOverlayUrl')?.value || '';
      if (!url) {
        showToast('暂无直播地址');
        return;
      }
      navigator.clipboard.writeText(url).then(
        () => showToast('直播地址已复制'),
        () => showToast('复制失败，请手动选择复制', true),
      );
    });
    document.getElementById('btnLiveOverlayTest')?.addEventListener('click', async () => {
      try {
        await apiFetch('/api/live-overlay/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        showToast('测试弹幕已发送');
        await refreshLiveOverlayStatus();
      } catch (error) {
        showToast(`发送失败：${error.message || error}`, true);
      }
    });
  }

  refreshLiveOverlayStatus();
  if (liveOverlayStatusTimer) {
    clearInterval(liveOverlayStatusTimer);
  }
  liveOverlayStatusTimer = setInterval(() => {
    if (document.hidden) return;
    refreshLiveOverlayStatus();
  }, 2000);
}
