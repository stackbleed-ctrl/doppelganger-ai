import { useState, useEffect } from 'react'
import { Search, Plus, Clock, Tag, Loader2, Brain } from 'lucide-react'
import { useStore } from '../lib/store'
import { searchMemory, getMemoryTimeline, storeMemory } from '../lib/api'
import clsx from 'clsx'
import { format } from 'date-fns'

export function MemoryPage() {
  const { memories, setMemories } = useStore()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)
  const [newMemory, setNewMemory] = useState('')
  const [storing, setStoring] = useState(false)
  const [view, setView] = useState<'search' | 'timeline'>('timeline')
  const [timeline, setTimeline] = useState<any[]>([])
  const [loadingTimeline, setLoadingTimeline] = useState(false)

  useEffect(() => {
    loadTimeline()
  }, [])

  const loadTimeline = async () => {
    setLoadingTimeline(true)
    try {
      const data = await getMemoryTimeline(72)
      setTimeline(data.nodes)
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingTimeline(false)
    }
  }

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const data = await searchMemory(query, 10)
      setResults(data.results)
      setView('search')
    } catch (e) {
      console.error(e)
    } finally {
      setSearching(false)
    }
  }

  const handleStore = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newMemory.trim()) return
    setStoring(true)
    try {
      await storeMemory(newMemory, ['manual'])
      setNewMemory('')
      setTimeout(loadTimeline, 500)
    } catch (e) {
      console.error(e)
    } finally {
      setStoring(false)
    }
  }

  const displayNodes = view === 'search' ? results : timeline

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border bg-surface/50 px-6 py-4">
        <div className="mx-auto max-w-4xl space-y-3">
          {/* Search */}
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search your memory graph…"
                className="w-full rounded-lg border border-border bg-panel py-2.5 pl-10 pr-4 font-body text-sm text-text placeholder-muted focus:border-purple/40 focus:outline-none transition-colors"
              />
            </div>
            <button
              type="submit"
              disabled={searching}
              className="flex items-center gap-2 rounded-lg border border-purple/40 bg-purple/10 px-4 py-2 text-sm font-medium text-purple hover:bg-purple/20 transition-all disabled:opacity-50"
            >
              {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Search
            </button>
            <button
              type="button"
              onClick={() => { setView('timeline'); setResults([]) }}
              className={clsx(
                'rounded-lg border px-4 py-2 text-sm font-medium transition-all',
                view === 'timeline'
                  ? 'border-cyan/40 text-cyan bg-cyan/10'
                  : 'border-border text-muted hover:text-text'
              )}
            >
              <Clock className="h-4 w-4" />
            </button>
          </form>

          {/* Store new memory */}
          <form onSubmit={handleStore} className="flex gap-2">
            <input
              value={newMemory}
              onChange={e => setNewMemory(e.target.value)}
              placeholder="Store a new memory…"
              className="flex-1 rounded-lg border border-border bg-panel py-2 px-4 font-body text-sm text-text placeholder-muted focus:border-green/40 focus:outline-none transition-colors"
            />
            <button
              type="submit"
              disabled={storing || !newMemory.trim()}
              className="flex items-center gap-2 rounded-lg border border-green/40 bg-green/10 px-3 py-2 text-sm font-medium text-green hover:bg-green/20 transition-all disabled:opacity-50"
            >
              {storing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            </button>
          </form>
        </div>
      </div>

      {/* Memory list */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-4xl">
          {/* Stats bar */}
          <div className="mb-4 flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-purple" />
              <span className="font-mono text-xs text-subtle">
                {view === 'timeline' ? `${timeline.length} memories (72h)` : `${results.length} results`}
              </span>
            </div>
          </div>

          {loadingTimeline && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-purple" />
            </div>
          )}

          <div className="space-y-2">
            {displayNodes.map((node: any, i: number) => (
              <MemoryCard key={node.id ?? i} node={node} />
            ))}
          </div>

          {!loadingTimeline && displayNodes.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 opacity-50">
              <Brain className="h-10 w-10 text-muted mb-3" />
              <p className="font-mono text-sm text-muted">
                {view === 'search' ? 'No memories found.' : 'Memory graph is empty.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function MemoryCard({ node }: { node: any }) {
  const score = node.score != null ? Math.round(node.score * 100) : null

  return (
    <div className="group flex gap-4 rounded-xl border border-border bg-panel px-4 py-3 hover:border-purple/30 transition-all animate-fade-in">
      {/* Score / relevance bar */}
      {score != null && (
        <div className="flex flex-col items-center gap-1 pt-0.5">
          <span className="font-mono text-xs text-purple">{score}</span>
          <div className="h-12 w-0.5 bg-border rounded-full overflow-hidden">
            <div
              className="bg-purple rounded-full w-full"
              style={{ height: `${score}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex-1 min-w-0">
        <p className="font-body text-sm text-text leading-relaxed">{node.content}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {/* Tags */}
          {(node.tags ?? []).map((tag: string) => (
            <span key={tag} className="flex items-center gap-1 rounded-md bg-panel border border-border px-2 py-0.5">
              <Tag className="h-3 w-3 text-muted" />
              <span className="font-mono text-xs text-subtle">{tag}</span>
            </span>
          ))}

          {/* Timestamp */}
          {node.created_at && (
            <span className="ml-auto font-mono text-xs text-muted">
              {format(new Date(node.created_at * 1000), 'MMM d, HH:mm')}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
