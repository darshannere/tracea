import { useState, useEffect } from 'react'

export function useAuth() {
  const [hasKey, setHasKey] = useState(() => {
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
