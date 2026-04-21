import { useState } from 'react'
import { ChevronRight, BookOpen, Hash, Gauge, AlertTriangle, Wrench, Braces } from 'lucide-react'

interface SectionProps {
  title: string
  icon: React.ElementType
  children: React.ReactNode
  defaultOpen?: boolean
}

function Section({ title, icon: Icon, children, defaultOpen = false }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-zinc-100 last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors text-left"
      >
        <Icon className="h-3.5 w-3.5 text-zinc-400 shrink-0" />
        <span className="flex-1">{title}</span>
        <ChevronRight className={cn('h-3.5 w-3.5 text-zinc-400 shrink-0 transition-transform', open && 'rotate-90')} />
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  )
}

export function RulesHelpPanel() {
  return (
    <div className="h-full overflow-auto bg-white border border-zinc-200 rounded-lg">
      <div className="px-3 py-3 border-b border-zinc-100 flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-accent" />
        <span className="text-sm font-semibold text-zinc-800">Rule Reference</span>
      </div>

      <Section title="Rule Structure" icon={Braces} defaultOpen>
        <div className="space-y-2 text-xs text-zinc-600">
          <p>Every rule needs these top-level fields:</p>
          <pre className="bg-zinc-50 rounded p-2 font-mono text-[11px] text-zinc-700 overflow-x-auto">
{`rules:
  - id: unique_rule_id
    description: "What this rule detects"
    condition:
      ...
    issue_category: my_category
    severity: high`}
          </pre>
        </div>
      </Section>

      <Section title="Available Fields" icon={Hash}>
        <div className="space-y-1.5 text-xs text-zinc-600">
          <p className="text-zinc-500 mb-1">Fields you can match against on each event:</p>
          {[
            { field: 'type', desc: 'Event type: session_start, chat.completion, tool_call, tool_result, error, session_end' },
            { field: 'cost_usd', desc: 'Call cost in USD (number)' },
            { field: 'duration_ms', desc: 'Call duration in milliseconds (number)' },
            { field: 'status_code', desc: 'HTTP status code: 200, 429, 500, etc.' },
            { field: 'tool_name', desc: 'Name of the tool being called' },
            { field: 'model', desc: 'Model name: gpt-4o, claude-3-sonnet, etc.' },
            { field: 'content', desc: 'Response content text' },
            { field: 'error', desc: 'Error message string' },
            { field: 'tokens_used', desc: 'Total tokens consumed (number)' },
          ].map((f) => (
            <div key={f.field} className="flex gap-2">
              <code className="shrink-0 font-mono text-[11px] bg-zinc-100 px-1 py-0.5 rounded text-zinc-700">{f.field}</code>
              <span className="text-zinc-500">{f.desc}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Operators" icon={Gauge}>
        <div className="space-y-1.5 text-xs text-zinc-600">
          <p className="text-zinc-500 mb-1">Comparison operators for simple conditions:</p>
          {[
            { op: 'eq', desc: 'Equals (strict)' },
            { op: 'equals', desc: 'Equals (string compare)' },
            { op: 'ne', desc: 'Not equals' },
            { op: 'gt', desc: 'Greater than (numeric)' },
            { op: 'gte', desc: 'Greater than or equal' },
            { op: 'lt', desc: 'Less than (numeric)' },
            { op: 'lte', desc: 'Less than or equal' },
            { op: 'contains', desc: 'String contains substring' },
            { op: 'starts_with', desc: 'String starts with' },
            { op: 'exists', desc: 'Field is present and non-empty' },
          ].map((o) => (
            <div key={o.op} className="flex gap-2">
              <code className="shrink-0 font-mono text-[11px] bg-zinc-100 px-1 py-0.5 rounded text-zinc-700 w-20 text-center">{o.op}</code>
              <span className="text-zinc-500">{o.desc}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Composite Conditions" icon={Braces}>
        <div className="space-y-2 text-xs text-zinc-600">
          <p>Combine conditions with <code className="font-mono bg-zinc-100 px-1 rounded">and</code> or <code className="font-mono bg-zinc-100 px-1 rounded">or</code>:</p>
          <pre className="bg-zinc-50 rounded p-2 font-mono text-[11px] text-zinc-700 overflow-x-auto">
{`condition:
  and:
    - field: type
      op: equals
      value: "error"
    - field: status_code
      op: gte
      value: 500`}
          </pre>
        </div>
      </Section>

      <Section title="Repetition Detection" icon={Wrench}>
        <div className="space-y-2 text-xs text-zinc-600">
          <p>Detect when the same value repeats N times in a row:</p>
          <pre className="bg-zinc-50 rounded p-2 font-mono text-[11px] text-zinc-700 overflow-x-auto">
{`condition:
  field: tool_name
  op: exists
repetition:
  field: tool_name
  min_count: 5`}
          </pre>
        </div>
      </Section>

      <Section title="Severity Levels" icon={AlertTriangle}>
        <div className="space-y-1 text-xs text-zinc-600">
          {[
            { level: 'critical', color: 'text-rose-600', desc: 'Immediate attention required' },
            { level: 'high', color: 'text-orange-600', desc: 'Important, investigate soon' },
            { level: 'medium', color: 'text-amber-600', desc: 'Worth monitoring' },
            { level: 'low', color: 'text-zinc-500', desc: 'Informational' },
          ].map((s) => (
            <div key={s.level} className="flex items-center gap-2">
              <span className={cn('font-medium capitalize w-14', s.color)}>{s.level}</span>
              <span className="text-zinc-500">{s.desc}</span>
            </div>
          ))}
        </div>
      </Section>
    </div>
  )
}

function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(' ')
}
