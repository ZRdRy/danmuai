import { API } from './transport.js';

export function guessProviderIdFromEndpoint(endpoint, apiMode) {
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
  const mode = apiMode ?? document.getElementById('api_mode')?.value ?? '';
  if (mode === 'doubao') return 'custom_doubao';
  return 'custom_openai';
}

const MANUAL_PROVIDER_LABEL = '手动填写';

// Matches backend ProviderSpec.lock_mode=False presets only.
const EDITABLE_API_MODE_PROVIDER_IDS = new Set(['custom_openai', 'custom_doubao']);

export const API_MODE_OPTIONS = [
  { value: 'doubao', label: '豆包（火山方舟）' },
  { value: 'openai', label: 'OpenAI 兼容接口' },
];

// Mic tab only: suffix clarifies audio capability; API tab uses plain provider labels.
const MIC_LABEL_SUFFIX = {
  doubao: '（支持部分全模态模型）',
  mimo: '（mimo-v2.5）',
  custom_openai: '（需模型支持音频输入）',
  custom_doubao: '（需模型支持 input_audio）',
};

let providersDeps = {
  showToast: () => {},
  pickDefaultCatalogModelId: () => '',
  renderVisionModelPicker: () => {},
  pickDefaultMicCatalogModelId: () => '',
  renderMicModelPicker: () => {},
  updateMicModeHint: () => {},
};

let providersCache = [];

export function configureSettingsProviders(deps) {
  providersDeps = { ...providersDeps, ...deps };
}

export function initApiModeSelect() {
  const sel = document.getElementById('api_mode');
  if (!sel) return;
  sel.innerHTML = '';
  API_MODE_OPTIONS.forEach(({ value, label }) => {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = label;
    sel.appendChild(opt);
  });
}

export function normalizeApiModeForSelect(mode, endpoint = '') {
  const raw = String(mode || '').trim().toLowerCase();
  if (raw === 'doubao') return 'doubao';
  if (raw === 'openai' || raw === 'openai-compatible' || raw === 'openai_compatible') {
    return 'openai';
  }
  const endpointVal = endpoint || document.getElementById('api_endpoint')?.value || '';
  const providerId = guessProviderIdFromEndpoint(endpointVal, '');
  if (providerId === 'doubao' || providerId === 'custom_doubao') return 'doubao';
  return 'openai';
}

export function applyApiModeValue(mode) {
  initApiModeSelect();
  const sel = document.getElementById('api_mode');
  if (!sel) return;
  const endpoint = document.getElementById('api_endpoint')?.value || '';
  const normalized = normalizeApiModeForSelect(mode, endpoint);
  const hasOption = Array.from(sel.options).some((opt) => opt.value === normalized);
  if (hasOption) sel.value = normalized;
}

export function syncApiModeLockState() {
  const sel = document.getElementById('api_mode');
  if (!sel) return;
  const presetSel = document.getElementById('providerPreset');
  const presetId = (presetSel?.value || '').trim() || resolveProviderIdForPicker();
  const locked = Boolean(presetId && !EDITABLE_API_MODE_PROVIDER_IDS.has(presetId));
  sel.disabled = locked;
}

function appendManualProviderOption(sel) {
  const opt = document.createElement('option');
  opt.value = '';
  opt.textContent = MANUAL_PROVIDER_LABEL;
  sel.appendChild(opt);
}

function fillProviderPresetSelect(sel, { mic = false } = {}) {
  sel.innerHTML = '';
  providersCache.forEach((p) => {
    const opt = document.createElement('option');
    opt.value = p.id;
    const suffix = mic ? (MIC_LABEL_SUFFIX[p.id] || '') : '';
    opt.textContent = `${p.label}${suffix}`;
    sel.appendChild(opt);
  });
  appendManualProviderOption(sel);
}

export async function loadProviders() {
  providersCache = await fetch(`${API.base}/api/providers`).then((r) => r.json());
  const sel = document.getElementById('providerPreset');
  if (sel) {
    fillProviderPresetSelect(sel);
  }
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
  const micSel = document.getElementById('micProviderPreset');
  if (micSel) {
    fillProviderPresetSelect(micSel, { mic: true });
  }
  initApiModeSelect();
}

export function syncProviderPresetFromEndpoint() {
  const sel = document.getElementById('providerPreset');
  if (!sel) return;
  const endpoint = document.getElementById('api_endpoint')?.value || '';
  const apiMode = document.getElementById('api_mode')?.value || '';
  const guessed = guessProviderIdFromEndpoint(endpoint, apiMode);
  if (!guessed) {
    sel.value = '';
    syncApiModeLockState();
    return;
  }
  const hasOption = Array.from(sel.options).some((opt) => opt.value === guessed);
  sel.value = hasOption ? guessed : '';
  syncApiModeLockState();
}

export function syncProviderPresetAfterEndpointEdit() {
  syncProviderPresetFromEndpoint();
  providersDeps.renderVisionModelPicker(resolveProviderIdForPicker(), document.getElementById('model')?.value || '');
}

export function applyProviderPreset(providerId) {
  const provider = providersCache.find((item) => item.id === providerId);
  if (!provider) return;
  document.getElementById('api_endpoint').value = provider.default_endpoint;
  applyApiModeValue(provider.mode === 'openai-compatible' ? 'openai' : provider.mode);
  syncApiModeLockState();
  const apiKeyEl = document.getElementById('api_key');
  if (apiKeyEl) apiKeyEl.value = '';
  const defaultModelId = providersDeps.pickDefaultCatalogModelId(providerId);
  providersDeps.renderVisionModelPicker(providerId, defaultModelId, { providerSwitch: true });
  providersDeps.showToast(`已填入 ${provider.label} 的默认地址，请填写对应 API 密钥~`);
}

export function resolveProviderIdForPicker() {
  const endpoint = document.getElementById('api_endpoint')?.value || '';
  const apiMode = document.getElementById('api_mode')?.value || '';
  return guessProviderIdFromEndpoint(endpoint, apiMode);
}

export function syncMicProviderPresetFromEndpoint() {
  const sel = document.getElementById('micProviderPreset');
  if (!sel) return;
  const endpoint = document.getElementById('mic_api_endpoint')?.value || '';
  const apiMode = document.getElementById('mic_api_mode')?.value || '';
  const guessed = guessProviderIdFromEndpoint(endpoint, apiMode);
  if (!guessed) {
    sel.value = '';
    return;
  }
  const hasOption = Array.from(sel.options).some((opt) => opt.value === guessed);
  sel.value = hasOption ? guessed : '';
}

export function resolveMicProviderIdForPicker() {
  const endpoint = document.getElementById('mic_api_endpoint')?.value || '';
  const apiMode = document.getElementById('mic_api_mode')?.value || '';
  return guessProviderIdFromEndpoint(endpoint, apiMode);
}

export function applyMicProviderPreset(providerId) {
  const provider = providersCache.find((item) => item.id === providerId);
  if (!provider) return;
  document.getElementById('mic_api_endpoint').value = provider.default_endpoint;
  document.getElementById('mic_api_mode').value = provider.mode === 'openai-compatible'
    ? 'openai'
    : provider.mode;
  const micKeyEl = document.getElementById('mic_api_key');
  if (micKeyEl) micKeyEl.value = '';
  const defaultModelId = providersDeps.pickDefaultMicCatalogModelId(providerId);
  providersDeps.renderMicModelPicker(providerId, defaultModelId, { providerSwitch: true });
  providersDeps.updateMicModeHint();
  providersDeps.showToast(`已填入 ${provider.label} 的默认麦克风地址，请填写对应 API 密钥~`);
}
