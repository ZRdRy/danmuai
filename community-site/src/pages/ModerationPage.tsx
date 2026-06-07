import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useCommunity } from '../context/CommunityContext'
import { useToast } from '../context/ToastContext'
import { Header } from '../components/layout/Header'
import { AuthModal } from '../components/auth/AuthModal'
import { CreatePostModal } from '../components/create/CreatePostModal'
import { Button } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { getModerationService } from '../services/moderationService'
import type { CommunityReport } from '../services/types'
import { isAdminUser, isStaffUser } from '../types/community'
import { formatRelativeTime } from '../utils/formatTime'

interface ModerationPageProps {
  search: string
  onSearchChange: (v: string) => void
}

export function ModerationPage({ search, onSearchChange }: ModerationPageProps) {
  const { currentUser, refresh, dataSource } = useCommunity()
  const { showToast } = useToast()
  const moderation = getModerationService()

  const [reports, setReports] = useState<CommunityReport[]>([])
  const [loading, setLoading] = useState(true)
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [createOpen, setCreateOpen] = useState(false)
  const [banUserId, setBanUserId] = useState('')
  const [banUsername, setBanUsername] = useState('')

  const loadReports = useCallback(async () => {
    if (!isStaffUser(currentUser)) {
      setReports([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const list = await moderation.listPendingReports()
      setReports(list)
    } catch (e) {
      showToast(e instanceof Error ? e.message : '加载举报失败')
    } finally {
      setLoading(false)
    }
  }, [currentUser, moderation, showToast])

  useEffect(() => {
    void loadReports()
  }, [loadReports, dataSource])

  const headerProps = {
    search,
    onSearchChange,
    onOpenCreate: () => setCreateOpen(true),
    onOpenLogin: () => {
      setAuthMode('login')
      setAuthOpen(true)
    },
    onOpenRegister: () => {
      setAuthMode('register')
      setAuthOpen(true)
    },
  }

  if (!currentUser) {
    return (
      <>
        <Header {...headerProps} />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState message="请先登录" hint="管理台仅对版主与管理员开放" />
        </main>
        <AuthModal
          open={authOpen}
          mode={authMode}
          onClose={() => setAuthOpen(false)}
          onModeChange={setAuthMode}
        />
      </>
    )
  }

  if (!isStaffUser(currentUser)) {
    return <Navigate to="/" replace />
  }

  const handleResolve = async (reportId: string, status: 'resolved' | 'dismissed') => {
    const err = await moderation.resolveReport(reportId, status)
    if (err) showToast(err)
    else {
      showToast(status === 'resolved' ? '已标记为已处理' : '已忽略')
      await loadReports()
    }
  }

  const handleDeletePost = async (postId: string) => {
    const err = await moderation.staffSoftDeletePost(postId)
    if (err) showToast(err)
    else {
      showToast('帖子已删除')
      await refresh()
      await loadReports()
    }
  }

  const handleDeleteComment = async (commentId: string) => {
    const err = await moderation.staffSoftDeleteComment(commentId)
    if (err) showToast(err)
    else {
      showToast('评论已删除')
      await loadReports()
    }
  }

  const handleFeatured = async (postId: string, featured: boolean) => {
    const err = await moderation.staffSetFeatured(postId, featured)
    if (err) showToast(err)
    else {
      showToast(featured ? '已设为精华' : '已取消精华')
      await refresh()
    }
  }

  const handleBanToggle = async (userId: string, status: 'active' | 'banned') => {
    const err = await moderation.adminSetUserStatus(userId, status)
    if (err) showToast(err)
    else showToast(status === 'banned' ? '用户已封禁' : '用户已解封')
  }

  const loadAuthorForPost = async (postId: string) => {
    const prof = await moderation.lookupProfileForPost(postId)
    if (prof) {
      setBanUserId(prof.authorId)
      setBanUsername(prof.username)
    }
  }

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
        <h1 className="mb-2 text-2xl font-bold">内容管理</h1>
        <p className="mb-6 text-sm" style={{ color: 'var(--color-text-dim)' }}>
          待处理举报 {reports.length} 条
          {dataSource === 'mock' && '（演示数据）'}
        </p>

        {isAdminUser(currentUser) && (
          <section
            className="mb-6 rounded-2xl p-4"
            style={{ background: 'var(--color-surface-alt)' }}
          >
            <h2 className="mb-2 text-sm font-bold">封禁用户（仅管理员）</h2>
            <p className="mb-3 text-xs" style={{ color: 'var(--color-text-dim)' }}>
              在下方举报卡片点击「载入作者」后，可封禁/解封帖子作者。
            </p>
            {banUserId ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold">@{banUsername}</span>
                <Button
                  variant="danger"
                  className="!px-3 !py-1 text-xs"
                  onClick={() => void handleBanToggle(banUserId, 'banned')}
                >
                  封禁
                </Button>
                <Button
                  variant="secondary"
                  className="!px-3 !py-1 text-xs"
                  onClick={() => void handleBanToggle(banUserId, 'active')}
                >
                  解封
                </Button>
              </div>
            ) : (
              <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
                尚未选择用户
              </p>
            )}
          </section>
        )}

        {loading ? (
          <p className="text-sm" style={{ color: 'var(--color-text-dim)' }}>
            加载中…
          </p>
        ) : reports.length === 0 ? (
          <EmptyState message="暂无待处理举报" hint="用户举报后会显示在这里" />
        ) : (
          <ul className="flex flex-col gap-4">
            {reports.map((r) => (
              <li
                key={r.id}
                className="rounded-2xl p-4 sm:p-5"
                style={{
                  background: 'var(--color-surface)',
                  boxShadow: 'var(--shadow-warm)',
                }}
              >
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span
                    className="rounded-lg px-2 py-0.5 text-xs font-bold"
                    style={{
                      background: 'var(--color-soft-peach)',
                      color: 'var(--color-primary-hover)',
                    }}
                  >
                    {r.targetType === 'post' ? '帖子' : '评论'}
                  </span>
                  <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
                    {formatRelativeTime(r.createdAt)}
                  </span>
                </div>
                <p className="mb-1 text-sm font-bold">
                  {r.postTitle ?? '（帖子）'}
                  {r.targetType === 'comment' && r.commentPreview && (
                    <span className="mt-1 block font-normal" style={{ color: 'var(--color-text-dim)' }}>
                      评论：{r.commentPreview}
                    </span>
                  )}
                </p>
                {r.reason && (
                  <p className="mb-3 text-sm" style={{ color: 'var(--color-text-dim)' }}>
                    原因：{r.reason}
                  </p>
                )}
                <div className="mb-3 flex flex-wrap gap-2">
                  <Link
                    to={`/post/${r.postId}`}
                    className="text-xs font-semibold no-underline"
                    style={{ color: 'var(--color-primary)' }}
                  >
                    查看帖子
                  </Link>
                  {isAdminUser(currentUser) && (
                    <button
                      type="button"
                      className="text-xs font-semibold"
                      style={{ color: 'var(--color-text-dim)' }}
                      onClick={() => void loadAuthorForPost(r.postId)}
                    >
                      载入作者
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {r.targetType === 'post' ? (
                    <Button
                      variant="danger"
                      className="!px-3 !py-1 text-xs"
                      onClick={() => void handleDeletePost(r.postId)}
                    >
                      软删帖子
                    </Button>
                  ) : (
                    r.commentId && (
                      <Button
                        variant="danger"
                        className="!px-3 !py-1 text-xs"
                        onClick={() => void handleDeleteComment(r.commentId!)}
                      >
                        软删评论
                      </Button>
                    )
                  )}
                  <Button
                    variant="secondary"
                    className="!px-3 !py-1 text-xs"
                    onClick={() => void handleFeatured(r.postId, true)}
                  >
                    设为精华
                  </Button>
                  <Button
                    variant="ghost"
                    className="!px-3 !py-1 text-xs"
                    onClick={() => void handleFeatured(r.postId, false)}
                  >
                    取消精华
                  </Button>
                  <Button
                    variant="primary"
                    className="!px-3 !py-1 text-xs"
                    onClick={() => void handleResolve(r.id, 'resolved')}
                  >
                    已处理
                  </Button>
                  <Button
                    variant="ghost"
                    className="!px-3 !py-1 text-xs"
                    onClick={() => void handleResolve(r.id, 'dismissed')}
                  >
                    忽略
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>

      <AuthModal
        open={authOpen}
        mode={authMode}
        onClose={() => setAuthOpen(false)}
        onModeChange={setAuthMode}
      />
      <CreatePostModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  )
}
