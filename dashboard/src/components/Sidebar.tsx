import { NavLink } from 'react-router-dom'
import {
  LayoutGrid,
  TrendingUp,
  DollarSign,
  Brain,
  Zap,
  Play,
  FlaskConical,
  Moon,
  Sun,
} from 'lucide-react'
import { useTheme } from '../hooks/useTheme'

interface NavItem {
  to: string
  icon: React.ReactNode
  label: string
}

const NAV_ITEMS: NavItem[] = [
  { to: '/assets', icon: <LayoutGrid size={16} />, label: 'Assets' },
  { to: '/evals', icon: <TrendingUp size={16} />, label: 'Eval Trends' },
  { to: '/costs', icon: <DollarSign size={16} />, label: 'Cost Monitor' },
  { to: '/instincts', icon: <Brain size={16} />, label: 'Instinct Store' },
  { to: '/providers', icon: <Zap size={16} />, label: 'Providers' },
  { to: '/loops', icon: <Play size={16} />, label: 'Loop Control' },
]

export default function Sidebar() {
  const { theme, toggle } = useTheme()

  return (
    <aside
      style={{
        width: '220px',
        minWidth: '220px',
        background: 'var(--surface-1)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        padding: '1rem 0',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0 1rem 1.25rem',
          borderBottom: '1px solid var(--border)',
          marginBottom: '0.75rem',
        }}
      >
        <FlaskConical size={20} color="var(--accent)" />
        <span
          style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}
        >
          Reagent
        </span>
      </div>

      <nav style={{ flex: 1 }}>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: '0.625rem',
              padding: '0.5rem 1rem',
              color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
              background: isActive ? 'var(--accent-subtle)' : 'transparent',
              textDecoration: 'none',
              fontSize: '0.875rem',
              borderRadius: '0',
              transition: 'background 0.15s, color 0.15s',
              borderLeft: isActive
                ? '2px solid var(--accent)'
                : '2px solid transparent',
            })}
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div
        style={{
          padding: '0.75rem 1rem',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>v0.2.0</span>
        <button
          onClick={toggle}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            padding: '0.375rem',
            cursor: 'pointer',
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            transition: 'color 0.15s, border-color 0.15s',
          }}
        >
          {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
        </button>
      </div>
    </aside>
  )
}
