import { Link } from 'react-router-dom'
import { useCommunity } from '../../context/CommunityContext'
import { isStaffUser } from '../../types/community'
import { useTheme } from '../../context/ThemeContext'
import { Button } from '../ui/Button'
import { DefaultAvatar } from '../icons/DefaultAvatar'

interface HeaderProps {
  search: string
  onSearchChange: (v: string) => void
  onOpenCreate: () => void
  onOpenLogin: () => void
  onOpenRegister: () => void
}

export function Header({
  search,
  onSearchChange,
  onOpenCreate,
  onOpenLogin,
  onOpenRegister,
}: HeaderProps) {
  const { currentUser, logout, dataSource } = useCommunity()
  const { theme, toggleTheme } = useTheme()

  return (
    <header
      className="sticky top-0 z-40 border-b backdrop-blur-md"
      style={{
        background: 'color-mix(in srgb, var(--color-bg) 94%, transparent)',
        borderColor: 'var(--color-border)',
      }}
    >
      <div className="mx-auto max-w-6xl px-4 py-3 sm:px-6">
        {/* 第一行：品牌 + 操作 */}
        <div className="flex items-center gap-2 sm:gap-3">
          <Link
            to="/"
            className="flex min-w-0 shrink items-center gap-2 no-underline"
            style={{ color: 'var(--color-text)' }}
          >
            <svg width="28" height="28" className="shrink-0 sm:h-8 sm:w-8" viewBox="0 0 32 32" aria-hidden="true">
              <circle cx="16" cy="16" r="16" fill="#FFE5D9" className="dark:opacity-90" />
              <circle cx="11" cy="13" r="2" fill="#FFA5A5" />
              <circle cx="21" cy="13" r="2" fill="#FFA5A5" />
              <path
                d="M10 19c2 2 10 2 12 0"
                stroke="#FFA5A5"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
            <span className="truncate text-base font-bold sm:text-xl">DanmuAI 社区</span>
            {dataSource === 'mock' && (
              <span
                className="hidden rounded-md px-1.5 py-0.5 text-[10px] font-semibold sm:inline"
                style={{ background: 'var(--color-accent-bg)', color: 'var(--color-text-dim)' }}
              >
                演示数据
              </span>
            )}
          </Link>

          <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
            <button
              type="button"
              onClick={toggleTheme}
              className="rounded-xl p-2 transition hover:bg-[var(--color-accent-bg)]"
              aria-label={theme === 'light' ? '切换到黑夜模式' : '切换到亮色模式'}
            >
              {theme === 'light' ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="5" />
                  <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                </svg>
              )}
            </button>

            {isStaffUser(currentUser) && (
              <Link
                to="/moderation"
                className="hidden rounded-xl px-3 py-2 text-sm font-semibold no-underline transition hover:bg-[var(--color-accent-bg)] sm:inline-flex"
                style={{ color: 'var(--color-primary)' }}
              >
                管理
              </Link>
            )}

            <Button
              variant="primary"
              onClick={onOpenCreate}
              className="hidden !px-4 !py-2 shadow-[var(--shadow-btn)] md:inline-flex"
            >
              发帖
            </Button>

            {currentUser ? (
              <div className="flex items-center gap-1 sm:gap-2">
                <div className="hidden items-center gap-2 sm:flex">
                  <DefaultAvatar size="sm" />
                  <span className="max-w-[5rem] truncate text-sm font-semibold sm:max-w-none">
                    {currentUser.username}
                  </span>
                </div>
                <Button variant="ghost" className="!px-2.5 !py-2 text-xs sm:!px-4 sm:text-sm" onClick={logout}>
                  退出
                </Button>
              </div>
            ) : (
              <>
                <Button
                  variant="secondary"
                  className="!px-2.5 !py-2 text-xs sm:!px-4 sm:text-sm"
                  onClick={onOpenLogin}
                >
                  登录
                </Button>
                <Button
                  variant="ghost"
                  className="hidden !px-4 !py-2 sm:inline-flex"
                  onClick={onOpenRegister}
                >
                  注册
                </Button>
              </>
            )}
          </div>
        </div>

        {/* 第二行：搜索 */}
        <div className="mt-3">
          <input
            type="search"
            placeholder="搜索帖子、标签、作者…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full rounded-xl border-0 px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            style={{
              background: 'var(--color-surface-alt)',
              color: 'var(--color-text)',
              boxShadow: 'inset 0 0 0 1px var(--color-border)',
            }}
          />
        </div>
      </div>
    </header>
  )
}
