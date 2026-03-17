import { useEffect, useState } from 'react'
import { Radio, Cpu, Wifi, Activity, Eye, EyeOff } from 'lucide-react'
import { useStore } from '../lib/store'
import { getPresence, getHealth } from '../lib/api'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, AreaChart, Area } from 'recharts'
import clsx from 'clsx'

const MAX_HISTORY = 30

export function PerceptionPage() {
  const { presence, health } = useStore()
  const [cpuHistory, setCpuHistory] = useState<{ t: string; v: number }[]>([])
  const [memHistory, setMemHistory] = useState<{ t: string; v: number }[]>([])

  useEffect(() => {
    const tick = async () => {
      try {
        const h = await getHealth()
        const now = new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
        // Extract system metrics from layer data if available
        const cpu = h?.layers?.PerceptionPipeline?.cpu_percent
        const mem = h?.layers?.PerceptionPipeline?.mem_percent
        if (cpu != null) {
          setCpuHistory(prev => [...prev.slice(-MAX_HISTORY + 1), { t: now, v: Math.round(cpu) }])
        }
        if (mem != null) {
          setMemHistory(prev => [...prev.slice(-MAX_HISTORY + 1), { t: now, v: Math.round(mem) }])
        }
      } catch {/* ignore */}
    }

    tick()
    const id = setInterval(tick, 3000)
    return () => clearInterval(id)
  }, [])

  const activityColor: Record<string, string> = {
    active: 'text-green',
    typing: 'text-cyan',
    idle: 'text-amber',
    away: 'text-muted',
    walking: 'text-purple',
    unknown: 'text-muted',
  }

  const layers = health?.layers ?? {}

  return (
    <div className="h-full overflow-y-auto px-6 py-4">
      <div className="mx-auto max-w-3xl space-y-4">

        {/* Presence card */}
        <div className="rounded-xl border border-border bg-panel px-5 py-4">
          <div className="flex items-center gap-3 mb-4">
            <Radio className="h-5 w-5 text-red" />
            <h3 className="font-display text-sm font-semibold text-bright">Presence Sensing</h3>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <StatBlock
              label="Status"
              value={presence?.detected ? 'Detected' : 'Away'}
              icon={presence?.detected ? <Eye className="h-4 w-4 text-green" /> : <EyeOff className="h-4 w-4 text-muted" />}
              valueClass={presence?.detected ? 'text-green' : 'text-muted'}
            />
            <StatBlock
              label="Activity"
              value={presence?.activity ?? '—'}
              valueClass={activityColor[presence?.activity ?? 'unknown'] ?? 'text-muted'}
            />
            <StatBlock
              label="Confidence"
              value={presence ? `${Math.round(presence.confidence * 100)}%` : '—'}
              valueClass={
                (presence?.confidence ?? 0) > 0.7 ? 'text-green'
                  : (presence?.confidence ?? 0) > 0.4 ? 'text-amber'
                  : 'text-muted'
              }
            />
          </div>
        </div>

        {/* CPU chart */}
        <div className="rounded-xl border border-border bg-panel px-5 py-4">
          <div className="flex items-center gap-2 mb-3">
            <Cpu className="h-4 w-4 text-cyan" />
            <h3 className="font-mono text-xs text-muted">CPU USAGE</h3>
          </div>
          {cpuHistory.length > 1 ? (
            <ResponsiveContainer width="100%" height={100}>
              <AreaChart data={cpuHistory}>
                <defs>
                  <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="t" hide />
                <YAxis domain={[0, 100]} hide />
                <Tooltip
                  contentStyle={{ background: '#0d1117', border: '1px solid #1e2832', borderRadius: 8 }}
                  labelStyle={{ color: '#6b8299', fontSize: 10 }}
                  itemStyle={{ color: '#00d4ff', fontSize: 10 }}
                  formatter={(v: any) => [`${v}%`, 'CPU']}
                />
                <Area type="monotone" dataKey="v" stroke="#00d4ff" strokeWidth={1.5} fill="url(#cpuGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <p className="font-mono text-xs text-muted py-4 text-center">Collecting data…</p>
          )}
        </div>

        {/* System layer health */}
        <div className="rounded-xl border border-border bg-panel px-5 py-4">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="h-4 w-4 text-green" />
            <h3 className="font-mono text-xs text-muted">LAYER STATUS</h3>
          </div>
          <div className="space-y-2">
            {Object.entries(layers).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between">
                <span className="font-mono text-xs text-subtle">{name}</span>
                <div className="flex items-center gap-2">
                  <span className={clsx(
                    'h-1.5 w-1.5 rounded-full',
                    status === 'ok' ? 'bg-green' : 'bg-amber'
                  )} />
                  <span className={clsx(
                    'font-mono text-xs',
                    status === 'ok' ? 'text-green' : 'text-amber'
                  )}>
                    {typeof status === 'string' ? status.toUpperCase() : 'ACTIVE'}
                  </span>
                </div>
              </div>
            ))}
            {Object.keys(layers).length === 0 && (
              <p className="font-mono text-xs text-muted text-center py-2">Waiting for health data…</p>
            )}
          </div>
        </div>

        {/* WiFi CSI note */}
        <div className="rounded-xl border border-border bg-panel/50 px-5 py-3 flex items-start gap-3">
          <Wifi className="h-4 w-4 text-muted mt-0.5 flex-shrink-0" />
          <div>
            <p className="font-mono text-xs text-subtle">WiFi CSI Sensing</p>
            <p className="font-body text-xs text-muted mt-0.5">
              Enable with <code className="text-cyan bg-cyan/10 px-1 rounded">ENABLE_WIFI_CSI=true</code> in .env.
              Requires monitor-mode NIC and <code className="text-cyan bg-cyan/10 px-1 rounded">--profile wifi-csi</code> Docker flag.
              Falls back to CPU/mic activity heuristics otherwise.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function StatBlock({ label, value, icon, valueClass }: {
  label: string
  value: string
  icon?: React.ReactNode
  valueClass?: string
}) {
  return (
    <div className="rounded-lg border border-border bg-surface/50 px-3 py-2.5">
      <p className="font-mono text-xs text-muted mb-1">{label}</p>
      <div className="flex items-center gap-1.5">
        {icon}
        <span className={clsx('font-display text-sm font-semibold capitalize', valueClass)}>
          {value}
        </span>
      </div>
    </div>
  )
}
