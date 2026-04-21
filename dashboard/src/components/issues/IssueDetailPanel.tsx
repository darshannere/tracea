import { Link } from 'react-router-dom'
import {
  Lightbulb, Zap, DollarSign, Clock, Hash, Wrench, FileText,
  AlertTriangle, Bug, ExternalLink, Layers
} from 'lucide-react'

interface IssueDetail {
  issue_id: string
  session_id: string
  issue_category: string
  severity: string
  detected_at: string
  rca_status: 'pending' | 'done' | 'failed' | null
  rca_text?: string
  rule_description?: string
  captured_values?: string
  session_cost_total?: number
  session_duration_ms?: number
  session_event_count?: number
  error_message?: string
  rule_config_snapshot?: string
  event_id?: string
}

function formatCost(cost: number | undefined): string {
  if (cost === undefined || cost === null) return '-'
  return `$${cost.toFixed(4)}`
}

function formatDuration(ms: number | undefined): string {
  if (ms === undefined || ms === null) return '-'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function parseMarkdownish(text: string): React.ReactNode[] {
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let key = 0

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      nodes.push(<div key={key++} className="h-2" />)
      continue
    }

    // Heading: ## Root-Cause Analysis
    if (trimmed.startsWith('## ')) {
      nodes.push(
        <h4 key={key++} className="text-sm font-semibold text-zinc-800 mt-3 mb-1 flex items-center gap-1.5">
          <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
          {trimmed.replace(/^##\s*/, '')}
        </h4>
      )
      continue
    }

    // Bullet with bold label: - **Observable Symptoms:**
    const bulletBoldMatch = trimmed.match(/^[-*]\s*\*\*(.+?)\*\*\s*(.*)$/)
    if (bulletBoldMatch) {
      nodes.push(
        <div key={key++} className="flex gap-2 text-xs text-zinc-600 py-0.5">
          <span className="text-zinc-400 shrink-0">•</span>
          <span>
            <span className="font-medium text-zinc-700">{bulletBoldMatch[1]}</span>
            {bulletBoldMatch[2] && <span className="ml-1">{bulletBoldMatch[2]}</span>}
          </span>
        </div>
      )
      continue
    }

    // Plain bullet: - something
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      nodes.push(
        <div key={key++} className="flex gap-2 text-xs text-zinc-600 py-0.5">
          <span className="text-zinc-400 shrink-0">•</span>
          <span>{renderBold(trimmed.replace(/^[-*]\s*/, ''))}</span>
        </div>
      )
      continue
    }

    // Paragraph with possible bold
    nodes.push(
      <p key={key++} className="text-xs text-zinc-600 leading-relaxed py-0.5">
        {renderBold(trimmed)}
      </p>
    )
  }

  return nodes
}

function renderBold(text: string): React.ReactNode {
  const parts = text.split(/(\*\*.+?\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-medium text-zinc-800">{part.slice(2, -2)}</strong>
    }
    return <span key={i}>{part}</span>
  })
}

function TriggerDetails({ captured }: { captured?: string }) {
  if (!captured) return null
  try {
    const data = JSON.parse(captured)
    const entries = Object.entries(data).filter(([, v]) => v !== null && v !== '')
    if (entries.length === 0) return null

    return (
      <div className="space-y-1.5">
        <h4 className="text-xs font-medium text-zinc-700 flex items-center gap-1.5">
          <Bug className="h-3.5 w-3.5 text-rose-500" />
          What Triggered This
        </h4>
        <div className="bg-white border border-zinc-200 rounded-md p-2.5 space-y-1">
          {entries.map(([key, value]) => (
            <div key={key} className="flex gap-2 text-xs">
              <code className="shrink-0 font-mono text-[11px] bg-zinc-100 px-1 py-0.5 rounded text-zinc-600">{key}</code>
              <span className="text-zinc-700 font-mono text-[11px] truncate">{String(value)}</span>
            </div>
          ))}
        </div>
      </div>
    )
  } catch {
    return (
      <div className="space-y-1.5">
        <h4 className="text-xs font-medium text-zinc-700 flex items-center gap-1.5">
          <Bug className="h-3.5 w-3.5 text-rose-500" />
          What Triggered This
        </h4>
        <pre className="bg-white border border-zinc-200 rounded-md p-2.5 text-[11px] font-mono text-zinc-700 whitespace-pre-wrap">
          {captured}
        </pre>
      </div>
    )
  }
}

function SessionContext({
  cost,
  duration,
  events,
}: {
  cost?: number
  duration?: number
  events?: number
}) {
  const stats = [
    { label: 'Session Cost', value: formatCost(cost), icon: DollarSign, color: 'text-emerald-600' },
    { label: 'Duration', value: formatDuration(duration), icon: Clock, color: 'text-amber-600' },
    { label: 'Events', value: events?.toLocaleString() ?? '-', icon: Hash, color: 'text-sky-600' },
  ]

  return (
    <div className="space-y-1.5">
      <h4 className="text-xs font-medium text-zinc-700 flex items-center gap-1.5">
        <Layers className="h-3.5 w-3.5 text-indigo-500" />
        Session Context
      </h4>
      <div className="grid grid-cols-3 gap-2">
        {stats.map((s) => (
          <div key={s.label} className="bg-white border border-zinc-200 rounded-md p-2 text-center">
            <s.icon className={`h-3 w-3 mx-auto mb-1 ${s.color}`} />
            <div className="text-[11px] font-semibold text-zinc-800">{s.value}</div>
            <div className="text-[10px] text-zinc-400 mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RuleSnapshot({ snapshot }: { snapshot?: string }) {
  if (!snapshot) return null
  try {
    const rule = JSON.parse(snapshot)
    return (
      <div className="space-y-1.5">
        <h4 className="text-xs font-medium text-zinc-700 flex items-center gap-1.5">
          <Wrench className="h-3.5 w-3.5 text-violet-500" />
          Detection Rule
        </h4>
        <div className="bg-white border border-zinc-200 rounded-md p-2.5 space-y-1">
          {rule.id && (
            <div className="flex gap-2 text-xs">
              <span className="text-zinc-400 shrink-0 w-16">ID</span>
              <code className="font-mono text-zinc-700">{rule.id}</code>
            </div>
          )}
          {rule.description && (
            <div className="flex gap-2 text-xs">
              <span className="text-zinc-400 shrink-0 w-16">Desc</span>
              <span className="text-zinc-700">{rule.description}</span>
            </div>
          )}
          {rule.severity && (
            <div className="flex gap-2 text-xs">
              <span className="text-zinc-400 shrink-0 w-16">Severity</span>
              <span className="capitalize text-zinc-700">{rule.severity}</span>
            </div>
          )}
        </div>
      </div>
    )
  } catch {
    return null
  }
}

export function IssueDetailPanel({ issue }: { issue: IssueDetail }) {
  return (
    <div className="px-4 py-4 bg-zinc-50 border-b border-zinc-200 space-y-4">
      {/* Top row: Session context + Trigger */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SessionContext
          cost={issue.session_cost_total}
          duration={issue.session_duration_ms}
          events={issue.session_event_count}
        />
        <TriggerDetails captured={issue.captured_values} />
      </div>

      {/* RCA Analysis */}
      {issue.rca_text && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-medium text-zinc-700 flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5 text-accent" />
              Root-Cause Analysis
            </h4>
            <Link
              to={`/sessions/${issue.session_id}`}
              className="text-[11px] text-accent hover:underline flex items-center gap-1"
            >
              <ExternalLink className="h-3 w-3" />
              View Session
            </Link>
          </div>
          <div className="bg-white border border-zinc-200 rounded-md p-3.5">
            {parseMarkdownish(issue.rca_text)}
          </div>
        </div>
      )}

      {/* Error message */}
      {issue.error_message && (
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-zinc-700 flex items-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
            Error
          </h4>
          <div className="bg-red-50 border border-red-200 rounded-md p-2.5 text-xs text-red-700 font-mono">
            {issue.error_message}
          </div>
        </div>
      )}

      {/* Rule snapshot */}
      <RuleSnapshot snapshot={issue.rule_config_snapshot} />

      {/* Event IDs */}
      {issue.event_id && (
        <div className="flex items-center gap-2 text-[11px] text-zinc-500">
          <Zap className="h-3 w-3" />
          <span>Triggering event:</span>
          <code className="font-mono bg-zinc-100 px-1 py-0.5 rounded">{issue.event_id.slice(0, 12)}...</code>
        </div>
      )}
    </div>
  )
}
