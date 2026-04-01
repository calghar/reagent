import { useState, useMemo, useCallback, useEffect } from 'react'
import {
  Search,
  BookOpen,
  Layers,
  Shield,
  Terminal,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Zap,
  Brain,
  Filter,
  Download,
  Upload,
  Trash2,
} from 'lucide-react'
import { useInstincts } from '../hooks/useInstincts'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import { EmptyState } from '../components/EmptyState'
import type { InstinctRow } from '../api/types'

// ── Constants ──────────────────────────────────────────────────────────────────

const PAGE_SIZE = 25

type Tab = 'all' | 'category' | 'tier'
type ConfidenceFilter = 'all' | 'medium' | 'high'

const TIER_META: Record<
  string,
  { color: string; glow: string; label: string; icon: typeof Shield }
> = {
  global: {
    color: '#f59e0b',
    glow: 'rgba(245, 158, 11, 0.15)',
    label: 'Global',
    icon: Zap,
  },
  team: {
    color: '#a855f7',
    glow: 'rgba(168, 85, 247, 0.15)',
    label: 'Team',
    icon: Layers,
  },
  workspace: {
    color: '#00d4ff',
    glow: 'rgba(0, 212, 255, 0.15)',
    label: 'Workspace',
    icon: Shield,
  },
}

const CATEGORY_COLORS: string[] = [
  '#00d4ff',
  '#ff0080',
  '#00ff88',
  '#f59e0b',
  '#a855f7',
  '#ef4444',
  '#3b82f6',
  '#14b8a6',
  '#f97316',
  '#ec4899',
]

function categoryColor(cat: string): string {
  let hash = 0
  for (let i = 0; i < cat.length; i++) {
    hash = ((hash << 5) - hash + cat.charCodeAt(i)) | 0
  }
  return CATEGORY_COLORS[Math.abs(hash) % CATEGORY_COLORS.length]
}

function relativeTime(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = now - then
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.floor(months / 12)}y ago`
}

function confidenceColor(c: number): string {
  if (c >= 0.8) return 'var(--grade-a)'
  if (c >= 0.5) return 'var(--grade-c)'
  return 'var(--grade-f)'
}

function successColor(r: number): string {
  if (r >= 0.8) return 'var(--grade-a)'
  if (r >= 0.6) return 'var(--grade-c)'
  return 'var(--grade-f)'
}

// ── Clipboard helper ───────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      })
      .catch(() => {
        /* ignore */
      })
  }, [text])

  return (
    <button
      className="icon-btn"
      onClick={handleCopy}
      aria-label={copied ? 'Copied' : 'Copy command'}
      title={copied ? 'Copied!' : 'Copy to clipboard'}
    >
      {copied ? (
        <Check size={14} style={{ color: 'var(--grade-a)' }} />
      ) : (
        <Copy size={14} />
      )}
    </button>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function TierBadge({ tier }: { tier: string }) {
  const meta = TIER_META[tier]
  if (!meta) {
    return (
      <span
        className="badge"
        style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}
      >
        {tier}
      </span>
    )
  }
  return (
    <span
      className="badge"
      style={{
        color: meta.color,
        background: `${meta.color}18`,
        boxShadow: `0 0 8px ${meta.glow}`,
      }}
    >
      {meta.label}
    </span>
  )
}

function CategoryBadge({ category }: { category: string }) {
  const color = categoryColor(category)
  return (
    <span
      className="badge"
      style={{
        color,
        background: `${color}14`,
        border: `1px solid ${color}30`,
      }}
    >
      {category}
    </span>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = confidenceColor(value)
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        minWidth: '100px',
      }}
    >
      <div className="instinct-progress-track">
        <div
          className="instinct-progress-fill"
          style={{
            width: `${pct}%`,
            background: color,
            boxShadow: `0 0 6px ${color}40`,
          }}
        />
      </div>
      <span
        className="data-value"
        style={{ fontSize: '0.75rem', color, minWidth: '32px' }}
      >
        {pct}%
      </span>
    </div>
  )
}

interface InstinctRowItemProps {
  inst: InstinctRow
  expanded: boolean
  onToggle: () => void
  staggerIndex: number
}

function InstinctRowItem({
  inst,
  expanded,
  onToggle,
  staggerIndex,
}: InstinctRowItemProps) {
  return (
    <>
      <tr
        className="expandable-row animate-stagger-in"
        style={{ animationDelay: `${Math.min(staggerIndex, 10) * 0.03}s` }}
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <td style={{ maxWidth: 0 }}>
          <div
            className={`instinct-content-cell ${expanded ? 'instinct-content-expanded' : ''}`}
          >
            {inst.content}
          </div>
        </td>
        <td>
          <CategoryBadge category={inst.category} />
        </td>
        <td>
          <TierBadge tier={inst.trust_tier} />
        </td>
        <td>
          <ConfidenceBar value={inst.confidence} />
        </td>
        <td>
          <span className="data-value" style={{ color: 'var(--text-primary)' }}>
            {inst.use_count}
          </span>
        </td>
        <td>
          <span
            className="data-value"
            style={{ color: successColor(inst.success_rate) }}
          >
            {Math.round(inst.success_rate * 100)}%
          </span>
        </td>
        <td style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
          {relativeTime(inst.created_at)}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7} style={{ padding: 0 }}>
            <div className="expand-detail instinct-expand-detail">
              <p
                style={{
                  margin: '0 0 0.5rem',
                  color: 'var(--text-primary)',
                  lineHeight: 1.7,
                }}
              >
                {inst.content}
              </p>
              <div
                style={{
                  display: 'flex',
                  gap: '1.5rem',
                  flexWrap: 'wrap',
                  fontSize: '0.8125rem',
                }}
              >
                <span style={{ color: 'var(--text-muted)' }}>
                  ID:{' '}
                  <code style={{ color: 'var(--accent)', fontSize: '0.75rem' }}>
                    {inst.instinct_id}
                  </code>
                </span>
                <span style={{ color: 'var(--text-muted)' }}>
                  Created:{' '}
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {new Date(inst.created_at).toLocaleString()}
                  </span>
                </span>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ── Summary stats ──────────────────────────────────────────────────────────────

interface SummaryStats {
  total: number
  avgConfidence: number
  categories: Map<string, number>
  tiers: Map<string, { count: number; avgConf: number }>
}

function computeStats(data: InstinctRow[]): SummaryStats {
  const categories = new Map<string, number>()
  const tierAcc = new Map<string, { count: number; sum: number }>()
  let confSum = 0

  for (const inst of data) {
    confSum += inst.confidence
    categories.set(inst.category, (categories.get(inst.category) ?? 0) + 1)
    const t = tierAcc.get(inst.trust_tier) ?? { count: 0, sum: 0 }
    t.count++
    t.sum += inst.confidence
    tierAcc.set(inst.trust_tier, t)
  }

  const tiers = new Map<string, { count: number; avgConf: number }>()
  for (const [k, v] of tierAcc) {
    tiers.set(k, { count: v.count, avgConf: v.count > 0 ? v.sum / v.count : 0 })
  }

  return {
    total: data.length,
    avgConfidence: data.length > 0 ? confSum / data.length : 0,
    categories,
    tiers,
  }
}

function SummaryCards({ stats }: { stats: SummaryStats }) {
  const topCategories = [...stats.categories.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)

  return (
    <div
      className="summary-cards-row"
      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}
    >
      <div className="card instinct-stat-card">
        <div
          style={{
            color: 'var(--text-muted)',
            fontSize: '0.6875rem',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          Total Instincts
        </div>
        <div
          className="data-value"
          style={{ fontSize: '1.5rem', color: 'var(--accent)' }}
        >
          {stats.total}
        </div>
      </div>
      <div className="card instinct-stat-card">
        <div
          style={{
            color: 'var(--text-muted)',
            fontSize: '0.6875rem',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          Avg Confidence
        </div>
        <div
          className="data-value"
          style={{ fontSize: '1.5rem', color: confidenceColor(stats.avgConfidence) }}
        >
          {Math.round(stats.avgConfidence * 100)}%
        </div>
      </div>
      {topCategories.map(([cat, count]) => (
        <div className="card instinct-stat-card" key={cat}>
          <div
            style={{
              color: 'var(--text-muted)',
              fontSize: '0.6875rem',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}
          >
            {cat}
          </div>
          <div
            className="data-value"
            style={{ fontSize: '1.5rem', color: categoryColor(cat) }}
          >
            {count}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── CLI Actions Panel ──────────────────────────────────────────────────────────

const CLI_ACTIONS: Array<{
  title: string
  desc: string
  cmd: string
  icon: typeof Terminal
}> = [
  {
    title: 'Extract Instincts',
    desc: 'Learn new patterns from session transcripts',
    cmd: 'reagent instincts extract',
    icon: Download,
  },
  {
    title: 'Prune Stale',
    desc: 'Remove low-confidence or unused instincts',
    cmd: 'reagent instincts prune',
    icon: Trash2,
  },
  {
    title: 'Export',
    desc: 'Export instinct store to JSON file',
    cmd: 'reagent instincts export instincts.json',
    icon: Upload,
  },
  {
    title: 'Import',
    desc: 'Import instincts from a JSON file',
    cmd: 'reagent instincts import <file>',
    icon: Download,
  },
]

function CLIActionsPanel() {
  return (
    <div className="instinct-cli-grid">
      {CLI_ACTIONS.map((action) => {
        const Icon = action.icon
        return (
          <div className="card instinct-cli-card" key={action.title}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '0.375rem',
              }}
            >
              <Icon size={14} style={{ color: 'var(--accent)' }} />
              <span
                style={{
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  color: 'var(--text-primary)',
                }}
              >
                {action.title}
              </span>
            </div>
            <p
              style={{
                margin: '0 0 0.5rem',
                fontSize: '0.75rem',
                color: 'var(--text-muted)',
                lineHeight: 1.5,
              }}
            >
              {action.desc}
            </p>
            <div className="instinct-cli-cmd">
              <Terminal size={12} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <code
                style={{
                  flex: 1,
                  fontSize: '0.75rem',
                  color: 'var(--accent)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {action.cmd}
              </code>
              <CopyButton text={action.cmd} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Pagination ─────────────────────────────────────────────────────────────────

interface PaginationProps {
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
}

function Pagination({ total, page, pageSize, onPageChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const start = Math.min(page * pageSize + 1, total)
  const end = Math.min((page + 1) * pageSize, total)

  if (total <= pageSize) return null

  return (
    <div className="instinct-pagination">
      <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
        Showing{' '}
        <span className="data-value" style={{ color: 'var(--text-secondary)' }}>
          {start}–{end}
        </span>{' '}
        of{' '}
        <span className="data-value" style={{ color: 'var(--text-secondary)' }}>
          {total}
        </span>{' '}
        instincts
      </span>
      <div style={{ display: 'flex', gap: '0.375rem' }}>
        <button
          className="btn btn-ghost"
          style={{ padding: '0.3125rem 0.75rem', fontSize: '0.8125rem' }}
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </button>
        <span
          className="data-value"
          style={{
            padding: '0.3125rem 0.5rem',
            fontSize: '0.8125rem',
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          {page + 1} / {totalPages}
        </span>
        <button
          className="btn btn-ghost"
          style={{ padding: '0.3125rem 0.75rem', fontSize: '0.8125rem' }}
          disabled={page >= totalPages - 1}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  )
}

// ── Collapsible Section ────────────────────────────────────────────────────────

interface CollapsibleSectionProps {
  title: React.ReactNode
  count: number
  avgConfidence: number
  defaultOpen?: boolean
  children: React.ReactNode
}

function CollapsibleSection({
  title,
  count,
  avgConfidence,
  defaultOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="card" style={{ padding: 0, marginBottom: '0.75rem' }}>
      <button
        className="instinct-collapsible-header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{title}</span>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
            fontSize: '0.75rem',
          }}
        >
          <span style={{ color: 'var(--text-muted)' }}>
            <span className="data-value" style={{ color: 'var(--text-secondary)' }}>
              {count}
            </span>{' '}
            instincts
          </span>
          <span style={{ color: 'var(--text-muted)' }}>
            avg conf:{' '}
            <span
              className="data-value"
              style={{ color: confidenceColor(avgConfidence) }}
            >
              {Math.round(avgConfidence * 100)}%
            </span>
          </span>
        </div>
      </button>
      {open && <div style={{ padding: '0' }}>{children}</div>}
    </div>
  )
}

// ── Instinct mini card (for tier/category views) ───────────────────────────────

function InstinctCard({
  inst,
  staggerIndex,
}: {
  inst: InstinctRow
  staggerIndex: number
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div
      className="instinct-mini-card animate-stagger-in"
      style={{ animationDelay: `${Math.min(staggerIndex, 12) * 0.03}s` }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: '0.75rem',
        }}
      >
        <div
          className={`instinct-content-cell ${expanded ? 'instinct-content-expanded' : ''}`}
          onClick={() => setExpanded((v) => !v)}
          style={{ cursor: 'pointer', flex: 1 }}
        >
          {inst.content}
        </div>
        <TierBadge tier={inst.trust_tier} />
      </div>
      <div className="instinct-card-meta">
        <CategoryBadge category={inst.category} />
        <ConfidenceBar value={inst.confidence} />
        <span
          className="data-value"
          style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}
        >
          {inst.use_count} uses
        </span>
        <span
          className="data-value"
          style={{ fontSize: '0.75rem', color: successColor(inst.success_rate) }}
        >
          {Math.round(inst.success_rate * 100)}% success
        </span>
        <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
          {relativeTime(inst.created_at)}
        </span>
      </div>
    </div>
  )
}

// ── Tab: All (paginated table) ─────────────────────────────────────────────────

function AllTab({ instincts }: { instincts: InstinctRow[] }) {
  const [page, setPage] = useState(0)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const paged = useMemo(
    () => instincts.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [instincts, page]
  )

  // Reset page if instincts change
  const maxPage = Math.max(0, Math.ceil(instincts.length / PAGE_SIZE) - 1)
  useEffect(() => {
    if (page > maxPage) setPage(maxPage)
  }, [page, maxPage])

  if (instincts.length === 0) {
    return (
      <EmptyState
        icon={<Brain size={40} />}
        title="No instincts found"
        description="No instincts match your current filters. Try adjusting your search or confidence threshold."
      />
    )
  }

  return (
    <>
      <div className="card" style={{ padding: 0 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '35%' }}>Content</th>
              <th>Category</th>
              <th>Trust Tier</th>
              <th>Confidence</th>
              <th>Uses</th>
              <th>Success</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((inst, i) => (
              <InstinctRowItem
                key={inst.instinct_id}
                inst={inst}
                expanded={expandedId === inst.instinct_id}
                onToggle={() =>
                  setExpandedId(
                    expandedId === inst.instinct_id ? null : inst.instinct_id
                  )
                }
                staggerIndex={i}
              />
            ))}
          </tbody>
        </table>
      </div>
      <Pagination
        total={instincts.length}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />
    </>
  )
}

// ── Tab: By Category ───────────────────────────────────────────────────────────

function CategoryTab({ instincts }: { instincts: InstinctRow[] }) {
  const grouped = useMemo(() => {
    const map = new Map<string, InstinctRow[]>()
    for (const inst of instincts) {
      const list = map.get(inst.category) ?? []
      list.push(inst)
      map.set(inst.category, list)
    }
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length)
  }, [instincts])

  if (grouped.length === 0) {
    return (
      <EmptyState
        icon={<BookOpen size={40} />}
        title="No categories found"
        description="No instincts match your filters."
      />
    )
  }

  return (
    <div>
      {grouped.map(([category, items], gi) => {
        const avgConf = items.reduce((s, i) => s + i.confidence, 0) / items.length
        return (
          <CollapsibleSection
            key={category}
            title={
              <>
                <CategoryBadge category={category} />{' '}
                <span style={{ marginLeft: '0.25rem' }}>{category}</span>
              </>
            }
            count={items.length}
            avgConfidence={avgConf}
            defaultOpen={gi === 0}
          >
            <div className="instinct-card-list">
              {items.map((inst, i) => (
                <InstinctCard key={inst.instinct_id} inst={inst} staggerIndex={i} />
              ))}
            </div>
          </CollapsibleSection>
        )
      })}
    </div>
  )
}

// ── Tab: By Trust Tier ─────────────────────────────────────────────────────────

const TIER_ORDER = ['global', 'team', 'workspace'] as const

function TierTab({ instincts }: { instincts: InstinctRow[] }) {
  const grouped = useMemo(() => {
    const map = new Map<string, InstinctRow[]>()
    for (const inst of instincts) {
      const list = map.get(inst.trust_tier) ?? []
      list.push(inst)
      map.set(inst.trust_tier, list)
    }
    return map
  }, [instincts])

  const tiers = TIER_ORDER.filter((t) => grouped.has(t))
  const otherTiers = [...grouped.keys()].filter(
    (t) => !TIER_ORDER.includes(t as (typeof TIER_ORDER)[number])
  )
  const allTiers = [...tiers, ...otherTiers]

  if (allTiers.length === 0) {
    return (
      <EmptyState
        icon={<Shield size={40} />}
        title="No trust tiers found"
        description="No instincts match your filters."
      />
    )
  }

  return (
    <div>
      {allTiers.map((tier, ti) => {
        const items = grouped.get(tier) ?? []
        const meta = TIER_META[tier]
        const avgConf = items.reduce((s, i) => s + i.confidence, 0) / items.length
        const TierIcon = meta?.icon ?? Shield

        return (
          <CollapsibleSection
            key={tier}
            title={
              <span
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <TierIcon
                  size={16}
                  style={{ color: meta?.color ?? 'var(--text-secondary)' }}
                />
                <span style={{ color: meta?.color ?? 'var(--text-secondary)' }}>
                  {meta?.label ?? tier}
                </span>
              </span>
            }
            count={items.length}
            avgConfidence={avgConf}
            defaultOpen={ti === 0}
          >
            <div className="instinct-card-list">
              {items.map((inst, i) => (
                <InstinctCard key={inst.instinct_id} inst={inst} staggerIndex={i} />
              ))}
            </div>
          </CollapsibleSection>
        )
      })}
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function InstinctStore() {
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<Tab>('all')
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>('all')
  const { data, isLoading, error } = useInstincts()

  const stats = useMemo(() => computeStats(data ?? []), [data])

  const filtered = useMemo(() => {
    if (!data) return []
    let result = data

    // Confidence filter
    if (confidenceFilter === 'high') {
      result = result.filter((i) => i.confidence >= 0.8)
    } else if (confidenceFilter === 'medium') {
      result = result.filter((i) => i.confidence >= 0.5)
    }

    // Search
    const q = search.toLowerCase().trim()
    if (q) {
      result = result.filter(
        (i) =>
          i.content.toLowerCase().includes(q) ||
          i.category.toLowerCase().includes(q) ||
          i.trust_tier.toLowerCase().includes(q)
      )
    }

    return result
  }, [data, search, confidenceFilter])

  const handleConfidenceFilter = useCallback((f: ConfidenceFilter) => {
    setConfidenceFilter(f)
  }, [])

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title">Instinct Store</h1>
        <p className="page-subtitle">Learned patterns that guide asset generation</p>
      </div>

      {/* Banner */}
      <div className="page-banner">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
          <Brain
            size={18}
            style={{ color: 'var(--accent)', flexShrink: 0, marginTop: '1px' }}
          />
          <div>
            <p style={{ margin: '0 0 0.375rem' }}>
              <strong style={{ color: 'var(--text-primary)' }}>Instincts</strong> are
              patterns ReAgent learns from evaluation feedback to improve future asset
              generation. Higher confidence means the pattern has been validated through
              repeated successful usage.
            </p>
            <p style={{ margin: 0 }}>
              Extract instincts from session transcripts via CLI:{' '}
              <code style={{ fontSize: '0.75rem' }}>reagent instincts extract</code>
            </p>
          </div>
        </div>
      </div>

      {/* Summary stats */}
      {!isLoading && !error && data && data.length > 0 && (
        <SummaryCards stats={stats} />
      )}

      {/* Search + Filters */}
      {!isLoading && !error && (
        <div className="filter-bar" style={{ marginBottom: '1rem' }}>
          <div style={{ position: 'relative', flex: '1 1 260px', maxWidth: '360px' }}>
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
              placeholder="Search instincts by content, category, or tier…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search instincts"
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
            <Filter size={13} style={{ color: 'var(--text-muted)' }} />
            <span
              style={{
                fontSize: '0.75rem',
                color: 'var(--text-muted)',
                marginRight: '0.25rem',
              }}
            >
              Confidence:
            </span>
            {(['all', 'medium', 'high'] as const).map((f) => (
              <button
                key={f}
                className={`filter-chip ${confidenceFilter === f ? 'active' : ''}`}
                onClick={() => handleConfidenceFilter(f)}
              >
                {f === 'all' ? 'All' : f === 'medium' ? '≥50%' : '≥80%'}
              </button>
            ))}
          </div>

          {filtered.length !== (data?.length ?? 0) && (
            <span
              style={{
                fontSize: '0.75rem',
                color: 'var(--text-muted)',
                marginLeft: 'auto',
              }}
            >
              <span className="data-value" style={{ color: 'var(--accent)' }}>
                {filtered.length}
              </span>{' '}
              of {data?.length ?? 0} shown
            </span>
          )}
        </div>
      )}

      {/* CLI Actions — prominent above the instincts table */}
      {!isLoading && !error && (
        <div style={{ marginBottom: '1.5rem' }}>
          <div
            style={{
              marginBottom: '1rem',
              padding: '0.75rem 1rem',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              fontSize: '0.8125rem',
              lineHeight: 1.6,
              color: 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.625rem',
            }}
          >
            <Brain
              size={16}
              style={{ color: 'var(--accent)', flexShrink: 0, marginTop: '2px' }}
            />
            <span>
              Instinct extraction analyzes your Claude Code session transcripts to
              discover workflow patterns and coding preferences. You need to have used
              Claude Code in your repo to generate session data.
            </span>
          </div>
          <h3
            style={{
              fontSize: '0.8125rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--text-muted)',
              margin: '0 0 0.75rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <Terminal size={14} />
            CLI Actions
          </h3>
          <CLIActionsPanel />
        </div>
      )}

      {/* Tabs */}
      {!isLoading && !error && (
        <div className="tab-bar">
          <button
            className={`tab-btn ${tab === 'all' ? 'active' : ''}`}
            onClick={() => setTab('all')}
          >
            <span
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}
            >
              <BookOpen size={14} /> All
            </span>
          </button>
          <button
            className={`tab-btn ${tab === 'category' ? 'active' : ''}`}
            onClick={() => setTab('category')}
          >
            <span
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}
            >
              <Layers size={14} /> By Category
            </span>
          </button>
          <button
            className={`tab-btn ${tab === 'tier' ? 'active' : ''}`}
            onClick={() => setTab('tier')}
          >
            <span
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}
            >
              <Shield size={14} /> By Trust Tier
            </span>
          </button>
        </div>
      )}

      {/* Loading / Error */}
      {isLoading && <LoadingSpinner label="Loading instincts…" />}
      {error && (
        <ErrorMessage
          error={error instanceof Error ? error : new Error(String(error))}
        />
      )}

      {/* Empty data state */}
      {!isLoading && !error && data && data.length === 0 && (
        <EmptyState
          icon={<Brain size={48} />}
          title="No instincts yet"
          description="Extract instincts from your evaluation sessions to start building your pattern library. Run: reagent instincts extract"
        />
      )}

      {/* Tab content */}
      {!isLoading && !error && data && data.length > 0 && (
        <>
          {tab === 'all' && <AllTab instincts={filtered} />}
          {tab === 'category' && <CategoryTab instincts={filtered} />}
          {tab === 'tier' && <TierTab instincts={filtered} />}
        </>
      )}
    </div>
  )
}
