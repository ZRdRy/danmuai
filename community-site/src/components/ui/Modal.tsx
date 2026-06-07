import { useEffect, type ReactNode } from 'react'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

export function Modal({ open, onClose, title, children }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <button
        type="button"
        className="absolute inset-0 backdrop-blur-sm"
        style={{ background: 'var(--color-overlay)' }}
        aria-label="关闭"
        onClick={onClose}
      />
      <div
        className="relative z-10 w-full max-w-md rounded-3xl p-6 shadow-lg"
        style={{
          background: 'var(--color-surface)',
          boxShadow: 'var(--shadow-warm-hover)',
        }}
      >
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2
            id="modal-title"
            className="text-lg font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-xl leading-none opacity-60 hover:opacity-100"
            aria-label="关闭"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
