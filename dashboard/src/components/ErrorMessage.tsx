import { AlertCircle } from 'lucide-react'

interface ErrorMessageProps {
  error: Error | null
  fallback?: string
}

export default function ErrorMessage({
  error,
  fallback = 'Something went wrong.',
}: ErrorMessageProps) {
  const message = error?.message ?? fallback
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.625rem',
        padding: '1rem',
        background: 'rgba(239,68,68,0.1)',
        border: '1px solid rgba(239,68,68,0.3)',
        borderRadius: '8px',
        color: '#ef4444',
        fontSize: '0.875rem',
      }}
      role="alert"
    >
      <AlertCircle size={16} />
      <span>{message}</span>
    </div>
  )
}
