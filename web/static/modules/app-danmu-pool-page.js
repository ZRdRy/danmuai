import { apiFetch } from './transport.js';

let danmuPoolMeta = null;
let toast = () => {};
let handlersBound = false;

function showToast(message, isError = false) {
  toast(message, isError);
}

function poolEffectiveEnabledLocal() {
  return Boolean(document.getElementById('poolCustomEnabled')?.checked);
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

export async function loadDanmuPoolPage() {
  const [meta, custom] = await Promise.all([
    apiFetch('/api/danmu-pool/meta'),
    apiFetch('/api/danmu-pool/custom'),
  ]);
  danmuPoolMeta = meta;
  const customEl = document.getElementById('poolCustomEnabled');
  const minEl = document.getElementById('poolMinOnScreen');
  if (customEl) customEl.checked = Boolean(meta.custom_enabled);
  if (minEl) minEl.value = String(meta.min_on_screen ?? 5);
  renderCustomDanmuPoolList(custom.items || []);
  updatePoolMinOnScreenControl();
}

async function saveDanmuPoolSettings() {
  const body = {
    custom_enabled: Boolean(document.getElementById('poolCustomEnabled')?.checked),
    min_on_screen: parseInt(document.getElementById('poolMinOnScreen')?.value, 10) || 0,
  };
  await apiFetch('/api/danmu-pool/settings', {
    method: 'PUT',
    body: JSON.stringify(body),
  });
  danmuPoolMeta = await apiFetch('/api/danmu-pool/meta');
  updatePoolMinOnScreenControl();
  showToast('公式化弹幕库设置已保存');
}

async function addCustomDanmuPoolItems() {
  const textarea = document.getElementById('poolCustomTextarea');
  const text = textarea?.value || '';
  if (!text.trim()) {
    showToast('请先输入要追加的弹幕句子', true);
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
    showToast(`已追加 ${result.added} 条`);
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
  showToast(`已删除 ${result.removed} 条`);
}

export function initDanmuPoolPage(deps = {}) {
  toast = deps.showToast || toast;
  if (handlersBound) return;
  handlersBound = true;

  document.getElementById('btnSavePoolSettings')?.addEventListener('click', () => {
    saveDanmuPoolSettings().catch((error) => showToast(error.message, true));
  });
  document.getElementById('btnPoolCustomAppend')?.addEventListener('click', () => {
    addCustomDanmuPoolItems().catch((error) => showToast(error.message, true));
  });
  document.getElementById('btnPoolCustomClearInput')?.addEventListener('click', () => {
    const textarea = document.getElementById('poolCustomTextarea');
    if (textarea) textarea.value = '';
  });
  document.getElementById('btnPoolCustomDelete')?.addEventListener('click', () => {
    deleteSelectedCustomDanmuPoolItems().catch((error) => showToast(error.message, true));
  });
  document.getElementById('poolCustomSelectAll')?.addEventListener('change', (event) => {
    const checked = event.target.checked;
    document.querySelectorAll('#poolCustomList .pool-custom-cb').forEach((cb) => {
      cb.checked = checked;
    });
  });
  document.getElementById('poolCustomEnabled')?.addEventListener('change', () => {
    if (danmuPoolMeta) {
      danmuPoolMeta.effective_pool_enabled = poolEffectiveEnabledLocal();
    }
    updatePoolMinOnScreenControl();
  });
}
