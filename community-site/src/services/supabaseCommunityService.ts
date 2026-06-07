import { getSupabaseClient } from '../lib/supabase'
import type { Post } from '../types/community'
import { getAuthService } from './authService'
import {
  fetchProfilesMap,
  mapCommentRow,
  mapPostRow,
} from './mapRows'
import type {
  CommunityBootstrap,
  CommunityService,
  CreatePostInput,
  DbCommentRow,
  DbPostRow,
  DbProfileRow,
  ToggleLikeResult,
} from './types'

async function loadProfiles(userIds: string[]): Promise<Map<string, DbProfileRow>> {
  const supabase = getSupabaseClient()
  return fetchProfilesMap(userIds, async (ids) => {
    const { data, error } = await supabase
      .from('community_profiles')
      .select('user_id, username, display_name')
      .in('user_id', ids)
      .eq('status', 'active')
    if (error) throw error
    return (data ?? []) as DbProfileRow[]
  })
}

async function fetchPostsRows(): Promise<Post[]> {
  const supabase = getSupabaseClient()
  const { data, error } = await supabase
    .from('community_posts')
    .select(
      'id, author_id, title, content, category, tags, like_count, comment_count, is_featured, created_at',
    )
    .eq('is_deleted', false)
    .order('created_at', { ascending: false })
    .limit(200)
  if (error) throw error
  const rows = (data ?? []) as DbPostRow[]
  const profiles = await loadProfiles(rows.map((r) => r.author_id))
  return rows.map((r) => mapPostRow(r, profiles.get(r.author_id)))
}

export const supabaseCommunityService: CommunityService = {
  mode: 'supabase',

  async bootstrap(): Promise<CommunityBootstrap> {
    const [posts, currentUser] = await Promise.all([
      fetchPostsRows(),
      getAuthService().getCurrentUser(),
    ])
    const likedPostIds = currentUser
      ? await this.getLikedPostIds(posts.map((p) => p.id))
      : new Set<string>()
    return {
      posts,
      comments: [],
      likedPostIds,
      currentUser,
    }
  },

  async listPosts() {
    return fetchPostsRows()
  },

  async getPost(id: string) {
    const supabase = getSupabaseClient()
    const { data, error } = await supabase
      .from('community_posts')
      .select(
        'id, author_id, title, content, category, tags, like_count, comment_count, is_featured, created_at',
      )
      .eq('id', id)
      .eq('is_deleted', false)
      .maybeSingle()
    if (error) throw error
    if (!data) return null
    const row = data as DbPostRow
    const profiles = await loadProfiles([row.author_id])
    return mapPostRow(row, profiles.get(row.author_id))
  },

  async listComments(postId: string) {
    const supabase = getSupabaseClient()
    const { data, error } = await supabase
      .from('community_comments')
      .select('id, post_id, author_id, content, created_at')
      .eq('post_id', postId)
      .eq('is_deleted', false)
      .order('created_at', { ascending: true })
    if (error) throw error
    const rows = (data ?? []) as DbCommentRow[]
    const profiles = await loadProfiles(rows.map((r) => r.author_id))
    return rows.map((r) => mapCommentRow(r, profiles.get(r.author_id)))
  },

  async getLikedPostIds(postIds: string[]) {
    const set = new Set<string>()
    if (postIds.length === 0) return set
    const user = await getAuthService().getCurrentUser()
    if (!user) return set
    const supabase = getSupabaseClient()
    const { data, error } = await supabase
      .from('community_post_likes')
      .select('post_id')
      .eq('user_id', user.id)
      .in('post_id', postIds)
    if (error) throw error
    for (const row of data ?? []) {
      set.add(row.post_id as string)
    }
    return set
  },

  async createPost(input: CreatePostInput) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再发帖'
    const title = input.title.trim()
    const content = input.body.trim()
    if (!title) return '请输入标题'
    if (content.length < 10) return '正文至少需要 10 个字'
    if (content.length > 5000) return '正文不能超过 5000 字'
    const supabase = getSupabaseClient()
    const { error } = await supabase.from('community_posts').insert({
      author_id: user.id,
      title,
      content,
      category: input.category,
      tags: input.tags.slice(0, 5),
    })
    if (error) return error.message
    return null
  },

  async softDeletePost(postId: string) {
    const supabase = getSupabaseClient()
    const { error } = await supabase
      .from('community_posts')
      .update({
        is_deleted: true,
        deleted_at: new Date().toISOString(),
      })
      .eq('id', postId)
    if (error) return error.message
    return null
  },

  async createComment(postId: string, body: string) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再评论'
    const content = body.trim()
    if (!content) return '请输入评论内容'
    const supabase = getSupabaseClient()
    const { error } = await supabase.from('community_comments').insert({
      post_id: postId,
      author_id: user.id,
      content,
    })
    if (error) return error.message
    return null
  },

  async softDeleteComment(commentId: string) {
    const supabase = getSupabaseClient()
    const { error } = await supabase
      .from('community_comments')
      .update({
        is_deleted: true,
        deleted_at: new Date().toISOString(),
      })
      .eq('id', commentId)
    if (error) return error.message
    return null
  },

  async toggleLike(postId: string): Promise<ToggleLikeResult | string> {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再点赞'
    const supabase = getSupabaseClient()
    const { data: existing } = await supabase
      .from('community_post_likes')
      .select('post_id')
      .eq('post_id', postId)
      .eq('user_id', user.id)
      .maybeSingle()

    if (existing) {
      const { error } = await supabase
        .from('community_post_likes')
        .delete()
        .eq('post_id', postId)
        .eq('user_id', user.id)
      if (error) return error.message
    } else {
      const { error } = await supabase.from('community_post_likes').insert({
        post_id: postId,
        user_id: user.id,
      })
      if (error) return error.message
    }

    const post = await this.getPost(postId)
    if (!post) return '帖子不存在'
    return {
      liked: !existing,
      likeCount: post.likeCount,
    }
  },
}
