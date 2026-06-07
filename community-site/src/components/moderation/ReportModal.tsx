import { useState } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'

interface ReportModalProps {
  open: boolean
  title: string
  onClose: () => void
  onSubmit: (reason: string) => Promise<string | null>
  onSuccess: () => void
}

export function ReportModal({
  open,
  title,
  onClose,
  onSubmit,
  onSuccess,
}: ReportModalProps) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleClose = () => {
    setReason('')
    setError(null)
    onClose()
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)
    const err = await onSubmit(reason.trim())
    setSubmitting(false)
    if (err) {
      setError(err)
      return
    }
    setReason('')
    onSuccess()
    onClose()
  }

  return (
    <Modal open={open} title={title} onClose={handleClose}>
      <p className="mb-3 text-sm" style={{ color: 'var(--color-text-dim)' }}>
        可选填写举报原因，管理员将在处理台查看。
      </p>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="例如：广告、辱骂、无关内容…（可选）"
        maxLength={500}
        rows={4}
        className="mb-3 w-full resize-none rounded-xl border-0 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
        style={{
          background: 'var(--color-surface-alt)',
          color: 'var(--color-text)',
          boxShadow: 'inset 0 0 0 1px var(--color-border)',
        }}
      />
      {error && (
        <p className="mb-3 text-sm font-semibold" style={{ color: 'var(--color-danger)' }}>
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={handleClose} disabled={submitting}>
          取消
        </Button>
        <Button variant="primary" onClick={() => void handleSubmit()} disabled={submitting}>
          {submitting ? '提交中…' : '提交举报'}
        </Button>
      </div>
    </Modal>
  )
}
