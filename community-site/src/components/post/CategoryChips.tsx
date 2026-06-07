import { CATEGORY_FILTERS, type PostCategoryFilter } from '../../types/community'

interface CategoryChipsProps {
  value: PostCategoryFilter
  onChange: (v: PostCategoryFilter) => void
}

export function CategoryChips({ value, onChange }: CategoryChipsProps) {
  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 scrollbar-none">
      {CATEGORY_FILTERS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className="shrink-0 rounded-xl px-3 py-1.5 text-sm font-semibold transition"
          style={
            value === key
              ? {
                  background: 'var(--color-accent-bg)',
                  color: 'var(--color-primary-hover)',
                }
              : {
                  background: 'var(--color-surface)',
                  color: 'var(--color-text-dim)',
                  boxShadow: 'inset 0 0 0 1px var(--color-border)',
                }
          }
        >
          {label}
        </button>
      ))}
    </div>
  )
}
