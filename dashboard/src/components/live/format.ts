export function formatTs(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function latencyClass(ms: number | null): string {
  if (ms === null || ms === undefined) return ''
  if (ms < 500) return 'text-emerald-500'
  if (ms < 2000) return 'text-amber-500'
  return 'text-rose-500'
}

export function formatTokensCompact(n: number | null): string {
  if (n === null || n === undefined) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return `${n}`
}

export function formatCost(n: number | null): string {
  if (n === null || n === undefined) return '$0.0000'
  return `$${n.toFixed(4)}`
}
