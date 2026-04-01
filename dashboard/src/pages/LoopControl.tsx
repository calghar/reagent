import { useState, useMemo, useCallback, Fragment } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Play,
  Check,
  Sparkles,
  TrendingUp,
  Eye,
  Terminal,
  ChevronRight,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  Rocket,
  X,
  Package,
  RotateCcw,
} from 'lucide-react'
import {
  approvePendingAsset,
  rejectPendingAsset,
  deployAllPending,
} from '../api/client'
import {
  useLoopRuns,
  usePendingAssets,
  useGenerations,
  useRepos,
} from '../hooks/useLoops'
import { ActionButton } from '../components/ActionButton'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'
import { Modal } from '../components/Modal'
import { useToast } from '../components/Toast'

// ── Types ────────────────────────────────────────────────────────────────────

type LoopType = 'init' | 'improve' | 'watch'
type TabId = 'runs' | 'pending' | 'generations'

interface LoopTypeOption {
  id: LoopType
  icon: React.ReactNode
  title: string
  description: string
}

// ── Constants ────────────────────────────────────────────────────────────────

const LOOP_TYPES: LoopTypeOption[] = [
  {
    id: 'init',
    icon: <Sparkles size={22} />,
    title: 'Init',
    description: 'Generate all missing assets from scratch',
  },
  {
    id: 'improve',
    icon: <TrendingUp size={22} />,
    title: 'Improve',
    description: 'Regenerate below-threshold assets to raise quality',
  },
  {
    id: 'watch',
    icon: <Eye size={22} />,
    title: 'Watch',
    description: 'Monitor for file changes and auto-regenerate',
  },
]

const STATUS_ICONS: Record<string, React.ReactNode> = {
  running: <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />,
  completed: <CheckCircle size={14} color="var(--grade-a)" />,
  failed: <XCircle size={14} color="var(--grade-f)" />,
  stopped: <AlertTriangle size={14} color="var(--grade-c)" />,
}

// ── Helper: score color ──────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--grade-a)'
  if (score >= 60) return 'var(--grade-c)'
  return 'var(--grade-f)'
}

// ── Component ────────────────────────────────────────────────────────────────

export default function LoopControl() {
  const qc = useQueryClient()
  const { addToast } = useToast()

  // ── Trigger workflow state ─────────────────────────────────────────────────
  const [selectedType, setSelectedType] = useState<LoopType>('improve')
  const [repoPath, setRepoPath] = useState('')
  const [copied, setCopied] = useState(false)

  // ── Tab & UI state ─────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<TabId>('runs')
  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [confirmAction, setConfirmAction] = useState<{
    type: 'approve' | 'reject' | 'deploy-all' | 'reject-all'
    pendingId?: string
    assetName?: string
  } | null>(null)
  const [diffModal, setDiffModal] = useState<{
    name: string
    previous: string
    current: string
  } | null>(null)

  // ── Data queries ───────────────────────────────────────────────────────────
  const { data: loopRuns, isLoading: loadingRuns } = useLoopRuns()
  const { data: pendingAssets, isLoading: loadingPending } = usePendingAssets()
  const { data: generations, isLoading: loadingGens } = useGenerations()
  const { data: knownReposData } = useRepos()

  // ── Mutations ──────────────────────────────────────────────────────────────
  const approveMutation = useMutation({
    mutationFn: (id: string) => approvePendingAsset(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pending-assets'] })
      addToast({ type: 'success', title: 'Asset approved' })
    },
    onError: (err: Error) => {
      addToast({ type: 'error', title: 'Approval failed', message: err.message })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (id: string) => rejectPendingAsset(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pending-assets'] })
      addToast({ type: 'info', title: 'Asset rejected' })
    },
    onError: (err: Error) => {
      addToast({ type: 'error', title: 'Rejection failed', message: err.message })
    },
  })

  const deployAllMutation = useMutation({
    mutationFn: deployAllPending,
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: ['pending-assets'] })
      void qc.invalidateQueries({ queryKey: ['assets'] })
      addToast({
        type: 'success',
        title: 'Deployed',
        message: `${result.deployed_count} asset(s) deployed`,
      })
    },
    onError: (err: Error) => {
      addToast({ type: 'error', title: 'Deploy failed', message: err.message })
    },
  })

  // ── Derived values ─────────────────────────────────────────────────────────
  const cliCommand = `reagent loop ${selectedType} --repo ${repoPath || '.'}`

  const pendingCount = pendingAssets?.filter((a) => a.status === 'pending').length ?? 0

  const knownRepos = useMemo(() => {
    const repos = new Set<string>()
    if (knownReposData) {
      for (const r of knownReposData) repos.add(r)
    }
    if (loopRuns) {
      for (const run of loopRuns) repos.add(run.repo_path)
    }
    return Array.from(repos).sort()
  }, [knownReposData, loopRuns])

  const filteredRuns = useMemo(() => {
    if (!loopRuns) return []
    return loopRuns.filter((run) => {
      if (typeFilter !== 'all' && run.loop_type !== typeFilter) return false
      if (statusFilter !== 'all' && run.status !== statusFilter) return false
      return true
    })
  }, [loopRuns, typeFilter, statusFilter])

  // ── Handlers ───────────────────────────────────────────────────────────────
  const copyCommand = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(cliCommand)
      setCopied(true)
      addToast({ type: 'success', title: 'Copied to clipboard', message: cliCommand })
      setTimeout(() => setCopied(false), 2000)
    } catch {
      addToast({
        type: 'error',
        title: 'Copy failed',
        message: 'Could not access clipboard',
      })
    }
  }, [cliCommand, addToast])

  const handleConfirmAction = async () => {
    if (!confirmAction) return
    try {
      switch (confirmAction.type) {
        case 'approve':
          if (confirmAction.pendingId)
            await approveMutation.mutateAsync(confirmAction.pendingId)
          break
        case 'reject':
          if (confirmAction.pendingId)
            await rejectMutation.mutateAsync(confirmAction.pendingId)
          break
        case 'deploy-all':
          await deployAllMutation.mutateAsync()
          break
        case 'reject-all':
          if (pendingAssets) {
            const results = await Promise.allSettled(
              pendingAssets
                .filter((a) => a.status === 'pending')
                .map((asset) => rejectMutation.mutateAsync(asset.pending_id))
            )
            const failed = results.filter((r) => r.status === 'rejected').length
            if (failed > 0) {
              addToast({
                type: 'error',
                title: 'Partial failure',
                message: `${failed} rejection(s) failed`,
              })
            }
          }
          break
      }
    } catch {
      // onError handlers on mutations already show toasts
    } finally {
      setConfirmAction(null)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="animate-fade-in">
      {/* ── Page Header ─────────────────────────────────────────────────────── */}
      <div className="page-header">
        <h1 className="page-title">Loop Control</h1>
        <p className="page-subtitle">
          Configure and launch autonomous improvement loops
        </p>
      </div>

      <div className="page-banner">
        Autonomous loops run generate → evaluate → improve cycles with guardrails. All
        generated assets are queued for approval before deployment. Start a loop via
        CLI, then monitor progress in the <strong>Loop Runs</strong> tab below.
      </div>

      {/* ── Trigger Workflow ─────────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
        <h2
          style={{
            fontSize: '1rem',
            fontWeight: 600,
            color: 'var(--text-primary)',
            margin: '0 0 1.25rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Terminal size={18} color="var(--accent)" />
          Launch a Loop
        </h2>

        {/* Step 1: Loop Type */}
        <div style={{ marginBottom: '1.25rem' }}>
          <div
            style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--text-muted)',
              marginBottom: '0.625rem',
            }}
          >
            1 · Loop Type
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '0.75rem',
            }}
          >
            {LOOP_TYPES.map((lt) => {
              const isSelected = selectedType === lt.id
              return (
                <button
                  key={lt.id}
                  onClick={() => setSelectedType(lt.id)}
                  className="card-interactive"
                  style={{
                    background: isSelected
                      ? 'var(--accent-subtle)'
                      : 'var(--surface-2)',
                    border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius)',
                    padding: '1rem',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.2s ease',
                    boxShadow: isSelected ? 'var(--glow-primary-strong)' : 'none',
                    outline: 'none',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      marginBottom: '0.375rem',
                    }}
                  >
                    {/* Radio indicator */}
                    <span
                      style={{
                        width: '16px',
                        height: '16px',
                        borderRadius: '50%',
                        border: `2px solid ${isSelected ? 'var(--accent)' : 'var(--text-muted)'}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      {isSelected && (
                        <span
                          style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: 'var(--accent)',
                          }}
                        />
                      )}
                    </span>
                    <span
                      style={{
                        color: isSelected ? 'var(--accent)' : 'var(--text-muted)',
                      }}
                    >
                      {lt.icon}
                    </span>
                    <span
                      style={{
                        fontWeight: 600,
                        fontSize: '0.9375rem',
                        color: isSelected ? 'var(--accent)' : 'var(--text-primary)',
                      }}
                    >
                      {lt.title}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: '0.8125rem',
                      color: 'var(--text-secondary)',
                      lineHeight: 1.4,
                    }}
                  >
                    {lt.description}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Step 2: Repository */}
        <div style={{ marginBottom: '1.25rem' }}>
          <div
            style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--text-muted)',
              marginBottom: '0.625rem',
            }}
          >
            2 · Repository
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <select
              className="filter-select"
              value={knownRepos.includes(repoPath) ? repoPath : '__custom__'}
              onChange={(e) => {
                if (e.target.value !== '__custom__') setRepoPath(e.target.value)
              }}
              style={{ minWidth: '200px' }}
            >
              <option value="__custom__">Select a repo…</option>
              {knownRepos.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <input
              className="input"
              type="text"
              value={repoPath}
              onChange={(e) => setRepoPath(e.target.value)}
              placeholder="/absolute/path/to/repo"
              style={{ flex: 1, maxWidth: '400px' }}
            />
          </div>
          <div
            style={{
              fontSize: '0.6875rem',
              color: 'var(--text-muted)',
              marginTop: '0.375rem',
            }}
          >
            Enter the absolute path to any repository on this machine
            {knownRepos.length > 0 &&
              ', or select a previously scanned repo from the dropdown.'}
          </div>
        </div>

        {/* Step 3: Summary Card */}
        <div
          style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--accent)',
            borderRadius: 'var(--radius)',
            padding: '1rem 1.25rem',
            marginBottom: '1.25rem',
            boxShadow: 'var(--glow-primary)',
          }}
        >
          <div
            style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--text-muted)',
              marginBottom: '0.75rem',
            }}
          >
            3 · Pre-launch Summary
          </div>

          {/* Command display */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              marginBottom: '0.75rem',
            }}
          >
            <ChevronRight size={14} color="var(--accent)" style={{ flexShrink: 0 }} />
            <code
              className="data-value"
              style={{
                flex: 1,
                fontSize: '0.9375rem',
                color: 'var(--accent)',
                background: 'var(--surface-0)',
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid var(--border)',
              }}
            >
              {cliCommand}
            </code>
          </div>

          {/* Guardrails info */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '0.75rem',
              fontSize: '0.8125rem',
              color: 'var(--text-secondary)',
            }}
          >
            {selectedType === 'watch' ? (
              <>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                  }}
                >
                  <Eye size={12} color="var(--text-muted)" />
                  Monitors file changes in real-time
                </span>
                <span
                  style={{
                    width: '1px',
                    height: '1em',
                    background: 'var(--border)',
                    alignSelf: 'center',
                  }}
                />
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                  }}
                >
                  <Clock size={12} color="var(--text-muted)" />
                  30-minute timeout
                </span>
              </>
            ) : (
              <>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                  }}
                >
                  <RotateCcw size={12} color="var(--text-muted)" />
                  Max 5 iterations
                </span>
                <span
                  style={{
                    width: '1px',
                    height: '1em',
                    background: 'var(--border)',
                    alignSelf: 'center',
                  }}
                />
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                  }}
                >
                  <AlertTriangle size={12} color="var(--text-muted)" />
                  $2.00 budget cap
                </span>
                <span
                  style={{
                    width: '1px',
                    height: '1em',
                    background: 'var(--border)',
                    alignSelf: 'center',
                  }}
                />
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                  }}
                >
                  <TrendingUp size={12} color="var(--text-muted)" />
                  Target score: 80
                </span>
              </>
            )}
          </div>

          <div
            style={{
              marginTop: '0.625rem',
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              fontStyle: 'italic',
            }}
          >
            {selectedType === 'watch'
              ? 'Copy the command below and run it in your terminal to start watching'
              : 'Assets are queued for approval before deployment'}
          </div>
        </div>

        {/* Step 4: Action */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button
            className="btn btn-primary"
            onClick={() => void copyCommand()}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            {copied ? <Check size={14} /> : <Terminal size={14} />}
            {copied ? 'Copied!' : 'Copy Command to Clipboard'}
          </button>

          {pendingCount > 0 && (
            <StatusBadge
              status={`${pendingCount} pending approval`}
              variant="warning"
            />
          )}
        </div>
      </div>

      {/* ── Tab Bar ──────────────────────────────────────────────────────────── */}
      <div className="tab-bar">
        <button
          className={`tab-btn ${activeTab === 'runs' ? 'active' : ''}`}
          onClick={() => setActiveTab('runs')}
        >
          Loop Runs {loopRuns ? `(${filteredRuns.length})` : ''}
        </button>
        <button
          className={`tab-btn ${activeTab === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          Pending Approval {pendingCount > 0 && `(${pendingCount})`}
        </button>
        <button
          className={`tab-btn ${activeTab === 'generations' ? 'active' : ''}`}
          onClick={() => setActiveTab('generations')}
        >
          Generations {generations ? `(${generations.length})` : ''}
        </button>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* ── Tab 1: Loop Runs ───────────────────────────────────────────────── */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {activeTab === 'runs' && (
        <div className="animate-fade-in">
          {/* Filters */}
          <div className="filter-bar">
            <select
              className="filter-select"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="all">All Types</option>
              <option value="init">Init</option>
              <option value="improve">Improve</option>
              <option value="watch">Watch</option>
            </select>
            <select
              className="filter-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All Statuses</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="stopped">Stopped</option>
            </select>
          </div>

          <div className="card" style={{ padding: 0 }}>
            {loadingRuns ? (
              <div
                style={{
                  padding: '2rem',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                }}
              >
                <Loader2
                  size={20}
                  style={{
                    animation: 'spin 1s linear infinite',
                    marginBottom: '0.5rem',
                  }}
                />
                <div>Loading loop runs…</div>
              </div>
            ) : !loopRuns || loopRuns.length === 0 ? (
              <EmptyState
                icon={<Play size={40} />}
                title="No loop runs yet"
                description="Use the trigger section above to copy a CLI command and start your first autonomous improvement loop."
              />
            ) : filteredRuns.length === 0 ? (
              <EmptyState
                icon={<Clock size={40} />}
                title="No matching runs"
                description="Try adjusting the type or status filters above."
              />
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: '2rem' }} />
                    <th>Status</th>
                    <th>Type</th>
                    <th>Repository</th>
                    <th>Iterations</th>
                    <th>Avg Score</th>
                    <th>Cost</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRuns.map((run) => {
                    const isExpanded = expandedRun === run.loop_id
                    return (
                      <Fragment key={run.loop_id}>
                        <tr
                          className="expandable-row"
                          onClick={() =>
                            setExpandedRun(isExpanded ? null : run.loop_id)
                          }
                        >
                          <td style={{ width: '2rem', textAlign: 'center' }}>
                            <ChevronRight
                              size={14}
                              style={{
                                transition: 'transform 0.2s',
                                transform: isExpanded ? 'rotate(90deg)' : 'rotate(0)',
                                color: 'var(--text-muted)',
                              }}
                            />
                          </td>
                          <td>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.375rem',
                              }}
                            >
                              {STATUS_ICONS[run.status] ?? null}
                              <StatusBadge status={run.status} />
                            </span>
                          </td>
                          <td>
                            <span
                              style={{
                                fontWeight: 500,
                                textTransform: 'capitalize',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.375rem',
                              }}
                            >
                              {run.loop_type === 'init' && (
                                <Sparkles size={12} color="var(--accent)" />
                              )}
                              {run.loop_type === 'improve' && (
                                <TrendingUp size={12} color="var(--accent)" />
                              )}
                              {run.loop_type === 'watch' && (
                                <Eye size={12} color="var(--accent)" />
                              )}
                              {run.loop_type}
                            </span>
                          </td>
                          <td
                            style={{
                              color: 'var(--text-secondary)',
                              fontSize: '0.8125rem',
                            }}
                          >
                            {run.repo_path === '.'
                              ? '.'
                              : run.repo_path.split('/').pop()}
                          </td>
                          <td className="data-value">{run.iteration}</td>
                          <td
                            className="data-value"
                            style={{
                              fontWeight: 600,
                              color:
                                run.avg_score != null
                                  ? scoreColor(run.avg_score)
                                  : 'var(--text-muted)',
                            }}
                          >
                            {run.avg_score != null ? run.avg_score.toFixed(1) : '—'}
                          </td>
                          <td className="data-value">${run.total_cost.toFixed(4)}</td>
                          <td
                            style={{
                              color: 'var(--text-muted)',
                              fontSize: '0.8125rem',
                            }}
                          >
                            {new Date(run.started_at).toLocaleString()}
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr key={`${run.loop_id}-detail`}>
                            <td colSpan={8} style={{ padding: 0 }}>
                              <div
                                className="expand-detail"
                                style={{
                                  display: 'grid',
                                  gridTemplateColumns:
                                    'repeat(auto-fit, minmax(180px, 1fr))',
                                  gap: '0.75rem',
                                  fontSize: '0.8125rem',
                                }}
                              >
                                <div>
                                  <div
                                    style={{
                                      color: 'var(--text-muted)',
                                      fontSize: '0.6875rem',
                                      textTransform: 'uppercase',
                                      letterSpacing: '0.06em',
                                      marginBottom: '0.25rem',
                                    }}
                                  >
                                    Full Path
                                  </div>
                                  <div
                                    className="data-value"
                                    style={{
                                      color: 'var(--text-secondary)',
                                      fontSize: '0.75rem',
                                      wordBreak: 'break-all',
                                    }}
                                  >
                                    {run.repo_path}
                                  </div>
                                </div>
                                <div>
                                  <div
                                    style={{
                                      color: 'var(--text-muted)',
                                      fontSize: '0.6875rem',
                                      textTransform: 'uppercase',
                                      letterSpacing: '0.06em',
                                      marginBottom: '0.25rem',
                                    }}
                                  >
                                    Loop ID
                                  </div>
                                  <code
                                    className="data-value"
                                    style={{
                                      background: 'var(--surface-3)',
                                      padding: '0.125rem 0.375rem',
                                      borderRadius: '4px',
                                      fontSize: '0.75rem',
                                    }}
                                  >
                                    {run.loop_id.slice(0, 16)}
                                  </code>
                                </div>
                                {run.stop_reason && (
                                  <div>
                                    <div
                                      style={{
                                        color: 'var(--text-muted)',
                                        fontSize: '0.6875rem',
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.06em',
                                        marginBottom: '0.25rem',
                                      }}
                                    >
                                      Stop Reason
                                    </div>
                                    <div
                                      style={{
                                        color: 'var(--grade-c)',
                                        fontSize: '0.8125rem',
                                        lineHeight: 1.5,
                                      }}
                                    >
                                      {run.stop_reason.includes(';') ? (
                                        <ul
                                          style={{
                                            margin: 0,
                                            paddingLeft: '1.25rem',
                                            listStyle: 'disc',
                                          }}
                                        >
                                          {run.stop_reason
                                            .split(';')
                                            .map((r) => r.trim())
                                            .filter(Boolean)
                                            .map((reason, i) => (
                                              <li key={i}>{reason}</li>
                                            ))}
                                        </ul>
                                      ) : (
                                        run.stop_reason
                                      )}
                                    </div>
                                  </div>
                                )}
                                {run.completed_at && (
                                  <div>
                                    <div
                                      style={{
                                        color: 'var(--text-muted)',
                                        fontSize: '0.6875rem',
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.06em',
                                        marginBottom: '0.25rem',
                                      }}
                                    >
                                      Completed
                                    </div>
                                    <div style={{ color: 'var(--text-secondary)' }}>
                                      {new Date(run.completed_at).toLocaleString()}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* ── Tab 2: Pending Approval ────────────────────────────────────────── */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {activeTab === 'pending' && (
        <div className="animate-fade-in">
          {loadingPending ? (
            <div
              style={{
                padding: '2rem',
                textAlign: 'center',
                color: 'var(--text-muted)',
              }}
            >
              <Loader2
                size={20}
                style={{ animation: 'spin 1s linear infinite', marginBottom: '0.5rem' }}
              />
              <div>Loading pending assets…</div>
            </div>
          ) : !pendingAssets || pendingAssets.length === 0 ? (
            <EmptyState
              icon={<Package size={40} />}
              title="No pending assets"
              description="When a loop generates or improves assets, they appear here for review before being written to disk. Run a loop to get started."
            />
          ) : (
            <>
              {/* Bulk actions bar */}
              {pendingCount > 0 && (
                <div className="bulk-actions-bar">
                  <span
                    style={{
                      fontSize: '0.8125rem',
                      color: 'var(--text-secondary)',
                      marginRight: 'auto',
                    }}
                  >
                    {pendingCount} asset{pendingCount !== 1 ? 's' : ''} awaiting review
                  </span>
                  <ActionButton
                    onClick={() => {
                      setConfirmAction({ type: 'deploy-all' })
                      return Promise.resolve()
                    }}
                    icon={<Rocket size={14} />}
                    variant="primary"
                    size="sm"
                  >
                    Deploy All
                  </ActionButton>
                  <ActionButton
                    onClick={() => {
                      setConfirmAction({ type: 'reject-all' })
                      return Promise.resolve()
                    }}
                    icon={<X size={14} />}
                    variant="danger"
                    size="sm"
                  >
                    Reject All
                  </ActionButton>
                </div>
              )}

              {/* Pending asset cards */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                  gap: '0.75rem',
                }}
              >
                {pendingAssets.map((asset, idx) => (
                  <div
                    key={asset.pending_id}
                    className="pending-card animate-stagger-in"
                    style={{ animationDelay: `${idx * 0.04}s` }}
                  >
                    <div className="pending-card-header">
                      <div style={{ minWidth: 0 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: '0.9375rem',
                            color: 'var(--text-primary)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {asset.asset_name}
                        </div>
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            marginTop: '0.25rem',
                          }}
                        >
                          <span
                            className="badge"
                            style={{
                              background: 'var(--accent-subtle)',
                              color: 'var(--accent)',
                            }}
                          >
                            {asset.asset_type}
                          </span>
                          <StatusBadge status={asset.status} />
                        </div>
                      </div>
                      {/* Score change */}
                      <div style={{ textAlign: 'right', flexShrink: 0 }}>
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.25rem',
                          }}
                        >
                          {asset.previous_score != null && (
                            <span
                              className="data-value"
                              style={{
                                color: 'var(--text-muted)',
                                fontSize: '0.875rem',
                              }}
                            >
                              {asset.previous_score.toFixed(0)} →
                            </span>
                          )}
                          <span
                            className="data-value"
                            style={{
                              fontSize: '1.125rem',
                              fontWeight: 700,
                              color: scoreColor(asset.new_score),
                            }}
                          >
                            {asset.new_score.toFixed(0)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {asset.generation_method} · iter {asset.iteration} ·{' '}
                      {new Date(asset.created_at).toLocaleDateString()}
                    </div>

                    {/* Card actions */}
                    {asset.status === 'pending' && (
                      <div className="pending-card-actions">
                        <ActionButton
                          onClick={() => {
                            setConfirmAction({
                              type: 'approve',
                              pendingId: asset.pending_id,
                              assetName: asset.asset_name,
                            })
                            return Promise.resolve()
                          }}
                          icon={<Check size={12} />}
                          variant="primary"
                          size="sm"
                        >
                          Approve
                        </ActionButton>
                        <ActionButton
                          onClick={() => {
                            setConfirmAction({
                              type: 'reject',
                              pendingId: asset.pending_id,
                              assetName: asset.asset_name,
                            })
                            return Promise.resolve()
                          }}
                          icon={<X size={12} />}
                          variant="danger"
                          size="sm"
                        >
                          Reject
                        </ActionButton>
                        {asset.previous_content != null && (
                          <ActionButton
                            onClick={() => {
                              setDiffModal({
                                name: asset.asset_name,
                                previous: asset.previous_content ?? '',
                                current: asset.content,
                              })
                              return Promise.resolve()
                            }}
                            icon={<Eye size={12} />}
                            variant="ghost"
                            size="sm"
                          >
                            Diff
                          </ActionButton>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* ── Tab 3: Generations ─────────────────────────────────────────────── */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {activeTab === 'generations' && (
        <div className="card animate-fade-in" style={{ padding: 0 }}>
          {loadingGens ? (
            <div
              style={{
                padding: '2rem',
                textAlign: 'center',
                color: 'var(--text-muted)',
              }}
            >
              <Loader2
                size={20}
                style={{ animation: 'spin 1s linear infinite', marginBottom: '0.5rem' }}
              />
              <div>Loading generations…</div>
            </div>
          ) : !generations || generations.length === 0 ? (
            <EmptyState
              icon={<Sparkles size={40} />}
              title="No generation records"
              description="When assets are created or regenerated via LLM during loop execution, they appear here with provider and cost details."
            />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Cost</th>
                  <th>Generated</th>
                </tr>
              </thead>
              <tbody>
                {generations.map((g, idx) => (
                  <tr
                    key={g.cache_key}
                    className="animate-stagger-in"
                    style={{ animationDelay: `${idx * 0.03}s` }}
                  >
                    <td style={{ fontWeight: 500 }}>{g.name}</td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          background: 'var(--accent-subtle)',
                          color: 'var(--accent)',
                        }}
                      >
                        {g.asset_type}
                      </span>
                    </td>
                    <td>{g.provider}</td>
                    <td>
                      <span
                        className="data-value"
                        style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}
                      >
                        {g.model}
                      </span>
                    </td>
                    <td className="data-value">${g.cost_usd.toFixed(5)}</td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
                      {new Date(g.generated_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Confirm Dialog ──────────────────────────────────────────────────── */}
      <ConfirmDialog
        isOpen={confirmAction != null}
        title={
          confirmAction?.type === 'approve'
            ? 'Approve Asset'
            : confirmAction?.type === 'reject'
              ? 'Reject Asset'
              : confirmAction?.type === 'deploy-all'
                ? 'Deploy All Pending'
                : 'Reject All Pending'
        }
        message={
          confirmAction?.type === 'approve'
            ? `Approve "${confirmAction.assetName ?? 'this asset'}" for deployment?`
            : confirmAction?.type === 'reject'
              ? `Reject "${confirmAction.assetName ?? 'this asset'}"? This cannot be undone.`
              : confirmAction?.type === 'deploy-all'
                ? `Deploy all ${pendingCount} pending asset(s)? They will be written to disk.`
                : `Reject all ${pendingCount} pending asset(s)? This cannot be undone.`
        }
        confirmLabel={
          confirmAction?.type === 'approve'
            ? 'Approve'
            : confirmAction?.type === 'reject'
              ? 'Reject'
              : confirmAction?.type === 'deploy-all'
                ? 'Deploy All'
                : 'Reject All'
        }
        variant={
          confirmAction?.type === 'approve' || confirmAction?.type === 'deploy-all'
            ? 'primary'
            : 'danger'
        }
        onConfirm={() => void handleConfirmAction()}
        onCancel={() => setConfirmAction(null)}
      />

      {/* ── Diff Modal ──────────────────────────────────────────────────────── */}
      <Modal
        isOpen={diffModal != null}
        onClose={() => setDiffModal(null)}
        title={`Diff: ${diffModal?.name ?? ''}`}
        size="lg"
      >
        {diffModal && (
          <div className="diff-container">
            <div>
              <div className="diff-panel-label">Previous</div>
              <div className="diff-panel">{diffModal.previous}</div>
            </div>
            <div>
              <div className="diff-panel-label">New</div>
              <div className="diff-panel">{diffModal.current}</div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
