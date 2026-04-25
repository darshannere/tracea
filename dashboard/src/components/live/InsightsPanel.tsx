import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AreaChart, Area,
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid,
} from 'recharts'
import { useLive } from './LiveContext'
import { useUser } from '@/hooks/UserContext'
import type { ToolEvent } from './LiveContext'
import api from '@/lib/api'

const COLORS = {
  indigo: '#6366f1',
  emerald: '#10b981',
  sky: '#0ea5e9',
  amber: '#f59e0b',
  rose: '#f43f5e',
  cyan: '#06b6d4',
}

const TOOLTIP_STYLE: React.CSSProperties = {
  fontSize: 11,
  borderRadius: 6,
  border: '1px solid #e4e4e7',
  background: '#fff',
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
}
const TICK_STYLE = { fill: '#71717a', fontSize: 10 }
const GRID = <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />

interface StalledAgent {
  agent_id: string
  agent_type: string
  last_activity_ts: number
  idle_seconds: number
}

type Tab = 'Cost' | 'Activity' | 'Health'
const TABS: Tab[] = ['Cost', 'Activity', 'Health']

function computeLatencyPercentiles(events: ToolEvent[]) {
  const durations = events
    .filter((e) => e.duration_ms != null)
    .map((e) => e.duration_ms as number)
    .sort((a, b) => a - b)
  if (durations.length === 0) return { p50: 0, p95: 0, count: 0 }
  const p50 = durations[Math.floor(durations.length * 0.5)] ?? 0
  const p95 = durations[Math.floor(durations.length * 0.95)] ?? 0
  return { p50, p95, count: durations.length }
}

export function InsightsPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('Cost')
  const { selectedUser } = useUser()
  const { events, sessions } = useLive()

  const latestSessionId = sessions[0]?.session_id ?? null

  // --- Cost tab ---
  const hasFetchedCost = useRef(false)
  const [costDailyData, setCostDailyData] = useState<{ day: string; cost_usd: number }[]>([])
  const [costDailyStatus, setCostDailyStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')
  const [costAgentData, setCostAgentData] = useState<{ agent_type: string; cost_usd: number }[]>([])
  const [costAgentStatus, setCostAgentStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')

  const userParam = selectedUser ? `?user_id=${encodeURIComponent(selectedUser)}` : ''

  useEffect(() => {
    if (activeTab !== 'Cost') return
    hasFetchedCost.current = true
    setCostDailyStatus('loading')
    setCostAgentStatus('loading')

    api.get(`/api/v1/observagent/insights/cost-daily${userParam}`)
      .then(r => { setCostDailyData(r.data); setCostDailyStatus('ok') })
      .catch(() => setCostDailyStatus('error'))

    api.get(`/api/v1/observagent/insights/cost-by-agent${userParam}`)
      .then(r => { setCostAgentData(r.data); setCostAgentStatus('ok') })
      .catch(() => setCostAgentStatus('error'))
  }, [activeTab, selectedUser])

  // --- Activity tab ---
  const [activityData, setActivityData] = useState<{ bucket_ms: number; tool_calls: number }[]>([])
  const [activityStatus, setActivityStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')
  const [tokensData, setTokensData] = useState<{ bucket_ms: number; input_tokens: number; output_tokens: number }[]>([])
  const [tokensStatus, setTokensStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')

  // --- Health tab ---
  const [stalledAgents, setStalledAgents] = useState<StalledAgent[]>([])
  const [stalledStatus, setStalledStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')
  const stalledCount = stalledStatus === 'ok' ? stalledAgents.length : 0

  const [errorRateData, setErrorRateData] = useState<{ bucket_ms: number; error_rate: number }[]>([])
  const [errorRateStatus, setErrorRateStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')
  const [latencyData, setLatencyData] = useState<{ tool_name: string; p50_ms: number; p95_ms: number; sample_count: number }[]>([])
  const [latencyStatus, setLatencyStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')

  // Always-on stalled agents poll
  useEffect(() => {
    const fetchStalled = () => {
      setStalledStatus('loading')
      api.get(`/api/v1/observagent/insights/stalled-agents${userParam}`)
        .then(r => { setStalledAgents(r.data); setStalledStatus('ok') })
        .catch(() => setStalledStatus('error'))
    }
    fetchStalled()
    const id = setInterval(fetchStalled, 30000)
    return () => clearInterval(id)
  }, [selectedUser])

  // Health tab polling
  useEffect(() => {
    if (activeTab !== 'Health' || !latestSessionId) return
    const fetchHealth = () => {
      setErrorRateStatus('loading')
      setLatencyStatus('loading')

      const baseParams = new URLSearchParams({ session_id: latestSessionId })
      if (selectedUser) baseParams.append('user_id', selectedUser)

      api.get(`/api/v1/observagent/insights/error-rate?${baseParams.toString()}`)
        .then(r => {
          const transformed = r.data.map((d: { bucket_ms: number; errors: number; total: number }) => ({
            bucket_ms: d.bucket_ms,
            error_rate: d.total > 0 ? (d.errors / d.total) * 100 : 0,
          }))
          setErrorRateData(transformed)
          setErrorRateStatus('ok')
        })
        .catch(() => setErrorRateStatus('error'))

      api.get(`/api/v1/observagent/insights/latency-by-tool?${baseParams.toString()}`)
        .then(r => { setLatencyData(r.data); setLatencyStatus('ok') })
        .catch(() => setLatencyStatus('error'))
    }
    fetchHealth()
    const id = setInterval(fetchHealth, 30000)
    return () => clearInterval(id)
  }, [activeTab, latestSessionId, selectedUser])

  // Activity tab polling
  useEffect(() => {
    if (activeTab !== 'Activity' || !latestSessionId) return
    const fetchData = () => {
      setActivityStatus('loading')
      setTokensStatus('loading')
      const baseParams = new URLSearchParams({ session_id: latestSessionId })
      if (selectedUser) baseParams.append('user_id', selectedUser)

      api.get(`/api/v1/observagent/insights/activity?${baseParams.toString()}`)
        .then(r => { setActivityData(r.data); setActivityStatus('ok') })
        .catch(() => setActivityStatus('error'))

      api.get(`/api/v1/observagent/insights/tokens-over-time?${baseParams.toString()}`)
        .then(r => { setTokensData(r.data); setTokensStatus('ok') })
        .catch(() => setTokensStatus('error'))
    }
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [activeTab, latestSessionId, selectedUser])

  const latency = useMemo(() => computeLatencyPercentiles(events), [events])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b border-zinc-200 shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 py-2 text-xs font-medium transition-colors',
              activeTab === tab
                ? 'border-b-2 border-accent text-accent'
                : 'text-zinc-500 hover:text-zinc-800'
            )}
          >
            {tab === 'Health' && stalledCount > 0 ? `Health (${stalledCount})` : tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto p-4 space-y-6">
        {activeTab === 'Cost' && (
          <>
            <ChartSection title="7-Day Cost Trend">
              {costDailyStatus === 'loading' || costDailyStatus === 'idle' ? (
                <Skeleton />
              ) : costDailyStatus === 'error' ? (
                <Retry onClick={() => {
                  setCostDailyStatus('loading')
                  api.get(`/api/v1/observagent/insights/cost-daily${userParam}`)
                    .then(r => { setCostDailyData(r.data); setCostDailyStatus('ok') })
                    .catch(() => setCostDailyStatus('error'))
                }} />
              ) : costDailyData.length === 0 ? (
                <NoData />
              ) : (
                <div style={{ height: 160 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={costDailyData} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
                      {GRID}
                      <XAxis dataKey="day" tick={TICK_STYLE} tickFormatter={(v: string) => new Date(v).toLocaleDateString('en', { month: 'short', day: 'numeric' })} />
                      <YAxis tick={TICK_STYLE} width={44} tickFormatter={(v: number) => `$${v.toFixed(3)}`} />
                      <Tooltip formatter={(v) => [`$${Number(v).toFixed(4)}`, 'Cost']} contentStyle={TOOLTIP_STYLE} />
                      <Area dataKey="cost_usd" fill={COLORS.indigo} stroke={COLORS.indigo} fillOpacity={0.20} type="monotone" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartSection>

            <ChartSection title="Cost by Agent">
              {costAgentStatus === 'loading' || costAgentStatus === 'idle' ? (
                <Skeleton />
              ) : costAgentStatus === 'error' ? (
                <Retry onClick={() => {
                  setCostAgentStatus('loading')
                  api.get(`/api/v1/observagent/insights/cost-by-agent${userParam}`)
                    .then(r => { setCostAgentData(r.data); setCostAgentStatus('ok') })
                    .catch(() => setCostAgentStatus('error'))
                }} />
              ) : costAgentData.length === 0 ? (
                <NoData />
              ) : (
                <div style={{ height: 160 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={costAgentData} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
                      {GRID}
                      <XAxis dataKey="agent_type" tick={TICK_STYLE} angle={-20} textAnchor="end" />
                      <YAxis tick={TICK_STYLE} width={44} tickFormatter={(v: number) => `$${v.toFixed(3)}`} />
                      <Tooltip formatter={(v) => [`$${Number(v).toFixed(4)}`, 'Cost']} contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="cost_usd" fill={COLORS.indigo} radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartSection>

            <ChartSection title="Tool Call Latency">
              {latency.count === 0 ? (
                <NoData />
              ) : (
                <div className="grid grid-cols-3 gap-3">
                  <StatBox label="p50" value={`${latency.p50}ms`} color="text-emerald-500" />
                  <StatBox label="p95" value={`${latency.p95}ms`} color="text-amber-500" />
                  <StatBox label="samples" value={`${latency.count}`} color="text-zinc-800" />
                </div>
              )}
            </ChartSection>
          </>
        )}

        {activeTab === 'Activity' && (
          <>
            {latestSessionId ? (
              <p className="text-xs text-zinc-500 mb-2">
                Session: {latestSessionId.slice(0, 8)}
              </p>
            ) : (
              <p className="text-xs text-zinc-500">No active session yet.</p>
            )}

            {latestSessionId && (
              <>
                <ChartSection title="Tool Call Activity">
                  {activityStatus === 'loading' ? <Skeleton /> : activityStatus === 'error' ? <Retry onClick={() => {
                    setActivityStatus('loading')
                    api.get(`/api/v1/observagent/insights/activity?session_id=${latestSessionId}`)
                      .then(r => { setActivityData(r.data); setActivityStatus('ok') })
                      .catch(() => setActivityStatus('error'))
                  }} /> : activityData.length === 0 ? <NoData /> : (
                    <div style={{ height: 160 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={activityData} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
                          {GRID}
                          <XAxis dataKey="bucket_ms" tick={TICK_STYLE} tickFormatter={(v: number) => new Date(v).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', hour12: false })} />
                          <YAxis tick={TICK_STYLE} allowDecimals={false} />
                          <Tooltip formatter={(v) => [`${v} calls`, 'Tool Calls']} contentStyle={TOOLTIP_STYLE} />
                          <Area dataKey="tool_calls" fill={COLORS.sky} stroke={COLORS.sky} fillOpacity={0.20} type="monotone" />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </ChartSection>

                <ChartSection title="Token Burn Rate">
                  {tokensStatus === 'loading' ? <Skeleton /> : tokensStatus === 'error' ? <Retry onClick={() => {
                    setTokensStatus('loading')
                    api.get(`/api/v1/observagent/insights/tokens-over-time?session_id=${latestSessionId}`)
                      .then(r => { setTokensData(r.data); setTokensStatus('ok') })
                      .catch(() => setTokensStatus('error'))
                  }} /> : tokensData.length === 0 ? <NoData /> : (
                    <>
                      <div className="h-[140px]">
                        <p className="text-[10px] text-zinc-500 mb-1">Input Tokens</p>
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={tokensData} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
                            {GRID}
                            <XAxis dataKey="bucket_ms" tick={TICK_STYLE} tickFormatter={(v: number) => new Date(v).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', hour12: false })} />
                            <YAxis tick={TICK_STYLE} allowDecimals={false} />
                            <Tooltip formatter={(v: any) => [`${v}`, 'Input']} contentStyle={TOOLTIP_STYLE} />
                            <Area dataKey="input_tokens" fill={COLORS.sky} stroke={COLORS.sky} fillOpacity={0.25} type="monotone" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="h-[140px]">
                        <p className="text-[10px] text-zinc-500 mb-1">Output Tokens</p>
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={tokensData} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
                            {GRID}
                            <XAxis dataKey="bucket_ms" tick={TICK_STYLE} tickFormatter={(v: number) => new Date(v).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', hour12: false })} />
                            <YAxis tick={TICK_STYLE} allowDecimals={false} />
                            <Tooltip formatter={(v: any) => [`${v}`, 'Output']} contentStyle={TOOLTIP_STYLE} />
                            <Area dataKey="output_tokens" fill={COLORS.emerald} stroke={COLORS.emerald} fillOpacity={0.25} type="monotone" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </>
                  )}
                </ChartSection>
              </>
            )}
          </>
        )}

        {activeTab === 'Health' && (
          <>
            <ChartSection title="Stalled Agents">
              {stalledStatus === 'loading' || stalledStatus === 'idle' ? (
                <Skeleton height={48} />
              ) : stalledStatus === 'error' ? (
                <Retry onClick={() => {
                  setStalledStatus('loading')
                  api.get(`/api/v1/observagent/insights/stalled-agents${userParam}`)
                    .then(r => { setStalledAgents(r.data); setStalledStatus('ok') })
                    .catch(() => setStalledStatus('error'))
                }} />
              ) : stalledAgents.length === 0 ? (
                <div className="rounded border border-emerald-200 bg-emerald-50 p-3 text-center">
                  <p className="text-xs text-emerald-600">All agents healthy</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {stalledAgents.map((agent) => {
                    const minutes = Math.floor(agent.idle_seconds / 60)
                    const seconds = agent.idle_seconds % 60
                    const idleLabel = `${minutes}m ${seconds}s`
                    const startTime = new Date(agent.last_activity_ts).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', hour12: false })
                    const displayName = agent.agent_type || agent.agent_id.slice(0, 8)
                    return (
                      <div key={agent.agent_id} className="rounded border border-zinc-200 p-2 flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-zinc-700 truncate">{displayName}</p>
                          <p className="text-[10px] text-zinc-400">last active {startTime}</p>
                        </div>
                        <div className="text-xs font-mono text-amber-500 shrink-0">{idleLabel}</div>
                      </div>
                    )
                  })}
                </div>
              )}
            </ChartSection>

            <ChartSection title="Error Rate">
              {!latestSessionId ? (
                <NoData />
              ) : errorRateStatus === 'loading' || errorRateStatus === 'idle' ? (
                <Skeleton />
              ) : errorRateStatus === 'error' ? (
                <Retry onClick={() => {
                  setErrorRateStatus('loading')
                  const p = new URLSearchParams({ session_id: latestSessionId })
                  if (selectedUser) p.append('user_id', selectedUser)
                  api.get(`/api/v1/observagent/insights/error-rate?${p.toString()}`)
                    .then(r => {
                      const transformed = r.data.map((d: { bucket_ms: number; errors: number; total: number }) => ({
                        bucket_ms: d.bucket_ms,
                        error_rate: d.total > 0 ? (d.errors / d.total) * 100 : 0,
                      }))
                      setErrorRateData(transformed)
                      setErrorRateStatus('ok')
                    })
                    .catch(() => setErrorRateStatus('error'))
                }} />
              ) : errorRateData.length === 0 ? (
                <NoData />
              ) : (
                <div style={{ height: 160 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={errorRateData} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
                      {GRID}
                      <XAxis dataKey="bucket_ms" tick={TICK_STYLE} tickFormatter={(v: number) => new Date(v).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', hour12: false })} />
                      <YAxis tick={TICK_STYLE} tickFormatter={(v: number) => `${v.toFixed(1)}%`} domain={[0, 'auto']} />
                      <Tooltip formatter={(v) => [`${Number(v).toFixed(2)}%`, 'Error Rate']} contentStyle={TOOLTIP_STYLE} />
                      <Area dataKey="error_rate" fill={COLORS.rose} stroke={COLORS.rose} fillOpacity={0.15} type="monotone" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartSection>

            <ChartSection title="Latency by Tool">
              {!latestSessionId ? (
                <NoData />
              ) : latencyStatus === 'loading' || latencyStatus === 'idle' ? (
                <Skeleton />
              ) : latencyStatus === 'error' ? (
                <Retry onClick={() => {
                  setLatencyStatus('loading')
                  const p = new URLSearchParams({ session_id: latestSessionId })
                  if (selectedUser) p.append('user_id', selectedUser)
                  api.get(`/api/v1/observagent/insights/latency-by-tool?${p.toString()}`)
                    .then(r => { setLatencyData(r.data); setLatencyStatus('ok') })
                    .catch(() => setLatencyStatus('error'))
                }} />
              ) : latencyData.length === 0 ? (
                <NoData text="No latency data yet (need 2+ tool calls per type)" />
              ) : (
                <div style={{ height: 160 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={latencyData} margin={{ top: 4, right: 8, bottom: 28, left: 0 }}>
                      {GRID}
                      <XAxis dataKey="tool_name" tick={TICK_STYLE} angle={-20} textAnchor="end" />
                      <YAxis tick={TICK_STYLE} tickFormatter={(v: number) => `${v}ms`} />
                      <Tooltip formatter={(v) => [`${v}ms`]} contentStyle={TOOLTIP_STYLE} />
                      <Legend wrapperStyle={{ fontSize: 9 }} />
                      <Bar dataKey="p50_ms" fill={COLORS.sky} name="p50" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="p95_ms" fill={COLORS.amber} name="p95" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartSection>
          </>
        )}
      </div>
    </div>
  )
}

function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(' ')
}

function ChartSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
        {title}
      </h3>
      {children}
    </div>
  )
}

function Skeleton({ height = 160 }: { height?: number }) {
  return <div style={{ height }} className="animate-pulse bg-zinc-100 rounded" />
}

function NoData({ text = 'No data yet' }: { text?: string }) {
  return <p className="text-xs text-zinc-400">{text}</p>
}

function Retry({ onClick }: { onClick: () => void }) {
  return (
    <p className="text-xs text-zinc-400">
      Failed to load —{' '}
      <button className="underline text-accent" onClick={onClick}>retry?</button>
    </p>
  )
}

function StatBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded border border-zinc-200 p-2 text-center">
      <div className={cn('text-lg font-mono font-semibold', color)}>{value}</div>
      <div className="text-[10px] text-zinc-400">{label}</div>
    </div>
  )
}
