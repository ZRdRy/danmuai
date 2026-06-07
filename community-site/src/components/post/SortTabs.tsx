import { SORT_OPTIONS, type SortKind } from '../../types/community'

interface SortTabsProps {
  value: SortKind
  onChange: (v: SortKind) => void
}

export function SortTabs({ value, onChange }: SortTabsProps) {
  return (
    <div className="flex gap-1 rounded-xl p-1" style={{ background: 'var(--color-surface-alt)' }}>
      {SORT_OPTIONS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className="rounded-lg px-4 py-1.5 text-sm font-semibold transition"
          style={
            value === key
              ? {
                  background: 'var(--color-surface)',
                  color: 'var(--color-primary)',
                  boxShadow: 'var(--shadow-warm)',
                }
              : { color: 'var(--color-text-dim)' }
          }
        >
          {label}
        </button>
      ))}
    </div>
  )
}
