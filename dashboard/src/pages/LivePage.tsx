import { useState } from 'react'
import { LiveProvider, useLive } from '@/components/live/LiveContext'
import { AgentTree } from '@/components/live/AgentTree'
import { ToolLog } from '@/components/live/ToolLog'
import { InsightsPanel } from '@/components/live/InsightsPanel'
import { formatCost } from '@/components/live/format'
import { Activity, Zap, AlertTriangle, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'

type ActiveTab = 'log' | 'insights'

function LivePageInner() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('log')
  const {
    timeFilter,
    setTimeFilter,
    health,
    sessions,
    isLoading,
  } = useLive()

  const totalCost = sessions.reduce((sum, s) => sum + (s.total_cost ?? 0), 0)
  const totalTokens = sessions.reduce((sum, s) => sum + (s.total_tokens ?? 0), 0)
  const activeSessions = sessions.filter((s) => !s.ended_at).length

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top bar */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-2 border-b border-zinc-200 bg-white">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_8px_#6366f1] animate-pulse shrink-0" />
          <span className="text-sm font-bold text-zinc-900">Live</span>
        </div>
        <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-accent/10 border border-accent/25">
          <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
          <span className="font-mono text-[10px] text-accent uppercase tracking-widest">
            {isLoading ? 'Syncing' : 'Live'}
          </span>
        </div>

        {/* Tab switcher */}
        <div className="ml-auto flex items-center gap-1">
          {(['log', 'insights'] as ActiveTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'px-3 py-1 text-xs font-medium capitalize border-b-2 transition-colors',
                activeTab === tab
                  ? 'border-accent text-accent'
                  : 'border-transparent text-zinc-500 hover:text-zinc-800'
              )}
            >
              {tab === 'log' ? 'Log' : 'Insights'}
            </button>
          ))}
        </div>
      </div>

      {/* 3-column layout */}
      <div className="flex flex-1 overflow-hidden gap-0">
        {/* Col 1: Agent Tree */}
        <div
          className="shrink-0 border-r border-zinc-200 flex flex-col overflow-hidden bg-white"
          style={{ flexBasis: '32%', minWidth: '200px', maxWidth: '360px' }}
        >
          <div className="px-3 py-2 border-b border-zinc-200 text-[10px] uppercase tracking-wider text-zinc-400 font-semibold flex items-center gap-1.5">
            <Activity className="h-3 w-3" />
            Sessions
            {activeSessions > 0 && (
              <span className="ml-auto rounded-full bg-accent/10 px-1.5 py-0.5 text-[9px] font-mono text-accent leading-none">
                {activeSessions} active
              </span>
            )}
          </div>
          {/* Time filter strip */}
          <div className="px-3 py-2 border-b border-zinc-200 flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-zinc-400 uppercase tracking-wide mr-1">Log:</span>
            {(['5m', '15m', '1h', 'all'] as const).map((value) => {
              const label = value === 'all' ? 'All' : `Last ${value}`
              return (
                <button
                  key={value}
                  onClick={() => setTimeFilter(value)}
                  className={cn(
                    'px-2 py-0.5 rounded text-[10px] font-medium transition-colors border',
                    timeFilter === value
                      ? 'bg-accent/10 border-accent/25 text-accent'
                      : 'border-zinc-200 text-zinc-500 hover:text-zinc-800 hover:border-zinc-400'
                  )}
                >
                  {label}
                </button>
              )
            })}
          </div>
          <AgentTree />
        </div>

        {/* Col 2: Log / Insights */}
        <div className="flex-1 flex flex-col overflow-hidden bg-white">
          <div className="flex-1 overflow-hidden flex flex-col">
            {activeTab === 'insights' ? (
              <div className="flex-1 overflow-auto">
                <InsightsPanel />
              </div>
            ) : (
              <ToolLog />
            )}
          </div>
        </div>

        {/* Col 3: Stats */}
        <div className="w-52 shrink-0 border-l border-zinc-200 flex flex-col overflow-y-auto bg-white">
          <div className="border-b border-zinc-200 p-3">
            <h4 className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold mb-2 flex items-center gap-1">
              <Zap className="h-3 w-3" />
              Cost
            </h4>
            <div className="space-y-2">
              <div>
                <div className="text-lg font-mono font-semibold text-zinc-800">{formatCost(totalCost)}</div>
                <div className="text-[10px] text-zinc-400">total cost</div>
              </div>
              <div>
                <div className="text-sm font-mono font-medium text-zinc-700">{totalTokens.toLocaleString()}</div>
                <div className="text-[10px] text-zinc-400">total tokens</div>
              </div>
            </div>
          </div>

          <div className="p-3">
            <h4 className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold mb-2 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              Health
            </h4>
            {health ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-zinc-500">Error rate</span>
                  <span className={cn(
                    'text-xs font-mono font-medium',
                    health.errorRate > 5 ? 'text-rose-500' : 'text-emerald-600'
                  )}>
                    {health.errorRate.toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-zinc-500">Errors</span>
                  <span className="text-xs font-mono text-zinc-700">{health.errorCount}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-zinc-500">Calls</span>
                  <span className="text-xs font-mono text-zinc-700">{health.totalCalls}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-zinc-500">Last event</span>
                  <span className="text-[10px] font-mono text-zinc-500">
                    {health.lastEventTs
                      ? new Date(health.lastEventTs).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                      : '—'}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-zinc-400">Loading...</p>
            )}
          </div>

          <div className="border-t border-zinc-200 p-3">
            <h4 className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold mb-2 flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Sessions
            </h4>
            <div className="space-y-1">
              {sessions.slice(0, 5).map((s) => (
                <div key={s.session_id} className="flex items-center justify-between text-[10px]">
                  <span className="text-zinc-600 truncate max-w-[80px]">{s.session_id.slice(0, 8)}…</span>
                  <span className="text-zinc-400 font-mono">{formatCost(s.total_cost)}</span>
                </div>
              ))}
              {sessions.length === 0 && (
                <p className="text-[10px] text-zinc-400">No sessions</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export function LivePage() {
  return (
    <LiveProvider>
      <LivePageInner />
    </LiveProvider>
  )
}
