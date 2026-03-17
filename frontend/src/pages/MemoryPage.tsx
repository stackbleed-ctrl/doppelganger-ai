import { useState, useEffect } from 'react'
import { Search, Plus, Clock, Tag, Loader2, Brain, GitBranch, Upload, Globe, BookOpen } from 'lucide-react'
import { useStore } from '../lib/store'
import { searchMemory, getMemoryTimeline, storeMemory } from '../lib/api'
import { MemoryGraph } from '../components/graph/MemoryGraph'
import clsx from 'clsx'
import { format } from 'date-fns'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
type Tab = 'timeline' | 'search' | 'graph' | 'import'

export function MemoryPage() {
  const { memories, setMemories } = useStore()
  const [tab, setTab] = useState<Tab>('timeline')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)
  const [newMemory, setNewMemory] = useState('')
  const [storing, setStoring] = useState(false)
  const [timeline, setTimeline] = useState<any[]>([])
  const [loadingTimeline, setLoadingTimeline] = useState(false)
  const [importing, setImporting] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<any>(null)
  const [obsidianPath, setObsidianPath] = useState('')
  const [browserDays, setBrowserDays] = useState(30)

  useEffect(() => { loadTimeline() }, [])

  const loadTimeline = async () => {
    setLoadingTimeline(true)
    try {
      const data = await getMemoryTimeline(72)
      setTimeline(data.nodes)
    } catch {/* ignore */}
    finally { setLoadingTimeline(false) }
  }

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const data = await searchMemory(query, 12)
      setResults(data.results)
      setTab('search')
    } finally { setSearching(false) }
  }

  const handleStore = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newMemory.trim()) return
    setStoring(true)
    try {
      await storeMemory(newMemory, ['manual'])
      setNewMemory('')
      setTimeout(loadTimeline, 500)
    } finally { setStoring(false) }
  }

  const handleImport = async (source: string) => {
    setImporting(source)
    setImportResult(null)
    try {
      const body: any = { source }
      if (source === 'obsidian') body.vault_path = obsidianPath
      if (source === 'notion') body.import_all = true
      if (source === 'browser') body.days_back = browserDays
      const resp = await fetch(`${API}/memory/import`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      setImportResult(await resp.json())
      setTimeout(loadTimeline, 1000)
    } catch (e: any) {
      setImportResult({ error: e.message })
    } finally { setImporting(null) }
  }

  const displayNodes = tab === 'search' ? results : timeline
  const TABS = [
    { id: 'timeline', label: 'Timeline', icon: Clock },
    { id: 'search',   label: 'Search',   icon: Search },
    { id: 'graph',    label: 'Graph',    icon: GitBranch },
    { id: 'import',   label: 'Import',   icon: Upload },
  ] as const

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border bg-surface/50 px-6 py-3">
        <div className="mx-auto max-w-4xl space-y-2">
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
              <input value={query} onChange={e => setQuery(e.target.value)}
                placeholder="Search your memory graph…"
                className="w-full rounded-lg border border-border bg-panel py-2.5 pl-10 pr-4 font-body text-sm text-text placeholder-muted focus:border-purple/40 focus:outline-none" />
            </div>
            <button type="submit" disabled={searching}
              className="flex items-center gap-2 rounded-lg border border-purple/40 bg-purple/10 px-4 py-2 text-sm font-medium text-purple hover:bg-purple/20 disabled:opacity-50">
              {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            </button>
          </form>
          <form onSubmit={handleStore} className="flex gap-2">
            <input value={newMemory} onChange={e => setNewMemory(e.target.value)}
              placeholder="Store a new memory…"
              className="flex-1 rounded-lg border border-border bg-panel py-2 px-4 font-body text-sm text-text placeholder-muted focus:border-green/40 focus:outline-none" />
            <button type="submit" disabled={storing || !newMemory.trim()}
              className="rounded-lg border border-green/40 bg-green/10 px-3 py-2 text-sm text-green hover:bg-green/20 disabled:opacity-50">
              {storing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            </button>
          </form>
          <div className="flex gap-1">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setTab(id as Tab)}
                className={clsx('flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-xs font-medium transition-all',
                  tab === id ? 'bg-panel border border-border text-bright' : 'text-muted hover:text-text')}>
                <Icon className="h-3.5 w-3.5" />{label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {tab === 'graph' ? (
        <MemoryGraph />
      ) : tab === 'import' ? (
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="mx-auto max-w-2xl space-y-4">
            <div className="flex items-center gap-2 mb-2">
              <Upload className="h-4 w-4 text-cyan" />
              <h2 className="font-display text-sm font-semibold text-bright">Import Memory</h2>
            </div>
            {[
              { id: 'obsidian', label: 'Obsidian Vault', icon: BookOpen, color: 'border-purple/40 text-purple hover:bg-purple/10',
                desc: 'Import all markdown notes',
                field: <input value={obsidianPath} onChange={e => setObsidianPath(e.target.value)}
                  placeholder="/Users/you/obsidian-vault"
                  className="w-full rounded-lg border border-border bg-panel px-3 py-2 font-mono text-xs text-text placeholder-muted focus:outline-none" />
              },
              { id: 'notion', label: 'Notion', icon: Globe, color: 'border-cyan/40 text-cyan hover:bg-cyan/10',
                desc: 'Requires NOTION_API_KEY in .env',
                field: <p className="font-mono text-xs text-muted">Set NOTION_API_KEY env var to enable</p>
              },
              { id: 'browser', label: 'Browser History', icon: Search, color: 'border-green/40 text-green hover:bg-green/10',
                desc: 'Chrome, Firefox, Safari — local SQLite read',
                field: <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-muted">Days back:</span>
                  <input type="number" min={1} max={365} value={browserDays}
                    onChange={e => setBrowserDays(Number(e.target.value))}
                    className="w-20 rounded-lg border border-border bg-panel px-2 py-1 font-mono text-xs text-text focus:outline-none" />
                </div>
              },
            ].map(src => (
              <div key={src.id} className="rounded-xl border border-border bg-panel p-4 space-y-3">
                <div className="flex items-center gap-3">
                  <src.icon className="h-5 w-5 text-cyan" />
                  <div>
                    <p className="font-mono text-sm font-medium text-bright">{src.label}</p>
                    <p className="font-body text-xs text-muted">{src.desc}</p>
                  </div>
                </div>
                {src.field}
                <button onClick={() => handleImport(src.id)} disabled={importing === src.id}
                  className={clsx('flex items-center gap-2 rounded-lg border px-4 py-2 font-mono text-xs font-medium transition-all disabled:opacity-50', src.color)}>
                  {importing === src.id
                    ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Importing…</>
                    : <><Upload className="h-3.5 w-3.5" /> Import</>
                  }
                </button>
              </div>
            ))}
            {importResult && (
              <div className={clsx('rounded-xl border p-4', importResult.error ? 'border-red/30 bg-red/5' : 'border-green/30 bg-green/5')}>
                <pre className="font-mono text-xs text-text whitespace-pre-wrap">{JSON.stringify(importResult, null, 2)}</pre>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="mx-auto max-w-4xl">
            <div className="mb-3 flex items-center gap-3">
              <Brain className="h-4 w-4 text-purple" />
              <span className="font-mono text-xs text-subtle">
                {tab === 'search' ? `${results.length} results for "${query}"` : `${timeline.length} memories (72h)`}
              </span>
            </div>
            {loadingTimeline && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-purple" /></div>}
            <div className="space-y-2">
              {displayNodes.map((node: any, i: number) => (
                <div key={node.id ?? i} className="flex gap-4 rounded-xl border border-border bg-panel px-4 py-3 hover:border-purple/30 transition-all">
                  {node.score != null && (
                    <div className="flex flex-col items-center gap-1 pt-0.5">
                      <span className="font-mono text-xs text-purple">{Math.round(node.score * 100)}</span>
                      <div className="h-12 w-0.5 bg-border rounded-full overflow-hidden">
                        <div className="bg-purple rounded-full w-full" style={{ height: `${Math.round(node.score * 100)}%` }} />
                      </div>
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="font-body text-sm text-text leading-relaxed">{node.content}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      {(node.tags ?? []).map((tag: string) => (
                        <span key={tag} className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5">
                          <Tag className="h-3 w-3 text-muted" />
                          <span className="font-mono text-xs text-subtle">{tag}</span>
                        </span>
                      ))}
                      {node.created_at && (
                        <span className="ml-auto font-mono text-xs text-muted">
                          {format(new Date(node.created_at * 1000), 'MMM d, HH:mm')}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {!loadingTimeline && displayNodes.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16 opacity-50">
                <Brain className="h-10 w-10 text-muted mb-3" />
                <p className="font-mono text-sm text-muted">{tab === 'search' ? 'No memories found.' : 'Memory graph is empty.'}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
