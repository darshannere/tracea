import { useState } from 'react'
import { ShieldAlert, KeyRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface AuthErrorStateProps {
  heading?: string
  body?: string
}

export function AuthErrorState({
  heading = 'Authentication required',
  body = 'Enter your API key to continue',
}: AuthErrorStateProps) {
  const [apiKey, setApiKey] = useState('')
  const [visible, setVisible] = useState(false)

  const handleSave = () => {
    if (!apiKey.trim()) return
    localStorage.setItem('tracea_api_key', apiKey.trim())
    window.location.reload()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSave()
  }

  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center p-8">
      <ShieldAlert size={48} className="text-indigo-500" />
      <h2 className="text-xl font-semibold text-zinc-800">{heading}</h2>
      <p className="text-sm text-zinc-500 max-w-sm">{body}</p>

      <div className="w-full max-w-sm flex items-center gap-2 mt-2">
        <Input
          type={visible ? 'text' : 'password'}
          placeholder="Paste your tracea API key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 font-mono text-sm"
        />
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setVisible(!visible)}
          title={visible ? 'Hide' : 'Show'}
        >
          {visible ? (
            <span className="text-xs text-zinc-500">hide</span>
          ) : (
            <span className="text-xs text-zinc-500">show</span>
          )}
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!apiKey.trim()}
        >
          <KeyRound className="h-4 w-4 mr-1" />
          Connect
        </Button>
      </div>

      <p className="text-xs text-zinc-400 mt-1">
        Find your API key in the server console or <code className="bg-zinc-100 px-1 rounded">data/api_key.txt</code>
      </p>
    </div>
  )
}
