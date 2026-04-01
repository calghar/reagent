import { scoreToGrade } from '../api/types'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, Play, Shield } from 'lucide-react'
import GradeBadge from './GradeBadge'
import type { AssetSummary } from '../api/types'

interface AssetCardProps {
  asset: AssetSummary
}

const TYPE_COLOURS: Record<string, string> = {
  agent: '#6366f1',
  skill: '#06b6d4',
  hook: '#8b5cf6',
  rule: '#f59e0b',
  command: '#10b981',
  claude_md: '#ec4899',
}

export default function AssetCard({ asset }: AssetCardProps) {
  const navigate = useNavigate()
  const grade = scoreToGrade(asset.latest_score)
  const pct = asset.latest_score.toFixed(1)
  const typeColour = TYPE_COLOURS[asset.asset_type] ?? '#888'
  const lastEval = new Date(asset.last_evaluated).toLocaleDateString()
  const detailUrl = `/assets/detail/${encodeURIComponent(asset.asset_path)}`

  return (
    <Link
      to={detailUrl}
      className="card card-interactive"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        textDecoration: 'none',
        color: 'inherit',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '0.5rem',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontWeight: 600,
              fontSize: '0.9375rem',
              color: 'var(--text-primary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            {asset.asset_name}
            {asset.status === 'pending' && (
              <span
                style={{
                  fontSize: '0.625rem',
                  fontWeight: 600,
                  color: '#f59e0b',
                  background: 'rgba(245, 158, 11, 0.12)',
                  padding: '0.125rem 0.375rem',
                  borderRadius: '0.25rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  flexShrink: 0,
                }}
              >
                Pending
              </span>
            )}
          </div>
          <span
            style={{
              fontSize: '0.75rem',
              color: typeColour,
              fontWeight: 500,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            {asset.asset_type}
          </span>
        </div>
        <GradeBadge grade={grade} />
      </div>

      {/* Score bar */}
      <div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: '0.375rem',
          }}
        >
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Quality score
          </span>
          <span
            style={{
              fontSize: '0.875rem',
              fontWeight: 600,
              color:
                asset.latest_score >= 80
                  ? 'var(--grade-a)'
                  : asset.latest_score >= 60
                    ? 'var(--grade-c)'
                    : 'var(--grade-f)',
            }}
          >
            {pct}%
          </span>
        </div>
        <div
          style={{
            height: '4px',
            background: 'var(--surface-2)',
            borderRadius: '2px',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${pct}%`,
              background:
                asset.latest_score >= 80
                  ? 'var(--grade-a)'
                  : asset.latest_score >= 60
                    ? 'var(--grade-c)'
                    : 'var(--grade-f)',
              borderRadius: '2px',
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>

      {/* Footer */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
        }}
      >
        <span>
          {asset.evaluation_count} eval{asset.evaluation_count !== 1 ? 's' : ''}
        </span>
        <span>{lastEval}</span>
      </div>

      {/* Quick actions */}
      <div className="card-quick-actions" onClick={(e) => e.preventDefault()}>
        <button
          className="icon-btn"
          title="View detail"
          onClick={(e) => {
            e.preventDefault()
            navigate(detailUrl)
          }}
        >
          <Eye size={14} />
        </button>
        <button
          className="icon-btn"
          title="Evaluate"
          onClick={(e) => {
            e.preventDefault()
            navigate(detailUrl)
          }}
        >
          <Play size={14} />
        </button>
        <button
          className="icon-btn"
          title="Security scan"
          onClick={(e) => {
            e.preventDefault()
            navigate(detailUrl)
          }}
        >
          <Shield size={14} />
        </button>
      </div>
    </Link>
  )
}
