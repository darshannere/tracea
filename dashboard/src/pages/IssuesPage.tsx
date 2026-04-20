import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { usePolling } from '@/hooks/usePolling'
import api from '@/lib/api'
import * as Collapsible from '@radix-ui/react-collapsible'
import { AlertCircle, ChevronDown, Loader2, CheckCircle2, XCircle, Minus, Clock, Slack, Webhook } from 'lucide-react'
import { cn } from '@/lib/utils'

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

function RcaStatusIcon({ status }: { status: RcaStatus }) {
  if (status === 'pending') {
    return <Loader2 className="h-3.5 w-3.5 text-yellow-500 animate-spin" />
  }
  if (status === 'done') {
    return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
  }
  if (status === 'failed') {
    return <XCircle className="h-3.5 w-3.5 text-red-500" />
  }
  return <Minus className="h-3.5 w-3.5 text-zinc-400" />
}

interface IssueCardProps {
  issue: Issue
}

function IssueCard({ issue }: IssueCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [alertExpanded, setAlertExpanded] = useState(false)
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
          <RcaStatusIcon status={issue.rca_status} />
          <ChevronDown className={cn(
            'h-4 w-4 text-zinc-400 transition-transform',
            expanded ? 'rotate-180' : ''
          )} />
        </div>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <div className="px-4 py-4 bg-zinc-50 border-b border-zinc-200 space-y-4">
          {issue.rca_text && (
            <div>
              <h4 className="text-xs font-medium text-zinc-600 mb-1.5">RCA</h4>
              <pre className="bg-zinc-100 rounded p-3 text-xs text-zinc-700 whitespace-pre-wrap font-mono">
                {issue.rca_text}
              </pre>
            </div>
          )}
          {issue.triggering_event_ids && issue.triggering_event_ids.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-zinc-600 mb-1.5">Triggering Events</h4>
              <div className="flex flex-wrap gap-2">
                {issue.triggering_event_ids.map((eid) => (
                  <Link
                    key={eid}
                    to={`/sessions/${issue.session_id}`}
                    className="text-xs text-accent hover:underline font-mono bg-zinc-100 px-2 py-1 rounded"
                  >
                    {eid.slice(0, 8)}...
                  </Link>
                ))}
              </div>
            </div>
          )}
          {issue.alert_delivery && (
            <Collapsible.Root open={alertExpanded} onOpenChange={setAlertExpanded}>
              <Collapsible.Trigger asChild>
                <button className="flex items-center gap-2 text-xs font-medium text-zinc-600 hover:text-zinc-900 transition-colors">
                  <ChevronDown className={cn(
                    'h-3 w-3 transition-transform',
                    alertExpanded ? 'rotate-180' : ''
                  )} />
                  Alert Delivery Status
                </button>
              </Collapsible.Trigger>
              <Collapsible.Content>
                <div className="mt-2 space-y-2 pl-5">
                  {issue.alert_delivery.slack_status && (
                    <div className="flex items-center gap-2 text-xs text-zinc-600">
                      <Slack className="h-3.5 w-3.5" />
                      <span>Slack:</span>
                      <span className={cn(
                        'font-medium',
                        issue.alert_delivery.slack_status === 'sent' ? 'text-green-600' :
                          issue.alert_delivery.slack_status === 'failed' ? 'text-red-600' : 'text-yellow-600'
                      )}>
                        {issue.alert_delivery.slack_status}
                      </span>
                      {issue.alert_delivery.slack_retry_count != null && issue.alert_delivery.slack_retry_count > 0 && (
                        <span className="text-zinc-400">(retry: {issue.alert_delivery.slack_retry_count})</span>
                      )}
                    </div>
                  )}
                  {issue.alert_delivery.webhook_status && (
                    <div className="flex items-center gap-2 text-xs text-zinc-600">
                      <Webhook className="h-3.5 w-3.5" />
                      <span>Webhook:</span>
                      <span className={cn(
                        'font-medium',
                        issue.alert_delivery.webhook_status === 'sent' ? 'text-green-600' :
                          issue.alert_delivery.webhook_status === 'failed' ? 'text-red-600' : 'text-yellow-600'
                      )}>
                        {issue.alert_delivery.webhook_status}
                      </span>
                      {issue.alert_delivery.webhook_retry_count != null && issue.alert_delivery.webhook_retry_count > 0 && (
                        <span className="text-zinc-400">(retry: {issue.alert_delivery.webhook_retry_count})</span>
                      )}
                    </div>
                  )}
                </div>
              </Collapsible.Content>
            </Collapsible.Root>
          )}
        </div>
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
