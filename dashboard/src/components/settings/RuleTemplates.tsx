import { useState } from 'react'
import { Plus, ChevronDown, Copy, Check } from 'lucide-react'
import { toast } from 'sonner'

interface RuleTemplate {
  label: string
  description: string
  yaml: string
}

export const RULE_TEMPLATES: RuleTemplate[] = [
  {
    label: 'Tool Error',
    description: 'Detect when an LLM API call returns an error',
    yaml: `  - id: my_tool_error
    description: "LLM API call returned an error"
    condition:
      exists: error
    issue_category: tool_error
    severity: high`,
  },
  {
    label: 'High Cost',
    description: 'Flag individual calls costing more than a threshold',
    yaml: `  - id: my_high_cost
    description: "Individual call cost exceeds $0.10"
    condition:
      field: cost_usd
      op: gt
      value: 0.10
    issue_category: high_cost
    severity: high`,
  },
  {
    label: 'High Latency',
    description: 'Detect calls taking longer than a threshold',
    yaml: `  - id: my_high_latency
    description: "Call duration exceeds 10 seconds"
    condition:
      field: duration_ms
      op: gt
      value: 10000
    issue_category: high_latency
    severity: medium`,
  },
  {
    label: 'Rate Limit (429)',
    description: 'Detect API rate limit responses',
    yaml: `  - id: my_rate_limit
    description: "API returned 429 rate limit response"
    condition:
      field: status_code
      op: eq
      value: 429
    issue_category: rate_limit_hit
    severity: high`,
  },
  {
    label: 'Model 5xx Error',
    description: 'Detect model provider server errors',
    yaml: `  - id: my_model_5xx
    description: "Model provider returned 5xx error"
    condition:
      and:
        - field: status_code
          op: gte
          value: 500
        - field: status_code
          op: lt
          value: 600
    issue_category: model_error_5xx
    severity: high`,
  },
  {
    label: 'Empty Response',
    description: 'Detect empty content from chat.completion or tool_result',
    yaml: `  - id: my_empty_response
    description: "LLM returned empty content"
    condition:
      or:
        - and:
            - field: type
              op: equals
              value: "chat.completion"
            - field: content
              op: eq
              value: ""
        - and:
            - field: type
              op: equals
              value: "tool_result"
            - field: content
              op: eq
              value: ""
    issue_category: empty_response
    severity: medium`,
  },
  {
    label: 'Repeated Tool Call',
    description: 'Same tool called N+ times in a row',
    yaml: `  - id: my_repeated_tool
    description: "Same tool called 5+ times in a row"
    condition:
      field: tool_name
      op: exists
    repetition:
      field: tool_name
      min_count: 5
    issue_category: repeated_tool_call
    severity: medium`,
  },
]

interface RuleTemplatesProps {
  onAppend: (yaml: string) => void
}

export function RuleTemplates({ onAppend }: RuleTemplatesProps) {
  const [open, setOpen] = useState(false)
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)

  const handleAppend = (template: RuleTemplate, _index: number) => {
    onAppend(template.yaml)
    toast.success(`Added "${template.label}" rule`)
    setOpen(false)
  }

  const handleCopy = async (template: RuleTemplate, _index: number) => {
    try {
      await navigator.clipboard.writeText(template.yaml)
      setCopiedIndex(_index)
      toast.success(`Copied "${template.label}" to clipboard`)
      setTimeout(() => setCopiedIndex(null), 2000)
    } catch {
      toast.error('Failed to copy')
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs font-medium text-zinc-700 bg-white border border-zinc-300 rounded-md px-2.5 py-1.5 hover:bg-zinc-50 transition-colors"
      >
        <Plus className="h-3.5 w-3.5" />
        Add Rule Template
        <ChevronDown className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-0 mt-1 w-80 bg-white border border-zinc-200 rounded-lg shadow-lg z-20 py-1 max-h-80 overflow-auto">
            {RULE_TEMPLATES.map((template, i) => (
              <div
                key={template.label}
                className="px-3 py-2 hover:bg-zinc-50 border-b border-zinc-100 last:border-0"
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    onClick={() => handleAppend(template, i)}
                    className="text-left flex-1"
                  >
                    <div className="text-sm font-medium text-zinc-800">{template.label}</div>
                    <div className="text-xs text-zinc-500 mt-0.5">{template.description}</div>
                  </button>
                  <button
                    onClick={() => handleCopy(template, i)}
                    className="shrink-0 p-1 text-zinc-400 hover:text-zinc-600 transition-colors"
                    title="Copy YAML"
                  >
                    {copiedIndex === i ? (
                      <Check className="h-3.5 w-3.5 text-green-600" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(' ')
}
