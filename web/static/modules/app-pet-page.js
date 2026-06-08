import { apiFetch } from './transport.js';

let toast = () => {};
let handlersBound = false;
let currentAssetSource = 'builtin';
let currentAssetPath = '';

function showToast(message, isError = false) {
  toast(message, isError);
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setStatusText(text) {
  setText('petStatusText', text);
}

function setAssetText(text) {
  setText('petAssetText', text);
}

function setAssetError(message) {
  const errorEl = document.getElementById('petAssetErrorText');
  if (!errorEl) return;
  if (message) {
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
  } else {
    errorEl.textContent = '';
    errorEl.classList.add('hidden');
  }
}

function setResetButtonEnabled(enabled) {
  const btn = document.getElementById('btnPetResetAsset');
  if (!btn) return;
  btn.disabled = !enabled;
  btn.classList.toggle('opacity-50', !enabled);
  btn.classList.toggle('cursor-not-allowed', !enabled);
}

function describeAsset(data) {
  const asset = data.asset || {};
  const displayName = asset.display_name || asset.id || '默认桌宠';
  const sourceLabel = currentAssetSource === 'local' ? '本地目录' : '内置默认';

  if (asset.ok) {
    setAssetText(displayName);
    setAssetError('');
  } else if (asset.error) {
    setAssetText(currentAssetSource === 'local' ? '自定义桌宠加载失败' : '默认桌宠');
    setAssetError(asset.error);
  } else {
    setAssetText('默认桌宠');
    setAssetError('');
  }

  setText('petAssetSourceText', sourceLabel);
  setText('petAssetPathText', currentAssetPath || '—');
  setResetButtonEnabled(currentAssetSource === 'local' || Boolean(currentAssetPath));
}

function fillPetForm(data) {
  const enabled = document.getElementById('petEnabled');
  const scale = document.getElementById('petScale');
  const opacity = document.getElementById('petOpacity');
  const alwaysOnTop = document.getElementById('petAlwaysOnTop');
  const clickThrough = document.getElementById('petClickThrough');
  const commandBox = document.getElementById('petCommandBoxEnabled');
  const ttl = document.getElementById('petCommandTtl');
  const applyCount = document.getElementById('petCommandApplyCount');

  if (enabled) enabled.checked = Boolean(data.enabled);
  if (scale) scale.value = String(data.scale ?? 1);
  if (opacity) opacity.value = String(data.opacity ?? 1);
  if (alwaysOnTop) alwaysOnTop.checked = Boolean(data.always_on_top);
  if (clickThrough) clickThrough.checked = Boolean(data.click_through);
  if (commandBox) commandBox.checked = Boolean(data.command_box_enabled);
  if (ttl) ttl.value = String(data.command_ttl_sec ?? 30);
  if (applyCount) applyCount.value = String(data.command_apply_count ?? 1);

  currentAssetSource = data.asset_source === 'local' ? 'local' : 'builtin';
  currentAssetPath = String(data.asset_path || '');

  const pending = data.pending_command;
  if (data.has_pending_command && pending?.preview) {
    setStatusText(`已启用 · 待注入指令：${pending.preview}`);
  } else if (!data.enabled) {
    setStatusText('未启用');
  } else if (data.visible) {
    setStatusText('已启用');
  } else {
    setStatusText('已启用 · 已隐藏（可在桌宠右键菜单显示）');
  }

  describeAsset(data);
}

function collectPetPayload() {
  return {
    enabled: Boolean(document.getElementById('petEnabled')?.checked),
    scale: parseFloat(document.getElementById('petScale')?.value) || 1,
    opacity: parseFloat(document.getElementById('petOpacity')?.value) || 1,
    always_on_top: Boolean(document.getElementById('petAlwaysOnTop')?.checked),
    click_through: Boolean(document.getElementById('petClickThrough')?.checked),
    command_box_enabled: Boolean(document.getElementById('petCommandBoxEnabled')?.checked),
    command_ttl_sec: parseInt(document.getElementById('petCommandTtl')?.value, 10) || 30,
    command_apply_count: parseInt(document.getElementById('petCommandApplyCount')?.value, 10) || 1,
    asset_source: currentAssetSource,
    asset_path: currentAssetPath,
  };
}

export async function loadPetPage() {
  const data = await apiFetch('/api/pet/settings');
  fillPetForm(data);
}

async function savePetSettings() {
  const payload = collectPetPayload();
  const data = await apiFetch('/api/pet/settings', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  fillPetForm(data);
  showToast('桌宠设置已保存');
}

async function submitPetCommand() {
  const input = document.getElementById('petCommandInput');
  const text = input?.value || '';
  if (!text.trim()) {
    showToast('请先输入指令内容', true);
    return;
  }
  await apiFetch('/api/pet/command', {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
  if (input) input.value = '';
  await loadPetPage();
  showToast('已加入下一次弹幕生成');
}

async function importPetFolder() {
  const data = await apiFetch('/api/pet/import-folder', { method: 'POST' });
  if (data.cancelled) {
    fillPetForm(data);
    return;
  }
  fillPetForm(data);
  const asset = data.asset || {};
  showToast(`已切换到桌宠：${asset.display_name || asset.id || '自定义桌宠'}`);
}

async function resetPetAsset() {
  const data = await apiFetch('/api/pet/reset-asset', { method: 'POST' });
  fillPetForm(data);
  showToast('已恢复默认桌宠');
}

export function initPetPage(deps = {}) {
  toast = deps.showToast || toast;
  if (handlersBound) return;
  handlersBound = true;

  document.getElementById('btnPetSave')?.addEventListener('click', () => {
    savePetSettings().catch((error) => showToast(error.message, true));
  });
  document.getElementById('btnPetCommandSubmit')?.addEventListener('click', () => {
    submitPetCommand().catch((error) => showToast(error.message, true));
  });
  document.getElementById('btnPetImportFolder')?.addEventListener('click', () => {
    importPetFolder().catch((error) => showToast(error.message, true));
  });
  document.getElementById('btnPetResetAsset')?.addEventListener('click', () => {
    resetPetAsset().catch((error) => showToast(error.message, true));
  });
}
