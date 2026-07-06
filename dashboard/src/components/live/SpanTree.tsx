import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { cn } from '@/lib/utils'

interface SpanNode {
  trace_id: string
  span_id: string
  parent_span_id: string | null
  name: string
  kind: number
  start_time: string
  end_time: string | null
  attributes: string  // JSON
  children: SpanNode[]
}

interface SpanTreeProps {
  sessionId: string
}

export function SpanTree({ sessionId }: SpanTreeProps) {
  const [roots, setRoots] = useState<SpanNode[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await api.get<{ spans: SpanNode[] }>(
          `/api/v1/sessions/${sessionId}/spans`
        )
        if (!cancelled) setRoots(res.data.spans)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 5000)  // refresh while session is active
    return () => { cancelled = true; clearInterval(id) }
  }, [sessionId])

  if (loading) return <div className="text-xs text-muted-foreground p-2">Loading spans...</div>
  if (roots.length === 0) return <div className="text-xs text-muted-foreground/60 p-2">No spans for this session.</div>

  return (
    <div className="overflow-auto flex-1 font-mono text-xs p-2">
      {roots.map((r) => <SpanNodeView key={r.span_id} node={r} depth={0} />)}
    </div>
  )
}

function SpanNodeView({ node, depth }: { node: SpanNode; depth: number }) {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = node.children.length > 0
  const duration = node.start_time && node.end_time
    ? new Date(node.end_time).getTime() - new Date(node.start_time).getTime()
    : null

  // Heuristic: is this a tool span?
  const isTool = node.name.includes('tool') || node.name.includes('Tool')
  const isLlm = node.name.includes('llm') || node.name.includes('chat') || node.name.includes('interaction')

  return (
    <div style={{ paddingLeft: depth * 16 }}>
      <div
        className="flex items-center gap-1.5 py-0.5 hover:bg-muted/40 cursor-pointer"
        onClick={() => hasChildren && setExpanded(!expanded)}
      >
        {hasChildren ? (
          <span className="text-muted-foreground w-3">{expanded ? '▾' : '▸'}</span>
        ) : (
          <span className="w-3" />
        )}
        <span className={cn(
          'h-1.5 w-1.5 rounded-full shrink-0',
          isTool ? 'bg-emerald-500' : isLlm ? 'bg-violet-500' : 'bg-muted-foreground'
        )} />
        <span className="text-foreground/90 truncate">{node.name}</span>
        {duration != null && (
          <span className="text-muted-foreground/60 text-[10px] shrink-0">
            {duration < 1000 ? `${duration}ms` : `${(duration/1000).toFixed(1)}s`}
          </span>
        )}
      </div>
      {expanded && hasChildren && (
        <div>
          {node.children.map((c) => <SpanNodeView key={c.span_id} node={c} depth={depth + 1} />)}
        </div>
      )}
    </div>
  )
}
