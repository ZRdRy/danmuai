import { useState } from 'react'
import { useCommunity } from '../../context/CommunityContext'
import { useToast } from '../../context/ToastContext'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

type AuthMode = 'login' | 'register'

interface AuthModalProps {
  open: boolean
  mode: AuthMode
  onClose: () => void
  onModeChange: (mode: AuthMode) => void
}

export function AuthModal({ open, mode, onClose, onModeChange }: AuthModalProps) {
  const { login, register } = useCommunity()
  const { showToast } = useToast()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setUsername('')
    setPassword('')
    setConfirm('')
    setError(null)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (mode === 'login') {
      const err = await login(username, password)
      if (err) {
        setError(err)
        return
      }
      showToast('欢迎回来')
    } else {
      const err = await register(username, password, confirm)
      if (err) {
        setError(err)
        return
      }
      showToast('注册成功')
    }
    handleClose()
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={mode === 'login' ? '登录社区' : '加入社区'}
    >
      <p className="-mt-2 mb-4 text-xs leading-relaxed" style={{ color: 'var(--color-text-dim)' }}>
        请不要使用您的任何正在使用的账户的密码，避免泄露风险。
        {mode === 'register' && ' 请不要在使用时透露您的个人信息'}
      </p>

      <div className="mb-4 flex gap-2 rounded-xl p-1" style={{ background: 'var(--color-surface-alt)' }}>
        <button
          type="button"
          className="flex-1 rounded-lg py-2 text-sm font-semibold transition"
          style={
            mode === 'login'
              ? { background: 'var(--color-surface)', color: 'var(--color-primary)', boxShadow: 'var(--shadow-warm)' }
              : { color: 'var(--color-text-dim)' }
          }
          onClick={() => {
            onModeChange('login')
            setError(null)
          }}
        >
          登录
        </button>
        <button
          type="button"
          className="flex-1 rounded-lg py-2 text-sm font-semibold transition"
          style={
            mode === 'register'
              ? { background: 'var(--color-surface)', color: 'var(--color-primary)', boxShadow: 'var(--shadow-warm)' }
              : { color: 'var(--color-text-dim)' }
          }
          onClick={() => {
            onModeChange('register')
            setError(null)
          }}
        >
          注册
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-semibold">用户名</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-xl border-0 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            style={{
              background: 'var(--color-surface-alt)',
              color: 'var(--color-text)',
            }}
            placeholder="例如：qiaoqiao"
            autoComplete="username"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">密码</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-xl border-0 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            style={{
              background: 'var(--color-surface-alt)',
              color: 'var(--color-text)',
            }}
            placeholder={mode === 'login' ? '原型阶段任意填写' : '至少6位数'}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
        </div>
        {mode === 'register' && (
          <>
            <div>
              <label className="mb-1 block text-sm font-semibold">确认密码</label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full rounded-xl border-0 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                style={{
                  background: 'var(--color-surface-alt)',
                  color: 'var(--color-text)',
                }}
                autoComplete="new-password"
              />
            </div>
            <ul
              className="space-y-1.5 rounded-xl p-3 text-xs leading-relaxed"
              style={{
                background: 'var(--color-accent-bg)',
                color: 'var(--color-text-dim)',
              }}
            >
              <li>· 正式版计划：每天每设备注册一个账户</li>
              <li>· 暂不支持上传头像，大家用同款小圆脸</li>
              <li>· 用户名不可与已有用户重复</li>
            </ul>
          </>
        )}
        {error && <p className="text-sm" style={{ color: 'var(--color-danger-text)' }}>{error}</p>}
        <Button type="submit" variant="primary" className="w-full">
          {mode === 'login' ? '进入社区' : '完成注册'}
        </Button>
        {mode === 'login' && (
          <p className="text-center text-xs" style={{ color: 'var(--color-text-dim)' }}>
            还没有账号？{' '}
            <button
              type="button"
              className="font-semibold underline-offset-2 hover:underline"
              style={{ color: 'var(--color-primary)' }}
              onClick={() => onModeChange('register')}
            >
              去注册
            </button>
          </p>
        )}
      </form>
    </Modal>
  )
}
