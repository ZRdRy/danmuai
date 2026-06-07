import type { Comment, Post } from '../../types/community'
import { formatRelativeTime } from '../../utils/formatTime'
import { DefaultAvatar } from '../icons/DefaultAvatar'
import { Button } from '../ui/Button'

interface CommentItemProps {
  comment: Comment
  post: Post
  currentUserId: string | undefined
  onDeleteRequest: () => void
  onReportRequest?: () => void
}

export function CommentItem({
  comment,
  post,
  currentUserId,
  onDeleteRequest,
  onReportRequest,
}: CommentItemProps) {
  const isAuthor = currentUserId === comment.authorId
  const isPostOwner = currentUserId === post.authorId
  const canDelete = isAuthor || isPostOwner

  return (
    <div
      className="flex gap-3 rounded-2xl p-4"
      style={{ background: 'var(--color-surface-alt)' }}
    >
      <DefaultAvatar size="sm" />
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold">{comment.authorName}</span>
          {isPostOwner && comment.authorId !== post.authorId && (
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
              style={{ background: 'var(--color-accent-bg)', color: 'var(--color-primary)' }}
            >
              帖主可见管理
            </span>
          )}
          <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
            {formatRelativeTime(comment.createdAt)}
          </span>
        </div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{comment.body}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {canDelete && currentUserId && (
            <Button
              variant="danger"
              className="!px-3 !py-1 text-xs"
              onClick={onDeleteRequest}
            >
              删除评论
            </Button>
          )}
          {onReportRequest && currentUserId && !isAuthor && (
            <Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={onReportRequest}>
              举报
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
