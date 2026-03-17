import { NavLink } from 'react-router-dom'
import {
  MessageSquare, Brain, Globe2, Zap, Radio,
  ChevronLeft, Dna
} from 'lucide-react'
import { useStore } from '../lib/store'
import clsx from 'clsx'

const NAV = [
  { to: '/chat',        icon: MessageSquare, label: 'Chat',       color: 'text-cyan' },
  { to: '/memory',      icon: Brain,         label: 'Memory',     color: 'text-purple' },
  { to: '/sim',         icon: Globe2,        label: 'Worlds',     color: 'text-green' },
  { to: '/skills',      icon: Zap,           label: 'Skills',     color: 'text-amber' },
  { to: '/perception',  icon: Radio,         label: 'Senses',     color: 'text-red' },
]

export function Sidebar() {
  const { sidebarOpen, toggleSidebar, health, wsConnected } = useStore()

  return (
    <aside className={clsx(
      'fixed left-0 top-0 z-20 flex h-full flex-col bg-surface border-r border-border',
      'transition-all duration-300',
      sidebarOpen ? 'w-64' : 'w-0 overflow-hidden'
    )}>
      {/* Logo */}
      <div className="flex h-14 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-2">
          <Dna className="h-6 w-6 text-cyan animate-pulse-slow" />
          <span className="font-display font-bold text-bright tracking-tight">Doppelganger</span>
        </div>
        <button
          onClick={toggleSidebar}
          className="rounded p-1 text-muted hover:text-text transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      {/* Status badge */}
      <div className="mx-3 mt-3 rounded-lg border border-border bg-panel px-3 py-2">
        <div className="flex items-center gap-2">
          <span className={clsx(
            'h-2 w-2 rounded-full',
            wsConnected ? 'bg-green animate-pulse' : 'bg-red'
          )} />
          <span className="font-mono text-xs text-subtle">
            {wsConnected ? 'ONLINE' : 'OFFLINE'}
          </span>
          {health && (
            <span className="ml-auto font-mono text-xs text-muted">
              {health.uptime_sec > 3600
                ? `${Math.floor(health.uptime_sec / 3600)}h`
                : `${Math.floor(health.uptime_sec / 60)}m`}
            </span>
          )}
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-1 flex-col gap-1 p-3 mt-2">
        {NAV.map(({ to, icon: Icon, label, color }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => clsx(
              'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150',
              isActive
                ? 'bg-panel border border-border text-bright shadow-sm'
                : 'text-muted hover:text-text hover:bg-panel/50'
            )}
          >
            {({ isActive }) => (
              <>
                <Icon className={clsx('h-4 w-4', isActive ? color : 'text-muted')} />
                <span>{label}</span>
                {isActive && (
                  <span className={clsx('ml-auto h-1.5 w-1.5 rounded-full', color.replace('text-', 'bg-'))} />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom — layer health */}
      {health && (
        <div className="border-t border-border p-3">
          <p className="mb-2 font-mono text-xs text-muted">LAYERS</p>
          {Object.entries(health.layers ?? {}).map(([name, status]) => (
            <div key={name} className="flex items-center justify-between py-0.5">
              <span className="font-mono text-xs text-subtle truncate">{name}</span>
              <span className={clsx(
                'font-mono text-xs',
                status === 'ok' ? 'text-green' : 'text-amber'
              )}>
                {typeof status === 'string' ? status : 'ok'}
              </span>
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
