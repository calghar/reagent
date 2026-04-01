import { useState, useMemo, type ReactNode } from 'react'
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  DollarSign,
  Database,
  Zap,
  AlertTriangle,
  ToggleLeft,
  ToggleRight,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useCosts, useCostEntries, useAllCostEntries } from '../hooks/useCosts'
import { EmptyState } from '../components/EmptyState'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import type { CostEntry } from '../api/types'

// ── Cyberpunk neon palette ──────────────────────────────────────────────────
const NEON_COLORS = ['#00d4ff', '#ff0080', '#00ff88', '#ffcc00', '#a855f7']

const PROVIDER_COLOR_MAP: Record<string, string> = {
  anthropic: '#00d4ff',
  openai: '#ff0080',
  google: '#00ff88',
  azure: '#ffcc00',
  local: '#a855f7',
}

function providerColor(name: string): string {
  const key = name.toLowerCase()
  if (key in PROVIDER_COLOR_MAP) return PROVIDER_COLOR_MAP[key]
  // Hash-based fallback for unknown providers
  let hash = 0
  for (let i = 0; i < key.length; i++) hash = key.charCodeAt(i) + ((hash << 5) - hash)
  return NEON_COLORS[Math.abs(hash) % NEON_COLORS.length]
}

type DateRange = '7d' | '30d' | 'all'

// ── Main component ──────────────────────────────────────────────────────────

export default function CostMonitor() {
  const [page, setPage] = useState(1)
  const [dateRange, setDateRange] = useState<DateRange>('all')
  const [showDemo, setShowDemo] = useState(true)
  const pageSize = 20

  // Reset pagination when the demo filter toggles so users don't land on a stale page
  const toggleDemo = () => {
    setShowDemo((v) => !v)
    setPage(1)
  }

  const { data: summary, isLoading: summaryLoading, error: summaryError } = useCosts()
  const { data: entriesPage, isLoading: entriesLoading } = useCostEntries(
    page,
    pageSize
  )
  const { data: allEntries } = useAllCostEntries()

  // ── Demo data detection ────────────────────────────────────────────────
  const allItems = allEntries?.items ?? []
  const hasDemoData = useMemo(() => allItems.some((e) => e.tier === 'demo'), [allItems])
  const demoCount = useMemo(
    () => allItems.filter((e) => e.tier === 'demo').length,
    [allItems]
  )
  const realCount = useMemo(
    () => allItems.filter((e) => e.tier !== 'demo').length,
    [allItems]
  )

  // ── Derived data (respects demo filter) ────────────────────────────────
  const activeEntries = useMemo(
    () => (showDemo ? allItems : allItems.filter((e) => e.tier !== 'demo')),
    [allItems, showDemo]
  )

  const filteredTotalUsd = useMemo(
    () => activeEntries.reduce((s, e) => s + e.cost_usd, 0),
    [activeEntries]
  )

  const realTotalUsd = useMemo(
    () => allItems.filter((e) => e.tier !== 'demo').reduce((s, e) => s + e.cost_usd, 0),
    [allItems]
  )

  const filteredByProvider = useMemo(() => {
    const map = new Map<string, { total: number; count: number }>()
    for (const e of activeEntries) {
      const cur = map.get(e.provider) ?? { total: 0, count: 0 }
      cur.total += e.cost_usd
      cur.count += 1
      map.set(e.provider, cur)
    }
    return [...map.entries()]
      .sort((a, b) => b[1].total - a[1].total)
      .map(([name, { total, count }]) => ({ name, value: total, count }))
  }, [activeEntries])

  const dailyData = useMemo(() => {
    const byDate = new Map<string, number>()
    for (const e of activeEntries) {
      const d = e.timestamp.slice(0, 10)
      byDate.set(d, (byDate.get(d) ?? 0) + e.cost_usd)
    }
    let entries = [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0]))

    if (dateRange !== 'all') {
      const now = new Date()
      const daysBack = dateRange === '7d' ? 7 : 30
      const cutoff = new Date(now.getTime() - daysBack * 86_400_000)
        .toISOString()
        .slice(0, 10)
      entries = entries.filter(([date]) => date >= cutoff)
    }

    return entries.map(([date, cost]) => ({ date, cost }))
  }, [activeEntries, dateRange])

  // ── Table entries (paginated, with demo filter applied) ────────────────
  const tableItems = useMemo(() => {
    if (!entriesPage) return []
    if (showDemo) return entriesPage.items
    return entriesPage.items.filter((e) => e.tier !== 'demo')
  }, [entriesPage, showDemo])

  const cacheHitRate = summary?.cache_hit_rate ?? 0
  const cachePercent = cacheHitRate * 100

  // ── Loading / error ────────────────────────────────────────────────────
  if (summaryLoading) return <LoadingSpinner />
  if (summaryError) {
    return (
      <ErrorMessage
        error={
          summaryError instanceof Error ? summaryError : new Error(String(summaryError))
        }
      />
    )
  }

  const totalPages = entriesPage ? Math.ceil(entriesPage.total / pageSize) : 0
  const hasData = (summary?.entry_count ?? 0) > 0
  const hasRealData = realCount > 0

  return (
    <div className="animate-fade-in">
      {/* ── Page header ───────────────────────────────────────────────── */}
      <div className="page-header">
        <h1 className="page-title">Cost Monitor</h1>
        <p className="page-subtitle">
          Costs tracked from ReAgent LLM operations — asset generation, evaluation, and
          regeneration.
        </p>
      </div>

      <div className="page-banner">
        Monitor LLM API spending across all reagent operations. Costs are tracked
        per-request during asset generation, evaluation, and regeneration. Use{' '}
        <code>reagent cost</code> from the CLI for a quick summary. The tiered provider
        system automatically falls back to cheaper models when possible.
      </div>

      {/* ── Demo data banner ──────────────────────────────────────────── */}
      {hasDemoData && (
        <div className="demo-banner">
          <div className="demo-banner-icon">
            <AlertTriangle size={18} />
          </div>
          <div className="demo-banner-content">
            <strong>
              {demoCount} of {allItems.length} cost entries
            </strong>{' '}
            are from demo seed data (
            <code style={{ fontSize: '0.75rem' }}>scripts/seed_cost_data.py</code>),
            used for dashboard testing. These entries include simulated Anthropic,
            OpenAI, and Google usage.
            {!hasRealData && (
              <span
                style={{
                  display: 'block',
                  marginTop: '0.25rem',
                  color: 'var(--text-muted)',
                }}
              >
                No real cost data yet — run <code>reagent create</code> or{' '}
                <code>reagent evaluate</code> to generate real entries.
              </span>
            )}
          </div>
          <div
            className="demo-banner-toggle"
            onClick={() => toggleDemo()}
            role="switch"
            aria-checked={showDemo}
            aria-label="Show demo data"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                toggleDemo()
              }
            }}
          >
            <span className="demo-banner-toggle-label">Show Demo</span>
            {showDemo ? (
              <ToggleRight size={24} className="demo-toggle-icon active" />
            ) : (
              <ToggleLeft size={24} className="demo-toggle-icon" />
            )}
          </div>
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────────────── */}
      {!hasData ? (
        <EmptyState
          icon={<DollarSign size={40} />}
          title="No cost data yet"
          description="Generate assets with `reagent create` to start tracking costs. Cost entries appear when assets are generated, evaluated, or regenerated using LLM providers."
        />
      ) : activeEntries.length === 0 && !showDemo ? (
        <EmptyState
          icon={<DollarSign size={40} />}
          title="No real cost data yet"
          description="All current entries are demo data. Run `reagent create` or `reagent evaluate --repo .` to generate real LLM cost entries. Toggle 'Show Demo' above to view seed data."
        />
      ) : (
        <>
          {/* ── Date range selector ────────────────────────────────────── */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              marginBottom: '1.5rem',
            }}
          >
            <div className="range-btn-group">
              {(
                [
                  ['7d', 'Last 7 days'],
                  ['30d', 'Last 30 days'],
                  ['all', 'All time'],
                ] as const
              ).map(([val, label]) => (
                <button
                  key={val}
                  className={`range-btn ${dateRange === val ? 'active' : ''}`}
                  onClick={() => setDateRange(val)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* ── Summary cards ──────────────────────────────────────────── */}
          <div className="cost-summary-grid">
            <SummaryCard
              icon={<DollarSign size={16} />}
              label="Total Spend"
              value={`$${filteredTotalUsd.toFixed(4)}`}
              sub={hasDemoData && showDemo ? `Includes demo data` : undefined}
              delay={1}
              mono
            />
            {hasDemoData && (
              <SummaryCard
                icon={<Zap size={16} />}
                label="Real Spend"
                value={`$${realTotalUsd.toFixed(4)}`}
                sub={`${realCount} real entr${realCount === 1 ? 'y' : 'ies'}`}
                delay={2}
                mono
              />
            )}
            <SummaryCard
              icon={<Database size={16} />}
              label="Entry Count"
              value={String(activeEntries.length)}
              sub={hasDemoData ? `${realCount} real · ${demoCount} demo` : undefined}
              delay={hasDemoData ? 3 : 2}
            />
            <SummaryCard
              icon={<Zap size={16} />}
              label="Cache Hit Rate"
              value={`${cachePercent.toFixed(1)}%`}
              delay={hasDemoData ? 4 : 3}
              progressPercent={cachePercent}
            />
          </div>

          {/* ── Charts ─────────────────────────────────────────────────── */}
          <div className="cost-charts-grid">
            {/* Provider pie chart */}
            <div className="card">
              <h3 className="cost-chart-title">Spend by Provider</h3>
              <p className="cost-chart-note">
                Only shows providers used by ReAgent. Does not include external API
                usage.
              </p>
              {filteredByProvider.length === 0 ? (
                <div
                  style={{
                    color: 'var(--text-muted)',
                    textAlign: 'center',
                    padding: '2rem',
                  }}
                >
                  No cost data for current filter
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      data={filteredByProvider}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      innerRadius={45}
                      paddingAngle={2}
                      label={({ name, percent }: { name: string; percent: number }) =>
                        `${name} ${(percent * 100).toFixed(0)}%`
                      }
                      labelLine={false}
                    >
                      {filteredByProvider.map((entry, i) => (
                        <Cell
                          key={entry.name}
                          fill={providerColor(entry.name)}
                          stroke="var(--surface-1)"
                          strokeWidth={2}
                          style={{
                            filter: `drop-shadow(0 0 4px ${NEON_COLORS[i % NEON_COLORS.length]}40)`,
                          }}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<ProviderTooltip />} />
                    <Legend
                      formatter={(value: string) => (
                        <span
                          style={{
                            color: 'var(--text-secondary)',
                            fontSize: '0.75rem',
                          }}
                        >
                          {value}
                        </span>
                      )}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Daily bar chart */}
            <div className="card">
              <h3 className="cost-chart-title">Daily Spend</h3>
              <p className="cost-chart-note">
                {showDemo && hasDemoData
                  ? 'Includes demo entries. Toggle off to see real spend only.'
                  : 'Showing real LLM usage costs by day.'}
              </p>
              {dailyData.length === 0 ? (
                <div
                  style={{
                    color: 'var(--text-muted)',
                    textAlign: 'center',
                    padding: '2rem',
                  }}
                >
                  No daily data for selected range
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart
                    data={dailyData}
                    margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#00d4ff" stopOpacity={0.9} />
                        <stop offset="100%" stopColor="#00d4ff" stopOpacity={0.3} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="var(--border)"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                      axisLine={{ stroke: 'var(--border)' }}
                      tickFormatter={(v: string) => {
                        const parts = v.split('-')
                        return `${parts[1]}/${parts[2]}`
                      }}
                    />
                    <YAxis
                      tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                      axisLine={{ stroke: 'var(--border)' }}
                      tickFormatter={(v: number) => `$${v.toFixed(3)}`}
                      width={60}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'var(--surface-2)',
                        border: '1px solid var(--border)',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        color: 'var(--text-primary)',
                        boxShadow: '0 0 12px rgba(0, 212, 255, 0.15)',
                      }}
                      formatter={(v: number) => [`$${v.toFixed(5)}`, 'Cost']}
                      labelFormatter={(label: string) => {
                        const d = new Date(label + 'T00:00:00')
                        return d.toLocaleDateString('en-US', {
                          weekday: 'short',
                          month: 'short',
                          day: 'numeric',
                        })
                      }}
                    />
                    <Bar
                      dataKey="cost"
                      fill="url(#barGradient)"
                      radius={[3, 3, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* ── Entries table ──────────────────────────────────────────── */}
          <div className="card">
            <h3 className="cost-table-section-title">Cost Entries</h3>

            {entriesLoading ? (
              <LoadingSpinner />
            ) : (
              <>
                <div style={{ overflowX: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Timestamp</th>
                        <th>Provider</th>
                        <th>Model</th>
                        <th>Asset</th>
                        <th style={{ textAlign: 'right' }}>Tokens In</th>
                        <th style={{ textAlign: 'right' }}>Tokens Out</th>
                        <th style={{ textAlign: 'right' }}>Cost</th>
                        <th>Tier</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tableItems.length === 0 ? (
                        <tr>
                          <td
                            colSpan={8}
                            style={{
                              textAlign: 'center',
                              color: 'var(--text-muted)',
                              padding: '2rem',
                            }}
                          >
                            {showDemo
                              ? 'No entries on this page.'
                              : 'No real entries on this page. Toggle "Show Demo" to see all.'}
                          </td>
                        </tr>
                      ) : (
                        tableItems.map((e) => <CostRow key={e.cost_id} entry={e} />)
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div className="cost-pagination">
                  <span>
                    {entriesPage
                      ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, entriesPage.total)} of ${entriesPage.total} entries`
                      : ''}
                  </span>
                  <div className="cost-pagination-btns">
                    <button
                      className="btn btn-ghost"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                      aria-label="Previous page"
                    >
                      <ChevronLeft size={14} />
                      <span>Prev</span>
                    </button>
                    <span
                      className="data-value"
                      style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}
                    >
                      {page} / {totalPages || 1}
                    </span>
                    <button
                      className="btn btn-ghost"
                      onClick={() => setPage((p) => p + 1)}
                      disabled={page >= totalPages}
                      aria-label="Next page"
                    >
                      <span>Next</span>
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface SummaryCardProps {
  icon: ReactNode
  label: string
  value: string
  sub?: string
  delay: number
  mono?: boolean
  progressPercent?: number
}

function SummaryCard({
  icon,
  label,
  value,
  sub,
  delay,
  mono,
  progressPercent,
}: SummaryCardProps) {
  return (
    <div className={`card cost-summary-card animate-stagger-in stagger-${delay}`}>
      <div className="cost-summary-card-icon">{icon}</div>
      <div className="cost-summary-label">{label}</div>
      <div className={`cost-summary-value ${mono ? 'data-value' : ''}`}>{value}</div>
      {sub && <div className="cost-summary-sub">{sub}</div>}
      {progressPercent != null && (
        <div className="cost-progress-bar">
          <div
            className="cost-progress-fill"
            style={{ width: `${Math.min(100, progressPercent)}%` }}
          />
        </div>
      )}
    </div>
  )
}

function CostRow({ entry: e }: { entry: CostEntry }) {
  const isDemo = e.tier === 'demo'
  const color = providerColor(e.provider)
  const ts = e.timestamp.slice(0, 19).replace('T', ' ')

  return (
    <tr style={isDemo ? { opacity: 0.7 } : undefined}>
      <td
        style={{
          color: 'var(--text-secondary)',
          whiteSpace: 'nowrap',
          fontSize: '0.8125rem',
        }}
      >
        {ts}
      </td>
      <td>
        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
          <span
            className="provider-dot"
            style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}60` }}
          />
          {e.provider}
        </span>
      </td>
      <td style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{e.model}</td>
      <td>{e.asset_name || '—'}</td>
      <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
        {e.input_tokens.toLocaleString()}
      </td>
      <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
        {e.output_tokens.toLocaleString()}
      </td>
      <td style={{ textAlign: 'right' }}>
        <span className="data-value">${e.cost_usd.toFixed(5)}</span>
      </td>
      <td>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
          {e.tier}
        </span>
        {isDemo && <span className="badge-demo">DEMO</span>}
      </td>
    </tr>
  )
}

interface TooltipPayloadItem {
  name: string
  value: number
  payload: { name: string; value: number; count: number }
}

function ProviderTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: TooltipPayloadItem[]
}) {
  if (!active || !payload?.length) return null
  const item = payload[0]
  const { name, count } = item.payload
  const total = item.value

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: '6px',
        padding: '0.5rem 0.75rem',
        fontSize: '0.75rem',
        color: 'var(--text-primary)',
        boxShadow: '0 0 12px rgba(0, 212, 255, 0.15)',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{name}</div>
      <div>
        <span className="data-value">${total.toFixed(5)}</span> total
      </div>
      <div style={{ color: 'var(--text-secondary)' }}>
        {count} entr{count === 1 ? 'y' : 'ies'}
      </div>
    </div>
  )
}
