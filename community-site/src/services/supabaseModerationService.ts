import { getSupabaseClient } from '../lib/supabase'
import { getAuthService } from './authService'
import type { CommunityReport, ModerationService } from './types'
import type { UserStatus } from '../types/community'

interface DbReportRow {
  id: string
  reporter_id: string
  target_type: 'post' | 'comment'
  post_id: string
  comment_id: string | null
  reason: string | null
  status: 'pending' | 'resolved' | 'dismissed'
  created_at: string
}

function mapReport(row: DbReportRow, postTitle?: string, commentPreview?: string): CommunityReport {
  return {
    id: row.id,
    reporterId: row.reporter_id,
    targetType: row.target_type,
    postId: row.post_id,
    commentId: row.comment_id ?? undefined,
    reason: row.reason ?? undefined,
    status: row.status,
    createdAt: row.created_at,
    postTitle,
    commentPreview,
  }
}

export const supabaseModerationService: ModerationService = {
  mode: 'supabase',

  async reportPost(postId, reason) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再举报'
    if (user.status === 'banned') return '账号已被封禁，无法举报'
    const supabase = getSupabaseClient()
    const { error } = await supabase.from('community_reports').insert({
      reporter_id: user.id,
      target_type: 'post',
      post_id: postId,
      reason: reason?.trim() || null,
    })
    if (error) {
      if (error.code === '23505') return '您已举报过该内容'
      if (error.message.includes('rate limit')) return '举报过于频繁，请稍后再试'
      return error.message
    }
    return null
  },

  async reportComment(postId, commentId, reason) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再举报'
    if (user.status === 'banned') return '账号已被封禁，无法举报'
    const supabase = getSupabaseClient()
    const { error } = await supabase.from('community_reports').insert({
      reporter_id: user.id,
      target_type: 'comment',
      post_id: postId,
      comment_id: commentId,
      reason: reason?.trim() || null,
    })
    if (error) {
      if (error.code === '23505') return '您已举报过该内容'
      if (error.message.includes('rate limit')) return '举报过于频繁，请稍后再试'
      return error.message
    }
    return null
  },

  async listPendingReports() {
    const supabase = getSupabaseClient()
    const { data, error } = await supabase
      .from('community_reports')
      .select('id, reporter_id, target_type, post_id, comment_id, reason, status, created_at')
      .eq('status', 'pending')
      .order('created_at', { ascending: false })
      .limit(100)
    if (error) throw error
    const rows = (data ?? []) as DbReportRow[]
    if (rows.length === 0) return []

    const postIds = [...new Set(rows.map((r) => r.post_id))]
    const commentIds = rows
      .filter((r) => r.comment_id)
      .map((r) => r.comment_id as string)

    const { data: posts } = await supabase
      .from('community_posts')
      .select('id, title')
      .in('id', postIds)
    const postTitleMap = new Map(
      (posts ?? []).map((p: { id: string; title: string }) => [p.id, p.title]),
    )

    let commentPreviewMap = new Map<string, string>()
    if (commentIds.length > 0) {
      const { data: cmts } = await supabase
        .from('community_comments')
        .select('id, content')
        .in('id', commentIds)
      commentPreviewMap = new Map(
        (cmts ?? []).map((c: { id: string; content: string }) => [
          c.id,
          c.content.length > 60 ? `${c.content.slice(0, 60)}…` : c.content,
        ]),
      )
    }

    return rows.map((r) =>
      mapReport(
        r,
        postTitleMap.get(r.post_id),
        r.comment_id ? commentPreviewMap.get(r.comment_id) : undefined,
      ),
    )
  },

  async resolveReport(reportId, status) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录'
    const supabase = getSupabaseClient()
    const { error } = await supabase
      .from('community_reports')
      .update({
        status,
        resolved_at: new Date().toISOString(),
        resolved_by: user.id,
      })
      .eq('id', reportId)
    if (error) return error.message
    return null
  },

  async staffSoftDeletePost(postId) {
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

  async staffSoftDeleteComment(commentId) {
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

  async staffSetFeatured(postId, featured) {
    const supabase = getSupabaseClient()
    const { error } = await supabase
      .from('community_posts')
      .update({ is_featured: featured })
      .eq('id', postId)
      .eq('is_deleted', false)
    if (error) return error.message
    return null
  },

  async adminSetUserStatus(userId, status) {
    const supabase = getSupabaseClient()
    const { error } = await supabase
      .from('community_profiles')
      .update({ status })
      .eq('user_id', userId)
    if (error) return error.message
    return null
  },

  async lookupProfileForPost(postId) {
    const supabase = getSupabaseClient()
    const { data: post, error: postErr } = await supabase
      .from('community_posts')
      .select('author_id')
      .eq('id', postId)
      .maybeSingle()
    if (postErr || !post) return null
    const { data: prof, error: profErr } = await supabase
      .from('community_profiles')
      .select('user_id, username, status')
      .eq('user_id', post.author_id)
      .maybeSingle()
    if (profErr || !prof) return null
    return {
      authorId: prof.user_id,
      username: prof.username,
      status: prof.status as UserStatus,
    }
  },
}
