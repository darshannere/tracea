import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePolling } from '@/hooks/usePolling'
import { useAuth } from '@/hooks/useAuth'
import api from '@/lib/api'
import { AuthErrorState } from '@/components/layout/AuthErrorState'
import { MiniCostChart, MiniTokenChart } from '@/components/charts/MiniCharts'
import { Clock, Zap, AlertCircle, ArrowUpDown } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from '@tanstack/react-table'

interface Session {
  session_id: string
  started_at: string
  ended_at: string | null
  duration_ms: number | null
  total_cost: number | null
  total_tokens: number | null
  event_count: number | null
  issue_count: number | null
}

function computeDuration(session: Session): number {
  if (session.duration_ms !== null) return session.duration_ms
  const start = new Date(session.started_at).getTime()
  const end = session.ended_at ? new Date(session.ended_at).getTime() : Date.now()
  return end - start
}

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
}

function formatCost(cost: number | null): string {
  if (cost === null) return '-'
  return `$${cost.toFixed(4)}`
}

function formatTokens(tokens: number | null): string {
  if (tokens === null) return '-'
  return tokens.toLocaleString()
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

export function SessionsPage() {
  const { hasKey } = useAuth()
  const navigate = useNavigate()
  const [sorting, setSorting] = useState<SortingState>([])

  const { data, error } = usePolling(async () => {
    const res = await api.get<{ sessions: Session[]; total: number }>('/api/v1/sessions')
    return res.data
  })

  const sessions: Session[] = data?.sessions ?? []
  const total = data?.total ?? 0

  const columns: ColumnDef<Session>[] = useMemo(
    () => [
      {
        accessorKey: 'session_id',
        header: 'Session ID',
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.session_id.slice(0, 8)}...</span>
        ),
      },
      {
        accessorKey: 'started_at',
        header: 'Start Time',
        cell: ({ row }) => formatDate(row.original.started_at),
      },
      {
        id: 'duration',
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 hover:text-accent"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Duration
            <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        accessorFn: (row) => computeDuration(row),
        cell: ({ row }) => formatDuration(computeDuration(row.original)),
      },
      {
        accessorKey: 'total_cost',
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 hover:text-accent"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Cost
            <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        cell: ({ row }) => formatCost(row.original.total_cost),
      },
      {
        accessorKey: 'total_tokens',
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 hover:text-accent"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Tokens
            <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        cell: ({ row }) => formatTokens(row.original.total_tokens),
      },
      {
        accessorKey: 'event_count',
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 hover:text-accent"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Events
            <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        cell: ({ row }) => row.original.event_count ?? '-',
      },
      {
        accessorKey: 'issue_count',
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 hover:text-accent"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Issues
            <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        cell: ({ row }) => {
          const count = row.original.issue_count
          if (count === null || count === 0) return <span className="text-zinc-400">-</span>
          return (
            <Badge variant="error" className="gap-1">
              <AlertCircle className="h-3 w-3" />
              {count}
            </Badge>
          )
        },
      },
    ],
    []
  )

  const table = useReactTable({
    data: sessions,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const aggregatedMetrics = useMemo(() => {
    const dailyCost: Record<string, number> = {}
    const dailyTokens: Record<string, number> = {}

    sessions.forEach((s) => {
      if (!s.started_at) return
      const day = s.started_at.split('T')[0]
      dailyCost[day] = (dailyCost[day] ?? 0) + (s.total_cost ?? 0)
      dailyTokens[day] = (dailyTokens[day] ?? 0) + (s.total_tokens ?? 0)
    })

    const costSeries = Object.entries(dailyCost)
      .map(([date, cost]) => ({ date, cost }))
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-30)

    const tokenSeries = Object.entries(dailyTokens)
      .map(([date, tokens]) => ({ date, tokens }))
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-30)

    return { costSeries, tokenSeries }
  }, [sessions])

  if (!hasKey) {
    return <AuthErrorState />
  }

  if (data === null) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Zap className="h-5 w-5 text-accent" />
          <h2 className="text-xl font-semibold">Sessions</h2>
        </div>
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
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

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <Clock className="h-8 w-8 mb-2" />
        <p className="text-sm font-medium">No sessions yet</p>
        <p className="text-xs text-zinc-400">Start using the SDK to see your first session</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Zap className="h-5 w-5 text-accent" />
          <h2 className="text-xl font-semibold">Sessions</h2>
          <span className="text-sm text-zinc-500">{total} total</span>
        </div>
      </div>

      {aggregatedMetrics.costSeries.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <div className="border border-zinc-200 rounded-lg p-4">
            <h3 className="text-sm font-medium text-zinc-700 mb-3">Cost per Day</h3>
            <MiniCostChart data={aggregatedMetrics.costSeries} />
          </div>
          <div className="border border-zinc-200 rounded-lg p-4">
            <h3 className="text-sm font-medium text-zinc-700 mb-3">Tokens per Day</h3>
            <MiniTokenChart data={aggregatedMetrics.tokenSeries} />
          </div>
        </div>
      )}

      <div className="border border-zinc-200 rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id} className="bg-zinc-50">
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                className="cursor-pointer"
                onClick={() => navigate(`/sessions/${row.original.session_id}`)}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
