import { useState } from 'react'
import { Globe2, Loader2, ChevronDown, ChevronUp, Zap } from 'lucide-react'
import { useStore } from '../lib/store'
import { runSimulation } from '../lib/api'
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts'
import clsx from 'clsx'

const EXAMPLE_SCENARIOS = [
  "What if I quit my job and go freelance?",
  "What if I move to a new city?",
  "What if I start building a side project this weekend?",
  "What if I cut social media for 30 days?",
]

export function SimPage() {
  const { simResult, simLoading, setSimResult, setSimLoading } = useStore()
  const [scenario, setScenario] = useState('')
  const [worlds, setWorlds] = useState(3)
  const [steps, setSteps] = useState(4)
  const [expandedWorld, setExpandedWorld] = useState<number | null>(null)

  const handleSimulate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!scenario.trim() || simLoading) return
    setSimLoading(true)
    setSimResult(null)
    try {
      const result = await runSimulation(scenario, steps, worlds)
      setSimResult(result)
    } catch (err) {
      console.error(err)
    } finally {
      setSimLoading(false)
    }
  }

  const chartData = simResult?.worlds.map((w: any, i: number) => ({
    name: `W${i + 1}`,
    score: Math.round(w.utility_score * 100),
  })) ?? []

  return (
    <div className="flex h-full flex-col">
      {/* Input panel */}
      <div className="border-b border-border bg-surface/50 px-6 py-4">
        <div className="mx-auto max-w-3xl">
          <form onSubmit={handleSimulate} className="space-y-3">
            <div className="flex gap-2">
              <textarea
                value={scenario}
                onChange={e => setScenario(e.target.value)}
                placeholder="Describe a scenario to simulate across parallel worlds…"
                rows={2}
                className="flex-1 resize-none rounded-xl border border-border bg-panel px-4 py-3 font-body text-sm text-text placeholder-muted focus:border-green/40 focus:outline-none transition-colors"
              />
              <button
                type="submit"
                disabled={simLoading || !scenario.trim()}
                className={clsx(
                  'flex flex-col items-center justify-center gap-1 rounded-xl border px-5 py-3 text-sm font-medium transition-all',
                  simLoading || !scenario.trim()
                    ? 'border-border text-muted opacity-50 cursor-not-allowed'
                    : 'border-green/40 bg-green/10 text-green hover:bg-green/20 shadow-glow-green'
                )}
              >
                {simLoading
                  ? <Loader2 className="h-5 w-5 animate-spin" />
                  : <Globe2 className="h-5 w-5" />
                }
                <span className="font-mono text-xs">{simLoading ? 'Running' : 'Simulate'}</span>
              </button>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 font-mono text-xs text-subtle">
                Worlds:
                <select
                  value={worlds}
                  onChange={e => setWorlds(Number(e.target.value))}
                  className="rounded bg-panel border border-border px-2 py-1 text-xs text-text"
                >
                  {[2,3,4,5].map(n => <option key={n}>{n}</option>)}
                </select>
              </label>
              <label className="flex items-center gap-2 font-mono text-xs text-subtle">
                Depth:
                <select
                  value={steps}
                  onChange={e => setSteps(Number(e.target.value))}
                  className="rounded bg-panel border border-border px-2 py-1 text-xs text-text"
                >
                  {[2,4,6,8].map(n => <option key={n}>{n}</option>)}
                </select>
              </label>
            </div>

            {/* Examples */}
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_SCENARIOS.map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setScenario(s)}
                  className="rounded-lg border border-border bg-panel px-3 py-1 font-body text-xs text-subtle hover:text-text hover:border-green/30 transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </form>
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-3xl">
          {simLoading && (
            <div className="flex flex-col items-center justify-center py-16 gap-4">
              <div className="relative h-16 w-16">
                <Globe2 className="h-16 w-16 text-green opacity-20 animate-spin" style={{ animationDuration: '8s' }} />
                <Loader2 className="absolute inset-0 h-16 w-16 text-green animate-spin" />
              </div>
              <p className="font-mono text-sm text-subtle">Simulating {worlds} parallel worlds…</p>
              <p className="font-mono text-xs text-muted">This may take 20–60 seconds</p>
            </div>
          )}

          {simResult && (
            <div className="space-y-4 animate-fade-in">
              {/* Synthesis card */}
              <div className="rounded-xl border border-green/30 bg-green/5 px-5 py-4 shadow-glow-green">
                <div className="flex items-start gap-3">
                  <Zap className="mt-0.5 h-5 w-5 flex-shrink-0 text-green" />
                  <div>
                    <p className="font-display text-xs font-semibold uppercase tracking-wider text-green mb-1">
                      Best Path · {Math.round(simResult.confidence * 100)}% confidence
                    </p>
                    <p className="font-body text-sm text-text leading-relaxed">{simResult.synthesis}</p>
                    <p className="mt-2 font-mono text-xs text-subtle">
                      {simResult.worlds.length} worlds · {simResult.elapsed_sec}s
                    </p>
                  </div>
                </div>
              </div>

              {/* Score chart */}
              {chartData.length > 0 && (
                <div className="rounded-xl border border-border bg-panel px-5 py-4">
                  <p className="mb-3 font-mono text-xs text-muted">WORLD UTILITY SCORES</p>
                  <ResponsiveContainer width="100%" height={80}>
                    <BarChart data={chartData} barSize={32}>
                      <XAxis dataKey="name" />
                      <YAxis domain={[0, 100]} hide />
                      <Tooltip
                        contentStyle={{ background: '#131920', border: '1px solid #1e2832', borderRadius: 8 }}
                        labelStyle={{ color: '#6b8299', fontFamily: 'JetBrains Mono', fontSize: 11 }}
                        itemStyle={{ color: '#00ff94' }}
                      />
                      <Bar dataKey="score" radius={[4,4,0,0]}>
                        {chartData.map((_: any, i: number) => (
                          <Cell
                            key={i}
                            fill={i === 0 ? '#00ff94' : '#1e2832'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* World cards */}
              <div className="space-y-2">
                {simResult.worlds.map((w: any, i: number) => (
                  <div
                    key={i}
                    className={clsx(
                      'rounded-xl border bg-panel transition-all cursor-pointer',
                      i === 0 ? 'border-green/30' : 'border-border hover:border-border/60',
                    )}
                    onClick={() => setExpandedWorld(expandedWorld === i ? null : i)}
                  >
                    <div className="flex items-center gap-3 px-4 py-3">
                      <span className={clsx(
                        'flex h-6 w-6 items-center justify-center rounded-full font-mono text-xs font-bold',
                        i === 0 ? 'bg-green/20 text-green' : 'bg-panel text-muted border border-border'
                      )}>
                        {i + 1}
                      </span>
                      <p className="flex-1 font-body text-sm text-text leading-snug line-clamp-2">
                        {w.outcome}
                      </p>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={clsx(
                          'font-mono text-xs',
                          w.utility_score >= 0.7 ? 'text-green' : w.utility_score >= 0.4 ? 'text-amber' : 'text-red'
                        )}>
                          {Math.round(w.utility_score * 100)}
                        </span>
                        {expandedWorld === i
                          ? <ChevronUp className="h-3 w-3 text-muted" />
                          : <ChevronDown className="h-3 w-3 text-muted" />
                        }
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!simLoading && !simResult && (
            <div className="flex flex-col items-center justify-center py-16 opacity-50">
              <Globe2 className="h-12 w-12 text-muted mb-3" />
              <p className="font-mono text-sm text-muted">Enter a scenario to explore parallel futures.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
