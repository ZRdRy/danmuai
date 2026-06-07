interface EmptyStateProps {
  message: string
  hint?: string
}

export function EmptyState({ message, hint }: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-3xl py-16 text-center"
      style={{ background: 'var(--color-surface-alt)' }}
    >
      <svg
        width="80"
        height="80"
        viewBox="0 0 80 80"
        className="mb-4 opacity-80"
        aria-hidden="true"
      >
        <circle cx="40" cy="40" r="36" fill="var(--color-soft-peach)" />
        <path
          d="M28 48h24M32 32h.01M48 32h.01"
          stroke="var(--color-primary)"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
      <p className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
        {message}
      </p>
      <p className="mt-2 max-w-xs text-sm leading-relaxed" style={{ color: 'var(--color-text-dim)' }}>
        {hint ?? '试试换个关键词或分类吧'}
      </p>
    </div>
  )
}
