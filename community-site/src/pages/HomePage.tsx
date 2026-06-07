import { useState } from 'react'
import { useCommunity } from '../context/CommunityContext'
import { useFilteredPosts } from '../hooks/useFilteredPosts'
import { usePageLoading } from '../hooks/usePageLoading'
import { Header } from '../components/layout/Header'
import { HeroBanner } from '../components/layout/HeroBanner'
import { MobileCreateFab } from '../components/layout/MobileCreateFab'
import { RulesAccordion, RulesSidebar } from '../components/layout/RulesSidebar'
import { AuthModal } from '../components/auth/AuthModal'
import { CreatePostModal } from '../components/create/CreatePostModal'
import { CategoryChips } from '../components/post/CategoryChips'
import { PostCard } from '../components/post/PostCard'
import { SortTabs } from '../components/post/SortTabs'
import { EmptyState } from '../components/ui/EmptyState'
import { PostListSkeleton } from '../components/ui/PostListSkeleton'
import type { PostCategoryFilter, SortKind } from '../types/community'

interface HomePageProps {
  search: string
  onSearchChange: (v: string) => void
}

export function HomePage({ search, onSearchChange }: HomePageProps) {
  const { posts, likedPostIds, isLoading: bootLoading, error, currentUser } = useCommunity()
  const [category, setCategory] = useState<PostCategoryFilter>('all')
  const [sort, setSort] = useState<SortKind>('latest')
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [createOpen, setCreateOpen] = useState(false)
  const routeLoading = usePageLoading()
  const loading = bootLoading || routeLoading

  const filtered = useFilteredPosts(posts, search, category, sort, likedPostIds)
  const hasSearch = search.trim().length > 0
  const hasFilter = category !== 'all'

  const emptyMessage = hasSearch
    ? '没有找到相关帖子'
    : hasFilter
      ? '这个分类下还没有帖子'
      : '暂时没有帖子'
  const emptyHint = hasSearch
    ? '试试更短的关键词，或换个分类看看'
    : hasFilter
      ? '欢迎成为第一个分享的人'
      : '点击发帖，分享你的第一条内容吧'

  return (
    <>
      {currentUser?.status === 'banned' && (
        <div
          className="border-b px-4 py-2 text-center text-sm font-semibold"
          style={{
            background: 'color-mix(in srgb, var(--color-danger) 12%, var(--color-bg))',
            color: 'var(--color-danger)',
            borderColor: 'var(--color-border)',
          }}
        >
          您的账号已被封禁，无法发帖、评论、点赞或举报。
        </div>
      )}

      <Header
        search={search}
        onSearchChange={onSearchChange}
        onOpenCreate={() => setCreateOpen(true)}
        onOpenLogin={() => {
          setAuthMode('login')
          setAuthOpen(true)
        }}
        onOpenRegister={() => {
          setAuthMode('register')
          setAuthOpen(true)
        }}
      />

      <main className="mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-6">
        {error && (
          <p
            className="mb-4 rounded-xl px-4 py-3 text-sm"
            style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger-text)' }}
          >
            加载失败：{error}
          </p>
        )}
        <HeroBanner />

        <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
          <div>
            <div className="mb-4 space-y-3">
              <CategoryChips value={category} onChange={setCategory} />
              <div className="flex justify-start sm:justify-end">
                <SortTabs value={sort} onChange={setSort} />
              </div>
            </div>

            {loading ? (
              <PostListSkeleton />
            ) : filtered.length === 0 ? (
              <EmptyState message={emptyMessage} hint={emptyHint} />
            ) : (
              <div className="flex flex-col gap-4">
                {filtered.map((post) => (
                  <PostCard key={post.id} post={post} />
                ))}
              </div>
            )}

            <div className="mt-6">
              <RulesAccordion />
            </div>
          </div>

          <RulesSidebar className="hidden lg:block" />
        </div>
      </main>

      <MobileCreateFab onClick={() => setCreateOpen(true)} />

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
