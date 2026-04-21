import { useState, useEffect } from 'react'

export function useAuth() {
  const [hasKey, setHasKey] = useState(() => {
    const stored = localStorage.getItem('tracea_api_key')
    if (!stored) {
      // Dev mode: auto-set a placeholder so the UI works without a real API key
      localStorage.setItem('tracea_api_key', 'dev-mode')
    }
    return !!localStorage.getItem('tracea_api_key')
  })

  useEffect(() => {
    const handleAuthError = () => {
      setHasKey(false)
    }
    window.addEventListener('tracea:auth-error', handleAuthError)
    return () => window.removeEventListener('tracea:auth-error', handleAuthError)
  }, [])

  return { hasKey }
}
