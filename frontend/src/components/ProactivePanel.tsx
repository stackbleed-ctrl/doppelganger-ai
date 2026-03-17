import { useEffect, useState } from 'react'
import { Sparkles, X, Volume2, Clock, Loader2 } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface Suggestion {
  id: string
  type: string
  text: string
  confidence: number
  ts: number
  persona_id: string
}

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  morning_brief:    { label: 'Morning',    color: 'text-amber' },
  evening_summary:  { label: 'Evening',    color: 'text-purple' },
  weekly_review:    { label: 'Week',       color: 'text-cyan' },
  task_reminder:    { label: 'Reminder',   color: 'text-red' },
  pattern_insight:  { label: 'Insight',    color: 'text-green' },
  context_tip:      { label: 'Tip',        color: 'text-cyan' },
  goal_nudge:       { label: 'Goal',       color: 'text-amber' },
  anomaly_alert:    { label: 'Alert',      color: 'text-red' },
}

export function ProactivePanel() {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [speaking, setSpeaking] = useState<string | null>(null)

  const load = async () => {
    try {
      const r = await fetch(`${API}/proactive/suggestions?limit=10`)
      const data = await r.json()
      setSuggestions(data.suggestions ?? [])
    } catch {/* ignore */}
    finally { setLoading(false) }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [])

  const dismiss = async (id: string) => {
    await fetch(`${API}/proactive/suggestions/${id}/dismiss`, { method: 'POST' })
    setSuggestions(s => s.filter(x => x.id !== id))
  }

  const speak = async (suggestion: Suggestion) => {
    setSpeaking(suggestion.id)
    try {
      await fetch(`${API}/voice/speak?text=${encodeURIComponent(suggestion.text)}`, { method: 'POST' })
    } finally {
      setSpeaking(null)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center py-8">
      <Loader2 className="h-5 w-5 animate-spin text-muted" />
    </div>
  )

  if (suggestions.length === 0) return (
    <div className="flex flex-col items-center justify-center py-12 opacity-50">
      <Sparkles className="h-8 w-8 text-muted mb-2" />
      <p className="font-mono text-xs text-muted">No suggestions yet.</p>
      <p className="font-mono text-xs text-muted">Doppelganger is watching.</p>
    </div>
  )

  return (
    <div className="space-y-2">
      {suggestions.map(s => {
        const meta = TYPE_LABELS[s.type] ?? { label: s.type, color: 'text-subtle' }
        return (
          <div
            key={s.id}
            className="group rounded-xl border border-border bg-panel px-4 py-3 hover:border-border/60 transition-all animate-fade-in"
          >
            <div className="flex items-start gap-3">
              <Sparkles className={clsx('mt-0.5 h-4 w-4 flex-shrink-0', meta.color)} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={clsx('font-mono text-xs font-medium', meta.color)}>
                    {meta.label}
                  </span>
                  <span className="font-mono text-xs text-muted">
                    {Math.round(s.confidence * 100)}% confidence
                  </span>
                </div>
                <p className="font-body text-sm text-text leading-relaxed">{s.text}</p>
                <div className="mt-1.5 flex items-center gap-1">
                  <Clock className="h-3 w-3 text-muted" />
                  <span className="font-mono text-xs text-muted">
                    {formatDistanceToNow(new Date(s.ts * 1000), { addSuffix: true })}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={() => speak(s)}
                  className="rounded p-1 text-muted hover:text-cyan transition-colors"
                  title="Speak"
                >
                  {speaking === s.id
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    : <Volume2 className="h-3.5 w-3.5" />
                  }
                </button>
                <button
                  onClick={() => dismiss(s.id)}
                  className="rounded p-1 text-muted hover:text-red transition-colors"
                  title="Dismiss"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
