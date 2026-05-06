import { useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { usePolling } from '@/hooks/usePolling'
import api from '@/lib/api'
import {
  PlayCircle, MessageSquare, Wrench, CheckCircle2, AlertCircle, StopCircle,
  ChevronLeft, Clock, DollarSign, Hash
} from 'lucide-react'
import * as Popover from '@radix-ui/react-popover'
import { cn } from '@/lib/utils'

type EventType = 'session_start' | 'chat.completion' | 'tool_call' | 'tool_result' | 'error' | 'session_end'

const EVENT_TYPE_ICONS: Record<EventType, React.ElementType> = {
  'session_start': PlayCircle,
  'chat.completion': MessageSquare,
  'tool_call': Wrench,
  'tool_result': CheckCircle2,
  'error': AlertCircle,
  'session_end': StopCircle,
}

const ALL_EVENT_TYPES: EventType[] = [
  'session_start', 'chat.completion', 'tool_call', 'tool_result', 'error', 'session_end',
]

const EVENT_TYPE_LABELS: Record<EventType, string> = {
  'session_start': 'Session Start',
  'chat.completion': 'Chat Completion',
  'tool_call': 'Tool Call',
  'tool_result': 'Tool Result',
  'error': 'Error',
  'session_end': 'Session End',
}

interface Event {
  event_id: string
  session_id: string
  event_type: string
  timestamp: string
  sequence: number
  model?: string
  tokens_used?: number
  cost_usd?: number
  tool_name?: string
  duration_ms?: number
  status_code?: number
  error_message?: string
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}

function truncate(str: string, len: number): string {
  return str.length > len ? str.slice(0, len) + '...' : str
}

function getKeyFields(event: Event): Record<string, string | number | undefined> {
  switch (event.event_type) {
    case 'chat.completion':
      return {
        model: event.model,
        tokens: event.tokens_used,
        cost: event.cost_usd,
      }
    case 'tool_call':
      return {
        tool: event.tool_name,
        duration: event.duration_ms != null ? `${event.duration_ms}ms` : undefined,
      }
    case 'tool_result':
      return {
        tool: event.tool_name,
        status: event.status_code,
      }
    case 'error':
      return {
        message: event.error_message,
        status: event.status_code,
      }
    default:
      return {}
  }
}

export function EventTimelinePage() {
  const { id: sessionId } = useParams<{ id: string }>()
  const [filterTypes, setFilterTypes] = useState<Set<EventType>>(new Set(ALL_EVENT_TYPES))
  const [filterOpen, setFilterOpen] = useState(false)

  const { data, error } = usePolling(async () => {
    const res = await api.get<{ events: Event[] }>(`/api/v1/sessions/${sessionId}/events`)
    return res.data
  })

  const events: Event[] = data?.events ?? []

  const filteredEvents = useMemo(() => {
    return events.filter((e) => filterTypes.has(e.event_type as EventType))
  }, [events, filterTypes])

  const session = useMemo(() => {
    if (events.length === 0) return null
    const first = events[0]
    const last = events[events.length - 1]
    const totalCost = events.reduce((sum, e) => sum + (e.cost_usd ?? 0), 0)
    const totalTokens = events.reduce((sum, e) => sum + (e.tokens_used ?? 0), 0)
    let durationMs: number | null = null
    if (first?.timestamp && last?.timestamp) {
      durationMs = new Date(last.timestamp).getTime() - new Date(first.timestamp).getTime()
    }
    return {
      session_id: sessionId,
      started_at: first?.timestamp,
      ended_at: last?.timestamp,
      duration_ms: durationMs,
      total_cost: totalCost,
      total_tokens: totalTokens,
    }
  }, [events, sessionId])

  const toggleType = (type: EventType) => {
    setFilterTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">Failed to load data</p>
        <p className="text-xs text-muted-foreground/60">Retrying in 5 seconds...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link
        to="/sessions"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronLeft className="h-4 w-4" />
        Back to Sessions
      </Link>

      {session && (
        <div className="bg-muted/50 border border-border rounded-lg p-4 grid grid-cols-5 gap-4 text-sm">
          <div>
            <div className="text-xs text-muted-foreground mb-1">Session ID</div>
            <div className="font-mono text-xs text-foreground">{session.session_id?.slice(0, 12)}...</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Started</div>
            <div className="text-foreground">{session.started_at ? new Date(session.started_at).toLocaleString() : '-'}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Duration</div>
            <div className="text-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {session.duration_ms != null ? `${(session.duration_ms / 1000).toFixed(1)}s` : '-'}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Total Cost</div>
            <div className="text-foreground flex items-center gap-1">
              <DollarSign className="h-3 w-3" />
              {session.total_cost?.toFixed(4) ?? '-'}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Total Tokens</div>
            <div className="text-foreground flex items-center gap-1">
              <Hash className="h-3 w-3" />
              {session.total_tokens?.toLocaleString() ?? '-'}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Event Timeline</h2>
        <Popover.Root open={filterOpen} onOpenChange={setFilterOpen}>
          <Popover.Trigger asChild>
            <button className="text-sm text-muted-foreground hover:text-foreground border border-input rounded-md px-3 py-1.5 flex items-center gap-2 transition-colors">
              Filter
              <span className="text-xs bg-muted rounded px-1.5 py-0.5">
                {filterTypes.size}/{ALL_EVENT_TYPES.length}
              </span>
            </button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              className="relative bg-white border border-border rounded-lg shadow-lg p-3 min-w-48 z-50"
              sideOffset={4}
            >
              <div className="space-y-2">
                {ALL_EVENT_TYPES.map((type) => (
                  <label key={type} className="flex items-center gap-2 cursor-pointer text-sm">
                    <input
                      type="checkbox"
                      checked={filterTypes.has(type)}
                      onChange={() => toggleType(type)}
                      className="rounded border-input"
                    />
                    {EVENT_TYPE_LABELS[type]}
                  </label>
                ))}
              </div>
              <Popover.Close className="absolute top-2 right-2 text-muted-foreground/60 hover:text-muted-foreground">
                ✕
              </Popover.Close>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      </div>

      {filteredEvents.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
          <Clock className="h-8 w-8 mb-2" />
          <p className="text-sm font-medium">No events in this session</p>
          <p className="text-xs text-muted-foreground/60">Events will appear here once the session has activity</p>
        </div>
      ) : (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground w-8"></th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Time</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Details</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.map((event) => {
                const Icon = EVENT_TYPE_ICONS[event.event_type as EventType] ?? Clock
                const keyFields = getKeyFields(event)
                return (
                  <tr key={event.event_id} className="border-b border-border/50 hover:bg-muted/50 transition-colors">
                    <td className="px-4 py-3">
                      <Icon className={cn(
                        'h-4 w-4',
                        event.event_type === 'error' ? 'text-red-500' :
                          event.event_type === 'session_start' ? 'text-green-500' :
                            event.event_type === 'session_end' ? 'text-muted-foreground/60' : 'text-accent'
                      )} />
                    </td>
                    <td className="px-4 py-3 text-foreground font-medium">
                      {EVENT_TYPE_LABELS[event.event_type as EventType] ?? event.event_type}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {formatTimestamp(event.timestamp)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {event.event_type === 'chat.completion' && (
                        <span>
                          {keyFields.model} · {keyFields.tokens?.toLocaleString()} tokens · ${Number(keyFields.cost ?? 0).toFixed(4)}
                        </span>
                      )}
                      {event.event_type === 'tool_call' && (
                        <span>
                          {keyFields.tool} · {keyFields.duration}
                        </span>
                      )}
                      {event.event_type === 'tool_result' && (
                        <span className={cn(
                          keyFields.status === 200 ? 'text-green-600' : 'text-red-600'
                        )}>
                          {keyFields.tool} · {keyFields.status}
                        </span>
                      )}
                      {event.event_type === 'error' && (
                        <span className="text-red-600">
                          {truncate(event.error_message ?? '', 60)}
                          {keyFields.status ? ` [${keyFields.status}]` : ''}
                        </span>
                      )}
                      {(event.event_type === 'session_start' || event.event_type === 'session_end') && (
                        <span className="text-muted-foreground/60">-</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
