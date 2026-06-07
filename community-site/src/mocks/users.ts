import type { User } from '../types/community'
import { DEMO_USER_ID } from '../types/community'

export const MOCK_USERS: User[] = [
  { id: DEMO_USER_ID, username: '演示用户' },
  { id: 'u-1', username: '小弹幕' },
  { id: 'u-2', username: '直播喵' },
  { id: 'u-3', username: '暖色主播' },
  { id: 'u-4', username: '配置达人' },
  { id: 'u-5', username: '新手小白' },
]

export function findUserByUsername(username: string): User | undefined {
  return MOCK_USERS.find((u) => u.username === username)
}

export function usernameExists(username: string): boolean {
  return MOCK_USERS.some((u) => u.username === username)
}
