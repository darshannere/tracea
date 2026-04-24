import { useState, useEffect } from 'react'

export function useAuth() {
  const [hasKey, setHasKey] = useState(() => {
    const stored = localStorage.getItem('tracea_api_key')
    return !!stored && stored !== ''
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
