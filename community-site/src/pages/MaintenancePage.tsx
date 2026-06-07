const DEFAULT_MESSAGE = '社区正在进化中，非常抱歉'

type MaintenancePageProps = {
  message?: string
}

export function MaintenancePage({ message = DEFAULT_MESSAGE }: MaintenancePageProps) {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center px-6 py-16 text-center"
      style={{ background: 'var(--color-bg)' }}
    >
      <div
        className="w-full max-w-md rounded-3xl px-8 py-10"
        style={{
          background:
            'linear-gradient(135deg, var(--color-surface) 0%, var(--color-surface-alt) 100%)',
          boxShadow: 'var(--shadow-warm)',
          border: '1px solid var(--color-border)',
        }}
      >
        <p
          className="mb-2 text-xs font-semibold uppercase tracking-wide"
          style={{ color: 'var(--color-primary)' }}
        >
          DanmuAI 社区
        </p>
        <h1 className="mb-4 text-2xl font-bold leading-snug sm:text-3xl">{message}</h1>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-dim)' }}>
          我们正在打磨更好的分享与互助体验，请稍后再来。
        </p>
      </div>
    </div>
  )
}
