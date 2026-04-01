import { useState, useMemo } from 'react'
import { Search, ChevronDown, ChevronRight, LayoutGrid } from 'lucide-react'
import { useAssets } from '../hooks/useAssets'
import AssetCard from '../components/AssetCard'
import { EmptyState } from '../components/EmptyState'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'

const ASSET_TYPES = [
  'All',
  'agent',
  'skill',
  'hook',
  'rule',
  'command',
  'settings',
  'claude_md',
]

export default function AssetOverview() {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('All')
  const [sort, setSort] = useState<'score' | 'name' | 'date'>('score')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const { data, isLoading, error } = useAssets(
    typeFilter !== 'All' ? typeFilter : undefined
  )

  const filtered = useMemo(() => {
    if (!data) return []
    const q = search.toLowerCase()
    let result = data.filter(
      (a) =>
        !q ||
        a.asset_name.toLowerCase().includes(q) ||
        a.asset_path.toLowerCase().includes(q) ||
        a.repo_path.toLowerCase().includes(q)
    )
    if (sort === 'score')
      result = [...result].sort((a, b) => b.latest_score - a.latest_score)
    if (sort === 'name')
      result = [...result].sort((a, b) => a.asset_name.localeCompare(b.asset_name))
    if (sort === 'date')
      result = [...result].sort((a, b) =>
        b.last_evaluated.localeCompare(a.last_evaluated)
      )
    return result
  }, [data, search, sort])

  const grouped = useMemo(() => {
    const map = new Map<string, typeof filtered>()
    for (const asset of filtered) {
      const repo = asset.repo_path.split('/').pop() || asset.repo_path
      const list = map.get(repo) || []
      list.push(asset)
      map.set(repo, list)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [filtered])

  const toggleCollapse = (repo: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(repo)) next.delete(repo)
      else next.add(repo)
      return next
    })
  }

  const repoAvgScore = (assets: typeof filtered) => {
    if (assets.length === 0) return 0
    return assets.reduce((sum, a) => sum + a.latest_score, 0) / assets.length
  }

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">Asset Overview</h1>
        <p className="page-subtitle">
          {filtered.length} assets across {grouped.length} repositories
        </p>
      </div>

      <div className="page-banner">
        Reagent assets are the building blocks of your AI agent configuration — agents,
        skills, hooks, commands, rules, and CLAUDE.md files. Quality scores are computed
        from telemetry data including invocation frequency, correction rates, and
        security scans. Run <code>reagent evaluate --repo PATH</code> to refresh scores.
      </div>

      <div
        style={{
          display: 'flex',
          gap: '0.75rem',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <div style={{ position: 'relative', flex: '1', minWidth: '200px' }}>
          <Search
            size={14}
            style={{
              position: 'absolute',
              left: '0.625rem',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--text-muted)',
            }}
          />
          <input
            className="input"
            style={{ width: '100%', paddingLeft: '2rem' }}
            placeholder="Search assets or repos…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
          {ASSET_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              style={{
                padding: '0.3125rem 0.75rem',
                border: `1px solid ${typeFilter === t ? 'var(--accent)' : 'var(--border)'}`,
                borderRadius: '100px',
                background: typeFilter === t ? 'rgba(99,102,241,0.15)' : 'transparent',
                color: typeFilter === t ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer',
                fontSize: '0.8125rem',
                fontWeight: 500,
              }}
            >
              {t === 'claude_md' ? 'CLAUDE.md' : t}
            </button>
          ))}
        </div>

        <select
          className="input"
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
        >
          <option value="score">Sort: Score ↓</option>
          <option value="name">Sort: Name A–Z</option>
          <option value="date">Sort: Last Evaluated</option>
        </select>
      </div>

      {isLoading && <LoadingSpinner />}
      {error && (
        <ErrorMessage
          error={error instanceof Error ? error : new Error(String(error))}
        />
      )}

      {!isLoading && !error && filtered.length === 0 && (
        <EmptyState
          icon={<LayoutGrid size={40} />}
          title="No assets found"
          description='Run "reagent evaluate --repo PATH" to populate your asset inventory.'
        />
      )}

      {!isLoading &&
        !error &&
        grouped.map(([repo, assets]) => {
          const isCollapsed = collapsed.has(repo)
          const avg = repoAvgScore(assets)
          const gradeColor =
            avg >= 80
              ? 'var(--grade-a)'
              : avg >= 60
                ? 'var(--grade-c)'
                : 'var(--grade-f)'

          return (
            <div key={repo} style={{ marginBottom: '1.5rem' }}>
              <button
                onClick={() => toggleCollapse(repo)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  marginBottom: isCollapsed ? 0 : '0.75rem',
                  color: 'var(--text-primary)',
                }}
              >
                {isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                <span style={{ fontWeight: 600, fontSize: '0.9375rem' }}>{repo}</span>
                <span
                  style={{
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                    marginLeft: '0.25rem',
                  }}
                >
                  {assets.length} asset{assets.length !== 1 ? 's' : ''}
                </span>
                <span
                  style={{
                    marginLeft: 'auto',
                    fontSize: '0.8125rem',
                    fontWeight: 600,
                    color: gradeColor,
                  }}
                >
                  avg {avg.toFixed(0)}
                </span>
              </button>

              {!isCollapsed && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                    gap: '0.75rem',
                  }}
                >
                  {assets.map((asset) => (
                    <AssetCard key={asset.asset_path} asset={asset} />
                  ))}
                </div>
              )}
            </div>
          )
        })}
    </div>
  )
}
