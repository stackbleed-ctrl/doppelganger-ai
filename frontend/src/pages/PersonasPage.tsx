import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Plus, Check, Trash2, ChevronRight } from 'lucide-react'
import clsx from 'clsx'

interface Persona {
  id: string
  name: string
  description: string
  color: string
  emoji: string
  voice_id: string
  temperature: number
  reasoning_style: string
  memory_scope: string
  auto_switch_triggers: string[]
}

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function fetchPersonas(): Promise<{ personas: Persona[]; active_id: string }> {
  const r = await fetch(`${API}/personas`)
  return r.json()
}

async function activatePersona(id: string): Promise<void> {
  await fetch(`${API}/personas/${id}/activate`, { method: 'POST' })
}

async function deletePersona(id: string): Promise<void> {
  await fetch(`${API}/personas/${id}`, { method: 'DELETE' })
}

export function PersonaBar() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [activeId, setActiveId] = useState('default')
  const [switching, setSwitching] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const data = await fetchPersonas()
      setPersonas(data.personas)
      setActiveId(data.active_id)
    } catch {/* backend may not be up */}
    finally { setLoading(false) }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [])

  const handleSwitch = async (persona: Persona) => {
    if (persona.id === activeId) return
    setSwitching(persona.id)
    try {
      await activatePersona(persona.id)
      setActiveId(persona.id)
    } finally {
      setSwitching(null)
    }
  }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (id === 'default') return
    await deletePersona(id)
    await load()
  }

  if (loading) return (
    <div className="flex items-center justify-center py-4">
      <Loader2 className="h-4 w-4 animate-spin text-muted" />
    </div>
  )

  return (
    <div className="space-y-1.5">
      <p className="font-mono text-xs text-muted px-1 mb-2">PERSONAS</p>
      {personas.map(p => {
        const isActive = p.id === activeId
        const isLoading = switching === p.id
        return (
          <button
            key={p.id}
            onClick={() => handleSwitch(p)}
            disabled={isLoading}
            className={clsx(
              'group w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all duration-200',
              isActive
                ? 'bg-panel border shadow-sm'
                : 'hover:bg-panel/50 border border-transparent'
            )}
            style={isActive ? { borderColor: p.color + '44', boxShadow: `0 0 12px ${p.color}18` } : {}}
          >
            {/* Emoji + color dot */}
            <div
              className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-base"
              style={{ background: p.color + '18', border: `1px solid ${p.color}33` }}
            >
              {p.emoji}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className={clsx(
                  'font-mono text-xs font-medium truncate',
                  isActive ? 'text-bright' : 'text-subtle'
                )}>
                  {p.name}
                </span>
                {isActive && (
                  <span
                    className="h-1.5 w-1.5 rounded-full flex-shrink-0"
                    style={{ background: p.color }}
                  />
                )}
              </div>
              <p className="font-body text-xs text-muted truncate">{p.description}</p>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              {isLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted" />
              ) : isActive ? (
                <Check className="h-3.5 w-3.5" style={{ color: p.color }} />
              ) : null}
              {p.id !== 'default' && (
                <button
                  onClick={(e) => handleDelete(e, p.id)}
                  className="rounded p-0.5 text-muted hover:text-red transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}


// ─── Full Personas Page ───────────────────────────────────────────────────────

export function PersonasPage() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [activeId, setActiveId] = useState('default')
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [switching, setSwitching] = useState<string | null>(null)

  const [form, setForm] = useState({
    id: '', name: '', description: '',
    system_prompt: '', voice_id: 'af_sky',
    temperature: 0.7, color: '#00d4ff', emoji: '🤖',
    reasoning_style: 'balanced', memory_scope: 'shared',
    auto_switch_triggers: '',
  })

  const load = async () => {
    try {
      const data = await fetchPersonas()
      setPersonas(data.personas)
      setActiveId(data.active_id)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleSwitch = async (id: string) => {
    setSwitching(id)
    try {
      await activatePersona(id)
      setActiveId(id)
    } finally { setSwitching(null) }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      await fetch(`${API}/personas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          auto_switch_triggers: form.auto_switch_triggers.split(',').map(s => s.trim()).filter(Boolean),
        }),
      })
      setShowCreate(false)
      setForm({ id: '', name: '', description: '', system_prompt: '', voice_id: 'af_sky', temperature: 0.7, color: '#00d4ff', emoji: '🤖', reasoning_style: 'balanced', memory_scope: 'shared', auto_switch_triggers: '' })
      await load()
    } finally { setCreating(false) }
  }

  const active = personas.find(p => p.id === activeId)

  return (
    <div className="h-full overflow-y-auto px-6 py-4">
      <div className="mx-auto max-w-3xl space-y-4">

        {/* Active persona hero */}
        {active && (
          <div
            className="rounded-2xl border p-5 transition-all"
            style={{ borderColor: active.color + '44', background: active.color + '08' }}
          >
            <div className="flex items-center gap-4">
              <div
                className="flex h-14 w-14 items-center justify-center rounded-2xl text-3xl"
                style={{ background: active.color + '18', border: `1px solid ${active.color}33` }}
              >
                {active.emoji}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="font-display text-lg font-bold text-bright">{active.name}</h2>
                  <span
                    className="rounded-full px-2 py-0.5 font-mono text-xs"
                    style={{ color: active.color, background: active.color + '18' }}
                  >
                    ACTIVE
                  </span>
                </div>
                <p className="font-body text-sm text-subtle">{active.description}</p>
                <div className="mt-1 flex gap-3">
                  <span className="font-mono text-xs text-muted">🗣 {active.voice_id}</span>
                  <span className="font-mono text-xs text-muted">🧠 {active.reasoning_style}</span>
                  <span className="font-mono text-xs text-muted">💾 {active.memory_scope}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Persona grid */}
        <div className="grid grid-cols-2 gap-3">
          {personas.map(p => {
            const isActive = p.id === activeId
            const isLoading = switching === p.id
            return (
              <button
                key={p.id}
                onClick={() => handleSwitch(p.id)}
                disabled={isActive || !!isLoading}
                className={clsx(
                  'flex items-start gap-3 rounded-xl border p-4 text-left transition-all',
                  isActive
                    ? 'cursor-default'
                    : 'hover:bg-panel cursor-pointer border-border'
                )}
                style={isActive ? {
                  borderColor: p.color + '44',
                  background: p.color + '08',
                } : {}}
              >
                <span className="text-2xl">{p.emoji}</span>
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-sm font-medium text-bright truncate">{p.name}</p>
                  <p className="font-body text-xs text-subtle mt-0.5 line-clamp-2">{p.description}</p>
                  {p.auto_switch_triggers.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {p.auto_switch_triggers.slice(0, 3).map(t => (
                        <span key={t} className="rounded bg-panel border border-border px-1.5 py-0.5 font-mono text-xs text-muted">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted flex-shrink-0 mt-0.5" />}
              </button>
            )
          })}

          {/* New persona card */}
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-border p-4 text-muted hover:text-text hover:border-cyan/40 transition-all"
          >
            <Plus className="h-5 w-5" />
            <span className="font-mono text-sm">New Persona</span>
          </button>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="rounded-xl border border-cyan/30 bg-cyan/5 p-5">
            <h3 className="font-display text-sm font-semibold text-bright mb-4">Create Persona</h3>
            <form onSubmit={handleCreate} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="ID" value={form.id} onChange={v => setForm(f => ({ ...f, id: v }))} placeholder="work_v2" required />
                <Field label="Name" value={form.name} onChange={v => setForm(f => ({ ...f, name: v }))} placeholder="Work Mode v2" required />
              </div>
              <Field label="Description" value={form.description} onChange={v => setForm(f => ({ ...f, description: v }))} placeholder="Brief description" />
              <div>
                <label className="font-mono text-xs text-muted block mb-1">System Prompt</label>
                <textarea
                  value={form.system_prompt}
                  onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                  rows={4}
                  placeholder="You are in... mode. Be..."
                  className="w-full resize-none rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text placeholder-muted focus:border-cyan/40 focus:outline-none"
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="font-mono text-xs text-muted block mb-1">Emoji</label>
                  <input value={form.emoji} onChange={e => setForm(f => ({ ...f, emoji: e.target.value }))}
                    className="w-full rounded-lg border border-border bg-panel px-3 py-2 text-center text-xl focus:outline-none" />
                </div>
                <div>
                  <label className="font-mono text-xs text-muted block mb-1">Color</label>
                  <input type="color" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
                    className="w-full h-[38px] rounded-lg border border-border bg-panel cursor-pointer" />
                </div>
                <div>
                  <label className="font-mono text-xs text-muted block mb-1">Temp</label>
                  <input type="number" min={0} max={1} step={0.1} value={form.temperature}
                    onChange={e => setForm(f => ({ ...f, temperature: Number(e.target.value) }))}
                    className="w-full rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text focus:outline-none" />
                </div>
              </div>
              <Field label="Auto-switch triggers (comma-separated)" value={form.auto_switch_triggers}
                onChange={v => setForm(f => ({ ...f, auto_switch_triggers: v }))}
                placeholder="meeting, standup, work" />
              <div className="flex gap-2 pt-1">
                <button type="submit" disabled={creating}
                  className="flex items-center gap-2 rounded-lg border border-cyan/40 bg-cyan/10 px-4 py-2 font-mono text-xs text-cyan hover:bg-cyan/20 transition-all disabled:opacity-50">
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  Create
                </button>
                <button type="button" onClick={() => setShowCreate(false)}
                  className="rounded-lg border border-border px-4 py-2 font-mono text-xs text-muted hover:text-text transition-all">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, required }: {
  label: string; value: string; onChange: (v: string) => void
  placeholder?: string; required?: boolean
}) {
  return (
    <div>
      <label className="font-mono text-xs text-muted block mb-1">{label}</label>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className="w-full rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text placeholder-muted focus:border-cyan/40 focus:outline-none"
      />
    </div>
  )
}
