import { BookOpen, Hash, Zap, Globe, Timer } from 'lucide-react'

export function AlertsHelpPanel() {
  return (
    <div className="h-full overflow-auto bg-white border border-zinc-200 rounded-lg">
      <div className="px-3 py-3 border-b border-zinc-100 flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-accent" />
        <span className="text-sm font-semibold text-zinc-800">Alerts Reference</span>
      </div>

      <div className="p-3 space-y-4 text-xs text-zinc-600">
        <div>
          <p className="text-zinc-500 mb-1.5">Each route sends matching issues to a webhook:</p>
          <pre className="bg-zinc-50 rounded p-2 font-mono text-[11px] text-zinc-700 overflow-x-auto">
{`routes:
  - issue_category: tool_error
    route_type: slack
    webhook_url: "\${SLACK_WEBHOOK_URL}"
    rate_limit_rpm: 60`}
          </pre>
        </div>

        <div className="space-y-1.5">
          <h4 className="font-medium text-zinc-700 flex items-center gap-1.5">
            <Hash className="h-3 w-3 text-zinc-400" />
            Fields
          </h4>
          {[
            { field: 'issue_category', desc: 'Category from detection rule, or "*" for catch-all' },
            { field: 'route_type', desc: '"slack" or "http" (generic webhook)' },
            { field: 'webhook_url', desc: 'Full webhook URL. Supports ${ENV_VAR} syntax' },
            { field: 'rate_limit_rpm', desc: 'Max messages per minute (default: 60)' },
          ].map((f) => (
            <div key={f.field} className="flex gap-2">
              <code className="shrink-0 font-mono text-[11px] bg-zinc-100 px-1 py-0.5 rounded text-zinc-700">{f.field}</code>
              <span className="text-zinc-500">{f.desc}</span>
            </div>
          ))}
        </div>

        <div className="space-y-1.5">
          <h4 className="font-medium text-zinc-700 flex items-center gap-1.5">
            <Zap className="h-3 w-3 text-zinc-400" />
            Route Types
          </h4>
          <div className="flex gap-2">
            <code className="shrink-0 font-mono text-[11px] bg-zinc-100 px-1 py-0.5 rounded text-zinc-700 w-14 text-center">slack</code>
            <span className="text-zinc-500">Sends formatted Slack message with issue details</span>
          </div>
          <div className="flex gap-2">
            <code className="shrink-0 font-mono text-[11px] bg-zinc-100 px-1 py-0.5 rounded text-zinc-700 w-14 text-center">http</code>
            <span className="text-zinc-500">Generic POST webhook for Zapier, Make, PagerDuty, etc.</span>
          </div>
        </div>

        <div className="space-y-1.5">
          <h4 className="font-medium text-zinc-700 flex items-center gap-1.5">
            <Globe className="h-3 w-3 text-zinc-400" />
            Environment Variables
          </h4>
          <p className="text-zinc-500">
            Use <code className="font-mono bg-zinc-100 px-1 rounded">{'${VAR_NAME}'}</code> in webhook_url to inject secrets without hardcoding them.
          </p>
        </div>

        <div className="space-y-1.5">
          <h4 className="font-medium text-zinc-700 flex items-center gap-1.5">
            <Timer className="h-3 w-3 text-zinc-400" />
            Rate Limiting
          </h4>
          <p className="text-zinc-500">
            rate_limit_rpm caps how many alerts go to a destination per minute. Use a catch-all route with low RPM as a safety net.
          </p>
        </div>
      </div>
    </div>
  )
}
