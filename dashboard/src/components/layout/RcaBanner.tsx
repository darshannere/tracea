import { useState, useEffect } from 'react'
import { CloudOff } from 'lucide-react'
import api from '@/lib/api'

interface RcaConfig {
  backend: string
  model: string
}

export function RcaBanner() {
  const [rcaConfig, setRcaConfig] = useState<RcaConfig>({
    backend: (window as unknown as Record<string, string>).TRACEA_RCA_BACKEND ?? 'disabled',
    model: '',
  })

  useEffect(() => {
    api
      .get<RcaConfig>('/api/v1/config/rca')
      .then((res) => setRcaConfig(res.data))
      .catch(() => {
        // Fallback to window.TRACEA_RCA_BACKEND if API call fails
        setRcaConfig({
          backend: (window as unknown as Record<string, string>).TRACEA_RCA_BACKEND ?? 'disabled',
          model: '',
        })
      })
  }, [])

  const isCloudRca = rcaConfig.backend === 'openai' || rcaConfig.backend === 'anthropic'

  if (!isCloudRca) return null

  return (
    <div
      className="bg-orange-500 text-white flex items-center justify-center gap-2 text-sm font-medium"
      style={{ height: '40px', width: '100%' }}
    >
      <CloudOff className="h-4 w-4" />
      <span>Using cloud RCA backend — costs may apply</span>
    </div>
  )
}
