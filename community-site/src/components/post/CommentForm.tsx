import { useState } from 'react'
import { useCommunity } from '../../context/CommunityContext'
import { Button } from '../ui/Button'

interface CommentFormProps {
  onSubmit: (body: string) => Promise<string | null> | string | null
  onSuccess: () => void
  onRequestLogin?: () => void
}

export function CommentForm({ onSubmit, onSuccess, onRequestLogin }: CommentFormProps) {
  const { currentUser } = useCommunity()
  const [body, setBody] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const err = await onSubmit(body)
    if (err) {
      setError(err)
      if (err.includes('登录') && onRequestLogin) onRequestLogin()
      return
    }
    setBody('')
    setError(null)
    onSuccess()
  }

  if (!currentUser) {
    return (
      <div
        className="mt-4 rounded-2xl px-4 py-5 text-center text-sm"
        style={{ background: 'var(--color-surface-alt)' }}
      >
        <p className="mb-3" style={{ color: 'var(--color-text-dim)' }}>
          登录后即可参与评论
        </p>
        {onRequestLogin && (
          <Button variant="primary" onClick={onRequestLogin}>
            去登录
          </Button>
        )}
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4">
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="写下你的评论…"
        rows={3}
        className="w-full resize-y rounded-xl border-0 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
        style={{
          background: 'var(--color-surface-alt)',
          color: 'var(--color-text)',
        }}
      />
      {error && (
        <p className="mt-2 text-sm" style={{ color: 'var(--color-danger-text)' }}>
          {error}
        </p>
      )}
      <Button type="submit" variant="primary" className="mt-3">
        发布评论
      </Button>
    </form>
  )
}
