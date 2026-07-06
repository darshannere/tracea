import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend,
} from 'recharts'
import api from '@/lib/api'
import { Card } from '@/components/ui/card'

interface MetricPoint { timestamp: string; value: number; attributes: Record<string, unknown> }
interface MetricsByCategory { [metricName: string]: MetricPoint[] }

interface MetricsChartsProps {
  sessionId: string
}

export function MetricsCharts({ sessionId }: MetricsChartsProps) {
  const [data, setData] = useState<MetricsByCategory>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await api.get<{ metrics: MetricsByCategory }>(
          `/api/v1/sessions/${sessionId}/metrics`
        )
        if (!cancelled) setData(res.data.metrics)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 10000)
    return () => { cancelled = true; clearInterval(id) }
  }, [sessionId])

  if (loading) return <div className="text-xs text-muted-foreground p-4">Loading metrics...</div>

  const costSeries = collectSeries(data, ['claude_code.cost.usage'])
  const tokenInput = collectSeries(data, ['gen_ai.client.token.usage', 'claude_code.token.usage'],
    (p) => p.attributes?.['gen_ai.token.type'] === 'input')
  const tokenOutput = collectSeries(data, ['gen_ai.client.token.usage', 'claude_code.token.usage'],
    (p) => p.attributes?.['gen_ai.token.type'] === 'output')

  if (Object.keys(data).length === 0) {
    return <div className="text-xs text-muted-foreground/60 p-4">No metrics for this session.</div>
  }

  return (
    <div className="grid grid-cols-2 gap-4 p-4">
      {costSeries.length > 0 && (
        <Card className="p-3">
          <h3 className="text-xs font-semibold mb-2">Cost over time (USD)</h3>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={costSeries}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis dataKey="t" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey="v" stroke="#10b981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}
      {(tokenInput.length > 0 || tokenOutput.length > 0) && (
        <Card className="p-3">
          <h3 className="text-xs font-semibold mb-2">Token usage</h3>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={mergeTokenSeries(tokenInput, tokenOutput)}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis dataKey="t" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line type="monotone" dataKey="input" stroke="#3b82f6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="output" stroke="#8b5cf6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  )
}

function collectSeries(
  data: MetricsByCategory,
  names: string[],
  filterFn?: (p: MetricPoint) => boolean,
): { t: string; v: number }[] {
  for (const n of names) {
    if (data[n]) {
      let pts = data[n]
      if (filterFn) pts = pts.filter(filterFn)
      return pts.map((p) => ({ t: p.timestamp.slice(11, 19), v: p.value }))
    }
  }
  return []
}

function mergeTokenSeries(inp: { t: string; v: number }[], out: { t: string; v: number }[]) {
  // Simple merge keyed on index (assumes both series align); refine if timestamps differ
  const len = Math.max(inp.length, out.length)
  const merged: { t: string; input: number | null; output: number | null }[] = []
  for (let i = 0; i < len; i++) {
    merged.push({
      t: inp[i]?.t ?? out[i]?.t ?? '',
      input: inp[i]?.v ?? null,
      output: out[i]?.v ?? null,
    })
  }
  return merged
}
