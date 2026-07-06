import type { ToolEvent } from './LiveContext'
import { formatTs } from './format'
import { cn } from '@/lib/utils'

interface MessageRowProps {
  event: ToolEvent
  showContent: boolean
}

export function MessageRow({ event, showContent = true }: MessageRowProps) {
  const isUser = event.role === 'user'
  const isAssistant = event.role === 'assistant'

  const dotClass = isUser ? 'bg-blue-500' : isAssistant ? 'bg-violet-500' : 'bg-amber-500'
  const label = isUser ? 'USER' : isAssistant ? 'ASSISTANT' : 'SYSTEM'

  return (
    <div className={cn(
      'px-2 py-1 font-mono text-xs border-l-2 flex flex-col gap-0.5 hover:bg-muted/50',
      isUser ? 'border-blue-300' : isAssistant ? 'border-violet-300' : 'border-amber-300'
    )}>
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', dotClass)} />
        <span className="text-accent font-mono font-semibold shrink-0">{label}</span>
        {event.model && (
          <span className="text-muted-foreground/60 shrink-0 text-[10px] truncate max-w-[160px]">
            {event.model}
          </span>
        )}
        <span className="text-muted-foreground/60 font-mono shrink-0 text-[10px]">
          {formatTs(event.timestamp)}
        </span>
        {event.cost_usd != null && event.cost_usd > 0 && (
          <span className="ml-auto shrink-0 rounded bg-muted px-1 text-[10px] text-muted-foreground">
            ${event.cost_usd.toFixed(4)}
          </span>
        )}
      </div>
      {showContent && event.content && (
        <div className="text-[11px] text-foreground/90 whitespace-pre-wrap break-words pl-3.5 max-h-40 overflow-auto">
          {event.content}
        </div>
      )}
      {!showContent && event.content && (
        <div className="text-[10px] text-muted-foreground/50 pl-3.5 italic">
          (content hidden — {event.content.length} chars)
        </div>
      )}
    </div>
  )
}
