import { INITIAL_COMMENTS, INITIAL_POSTS } from '../mocks/posts'
import type { Comment, Post } from '../types/community'
import { getAuthService } from './authService'
import type {
  CommunityBootstrap,
  CommunityService,
  CreatePostInput,
  ToggleLikeResult,
} from './types'

function excerpt(body: string): string {
  return body.length > 80 ? `${body.slice(0, 80)}…` : body
}

let posts: Post[] = [...INITIAL_POSTS]
let comments: Comment[] = [...INITIAL_COMMENTS]
let likedPostIds = new Set<string>()
let nextId = 1000
const genId = (p: string) => `${p}-${++nextId}`

export const mockCommunityService: CommunityService = {
  mode: 'mock',

  async bootstrap(): Promise<CommunityBootstrap> {
    const currentUser = await getAuthService().getCurrentUser()
    return {
      posts: [...posts],
      comments: [...comments],
      likedPostIds: new Set(likedPostIds),
      currentUser,
    }
  },

  async listPosts() {
    return [...posts]
  },

  async getPost(id: string) {
    return posts.find((p) => p.id === id) ?? null
  },

  async listComments(postId: string) {
    return comments
      .filter((c) => c.postId === postId)
      .sort(
        (a, b) =>
          new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
      )
  },

  async getLikedPostIds(postIds: string[]) {
    return new Set(postIds.filter((id) => likedPostIds.has(id)))
  },

  async createPost(input: CreatePostInput) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再发帖'
    const title = input.title.trim()
    const body = input.body.trim()
    if (!title) return '请输入标题'
    if (!body) return '请输入正文'
    const post: Post = {
      id: genId('p'),
      title,
      excerpt: excerpt(body),
      body,
      authorId: user.id,
      authorName: user.username,
      category: input.category,
      tags: input.tags,
      likeCount: 0,
      commentCount: 0,
      createdAt: new Date().toISOString(),
    }
    posts = [post, ...posts]
    return null
  },

  async softDeletePost(postId: string) {
    posts = posts.filter((p) => p.id !== postId)
    comments = comments.filter((c) => c.postId !== postId)
    likedPostIds = new Set([...likedPostIds].filter((id) => id !== postId))
    return null
  },

  async createComment(postId: string, body: string) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再评论'
    const text = body.trim()
    if (!text) return '请输入评论内容'
    const comment: Comment = {
      id: genId('c'),
      postId,
      authorId: user.id,
      authorName: user.username,
      body: text,
      createdAt: new Date().toISOString(),
    }
    comments = [...comments, comment]
    posts = posts.map((p) =>
      p.id === postId ? { ...p, commentCount: p.commentCount + 1 } : p,
    )
    return null
  },

  async softDeleteComment(commentId: string, postId: string) {
    comments = comments.filter((c) => c.id !== commentId)
    posts = posts.map((p) =>
      p.id === postId
        ? { ...p, commentCount: Math.max(0, p.commentCount - 1) }
        : p,
    )
    return null
  },

  async toggleLike(postId: string): Promise<ToggleLikeResult | string> {
    const wasLiked = likedPostIds.has(postId)
    if (wasLiked) likedPostIds.delete(postId)
    else likedPostIds.add(postId)
    let likeCount = 0
    posts = posts.map((p) => {
      if (p.id !== postId) return p
      likeCount = Math.max(0, p.likeCount + (wasLiked ? -1 : 1))
      return { ...p, likeCount }
    })
    return { liked: !wasLiked, likeCount }
  },
}

/** Mock moderation: toggle featured on in-memory posts. */
export function mockStaffSetFeatured(postId: string, featured: boolean): string | null {
  const idx = posts.findIndex((p) => p.id === postId)
  if (idx < 0) return '帖子不存在'
  posts[idx] = { ...posts[idx], isFeatured: featured }
  return null
}
