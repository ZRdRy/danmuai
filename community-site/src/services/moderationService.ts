import { isSupabaseConfigured } from '../lib/supabase'
import { mockModerationService } from './mockModerationService'
import { supabaseModerationService } from './supabaseModerationService'
import type { ModerationService } from './types'

export function getModerationService(): ModerationService {
  return isSupabaseConfigured ? supabaseModerationService : mockModerationService
}
