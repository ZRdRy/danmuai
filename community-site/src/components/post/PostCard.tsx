import { Link } from 'react-router-dom'
import { CATEGORY_LABELS, type Post } from '../../types/community'
import { formatRelativeTime } from '../../utils/formatTime'
import { DefaultAvatar } from '../icons/DefaultAvatar'

interface PostCardProps {
  post: Post & { likedByMe?: boolean }
}

export function PostCard({ post }: PostCardProps) {
  return (
    <Link
      to={`/post/${post.id}`}
      className="group block rounded-3xl p-5 no-underline transition hover:-translate-y-0.5 sm:p-6"
      style={{
        background: 'var(--color-surface)',
        color: 'var(--color-text)',
        boxShadow: 'var(--shadow-warm)',
      }}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="rounded-lg px-2.5 py-1 text-xs font-bold"
            style={{
              background: 'var(--color-soft-peach)',
              color: 'var(--color-primary-hover)',
            }}
          >
            {CATEGORY_LABELS[post.category]}
          </span>
          {post.isFeatured && (
            <span
              className="rounded-lg px-2 py-0.5 text-xs font-semibold"
              style={{ background: 'var(--color-accent-bg)', color: 'var(--color-primary)' }}
            >
              精华
            </span>
          )}
        </div>
        <div
          className="flex shrink-0 items-center gap-3 text-sm font-semibold"
          style={{ color: 'var(--color-text-dim)' }}
        >
          <span
            className="flex items-center gap-1"
            style={post.likedByMe ? { color: 'var(--color-primary)' } : undefined}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill={post.likedByMe ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
            {post.likeCount}
          </span>
          <span className="flex items-center gap-1">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z" />
            </svg>
            {post.commentCount}
          </span>
        </div>
      </div>

      <h3 className="mb-2 text-lg font-bold leading-snug group-hover:text-[var(--color-primary-hover)]">
        {post.title}
      </h3>
      <p
        className="mb-4 line-clamp-2 text-sm leading-relaxed"
        style={{ color: 'var(--color-text-dim)' }}
      >
        {post.excerpt}
      </p>

      {post.tags.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {post.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="rounded-md px-2 py-0.5 text-xs"
              style={{ background: 'var(--color-surface-alt)', color: 'var(--color-text-dim)' }}
            >
              #{tag}
            </span>
          ))}
          {post.tags.length > 4 && (
            <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
              +{post.tags.length - 4}
            </span>
          )}
        </div>
      )}

      <div
        className="flex items-center gap-2 border-t pt-3 text-sm"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <DefaultAvatar size="sm" />
        <span className="font-bold">{post.authorName}</span>
        <span style={{ color: 'var(--color-text-dim)' }}>
          {formatRelativeTime(post.createdAt)}
        </span>
      </div>
    </Link>
  )
}
