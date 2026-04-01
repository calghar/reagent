import { useProviders } from '../hooks/useProviders'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'

const ENV_VAR_MAP: Record<string, string> = {
  anthropic: 'ANTHROPIC_API_KEY',
  openai: 'OPENAI_API_KEY',
  google: 'GOOGLE_API_KEY',
  ollama: 'OLLAMA_HOST (optional)',
}

export default function ProviderConfig() {
  const { data, isLoading, error } = useProviders()

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">Provider Config</h1>
        <p className="page-subtitle">LLM provider status and API key configuration</p>
      </div>

      <div className="page-banner">
        Reagent supports multiple LLM providers with automatic tiered fallback. Set API
        keys via environment variables (e.g. <code>ANTHROPIC_API_KEY</code>) or in your
        shell profile. The provider marked available with a configured key will be used
        for generation. Ollama runs locally with no API key needed.
      </div>

      {isLoading && <LoadingSpinner />}
      {error && (
        <ErrorMessage
          error={error instanceof Error ? error : new Error(String(error))}
        />
      )}

      {!isLoading && !error && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: '1rem',
          }}
        >
          {(data ?? []).map((p) => (
            <div key={p.provider} className="card">
              {/* Status dot + name */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.625rem',
                  marginBottom: '0.875rem',
                }}
              >
                <span
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: p.available ? '#22c55e' : '#ef4444',
                    flexShrink: 0,
                  }}
                  aria-label={p.available ? 'available' : 'unavailable'}
                />
                <span
                  style={{
                    fontWeight: 600,
                    fontSize: '1rem',
                    textTransform: 'capitalize',
                  }}
                >
                  {p.provider}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <Row label="Model" value={p.model} />
                <Row
                  label="API key"
                  value={p.key_configured ? '✓ Configured' : '✗ Missing'}
                />
                <Row label="Status" value={p.available ? 'Available' : 'Unavailable'} />
              </div>

              {!p.key_configured && p.provider.toLowerCase() !== 'ollama' && (
                <div
                  style={{
                    marginTop: '0.75rem',
                    padding: '0.5rem',
                    background: 'rgba(255, 255, 255, 0.04)',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    color: 'var(--text-muted)',
                  }}
                >
                  Set{' '}
                  <code style={{ color: '#00d4ff' }}>
                    {ENV_VAR_MAP[p.provider.toLowerCase()] ??
                      `${p.provider.toUpperCase()}_API_KEY`}
                  </code>{' '}
                  in your environment
                </div>
              )}
            </div>
          ))}

          {(data?.length ?? 0) === 0 && (
            <div
              style={{
                gridColumn: '1/-1',
                textAlign: 'center',
                padding: '4rem',
                color: 'var(--text-muted)',
              }}
            >
              No providers configured
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        fontSize: '0.875rem',
      }}
    >
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ color: 'var(--text-primary)' }}>{value}</span>
    </div>
  )
}
