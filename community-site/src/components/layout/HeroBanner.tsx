export function HeroBanner() {
  return (
    <section
      className="mb-6 rounded-3xl px-5 py-6 sm:px-8 sm:py-7"
      style={{
        background:
          'linear-gradient(135deg, var(--color-surface) 0%, var(--color-surface-alt) 100%)',
        boxShadow: 'var(--shadow-warm)',
        border: '1px solid var(--color-border)',
      }}
    >
      <p
        className="mb-1 text-xs font-semibold uppercase tracking-wide sm:text-sm"
        style={{ color: 'var(--color-primary)' }}
      >
        DanmuAI 社区
      </p>
      <h1 className="text-xl font-bold leading-snug sm:text-2xl">
        分享提示词、配置、经验与问题
      </h1>
    </section>
  )
}
