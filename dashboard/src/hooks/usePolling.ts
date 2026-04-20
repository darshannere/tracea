import { useState, useEffect, useCallback } from 'react'

export function usePolling<T>(fetchFn: () => Promise<T>, interval = 5000) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const tick = useCallback(async () => {
    try {
      setLoading(true)
      const result = await fetchFn()
      setData(result)
      setError(null)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [fetchFn])

  useEffect(() => {
    tick()
    const id = setInterval(tick, interval)
    return () => clearInterval(id)
  }, [tick, interval])

  return { data, error, loading, refetch: tick }
}
