import { useState, useEffect, useRef, useCallback } from 'react'

export function usePolling<T>(fetchFn: () => Promise<T>, interval = 5000) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Use a ref so the interval never re-subscribes when the component re-renders
  // with a new inline arrow function. Without this, each state update recreates
  // the effect, which clears + restarts the interval AND calls tick() immediately,
  // producing a request storm.
  const fetchRef = useRef(fetchFn)
  fetchRef.current = fetchFn

  const tick = useCallback(async () => {
    try {
      setLoading(true)
      const result = await fetchRef.current()
      setData(result)
      setError(null)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, []) // stable — fetchRef.current always points to the latest fetchFn

  useEffect(() => {
    tick()
    const id = setInterval(tick, interval)
    return () => clearInterval(id)
  }, [tick, interval])

  return { data, error, loading, refetch: tick }
}
