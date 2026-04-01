import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { EvaluationPoint } from '../api/types'

interface ScoreChartProps {
  data: EvaluationPoint[]
}

const LINE_COLOURS = [
  '#6366f1',
  '#06b6d4',
  '#22c55e',
  '#f59e0b',
  '#ec4899',
  '#8b5cf6',
  '#10b981',
  '#f97316',
  '#0ea5e9',
  '#84cc16',
]

export default function ScoreChart({ data }: ScoreChartProps) {
  // Group by asset_name
  const assetNames = [...new Set(data.map((d) => d.asset_name))].slice(0, 10)

  // Build chart data: one entry per unique timestamp
  const byDate = new Map<string, Record<string, number>>()
  for (const point of data) {
    const dateKey = point.evaluated_at.slice(0, 10)
    const row = byDate.get(dateKey) ?? {}
    row[point.asset_name] = point.quality_score
    byDate.set(dateKey, row)
  }

  const chartData = [...byDate.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, scores]) => ({ date, ...scores }))

  if (chartData.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>
        No evaluation data available
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="date"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          axisLine={{ stroke: 'var(--border)' }}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          axisLine={{ stroke: 'var(--border)' }}
          tickFormatter={(v: number) => `${v}%`}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            color: 'var(--text-primary)',
            fontSize: '12px',
          }}
          formatter={(value: number) => [`${value.toFixed(1)}%`]}
        />
        <Legend wrapperStyle={{ fontSize: '12px', color: 'var(--text-secondary)' }} />
        {assetNames.map((name, i) => (
          <Line
            key={name}
            type="monotone"
            dataKey={name}
            stroke={LINE_COLOURS[i % LINE_COLOURS.length]}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
