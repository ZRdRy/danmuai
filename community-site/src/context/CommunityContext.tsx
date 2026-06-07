import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { getAuthService } from '../services/authService'
import { getCommunityService, getDataSourceMode } from '../services/communityService'
import type { DataSourceMode } from '../services/types'
import type {
  Comment,
  Post,
  PostCategoryKey,
  User,
} from '../types/community'

interface CommunityContextValue {
  posts: Post[]
  likedPostIds: Set<string>
  currentUser: User | null
  dataSource: DataSourceMode
  isLoading: boolean
  error: string | null
  login: (username: string, password: string) => Promise<string | null>
  register: (
    username: string,
    password: string,
    confirm: string,
  ) => Promise<string | null>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  addPost: (input: {
    title: string
    body: string
    category: PostCategoryKey
    tags: string[]
  }) => Promise<string | null>
  deletePost: (postId: string) => Promise<string | null>
  toggleLike: (postId: string) => Promise<string | null>
  addComment: (postId: string, body: string) => Promise<string | null>
  deleteComment: (commentId: string, postId: string) => Promise<string | null>
  getPost: (id: string) => Post | undefined
  getCommentsForPost: (postId: string) => Comment[]
  loadCommentsForPost: (postId: string) => Promise<void>
  isPostLiked: (postId: string) => boolean
}

const CommunityContext = createContext<CommunityContextValue | null>(null)

export function CommunityProvider({ children }: { children: ReactNode }) {
  const communityService = useMemo(() => getCommunityService(), [])
  const authService = useMemo(() => getAuthService(), [])
  const dataSource = getDataSourceMode()

  const [posts, setPosts] = useState<Post[]>([])
  const [likedPostIds, setLikedPostIds] = useState<Set<string>>(new Set())
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [commentsByPost, setCommentsByPost] = useState<Record<string, Comment[]>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const applyBootstrap = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const boot = await communityService.bootstrap()
      setPosts(boot.posts)
      setLikedPostIds(boot.likedPostIds)
      setCurrentUser(boot.currentUser)
      if (dataSource === 'mock' && boot.comments.length > 0) {
        const byPost: Record<string, Comment[]> = {}
        for (const c of boot.comments) {
          if (!byPost[c.postId]) byPost[c.postId] = []
          byPost[c.postId].push(c)
        }
        setCommentsByPost(byPost)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setIsLoading(false)
    }
  }, [communityService, dataSource])

  useEffect(() => {
    void applyBootstrap()
  }, [applyBootstrap])

  useEffect(() => {
    if (dataSource !== 'supabase') return
    let unsub: (() => void) | undefined
    void import('../lib/supabase').then(({ getSupabaseClient }) => {
      const { data } = getSupabaseClient().auth.onAuthStateChange(() => {
        void applyBootstrap()
      })
      unsub = () => data.subscription.unsubscribe()
    })
    return () => unsub?.()
  }, [dataSource, applyBootstrap])

  const refresh = useCallback(async () => {
    await applyBootstrap()
  }, [applyBootstrap])

  const login = useCallback(
    async (username: string, password: string) => {
      const err = await authService.login(username, password)
      if (err) return err
      await applyBootstrap()
      return null
    },
    [authService, applyBootstrap],
  )

  const register = useCallback(
    async (username: string, password: string, confirm: string) => {
      const err = await authService.register(username, password, confirm)
      if (err) return err
      await applyBootstrap()
      return null
    },
    [authService, applyBootstrap],
  )

  const logout = useCallback(async () => {
    await authService.logout()
    setCommentsByPost({})
    await applyBootstrap()
  }, [authService, applyBootstrap])

  const addPost = useCallback(
    async (input: {
      title: string
      body: string
      category: PostCategoryKey
      tags: string[]
    }) => {
      const err = await communityService.createPost(input)
      if (err) return err
      await applyBootstrap()
      return null
    },
    [communityService, applyBootstrap],
  )

  const deletePost = useCallback(
    async (postId: string) => {
      const err = await communityService.softDeletePost(postId)
      if (err) return err
      setCommentsByPost((prev) => {
        const next = { ...prev }
        delete next[postId]
        return next
      })
      await applyBootstrap()
      return null
    },
    [communityService, applyBootstrap],
  )

  const toggleLike = useCallback(
    async (postId: string) => {
      const result = await communityService.toggleLike(postId)
      if (typeof result === 'string') return result
      setLikedPostIds((prev) => {
        const next = new Set(prev)
        if (result.liked) next.add(postId)
        else next.delete(postId)
        return next
      })
      setPosts((prev) =>
        prev.map((p) =>
          p.id === postId ? { ...p, likeCount: result.likeCount } : p,
        ),
      )
      return null
    },
    [communityService],
  )

  const loadCommentsForPost = useCallback(
    async (postId: string) => {
      const list = await communityService.listComments(postId)
      setCommentsByPost((prev) => ({ ...prev, [postId]: list }))
    },
    [communityService],
  )

  const addComment = useCallback(
    async (postId: string, body: string) => {
      const err = await communityService.createComment(postId, body)
      if (err) return err
      await loadCommentsForPost(postId)
      await applyBootstrap()
      return null
    },
    [communityService, loadCommentsForPost, applyBootstrap],
  )

  const deleteComment = useCallback(
    async (commentId: string, postId: string) => {
      const err = await communityService.softDeleteComment(commentId, postId)
      if (err) return err
      await loadCommentsForPost(postId)
      await applyBootstrap()
      return null
    },
    [communityService, loadCommentsForPost, applyBootstrap],
  )

  const getPost = useCallback(
    (id: string) => posts.find((p) => p.id === id),
    [posts],
  )

  const getCommentsForPost = useCallback(
    (postId: string) => commentsByPost[postId] ?? [],
    [commentsByPost],
  )

  const isPostLiked = useCallback(
    (postId: string) => likedPostIds.has(postId),
    [likedPostIds],
  )

  const value = useMemo(
    () => ({
      posts,
      likedPostIds,
      currentUser,
      dataSource,
      isLoading,
      error,
      login,
      register,
      logout,
      refresh,
      addPost,
      deletePost,
      toggleLike,
      addComment,
      deleteComment,
      getPost,
      getCommentsForPost,
      loadCommentsForPost,
      isPostLiked,
    }),
    [
      posts,
      likedPostIds,
      currentUser,
      dataSource,
      isLoading,
      error,
      login,
      register,
      logout,
      refresh,
      addPost,
      deletePost,
      toggleLike,
      addComment,
      deleteComment,
      getPost,
      getCommentsForPost,
      loadCommentsForPost,
      isPostLiked,
    ],
  )

  return (
    <CommunityContext.Provider value={value}>
      {children}
    </CommunityContext.Provider>
  )
}

export function useCommunity(): CommunityContextValue {
  const ctx = useContext(CommunityContext)
  if (!ctx) throw new Error('useCommunity must be used within CommunityProvider')
  return ctx
}

export { DEMO_USER_ID } from '../types/community'
