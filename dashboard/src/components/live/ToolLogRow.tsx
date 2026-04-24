import type { ToolEvent } from './LiveContext'
import { formatTs, formatDuration, latencyClass, formatTokensCompact } from './format'
import { cn } from '@/lib/utils'

interface ToolLogRowProps {
  event: ToolEvent
}

export function ToolLogRow({ event }: ToolLogRowProps) {
  const isError = event.exit_status !== null && event.exit_status !== 0
  const isInProgress = event.hook_type === 'PreToolUse' && event.duration_ms === null
  const hasTokenBadge = event.nearest_input_tokens !== null && event.nearest_input_tokens > 0

  const rowClass = cn(
    'px-2 py-1 font-mono text-xs border-l-2 flex flex-col gap-0 hover:bg-zinc-50',
    isError
      ? 'border-rose-400 bg-rose-50/50'
      : 'border-transparent',
    isInProgress ? 'opacity-70' : ''
  )

  const latCls = latencyClass(event.duration_ms)

  return (
    <div className={rowClass}>
      {/* Line 1: tool_name | timestamp | latency | token badge */}
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn(
          'h-1.5 w-1.5 rounded-full shrink-0',
          isError
            ? 'bg-rose-500'
            : isInProgress
              ? 'bg-accent animate-pulse'
              : 'bg-emerald-500'
        )} />
        <span className="text-accent font-mono font-semibold truncate shrink-0 max-w-[140px]">
          {event.tool_name}
        </span>
        <span className="text-zinc-400 font-mono shrink-0 text-[10px]">
          {formatTs(event.timestamp)}
        </span>
        <span className={cn('shrink-0 text-[10px]', latCls || 'text-zinc-400')}>
          {formatDuration(event.duration_ms)}
        </span>
        {hasTokenBadge && (
          <span className="ml-auto shrink-0 rounded bg-zinc-100 px-1 text-[10px] text-zinc-600">
            {formatTokensCompact(event.nearest_input_tokens)}↑{' '}
            {formatTokensCompact(event.nearest_output_tokens ?? 0)}↓
          </span>
        )}
      </div>

      {/* Line 2 (conditional): tool_summary */}
      {event.tool_summary && (
        <div
          className="text-[10px] text-zinc-500 font-mono truncate"
          title={event.tool_summary}
        >
          {event.tool_summary}
        </div>
      )}
    </div>
  )
}
