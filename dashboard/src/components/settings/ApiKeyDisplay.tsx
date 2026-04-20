import { useState } from 'react'
import { Eye, EyeOff, Copy, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function ApiKeyDisplay() {
  const stored = localStorage.getItem('tracea_api_key') ?? ''
  const [apiKey] = useState<string>(stored)
  const [visible, setVisible] = useState(false)
  const [copied, setCopied] = useState(false)

  const displayValue = visible
    ? apiKey || 'Not set'
    : apiKey
    ? '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022' + apiKey.slice(-4)
    : 'Not set'

  const handleCopy = () => {
    if (!apiKey) return
    navigator.clipboard.writeText(apiKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-4">
      <label className="block text-sm font-medium text-zinc-700 mb-2">API Key</label>
      <div className="flex items-center gap-2">
        <div className="flex-1 flex items-center gap-2 bg-white border border-zinc-300 rounded-md px-3 py-2 text-sm font-mono min-h-[36px]">
          <span className="flex-1 break-all">{displayValue}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setVisible(!visible)}
          title={visible ? 'Hide API key' : 'Reveal API key'}
          disabled={!apiKey}
        >
          {visible ? (
            <EyeOff className="h-4 w-4 text-zinc-500" />
          ) : (
            <Eye className="h-4 w-4 text-zinc-500" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleCopy}
          title="Copy API key"
          disabled={!apiKey}
          className={cn(copied && 'text-green-600')}
        >
          {copied ? (
            <Check className="h-4 w-4 text-green-600" />
          ) : (
            <Copy className="h-4 w-4 text-zinc-500" />
          )}
        </Button>
      </div>
    </div>
  )
}
