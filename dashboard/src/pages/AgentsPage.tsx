import { useNavigate } from 'react-router-dom'
import { usePolling } from '@/hooks/usePolling'
import { useUser } from '@/hooks/UserContext'
import api from '@/lib/api'
import { AgentStat, agentColor, formatPlatform } from '@/components/agents/AgentBar'
import { Bot, AlertTriangle, DollarSign, Clock, Activity, ExternalLink } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function formatCost(cost: number): string {
  if (cost === 0) return '$0.00'
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  return `$${cost.toFixed(2)}`
}

export function AgentsPage() {
  const navigate = useNavigate()
  const { selectedUser } = useUser()

  const { data: agentsData } = usePolling(async () => {
    const params = selectedUser ? `?user_id=${encodeURIComponent(selectedUser)}` : ''
    const res = await api.get<{ agents: AgentStat[] }>(`/api/v1/agents${params}`)
    return res.data
  })

  const agents: AgentStat[] = agentsData?.agents ?? []
  const agentIds = agents.map((a) => a.agent_id)

  const totalCost = agents.reduce((sum, a) => sum + a.total_cost, 0)
  const totalSessions = agents.reduce((sum, a) => sum + a.session_count, 0)
  const totalErrors = agents.reduce((sum, a) => sum + a.error_session_count, 0)

  if (agentsData === null) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Bot className="h-5 w-5 text-accent" />
          <h2 className="text-xl font-semibold">Agents</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      </div>
    )
  }

  if (agents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <Bot className="h-8 w-8 mb-2" />
        <p className="text-sm font-medium">No agents tracked yet</p>
        <p className="text-xs text-zinc-400">Agents appear automatically when sessions are recorded</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Bot className="h-5 w-5 text-accent" />
        <h2 className="text-xl font-semibold">Agents</h2>
        <span className="text-sm text-zinc-500">{agents.length} tracked</span>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="border border-zinc-200 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 mb-1">
            <Activity className="h-3.5 w-3.5 text-indigo-500" />
            <span className="text-xs text-zinc-500">Total Sessions</span>
          </div>
          <div className="text-xl font-semibold text-zinc-900">{totalSessions.toLocaleString()}</div>
        </div>
        <div className="border border-zinc-200 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 mb-1">
            <DollarSign className="h-3.5 w-3.5 text-emerald-500" />
            <span className="text-xs text-zinc-500">Total Cost</span>
          </div>
          <div className="text-xl font-semibold text-zinc-900">{formatCost(totalCost)}</div>
        </div>
        <div className="border border-zinc-200 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
            <span className="text-xs text-zinc-500">Error Sessions</span>
          </div>
          <div className="text-xl font-semibold text-zinc-900">{totalErrors.toLocaleString()}</div>
        </div>
      </div>

      {/* Agent cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent) => {
          const color = agentColor(agent.agent_id, agentIds)
          const errorRate = agent.session_count > 0
            ? (agent.error_session_count / agent.session_count) * 100
            : 0
          const cleanRate = 100 - errorRate
          const platformLabel = formatPlatform(agent.platform)

          return (
            <div
              key={agent.agent_id}
              className="border border-zinc-200 rounded-lg p-4 bg-white hover:border-zinc-300 hover:shadow-sm transition-all cursor-pointer"
              onClick={() => navigate('/sessions', { state: { agent: agent.agent_id } })}
            >
              {/* Agent header */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2 min-w-0">
                  <div className={cn('h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0', color.bg)}>
                    <Bot className={cn('h-4 w-4', color.text)} />
                  </div>
                  <div className="min-w-0">
                    <div className={cn('text-xs font-mono font-semibold truncate', color.text)}>
                      {agent.agent_id}
                    </div>
                    {platformLabel && (
                      <span className="text-xs text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded mt-0.5 inline-block">
                        {platformLabel}
                      </span>
                    )}
                  </div>
                </div>
                <ExternalLink className="h-3.5 w-3.5 text-zinc-400 flex-shrink-0 mt-1" />
              </div>

              {/* Error/clean bar */}
              <div className="mb-3">
                <div className="flex justify-between text-xs text-zinc-500 mb-1">
                  <span>Health</span>
                  <span className={errorRate > 0 ? 'text-red-500 font-medium' : 'text-emerald-600 font-medium'}>
                    {errorRate.toFixed(0)}% error rate
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-zinc-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-emerald-500"
                    style={{ width: `${cleanRate}%` }}
                  />
                </div>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 gap-2">
                <div className="text-center py-2 px-3 rounded-md bg-zinc-50">
                  <div className="text-lg font-semibold text-zinc-900">{agent.session_count}</div>
                  <div className="text-xs text-zinc-500">Sessions</div>
                </div>
                <div className="text-center py-2 px-3 rounded-md bg-zinc-50">
                  <div className="text-lg font-semibold text-zinc-900">{formatCost(agent.total_cost)}</div>
                  <div className="text-xs text-zinc-500">Total Cost</div>
                </div>
              </div>

              {/* Last active */}
              <div className="flex items-center gap-1.5 mt-3 text-xs text-zinc-400">
                <Clock className="h-3 w-3" />
                <span>Last active {formatRelative(agent.last_active)}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
