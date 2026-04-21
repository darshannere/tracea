import { Zap, DollarSign, Hash, Clock, AlertCircle } from 'lucide-react'

interface StatCardsProps {
  sessions: {
    total_cost: number | null
    total_tokens: number | null
    duration_ms: number | null
    issue_count: number | null
    event_count: number | null
    started_at: string
    ended_at: string | null
  }[]
  total: number
}

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function computeDuration(session: StatCardsProps['sessions'][0]): number {
  if (session.duration_ms !== null) return session.duration_ms
  const start = new Date(session.started_at).getTime()
  const end = session.ended_at ? new Date(session.ended_at).getTime() : Date.now()
  return end - start
}

export function StatCards({ sessions, total }: StatCardsProps) {
  const totalCost = sessions.reduce((sum, s) => sum + (s.total_cost ?? 0), 0)
  const totalTokens = sessions.reduce((sum, s) => sum + (s.total_tokens ?? 0), 0)
  const avgDuration = sessions.length > 0
    ? sessions.reduce((sum, s) => sum + computeDuration(s), 0) / sessions.length
    : 0
  const sessionsWithIssues = sessions.filter((s) => (s.issue_count ?? 0) > 0).length
  const issueRate = sessions.length > 0 ? (sessionsWithIssues / sessions.length) * 100 : 0
  const avgEvents = sessions.length > 0
    ? sessions.reduce((sum, s) => sum + (s.event_count ?? 0), 0) / sessions.length
    : 0

  const stats = [
    {
      label: 'Total Sessions',
      value: total.toLocaleString(),
      icon: Zap,
      color: 'text-indigo-600',
      bg: 'bg-indigo-50',
    },
    {
      label: 'Total Cost',
      value: `$${totalCost.toFixed(4)}`,
      icon: DollarSign,
      color: 'text-emerald-600',
      bg: 'bg-emerald-50',
    },
    {
      label: 'Total Tokens',
      value: totalTokens.toLocaleString(),
      icon: Hash,
      color: 'text-sky-600',
      bg: 'bg-sky-50',
    },
    {
      label: 'Avg Duration',
      value: formatDuration(avgDuration),
      icon: Clock,
      color: 'text-amber-600',
      bg: 'bg-amber-50',
    },
    {
      label: 'Issue Rate',
      value: `${issueRate.toFixed(1)}%`,
      sub: `${sessionsWithIssues} session${sessionsWithIssues !== 1 ? 's' : ''}`,
      icon: AlertCircle,
      color: issueRate > 10 ? 'text-rose-600' : 'text-zinc-600',
      bg: issueRate > 10 ? 'bg-rose-50' : 'bg-zinc-50',
    },
    {
      label: 'Avg Events / Session',
      value: avgEvents.toFixed(1),
      icon: Zap,
      color: 'text-violet-600',
      bg: 'bg-violet-50',
    },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="border border-zinc-200 rounded-lg p-3 bg-white"
        >
          <div className="flex items-center gap-2 mb-2">
            <div className={`${stat.bg} rounded-md p-1.5`}>
              <stat.icon className={`h-3.5 w-3.5 ${stat.color}`} />
            </div>
            <span className="text-xs text-zinc-500 font-medium">{stat.label}</span>
          </div>
          <div className="text-lg font-semibold text-zinc-900 leading-tight">
            {stat.value}
          </div>
          {stat.sub && (
            <div className="text-xs text-zinc-400 mt-0.5">{stat.sub}</div>
          )}
        </div>
      ))}
    </div>
  )
}
