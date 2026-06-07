import { isSupabaseConfigured, getSupabaseClient } from '../lib/supabase'
import type { User, UserRole, UserStatus } from '../types/community'
import { MOCK_USERS, usernameExists } from '../mocks/users'
import type { AuthService } from './types'
import { getOrCreateDeviceId } from './deviceId'
import {
  authEmailFromUsername,
  mapAuthError,
  mapRegisterGuardError,
  normalizeUsername,
  validateUsername,
} from './username'

const SESSION_USER_KEY = 'danmu-community-user'

function loadMockSession(): User | null {
  try {
    const raw = sessionStorage.getItem(SESSION_USER_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as User
    if (parsed?.id && parsed?.username) return parsed
  } catch {
    /* ignore */
  }
  return null
}

function mockRoleForUsername(username: string): UserRole {
  if (username === 'admin') return 'admin'
  if (username === 'mod') return 'moderator'
  return 'user'
}

function saveMockSession(user: User | null) {
  try {
    if (user) sessionStorage.setItem(SESSION_USER_KEY, JSON.stringify(user))
    else sessionStorage.removeItem(SESSION_USER_KEY)
  } catch {
    /* ignore */
  }
}

let mockSession: User | null = loadMockSession()
let mockId = 1000

const mockAuthService: AuthService = {
  mode: 'mock',
  async getCurrentUser() {
    return mockSession
  },
  async login(username, _password) {
    const err = validateUsername(username)
    if (err) return err
    const n = normalizeUsername(username)
    const existing = MOCK_USERS.find((u) => u.username === n)
    mockSession = existing ?? {
      id: `u-${++mockId}`,
      username: n,
      role: mockRoleForUsername(n),
      status: 'active',
    }
    if (existing) {
      mockSession = {
        ...existing,
        role: mockRoleForUsername(n),
        status: existing.status ?? 'active',
      }
    }
    saveMockSession(mockSession)
    return null
  },
  async register(username, password, confirm) {
    const err = validateUsername(username)
    if (err) return err
    if (!password) return '请输入密码'
    if (password !== confirm) return '两次密码不一致'
    const n = normalizeUsername(username)
    if (usernameExists(n)) return '用户名已存在'
    mockSession = {
      id: `u-${++mockId}`,
      username: n,
      role: mockRoleForUsername(n),
      status: 'active',
    }
    MOCK_USERS.push(mockSession)
    saveMockSession(mockSession)
    return null
  },
  async logout() {
    mockSession = null
    saveMockSession(null)
  },
}

const supabaseAuthService: AuthService = {
  mode: 'supabase',
  async getCurrentUser() {
    const supabase = getSupabaseClient()
    const { data: sessionData } = await supabase.auth.getSession()
    const uid = sessionData.session?.user?.id
    if (!uid) return null
    const { data, error } = await supabase
      .from('community_profiles')
      .select('user_id, username, role, status')
      .eq('user_id', uid)
      .maybeSingle()
    if (error || !data) return null
    return {
      id: data.user_id,
      username: data.username,
      role: data.role as UserRole,
      status: data.status as UserStatus,
    }
  },
  async login(username, password) {
    const err = validateUsername(username)
    if (err) return err
    if (!password) return '请输入密码'
    const supabase = getSupabaseClient()
    const { error } = await supabase.auth.signInWithPassword({
      email: authEmailFromUsername(username),
      password,
    })
    if (error) return mapAuthError(error.message)
    return null
  },
  async register(username, password, confirm) {
    const err = validateUsername(username)
    if (err) return err
    if (!password) return '请输入密码'
    if (password.length < 6) return '密码至少 6 位'
    if (password !== confirm) return '两次密码不一致'
    const n = normalizeUsername(username)
    const supabase = getSupabaseClient()
    const email = authEmailFromUsername(n)
    const deviceId = getOrCreateDeviceId()

    const { data, error: fnError } = await supabase.functions.invoke(
      'community-register-guard',
      {
        body: { username: n, password, deviceId },
      },
    )

    if (fnError || !data || (data as { ok?: boolean }).ok !== true) {
      return await mapRegisterGuardError(fnError, data)
    }

    const { error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    if (signInError) {
      return '注册成功，请使用用户名和密码登录'
    }
    return null
  },
  async logout() {
    const supabase = getSupabaseClient()
    await supabase.auth.signOut()
  },
}

export function getAuthService(): AuthService {
  return isSupabaseConfigured ? supabaseAuthService : mockAuthService
}
