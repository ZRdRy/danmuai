export const AUTH_EMAIL_DOMAIN = 'danmuai.test'

const USERNAME_RE = /^[a-z0-9_]{3,24}$/

export function normalizeUsername(raw: string): string {
  return raw.trim().toLowerCase()
}

export function validateUsername(raw: string): string | null {
  const n = normalizeUsername(raw)
  if (!n) return '请输入用户名'
  if (!USERNAME_RE.test(n)) {
    return '用户名为 3–24 位小写字母、数字或下划线'
  }
  return null
}

export function authEmailFromUsername(username: string): string {
  const n = normalizeUsername(username)
  return `${n}@${AUTH_EMAIL_DOMAIN}`
}

export function mapAuthError(message: string): string {
  const m = message.toLowerCase()
  if (
    m.includes('email logins are disabled') ||
    m.includes('email_provider_disabled')
  ) {
    return 'Supabase 已关闭 Email 登录。请在 Dashboard → Authentication → Providers → Email 保持开启（仅关闭 Sign up / Confirm email），否则无法登录。'
  }
  if (m.includes('invalid login') || m.includes('invalid credentials')) {
    return '用户名或密码错误'
  }
  if (m.includes('already registered') || m.includes('already exists')) {
    return '用户名已存在'
  }
  if (m.includes('password')) return '密码不符合要求'
  if (message.includes('今天已经注册过')) return message
  if (
    m.includes('email rate limit') ||
    m.includes('over_email_send_rate_limit') ||
    m.includes('rate limit exceeded')
  ) {
    return '认证邮件发送过于频繁（Supabase 默认约 2 封/小时）。请约 1 小时后再注册，或在 Supabase 控制台关闭「Confirm email」/ 配置自定义 SMTP 后重试。'
  }
  if (m.includes('edge function') || m.includes('failed to fetch')) {
    return '注册服务暂时不可用，请稍后重试'
  }
  return message
}

type InvokeError = { message?: string; context?: Response }

function errorFromPayload(data: unknown): string | null {
  if (data && typeof data === 'object' && typeof (data as { error?: string }).error === 'string') {
    return mapAuthError((data as { error: string }).error)
  }
  return null
}

/** Parse Edge Function response (including non-2xx HTTP). */
export async function mapRegisterGuardError(
  error: InvokeError | null,
  data: unknown,
): Promise<string> {
  const fromData = errorFromPayload(data)
  if (fromData) return fromData

  if (!error) return '注册失败，请稍后重试'

  const ctx = error.context
  if (ctx && typeof ctx.json === 'function') {
    try {
      const body = await ctx.json()
      const fromBody = errorFromPayload(body)
      if (fromBody) return fromBody
    } catch {
      /* ignore */
    }
  }

  if (error.message) return mapAuthError(error.message)
  return '注册失败，请稍后重试'
}
