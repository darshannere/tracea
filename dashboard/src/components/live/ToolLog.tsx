import { useMemo, useState, useEffect } from 'react'
import { useLive, type TimeFilter } from './LiveContext'
import { ToolLogRow } from './ToolLogRow'

const WINDOW_MS: Partial<Record<TimeFilter, number>> = {
  '5m': 5 * 60 * 1000,
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
}

export function ToolLog() {
  const { events, activeSessionFilter, activeAgentFilter, timeFilter } = useLive()

  // 30-second tick keeps the time window fresh even when no events arrive
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (timeFilter === 'all') return
    const id = setInterval(() => setTick((t) => t + 1), 30_000)
    return () => clearInterval(id)
  }, [timeFilter])

  const filtered = useMemo(() => {
    let result = events
    if (activeSessionFilter) {
      result = result.filter((e) => e.session_id === activeSessionFilter)
      if (activeAgentFilter) {
        const byAgent = result.filter((e) => e.agent_id === activeAgentFilter)
        if (byAgent.length > 0) result = byAgent
      }
    } else if (activeAgentFilter) {
      result = result.filter((e) => e.agent_id === activeAgentFilter)
    }
    const windowMs = WINDOW_MS[timeFilter]
    if (windowMs != null) {
      const cutoffTs = Date.now() - windowMs
      result = result.filter((e) => e.timestamp >= cutoffTs)
    }
    return result.slice().reverse()
  }, [events, activeSessionFilter, activeAgentFilter, timeFilter, tick])

  return (
    <div className="overflow-auto flex-1 font-mono text-xs">
      {filtered.map((event) => (
        <ToolLogRow key={event.id} event={event} />
      ))}

      {filtered.length === 0 && (
        <div className="flex items-center justify-center h-full text-zinc-400 text-xs py-8">
          {activeAgentFilter
            ? 'No events for selected agent yet...'
            : activeSessionFilter
              ? 'No events for selected session yet...'
              : 'No events yet — waiting for tool calls...'}
        </div>
      )}
    </div>
  )
}
