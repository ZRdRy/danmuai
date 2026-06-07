import { useState } from 'react'
import { useCommunity } from '../../context/CommunityContext'
import { useToast } from '../../context/ToastContext'
import {
  CATEGORY_LABELS,
  type PostCategoryKey,
} from '../../types/community'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

const CATEGORIES = Object.entries(CATEGORY_LABELS) as [PostCategoryKey, string][]

interface CreatePostModalProps {
  open: boolean
  onClose: () => void
}

export function CreatePostModal({ open, onClose }: CreatePostModalProps) {
  const { addPost, currentUser } = useCommunity()
  const { showToast } = useToast()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [category, setCategory] = useState<PostCategoryKey>('experience')
  const [tagsInput, setTagsInput] = useState('')
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setTitle('')
    setBody('')
    setCategory('experience')
    setTagsInput('')
    setError(null)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const tags = tagsInput
      .split(/[,，\s]+/)
      .map((t) => t.trim())
      .filter(Boolean)
    const err = await addPost({ title, body, category, tags })
    if (err) {
      setError(err)
      return
    }
    showToast('发布成功')
    handleClose()
  }

  return (
    <Modal open={open} onClose={handleClose} title="发布帖子">
      {!currentUser && (
        <p
          className="-mt-2 mb-4 rounded-xl px-3 py-2 text-xs"
          style={{ background: 'var(--color-accent-bg)', color: 'var(--color-text-dim)' }}
        >
          发帖前请先登录；当前为原型，登录后即可体验发布流程。
        </p>
      )}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-semibold">标题</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-xl border-0 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            style={{
              background: 'var(--color-surface-alt)',
              color: 'var(--color-text)',
            }}
            placeholder="写一个吸引人的标题"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">正文</label>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={6}
            className="w-full resize-y rounded-xl border-0 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            style={{
              background: 'var(--color-surface-alt)',
              color: 'var(--color-text)',
            }}
            placeholder="分享提示词、配置心得或遇到的问题…"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">分类</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as PostCategoryKey)}
            className="w-full rounded-xl border-0 px-4 py-3 text-sm outline-none"
            style={{
              background: 'var(--color-surface-alt)',
              color: 'var(--color-text)',
            }}
          >
            {CATEGORIES.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">标签（可选）</label>
          <input
            type="text"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            className="w-full rounded-xl border-0 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            style={{
              background: 'var(--color-surface-alt)',
              color: 'var(--color-text)',
            }}
            placeholder="多个标签用逗号分隔，例如：MiMo, 人格"
          />
        </div>
        <div
          className="flex gap-2 rounded-xl px-3 py-2.5 text-xs leading-relaxed"
          style={{
            background: 'var(--color-surface-alt)',
            border: '1px dashed var(--color-border)',
            color: 'var(--color-text-dim)',
          }}
        >
          <span aria-hidden="true">ℹ️</span>
          <span>
            发布后暂不支持修改正文；若写错了，可以删除后重新发帖。
          </span>
        </div>
        {error && <p className="text-sm" style={{ color: 'var(--color-danger-text)' }}>{error}</p>}
        <Button type="submit" variant="primary" className="w-full !py-3">
          发布到社区
        </Button>
      </form>
    </Modal>
  )
}
