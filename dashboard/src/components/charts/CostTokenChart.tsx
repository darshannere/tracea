import { LineChart, Line, BarChart, Bar, XAxis, YAxis, ResponsiveContainer, CartesianGrid, Tooltip } from 'recharts'

export function CostChart({ data }: { data: { date: string; cost: number }[] }) {
  return (
    <div className="border border-zinc-200 rounded-lg p-4">
      <h3 className="text-sm font-medium text-zinc-700 mb-3">Cost per Day</h3>
      {data.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-zinc-400 text-sm">
          No data to display
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#71717a' }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#71717a' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${v.toFixed(2)}`}
              width={48}
            />
            <Tooltip
              formatter={(value: number) => [`$${value.toFixed(4)}`, 'Cost']}
              contentStyle={{ fontSize: 12, borderRadius: 6, border: '1px solid #e4e4e7' }}
            />
            <Line
              type="monotone"
              dataKey="cost"
              name="Cost (USD)"
              stroke="#6366f1"
              strokeWidth={2}
              dot={{ fill: '#6366f1', r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export function TokenChart({ data }: { data: { date: string; tokens: number }[] }) {
  return (
    <div className="border border-zinc-200 rounded-lg p-4">
      <h3 className="text-sm font-medium text-zinc-700 mb-3">Tokens per Day</h3>
      {data.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-zinc-400 text-sm">
          No data to display
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#71717a' }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#71717a' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              width={48}
            />
            <Tooltip
              formatter={(value: number) => [value.toLocaleString(), 'Tokens']}
              contentStyle={{ fontSize: 12, borderRadius: 6, border: '1px solid #e4e4e7' }}
            />
            <Bar
              dataKey="tokens"
              name="Tokens"
              fill="#6366f1"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
