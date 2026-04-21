import { useState, useEffect } from 'react'
import { AlertTriangle, X } from 'lucide-react'

export function ConnectionErrorBanner() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>

    const show = () => {
      setVisible(true)
      // Auto-hide after 8s so it doesn't linger when the backend comes back
      clearTimeout(timeout)
      timeout = setTimeout(() => setVisible(false), 8000)
    }

    window.addEventListener('tracea:connection-error', show)
    return () => {
      window.removeEventListener('tracea:connection-error', show)
      clearTimeout(timeout)
    }
  }, [])

  if (!visible) return null

  return (
    <div className="flex items-center gap-2 bg-red-600 text-white text-sm px-4 py-2">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span className="flex-1">
        Backend unreachable — make sure the tracea server is running on port 8080.
        Run: <code className="font-mono bg-red-700 px-1 rounded">uvicorn tracea.server.main:app --port 8080</code>
      </span>
      <button onClick={() => setVisible(false)} className="shrink-0 hover:opacity-75">
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
