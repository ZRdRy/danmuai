export function PostListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="skeleton rounded-3xl p-6"
          style={{ background: 'var(--color-surface-alt)', minHeight: 140 }}
        />
      ))}
    </div>
  )
}
