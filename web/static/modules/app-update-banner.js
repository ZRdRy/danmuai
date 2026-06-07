import { API, apiFetch } from './transport.js';

const DEFAULT_RELEASE_URL = 'https://github.com/PEPETII/danmuai/releases';
const APP_UPDATE_DISMISS_LOCAL_KEY = 'danmu_app_update_dismissed_latest';

const appVersionState = {
  current: '',
  latest: '',
  releaseUrl: DEFAULT_RELEASE_URL,
  message: '',
  checkStatus: 'pending',
};

const appUpdateDismissState = {
  dismissedLatestVersion: '',
};

let pendingAppUpdatePrompt = null;
let toast = () => {};
let handlersBound = false;

function showToast(message, isError = false) {
  toast(message, isError);
}

function normalizeVersionString(raw) {
  let value = String(raw || '').trim();
  if (value.length > 1 && (value[0] === 'v' || value[0] === 'V') && /\d/.test(value[1])) {
    value = value.slice(1);
  }
  return value;
}

function parseVersionSegments(raw) {
  const normalized = normalizeVersionString(raw);
  if (!normalized) throw new Error('empty version');
  let core = normalized;
  let prerelease = null;
  const dash = normalized.indexOf('-');
  if (dash >= 0) {
    core = normalized.slice(0, dash);
    prerelease = normalized.slice(dash + 1).trim() || null;
  }
  if (!core) return { segments: [0], prerelease };
  const segments = core.split('.').map((piece) => {
    const match = /^(\d*)/.exec(piece.trim());
    if (!match || match[1] === '') throw new Error(`invalid segment: ${piece}`);
    return parseInt(match[1], 10);
  });
  return { segments, prerelease };
}

function compareVersions(a, b) {
  const pa = parseVersionSegments(a);
  const pb = parseVersionSegments(b);
  const len = Math.max(pa.segments.length, pb.segments.length);
  for (let i = 0; i < len; i += 1) {
    const va = pa.segments[i] ?? 0;
    const vb = pb.segments[i] ?? 0;
    if (va !== vb) return va < vb ? -1 : 1;
  }
  if (pa.prerelease === null && pb.prerelease === null) return 0;
  if (pa.prerelease === null && pb.prerelease !== null) return 1;
  if (pa.prerelease !== null && pb.prerelease === null) return -1;
  if (pa.prerelease === pb.prerelease) return 0;
  return pa.prerelease < pb.prerelease ? -1 : 1;
}

function readAppUpdateDismissFromLocal() {
  try {
    return String(localStorage.getItem(APP_UPDATE_DISMISS_LOCAL_KEY) || '').trim();
  } catch {
    return '';
  }
}

function writeAppUpdateDismissToLocal(version) {
  try {
    localStorage.setItem(APP_UPDATE_DISMISS_LOCAL_KEY, version ? String(version) : '');
  } catch {
    /* ignore */
  }
}

function mergeAppUpdateDismissState(remote, localDismissed) {
  const remoteDismissed =
    typeof remote?.dismissedLatestVersion === 'string'
      ? remote.dismissedLatestVersion.trim()
      : '';
  appUpdateDismissState.dismissedLatestVersion = remoteDismissed || localDismissed || '';
}

async function loadAppUpdateDismissState() {
  const localDismissed = readAppUpdateDismissFromLocal();
  let remote = null;
  try {
    if (API.base) {
      remote = await fetch(`${API.base}/api/app-update-state`, { cache: 'no-store' }).then((r) =>
        r.ok ? r.json() : null,
      );
    }
  } catch {
    remote = null;
  }
  mergeAppUpdateDismissState(remote, localDismissed);
  writeAppUpdateDismissToLocal(appUpdateDismissState.dismissedLatestVersion);
}

async function persistAppUpdateDismiss(latestVersion) {
  const normalized = normalizeVersionString(latestVersion);
  appUpdateDismissState.dismissedLatestVersion = normalized;
  writeAppUpdateDismissToLocal(normalized);
  try {
    await apiFetch('/api/app-update-state', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dismissedLatestVersion: normalized }),
    });
  } catch {
    /* localStorage remains */
  }
}

function refreshAppVersionFooter() {
  const currentEl = document.getElementById('appVersionCurrent');
  const latestEl = document.getElementById('appVersionLatest');
  if (!currentEl || !latestEl) return;
  currentEl.textContent = appVersionState.current || '-';
  latestEl.classList.remove('version-latest-ok', 'version-latest-update', 'version-latest-failed');
  if (appVersionState.checkStatus === 'check_failed') {
    latestEl.textContent = '检查失败';
    latestEl.classList.add('version-latest-failed');
    return;
  }
  if (appVersionState.checkStatus === 'update_available') {
    latestEl.textContent = appVersionState.latest || '-';
    latestEl.classList.add('version-latest-update');
    return;
  }
  if (appVersionState.checkStatus === 'up_to_date') {
    latestEl.textContent = '已是最新';
    latestEl.classList.add('version-latest-ok');
    return;
  }
  latestEl.textContent = '-';
}

function showAppUpdateModal(latest, message) {
  const modal = document.getElementById('appUpdateModal');
  const msgEl = document.getElementById('appUpdateModalMessage');
  if (!modal || !msgEl) return;
  let text = `发现新版本 ${latest}，是否前往下载？`;
  if (message) text += `\n\n${message}`;
  msgEl.textContent = text;
  modal.classList.remove('hidden');
  modal.classList.add('flex');
}

function closeAppUpdateModal() {
  const modal = document.getElementById('appUpdateModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.classList.remove('flex');
}

function maybeShowAppUpdateModal() {
  if (!pendingAppUpdatePrompt) return;
  const { latest, message } = pendingAppUpdatePrompt;
  if (appUpdateDismissState.dismissedLatestVersion === normalizeVersionString(latest)) {
    pendingAppUpdatePrompt = null;
    return;
  }
  showAppUpdateModal(latest, message);
  pendingAppUpdatePrompt = null;
}

export async function initAppVersionAndUpdateCheck() {
  try {
    if (!API.base) {
      appVersionState.checkStatus = 'check_failed';
      refreshAppVersionFooter();
      return;
    }
    const versionRes = await fetch(`${API.base}/api/version`, { cache: 'no-store' });
    if (!versionRes.ok) throw new Error('version api failed');
    const versionData = await versionRes.json();
    const current = String(versionData.current_version || '').trim();
    appVersionState.current = current;
    window.DANMU_APP_VERSION = current;
    refreshAppVersionFooter();

    let remoteRow = null;
    try {
      if (window.DanmuSupabase?.isConfigured?.()) {
        remoteRow = await window.DanmuSupabase.fetchAppUpdate();
      }
    } catch (error) {
      console.warn('[version] supabase check failed', error);
      remoteRow = null;
    }

    if (!remoteRow?.latest_version) {
      appVersionState.checkStatus = 'check_failed';
      refreshAppVersionFooter();
      await loadAppUpdateDismissState();
      return;
    }

    const latest = normalizeVersionString(remoteRow.latest_version);
    appVersionState.latest = latest;
    appVersionState.releaseUrl = remoteRow.release_url || DEFAULT_RELEASE_URL;
    appVersionState.message = remoteRow.message || '';

    if (compareVersions(latest, current) > 0) {
      appVersionState.checkStatus = 'update_available';
      pendingAppUpdatePrompt = { latest, message: appVersionState.message };
    } else {
      appVersionState.checkStatus = 'up_to_date';
      pendingAppUpdatePrompt = null;
    }
    refreshAppVersionFooter();

    await loadAppUpdateDismissState();
    maybeShowAppUpdateModal();
  } catch (error) {
    console.warn('[version] init check failed', error);
    appVersionState.checkStatus = 'check_failed';
    refreshAppVersionFooter();
  }
}

export function initAppUpdateModal(deps = {}) {
  toast = deps.showToast || toast;
  if (handlersBound) return;
  handlersBound = true;

  document.getElementById('btnAppUpdateYes')?.addEventListener('click', () => {
    const url = appVersionState.releaseUrl || DEFAULT_RELEASE_URL;
    closeAppUpdateModal();
    try {
      const opened = window.open(url, '_blank', 'noopener,noreferrer');
      if (!opened) {
        navigator.clipboard?.writeText(url);
        showToast('请手动打开下载页：链接已复制到剪贴板');
      }
    } catch {
      showToast(`请前往下载：${url}`);
    }
  });
  document.getElementById('btnAppUpdateNo')?.addEventListener('click', async () => {
    const latest = appVersionState.latest;
    closeAppUpdateModal();
    if (latest) {
      await persistAppUpdateDismiss(latest);
    }
  });
  document.getElementById('appUpdateModal')?.addEventListener('click', (event) => {
    if (event.target.id === 'appUpdateModal') closeAppUpdateModal();
  });
}
