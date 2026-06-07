import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

const LOADING_MS = 300

export function usePageLoading(): boolean {
  const location = useLocation()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    const t = window.setTimeout(() => setLoading(false), LOADING_MS)
    return () => window.clearTimeout(t)
  }, [location.pathname])

  return loading
}
