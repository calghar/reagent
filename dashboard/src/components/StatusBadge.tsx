interface StatusBadgeProps {
  status: string
  variant?: 'success' | 'warning' | 'error' | 'info' | 'neutral'
}

const AUTO_VARIANT: Record<string, StatusBadgeProps['variant']> = {
  completed: 'success',
  approved: 'success',
  active: 'success',
  failed: 'error',
  rejected: 'error',
  error: 'error',
  running: 'info',
  in_progress: 'info',
  pending: 'warning',
  stopped: 'warning',
  paused: 'warning',
}

export function StatusBadge({ status, variant }: StatusBadgeProps) {
  const resolved = variant ?? AUTO_VARIANT[status.toLowerCase()] ?? 'neutral'
  return (
    <span className={`status-badge status-badge-${resolved}`}>
      <span className="status-badge-dot" />
      {status}
    </span>
  )
}
