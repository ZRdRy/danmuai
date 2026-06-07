import type { CommunityReport, ModerationService } from './types'
import { getAuthService } from './authService'
import { getCommunityService } from './communityService'
import { mockStaffSetFeatured } from './mockCommunityService'

const reports: CommunityReport[] = []
let nextReportId = 1

function mockRoleFromUsername(username: string) {
  if (username === 'admin') return 'admin' as const
  if (username === 'mod') return 'moderator' as const
  return 'user' as const
}

export const mockModerationService: ModerationService = {
  mode: 'mock',

  async reportPost(postId, reason) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再举报'
    if (reports.some((r) => r.reporterId === user.id && r.postId === postId && r.targetType === 'post')) {
      return '您已举报过该内容'
    }
    const post = await getCommunityService().getPost(postId)
    reports.push({
      id: `rep-${nextReportId++}`,
      reporterId: user.id,
      targetType: 'post',
      postId,
      reason,
      status: 'pending',
      createdAt: new Date().toISOString(),
      postTitle: post?.title,
    })
    return null
  },

  async reportComment(postId, commentId, reason) {
    const user = await getAuthService().getCurrentUser()
    if (!user) return '请先登录后再举报'
    if (
      reports.some(
        (r) =>
          r.reporterId === user.id &&
          r.commentId === commentId &&
          r.targetType === 'comment',
      )
    ) {
      return '您已举报过该内容'
    }
    const comments = await getCommunityService().listComments(postId)
    const c = comments.find((x) => x.id === commentId)
    reports.push({
      id: `rep-${nextReportId++}`,
      reporterId: user.id,
      targetType: 'comment',
      postId,
      commentId,
      reason,
      status: 'pending',
      createdAt: new Date().toISOString(),
      postTitle: (await getCommunityService().getPost(postId))?.title,
      commentPreview: c?.body,
    })
    return null
  },

  async listPendingReports() {
    const user = await getAuthService().getCurrentUser()
    const role = user ? mockRoleFromUsername(user.username) : 'user'
    if (role !== 'moderator' && role !== 'admin') return []
    return reports.filter((r) => r.status === 'pending')
  },

  async resolveReport(reportId, status) {
    const r = reports.find((x) => x.id === reportId)
    if (!r) return '举报不存在'
    r.status = status
    return null
  },

  async staffSoftDeletePost(postId) {
    return getCommunityService().softDeletePost(postId)
  },

  async staffSoftDeleteComment(commentId) {
    const svc = getCommunityService()
    const posts = await svc.listPosts()
    for (const p of posts) {
      const cmts = await svc.listComments(p.id)
      if (cmts.some((c) => c.id === commentId)) {
        return svc.softDeleteComment(commentId, p.id)
      }
    }
    return '评论不存在'
  },

  async staffSetFeatured(postId, featured) {
    return mockStaffSetFeatured(postId, featured)
  },

  async adminSetUserStatus() {
    return null
  },

  async lookupProfileForPost(postId) {
    const post = await getCommunityService().getPost(postId)
    if (!post) return null
    return {
      authorId: post.authorId,
      username: post.authorName,
      status: 'active' as const,
    }
  },
}
