import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'
import api from '@/lib/api'
import { useUser } from '@/hooks/UserContext'

export interface ToolEvent {
  id: string
  tool_name: string
  hook_type: 'PreToolUse' | 'PostToolUse'
  session_id: string
  agent_id: string | null
  tool_call_id: string | null
  timestamp: number
  duration_ms: number | null
  exit_status: number | null
  tool_summary: string | null
  nearest_input_tokens: number | null
  nearest_output_tokens: number | null
}

export interface LiveSession {
  session_id: string
  agent_id: string | null
  platform: string | null
  started_at: string
  ended_at: string | null
  last_event_at: string | null
  duration_ms: number | null
  event_count: number | null
  total_cost: number | null
  total_tokens: number | null
}

export type TimeFilter = '5m' | '15m' | '1h' | 'all'

interface LiveState {
  events: ToolEvent[]
  sessions: LiveSession[]
  activeSessionFilter: string | null
  activeAgentFilter: string | null
  timeFilter: TimeFilter
  isLoading: boolean
  health: {
    lastEventTs: string | null
    errorRate: number
    errorCount: number
    totalCalls: number
  } | null
}

interface LiveActions {
  setSessionFilter: (id: string | null) => void
  setAgentFilter: (id: string | null) => void
  setTimeFilter: (f: TimeFilter) => void
  refresh: () => Promise<void>
}

const LiveContext = createContext<(LiveState & LiveActions) | null>(null)

export function LiveProvider({ children }: { children: ReactNode }) {
  const { selectedUser } = useUser()
  const [events, setEvents] = useState<ToolEvent[]>([])
  const [sessions, setSessions] = useState<LiveSession[]>([])
  const [activeSessionFilter, setSessionFilter] = useState<string | null>(null)
  const [activeAgentFilter, setAgentFilter] = useState<string | null>(null)
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('all')
  const [isLoading, setIsLoading] = useState(false)
  const [health, setHealth] = useState<LiveState['health']>(null)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    try {
      const userParam = selectedUser ? `&user_id=${encodeURIComponent(selectedUser)}` : ''
      const [eventsRes, sessionsRes, healthRes] = await Promise.all([
        api.get<ToolEvent[]>(
          activeSessionFilter
            ? `/api/v1/observagent/events?session_id=${activeSessionFilter}${userParam}&limit=500`
            : `/api/v1/observagent/events?limit=200${userParam}`
        ),
        api.get<{ sessions: LiveSession[] }>(`/api/v1/observagent/sessions${userParam ? `?user_id=${encodeURIComponent(selectedUser)}` : ''}`),
        api.get(`/api/v1/observagent/health${userParam ? `?user_id=${encodeURIComponent(selectedUser)}` : ''}`),
      ])
      setEvents(eventsRes.data)
      setSessions(sessionsRes.data.sessions)
      setHealth(healthRes.data)
    } catch {
      // silent fail — polling will retry
    } finally {
      setIsLoading(false)
    }
  }, [activeSessionFilter, selectedUser])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [refresh])

  const handleSetSessionFilter = useCallback((id: string | null) => {
    setSessionFilter(id)
    setAgentFilter(null)
  }, [])

  const handleSetAgentFilter = useCallback((id: string | null) => {
    setAgentFilter(id)
    // When filtering by agent, also narrow to their latest session if no session filter
    if (id && !activeSessionFilter) {
      const latest = sessions.find((s) => s.agent_id === id)
      if (latest) setSessionFilter(latest.session_id)
    }
  }, [sessions, activeSessionFilter])

  return (
    <LiveContext.Provider
      value={{
        events,
        sessions,
        activeSessionFilter,
        activeAgentFilter,
        timeFilter,
        isLoading,
        health,
        setSessionFilter: handleSetSessionFilter,
        setAgentFilter: handleSetAgentFilter,
        setTimeFilter,
        refresh,
      }}
    >
      {children}
    </LiveContext.Provider>
  )
}

export function useLive() {
  const ctx = useContext(LiveContext)
  if (!ctx) throw new Error('useLive must be used inside LiveProvider')
  return ctx
}
