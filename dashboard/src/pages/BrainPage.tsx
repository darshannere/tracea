import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { usePolling } from '@/hooks/usePolling'
import { useUser } from '@/hooks/UserContext'
import api from '@/lib/api'
import { Brain, Search, Share2, X, Trash2, Download, Activity } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface BrainEntry {
  id: string
  user_id: string
  category: 'workflow' | 'error_fix' | 'codebase'
  title: string
  content: string
  confidence: number
  hit_count: number
  source_sessions: string[]
  created_at: string
  updated_at: string
}

interface BrainListResponse {
  entries: BrainEntry[]
  next_cursor: string | null
  total: number
}

interface GraphNode {
  id: string
  category: string
  title: string
  confidence: number
  hit_count: number
}

interface GraphEdge {
  source: string
  target: string
  weight: number
}

interface GraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

interface SynthStatus {
  pending: number
  in_progress: number
  done: number
  failed: number
  entries_total: number
}

const BADGE_COLORS: Record<string, string> = {
  workflow: 'bg-violet-100 text-violet-700',
  error_fix: 'bg-rose-100 text-rose-700',
  codebase: 'bg-sky-100 text-sky-700',
}

function CategoryBadge({ category }: { category: string }) {
  return (
    <span className={cn('text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded', BADGE_COLORS[category] ?? BADGE_COLORS.workflow)}>
      {category.replace('_', ' ')}
    </span>
  )
}

/* ── Knowledge Graph ── */

function BrainGraph({ data }: { data: GraphResponse }) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 })

  useEffect(() => {
    const updateSize = () => {
      if (svgRef.current?.parentElement) {
        const rect = svgRef.current.parentElement.getBoundingClientRect()
        setDimensions({ width: rect.width, height: Math.max(400, rect.height) })
      }
    }
    updateSize()
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
  }, [])

  const { nodes, edges } = useMemo(() => {
    const { width, height } = dimensions
    const nodeMap = new Map<string, { x: number; y: number; data: GraphNode }>()

    data.nodes.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(data.nodes.length, 1)
      const radius = Math.min(width, height) * 0.35
      nodeMap.set(n.id, {
        x: width / 2 + radius * Math.cos(angle),
        y: height / 2 + radius * Math.sin(angle),
        data: n,
      })
    })

    for (let iter = 0; iter < 60; iter++) {
      const ids = Array.from(nodeMap.keys())
      for (let i = 0; i < ids.length; i++) {
        for (let j = i + 1; j < ids.length; j++) {
          const a = nodeMap.get(ids[i])!
          const b = nodeMap.get(ids[j])!
          const dx = a.x - b.x
          const dy = a.y - b.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const force = 2000 / (dist * dist + 100)
          a.x += (dx / dist) * force; a.y += (dy / dist) * force
          b.x -= (dx / dist) * force; b.y -= (dy / dist) * force
        }
      }

      data.edges.forEach((edge) => {
        const a = nodeMap.get(edge.source)
        const b = nodeMap.get(edge.target)
        if (!a || !b) return
        const dx = b.x - a.x; const dy = b.y - a.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const f = dist * 0.01 * edge.weight
        a.x += (dx / dist) * f; a.y += (dy / dist) * f
        b.x -= (dx / dist) * f; b.y -= (dy / dist) * f
      })

      nodeMap.forEach((n) => {
        n.x += (width / 2 - n.x) * 0.05
        n.y += (height / 2 - n.y) * 0.05
      })
    }

    return {
      nodes: Array.from(nodeMap.values()),
      edges: data.edges.map((e) => ({
        ...e,
        sourceNode: nodeMap.get(e.source),
        targetNode: nodeMap.get(e.target),
      })).filter((e) => e.sourceNode && e.targetNode),
    }
  }, [data, dimensions])

  if (data.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
        <Share2 className="h-8 w-8 mb-2" />
        <p className="text-sm font-medium">No graph data yet</p>
        <p className="text-xs">Process more sessions to build the knowledge graph</p>
      </div>
    )
  }

  const nodeColors: Record<string, string> = {
    workflow: '#a5b4fc',
    error_fix: '#fda4af',
    codebase: '#7dd3fc',
  }

  return (
    <div className="w-full h-[500px] border border-border rounded-lg bg-card relative overflow-hidden">
      <svg ref={svgRef} width={dimensions.width} height={dimensions.height}>
        {edges.map((e, i) => (
          <line
            key={i}
            x1={e.sourceNode!.x} y1={e.sourceNode!.y}
            x2={e.targetNode!.x} y2={e.targetNode!.y}
            stroke="#d4d4d8" strokeWidth={Math.min(4, 1 + e.weight * 0.5)} opacity={0.5}
          />
        ))}
        {nodes.map((n) => {
          const color = nodeColors[n.data.category] ?? '#a5b4fc'
          const isHovered = hoveredNode === n.data.id
          const radius = 6 + Math.min(14, n.data.hit_count * 3)
          return (
            <g
              key={n.data.id}
              transform={`translate(${n.x}, ${n.y})`}
              onMouseEnter={() => setHoveredNode(n.data.id)}
              onMouseLeave={() => setHoveredNode(null)}
              className="cursor-pointer"
            >
              <circle
                r={radius + (isHovered ? 4 : 0)}
                fill={color}
                stroke={isHovered ? '#18181b' : '#a1a1aa'}
                strokeWidth={isHovered ? 2 : 1}
                opacity={0.9}
              />
              {isHovered && (
                <g transform={`translate(0, ${-radius - 12})`}>
                  <rect x={-80} y={-22} width={160} height={20} rx={4} fill="#18181b" />
                  <text y={-8} textAnchor="middle" fill="white" fontSize={10} fontFamily="sans-serif">
                    {n.data.title.slice(0, 30)}{n.data.title.length > 30 ? '…' : ''}
                  </text>
                </g>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/* ── Brain Page ── */

export function BrainPage() {
  const { selectedUser } = useUser()
  const [view, setView] = useState<'list' | 'graph'>('list')
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [allEntries, setAllEntries] = useState<BrainEntry[]>([])

  const { data, error } = usePolling(async () => {
    const params = new URLSearchParams()
    if (selectedUser) params.append('user_id', selectedUser)
    if (category) params.append('category', category)
    if (search) params.append('q', search)
    if (cursor) params.append('cursor', cursor)
    params.append('limit', '50')
    const res = await api.get<BrainListResponse>(`/api/v1/brain/entries?${params.toString()}`)
    return res.data
  })

  const { data: synthStatus } = usePolling(async () => {
    const params = new URLSearchParams()
    if (selectedUser) params.append('user_id', selectedUser)
    const res = await api.get<SynthStatus>(`/api/v1/brain/status?${params.toString()}`)
    return res.data
  }, 30000)

  const { data: graphData } = usePolling(async () => {
    const params = new URLSearchParams()
    if (selectedUser) params.append('user_id', selectedUser)
    const res = await api.get<GraphResponse>(`/api/v1/brain/graph?${params.toString()}`)
    return res.data
  }, 30000)

  useEffect(() => {
    if (data && cursor === null) setAllEntries(data.entries)
    else if (data && cursor) {
      setAllEntries((prev) => {
        const existingIds = new Set(prev.map((e) => e.id))
        return [...prev, ...data.entries.filter((e) => !existingIds.has(e.id))]
      })
    }
  }, [data, cursor])

  const hasMore = data?.next_cursor ?? false

  const handleSearch = useCallback((value: string) => {
    setSearch(value); setCursor(null); setAllEntries([])
  }, [])

  const handleCategoryChange = useCallback((cat: string | null) => {
    setCategory(cat); setCursor(null); setAllEntries([])
  }, [])

  const loadMore = useCallback(() => {
    if (data?.next_cursor) setCursor(data.next_cursor)
  }, [data])

  const groupedEntries = useMemo(() => {
    const groups: Record<string, BrainEntry[]> = {}
    allEntries.forEach((e) => {
      if (!groups[e.category]) groups[e.category] = []
      groups[e.category].push(e)
    })
    return groups
  }, [allEntries])

  const categoryOrder = ['workflow', 'error_fix', 'codebase']
  const categoryLabels: Record<string, string> = {
    workflow: 'Workflows',
    error_fix: 'Error Fixes',
    codebase: 'Codebase',
  }

  if (error && allEntries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
        <Brain className="h-8 w-8 mb-2" />
        <p className="text-sm">Failed to load brain entries</p>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Topbar */}
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div>
          <h2 className="text-base font-semibold">Company Brain</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {synthStatus
              ? `${synthStatus.entries_total} entries · ${synthStatus.done} synthesized · ${synthStatus.pending} pending${synthStatus.failed > 0 ? ` · ${synthStatus.failed} failed` : ''}`
              : 'Loading synthesis status…'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {view === 'list' && (
            <button
              onClick={() => {
                const content = allEntries.map((e) => `## ${e.title}\n\n${e.content}`).join('\n\n')
                const blob = new Blob([`# Company Brain\n\n${content}`], { type: 'text/markdown' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url; a.download = 'CLAUDE.md'
                a.click(); URL.revokeObjectURL(url)
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded hover:opacity-90 transition-opacity"
            >
              <Download className="h-3.5 w-3.5" />
              Download as CLAUDE.md
            </button>
          )}
          <button
            onClick={() => setView('list')}
            className={cn(
              'p-2 rounded border transition-colors text-xs',
              view === 'list' ? 'bg-accent text-white border-accent' : 'border-border text-muted-foreground hover:text-foreground'
            )}
            title="List view"
          >
            <span className="text-xs">▦</span>
          </button>
          <button
            onClick={() => setView('graph')}
            className={cn(
              'p-2 rounded border transition-colors',
              view === 'graph' ? 'bg-accent text-white border-accent' : 'border-border text-muted-foreground hover:text-foreground'
            )}
            title="Graph view"
          >
            <Share2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Live status banner */}
      <div className="flex items-center gap-2.5 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2.5">
        <span className="w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0" />
        <span className="text-xs font-medium text-emerald-700">
          Brain is live. Synthesizing from agent sessions automatically.
          New session ends → brain updates in ~30s.
        </span>
      </div>

      {view === 'list' && (
        <>
          {/* Search + Filters */}
          <div className="flex items-center gap-2.5">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search knowledge..."
                value={search}
                onChange={(e) => handleSearch(e.target.value)}
                className="w-full pl-8 pr-8 py-1.5 text-xs bg-card border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent text-foreground placeholder:text-muted-foreground"
              />
              {search && (
                <button onClick={() => handleSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
            <div className="flex items-center gap-1">
              {[
                { key: null, label: 'All' },
                { key: 'workflow', label: 'Workflows' },
                { key: 'error_fix', label: 'Error Fixes' },
                { key: 'codebase', label: 'Codebase' },
              ].map(({ key, label }) => (
                <button
                  key={label}
                  onClick={() => handleCategoryChange(key)}
                  className={cn(
                    'px-2.5 py-1 rounded text-[11px] font-medium border transition-colors',
                    category === key
                      ? 'bg-foreground text-background border-foreground'
                      : 'bg-card border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground/50'
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Entries */}
          {allEntries.length === 0 && data === null ? (
            <div className="space-y-2.5">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full rounded-lg" />
              ))}
            </div>
          ) : allEntries.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
              <Brain className="h-8 w-8 mb-2" />
              <p className="text-sm font-medium">No brain entries yet</p>
              <p className="text-xs mt-0.5">
                {search ? 'Try a different search term' : 'Sessions will be synthesized into knowledge automatically'}
              </p>
            </div>
          ) : (
            <div>
              {category === null ? (
                /* Grouped by category */
                categoryOrder.map((cat) => {
                  const entries = groupedEntries[cat]
                  if (!entries || entries.length === 0) return null
                  return (
                    <div key={cat} className="mb-6">
                      <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-2.5">
                        {categoryLabels[cat]}
                      </p>
                      <div className="space-y-2.5">
                        {entries.map((entry) => (
                          <BrainEntryCard key={entry.id} entry={entry} />
                        ))}
                      </div>
                    </div>
                  )
                })
              ) : (
                /* Flat list when filtered */
                <div className="space-y-2.5">
                  {allEntries.map((entry) => (
                    <BrainEntryCard key={entry.id} entry={entry} />
                  ))}
                </div>
              )}
              {hasMore && (
                <button
                  onClick={loadMore}
                  className="w-full mt-3 py-2 text-xs font-medium text-muted-foreground bg-secondary border border-border rounded-lg hover:bg-muted transition-colors"
                >
                  Load more
                </button>
              )}
            </div>
          )}
        </>
      )}

      {view === 'graph' && (
        <BrainGraph data={graphData ?? { nodes: [], edges: [] }} />
      )}
    </div>
  )
}

function BrainEntryCard({ entry }: { entry: BrainEntry }) {
  const [expanded, setExpanded] = useState(false)

  const handleDelete = async () => {
    if (!confirm('Delete this brain entry?')) return
    try {
      await api.delete(`/api/v1/brain/entries/${entry.id}`)
      window.location.reload()
    } catch {
      alert('Failed to delete entry')
    }
  }

  return (
    <div className="border border-border rounded-lg bg-card p-3.5 hover:border-muted-foreground/50 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <CategoryBadge category={entry.category} />
            <span className="text-[10px] text-muted-foreground font-medium">
              Confidence {Math.round(entry.confidence * 10)}/10
            </span>
            {entry.hit_count > 1 && (
              <span className="text-[10px] text-muted-foreground bg-secondary px-1.5 py-0.5 rounded">
                reinforced ×{entry.hit_count}
              </span>
            )}
          </div>
          <h3 className="text-[13px] font-semibold leading-snug">{entry.title}</h3>
        </div>
        <button
          onClick={handleDelete}
          className="text-muted-foreground hover:text-destructive transition-colors p-1 flex-shrink-0"
          title="Delete"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>

      <pre className={cn(
        'mt-2 text-[11px] leading-relaxed bg-secondary border border-border rounded-md p-2.5 overflow-hidden',
        !expanded ? 'max-h-20' : ''
      )}>
        {entry.content}
      </pre>

      {entry.content.length > 200 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-1.5 text-[11px] text-accent hover:underline"
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}

      <div className="mt-2.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
        <Activity className="h-3 w-3" />
        <span>
          {entry.source_sessions.length} session{entry.source_sessions.length !== 1 ? 's' : ''} · derived from {entry.source_sessions.slice(0, 2).join(', ')}{entry.source_sessions.length > 2 ? ` +${entry.source_sessions.length - 2} more` : ''} · last updated {new Date(entry.updated_at).toLocaleString()}
        </span>
      </div>
    </div>
  )
}