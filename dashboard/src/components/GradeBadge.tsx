interface GradeBadgeProps {
  grade: 'A' | 'B' | 'C' | 'D' | 'F'
}

const GRADE_STYLES: Record<string, { bg: string; color: string }> = {
  A: { bg: 'rgba(34,197,94,0.15)', color: '#22c55e' },
  B: { bg: 'rgba(132,204,22,0.15)', color: '#84cc16' },
  C: { bg: 'rgba(234,179,8,0.15)', color: '#eab308' },
  D: { bg: 'rgba(249,115,22,0.15)', color: '#f97316' },
  F: { bg: 'rgba(239,68,68,0.15)', color: '#ef4444' },
}

export default function GradeBadge({ grade }: GradeBadgeProps) {
  const { bg, color } = GRADE_STYLES[grade] ?? GRADE_STYLES['F']
  return (
    <span
      style={{
        background: bg,
        color,
        borderRadius: '4px',
        padding: '0.1875rem 0.5rem',
        fontSize: '0.8125rem',
        fontWeight: 700,
        letterSpacing: '0.05em',
        minWidth: '2rem',
        textAlign: 'center',
        flexShrink: 0,
      }}
    >
      {grade}
    </span>
  )
}
