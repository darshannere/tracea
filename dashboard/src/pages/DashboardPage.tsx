import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePolling } from '@/hooks/usePolling'
import { useUser } from '@/hooks/UserContext'
import api from '@/lib/api'
import { StatCards } from '@/components/charts/StatCards'
import {
  CostChart,
  TokenChart,
  EventsChart,
  DurationDistributionChart,
  HealthChart,
  HealthLegend,
} from '@/components/charts/InsightsCharts'
import { AgentStat, agentColor, formatPlatform } from '@/components/agents/AgentBar'
import { LayoutDashboard, AlertTriangle, AlertCircle, Info, Bot, ArrowRight } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface Session {
  session_id: string
  agent_id: string | null
  platform: string | null
  started_at: string
  ended_at: string | null
  duration_ms: number | null
  total_cost: number | null
  total_tokens: number | null
  event_count: number | null
  issue_count: number | null
}

interface Issue {
  issue_id: string
  severity: 'error' | 'warning' | 'info'
  issue_category: string
  detected_at: string
  agent_id: string | null
}


export function DashboardPage() {
  const navigate = useNavigate()
  const { selectedUser } = useUser()

  const { data: sessionsData } = usePolling(async () => {
    const params = selectedUser ? `?user_id=${encodeURIComponent(selectedUser)}` : ''
    const res = await api.get<{ sessions: Session[]; total: number }>(`/api/v1/sessions${params}`)
    return res.data
  })

  const { data: agentsData } = usePolling(async () => {
    const params = selectedUser ? `?user_id=${encodeURIComponent(selectedUser)}` : ''
    const res = await api.get<{ agents: AgentStat[] }>(`/api/v1/agents${params}`)
    return res.data
  })

  const { data: issuesData } = usePolling(async () => {
    const params = selectedUser ? `?user_id=${encodeURIComponent(selectedUser)}` : ''
    const res = await api.get<{ issues: Issue[] }>(`/api/v1/issues${params}`)
    return res.data
  })

  const sessions: Session[] = sessionsData?.sessions ?? []
  const agents: AgentStat[] = agentsData?.agents ?? []
  const issues: Issue[] = issuesData?.issues ?? []
  const agentIds = agents.map((a) => a.agent_id)

  const charts = useMemo(() => {
    const dailyCost: Record<string, number> = {}
    const dailyTokens: Record<string, number> = {}
    const dailyEvents: Record<string, number> = {}

    sessions.forEach((s) => {
      if (!s.started_at) return
      const day = s.started_at.split('T')[0]
      dailyCost[day] = (dailyCost[day] ?? 0) + (s.total_cost ?? 0)
      dailyTokens[day] = (dailyTokens[day] ?? 0) + (s.total_tokens ?? 0)
      dailyEvents[day] = (dailyEvents[day] ?? 0) + (s.event_count ?? 0)
    })

    return {
      costSeries: Object.entries(dailyCost)
        .map(([date, cost]) => ({ date, cost }))
        .sort((a, b) => a.date.localeCompare(b.date))
        .slice(-30),
      tokenSeries: Object.entries(dailyTokens)
        .map(([date, tokens]) => ({ date, tokens }))
        .sort((a, b) => a.date.localeCompare(b.date))
        .slice(-30),
      eventsSeries: Object.entries(dailyEvents)
        .map(([date, events]) => ({ date, events }))
        .sort((a, b) => a.date.localeCompare(b.date))
        .slice(-30),
    }
  }, [sessions])

  const issueSummary = useMemo(() => ({
    errors: issues.filter((i) => i.severity === 'error').length,
    warnings: issues.filter((i) => i.severity === 'warning').length,
    infos: issues.filter((i) => i.severity === 'info').length,
  }), [issues])

  const hasChartData =
    charts.costSeries.length > 0 ||
    charts.tokenSeries.length > 0 ||
    charts.eventsSeries.length > 0

  if (sessionsData === null) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <LayoutDashboard className="h-5 w-5 text-accent" />
          <h2 className="text-xl font-semibold">Dashboard</h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <LayoutDashboard className="h-5 w-5 text-accent" />
        <h2 className="text-xl font-semibold">Dashboard</h2>
      </div>

      {/* Stat Cards */}
      <StatCards sessions={sessions} total={sessionsData?.total ?? 0} />

      {/* Agents + Issues summary row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Agents panel */}
        <div className="border border-zinc-200 rounded-lg p-4 bg-white">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-zinc-500" />
              <span className="text-sm font-semibold text-zinc-700">Agents</span>
              <span className="text-xs text-zinc-400">{agents.length} tracked</span>
            </div>
            <button
              onClick={() => navigate('/agents')}
              className="flex items-center gap-1 text-xs text-accent hover:underline"
            >
              View all <ArrowRight className="h-3 w-3" />
            </button>
          </div>

          {agents.length === 0 ? (
            <p className="text-xs text-zinc-400">No agents recorded yet</p>
          ) : (
            <div className="space-y-2">
              {agents.slice(0, 5).map((agent) => {
                const color = agentColor(agent.agent_id, agentIds)
                const errorRate = agent.session_count > 0
                  ? Math.round((agent.error_session_count / agent.session_count) * 100)
                  : 0
                const platformLabel = formatPlatform(agent.platform)

                return (
                  <div
                    key={agent.agent_id}
                    className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-zinc-50 cursor-pointer"
                    onClick={() => navigate('/agents')}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={cn('h-2 w-2 rounded-full flex-shrink-0', color.dot)} />
                      <span className="text-xs font-mono font-medium text-zinc-700 truncate max-w-[120px]">
                        {agent.agent_id}
                      </span>
                      {platformLabel && (
                        <span className="text-xs text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded flex-shrink-0">
                          {platformLabel}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs flex-shrink-0">
                      <span className="text-zinc-500">{agent.session_count} sess</span>
                      <span className={errorRate > 0 ? 'text-red-500 font-medium' : 'text-emerald-600'}>
                        {errorRate}% err
                      </span>
                    </div>
                  </div>
                )
              })}
              {agents.length > 5 && (
                <button
                  onClick={() => navigate('/agents')}
                  className="w-full text-xs text-center text-zinc-400 hover:text-accent py-1"
                >
                  +{agents.length - 5} more agents
                </button>
              )}
            </div>
          )}
        </div>

        {/* Issues panel */}
        <div className="border border-zinc-200 rounded-lg p-4 bg-white">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-zinc-500" />
              <span className="text-sm font-semibold text-zinc-700">Issues</span>
              <span className="text-xs text-zinc-400">{issues.length} total</span>
            </div>
            <button
              onClick={() => navigate('/issues')}
              className="flex items-center gap-1 text-xs text-accent hover:underline"
            >
              View all <ArrowRight className="h-3 w-3" />
            </button>
          </div>

          <div className="space-y-2">
            <div
              className="flex items-center justify-between py-2 px-3 rounded-md bg-red-50 cursor-pointer hover:bg-red-100"
              onClick={() => navigate('/issues')}
            >
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
                <span className="text-sm font-medium text-red-700">Errors</span>
              </div>
              <span className="text-sm font-semibold text-red-600">{issueSummary.errors}</span>
            </div>
            <div
              className="flex items-center justify-between py-2 px-3 rounded-md bg-yellow-50 cursor-pointer hover:bg-yellow-100"
              onClick={() => navigate('/issues')}
            >
              <div className="flex items-center gap-2">
                <AlertCircle className="h-3.5 w-3.5 text-yellow-500" />
                <span className="text-sm font-medium text-yellow-700">Warnings</span>
              </div>
              <span className="text-sm font-semibold text-yellow-600">{issueSummary.warnings}</span>
            </div>
            <div
              className="flex items-center justify-between py-2 px-3 rounded-md bg-blue-50 cursor-pointer hover:bg-blue-100"
              onClick={() => navigate('/issues')}
            >
              <div className="flex items-center gap-2">
                <Info className="h-3.5 w-3.5 text-blue-500" />
                <span className="text-sm font-medium text-blue-700">Info</span>
              </div>
              <span className="text-sm font-semibold text-blue-600">{issueSummary.infos}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Session Health */}
      {sessions.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-zinc-200 rounded-lg p-4 bg-white">
            <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-2">
              Session Health
            </h4>
            <HealthChart sessions={sessions} />
            <HealthLegend sessions={sessions} />
          </div>

          {charts.costSeries.length > 0 && (
            <div className="border border-zinc-200 rounded-lg p-4 bg-white">
              <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-2">
                Cost per Day
              </h4>
              <CostChart data={charts.costSeries} />
            </div>
          )}
        </div>
      )}

      {/* Charts */}
      {hasChartData && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {charts.tokenSeries.length > 0 && (
            <div className="border border-zinc-200 rounded-lg p-4 bg-white">
              <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-2">
                Tokens per Day
              </h4>
              <TokenChart data={charts.tokenSeries} />
            </div>
          )}

          {charts.eventsSeries.length > 0 && (
            <div className="border border-zinc-200 rounded-lg p-4 bg-white">
              <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-2">
                Events per Day
              </h4>
              <EventsChart data={charts.eventsSeries} />
            </div>
          )}

          {sessions.length > 0 && (
            <div className="border border-zinc-200 rounded-lg p-4 bg-white">
              <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-2">
                Duration Distribution
              </h4>
              <DurationDistributionChart sessions={sessions} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
