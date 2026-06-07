type Size = 'sm' | 'md' | 'lg'

const sizes: Record<Size, number> = { sm: 28, md: 36, lg: 48 }

export function DefaultAvatar({ size = 'md' }: { size?: Size }) {
  const px = sizes[size]
  return (
    <svg
      width={px}
      height={px}
      viewBox="0 0 48 48"
      aria-hidden="true"
      className="shrink-0"
    >
      <circle cx="24" cy="24" r="24" fill="#FFE5D9" />
      <circle cx="17" cy="20" r="3" fill="#FFA5A5" />
      <circle cx="31" cy="20" r="3" fill="#FFA5A5" />
      <path
        d="M16 30c3 3 13 3 16 0"
        stroke="#FFA5A5"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  )
}
