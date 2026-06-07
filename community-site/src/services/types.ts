import type {
  Comment,
  Post,
  PostCategoryKey,
  ReportStatus,
  ReportTargetType,
  User,
  UserStatus,
} from '../types/community'

export type DataSourceMode = 'mock' | 'supabase'

export interface CreatePostInput {
  title: string
  body: string
  category: PostCategoryKey
  tags: string[]
}

export interface CommunityBootstrap {
  posts: Post[]
  comments: Comment[]
  likedPostIds: Set<string>
  currentUser: User | null
}

export interface ToggleLikeResult {
  liked: boolean
  likeCount: number
}

export interface CommunityService {
  readonly mode: DataSourceMode
  bootstrap(): Promise<CommunityBootstrap>
  listPosts(): Promise<Post[]>
  getPost(id: string): Promise<Post | null>
  listComments(postId: string): Promise<Comment[]>
  getLikedPostIds(postIds: string[]): Promise<Set<string>>
  createPost(input: CreatePostInput): Promise<string | null>
  softDeletePost(postId: string): Promise<string | null>
  createComment(postId: string, body: string): Promise<string | null>
  softDeleteComment(commentId: string, postId: string): Promise<string | null>
  toggleLike(postId: string): Promise<ToggleLikeResult | string>
}

export interface AuthService {
  readonly mode: DataSourceMode
  login(username: string, password: string): Promise<string | null>
  register(username: string, password: string, confirm: string): Promise<string | null>
  logout(): Promise<void>
  getCurrentUser(): Promise<User | null>
}

export interface CommunityReport {
  id: string
  reporterId: string
  targetType: ReportTargetType
  postId: string
  commentId?: string
  reason?: string
  status: ReportStatus
  createdAt: string
  postTitle?: string
  commentPreview?: string
}

export interface ModerationService {
  readonly mode: DataSourceMode
  reportPost(postId: string, reason?: string): Promise<string | null>
  reportComment(
    postId: string,
    commentId: string,
    reason?: string,
  ): Promise<string | null>
  listPendingReports(): Promise<CommunityReport[]>
  resolveReport(
    reportId: string,
    status: 'resolved' | 'dismissed',
  ): Promise<string | null>
  staffSoftDeletePost(postId: string): Promise<string | null>
  staffSoftDeleteComment(commentId: string): Promise<string | null>
  staffSetFeatured(postId: string, featured: boolean): Promise<string | null>
  adminSetUserStatus(
    userId: string,
    status: UserStatus,
  ): Promise<string | null>
  lookupProfileForPost(postId: string): Promise<{
    authorId: string
    username: string
    status: UserStatus
  } | null>
}

/** DB row shapes (snake_case) */
export interface DbPostRow {
  id: string
  author_id: string
  title: string
  content: string
  category: PostCategoryKey
  tags: string[]
  like_count: number
  comment_count: number
  is_featured: boolean
  created_at: string
}

export interface DbCommentRow {
  id: string
  post_id: string
  author_id: string
  content: string
  created_at: string
}

export interface DbProfileRow {
  user_id: string
  username: string
  display_name: string | null
}
