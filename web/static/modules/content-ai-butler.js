import { apiFetch } from './transport.js';
import { MASKED_API_KEY, reloadConfigFromServer } from './settings.js';

const AI_BUTLER_STATE = {
  messages: [],
  pendingPatch: null,
  pendingReasons: null,
  pendingCurrent: null,
  sending: false,
};

const AI_BUTLER_FIELD_LABELS = {
  temperature: '创意程度 (temperature)',
  max_tokens: '输出 token 上限',
  danmu_speed: '弹幕速度',
  danmu_lines: '弹幕行数',
  danmu_max_chars: '单条字数上限',
  dedup_threshold: '去重阈值',
  layout_mode: '显示区域',
  opacity: '透明度',
  font_size: '字号',
  eviction_mode: '退场模式',
  empty_accel: '空轨道加速',
  image_max_width: '截图最大宽度',
  image_quality: 'JPEG 质量',
  memory_mode: '记忆模式',
  memory_window: '记忆窗口',
  normal_recognition_interval_sec: '识图间隔（秒）',
  normal_reply_count: '每批弹幕条数',
};

let showToast = () => {};
let navigate = () => {};

export function configureAiButlerBindings(deps = {}) {
  showToast = deps.showToast || showToast;
  navigate = deps.navigate || navigate;
}

function aiButlerFieldLabel(key) {
  return AI_BUTLER_FIELD_LABELS[key] || key;
}

function appendAiButlerMessage(role, text) {
  const box = document.getElementById('aiButlerMessages');
  if (!box) return;
  const row = document.createElement('div');
  row.className =
    role === 'user' ? 'ai-butler-msg ai-butler-msg-user' : 'ai-butler-msg ai-butler-msg-assistant';
  const bubble = document.createElement('div');
  bubble.className = 'ai-butler-msg-bubble';
  bubble.textContent = text;
  row.appendChild(bubble);
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

function showAiButlerThinking() {
  removeAiButlerThinking();
  const box = document.getElementById('aiButlerMessages');
  if (!box) return;
  const row = document.createElement('div');
  row.id = 'aiButlerThinkingRow';
  row.className = 'ai-butler-msg ai-butler-msg-assistant ai-butler-msg-thinking';
  row.setAttribute('aria-busy', 'true');
  const bubble = document.createElement('div');
  bubble.className = 'ai-butler-msg-bubble ai-butler-thinking-bubble';
  bubble.textContent = '正在思考中…';
  row.appendChild(bubble);
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

function removeAiButlerThinking() {
  document.getElementById('aiButlerThinkingRow')?.remove();
}

function setAiButlerInputBusy(busy) {
  const input = document.getElementById('aiButlerInput');
  const sendBtn = document.getElementById('btnAiButlerSend');
  if (input) input.disabled = busy;
  if (sendBtn) {
    sendBtn.disabled = busy;
    sendBtn.textContent = busy ? '思考中…' : '发送';
  }
}

function clearAiButlerSuggestionPanel() {
  AI_BUTLER_STATE.pendingPatch = null;
  AI_BUTLER_STATE.pendingReasons = null;
  AI_BUTLER_STATE.pendingCurrent = null;
  const panel = document.getElementById('aiButlerSuggestionPanel');
  const body = document.getElementById('aiButlerPatchBody');
  const hint = document.getElementById('aiButlerDiscardedHint');
  if (body) body.replaceChildren();
  if (hint) {
    hint.textContent = '';
    hint.classList.add('hidden');
  }
  panel?.classList.add('hidden');
}

function renderAiButlerSuggestion(data) {
  const patch = data.patch || {};
  const keys = Object.keys(patch);
  if (!keys.length) {
    clearAiButlerSuggestionPanel();
    return;
  }
  AI_BUTLER_STATE.pendingPatch = { ...patch };
  AI_BUTLER_STATE.pendingReasons = { ...(data.reasons || {}) };
  AI_BUTLER_STATE.pendingCurrent = { ...(data.current_values || {}) };

  const body = document.getElementById('aiButlerPatchBody');
  if (!body) return;
  body.replaceChildren();
  keys.forEach((key) => {
    const tr = document.createElement('tr');
    const cells = [
      aiButlerFieldLabel(key),
      String(AI_BUTLER_STATE.pendingCurrent[key] ?? '-'),
      String(patch[key] ?? ''),
      String((data.reasons && data.reasons[key]) || '-'),
    ];
    cells.forEach((text) => {
      const td = document.createElement('td');
      td.className = 'py-2 pr-3 align-top';
      td.textContent = text;
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });

  const discarded = data.discarded_fields || [];
  const hint = document.getElementById('aiButlerDiscardedHint');
  if (hint && discarded.length) {
    hint.textContent = `已忽略不允许修改的字段：${discarded.join('、')}`;
    hint.classList.remove('hidden');
  } else if (hint) {
    hint.classList.add('hidden');
  }

  document.getElementById('aiButlerSuggestionPanel')?.classList.remove('hidden');
}

async function updateAiButlerApiHint() {
  const hint = document.getElementById('aiButlerApiHint');
  if (!hint) return;
  try {
    const cfg = await apiFetch('/api/config');
    const hasKey = cfg.api_key === MASKED_API_KEY || Boolean((cfg.api_key || '').trim());
    const hasModel = Boolean((cfg.model || '').trim());
    const hasEndpoint = Boolean((cfg.api_endpoint || '').trim());
    if (hasKey && hasModel && hasEndpoint) {
      hint.classList.add('hidden');
    } else {
      hint.classList.remove('hidden');
    }
  } catch {
    hint.classList.remove('hidden');
  }
}

async function sendAiButlerMessage() {
  if (AI_BUTLER_STATE.sending) return;
  const input = document.getElementById('aiButlerInput');
  const text = (input?.value || '').trim();
  if (!text) {
    showToast('请输入消息', true);
    return;
  }

  AI_BUTLER_STATE.sending = true;
  setAiButlerInputBusy(true);
  clearAiButlerSuggestionPanel();
  appendAiButlerMessage('user', text);
  AI_BUTLER_STATE.messages.push({ role: 'user', content: text });
  if (input) input.value = '';
  showAiButlerThinking();

  try {
    const history = AI_BUTLER_STATE.messages.slice(0, -1).slice(-20);
    const data = await apiFetch('/api/ai-butler/chat', {
      method: 'POST',
      body: JSON.stringify({ message: text, history }),
    });
    removeAiButlerThinking();
    const reply = data.reply || '（无回复）';
    appendAiButlerMessage('assistant', reply);
    AI_BUTLER_STATE.messages.push({ role: 'assistant', content: reply });
    renderAiButlerSuggestion(data);
    await updateAiButlerApiHint();
  } catch (err) {
    removeAiButlerThinking();
    appendAiButlerMessage('assistant', err.message || '请求失败');
    showToast(err.message || 'AI 管家请求失败', true);
  } finally {
    AI_BUTLER_STATE.sending = false;
    setAiButlerInputBusy(false);
  }
}

async function applyAiButlerPatch() {
  const patch = AI_BUTLER_STATE.pendingPatch;
  if (!patch || !Object.keys(patch).length) {
    showToast('没有可应用的配置建议', true);
    return;
  }
  const applyBtn = document.getElementById('btnAiButlerApply');
  if (applyBtn) applyBtn.disabled = true;
  try {
    await apiFetch('/api/config', {
      method: 'POST',
      body: JSON.stringify({ data: patch }),
    });
    await reloadConfigFromServer();
    clearAiButlerSuggestionPanel();
    showToast('配置已应用并同步到助手设置~');
  } catch (err) {
    showToast(err.message || '保存配置失败', true);
  } finally {
    if (applyBtn) applyBtn.disabled = false;
  }
}

export function initAiButlerPage() {
  updateAiButlerApiHint().catch(console.error);
}

export function bindAiButlerControls() {
  document.getElementById('btnAiButlerSend')?.addEventListener('click', () => {
    sendAiButlerMessage().catch(console.error);
  });
  document.getElementById('aiButlerInput')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendAiButlerMessage().catch(console.error);
    }
  });
  document.getElementById('btnAiButlerApply')?.addEventListener('click', () => {
    applyAiButlerPatch().catch(console.error);
  });
  document.getElementById('btnAiButlerCancel')?.addEventListener('click', () => {
    clearAiButlerSuggestionPanel();
    showToast('已取消配置建议');
  });
  document.getElementById('btnAiButlerGoSettings')?.addEventListener('click', () => {
    navigate('settings');
  });
}
