import { useState, useCallback } from 'react'
import type { ReactNode, MouseEvent } from 'react'
import { Loader2 } from 'lucide-react'

interface ActionButtonProps {
  onClick: () => Promise<unknown> | void
  children: ReactNode
  variant?: 'primary' | 'danger' | 'ghost'
  size?: 'sm' | 'md'
  icon?: ReactNode
  disabled?: boolean
  title?: string
}

export function ActionButton({
  onClick,
  children,
  variant = 'primary',
  size = 'md',
  icon,
  disabled,
  title,
}: ActionButtonProps) {
  const [loading, setLoading] = useState(false)

  const handleClick = useCallback(
    async (e: MouseEvent) => {
      e.preventDefault()
      if (loading || disabled) return
      setLoading(true)
      try {
        await onClick()
      } finally {
        setLoading(false)
      }
    },
    [onClick, loading, disabled]
  )

  const sizeClass = size === 'sm' ? 'action-btn-sm' : ''
  const variantClass = `action-btn-${variant}`

  return (
    <button
      className={`action-btn ${variantClass} ${sizeClass}`}
      onClick={handleClick}
      disabled={loading || disabled}
      title={title}
    >
      {loading ? (
        <Loader2 size={size === 'sm' ? 12 : 14} className="action-btn-spinner" />
      ) : icon ? (
        <span className="action-btn-icon">{icon}</span>
      ) : null}
      {children}
    </button>
  )
}
