import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useCommunity } from '../context/CommunityContext'
import { useToast } from '../context/ToastContext'
import { usePageLoading } from '../hooks/usePageLoading'
import { Header } from '../components/layout/Header'
import { MobileCreateFab } from '../components/layout/MobileCreateFab'
import { AuthModal } from '../components/auth/AuthModal'
import { CreatePostModal } from '../components/create/CreatePostModal'
import { CommentForm } from '../components/post/CommentForm'
import { CommentItem } from '../components/post/CommentItem'
import { DefaultAvatar } from '../components/icons/DefaultAvatar'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { EmptyState } from '../components/ui/EmptyState'
import { PostListSkeleton } from '../components/ui/PostListSkeleton'
import { CATEGORY_LABELS } from '../types/community'
import { formatDateTime } from '../utils/formatTime'
import { ReportModal } from '../components/moderation/ReportModal'
import { getModerationService } from '../services/moderationService'

interface PostDetailPageProps {
  search: string
  onSearchChange: (v: string) => void
}

type ConfirmState =
  | { type: 'post' }
  | { type: 'comment'; commentId: string }
  | null

type ReportState =
  | { type: 'post' }
  | { type: 'comment'; commentId: string }
  | null

export function PostDetailPage({ search, onSearchChange }: PostDetailPageProps) {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const {
    getPost,
    getCommentsForPost,
    currentUser,
    toggleLike,
    isPostLiked,
    deletePost,
    deleteComment,
    addComment,
    loadCommentsForPost,
    dataSource,
  } = useCommunity()
  const { showToast } = useToast()
  const loading = usePageLoading()
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [createOpen, setCreateOpen] = useState(false)
  const [confirm, setConfirm] = useState<ConfirmState>(null)
  const [report, setReport] = useState<ReportState>(null)
  const moderation = getModerationService()

  const post = id ? getPost(id) : undefined
  const comments = id ? getCommentsForPost(id) : []
  const liked = id ? isPostLiked(id) : false

  useEffect(() => {
    if (!id) return
    void loadCommentsForPost(id)
  }, [id, loadCommentsForPost, dataSource])

  const openLogin = () => {
    setAuthMode('login')
    setAuthOpen(true)
  }

  const handleConfirm = async () => {
    if (!id || !post) return
    if (confirm?.type === 'post') {
      const err = await deletePost(id)
      if (err) {
        showToast(err)
        setConfirm(null)
        return
      }
      showToast('帖子已删除')
      navigate('/')
    } else if (confirm?.type === 'comment') {
      const err = await deleteComment(confirm.commentId, id)
      if (err) showToast(err)
      else showToast('评论已删除')
    }
    setConfirm(null)
  }

  const headerProps = {
    search,
    onSearchChange,
    onOpenCreate: () => setCreateOpen(true),
    onOpenLogin: openLogin,
    onOpenRegister: () => {
      setAuthMode('register')
      setAuthOpen(true)
    },
  }

  if (!loading && !post) {
    return (
      <>
        <Header {...headerProps} />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState
            message="帖子不存在或已被删除"
            hint="可能已被作者删除，或链接有误"
          />
          <p className="mt-6 text-center">
            <Link
              to="/"
              className="font-semibold no-underline"
              style={{ color: 'var(--color-primary)' }}
            >
              返回广场
            </Link>
          </p>
        </main>
      </>
    )
  }

  const isAuthor = currentUser?.id === post?.authorId

  return (
    <>
      <Header {...headerProps} />

      <main className="mx-auto max-w-3xl px-4 py-5 sm:px-6 sm:py-6">
        <Link
          to="/"
          className="mb-4 inline-flex items-center gap-1 text-sm font-semibold no-underline"
          style={{ color: 'var(--color-primary)' }}
        >
          ← 返回广场
        </Link>

        {loading || !post ? (
          <PostListSkeleton count={1} />
        ) : (
          <article
            className="rounded-3xl p-5 sm:p-8"
            style={{
              background: 'var(--color-surface)',
              boxShadow: 'var(--shadow-warm)',
            }}
          >
            <div className="mb-4 flex flex-wrap gap-2">
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
              {post.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-md px-2 py-0.5 text-xs"
                  style={{ background: 'var(--color-surface-alt)', color: 'var(--color-text-dim)' }}
                >
                  #{tag}
                </span>
              ))}
            </div>

            <h1 className="mb-4 text-xl font-bold leading-snug sm:text-2xl">{post.title}</h1>

            <div className="mb-6 flex flex-wrap items-center gap-3">
              <DefaultAvatar size="md" />
              <div>
                <p className="font-bold">{post.authorName}</p>
                <p className="text-sm" style={{ color: 'var(--color-text-dim)' }}>
                  {formatDateTime(post.createdAt)}
                </p>
              </div>
            </div>

            <div
              className="mb-6 whitespace-pre-wrap text-base leading-relaxed"
              style={{ color: 'var(--color-text)' }}
            >
              {post.body}
            </div>

            <div
              className="flex flex-wrap gap-3 border-t pt-4"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <Button
                variant={liked ? 'primary' : 'secondary'}
                onClick={async () => {
                  const err = await toggleLike(post.id)
                  if (err) showToast(err)
                  else showToast(liked ? '已取消点赞' : '点赞成功')
                }}
              >
                {liked ? '已点赞' : '点赞'} · {post.likeCount}
              </Button>
              {isAuthor && (
                <Button variant="danger" onClick={() => setConfirm({ type: 'post' })}>
                  删除帖子
                </Button>
              )}
              {!isAuthor && currentUser && currentUser.status !== 'banned' && (
                <Button variant="ghost" onClick={() => setReport({ type: 'post' })}>
                  举报
                </Button>
              )}
            </div>

            <section className="mt-8">
              <h2 className="mb-4 text-lg font-bold">评论 ({comments.length})</h2>
              {comments.length === 0 ? (
                <p
                  className="mb-4 rounded-2xl px-4 py-6 text-center text-sm"
                  style={{ background: 'var(--color-surface-alt)', color: 'var(--color-text-dim)' }}
                >
                  还没有评论，来抢沙发吧
                </p>
              ) : (
                <div className="mb-4 flex flex-col gap-3">
                  {comments.map((c) => (
                    <CommentItem
                      key={c.id}
                      comment={c}
                      post={post}
                      currentUserId={currentUser?.id}
                      onDeleteRequest={() =>
                        setConfirm({ type: 'comment', commentId: c.id })
                      }
                      onReportRequest={
                        currentUser?.status !== 'banned'
                          ? () => setReport({ type: 'comment', commentId: c.id })
                          : undefined
                      }
                    />
                  ))}
                </div>
              )}
              <CommentForm
                onSubmit={async (body) => addComment(post.id, body)}
                onSuccess={() => showToast('评论发布成功')}
                onRequestLogin={openLogin}
              />
            </section>
          </article>
        )}
      </main>

      <MobileCreateFab onClick={() => setCreateOpen(true)} />

      <ConfirmDialog
        open={confirm?.type === 'post'}
        title="删除帖子"
        message="删除后无法恢复，确定要删除这篇帖子吗？"
        confirmLabel="删除"
        danger
        onConfirm={handleConfirm}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm?.type === 'comment'}
        title="删除评论"
        message="确定要删除这条评论吗？"
        confirmLabel="删除"
        danger
        onConfirm={handleConfirm}
        onCancel={() => setConfirm(null)}
      />

      <AuthModal
        open={authOpen}
        mode={authMode}
        onClose={() => setAuthOpen(false)}
        onModeChange={setAuthMode}
      />
      <CreatePostModal open={createOpen} onClose={() => setCreateOpen(false)} />

      <ReportModal
        open={report !== null}
        title={report?.type === 'comment' ? '举报评论' : '举报帖子'}
        onClose={() => setReport(null)}
        onSubmit={async (reason) => {
          if (!id || !report) return '无效操作'
          if (report.type === 'post') {
            return moderation.reportPost(id, reason)
          }
          return moderation.reportComment(id, report.commentId, reason)
        }}
        onSuccess={() => showToast('举报已提交，感谢反馈')}
      />
    </>
  )
}
