import { useEffect, useState } from 'react'
import { getSupabaseClient, isSupabaseConfigured } from '../lib/supabase'

const DEFAULT_MESSAGE = '社区正在进化中，非常抱歉'

function envMaintenanceEnabled(): boolean {
  const raw = import.meta.env.VITE_COMMUNITY_MAINTENANCE?.trim().toLowerCase()
  return raw === '1' || raw === 'true' || raw === 'yes'
}

function envMaintenanceMessage(): string | undefined {
  const msg = import.meta.env.VITE_COMMUNITY_MAINTENANCE_MESSAGE?.trim()
  return msg || undefined
}

async function fetchSupabaseMaintenance(): Promise<{
  enabled: boolean
  message: string
} | null> {
  if (!isSupabaseConfigured) return null
  try {
    const { data, error } = await getSupabaseClient()
      .from('community_site_status')
      .select('maintenance_enabled, message')
      .eq('id', 1)
      .maybeSingle()
    if (error || !data) return null
    const message =
      typeof data.message === 'string' && data.message.trim()
        ? data.message.trim()
        : DEFAULT_MESSAGE
    return {
      enabled: Boolean(data.maintenance_enabled),
      message,
    }
  } catch {
    return null
  }
}

export function useMaintenanceGate() {
  const envOn = envMaintenanceEnabled()
  const [state, setState] = useState<{
    loading: boolean
    inMaintenance: boolean
    message: string
  }>(() => ({
    loading: !envOn,
    inMaintenance: envOn,
    message: envMaintenanceMessage() ?? DEFAULT_MESSAGE,
  }))

  useEffect(() => {
    let cancelled = false

    async function run() {
      if (envMaintenanceEnabled()) {
        if (!cancelled) {
          setState({
            loading: false,
            inMaintenance: true,
            message: envMaintenanceMessage() ?? DEFAULT_MESSAGE,
          })
        }
        return
      }

      const remote = await fetchSupabaseMaintenance()
      if (cancelled) return

      if (remote?.enabled) {
        setState({
          loading: false,
          inMaintenance: true,
          message: remote.message,
        })
        return
      }

      setState({
        loading: false,
        inMaintenance: false,
        message: DEFAULT_MESSAGE,
      })
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
