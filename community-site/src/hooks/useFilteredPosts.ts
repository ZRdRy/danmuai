import { useMemo } from 'react'
import type { Post, PostCategoryFilter, SortKind } from '../types/community'

export function useFilteredPosts(
  posts: Post[],
  search: string,
  category: PostCategoryFilter,
  sort: SortKind,
  likedPostIds: Set<string>,
): (Post & { likedByMe: boolean })[] {
  return useMemo(() => {
    let result = posts.map((p) => ({
      ...p,
      likedByMe: likedPostIds.has(p.id),
    }))

    const q = search.trim().toLowerCase()
    if (q) {
      result = result.filter(
        (p) =>
          p.title.toLowerCase().includes(q) ||
          p.excerpt.toLowerCase().includes(q) ||
          p.authorName.toLowerCase().includes(q) ||
          p.tags.some((t) => t.toLowerCase().includes(q)),
      )
    }

    if (category !== 'all') {
      result = result.filter((p) => p.category === category)
    }

    if (sort === 'latest') {
      result.sort(
        (a, b) =>
          new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
      )
    } else if (sort === 'hot') {
      result.sort(
        (a, b) =>
          b.likeCount + b.commentCount - (a.likeCount + a.commentCount),
      )
    } else {
      result.sort((a, b) => {
        const af = a.isFeatured ? 1 : 0
        const bf = b.isFeatured ? 1 : 0
        if (bf !== af) return bf - af
        return (
          new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        )
      })
    }

    return result
  }, [posts, search, category, sort, likedPostIds])
}
