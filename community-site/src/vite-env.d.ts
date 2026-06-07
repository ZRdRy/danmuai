/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_ANON_KEY?: string
  readonly VITE_COMMUNITY_MAINTENANCE?: string
  readonly VITE_COMMUNITY_MAINTENANCE_MESSAGE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
