import { useState, useMemo, useEffect } from 'react'

import { usePolling } from '@/hooks/usePolling'
import api from '@/lib/api'
import * as Collapsible from '@radix-ui/react-collapsible'
import { AlertCircle, ChevronDown, CheckCircle2, XCircle, Minus, Clock, Shield, Hourglass, Bot } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { IssueDetailPanel } from '@/components/issues/IssueDetailPanel'
import { AgentStat, agentColor, formatPlatform } from '@/components/agents/AgentBar'

type Severity = 'error' | 'warning' | 'info'
type RcaStatus = 'pending' | 'done' | 'failed' | null

interface Issue {
  issue_id: string
  session_id: string
  agent_id: string | null
  platform: string | null
  issue_category: string
  severity: Severity
  detected_at: string
  rca_status: RcaStatus
  rca_text?: string
  triggering_event_ids?: string[]
  rule_description?: string
  captured_values?: string
  session_cost_total?: number
  session_duration_ms?: number
  session_event_count?: number
  error_message?: string
  rule_config_snapshot?: string
  event_id?: string
  alert_delivery?: {
    slack_status?: string
    slack_retry_count?: number
    webhook_status?: string
    webhook_retry_count?: number
  }
}

const SEVERITY_COLORS: Record<Severity, { bg: string; text: string }> = {
  error: { bg: '#ef4444', text: '#ffffff' },
  warning: { bg: '#eab308', text: '#000000' },
  info: { bg: '#3b82f6', text: '#ffffff' },
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

function RcaStatusBadge({ status }: { status: RcaStatus }) {
  if (status === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded" title="RCA pending">
        <Hourglass className="h-3 w-3" />
        Pending
      </span>
    )
  }
  if (status === 'done') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-600 bg-green-50 px-1.5 py-0.5 rounded" title="RCA complete">
        <CheckCircle2 className="h-3 w-3" />
        Done
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-red-600 bg-red-50 px-1.5 py-0.5 rounded" title="RCA failed">
        <XCircle className="h-3 w-3" />
        Failed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-zinc-500 bg-zinc-50 px-1.5 py-0.5 rounded" title="No RCA">
      <Minus className="h-3 w-3" />
      —
    </span>
  )
}

interface AgentPillProps {
  agentId: string
  allAgentIds: string[]
}

function AgentPill({ agentId, allAgentIds }: AgentPillProps) {
  const color = agentColor(agentId, allAgentIds)
  return (
    <span className={cn('inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono font-medium', color.bg, color.text)}>
      <span className={cn('h-1.5 w-1.5 rounded-full flex-shrink-0', color.dot)} />
      {agentId.length > 14 ? `${agentId.slice(0, 12)}…` : agentId}
    </span>
  )
}

interface IssueCardProps {
  issue: Issue
  allAgentIds: string[]
}

function IssueCard({ issue, allAgentIds }: IssueCardProps) {
  const [expanded, setExpanded] = useState(false)
  const sev = SEVERITY_COLORS[issue.severity] ?? SEVERITY_COLORS.info

  return (
    <Collapsible.Root open={expanded} onOpenChange={setExpanded}>
      <Collapsible.Trigger asChild>
        <div className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-50 cursor-pointer border-b border-zinc-100 transition-colors">
          <span
            className="px-2 py-0.5 rounded text-xs font-medium flex-shrink-0"
            style={{ backgroundColor: sev.bg, color: sev.text }}
          >
            {issue.severity}
          </span>
          {issue.agent_id ? (
            <AgentPill agentId={issue.agent_id} allAgentIds={allAgentIds} />
          ) : (
            <span className="text-xs text-zinc-400">no agent</span>
          )}
          {formatPlatform(issue.platform) && (
            <span className="text-xs text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded flex-shrink-0">
              {formatPlatform(issue.platform)}
            </span>
          )}
          <span className="text-xs font-mono text-zinc-500 truncate">
            {issue.session_id.slice(0, 8)}…
          </span>
          <span className="text-xs text-zinc-400 flex items-center gap-1 ml-auto flex-shrink-0">
            <Clock className="h-3 w-3" />
            {formatRelative(issue.detected_at)}
          </span>
          <RcaStatusBadge status={issue.rca_status} />
          <ChevronDown className={cn(
            'h-4 w-4 text-zinc-400 transition-transform flex-shrink-0',
            expanded ? 'rotate-180' : ''
          )} />
        </div>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <IssueDetailPanel issue={issue} />
      </Collapsible.Content>
    </Collapsible.Root>
  )
}

export function IssuesPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)

  const { data, error } = usePolling(async () => {
    const res = await api.get<{ issues: Issue[] }>('/api/v1/issues')
    return res.data
  })

  const { data: agentsData } = usePolling(async () => {
    const res = await api.get<{ agents: AgentStat[] }>('/api/v1/agents')
    return res.data
  })

  const allIssues: Issue[] = data?.issues ?? []
  const agents: AgentStat[] = agentsData?.agents ?? []
  const allAgentIds = agents.map((a) => a.agent_id)

  const issues = useMemo(
    () => selectedAgent ? allIssues.filter((i) => i.agent_id === selectedAgent) : allIssues,
    [allIssues, selectedAgent]
  )

  const grouped = useMemo(() => {
    return issues.reduce<Record<string, Issue[]>>((acc, issue) => {
      const cat = issue.issue_category
      if (!acc[cat]) acc[cat] = []
      acc[cat].push(issue)
      return acc
    }, {})
  }, [issues])

  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set())
  const [groupsInitialized, setGroupsInitialized] = useState(false)

  useEffect(() => {
    if (!groupsInitialized && Object.keys(grouped).length > 0) {
      setOpenGroups(new Set(Object.keys(grouped)))
      setGroupsInitialized(true)
    }
  }, [grouped, groupsInitialized])

  const toggleGroup = (cat: string) => {
    setOpenGroups((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  if (data === null) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Shield className="h-5 w-5 text-accent" />
          <h2 className="text-xl font-semibold">Issues</h2>
        </div>
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="border border-zinc-200 rounded-lg overflow-hidden">
              <Skeleton className="h-11 w-full" />
              <div className="p-4 space-y-3">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">Failed to load data</p>
        <p className="text-xs text-zinc-400">Retrying in 5 seconds...</p>
      </div>
    )
  }

  if (allIssues.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm font-medium">No issues detected</p>
        <p className="text-xs text-zinc-400">Issues will appear here when detection rules fire</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <AlertCircle className="h-5 w-5 text-zinc-500" />
        <h2 className="text-xl font-semibold">Issues</h2>
        <span className="text-sm text-zinc-500">
          {selectedAgent ? `${issues.length} of ${allIssues.length}` : `${allIssues.length} total`}
        </span>
      </div>

      {/* Agent filter */}
      {agents.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <Bot className="h-4 w-4 text-zinc-400 flex-shrink-0" />
          <button
            onClick={() => setSelectedAgent(null)}
            className={cn(
              'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
              selectedAgent === null
                ? 'border-zinc-400 bg-zinc-100 text-zinc-700'
                : 'border-zinc-200 bg-white text-zinc-500 hover:border-zinc-300'
            )}
          >
            All agents
          </button>
          {agents.map((agent) => {
            const color = agentColor(agent.agent_id, allAgentIds)
            const isSelected = selectedAgent === agent.agent_id
            const issueCount = allIssues.filter((i) => i.agent_id === agent.agent_id).length
            return (
              <button
                key={agent.agent_id}
                onClick={() => setSelectedAgent(isSelected ? null : agent.agent_id)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium border transition-colors',
                  isSelected
                    ? `${color.bg} ${color.text} ${color.border} border-2`
                    : 'border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300'
                )}
              >
                <span className={cn('h-1.5 w-1.5 rounded-full', color.dot)} />
                {agent.agent_id.length > 16 ? `${agent.agent_id.slice(0, 14)}…` : agent.agent_id}
                {issueCount > 0 && (
                  <span className="ml-0.5 text-red-500 font-semibold">{issueCount}</span>
                )}
              </button>
            )
          })}
        </div>
      )}

      <div className="space-y-4">
        {Object.keys(grouped).length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-zinc-400">
            <p className="text-sm">No issues for this agent</p>
          </div>
        ) : (
          Object.entries(grouped).map(([category, catIssues]) => (
            <div key={category} className="border border-zinc-200 rounded-lg overflow-hidden">
              <button
                onClick={() => toggleGroup(category)}
                className="w-full flex items-center gap-3 px-4 py-3 bg-zinc-50 hover:bg-zinc-100 transition-colors text-left"
              >
                <span className="px-2 py-0.5 rounded text-xs font-medium border border-zinc-300 text-zinc-700 bg-white">
                  {category}
                </span>
                <span className="text-xs text-zinc-500">{catIssues.length} issues</span>
                <ChevronDown className={cn(
                  'h-4 w-4 text-zinc-400 ml-auto transition-transform',
                  openGroups.has(category) ? 'rotate-180' : ''
                )} />
              </button>
              {openGroups.has(category) && (
                <div>
                  {catIssues.map((issue) => (
                    <IssueCard key={issue.issue_id} issue={issue} allAgentIds={allAgentIds} />
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
