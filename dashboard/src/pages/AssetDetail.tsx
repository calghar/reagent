import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  FileText,
  Clock,
  Star,
  GitBranch,
  Play,
  RefreshCw,
  Shield,
  AlertTriangle,
  Diff,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  fetchAssetContent,
  fetchAssetDetail,
  evaluateAsset,
  regenerateAsset,
  scanAsset,
} from '../api/client'
import ScoreChart from '../components/ScoreChart'
import GradeBadge from '../components/GradeBadge'
import { ActionButton } from '../components/ActionButton'
import { useToast } from '../components/Toast'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import { scoreToGrade } from '../api/types'
import type { ScanResult } from '../api/types'
import { useState } from 'react'

type TabId = 'content' | 'history' | 'security' | 'diff'

export default function AssetDetailPage() {
  const { '*': assetPath } = useParams()
  const [activeTab, setActiveTab] = useState<TabId>('content')
  const [scanResults, setScanResults] = useState<ScanResult | null>(null)
  const qc = useQueryClient()
  const { addToast } = useToast()

  const {
    data: content,
    isLoading: loadingContent,
    error: contentError,
  } = useQuery({
    queryKey: ['asset-content', assetPath],
    queryFn: () => fetchAssetContent(assetPath ?? ''),
    enabled: !!assetPath,
  })

  const { data: history, isLoading: loadingHistory } = useQuery({
    queryKey: ['asset-detail', assetPath],
    queryFn: () => fetchAssetDetail(assetPath ?? ''),
    enabled: !!assetPath,
  })

  const evalMutation = useMutation({
    mutationFn: () => evaluateAsset(assetPath ?? ''),
    onSuccess: (result) => {
      addToast({
        type: 'success',
        title: 'Evaluation complete',
        message:
          result.quality_score != null
            ? `Score: ${result.quality_score.toFixed(0)}/100`
            : result.message,
      })
      void qc.invalidateQueries({ queryKey: ['asset-content', assetPath] })
      void qc.invalidateQueries({ queryKey: ['asset-detail', assetPath] })
    },
    onError: (err: Error) => {
      addToast({ type: 'error', title: 'Evaluation failed', message: err.message })
    },
  })

  const regenMutation = useMutation({
    mutationFn: () => regenerateAsset(assetPath ?? ''),
    onSuccess: (result) => {
      addToast({
        type: 'success',
        title: 'Regeneration complete',
        message: result.message,
      })
      void qc.invalidateQueries({ queryKey: ['asset-content', assetPath] })
    },
    onError: (err: Error) => {
      addToast({ type: 'error', title: 'Regeneration failed', message: err.message })
    },
  })

  const scanMutation = useMutation({
    mutationFn: () => scanAsset(assetPath ?? ''),
    onSuccess: (result) => {
      setScanResults(result)
      setActiveTab('security')
      const count = result.findings.length
      addToast({
        type: count > 0 ? 'warning' : 'success',
        title: 'Security scan complete',
        message: count > 0 ? `${count} finding(s) detected` : 'No issues found',
      })
    },
    onError: (err: Error) => {
      addToast({ type: 'error', title: 'Scan failed', message: err.message })
    },
  })

  if (!assetPath) {
    return (
      <div style={{ padding: '2rem', color: 'var(--text-muted)' }}>
        No asset selected
      </div>
    )
  }

  const grade =
    content?.quality_score != null ? scoreToGrade(content.quality_score) : null

  return (
    <div className="animate-fade-in">
      {/* Back nav */}
      <Link
        to="/assets"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.375rem',
          color: 'var(--text-secondary)',
          textDecoration: 'none',
          fontSize: '0.8125rem',
          marginBottom: '1rem',
          transition: 'color 0.15s',
        }}
      >
        <ArrowLeft size={14} />
        Back to Assets
      </Link>

      {loadingContent && <LoadingSpinner label="Loading asset…" />}

      {contentError && (
        <ErrorMessage
          error={
            contentError instanceof Error
              ? contentError
              : new Error(String(contentError))
          }
        />
      )}

      {content && (
        <>
          {/* Metadata header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              marginBottom: '1.25rem',
            }}
          >
            <div>
              <h1
                style={{
                  fontSize: '1.5rem',
                  fontWeight: 700,
                  margin: '0 0 0.375rem',
                  color: 'var(--text-primary)',
                }}
              >
                {content.asset_name}
              </h1>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  fontSize: '0.8125rem',
                  color: 'var(--text-secondary)',
                  flexWrap: 'wrap',
                }}
              >
                <span
                  className="badge"
                  style={{
                    background: 'var(--accent-subtle)',
                    color: 'var(--accent)',
                  }}
                >
                  {content.asset_type}
                </span>
                <span
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                  }}
                >
                  <GitBranch size={12} /> {content.repo_path}
                </span>
                {content.last_evaluated && (
                  <span
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                    }}
                  >
                    <Clock size={12} />{' '}
                    {new Date(content.last_evaluated).toLocaleDateString()}
                  </span>
                )}
              </div>
            </div>

            {grade && content.quality_score != null && (
              <div style={{ textAlign: 'center', flexShrink: 0 }}>
                <div
                  style={{
                    fontSize: '2rem',
                    fontWeight: 700,
                    color:
                      content.quality_score >= 80
                        ? 'var(--grade-a)'
                        : content.quality_score >= 60
                          ? 'var(--grade-c)'
                          : 'var(--grade-f)',
                  }}
                >
                  {content.quality_score.toFixed(0)}
                </div>
                <GradeBadge grade={grade} />
              </div>
            )}
          </div>

          {/* Action toolbar */}
          <div className="asset-action-bar" style={{ marginBottom: '1.25rem' }}>
            <ActionButton
              onClick={() => evalMutation.mutateAsync()}
              icon={<Play size={14} />}
              variant="primary"
              size="sm"
            >
              Evaluate
            </ActionButton>
            <ActionButton
              onClick={() => regenMutation.mutateAsync()}
              icon={<RefreshCw size={14} />}
              variant="ghost"
              size="sm"
            >
              Regenerate
            </ActionButton>
            <ActionButton
              onClick={() => scanMutation.mutateAsync()}
              icon={<Shield size={14} />}
              variant="ghost"
              size="sm"
            >
              Security Scan
            </ActionButton>
          </div>

          {/* Tabs */}
          <div className="tab-bar">
            <button
              className={`tab-btn ${activeTab === 'content' ? 'active' : ''}`}
              onClick={() => setActiveTab('content')}
            >
              <FileText
                size={14}
                style={{ marginRight: '0.375rem', verticalAlign: 'text-bottom' }}
              />
              Content
            </button>
            <button
              className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              <Star
                size={14}
                style={{ marginRight: '0.375rem', verticalAlign: 'text-bottom' }}
              />
              Eval History ({history?.length ?? 0})
            </button>
            <button
              className={`tab-btn ${activeTab === 'security' ? 'active' : ''}`}
              onClick={() => setActiveTab('security')}
            >
              <Shield
                size={14}
                style={{ marginRight: '0.375rem', verticalAlign: 'text-bottom' }}
              />
              Security
              {scanResults && scanResults.findings.length > 0 && (
                <span
                  style={{
                    marginLeft: '0.375rem',
                    background: 'rgba(239,68,68,0.15)',
                    color: 'var(--grade-f)',
                    borderRadius: '9999px',
                    padding: '0.0625rem 0.375rem',
                    fontSize: '0.6875rem',
                    fontWeight: 600,
                  }}
                >
                  {scanResults.findings.length}
                </span>
              )}
            </button>
            <button
              className={`tab-btn ${activeTab === 'diff' ? 'active' : ''}`}
              onClick={() => setActiveTab('diff')}
            >
              <Diff
                size={14}
                style={{ marginRight: '0.375rem', verticalAlign: 'text-bottom' }}
              />
              Diff
            </button>
          </div>

          {/* Content Tab */}
          {activeTab === 'content' && (
            <div className="card animate-fade-in">
              <div className="markdown-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {content.content}
                </ReactMarkdown>
              </div>
            </div>
          )}

          {/* History Tab */}
          {activeTab === 'history' && (
            <div
              className="animate-fade-in"
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '1.25rem',
              }}
            >
              {loadingHistory && <LoadingSpinner label="Loading evaluation history…" />}

              {!loadingHistory && history && history.length > 0 && (
                <div className="card">
                  <h3
                    style={{
                      fontSize: '0.9375rem',
                      fontWeight: 600,
                      marginBottom: '1rem',
                    }}
                  >
                    Score Trend
                  </h3>
                  <ScoreChart data={history} />
                </div>
              )}

              {!loadingHistory && history && history.length > 0 && (
                <div className="card" style={{ padding: 0 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Score</th>
                        <th>Grade</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((ep) => (
                        <tr key={ep.evaluation_id}>
                          <td>{new Date(ep.evaluated_at).toLocaleString()}</td>
                          <td
                            style={{
                              fontWeight: 600,
                              color:
                                ep.quality_score >= 80
                                  ? 'var(--grade-a)'
                                  : ep.quality_score >= 60
                                    ? 'var(--grade-c)'
                                    : 'var(--grade-f)',
                            }}
                          >
                            {ep.quality_score.toFixed(1)}
                          </td>
                          <td>
                            <GradeBadge grade={scoreToGrade(ep.quality_score)} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {!loadingHistory && (!history || history.length === 0) && (
                <EmptyState
                  icon={<Star size={40} />}
                  title="No evaluation history"
                  description="Run an evaluation to see score trends for this asset."
                />
              )}
            </div>
          )}

          {/* Security Tab */}
          {activeTab === 'security' && (
            <div className="card animate-fade-in">
              {!scanResults ? (
                <EmptyState
                  icon={<Shield size={40} />}
                  title="No scan results"
                  description='Click the "Security Scan" button above to check this asset for vulnerabilities.'
                />
              ) : scanResults.findings.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  <StatusBadge status="No issues found" variant="success" />
                  <p
                    style={{
                      color: 'var(--text-secondary)',
                      marginTop: '0.75rem',
                      fontSize: '0.875rem',
                    }}
                  >
                    The security scan completed without finding any issues.
                  </p>
                </div>
              ) : (
                <div>
                  <div
                    style={{
                      marginBottom: '0.75rem',
                      fontSize: '0.875rem',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    {scanResults.findings.length} finding
                    {scanResults.findings.length !== 1 ? 's' : ''} detected
                  </div>
                  {scanResults.findings.map((finding, i) => (
                    <div key={i} className="finding-row">
                      <AlertTriangle
                        size={14}
                        className={`severity-${finding.severity.toLowerCase()}`}
                      />
                      <div style={{ flex: 1 }}>
                        <div
                          style={{
                            fontWeight: 500,
                            color: 'var(--text-primary)',
                          }}
                        >
                          {finding.message}
                        </div>
                        <div
                          style={{
                            fontSize: '0.75rem',
                            color: 'var(--text-muted)',
                            display: 'flex',
                            gap: '0.5rem',
                            marginTop: '0.25rem',
                          }}
                        >
                          <StatusBadge status={finding.severity} />
                          {finding.line && <span>Line {finding.line}</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Diff Tab */}
          {activeTab === 'diff' && (
            <div className="card animate-fade-in">
              <EmptyState
                icon={<Diff size={40} />}
                title="Diff not available"
                description="Side-by-side diff is available for pending assets that have a previous version. View pending assets from the Loop Control page."
              />
            </div>
          )}
        </>
      )}
    </div>
  )
}
