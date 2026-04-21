import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  CartesianGrid,
  Tooltip,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
} from 'recharts'

const COLORS = {
  indigo: '#6366f1',
  emerald: '#10b981',
  sky: '#0ea5e9',
  amber: '#f59e0b',
  rose: '#f43f5e',
  violet: '#8b5cf6',
  zinc: '#a1a1aa',
}

const tooltipStyle = {
  fontSize: 12,
  borderRadius: 6,
  border: '1px solid #e4e4e7',
  background: '#fff',
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
}

// ─── Cost per Day ───

interface CostChartProps {
  data: { date: string; cost: number }[]
}

export function CostChart({ data }: CostChartProps) {
  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${v.toFixed(2)}`}
          width={44}
        />
        <Tooltip
          formatter={(value: number) => [`$${value.toFixed(4)}`, 'Cost']}
          contentStyle={tooltipStyle}
          labelStyle={{ color: '#18181b', fontWeight: 500, marginBottom: 4 }}
        />
        <Line
          type="monotone"
          dataKey="cost"
          name="Cost"
          stroke={COLORS.indigo}
          strokeWidth={2}
          dot={{ fill: COLORS.indigo, r: 2 }}
          activeDot={{ r: 4, strokeWidth: 0 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

// ─── Tokens per Day ───

interface TokenChartProps {
  data: { date: string; tokens: number }[]
}

export function TokenChart({ data }: TokenChartProps) {
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
          width={44}
        />
        <Tooltip
          formatter={(value: number) => [value.toLocaleString(), 'Tokens']}
          contentStyle={tooltipStyle}
          labelStyle={{ color: '#18181b', fontWeight: 500, marginBottom: 4 }}
        />
        <Bar
          dataKey="tokens"
          name="Tokens"
          fill={COLORS.sky}
          radius={[3, 3, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

// ─── Events per Day ───

interface EventsChartProps {
  data: { date: string; events: number }[]
}

export function EventsChart({ data }: EventsChartProps) {
  return (
    <ResponsiveContainer width="100%" height={160}>
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="eventsGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={COLORS.emerald} stopOpacity={0.2} />
            <stop offset="95%" stopColor={COLORS.emerald} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          width={40}
        />
        <Tooltip
          formatter={(value: number) => [value.toLocaleString(), 'Events']}
          contentStyle={tooltipStyle}
          labelStyle={{ color: '#18181b', fontWeight: 500, marginBottom: 4 }}
        />
        <Area
          type="monotone"
          dataKey="events"
          name="Events"
          stroke={COLORS.emerald}
          strokeWidth={2}
          fill="url(#eventsGradient)"
          dot={{ fill: COLORS.emerald, r: 2 }}
          activeDot={{ r: 4, strokeWidth: 0 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ─── Duration Distribution ───

interface DurationChartProps {
  sessions: { duration_ms: number | null; started_at: string; ended_at: string | null }[]
}

export function DurationDistributionChart({ sessions }: DurationChartProps) {
  const buckets = [
    { label: '< 1 min', min: 0, max: 60_000, color: COLORS.emerald },
    { label: '1–5 min', min: 60_000, max: 300_000, color: COLORS.sky },
    { label: '5–15 min', min: 300_000, max: 900_000, color: COLORS.amber },
    { label: '15–60 min', min: 900_000, max: 3_600_000, color: COLORS.violet },
    { label: '> 60 min', min: 3_600_000, max: Infinity, color: COLORS.rose },
  ]

  const counts = buckets.map((b) => ({
    label: b.label,
    count: sessions.filter((s) => {
      const d = s.duration_ms ??
        (s.ended_at
          ? new Date(s.ended_at).getTime() - new Date(s.started_at).getTime()
          : Date.now() - new Date(s.started_at).getTime())
      return d >= b.min && d < b.max
    }).length,
    color: b.color,
  }))

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={counts} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" horizontal={false} />
        <XAxis
          type="number"
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          width={64}
        />
        <Tooltip
          formatter={(value: number) => [value.toLocaleString(), 'Sessions']}
          contentStyle={tooltipStyle}
          labelStyle={{ color: '#18181b', fontWeight: 500, marginBottom: 4 }}
        />
        <Bar dataKey="count" name="Sessions" radius={[0, 3, 3, 0]}>
          {counts.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ─── Session Health (Issues vs Clean) ───

interface HealthChartProps {
  sessions: { issue_count: number | null }[]
}

export function HealthChart({ sessions }: HealthChartProps) {
  const withIssues = sessions.filter((s) => (s.issue_count ?? 0) > 0).length
  const clean = sessions.length - withIssues

  const data = [
    { name: 'Clean', value: clean, color: COLORS.emerald },
    { name: 'With Issues', value: withIssues, color: COLORS.rose },
  ]

  return (
    <ResponsiveContainer width="100%" height={160}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={40}
          outerRadius={60}
          paddingAngle={3}
          dataKey="value"
          stroke="none"
        >
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip
          formatter={(value: number, name: string) => [value.toLocaleString(), name]}
          contentStyle={tooltipStyle}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

export function HealthLegend({ sessions }: HealthChartProps) {
  const withIssues = sessions.filter((s) => (s.issue_count ?? 0) > 0).length
  const clean = sessions.length - withIssues

  const items = [
    { label: 'Clean', value: clean, color: COLORS.emerald },
    { label: 'With Issues', value: withIssues, color: COLORS.rose },
  ]

  return (
    <div className="flex items-center justify-center gap-4 mt-1">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
          <span className="text-xs text-zinc-600">
            {item.label} ({item.value})
          </span>
        </div>
      ))}
    </div>
  )
}

// ─── Cost per Session over time ───

interface CostPerSessionProps {
  sessions: { started_at: string; total_cost: number | null }[]
}

export function CostPerSessionChart({ sessions }: CostPerSessionProps) {
  const data = sessions
    .filter((s) => s.started_at && (s.total_cost ?? 0) > 0)
    .map((s) => ({
      date: s.started_at.split('T')[0],
      cost: s.total_cost ?? 0,
    }))
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-30)

  if (data.length === 0) {
    return (
      <div className="h-[160px] flex items-center justify-center text-zinc-400 text-sm">
        No cost data to display
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#71717a' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${v.toFixed(2)}`}
          width={44}
        />
        <Tooltip
          formatter={(value: number) => [`$${value.toFixed(4)}`, 'Cost']}
          contentStyle={tooltipStyle}
          labelStyle={{ color: '#18181b', fontWeight: 500, marginBottom: 4 }}
        />
        <Bar dataKey="cost" name="Cost per Session" fill={COLORS.amber} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
