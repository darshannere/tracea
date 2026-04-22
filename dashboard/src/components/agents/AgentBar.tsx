import { Bot, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface AgentStat {
  agent_id: string
  session_count: number
  error_session_count: number
  total_cost: number
  last_active: string
  platform: string | null
}

const AGENT_COLORS = [
  { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-400', dot: 'bg-blue-500' },
  { bg: 'bg-violet-100', text: 'text-violet-700', border: 'border-violet-400', dot: 'bg-violet-500' },
  { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-400', dot: 'bg-emerald-500' },
  { bg: 'bg-orange-100', text: 'text-orange-700', border: 'border-orange-400', dot: 'bg-orange-500' },
  { bg: 'bg-pink-100', text: 'text-pink-700', border: 'border-pink-400', dot: 'bg-pink-500' },
  { bg: 'bg-teal-100', text: 'text-teal-700', border: 'border-teal-400', dot: 'bg-teal-500' },
]

export function agentColor(agentId: string, allAgentIds: string[]) {
  const idx = allAgentIds.indexOf(agentId)
  const safeIdx = idx === -1 ? 0 : idx
  return AGENT_COLORS[safeIdx % AGENT_COLORS.length]
}

const PLATFORM_LABELS: Record<string, string> = {
  'tracea-mcp': 'Claude Code',
  'openai': 'OpenAI',
  'anthropic': 'Anthropic',
  'azure_openai': 'Azure OpenAI',
  'ollama': 'Ollama',
  'unknown': 'Unknown',
}

export function formatPlatform(platform: string | null | undefined): string {
  if (!platform) return ''
  return PLATFORM_LABELS[platform] ?? platform
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

interface AgentBarProps {
  agents: AgentStat[]
  selectedAgent: string | null
  onSelect: (agentId: string | null) => void
}

export function AgentBar({ agents, selectedAgent, onSelect }: AgentBarProps) {
  if (agents.length === 0) return null

  const agentIds = agents.map((a) => a.agent_id)

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Bot className="h-4 w-4 text-zinc-500" />
        <span className="text-sm font-semibold text-zinc-700">Agents</span>
        <span className="text-xs text-zinc-400">{agents.length} active</span>
      </div>

      <div className="flex gap-3 overflow-x-auto pb-1">
        <button
          onClick={() => onSelect(null)}
          className={cn(
            'flex-shrink-0 px-3 py-2 rounded-lg border text-xs font-medium transition-colors',
            selectedAgent === null
              ? 'border-zinc-400 bg-zinc-100 text-zinc-700'
              : 'border-zinc-200 bg-white text-zinc-500 hover:border-zinc-300 hover:bg-zinc-50'
          )}
        >
          All agents
        </button>

        {agents.map((agent) => {
          const color = agentColor(agent.agent_id, agentIds)
          const errorRate = agent.session_count > 0
            ? Math.round((agent.error_session_count / agent.session_count) * 100)
            : 0
          const isSelected = selectedAgent === agent.agent_id
          const hasErrors = agent.error_session_count > 0
          const platformLabel = formatPlatform(agent.platform)

          return (
            <button
              key={agent.agent_id}
              onClick={() => onSelect(isSelected ? null : agent.agent_id)}
              className={cn(
                'flex-shrink-0 flex flex-col gap-1.5 px-3 py-2 rounded-lg border text-left transition-colors min-w-[160px]',
                isSelected
                  ? `${color.bg} ${color.border} border-2`
                  : 'border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50'
              )}
            >
              {/* Agent name + platform row */}
              <div className="flex items-center gap-1.5">
                <span className={cn('h-2 w-2 rounded-full flex-shrink-0', color.dot)} />
                <span className={cn('text-xs font-mono font-medium truncate max-w-[110px]', isSelected ? color.text : 'text-zinc-700')}>
                  {agent.agent_id}
                </span>
              </div>

              {/* Platform badge */}
              {platformLabel && (
                <span className="text-xs text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded w-fit">
                  {platformLabel}
                </span>
              )}

              {/* Stats row */}
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <span>{agent.session_count} sess</span>
                {hasErrors ? (
                  <span className="flex items-center gap-0.5 text-red-500 font-medium">
                    <AlertTriangle className="h-3 w-3" />
                    {errorRate}% err
                  </span>
                ) : (
                  <span className="text-emerald-600">0% err</span>
                )}
                <span className="ml-auto text-zinc-400">{formatRelative(agent.last_active)}</span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
