import { useLive } from './LiveContext'
import { cn } from '@/lib/utils'
import { Activity, Clock, Bot } from 'lucide-react'

export function AgentTree() {
  const {
    sessions,
    activeSessionFilter,
    activeAgentFilter,
    setSessionFilter,
    setAgentFilter,
  } = useLive()

  // Group sessions by agent_id
  const agentsMap = new Map<string, typeof sessions>()
  const soloSessions: typeof sessions = []

  for (const s of sessions) {
    if (s.agent_id) {
      if (!agentsMap.has(s.agent_id)) agentsMap.set(s.agent_id, [])
      agentsMap.get(s.agent_id)!.push(s)
    } else {
      soloSessions.push(s)
    }
  }

  const agentEntries = Array.from(agentsMap.entries()).sort((a, b) => {
    const aLast = a[1][0]?.last_event_at ?? ''
    const bLast = b[1][0]?.last_event_at ?? ''
    return bLast.localeCompare(aLast)
  })

  const isActive = (sid: string, aid?: string | null) => {
    if (activeAgentFilter && aid === activeAgentFilter) return true
    if (!activeAgentFilter && activeSessionFilter === sid) return true
    return false
  }

  return (
    <div className="flex-1 overflow-auto py-1">
      {/* Agents with sessions */}
      {agentEntries.map(([agentId, agentSessions]) => {
        const isAgentActive = activeAgentFilter === agentId
        return (
          <div key={agentId} className="mb-1">
            <button
              onClick={() => setAgentFilter(isAgentActive ? null : agentId)}
              className={cn(
                'w-full flex items-center gap-2 px-2 py-1.5 text-xs font-mono transition-colors',
                isAgentActive
                  ? 'bg-accent/10 text-accent'
                  : 'text-zinc-700 hover:bg-zinc-100'
              )}
            >
              <Bot className="h-3 w-3 shrink-0" />
              <span className="truncate">{agentId.slice(0, 14)}</span>
              <span className="ml-auto text-[10px] text-zinc-400">{agentSessions.length}</span>
            </button>
            <div className="ml-4 border-l border-zinc-200">
              {agentSessions.map((s) => (
                <button
                  key={s.session_id}
                  onClick={() => setSessionFilter(isActive(s.session_id, agentId) ? null : s.session_id)}
                  className={cn(
                    'w-full flex items-center gap-2 px-2 py-1 text-[10px] font-mono transition-colors',
                    isActive(s.session_id, agentId)
                      ? 'bg-accent/10 text-accent'
                      : 'text-zinc-500 hover:bg-zinc-50'
                  )}
                >
                  <Activity className="h-2.5 w-2.5 shrink-0" />
                  <span className="truncate">{s.session_id.slice(0, 10)}…</span>
                  {s.ended_at ? (
                    <Clock className="h-2.5 w-2.5 shrink-0 text-zinc-400 ml-auto" />
                  ) : (
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0 ml-auto" />
                  )}
                </button>
              ))}
            </div>
          </div>
        )
      })}

      {/* Solo sessions */}
      {soloSessions.length > 0 && (
        <div className="mt-2 pt-2 border-t border-zinc-200">
          <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-zinc-400 font-semibold">
            Solo Sessions
          </div>
          {soloSessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => setSessionFilter(isActive(s.session_id) ? null : s.session_id)}
              className={cn(
                'w-full flex items-center gap-2 px-2 py-1 text-[10px] font-mono transition-colors',
                isActive(s.session_id)
                  ? 'bg-accent/10 text-accent'
                  : 'text-zinc-500 hover:bg-zinc-50'
              )}
            >
              <Activity className="h-2.5 w-2.5 shrink-0" />
              <span className="truncate">{s.session_id.slice(0, 12)}…</span>
              {s.ended_at ? (
                <Clock className="h-2.5 w-2.5 shrink-0 text-zinc-400 ml-auto" />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0 ml-auto" />
              )}
            </button>
          ))}
        </div>
      )}

      {sessions.length === 0 && (
        <div className="px-2 py-4 text-xs text-zinc-400 text-center">
          No sessions yet
        </div>
      )}
    </div>
  )
}
