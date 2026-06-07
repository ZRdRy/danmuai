const STORAGE_KEY = 'danmu-community-device-id'

/** Stable per-browser id for registration rate limiting (not secret). */
export function getOrCreateDeviceId(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEY)?.trim()
    if (existing && existing.length >= 16 && existing.length <= 128) {
      return existing
    }
    const id = crypto.randomUUID()
    localStorage.setItem(STORAGE_KEY, id)
    return id
  } catch {
    return crypto.randomUUID()
  }
}
