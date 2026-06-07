import { COMMUNITY_RULES, COMMUNITY_RULES_INTRO } from '../../types/community'

function RulesList() {
  return (
    <ul className="space-y-3 text-sm" style={{ color: 'var(--color-text)' }}>
      {COMMUNITY_RULES.map((rule, i) => (
        <li key={i} className="flex gap-2 leading-relaxed">
          <span
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold"
            style={{
              background: 'var(--color-accent-bg)',
              color: 'var(--color-primary)',
            }}
          >
            {i + 1}
          </span>
          <span>{rule}</span>
        </li>
      ))}
    </ul>
  )
}

export function RulesSidebar({ className = '' }: { className?: string }) {
  return (
    <aside
      className={`rounded-3xl p-6 ${className}`}
      style={{
        background: 'var(--color-surface)',
        boxShadow: 'var(--shadow-warm)',
      }}
    >
      <h2
        className="mb-2 flex items-center gap-2 text-lg font-bold"
        style={{ color: 'var(--color-text)' }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            style={{ color: 'var(--color-primary)' }}
          />
        </svg>
        社区小贴士
      </h2>
      <p className="mb-4 text-xs leading-relaxed" style={{ color: 'var(--color-text-dim)' }}>
        {COMMUNITY_RULES_INTRO}
      </p>
      <RulesList />
    </aside>
  )
}

export function RulesAccordion() {
  return (
    <details
      className="rounded-3xl lg:hidden"
      style={{
        background: 'var(--color-surface)',
        boxShadow: 'var(--shadow-warm)',
      }}
    >
      <summary
        className="cursor-pointer list-none px-6 py-4 font-bold [&::-webkit-details-marker]:hidden"
        style={{ color: 'var(--color-text)' }}
      >
        社区小贴士 ▾
      </summary>
      <div
        className="border-t px-6 pb-4 pt-2"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <p className="mb-3 text-xs leading-relaxed" style={{ color: 'var(--color-text-dim)' }}>
          {COMMUNITY_RULES_INTRO}
        </p>
        <RulesList />
      </div>
    </details>
  )
}
