import { useEffect, useState } from 'react'
import { Zap, Play, Loader2, ChevronDown, ChevronUp, CheckCircle, XCircle } from 'lucide-react'
import { useStore } from '../lib/store'
import { listSkills, runSkill } from '../lib/api'
import clsx from 'clsx'

export function SkillsPage() {
  const { skills, setSkills } = useStore()
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, any>>({})
  const [expanded, setExpanded] = useState<string | null>(null)
  const [params, setParams] = useState<Record<string, Record<string, string>>>({})

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const data = await listSkills()
        setSkills(data.skills)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    if (skills.length === 0) load()
  }, [])

  const handleRun = async (skillName: string) => {
    setRunning(skillName)
    setResults(r => ({ ...r, [skillName]: null }))
    try {
      const skillParams = params[skillName] ?? {}
      const result = await runSkill(skillName, skillParams)
      setResults(r => ({ ...r, [skillName]: result }))
    } catch (err) {
      setResults(r => ({ ...r, [skillName]: { error: (err as Error).message } }))
    } finally {
      setRunning(null)
    }
  }

  const setParam = (skill: string, key: string, val: string) => {
    setParams(p => ({ ...p, [skill]: { ...(p[skill] ?? {}), [key]: val } }))
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-4">
      <div className="mx-auto max-w-3xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-amber" />
            <h2 className="font-display text-base font-semibold text-bright">Skills Marketplace</h2>
          </div>
          <span className="font-mono text-xs text-muted">{skills.length} installed</span>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-amber" />
          </div>
        )}

        <div className="space-y-3">
          {skills.map(skill => {
            const isExpanded = expanded === skill.name
            const result = results[skill.name]
            const isRunning = running === skill.name
            const paramDefs = Object.entries(skill.parameters?.properties ?? {})

            return (
              <div
                key={skill.name}
                className="rounded-xl border border-border bg-panel overflow-hidden transition-all"
              >
                {/* Header */}
                <div
                  className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-panel/80"
                  onClick={() => setExpanded(isExpanded ? null : skill.name)}
                >
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-amber/30 bg-amber/10">
                    <Zap className="h-4 w-4 text-amber" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-sm font-medium text-bright">{skill.name}</p>
                    <p className="font-body text-xs text-subtle truncate">{skill.description}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-muted">v{skill.version}</span>
                    {isExpanded ? <ChevronUp className="h-4 w-4 text-muted" /> : <ChevronDown className="h-4 w-4 text-muted" />}
                  </div>
                </div>

                {/* Expanded */}
                {isExpanded && (
                  <div className="border-t border-border px-4 py-3 space-y-3">
                    {/* Params */}
                    {paramDefs.length > 0 && (
                      <div className="space-y-2">
                        <p className="font-mono text-xs text-muted">PARAMETERS</p>
                        {paramDefs.map(([key, def]: [string, any]) => (
                          <div key={key} className="flex items-center gap-2">
                            <label className="w-32 font-mono text-xs text-subtle flex-shrink-0">{key}</label>
                            {def.enum ? (
                              <select
                                value={params[skill.name]?.[key] ?? def.default ?? ''}
                                onChange={e => setParam(skill.name, key, e.target.value)}
                                className="flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 font-mono text-xs text-text"
                              >
                                {def.enum.map((v: string) => <option key={v}>{v}</option>)}
                              </select>
                            ) : (
                              <input
                                value={params[skill.name]?.[key] ?? def.default ?? ''}
                                onChange={e => setParam(skill.name, key, e.target.value)}
                                placeholder={def.description ?? key}
                                className="flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 font-mono text-xs text-text placeholder-muted focus:border-amber/40 focus:outline-none"
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Run button */}
                    <button
                      onClick={() => handleRun(skill.name)}
                      disabled={isRunning}
                      className="flex items-center gap-2 rounded-lg border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs text-amber hover:bg-amber/20 transition-all disabled:opacity-50"
                    >
                      {isRunning
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <Play className="h-3.5 w-3.5" />
                      }
                      {isRunning ? 'Running…' : 'Run Skill'}
                    </button>

                    {/* Result */}
                    {result !== undefined && result !== null && (
                      <div className={clsx(
                        'rounded-lg border p-3',
                        result.error
                          ? 'border-red/30 bg-red/5'
                          : 'border-green/30 bg-green/5'
                      )}>
                        <div className="flex items-center gap-2 mb-2">
                          {result.error
                            ? <XCircle className="h-4 w-4 text-red" />
                            : <CheckCircle className="h-4 w-4 text-green" />
                          }
                          <span className="font-mono text-xs text-muted">
                            {result.error ? 'Error' : 'Result'}
                          </span>
                        </div>
                        <pre className="font-mono text-xs text-text overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(result, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {!loading && skills.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 opacity-50">
            <Zap className="h-10 w-10 text-muted mb-3" />
            <p className="font-mono text-sm text-muted">No skills installed.</p>
            <p className="font-mono text-xs text-muted mt-1">Add a folder to skills/ with manifest.json + skill.py</p>
          </div>
        )}
      </div>
    </div>
  )
}
