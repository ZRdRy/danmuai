/** Assistant settings form, model picker, capture region, compress preview. */

import { API, apiFetch, apiFormFetch } from './transport.js';

export const MASKED_API_KEY = '********';

let bindDeps = {
  showToast: () => {},
  navigate: () => {},
  onConfigSaved: null,
  onSettingsTabSwitch: null,
};

export function configureSettingsBindings(deps) {
  bindDeps = { ...bindDeps, ...deps };
}

function showToast(msg, isError = false) {
  bindDeps.showToast(msg, isError);
}

function navigate(page) {
  bindDeps.navigate(page);
}

const CONFIG_FIELDS = [
  'api_endpoint', 'api_mode', 'model', 'temperature', 'max_tokens',
  'danmu_speed', 'danmu_lines', 'danmu_max_chars', 'dedup_threshold',
  'screen_index', 'layout_mode', 'opacity', 'font_size', 'hotkey',
  'eviction_mode', 'danmu_pending_entry_cap', 'danmu_track_retention_cap', 'reply_queue_max_items',
  'image_max_width', 'image_quality',
  'mic_window_sec', 'mic_api_endpoint', 'mic_api_mode', 'mic_model',
  'memory_mode', 'memory_window',
  'normal_recognition_interval_sec', 'normal_reply_count',
  // W-FP-003：悬浮窗（弹幕姬式）模式与配置
  'display_mode',
  'floating_panel_opacity',
  'floating_panel_font_size',
  'floating_panel_max_items',
  'floating_panel_speed',
  'floating_panel_click_through',
];

/**
 * 助手设置「恢复默认」按 Tab 划分的字段范围。
 * api_key 不参与；识图区域（capture）走独立 API，不在此恢复。
 * 默认值来自 GET /api/config/defaults，勿在此硬编码。
 */
const SETTINGS_RESTORE_GROUPS = {
  api: [
    'api_endpoint', 'api_mode', 'screen_index', 'model', 'temperature', 'max_tokens',
    'memory_mode', 'memory_window',
  ],
  mic: ['mic_window_sec', 'mic_api_endpoint', 'mic_api_mode', 'mic_model'],
  capture: [],
  danmu: [
    'normal_recognition_interval_sec', 'normal_reply_count', 'danmu_speed', 'danmu_lines',
    'font_size', 'danmu_max_chars', 'opacity', 'dedup_threshold', 'layout_mode', 'hotkey',
    'eviction_mode', 'danmu_pending_entry_cap', 'danmu_track_retention_cap', 'reply_queue_max_items',
    'display_mode', 'floating_panel_opacity', 'floating_panel_font_size',
    'floating_panel_max_items', 'floating_panel_speed', 'floating_panel_click_through',
  ],
  rhythm: ['image_max_width', 'image_quality'],
  'danmu-read': [],
};

const SETTINGS_RESTORE_CHECKBOXES = {
  api: [],
  mic: ['mic_mode_enabled', 'mic_use_visual_model'],
  capture: [],
  danmu: ['empty_accel'],
  rhythm: [],
};

let configDefaultsCache = null;
let activeSettingsTabId = 'api';

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

export function initSettingsUiMode() {
  applySettingsUiMode();
  document.querySelectorAll('.settings-ui-mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      setSettingsUiMode(btn.dataset.settingsUiMode);
    });
  });
}

export function initNormalBatchControls() {
  ['normal_reply_count', 'normal_recognition_interval_sec', 'danmu_max_chars'].forEach((id) => {
    document.getElementById(id)?.addEventListener('input', updateNormalBatchPreview);
    document.getElementById(id)?.addEventListener('change', updateNormalBatchPreview);
  });
  updateNormalBatchPreview();
}

function configDefaultValue(key) {
  if (configDefaultsCache && configDefaultsCache[key] !== undefined && configDefaultsCache[key] !== '') {
    return String(configDefaultsCache[key]);
  }
  return '';
}

export async function loadConfigDefaults() {
  try {
    configDefaultsCache = await apiFetch('/api/config/defaults');
  } catch {
    configDefaultsCache = {};
  }
}

function allRestorableSettingKeys() {
  const keys = new Set();
  Object.values(SETTINGS_RESTORE_GROUPS).forEach((group) => {
    group.forEach((key) => keys.add(key));
  });
  Object.values(SETTINGS_RESTORE_CHECKBOXES).forEach((group) => {
    group.forEach((key) => keys.add(key));
  });
  return [...keys];
}

function restorableKeysForScope(scope) {
  if (scope === 'all') return allRestorableSettingKeys();
  const fields = SETTINGS_RESTORE_GROUPS[activeSettingsTabId] || [];
  const checkboxes = SETTINGS_RESTORE_CHECKBOXES[activeSettingsTabId] || [];
  return [...fields, ...checkboxes];
}

function applyDefaultToField(key, rawValue) {
  const value = rawValue === undefined || rawValue === null ? '' : String(rawValue);
  if (key === 'mic_mode_enabled' || key === 'mic_use_visual_model' || key === 'empty_accel' || key === 'floating_panel_click_through') {
    const el = document.getElementById(key);
    if (el) el.checked = value === '1';
    return;
  }
  const el = document.getElementById(key);
  if (!el) return;
  if (key === 'memory_mode') {
    const allowed = ['off', 'dedup_only', 'scene_card', 'strong'];
    el.value = allowed.includes(value) ? value : 'off';
    return;
  }
  if (key === 'layout_mode') {
    const allowed = ['fullscreen', '3/4', '1/2', '1/4'];
    el.value = allowed.includes(value) ? value : 'fullscreen';
    return;
  }
  if (key === 'display_mode') {
    const allowed = ['overlay', 'floating_panel', 'both'];
    el.value = allowed.includes(value) ? value : 'overlay';
    return;
  }
  if (key === 'eviction_mode') {
    el.value = value === 'accelerate' ? 'accelerate' : 'natural';
    return;
  }
  el.value = value;
}

/**
 * 恢复默认只改表单、不 POST /api/config，避免误点直接覆盖持久化配置。
 * api_key 不参与恢复：保留当前输入（含掩码 ******** 或用户刚输入的新密钥）。
 */
function applySettingsDefaults(scope) {
  if (!configDefaultsCache || !Object.keys(configDefaultsCache).length) {
    showToast('无法加载默认配置，请刷新页面后重试', true);
    return;
  }
  const keys = restorableKeysForScope(scope);
  if (scope === 'current' && keys.length === 0) {
    showToast('当前分组无可恢复的表单项', true);
    closeRestoreDefaultsModal();
    return;
  }
  const apiKeyEl = document.getElementById('api_key');
  const micKeyEl = document.getElementById('mic_api_key');
  const apiKeySnapshot = apiKeyEl?.value ?? '';
  const micKeySnapshot = micKeyEl?.value ?? '';
  keys.forEach((key) => {
    applyDefaultToField(key, configDefaultsCache[key]);
  });
  if (apiKeyEl) apiKeyEl.value = apiKeySnapshot;
  if (micKeyEl) micKeyEl.value = micKeySnapshot;
  syncProviderPresetFromEndpoint();
  const modelId = configDefaultsCache.model || document.getElementById('model')?.value || '';
  syncVisionModelPickerFromForm(modelId);
  syncMicProviderPresetFromEndpoint();
  const micModelId = configDefaultsCache.mic_model || document.getElementById('mic_model')?.value || '';
  syncMicModelPickerFromForm(micModelId);
  applyMicIndependentVisibility();
  updateMicModeHint();
  updateNormalBatchPreview();
  closeRestoreDefaultsModal();
  showToast('已恢复默认值，请点击「保存配置」生效');
}

function openRestoreDefaultsModal() {
  const modal = document.getElementById('restoreDefaultsModal');
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.classList.add('flex');
}

function closeRestoreDefaultsModal() {
  const modal = document.getElementById('restoreDefaultsModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.classList.remove('flex');
}

export function initRestoreDefaultsControls() {
  document.getElementById('btnRestoreSettingsDefaults')?.addEventListener('click', openRestoreDefaultsModal);
  document.getElementById('btnRestoreDefaultsCurrent')?.addEventListener('click', () => {
    applySettingsDefaults('current');
  });
  document.getElementById('btnRestoreDefaultsAll')?.addEventListener('click', () => {
    applySettingsDefaults('all');
  });
  document.getElementById('btnRestoreDefaultsCancel')?.addEventListener('click', closeRestoreDefaultsModal);
  const modal = document.getElementById('restoreDefaultsModal');
  modal?.addEventListener('click', (e) => {
    if (e.target === modal) closeRestoreDefaultsModal();
  });
}

export function collectFormData() {
  syncVisionModelToHidden();
  syncMicModelToHidden();
  const data = {};
  CONFIG_FIELDS.forEach((name) => {
    const el = document.getElementById(name);
    if (el) data[name] = el.value;
  });
  data.empty_accel = document.getElementById('empty_accel')?.checked ? '1' : '0';
  data.mic_mode_enabled = document.getElementById('mic_mode_enabled')?.checked ? '1' : '0';
  data.mic_use_visual_model = document.getElementById('mic_use_visual_model')?.checked ? '1' : '0';
  // W-FP-003：悬浮窗鼠标穿透 checkbox
  data.floating_panel_click_through = document.getElementById('floating_panel_click_through')?.checked ? '1' : '0';
  const key = (document.getElementById('api_key')?.value || '').trim();
  if (key && key !== MASKED_API_KEY) data.api_key = key;
  const micKey = (document.getElementById('mic_api_key')?.value || '').trim();
  if (micKey && micKey !== MASKED_API_KEY) data.mic_api_key = micKey;
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

function isMicUseVisualModel() {
  return document.getElementById('mic_use_visual_model')?.checked !== false;
}

function applyMicIndependentVisibility() {
  const section = document.getElementById('micIndependentSection');
  if (!section) return;
  section.classList.toggle('hidden', isMicUseVisualModel());
}

function getMicConfigContext() {
  if (isMicUseVisualModel()) {
    return {
      apiMode: document.getElementById('api_mode')?.value || 'doubao',
      modelId: (document.getElementById('model')?.value || '').trim(),
      endpoint: document.getElementById('api_endpoint')?.value || '',
    };
  }
  return {
    apiMode: document.getElementById('mic_api_mode')?.value || 'doubao',
    modelId: (document.getElementById('mic_model')?.value || '').trim(),
    endpoint: document.getElementById('mic_api_endpoint')?.value || '',
  };
}

function micModeConfigSupported() {
  const { apiMode, modelId, endpoint } = getMicConfigContext();
  const providerId = guessProviderIdFromEndpoint(endpoint, apiMode);
  if (apiMode === 'doubao' || providerId === 'doubao') {
    return micAudioLikelySupported || catalogModelSupportsMic(modelId);
  }
  if (providerId === 'mimo') {
    return micAudioLikelySupported
      || (modelId === 'mimo-v2.5' && catalogModelSupportsMic(modelId));
  }
  return false;
}

export function updateMicModeHint() {
  const hint = document.getElementById('micModeHint');
  const micOn = document.getElementById('mic_mode_enabled')?.checked;
  if (!hint) return;
  if (!micOn) {
    hint.classList.add('hidden');
    hint.textContent = '';
    return;
  }
  const { apiMode, modelId, endpoint } = getMicConfigContext();
  const providerId = guessProviderIdFromEndpoint(endpoint, apiMode);
  if (micModeConfigSupported()) {
    hint.classList.add('hidden');
    hint.textContent = '';
    return;
  }
  hint.classList.remove('hidden');
  if (providerId === 'mimo') {
    hint.textContent = `麦克风模式需使用 MiMo-V2.5（mimo-v2.5）。当前模型「${modelId || '未选'}」不支持开麦；请在麦克风标签改选 mimo-v2.5 或开启「与识图模型相同」，保存后再开始弹幕。`;
    return;
  }
  if (apiMode !== 'doubao' && providerId !== 'doubao') {
    hint.textContent = '麦克风模式需使用火山方舟豆包（doubao）或小米 MiMo（mimo-v2.5）。当前配置不支持开麦；可在本标签单独配置，或开启「与识图模型相同」。';
    return;
  }
  hint.textContent = `当前模型「${modelId || '未选'}」可能听不懂麦克风。请改选带「支持麦克风」的模型（例如 doubao-seed-2-0-mini），保存后再开始弹幕。`;
}

export function fillForm(cfg) {
  CONFIG_FIELDS.forEach((name) => {
    const el = document.getElementById(name);
    if (el && cfg[name] !== undefined) el.value = cfg[name];
  });
  const setIfEmpty = (id) => {
    const el = document.getElementById(id);
    const fallback = configDefaultValue(id);
    if (el && fallback && (cfg[id] === undefined || cfg[id] === '' || cfg[id] === null)) {
      el.value = fallback;
    }
  };
  setIfEmpty('danmu_speed');
  setIfEmpty('danmu_lines');
  setIfEmpty('font_size');
  setIfEmpty('opacity');
  setIfEmpty('dedup_threshold');
  setIfEmpty('hotkey');
  setIfEmpty('image_max_width');
  setIfEmpty('temperature');
  setIfEmpty('max_tokens');
  setIfEmpty('image_quality');
  setIfEmpty('danmu_max_chars');
  setIfEmpty('danmu_pending_entry_cap');
  setIfEmpty('danmu_track_retention_cap');
  setIfEmpty('reply_queue_max_items');
  // W-FP-003：悬浮窗字段
  setIfEmpty('display_mode');
  setIfEmpty('floating_panel_opacity');
  setIfEmpty('floating_panel_font_size');
  setIfEmpty('floating_panel_max_items');
  setIfEmpty('floating_panel_speed');
  const fpClickThrough = document.getElementById('floating_panel_click_through');
  if (fpClickThrough) {
    const value = cfg.floating_panel_click_through;
    if (value === '0' || value === 'false') fpClickThrough.checked = false;
    else if (value === '1' || value === 'true') fpClickThrough.checked = true;
    else fpClickThrough.checked = configDefaultValue('floating_panel_click_through') !== '0';
  }
  const evictionMode = document.getElementById('eviction_mode');
  if (evictionMode && !cfg.eviction_mode) {
    evictionMode.value = configDefaultValue('eviction_mode') || 'natural';
  }
  const emptyAccel = document.getElementById('empty_accel');
  if (emptyAccel) emptyAccel.checked = cfg.empty_accel !== '0';
  const memoryMode = document.getElementById('memory_mode');
  if (memoryMode) {
    const allowed = ['off', 'dedup_only', 'scene_card', 'strong'];
    const fallback = configDefaultValue('memory_mode') || 'off';
    memoryMode.value = allowed.includes(cfg.memory_mode) ? cfg.memory_mode : fallback;
  }
  const memoryWindow = document.getElementById('memory_window');
  if (memoryWindow && !cfg.memory_window) memoryWindow.value = configDefaultValue('memory_window') || '10';
  micAudioLikelySupported = cfg.mic_audio_likely_supported !== false;
  const micMode = document.getElementById('mic_mode_enabled');
  if (micMode) micMode.checked = cfg.mic_mode_enabled === '1';
  const micUseVisual = document.getElementById('mic_use_visual_model');
  if (micUseVisual) micUseVisual.checked = cfg.mic_use_visual_model !== '0';
  const micWindow = document.getElementById('mic_window_sec');
  if (micWindow && !cfg.mic_window_sec) micWindow.value = configDefaultValue('mic_window_sec') || '5';
  const micModelEl = document.getElementById('mic_model');
  const micModelId = cfg.mic_model || configDefaultValue('mic_model') || '';
  if (micModelEl) micModelEl.value = micModelId;
  syncMicProviderPresetFromEndpoint();
  syncMicModelPickerFromForm(micModelId);
  const micKeyEl = document.getElementById('mic_api_key');
  if (micKeyEl) micKeyEl.value = cfg.has_mic_api_key ? MASKED_API_KEY : '';
  applyMicIndependentVisibility();
  updateMicModeHint();
  const layoutMode = document.getElementById('layout_mode');
  if (layoutMode) {
    const allowed = ['fullscreen', '3/4', '1/2', '1/4'];
    const fallback = configDefaultValue('layout_mode') || 'fullscreen';
    layoutMode.value = allowed.includes(cfg.layout_mode) ? cfg.layout_mode : fallback;
  }
  const normalInterval = document.getElementById('normal_recognition_interval_sec');
  if (normalInterval && !cfg.normal_recognition_interval_sec) {
    normalInterval.value = configDefaultValue('normal_recognition_interval_sec') || '5';
  }
  const normalCount = document.getElementById('normal_reply_count');
  if (normalCount && !cfg.normal_reply_count) {
    normalCount.value = configDefaultValue('normal_reply_count') || String(DEFAULT_NORMAL_REPLY_COUNT);
  }
  updateNormalBatchPreview();
  const modelId = cfg.active_model_id || cfg.default_model_id || cfg.model || '';
  const modelEl = document.getElementById('model');
  if (modelEl) modelEl.value = modelId;
  syncVisionModelPickerFromForm(modelId);
  updateModelActiveSourceBanner(cfg);
  document.getElementById('api_key').value = cfg.has_api_key ? MASKED_API_KEY : '';
}

function updateModelActiveSourceBanner(cfg) {
  const banner = document.getElementById('modelActiveSourceBanner');
  if (!banner) return;
  const usesCustom = cfg?.uses_custom_credentials === true;
  if (!usesCustom) {
    banner.classList.add('hidden');
    banner.textContent = '';
    return;
  }
  const name = cfg.model_display_name || cfg.active_model_id || '';
  const id = cfg.active_model_id || '';
  banner.textContent =
    `当前默认模型来自自定义模型「${name}」（${id}）。助手设置中的 API 地址与密钥不用于生成弹幕，请在自定义模型列表中维护。`;
  banner.classList.remove('hidden');
  if (cfg.provider_model_mismatch) {
    banner.textContent +=
      ' 另外：当前 API 地址与已选模型目录不一致，保存配置时可能被拒绝，请重新选择视觉模型。';
  }
}

export async function reloadConfigFromServer() {
  const cfg = await apiFetch('/api/config');
  fillForm(cfg);
  syncProviderPresetFromEndpoint();
  const modelId = cfg.active_model_id || cfg.default_model_id || cfg.model || '';
  syncVisionModelPickerFromForm(modelId);
  updateModelActiveSourceBanner(cfg);
  await loadCustomModels();
  applyCaptureRegionFromPayload({
    mode: cfg.capture_region_mode || (cfg.region_w > 0 && cfg.region_h > 0 ? 'custom' : 'full'),
    region: {
      x: cfg.region_x ?? 0,
      y: cfg.region_y ?? 0,
      w: cfg.region_w ?? 0,
      h: cfg.region_h ?? 0,
    },
    selection_state: 'idle',
  });
  return cfg;
}

let captureRegionPollTimer = null;

export function applyCaptureRegionFromPayload(data) {
  const modeEl = document.getElementById('captureRegionModeLabel');
  const coordsEl = document.getElementById('captureRegionCoords');
  const resetBtn = document.getElementById('btnCaptureRegionReset');
  const selectBtn = document.getElementById('btnCaptureRegionSelect');
  if (!modeEl || !data) return;

  const mode = data.mode || 'full';
  const region = data.region || {};
  const state = data.selection_state || 'idle';
  const selecting = state === 'selecting';

  if (selectBtn) {
    selectBtn.disabled = selecting;
    selectBtn.textContent = selecting ? '正在框选…' : '鼠标框选识图范围';
  }

  if (selecting) {
    modeEl.textContent = '正在框选…请在识图显示器上拖动鼠标（Esc 取消）';
    coordsEl?.classList.add('hidden');
    return;
  }

  if (mode === 'custom' && region.w > 0 && region.h > 0) {
    modeEl.textContent = '自定义区域识图';
    if (coordsEl) {
      coordsEl.textContent = `区域：x=${region.x}, y=${region.y}, 宽=${region.w}, 高=${region.h}`;
      coordsEl.classList.remove('hidden');
    }
    resetBtn?.classList.remove('hidden');
    return;
  }

  modeEl.textContent = '全屏识图';
  coordsEl?.classList.add('hidden');
  resetBtn?.classList.add('hidden');
}

async function fetchCaptureRegionStatus() {
  return apiFetch('/api/capture-region');
}

function stopCaptureRegionPoll() {
  if (captureRegionPollTimer) {
    clearTimeout(captureRegionPollTimer);
    captureRegionPollTimer = null;
  }
}

async function pollCaptureRegionUntilDone() {
  stopCaptureRegionPoll();
  const maxMs = 120000;
  const intervalMs = 500;
  const start = Date.now();

  return new Promise((resolve) => {
    const tick = async () => {
      try {
        const data = await fetchCaptureRegionStatus();
        applyCaptureRegionFromPayload(data);
        const state = data.selection_state || 'idle';
        if (state !== 'selecting') {
          stopCaptureRegionPoll();
          resolve(data);
          return;
        }
        if (Date.now() - start >= maxMs) {
          stopCaptureRegionPoll();
          applyCaptureRegionFromPayload({ selection_state: 'timeout' });
          showToast('框选等待超时，请重试', true);
          resolve(data);
          return;
        }
        captureRegionPollTimer = setTimeout(tick, intervalMs);
      } catch (e) {
        stopCaptureRegionPoll();
        showToast(e.message || '获取识图区域状态失败', true);
        resolve(null);
      }
    };
    tick();
  });
}

export function initCaptureRegionControls() {
  document.getElementById('btnCaptureRegionSelect')?.addEventListener('click', async () => {
    try {
      const res = await apiFetch('/api/capture-region/select', { method: 'POST' });
      applyCaptureRegionFromPayload({
        mode: 'full',
        region: { x: 0, y: 0, w: 0, h: 0 },
        selection_state: res.selection_state || 'selecting',
      });
      showToast('请在识图显示器上拖动鼠标框选区域~');
      const done = await pollCaptureRegionUntilDone();
      if (!done) return;
      if (done.selection_state === 'saved') {
        showToast('识图区域已保存~');
      } else if (done.selection_state === 'cancelled') {
        showToast('已取消框选');
      } else if (done.selection_state === 'invalid') {
        showToast('区域无效或过小，请重新框选', true);
      }
    } catch (e) {
      showToast(e.message || '无法启动框选', true);
    }
  });

  document.getElementById('btnCaptureRegionReset')?.addEventListener('click', async () => {
    try {
      await apiFetch('/api/capture-region/reset', { method: 'POST' });
      const data = await fetchCaptureRegionStatus();
      applyCaptureRegionFromPayload(data);
      showToast('已恢复全屏识图~');
    } catch (e) {
      showToast(e.message || '恢复全屏失败', true);
    }
  });

  fetchCaptureRegionStatus()
    .then(applyCaptureRegionFromPayload)
    .catch(() => {});
}

export async function loadScreens() {
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

export async function loadProviders() {
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

function pickDefaultCatalogModelId(providerId) {
  const platform = resolveCatalogPlatform(providerId);
  if (!platform?.models?.length) return '';
  const preferred = platform.default_model_id;
  if (preferred && platform.models.some((m) => m.id === preferred)) {
    return preferred;
  }
  const cheapest = platform.models.find((m) => m.cheapest);
  return (cheapest || platform.models[0]).id;
}

function syncProviderPresetFromEndpoint() {
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

/** Catalog platform for vision picker: endpoint + api_mode only (not providerPreset). */
function resolveProviderIdForPicker() {
  const endpoint = document.getElementById('api_endpoint')?.value || '';
  const apiMode = document.getElementById('api_mode')?.value || '';
  return guessProviderIdFromEndpoint(endpoint, apiMode);
}

export function syncProviderPresetAfterEndpointEdit() {
  syncProviderPresetFromEndpoint();
  syncVisionModelPickerFromForm(document.getElementById('model')?.value || '');
}

// 切换服务商预设：填 endpoint/mode、清空 API Key 输入、重置为 catalog 默认视觉模型。
// 仅影响表单；运行中配置以 PUT /api/config 为准，与 Qt Overlay 无关。
export function applyProviderPreset(providerId) {
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

export async function loadModelCatalog() {
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

function guessProviderIdFromEndpoint(endpoint, apiMode) {
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

    const textWrap = document.createElement('span');
    textWrap.className = 'vision-model-id flex flex-col min-w-0';
    const nameSpan = document.createElement('span');
    nameSpan.className = 'font-semibold text-warmText truncate';
    nameSpan.textContent = model.name || model.id;
    const idSpan = document.createElement('span');
    idSpan.className = 'text-xs text-gray-400 truncate';
    idSpan.textContent = model.id;
    textWrap.append(nameSpan, idSpan);

    row.append(radio, textWrap);
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
  renderVisionModelPicker(resolveProviderIdForPicker(), selectedModelId || '');
}

const MIC_MODEL_CUSTOM_VALUE = '__mic_custom__';

function resolveMicProviderIdForPicker() {
  const endpoint = document.getElementById('mic_api_endpoint')?.value || '';
  const apiMode = document.getElementById('mic_api_mode')?.value || '';
  return guessProviderIdFromEndpoint(endpoint, apiMode);
}

function pickDefaultMicCatalogModelId(providerId) {
  const platform = resolveCatalogPlatform(providerId);
  if (!platform?.models?.length) return '';
  const micModel = platform.models.find((m) => m.supports_mic);
  return micModel ? micModel.id : '';
}

function setMicModelValue(modelId) {
  const hidden = document.getElementById('mic_model');
  if (hidden) hidden.value = modelId || '';
  updateMicModeHint();
}

function syncMicModelToHidden() {
  const customWrap = document.getElementById('micModelCustom');
  const customInput = document.getElementById('micModelCustomInput');
  const checked = document.querySelector('input[name="mic_model_choice"]:checked');
  if (checked?.value === MIC_MODEL_CUSTOM_VALUE) {
    setMicModelValue(customInput?.value?.trim() || '');
    return;
  }
  if (checked) {
    setMicModelValue(checked.value);
    return;
  }
  if (customWrap && !customWrap.classList.contains('hidden') && customInput) {
    setMicModelValue(customInput.value.trim());
  }
}

function showMicModelCustom(show, initialValue = '') {
  const wrap = document.getElementById('micModelCustom');
  const input = document.getElementById('micModelCustomInput');
  if (!wrap || !input) return;
  if (show) {
    wrap.classList.remove('hidden');
    if (initialValue !== undefined && initialValue !== null) input.value = initialValue;
    input.oninput = () => setMicModelValue(input.value.trim());
  } else {
    wrap.classList.add('hidden');
    input.oninput = null;
  }
}

function setMicModelPickerVisible(visible) {
  const picker = document.getElementById('micModelPicker');
  if (!picker) return;
  if (visible) picker.classList.remove('hidden');
  else picker.classList.add('hidden');
}

function renderMicModelPicker(providerId, selectedModelId, options = {}) {
  const picker = document.getElementById('micModelPicker');
  if (!picker) return;

  const { providerSwitch = false } = options;
  const platform = resolveCatalogPlatform(providerId);
  const micModels = (platform?.models || []).filter((m) => m.supports_mic);
  if (!micModels.length) {
    picker.innerHTML = '';
    setMicModelPickerVisible(false);
    const customInitial = providerSwitch ? '' : (selectedModelId || '');
    showMicModelCustom(true, customInitial);
    setMicModelValue(customInitial);
    return;
  }

  setMicModelPickerVisible(true);
  picker.innerHTML = '';
  const knownIds = new Set(micModels.map((m) => m.id));
  const defaultId = pickDefaultMicCatalogModelId(providerId);
  let selected;
  let useCustom;
  if (providerSwitch) {
    selected = defaultId || micModels[0].id;
    useCustom = false;
  } else {
    selected = selectedModelId && knownIds.has(selectedModelId)
      ? selectedModelId
      : (defaultId || micModels[0].id);
    useCustom = Boolean(selectedModelId && !knownIds.has(selectedModelId));
  }

  micModels.forEach((model) => {
    const row = document.createElement('label');
    row.className = 'vision-model-row';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'mic_model_choice';
    radio.value = model.id;
    radio.checked = !useCustom && model.id === selected;
    radio.addEventListener('change', () => {
      if (radio.checked) {
        showMicModelCustom(false);
        setMicModelValue(model.id);
      }
    });

    const textWrap = document.createElement('span');
    textWrap.className = 'vision-model-id flex flex-col min-w-0';
    const nameSpan = document.createElement('span');
    nameSpan.className = 'font-semibold text-warmText truncate';
    nameSpan.textContent = model.name || model.id;
    const idSpan = document.createElement('span');
    idSpan.className = 'text-xs text-gray-400 truncate';
    idSpan.textContent = model.id;
    textWrap.append(nameSpan, idSpan);

    row.append(radio, textWrap);
    appendVisionModelRowMeta(row, model);
    picker.appendChild(row);
  });

  const otherRow = document.createElement('label');
  otherRow.className = 'vision-model-row';
  const otherRadio = document.createElement('input');
  otherRadio.type = 'radio';
  otherRadio.name = 'mic_model_choice';
  otherRadio.value = MIC_MODEL_CUSTOM_VALUE;
  otherRadio.checked = useCustom;
  otherRadio.addEventListener('change', () => {
    const current = document.getElementById('mic_model')?.value || '';
    showMicModelCustom(true, useCustom ? (selectedModelId || current) : '');
    syncMicModelToHidden();
  });
  const otherLabel = document.createElement('span');
  otherLabel.className = 'vision-model-id';
  otherLabel.textContent = '自定义模型';
  otherRow.append(otherRadio, otherLabel);
  picker.appendChild(otherRow);

  if (useCustom) {
    showMicModelCustom(true, selectedModelId);
  } else {
    setMicModelValue(selected);
  }
}

function syncMicModelPickerFromForm(selectedModelId) {
  renderMicModelPicker(resolveMicProviderIdForPicker(), selectedModelId || '');
}

function syncMicProviderPresetFromEndpoint() {
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

function applyMicProviderPreset(providerId) {
  const p = providersCache.find((x) => x.id === providerId);
  if (!p) return;
  document.getElementById('mic_api_endpoint').value = p.default_endpoint;
  document.getElementById('mic_api_mode').value = p.mode === 'openai-compatible' ? 'openai' : p.mode;
  const micKeyEl = document.getElementById('mic_api_key');
  if (micKeyEl) micKeyEl.value = '';
  const defaultModelId = pickDefaultMicCatalogModelId(providerId);
  renderMicModelPicker(providerId, defaultModelId, { providerSwitch: true });
  updateMicModeHint();
  showToast(`已填入 ${p.label} 的默认麦克风地址，请填写对应 API 密钥~`);
}

// 自定义模型 CRUD：掩码 apiKey 在服务端保留；设为默认会同步 global model（ConfigService 双写规则）
export async function loadCustomModels() {
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
        const cfg = await reloadConfigFromServer();
        updateModelActiveSourceBanner(cfg);
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
/** 助手设置表单字段说明（悬停 Label 旁 ⓘ 显示） */
const SETTINGS_FIELD_TIPS = {
  providerPreset:
    '选一个常见 AI 平台，会自动填好接口地址和模式；选「自定义」则需自己逐项设置。',
  api_endpoint:
    '视觉模型服务的网址。火山方舟豆包一般填到 /api/v3；多数 OpenAI 兼容服务填到 /v1。',
  api_mode:
    'doubao：火山方舟豆包。openai：其他兼容 Chat 接口的服务（如部分第三方中转）。',
  mic_use_visual_model:
    '开启时开麦与识图共用上方「API 与模型」的接口与模型；关闭后可在本标签单独配置支持麦克风的模型。',
  micProviderPreset:
    '为麦克风接话选择服务商预设，会自动填入麦克风 API 地址与模式。',
  mic_api_endpoint:
    '麦克风专用 API 地址。豆包一般填到 /api/v3；MiMo 等 OpenAI 兼容服务填到 /v1。',
  mic_api_mode:
    '麦克风请求使用的 API 模式。开麦需 doubao 全模态或 MiMo 的 mimo-v2.5。',
  mic_model:
    '听懂麦克风并生成接话弹幕的模型；与识图视觉模型可不同。',
  mic_api_key:
    '麦克风专用 API 密钥，与识图密钥分开加密保存。留空保存不会覆盖已有密钥。',
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
  danmu_pending_entry_cap:
    '入口区（屏幕右侧待滚入）最多保留几条 pending 弹幕。0 表示无限制；低配机可设 200–500 作性能保护，超出时淘汰最远屏外条目而非拒绝新弹幕。',
  danmu_track_retention_cap:
    '所有轨道上同时保留的弹幕总条数上限。0 表示无限制；超出时优先淘汰屏外 pending。',
  reply_queue_max_items:
    'AI 回复在入队等待上屏时的最大条数。0 表示不裁剪；>0 时超出会从队首丢弃最旧条目。',
  empty_accel:
    '某行轨道空了时，暂时加快滚动，让新弹幕更快占满空位。',
  display_mode:
    '仅横向：保留原屏幕弹幕。 仅悬浮窗：开一个独立弹幕姬式悬浮窗。 两者并存：横向与悬浮窗同时显示。',
  floating_panel_opacity:
    '悬浮窗整体不透明度 0–100（0 = 完全透明，100 = 完全不透明）。',
  floating_panel_font_size:
    '悬浮窗内每条弹幕的字号（12–48 px）。',
  floating_panel_max_items:
    '悬浮窗同时显示的最多条数。超过时按 FIFO 丢最旧。',
  floating_panel_speed:
    '悬浮窗弹幕向上滚动的速度（0.5–5.0；越大越快）。',
  floating_panel_click_through:
    '勾选后鼠标点击会穿透悬浮窗，落到下层窗口（推荐开）。关闭后可在悬浮窗内拖动窗口。',
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

export function initSidebarNavFloatingHints() {
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

export function initSettingsFieldHints() {
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

export function switchSettingsTab(tabId) {
  activeSettingsTabId = tabId;
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
  bindDeps.onSettingsTabSwitch?.(tabId);
}

export function initSettingsTabs() {
  document.querySelectorAll('.settings-tab').forEach((tab) => {
    tab.addEventListener('click', () => switchSettingsTab(tab.dataset.settingsTab));
  });
}

export function bindSettingsControls(deps = {}) {
  configureSettingsBindings(deps);
  const { onConfigSaved } = bindDeps;

  document.getElementById('mic_mode_enabled')?.addEventListener('change', updateMicModeHint);
  document.getElementById('mic_use_visual_model')?.addEventListener('change', () => {
    applyMicIndependentVisibility();
    updateMicModeHint();
  });
  document.getElementById('micProviderPreset')?.addEventListener('change', (e) => {
    const id = e.target.value;
    if (id) applyMicProviderPreset(id);
    else syncMicProviderPresetFromEndpoint();
  });
  ['mic_api_endpoint', 'mic_api_mode'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', () => {
      syncMicProviderPresetFromEndpoint();
      syncMicModelPickerFromForm(document.getElementById('mic_model')?.value || '');
      updateMicModeHint();
    });
    document.getElementById(id)?.addEventListener('input', () => {
      syncMicProviderPresetFromEndpoint();
      updateMicModeHint();
    });
  });

  document.getElementById('settingsForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await apiFetch('/api/config', { method: 'POST', body: JSON.stringify({ data: collectFormData() }) });
      const cfg = await reloadConfigFromServer();
      const active = cfg.active_model_id || cfg.model || '';
      const label = cfg.model_display_name && cfg.model_display_name !== active
        ? `${cfg.model_display_name}（${active}）`
        : active;
      showToast(label ? `配置已保存，当前生效模型：${label}` : '配置已保存~');
      if (onConfigSaved) onConfigSaved();
      const keyInput = document.getElementById('api_key');
      if (keyInput?.value && keyInput.value !== MASKED_API_KEY) {
        keyInput.value = MASKED_API_KEY;
      }
      const micKeyInput = document.getElementById('mic_api_key');
      if (micKeyInput?.value && micKeyInput.value !== MASKED_API_KEY) {
        micKeyInput.value = MASKED_API_KEY;
      }
    } catch (err) {
      showToast(err.message || '保存时出了点小状况', true);
    }
  });

  document.getElementById('btnSaveAndStart')?.addEventListener('click', async () => {
    try {
      await apiFetch('/api/config', { method: 'POST', body: JSON.stringify({ data: collectFormData() }) });
      await apiFetch('/api/start', { method: 'POST' });
      showToast('已保存并开始生成弹幕！');
      navigate('overview');
    } catch (err) {
      showToast(err.message, true);
    }
  });

  document.getElementById('btnProbe')?.addEventListener('click', async () => {
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

  document.getElementById('toggleKey')?.addEventListener('click', () => {
    const inp = document.getElementById('api_key');
    inp.type = inp.type === 'password' ? 'text' : 'password';
  });

  document.getElementById('toggleMicKey')?.addEventListener('click', () => {
    const inp = document.getElementById('mic_api_key');
    if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
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

  document.getElementById('providerPreset')?.addEventListener('change', (e) => {
    if (e.target.value) applyProviderPreset(e.target.value);
    else syncProviderPresetAfterEndpointEdit();
  });

  document.getElementById('api_endpoint')?.addEventListener('change', syncProviderPresetAfterEndpointEdit);
  document.getElementById('api_mode')?.addEventListener('change', () => {
    syncProviderPresetAfterEndpointEdit();
    updateMicModeHint();
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
}
