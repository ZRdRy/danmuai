import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  children: ReactNode
}

const variantClass: Record<Variant, string> = {
  primary:
    'bg-[var(--color-primary)] text-white hover:opacity-95 active:scale-[0.98] disabled:opacity-50',
  secondary:
    'bg-[var(--color-surface)] border text-[var(--color-text)] hover:bg-[var(--color-surface-alt)]',
  ghost:
    'bg-transparent text-[var(--color-primary)] hover:bg-[var(--color-accent-bg)]',
  danger: 'hover:opacity-90 active:scale-[0.98]',
}

export function Button({
  variant = 'primary',
  className = '',
  children,
  style,
  ...props
}: ButtonProps) {
  const dangerStyle =
    variant === 'danger'
      ? {
          background: 'var(--color-danger-bg)',
          color: 'var(--color-danger-text)',
          ...style,
        }
      : style

  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${variantClass[variant]} ${className}`}
      style={
        variant === 'secondary'
          ? { borderColor: 'var(--color-border)', ...dangerStyle }
          : dangerStyle
      }
      {...props}
    >
      {children}
    </button>
  )
}
