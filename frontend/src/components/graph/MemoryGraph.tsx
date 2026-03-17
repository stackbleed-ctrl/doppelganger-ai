import { useEffect, useRef, useState, useCallback } from 'react'
import { Loader2, ZoomIn, ZoomOut, RefreshCw, Search } from 'lucide-react'
import clsx from 'clsx'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface GraphNode {
  id: string
  name: string
  type: string
  size: number
  color: string
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number | null
  fy?: number | null
}

interface GraphLink {
  source: string | GraphNode
  target: string | GraphNode
  relation: string
  weight: number
}

interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

const TYPE_COLORS: Record<string, string> = {
  person:       '#a855f7',
  project:      '#00d4ff',
  technology:   '#00ff94',
  organization: '#ffb800',
  concept:      '#6b8299',
  place:        '#ff6b6b',
  emotion:      '#ff4488',
  date:         '#94a3b8',
  default:      '#3d4f61',
}

async function fetchGraphData(): Promise<GraphData> {
  // Fetch entities and their relationships from the KG
  const [statsRes, timelineRes] = await Promise.all([
    fetch(`${API}/memory/graph/stats`),
    fetch(`${API}/memory/timeline?hours=168`),  // last week
  ])

  const stats = await statsRes.json().catch(() => ({}))
  const timeline = await timelineRes.json().catch(() => ({ nodes: [] }))

  // Build graph from memory nodes
  const nodeMap = new Map<string, GraphNode>()
  const links: GraphLink[] = []

  // Create nodes from memory timeline
  for (const mem of (timeline.nodes || []).slice(0, 80)) {
    const tags: string[] = mem.tags || []
    for (const tag of tags) {
      if (!nodeMap.has(tag) && tag.length > 2) {
        nodeMap.set(tag, {
          id: tag,
          name: tag,
          type: 'concept',
          size: 6,
          color: TYPE_COLORS.concept,
        })
      }
    }
    // Link tags that co-appear
    for (let i = 0; i < tags.length; i++) {
      for (let j = i + 1; j < tags.length; j++) {
        if (tags[i].length > 2 && tags[j].length > 2) {
          links.push({
            source: tags[i],
            target: tags[j],
            relation: 'co-occurs',
            weight: 0.5,
          })
        }
      }
    }
  }

  // Boost size for frequently appearing nodes
  const freq = new Map<string, number>()
  for (const link of links) {
    const s = link.source as string
    const t = link.target as string
    freq.set(s, (freq.get(s) || 0) + 1)
    freq.set(t, (freq.get(t) || 0) + 1)
  }
  for (const [id, node] of nodeMap) {
    node.size = Math.min(4 + (freq.get(id) || 0) * 1.5, 20)
  }

  return {
    nodes: Array.from(nodeMap.values()),
    links: links.slice(0, 200),
  }
}

export function MemoryGraph() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [search, setSearch] = useState('')
  const [hovering, setHovering] = useState<GraphNode | null>(null)
  const animRef = useRef<number>()
  const nodesRef = useRef<GraphNode[]>([])
  const linksRef = useRef<GraphLink[]>([])
  const isDragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const dragNode = useRef<GraphNode | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchGraphData()
      // Initialize positions
      const w = canvasRef.current?.width || 800
      const h = canvasRef.current?.height || 600
      data.nodes.forEach((n, i) => {
        n.x = w / 2 + (Math.random() - 0.5) * 300
        n.y = h / 2 + (Math.random() - 0.5) * 300
        n.vx = 0; n.vy = 0; n.fx = null; n.fy = null
      })
      nodesRef.current = data.nodes
      linksRef.current = data.links
      setGraphData(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Force simulation
  useEffect(() => {
    if (!graphData) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!

    const simulate = () => {
      const nodes = nodesRef.current
      const links = linksRef.current
      const w = canvas.width
      const h = canvas.height

      // Build adjacency for link forces
      const linkMap = new Map<string, string[]>()
      for (const link of links) {
        const s = typeof link.source === 'string' ? link.source : link.source.id
        const t = typeof link.target === 'string' ? link.target : link.target.id
        if (!linkMap.has(s)) linkMap.set(s, [])
        if (!linkMap.has(t)) linkMap.set(t, [])
        linkMap.get(s)!.push(t)
        linkMap.get(t)!.push(s)
      }

      const nodeById = new Map(nodes.map(n => [n.id, n]))

      // Apply forces
      for (const n of nodes) {
        if (n.fx != null) { n.x = n.fx; n.vx = 0 }
        if (n.fy != null) { n.y = n.fy; n.vy = 0 }

        // Center gravity
        n.vx! += (w / 2 - n.x!) * 0.002
        n.vy! += (h / 2 - n.y!) * 0.002

        // Repulsion from all other nodes
        for (const m of nodes) {
          if (m.id === n.id) continue
          const dx = n.x! - m.x!
          const dy = n.y! - m.y!
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const force = 800 / (dist * dist)
          n.vx! += (dx / dist) * force
          n.vy! += (dy / dist) * force
        }

        // Attraction along links
        for (const neighborId of (linkMap.get(n.id) || [])) {
          const m = nodeById.get(neighborId)
          if (!m) continue
          const dx = m.x! - n.x!
          const dy = m.y! - n.y!
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const target = 120
          const force = (dist - target) * 0.03
          n.vx! += (dx / dist) * force
          n.vy! += (dy / dist) * force
        }

        // Damping
        n.vx! *= 0.85
        n.vy! *= 0.85

        if (n.fx == null) n.x! += n.vx!
        if (n.fy == null) n.y! += n.vy!

        // Boundary
        n.x = Math.max(20, Math.min(w - 20, n.x!))
        n.y = Math.max(20, Math.min(h - 20, n.y!))
      }

      // Draw
      ctx.clearRect(0, 0, w, h)
      ctx.save()
      ctx.translate(offset.x, offset.y)
      ctx.scale(zoom, zoom)

      // Draw links
      for (const link of links) {
        const s = typeof link.source === 'string' ? nodeById.get(link.source) : link.source as GraphNode
        const t = typeof link.target === 'string' ? nodeById.get(link.target) : link.target as GraphNode
        if (!s || !t) continue
        const isHighlighted = selected && (s.id === selected.id || t.id === selected.id)
        ctx.beginPath()
        ctx.moveTo(s.x!, s.y!)
        ctx.lineTo(t.x!, t.y!)
        ctx.strokeStyle = isHighlighted ? '#00d4ff44' : '#1e283288'
        ctx.lineWidth = isHighlighted ? 1.5 : 0.5
        ctx.stroke()
      }

      // Draw nodes
      for (const node of nodes) {
        const isSelected = selected?.id === node.id
        const isHovered = hovering?.id === node.id
        const inSearch = search && node.name.toLowerCase().includes(search.toLowerCase())
        const r = node.size + (isSelected || isHovered ? 4 : 0)

        // Glow
        if (isSelected || isHovered || inSearch) {
          ctx.beginPath()
          ctx.arc(node.x!, node.y!, r + 6, 0, Math.PI * 2)
          ctx.fillStyle = node.color + '22'
          ctx.fill()
        }

        // Node circle
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, r, 0, Math.PI * 2)
        ctx.fillStyle = isSelected || inSearch ? node.color : node.color + 'bb'
        ctx.fill()
        ctx.strokeStyle = isSelected ? node.color : '#1e2832'
        ctx.lineWidth = isSelected ? 2 : 1
        ctx.stroke()

        // Label
        if (isSelected || isHovered || inSearch || node.size > 10) {
          ctx.fillStyle = '#c9d8e8'
          ctx.font = `${isSelected ? 600 : 400} ${Math.max(9, node.size * 0.9)}px "JetBrains Mono", monospace`
          ctx.textAlign = 'center'
          ctx.fillText(node.name, node.x!, node.y! + r + 12)
        }
      }

      ctx.restore()
      animRef.current = requestAnimationFrame(simulate)
    }

    animRef.current = requestAnimationFrame(simulate)
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current) }
  }, [graphData, zoom, offset, selected, hovering, search])

  // Mouse interaction
  const getNodeAt = (cx: number, cy: number): GraphNode | null => {
    const nodes = nodesRef.current
    const wx = (cx - offset.x) / zoom
    const wy = (cy - offset.y) / zoom
    for (const n of nodes) {
      const dx = wx - n.x!, dy = wy - n.y!
      if (Math.sqrt(dx * dx + dy * dy) < n.size + 4) return n
    }
    return null
  }

  const onMouseDown = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect()
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top
    const node = getNodeAt(cx, cy)
    if (node) {
      dragNode.current = node
      node.fx = node.x
      node.fy = node.y
    } else {
      isDragging.current = true
      dragStart.current = { x: e.clientX - offset.x, y: e.clientY - offset.y }
    }
  }

  const onMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect()
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top
    if (dragNode.current) {
      dragNode.current.fx = (cx - offset.x) / zoom
      dragNode.current.fy = (cy - offset.y) / zoom
    } else if (isDragging.current) {
      setOffset({ x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y })
    } else {
      setHovering(getNodeAt(cx, cy))
    }
  }

  const onMouseUp = (e: React.MouseEvent) => {
    if (dragNode.current) {
      const rect = canvasRef.current!.getBoundingClientRect()
      const cx = e.clientX - rect.left, cy = e.clientY - rect.top
      const moved = Math.abs(cx - (dragNode.current.fx! * zoom + offset.x)) > 5
      if (!moved) setSelected(dragNode.current)
      dragNode.current.fx = null
      dragNode.current.fy = null
      dragNode.current = null
    }
    isDragging.current = false
  }

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    setZoom(z => Math.max(0.3, Math.min(3, z * (e.deltaY > 0 ? 0.9 : 1.1))))
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-border bg-surface/50 px-4 py-2">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search nodes…"
            className="w-full rounded-lg border border-border bg-panel pl-8 pr-3 py-1.5 font-mono text-xs text-text placeholder-muted focus:border-cyan/40 focus:outline-none"
          />
        </div>
        <button onClick={() => setZoom(z => Math.min(3, z * 1.2))} className="rounded-lg border border-border p-1.5 text-muted hover:text-cyan transition-colors">
          <ZoomIn className="h-3.5 w-3.5" />
        </button>
        <button onClick={() => setZoom(z => Math.max(0.3, z * 0.8))} className="rounded-lg border border-border p-1.5 text-muted hover:text-cyan transition-colors">
          <ZoomOut className="h-3.5 w-3.5" />
        </button>
        <button onClick={load} className="rounded-lg border border-border p-1.5 text-muted hover:text-green transition-colors">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
        {graphData && (
          <span className="font-mono text-xs text-muted ml-auto">
            {graphData.nodes.length} nodes · {graphData.links.length} links
          </span>
        )}
      </div>

      {/* Canvas */}
      <div className="relative flex-1">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-void/80 z-10">
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-cyan" />
              <p className="font-mono text-xs text-subtle">Building memory graph…</p>
            </div>
          </div>
        )}
        <canvas
          ref={canvasRef}
          className="h-full w-full cursor-grab active:cursor-grabbing"
          style={{ cursor: hovering ? 'pointer' : isDragging.current ? 'grabbing' : 'grab' }}
          width={1200}
          height={700}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={() => { isDragging.current = false; dragNode.current = null; setHovering(null) }}
          onWheel={onWheel}
        />

        {/* Selected node panel */}
        {selected && (
          <div className="absolute bottom-4 left-4 w-64 rounded-xl border border-border bg-surface/95 p-4 backdrop-blur">
            <div className="flex items-center gap-2 mb-2">
              <span
                className="h-3 w-3 rounded-full"
                style={{ background: selected.color }}
              />
              <span className="font-mono text-sm font-medium text-bright">{selected.name}</span>
              <button onClick={() => setSelected(null)} className="ml-auto text-muted hover:text-text text-xs">✕</button>
            </div>
            <p className="font-mono text-xs text-muted capitalize">{selected.type}</p>
            <p className="font-mono text-xs text-subtle mt-1">Connections: {selected.size}</p>
          </div>
        )}

        {/* Legend */}
        <div className="absolute top-4 right-4 rounded-xl border border-border bg-surface/90 p-3 backdrop-blur">
          <p className="font-mono text-xs text-muted mb-2">ENTITY TYPES</p>
          {Object.entries(TYPE_COLORS).filter(([k]) => k !== 'default').map(([type, color]) => (
            <div key={type} className="flex items-center gap-2 py-0.5">
              <span className="h-2 w-2 rounded-full" style={{ background: color }} />
              <span className="font-mono text-xs text-subtle capitalize">{type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
