import { useState, useMemo } from 'react'

import { usePolling } from '@/hooks/usePolling'
import api from '@/lib/api'
import * as Collapsible from '@radix-ui/react-collapsible'
import { AlertCircle, ChevronDown, CheckCircle2, XCircle, Minus, Clock, Shield, Hourglass } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { IssueDetailPanel } from '@/components/issues/IssueDetailPanel'

type Severity = 'error' | 'warning' | 'info'
type RcaStatus = 'pending' | 'done' | 'failed' | null

interface Issue {
  issue_id: string
  session_id: string
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

interface IssueCardProps {
  issue: Issue
}

function IssueCard({ issue }: IssueCardProps) {
  const [expanded, setExpanded] = useState(false)
  const sev = SEVERITY_COLORS[issue.severity] ?? SEVERITY_COLORS.info

  return (
    <Collapsible.Root open={expanded} onOpenChange={setExpanded}>
      <Collapsible.Trigger asChild>
        <div className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-50 cursor-pointer border-b border-zinc-100 transition-colors">
          <span
            className="px-2 py-0.5 rounded text-xs font-medium"
            style={{ backgroundColor: sev.bg, color: sev.text }}
          >
            {issue.severity}
          </span>
          <span className="text-xs font-mono text-zinc-600 flex-1 truncate">
            {issue.session_id.slice(0, 8)}...
          </span>
          <span className="text-xs text-zinc-400 flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatRelative(issue.detected_at)}
          </span>
          <RcaStatusBadge status={issue.rca_status} />
          <ChevronDown className={cn(
            'h-4 w-4 text-zinc-400 transition-transform',
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
  const { data, error } = usePolling(async () => {
    const res = await api.get<{ issues: Issue[] }>('/api/v1/issues')
    return res.data
  })

  const issues: Issue[] = data?.issues ?? []

  const grouped = useMemo(() => {
    return issues.reduce<Record<string, Issue[]>>((acc, issue) => {
      const cat = issue.issue_category
      if (!acc[cat]) acc[cat] = []
      acc[cat].push(issue)
      return acc
    }, {})
  }, [issues])

  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set(Object.keys(grouped)))

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

  if (issues.length === 0) {
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
        <span className="text-sm text-zinc-500">{issues.length} total</span>
      </div>

      <div className="space-y-4">
        {Object.entries(grouped).map(([category, catIssues]) => (
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
                  <IssueCard key={issue.issue_id} issue={issue} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
