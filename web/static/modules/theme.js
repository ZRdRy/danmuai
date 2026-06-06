/** Web 控制台浅色 / 深色主题：localStorage 即时生效 + config.db 同步。 */

import { API, apiFetch, authHeaders } from './transport.js';

export const THEME_STORAGE_KEY = 'danmu_console_theme';

export function normalizeTheme(value) {
  return value === 'dark' ? 'dark' : 'light';
}

export function getStoredTheme() {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return normalizeTheme(value);
  } catch {
    return 'light';
  }
}

function storeThemeLocal(theme) {
  const normalized = normalizeTheme(theme);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, normalized);
  } catch {
    /* ignore quota / private mode */
  }
  return normalized;
}

export function applyTheme(theme) {
  const normalized = normalizeTheme(theme);
  const root = document.documentElement;
  if (normalized === 'dark') {
    root.setAttribute('data-theme', 'dark');
  } else {
    root.removeAttribute('data-theme');
  }

  const btn = document.getElementById('themeToggle');
  if (btn) {
    const isDark = normalized === 'dark';
    btn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
    btn.setAttribute('aria-label', isDark ? '切换浅色模式' : '切换黑夜模式');
    const label = btn.querySelector('.theme-toggle-label');
    if (label) {
      label.textContent = isDark ? '浅色模式' : '黑夜模式';
    }
  }
  return normalized;
}

async function syncThemeFromServer() {
  try {
    const body = await apiFetch('/api/console-theme');
    const serverTheme = normalizeTheme(body?.theme);
    const localTheme = getStoredTheme();
    if (serverTheme !== localTheme) {
      storeThemeLocal(serverTheme);
      applyTheme(serverTheme);
    }
  } catch (e) {
    console.warn('[theme] sync from server failed', e);
  }
}

async function persistThemeToServer(theme) {
  try {
    await fetch(`${API.base}/api/console-theme`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify({ theme }),
    });
  } catch (e) {
    console.warn('[theme] persist to server failed', e);
  }
}

function toggleTheme() {
  const next = getStoredTheme() === 'dark' ? 'light' : 'dark';
  storeThemeLocal(next);
  applyTheme(next);
  persistThemeToServer(next);
}

export function initTheme() {
  applyTheme(getStoredTheme());
  document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
  syncThemeFromServer();
}
