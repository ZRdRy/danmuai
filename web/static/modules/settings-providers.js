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
  if (mode === 'doubao') return 'doubao';
  return '';
}

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

export async function loadProviders() {
  providersCache = await fetch(`${API.base}/api/providers`).then((r) => r.json());
  const sel = document.getElementById('providerPreset');
  if (sel) {
    sel.innerHTML = '<option value="">自定义</option>';
    providersCache.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.label;
      sel.appendChild(opt);
    });
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
    micSel.innerHTML = '<option value="">自定义</option>';
    providersCache.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.label;
      micSel.appendChild(opt);
    });
  }
}

export function syncProviderPresetFromEndpoint() {
  const sel = document.getElementById('providerPreset');
  if (!sel) return;
  const endpoint = document.getElementById('api_endpoint')?.value || '';
  const apiMode = document.getElementById('api_mode')?.value || '';
  const guessed = guessProviderIdFromEndpoint(endpoint, apiMode);
  if (!guessed) {
    sel.value = '';
    return;
  }
  const hasOption = Array.from(sel.options).some((opt) => opt.value === guessed);
  sel.value = hasOption ? guessed : '';
}

export function syncProviderPresetAfterEndpointEdit() {
  syncProviderPresetFromEndpoint();
  providersDeps.renderVisionModelPicker(resolveProviderIdForPicker(), document.getElementById('model')?.value || '');
}

export function applyProviderPreset(providerId) {
  const provider = providersCache.find((item) => item.id === providerId);
  if (!provider) return;
  document.getElementById('api_endpoint').value = provider.default_endpoint;
  document.getElementById('api_mode').value = provider.mode === 'openai-compatible'
    ? 'openai'
    : provider.mode;
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
