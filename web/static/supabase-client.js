/** Thin PostgREST client for DanmuAI announcements and feedback. */
(function initDanmuSupabase(global) {
  const STORAGE_CLIENT_ID = 'danmu_feedback_client_id';
  const FEEDBACK_RATE_LIMIT_MSG = '每 3 小时最多提交 2 条反馈，请稍后再试';
  const APP_VERSION = '2026.05.27';

  function config() {
    const cfg = global.DANMU_SUPABASE;
    if (!cfg || !cfg.url || !cfg.anonKey) return null;
    const url = String(cfg.url).replace(/\/$/, '');
    const anonKey = String(cfg.anonKey).trim();
    if (!url || !anonKey || url.includes('YOUR_PROJECT')) return null;
    return { url, anonKey };
  }

  function isConfigured() {
    return config() !== null;
  }

  function authHeaders(extra) {
    const cfg = config();
    if (!cfg) throw new Error('未配置 Supabase，请复制 supabase-config.example.js 为 supabase-config.js');
    return {
      apikey: cfg.anonKey,
      Authorization: `Bearer ${cfg.anonKey}`,
      'Content-Type': 'application/json',
      ...extra,
    };
  }

  function getOrCreateClientId() {
    try {
      let id = global.localStorage.getItem(STORAGE_CLIENT_ID);
      if (id && /^[0-9a-f-]{36}$/i.test(id)) return id;
      id = global.crypto?.randomUUID?.() || null;
      if (!id) {
        id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
          const r = (Math.random() * 16) | 0;
          const v = c === 'x' ? r : (r & 0x3) | 0x8;
          return v.toString(16);
        });
      }
      global.localStorage.setItem(STORAGE_CLIENT_ID, id);
      return id;
    } catch {
      return '00000000-0000-4000-8000-000000000000';
    }
  }

  function parseErrorMessage(res, bodyText) {
    const text = bodyText || '';
    if (
      res.status === 403 ||
      res.status === 401 ||
      /row-level security/i.test(text) ||
      /policy/i.test(text)
    ) {
      if (/feedback/i.test(text) || res.url?.includes('/feedback')) {
        return FEEDBACK_RATE_LIMIT_MSG;
      }
    }
    try {
      const parsed = JSON.parse(text);
      const msg = parsed.message || parsed.error || parsed.hint || parsed.details;
      if (msg) return String(msg);
    } catch {
      /* ignore */
    }
    return text || `请求失败（HTTP ${res.status}）`;
  }

  async function supabaseFetch(path, options = {}) {
    const cfg = config();
    if (!cfg) throw new Error('未配置 Supabase');
    const res = await global.fetch(`${cfg.url}${path}`, {
      ...options,
      headers: authHeaders(options.headers),
    });
    if (!res.ok) {
      const text = await res.text();
      const err = new Error(parseErrorMessage(res, text));
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    const text = await res.text();
    if (!text) return null;
    return JSON.parse(text);
  }

  async function listAnnouncements() {
    const query =
      '/rest/v1/announcements?select=id,title,body,level,pinned,created_at,starts_at,ends_at' +
      '&order=pinned.desc,created_at.desc';
    return supabaseFetch(query, { method: 'GET' });
  }

  async function getFeedbackQuota() {
    const clientId = getOrCreateClientId();
    return supabaseFetch('/rest/v1/rpc/feedback_quota', {
      method: 'POST',
      headers: { Prefer: 'return=representation' },
      body: JSON.stringify({ p_client_id: clientId }),
    });
  }

  async function submitFeedback({ content, contact }) {
    const trimmed = String(content || '').trim();
    if (!trimmed) throw new Error('请填写反馈内容');
    if (trimmed.length > 2000) throw new Error('反馈内容不能超过 2000 字');
    const contactVal = String(contact || '').trim();
    if (contactVal.length > 200) throw new Error('联系方式不能超过 200 字');

    const clientId = getOrCreateClientId();
    try {
      await supabaseFetch('/rest/v1/feedback', {
        method: 'POST',
        headers: { Prefer: 'return=minimal' },
        body: JSON.stringify({
          content: trimmed,
          contact: contactVal || null,
          client_id: clientId,
          app_version: APP_VERSION,
          platform: 'windows',
          locale: global.navigator?.language || 'zh-CN',
        }),
      });
    } catch (err) {
      if (err.status === 403 || err.status === 401) {
        throw new Error(FEEDBACK_RATE_LIMIT_MSG);
      }
      throw err;
    }
  }

  global.DanmuSupabase = {
    APP_VERSION,
    FEEDBACK_RATE_LIMIT_MSG,
    isConfigured,
    getOrCreateClientId,
    listAnnouncements,
    getFeedbackQuota,
    submitFeedback,
  };
})(typeof window !== 'undefined' ? window : globalThis);
