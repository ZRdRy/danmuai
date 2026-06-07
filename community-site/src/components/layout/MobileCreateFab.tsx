interface MobileCreateFabProps {
  onClick: () => void
}

export function MobileCreateFab({ onClick }: MobileCreateFabProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="fixed bottom-6 right-4 z-30 flex h-14 w-14 items-center justify-center rounded-full text-white shadow-lg transition active:scale-95 md:hidden"
      style={{
        background: 'var(--color-primary)',
        boxShadow: 'var(--shadow-btn)',
      }}
      aria-label="发帖"
    >
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
        <path d="M12 5v14M5 12h14" strokeLinecap="round" />
      </svg>
    </button>
  )
}
