export type PostCategoryKey =
  | 'prompt'
  | 'experience'
  | 'help'
  | 'config'
  | 'showcase'

export type PostCategoryFilter = 'all' | PostCategoryKey

export type SortKind = 'latest' | 'hot' | 'featured'

export type UserRole = 'user' | 'moderator' | 'admin'
export type UserStatus = 'active' | 'banned'

export interface User {
  id: string
  username: string
  role?: UserRole
  status?: UserStatus
}

export function isStaffUser(user: User | null | undefined): boolean {
  if (!user || user.status === 'banned') return false
  return user.role === 'moderator' || user.role === 'admin'
}

export function isAdminUser(user: User | null | undefined): boolean {
  if (!user || user.status === 'banned') return false
  return user.role === 'admin'
}

export interface Post {
  id: string
  title: string
  excerpt: string
  body: string
  authorId: string
  authorName: string
  category: PostCategoryKey
  tags: string[]
  likeCount: number
  commentCount: number
  createdAt: string
  isFeatured?: boolean
}

export interface Comment {
  id: string
  postId: string
  authorId: string
  authorName: string
  body: string
  createdAt: string
}

export const CATEGORY_LABELS: Record<PostCategoryKey, string> = {
  prompt: '提示词分享',
  experience: '使用经验',
  help: '问题求助',
  config: '配置分享',
  showcase: '作品展示',
}

export const CATEGORY_FILTERS: { key: PostCategoryFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'prompt', label: '提示词分享' },
  { key: 'experience', label: '使用经验' },
  { key: 'help', label: '问题求助' },
  { key: 'config', label: '配置分享' },
  { key: 'showcase', label: '作品展示' },
]

export type ReportTargetType = 'post' | 'comment'
export type ReportStatus = 'pending' | 'resolved' | 'dismissed'

export const SORT_OPTIONS: { key: SortKind; label: string }[] = [
  { key: 'latest', label: '最新' },
  { key: 'hot', label: '最热' },
  { key: 'featured', label: '精华' },
]

/** 侧栏标题下的一句友好说明 */
export const COMMUNITY_RULES_INTRO =
  '由于服务器原因可能会存在一定的延迟，非常抱歉'

export const COMMUNITY_RULES = [
  '请用文字分享，暂不支持发图片',
  '友善交流，请勿广告或灌水',
  '帖子发布后如需修改，请删除后重新发布',
  '只能删除自己发布的帖子',
  '帖主可以管理自己帖子下的评论',
  '评论者可以删除自己的评论',
]

export const DEMO_USER_ID = 'u-demo'
