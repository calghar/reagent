import { useState, useMemo, useEffect, Fragment } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import {
  Search,
  TrendingUp,
  TrendingDown,
  Minus,
  ChevronDown,
  ChevronRight,
  BarChart3,
  CheckSquare,
  Square,
} from 'lucide-react'
import { useEvaluations } from '../hooks/useEvaluations'
import { useAssets } from '../hooks/useAssets'
import type { EvaluationPoint } from '../api/types'
import { scoreToGrade, scoreColour } from '../api/types'
import GradeBadge from '../components/GradeBadge'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import { EmptyState } from '../components/EmptyState'

// ── Constants ───────────────────────────────────────────────────────────────

const ASSET_TYPES = [
  'All',
  'agent',
  'skill',
  'hook',
  'command',
  'claude_md',
  'settings',
] as const
const MAX_CHART_LINES = 15
const DEBOUNCE_MS = 300

/** Cyberpunk-friendly hues distributed around the colour wheel. */
const PROJECT_HUES = [190, 330, 145, 45, 270, 20, 210, 90, 160, 300]

// ── Types ───────────────────────────────────────────────────────────────────

type SortField = 'name' | 'type' | 'score' | 'trend' | 'date'
type SortDir = 'asc' | 'desc'
type Trend = 'up' | 'down' | 'flat'

interface AssetAgg {
  key: string
  assetName: string
  assetType: string
  repoPath: string
  latestScore: number
  previousScore: number | null
  lastEvaluated: string
  evalCount: number
  trend: Trend
}

interface CyberTooltipPayloadEntry {
  name?: string
  value?: number
  color?: string
  dataKey?: string | number
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function repoDisplayName(repoPath: string): string {
  if (!repoPath) return 'Unknown'
  return repoPath.split('/').pop() || repoPath
}

function generateAssetColor(repoIdx: number, assetIdx: number): string {
  const hue = PROJECT_HUES[repoIdx % PROJECT_HUES.length]
  const lightness = 58 + (assetIdx % 4) * 8
  const saturation = 88 - (assetIdx % 3) * 14
  return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}

function trendSortValue(t: Trend): number {
  if (t === 'up') return 1
  if (t === 'down') return -1
  return 0
}

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--grade-a)'
  if (score >= 60) return 'var(--grade-c)'
  return 'var(--grade-f)'
}

function formatTypeLabel(t: string): string {
  return t === 'claude_md' ? 'CLAUDE.md' : t
}

// ── Custom Tooltip ──────────────────────────────────────────────────────────

function CyberTooltip(props: {
  active?: boolean
  payload?: CyberTooltipPayloadEntry[]
  label?: string
}) {
  const { active, payload, label } = props
  if (!active || !payload?.length) return null
  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--accent)',
        borderRadius: '6px',
        padding: '0.75rem',
        boxShadow: 'var(--glow-primary)',
        maxWidth: 320,
      }}
    >
      <div
        style={{
          color: 'var(--text-secondary)',
          fontSize: '0.75rem',
          marginBottom: '0.5rem',
          fontWeight: 600,
        }}
      >
        {label}
      </div>
      {payload
        .filter((e) => e.value != null)
        .map((entry) => (
          <div
            key={entry.name}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '0.8125rem',
              padding: '0.125rem 0',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: entry.color,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                color: 'var(--text-secondary)',
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {entry.name}
            </span>
            <span
              className="data-value"
              style={{ color: entry.color, fontWeight: 600 }}
            >
              {typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}
            </span>
          </div>
        ))}
    </div>
  )
}

// ── Component ───────────────────────────────────────────────────────────────

export default function EvalTrends() {
  // ── State ───────────────────────────────────────────────────────────────
  const [repoFilter, setRepoFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState<string>('All')
  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(new Set())
  const [hiddenLines, setHiddenLines] = useState<Set<string>>(new Set())
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [sortField, setSortField] = useState<SortField>('score')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const navigate = useNavigate()

  // ── Debounced search ────────────────────────────────────────────────────
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput])

  // ── Data hooks ──────────────────────────────────────────────────────────
  const { data: rawEvalData, isLoading, error } = useEvaluations(1000)
  const { data: assets } = useAssets()

  // Cast to concrete array (the hook generic sometimes widens the type)
  const evalData: EvaluationPoint[] =
    (rawEvalData as EvaluationPoint[] | undefined) ?? []
  const hasData = evalData.length > 0

  // ── Asset path lookup (for table click-through to detail) ───────────────
  const assetPathLookup = useMemo(() => {
    if (!assets) return new Map<string, string>()
    const map = new Map<string, string>()
    for (const a of assets) {
      map.set(`${a.repo_path}::${a.asset_name}`, a.asset_path)
    }
    return map
  }, [assets])

  // ── Unique repos from evaluation data (no cross-ref needed) ─────────────
  const repos: string[] = useMemo(() => {
    if (evalData.length === 0) return []
    const set = new Set(evalData.map((e) => e.repo_path))
    return [...set].filter(Boolean).sort()
  }, [evalData])

  // ── Filtered evaluations (AND logic across all filters) ─────────────────
  const filteredEvals: EvaluationPoint[] = useMemo(() => {
    if (evalData.length === 0) return []
    let result: EvaluationPoint[] = evalData
    if (repoFilter !== 'all') {
      result = result.filter((e) => e.repo_path === repoFilter)
    }
    if (typeFilter !== 'All') {
      result = result.filter((e) => e.asset_type === typeFilter)
    }
    if (debouncedSearch) {
      const term = debouncedSearch.toLowerCase()
      result = result.filter((e) => e.asset_name.toLowerCase().includes(term))
    }
    return result
  }, [evalData, repoFilter, typeFilter, debouncedSearch])

  // ── Per-asset aggregation from filtered evals ───────────────────────────
  const assetAggs = useMemo(() => {
    const groups = new Map<string, EvaluationPoint[]>()
    for (const e of filteredEvals) {
      const key = `${e.repo_path}::${e.asset_name}`
      const arr = groups.get(key)
      if (arr) arr.push(e)
      else groups.set(key, [e])
    }

    const result: AssetAgg[] = []
    for (const [key, points] of groups) {
      const sorted = [...points].sort((a, b) =>
        a.evaluated_at.localeCompare(b.evaluated_at)
      )
      const latest = sorted[sorted.length - 1]
      const prev = sorted.length >= 2 ? sorted[sorted.length - 2] : null

      let trend: Trend = 'flat'
      if (prev) {
        const diff = latest.quality_score - prev.quality_score
        if (diff > 1) trend = 'up'
        else if (diff < -1) trend = 'down'
      }

      result.push({
        key,
        assetName: latest.asset_name,
        assetType: latest.asset_type,
        repoPath: latest.repo_path,
        latestScore: latest.quality_score,
        previousScore: prev ? prev.quality_score : null,
        lastEvaluated: latest.evaluated_at,
        evalCount: sorted.length,
        trend,
      })
    }
    return result
  }, [filteredEvals])

  // ── Summary stats ───────────────────────────────────────────────────────
  const summary = useMemo(() => {
    const total = assetAggs.length
    if (total === 0)
      return { total: 0, avgScore: 0, improving: 0, declining: 0, stable: 0 }
    const avgScore = assetAggs.reduce((s, a) => s + a.latestScore, 0) / total
    const improving = assetAggs.filter((a) => a.trend === 'up').length
    const declining = assetAggs.filter((a) => a.trend === 'down').length
    const stable = assetAggs.filter((a) => a.trend === 'flat').length
    return { total, avgScore, improving, declining, stable }
  }, [assetAggs])

  // ── Colour map: project-aware palette ───────────────────────────────────
  const colorMap = useMemo(() => {
    const map = new Map<string, string>()
    const repoIndex = new Map<string, number>()
    const repoCounter = new Map<string, number>()
    for (const repo of repos) {
      repoIndex.set(repo, repoIndex.size)
      repoCounter.set(repo, 0)
    }
    for (const a of assetAggs) {
      const ri = repoIndex.get(a.repoPath) ?? 0
      const ai = repoCounter.get(a.repoPath) ?? 0
      map.set(a.key, generateAssetColor(ri, ai))
      repoCounter.set(a.repoPath, ai + 1)
    }
    return map
  }, [assetAggs, repos])

  // ── Display name map (disambiguate same name across repos) ──────────────
  const nameMap = useMemo(() => {
    const map = new Map<string, string>()
    const nameCounts = new Map<string, number>()
    for (const a of assetAggs) {
      nameCounts.set(a.assetName, (nameCounts.get(a.assetName) ?? 0) + 1)
    }
    for (const a of assetAggs) {
      const dup = (nameCounts.get(a.assetName) ?? 0) > 1
      map.set(
        a.key,
        dup ? `${a.assetName} (${repoDisplayName(a.repoPath)})` : a.assetName
      )
    }
    return map
  }, [assetAggs])

  // ── Group assets by repo for selection panel + table ────────────────────
  const groupedByRepo = useMemo(() => {
    const groups = new Map<string, AssetAgg[]>()
    for (const a of assetAggs) {
      const arr = groups.get(a.repoPath) ?? []
      arr.push(a)
      groups.set(a.repoPath, arr)
    }
    return groups
  }, [assetAggs])

  // ── Sorted groups for table ─────────────────────────────────────────────
  const sortedGrouped = useMemo(() => {
    const sorted = new Map<string, AssetAgg[]>()
    for (const [repo, items] of groupedByRepo) {
      const s = [...items].sort((a, b) => {
        let cmp = 0
        switch (sortField) {
          case 'name':
            cmp = a.assetName.localeCompare(b.assetName)
            break
          case 'type':
            cmp = a.assetType.localeCompare(b.assetType)
            break
          case 'score':
            cmp = a.latestScore - b.latestScore
            break
          case 'trend':
            cmp = trendSortValue(a.trend) - trendSortValue(b.trend)
            break
          case 'date':
            cmp = a.lastEvaluated.localeCompare(b.lastEvaluated)
            break
        }
        return sortDir === 'desc' ? -cmp : cmp
      })
      sorted.set(repo, s)
    }
    return sorted
  }, [groupedByRepo, sortField, sortDir])

  // ── Chart keys + data ───────────────────────────────────────────────────
  const chartKeys = useMemo(() => {
    const validKeys = new Set(assetAggs.map((a) => a.key))
    return [...selectedAssets].filter((k) => validKeys.has(k)).slice(0, MAX_CHART_LINES)
  }, [selectedAssets, assetAggs])

  const chartData = useMemo(() => {
    if (chartKeys.length === 0) return []
    const chartKeySet = new Set(chartKeys)
    const byTimestamp = new Map<string, Record<string, number | string>>()

    for (const point of filteredEvals) {
      const key = `${point.repo_path}::${point.asset_name}`
      if (!chartKeySet.has(key)) continue
      // Use full timestamp so multiple evaluations per day are distinct
      const ts = point.evaluated_at
      const row: Record<string, number | string> = byTimestamp.get(ts) ?? {
        date: ts,
      }
      row[key] = point.quality_score
      byTimestamp.set(ts, row)
    }

    return [...byTimestamp.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, row]) => row)
  }, [filteredEvals, chartKeys])

  // ── Event handlers ──────────────────────────────────────────────────────

  function toggleAsset(key: string) {
    setSelectedAssets((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function selectAllForRepo(repo: string) {
    setSelectedAssets((prev) => {
      const next = new Set(prev)
      for (const a of assetAggs) {
        if (a.repoPath === repo) next.add(a.key)
      }
      return next
    })
  }

  function selectNoneForRepo(repo: string) {
    setSelectedAssets((prev) => {
      const next = new Set(prev)
      for (const a of assetAggs) {
        if (a.repoPath === repo) next.delete(a.key)
      }
      return next
    })
  }

  function toggleGroup(repo: string) {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(repo)) next.delete(repo)
      else next.add(repo)
      return next
    })
  }

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  function sortIndicator(field: SortField): string {
    if (sortField !== field) return ''
    return sortDir === 'asc' ? ' ↑' : ' ↓'
  }

  function handleRowClick(asset: AssetAgg) {
    const assetPath = assetPathLookup.get(asset.key)
    if (assetPath) {
      navigate(`/assets/detail/${encodeURIComponent(assetPath)}`)
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="animate-fade-in">
      {/* ── Page Header ──────────────────────────────────────────────── */}
      <div className="page-header">
        <h1 className="page-title">Eval Trends</h1>
        <p className="page-subtitle">
          Quality score history and trend analysis across all projects
        </p>
      </div>

      <div className="page-banner">
        Track how asset quality evolves over time. Each data point represents an
        evaluation run via <code>reagent evaluate</code>. Select assets below to compare
        their score trajectories. Run <code>reagent evaluate --repo .</code> regularly
        to build meaningful trend data.
      </div>

      {/* ── Loading / Error / Empty ──────────────────────────────────── */}
      {isLoading && <LoadingSpinner />}
      {error && (
        <ErrorMessage
          error={error instanceof Error ? error : new Error(String(error))}
        />
      )}
      {!isLoading && !error && !hasData && (
        <EmptyState
          icon={<BarChart3 size={40} />}
          title="No evaluation data"
          description='Run "reagent evaluate --repo ." to generate trend data for your assets.'
        />
      )}

      {!isLoading && !error && hasData && (
        <>
          {/* ── Filter Bar ─────────────────────────────────────────────── */}
          <div className="filter-bar">
            <select
              value={repoFilter}
              onChange={(e) => setRepoFilter(e.target.value)}
              className="filter-select"
              aria-label="Filter by repository"
            >
              <option value="all">All projects</option>
              {repos.map((r) => (
                <option key={r} value={r}>
                  {repoDisplayName(r)}
                </option>
              ))}
            </select>

            <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
              {ASSET_TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className={`filter-chip${typeFilter === t ? 'active' : ''}`}
                >
                  {formatTypeLabel(t)}
                </button>
              ))}
            </div>

            <div
              style={{ position: 'relative', display: 'flex', alignItems: 'center' }}
            >
              <Search
                size={14}
                style={{
                  position: 'absolute',
                  left: '0.625rem',
                  color: 'var(--text-muted)',
                  pointerEvents: 'none',
                }}
              />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search assets…"
                className="input"
                style={{ paddingLeft: '2rem', minWidth: 200 }}
                aria-label="Search assets by name"
              />
            </div>
          </div>

          {/* ── Summary Cards ──────────────────────────────────────────── */}
          <div className="summary-cards-row">
            <div className="card stagger-1 animate-stagger-in">
              <div
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-secondary)',
                  marginBottom: '0.25rem',
                }}
              >
                Assets Evaluated
              </div>
              <div
                className="data-value"
                style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent)' }}
              >
                {summary.total}
              </div>
            </div>

            <div className="card stagger-2 animate-stagger-in">
              <div
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-secondary)',
                  marginBottom: '0.25rem',
                }}
              >
                Average Score
              </div>
              <div
                className="data-value"
                style={{
                  fontSize: '1.5rem',
                  fontWeight: 700,
                  color: scoreColor(summary.avgScore),
                }}
              >
                {summary.avgScore.toFixed(1)}
              </div>
            </div>

            <div className="card stagger-3 animate-stagger-in">
              <div
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-secondary)',
                  marginBottom: '0.25rem',
                }}
              >
                <TrendingUp
                  size={12}
                  style={{ verticalAlign: 'middle', marginRight: '0.25rem' }}
                />
                Improving
              </div>
              <div
                className="data-value"
                style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--grade-a)' }}
              >
                {summary.improving}
              </div>
            </div>

            <div className="card stagger-4 animate-stagger-in">
              <div
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-secondary)',
                  marginBottom: '0.25rem',
                }}
              >
                <TrendingDown
                  size={12}
                  style={{ verticalAlign: 'middle', marginRight: '0.25rem' }}
                />
                Declining
              </div>
              <div
                className="data-value"
                style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--grade-f)' }}
              >
                {summary.declining}
              </div>
            </div>

            <div className="card stagger-5 animate-stagger-in">
              <div
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-secondary)',
                  marginBottom: '0.25rem',
                }}
              >
                <Minus
                  size={12}
                  style={{ verticalAlign: 'middle', marginRight: '0.25rem' }}
                />
                Stable
              </div>
              <div
                className="data-value"
                style={{
                  fontSize: '1.5rem',
                  fontWeight: 700,
                  color: 'var(--text-secondary)',
                }}
              >
                {summary.stable}
              </div>
            </div>
          </div>

          {/* ── Chart Section ──────────────────────────────────────────── */}
          <div
            className="card stagger-6 animate-stagger-in"
            style={{ marginBottom: '1.5rem', padding: 0 }}
          >
            {/* Chart header */}
            <div style={{ padding: '1.25rem 1.25rem 0' }}>
              <h2
                style={{
                  fontSize: '0.9375rem',
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  margin: 0,
                }}
              >
                Quality Score Trends
              </h2>
              <p
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-muted)',
                  margin: '0.25rem 0 0',
                }}
              >
                {selectedAssets.size === 0
                  ? 'Select assets from the panel to chart their scores'
                  : `${chartKeys.length} asset${chartKeys.length !== 1 ? 's' : ''} charted`}
                {selectedAssets.size > MAX_CHART_LINES && (
                  <span style={{ color: 'var(--grade-c)', marginLeft: '0.5rem' }}>
                    (max {MAX_CHART_LINES} — showing first {MAX_CHART_LINES} of{' '}
                    {selectedAssets.size} selected)
                  </span>
                )}
              </p>
            </div>

            {/* Two-column: selection panel + chart */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '240px 1fr',
                gap: 0,
                minHeight: 400,
              }}
            >
              {/* Asset selection panel */}
              <div
                style={{
                  borderRight: '1px solid var(--border)',
                  padding: '0.75rem',
                  overflowY: 'auto',
                  maxHeight: 440,
                  fontSize: '0.8125rem',
                }}
              >
                {[...groupedByRepo.entries()].map(([repo, items]) => {
                  const selectedCount = items.filter((a) =>
                    selectedAssets.has(a.key)
                  ).length
                  return (
                    <div key={repo} style={{ marginBottom: '0.75rem' }}>
                      {/* Project heading */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          marginBottom: '0.25rem',
                        }}
                      >
                        <span
                          style={{
                            fontWeight: 600,
                            color: 'var(--text-primary)',
                            fontSize: '0.75rem',
                            textTransform: 'uppercase',
                            letterSpacing: '0.05em',
                          }}
                        >
                          {repoDisplayName(repo)}
                          <span
                            style={{
                              color: 'var(--text-muted)',
                              fontWeight: 400,
                              marginLeft: '0.375rem',
                            }}
                          >
                            {selectedCount}/{items.length}
                          </span>
                        </span>
                      </div>

                      {/* Select All / None */}
                      <div
                        style={{
                          display: 'flex',
                          gap: '0.375rem',
                          marginBottom: '0.375rem',
                        }}
                      >
                        <button
                          className="btn btn-ghost"
                          style={{
                            padding: '0.125rem 0.5rem',
                            fontSize: '0.6875rem',
                          }}
                          onClick={() => selectAllForRepo(repo)}
                        >
                          All
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{
                            padding: '0.125rem 0.5rem',
                            fontSize: '0.6875rem',
                          }}
                          onClick={() => selectNoneForRepo(repo)}
                        >
                          None
                        </button>
                      </div>

                      {/* Asset checkboxes */}
                      {items.map((a) => {
                        const checked = selectedAssets.has(a.key)
                        return (
                          <button
                            key={a.key}
                            onClick={() => toggleAsset(a.key)}
                            aria-pressed={checked}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.375rem',
                              padding: '0.1875rem 0.25rem',
                              width: '100%',
                              border: 'none',
                              background: 'transparent',
                              cursor: 'pointer',
                              color: checked
                                ? 'var(--text-primary)'
                                : 'var(--text-muted)',
                              transition: 'color 0.15s',
                              textAlign: 'left',
                              borderRadius: '4px',
                              fontSize: '0.8125rem',
                            }}
                          >
                            {checked ? (
                              <CheckSquare
                                size={14}
                                style={{
                                  color: colorMap.get(a.key),
                                  flexShrink: 0,
                                }}
                              />
                            ) : (
                              <Square size={14} style={{ flexShrink: 0 }} />
                            )}
                            <span
                              style={{
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                flex: 1,
                              }}
                            >
                              {a.assetName}
                            </span>
                            <span
                              className="data-value"
                              style={{
                                fontSize: '0.6875rem',
                                color: scoreColor(a.latestScore),
                                flexShrink: 0,
                              }}
                            >
                              {a.latestScore.toFixed(0)}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  )
                })}

                {assetAggs.length === 0 && (
                  <div
                    style={{
                      color: 'var(--text-muted)',
                      padding: '1rem',
                      textAlign: 'center',
                    }}
                  >
                    No matching assets
                  </div>
                )}
              </div>

              {/* Chart area */}
              <div style={{ padding: '1rem 1rem 0.5rem 0' }}>
                {chartKeys.length === 0 ? (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      height: '100%',
                      color: 'var(--text-muted)',
                      gap: '0.75rem',
                    }}
                  >
                    <BarChart3 size={36} />
                    <span style={{ fontSize: '0.875rem' }}>
                      Select assets from the panel to visualize score trends
                    </span>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={380}>
                    <LineChart
                      data={chartData}
                      margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                        axisLine={{ stroke: 'var(--border)' }}
                        tickLine={{ stroke: 'var(--border)' }}
                        tickFormatter={(v: string) => {
                          const d = new Date(v)
                          if (isNaN(d.getTime())) return v.slice(0, 10)
                          return d.toLocaleString(undefined, {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        }}
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                        axisLine={{ stroke: 'var(--border)' }}
                        tickLine={{ stroke: 'var(--border)' }}
                        tickFormatter={(v: number) => `${v}`}
                      />
                      <Tooltip content={<CyberTooltip />} />
                      <Legend
                        wrapperStyle={{
                          fontSize: '0.6875rem',
                          paddingTop: '0.5rem',
                        }}
                        onClick={(data) => {
                          const dk =
                            typeof data.dataKey === 'string'
                              ? data.dataKey
                              : typeof data.dataKey === 'number'
                                ? String(data.dataKey)
                                : ''
                          if (!dk) return
                          setHiddenLines((prev) => {
                            const next = new Set(prev)
                            if (next.has(dk)) next.delete(dk)
                            else next.add(dk)
                            return next
                          })
                        }}
                        formatter={(value, entry) => {
                          const dk =
                            typeof entry.dataKey === 'string'
                              ? entry.dataKey
                              : typeof entry.dataKey === 'number'
                                ? String(entry.dataKey)
                                : ''
                          const isHidden = hiddenLines.has(dk)
                          return (
                            <span
                              style={{
                                color: isHidden
                                  ? 'var(--text-muted)'
                                  : (entry.color ?? 'var(--text-primary)'),
                                textDecoration: isHidden ? 'line-through' : 'none',
                                cursor: 'pointer',
                              }}
                            >
                              {String(value)}
                            </span>
                          )
                        }}
                      />
                      {chartKeys.map((key) => {
                        const isHidden = hiddenLines.has(key)
                        return (
                          <Line
                            key={key}
                            type="monotone"
                            dataKey={key}
                            name={nameMap.get(key) ?? key}
                            stroke={colorMap.get(key) ?? '#888'}
                            strokeWidth={isHidden ? 0 : 2}
                            dot={isHidden ? false : { r: 2 }}
                            activeDot={isHidden ? { r: 0 } : { r: 4, strokeWidth: 2 }}
                            connectNulls
                            animationDuration={600}
                          />
                        )
                      })}
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>

          {/* ── Grouped Table ──────────────────────────────────────────── */}
          {assetAggs.length > 0 && (
            <div className="card stagger-7 animate-stagger-in" style={{ padding: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 32 }} />
                    <th className="sortable" onClick={() => handleSort('name')}>
                      Asset Name{sortIndicator('name')}
                    </th>
                    <th className="sortable" onClick={() => handleSort('type')}>
                      Type{sortIndicator('type')}
                    </th>
                    <th className="sortable" onClick={() => handleSort('score')}>
                      Score{sortIndicator('score')}
                    </th>
                    <th>Grade</th>
                    <th className="sortable" onClick={() => handleSort('trend')}>
                      Trend{sortIndicator('trend')}
                    </th>
                    <th className="sortable" onClick={() => handleSort('date')}>
                      Last Evaluated{sortIndicator('date')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[...sortedGrouped.entries()].map(([repo, items]) => {
                    const isCollapsed = collapsedGroups.has(repo)
                    const repoAvg =
                      items.length > 0
                        ? items.reduce((s, a) => s + a.latestScore, 0) / items.length
                        : 0

                    return (
                      <Fragment key={repo}>
                        {/* Group header row */}
                        <tr
                          onClick={() => toggleGroup(repo)}
                          style={{
                            cursor: 'pointer',
                            background: 'var(--surface-2)',
                          }}
                        >
                          <td
                            style={{
                              padding: '0.625rem 0.75rem',
                              width: 32,
                            }}
                          >
                            {isCollapsed ? (
                              <ChevronRight
                                size={14}
                                style={{ color: 'var(--text-muted)' }}
                              />
                            ) : (
                              <ChevronDown
                                size={14}
                                style={{ color: 'var(--accent)' }}
                              />
                            )}
                          </td>
                          <td
                            colSpan={4}
                            style={{
                              fontWeight: 600,
                              color: 'var(--text-primary)',
                              fontSize: '0.8125rem',
                              letterSpacing: '0.03em',
                            }}
                          >
                            {repoDisplayName(repo)}
                            <span
                              style={{
                                color: 'var(--text-muted)',
                                fontWeight: 400,
                                marginLeft: '0.625rem',
                                fontSize: '0.75rem',
                              }}
                            >
                              {items.length} asset
                              {items.length !== 1 ? 's' : ''}
                            </span>
                          </td>
                          <td style={{ fontWeight: 600, fontSize: '0.8125rem' }}>
                            <span
                              className="data-value"
                              style={{ color: scoreColor(repoAvg) }}
                            >
                              avg {repoAvg.toFixed(1)}
                            </span>
                          </td>
                          <td />
                        </tr>

                        {/* Individual asset rows */}
                        {!isCollapsed &&
                          items.map((asset, idx) => (
                            <tr
                              key={asset.key}
                              className={`animate-stagger-in stagger-${Math.min(idx + 1, 8)}`}
                              style={{
                                cursor: assetPathLookup.has(asset.key)
                                  ? 'pointer'
                                  : 'default',
                              }}
                              onClick={() => handleRowClick(asset)}
                            >
                              <td />
                              <td style={{ fontWeight: 500 }}>{asset.assetName}</td>
                              <td>
                                <span
                                  className="filter-chip"
                                  style={{ cursor: 'inherit' }}
                                >
                                  {formatTypeLabel(asset.assetType)}
                                </span>
                              </td>
                              <td>
                                <span
                                  className={`data-value ${scoreColour(asset.latestScore)}`}
                                  style={{ fontWeight: 600 }}
                                >
                                  {asset.latestScore.toFixed(1)}
                                </span>
                              </td>
                              <td>
                                <GradeBadge grade={scoreToGrade(asset.latestScore)} />
                              </td>
                              <td>
                                {asset.trend === 'up' && (
                                  <TrendingUp size={14} className="trend-up" />
                                )}
                                {asset.trend === 'down' && (
                                  <TrendingDown size={14} className="trend-down" />
                                )}
                                {asset.trend === 'flat' && (
                                  <Minus size={14} className="trend-flat" />
                                )}
                              </td>
                              <td
                                style={{
                                  color: 'var(--text-muted)',
                                  fontSize: '0.8125rem',
                                }}
                              >
                                {new Date(asset.lastEvaluated).toLocaleString(
                                  undefined,
                                  {
                                    month: 'short',
                                    day: 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit',
                                  }
                                )}
                              </td>
                            </tr>
                          ))}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
