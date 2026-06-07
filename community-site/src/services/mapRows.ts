import type { Comment, Post } from '../types/community'
import type { DbCommentRow, DbPostRow, DbProfileRow } from './types'

export function excerptFromContent(content: string): string {
  const t = content.trim()
  return t.length > 80 ? `${t.slice(0, 80)}…` : t
}

export function authorNameFromProfile(
  profile: DbProfileRow | undefined,
  authorId: string,
): string {
  if (!profile) return authorId.slice(0, 8)
  return profile.display_name?.trim() || profile.username
}

export function mapPostRow(
  row: DbPostRow,
  profile: DbProfileRow | undefined,
): Post {
  return {
    id: row.id,
    title: row.title,
    excerpt: excerptFromContent(row.content),
    body: row.content,
    authorId: row.author_id,
    authorName: authorNameFromProfile(profile, row.author_id),
    category: row.category,
    tags: row.tags ?? [],
    likeCount: row.like_count,
    commentCount: row.comment_count,
    createdAt: row.created_at,
    isFeatured: row.is_featured,
  }
}

export function mapCommentRow(
  row: DbCommentRow,
  profile: DbProfileRow | undefined,
): Comment {
  return {
    id: row.id,
    postId: row.post_id,
    authorId: row.author_id,
    authorName: authorNameFromProfile(profile, row.author_id),
    body: row.content,
    createdAt: row.created_at,
  }
}

export async function fetchProfilesMap(
  userIds: string[],
  fetcher: (ids: string[]) => Promise<DbProfileRow[]>,
): Promise<Map<string, DbProfileRow>> {
  const unique = [...new Set(userIds.filter(Boolean))]
  const map = new Map<string, DbProfileRow>()
  if (unique.length === 0) return map
  const rows = await fetcher(unique)
  for (const r of rows) {
    map.set(r.user_id, r)
  }
  return map
}
