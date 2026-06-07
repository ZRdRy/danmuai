import { isSupabaseConfigured } from '../lib/supabase'
import { mockCommunityService } from './mockCommunityService'
import { supabaseCommunityService } from './supabaseCommunityService'
import type { CommunityService } from './types'

export function getCommunityService(): CommunityService {
  return isSupabaseConfigured ? supabaseCommunityService : mockCommunityService
}

export function getDataSourceMode(): 'mock' | 'supabase' {
  return isSupabaseConfigured ? 'supabase' : 'mock'
}
