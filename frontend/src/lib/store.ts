import { create } from 'zustand'

// ─── Types ────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  ts: number
  streaming?: boolean
}

export interface MemoryNode {
  id: string
  content: string
  tags: string[]
  source: string
  created_at: number
  score?: number
}

export interface PresenceState {
  detected: boolean
  activity: string
  confidence: number
  last_seen: number
}

export interface SystemHealth {
  status: string
  uptime_sec: number
  layers: Record<string, any>
}

export interface SimWorld {
  outcome: string
  utility_score: number
  steps: number
}

export interface SimResult {
  scenario: string
  best_action: string
  synthesis: string
  confidence: number
  elapsed_sec: number
  worlds: SimWorld[]
}

export interface Skill {
  name: string
  description: string
  version: string
  parameters: Record<string, any>
}

// ─── Store ────────────────────────────────────────────────────────────────

interface AppState {
  // Chat
  messages: ChatMessage[]
  addMessage: (msg: ChatMessage) => void
  updateLastMessage: (text: string, done?: boolean) => void
  clearMessages: () => void

  // Memory
  memories: MemoryNode[]
  setMemories: (nodes: MemoryNode[]) => void
  addMemory: (node: MemoryNode) => void

  // Presence
  presence: PresenceState | null
  setPresence: (p: PresenceState) => void

  // Health
  health: SystemHealth | null
  setHealth: (h: SystemHealth) => void

  // Simulation
  simResult: SimResult | null
  simLoading: boolean
  setSimResult: (r: SimResult | null) => void
  setSimLoading: (v: boolean) => void

  // Skills
  skills: Skill[]
  setSkills: (s: Skill[]) => void

  // UI
  activeTab: 'chat' | 'memory' | 'sim' | 'skills' | 'perception'
  setActiveTab: (t: AppState['activeTab']) => void
  sidebarOpen: boolean
  toggleSidebar: () => void

  // WebSocket
  wsConnected: boolean
  setWsConnected: (v: boolean) => void
}

export const useStore = create<AppState>((set, get) => ({
  // Chat
  messages: [],
  addMessage: (msg) => set(s => ({ messages: [...s.messages, msg] })),
  updateLastMessage: (text, done = false) => set(s => {
    const msgs = [...s.messages]
    const last = msgs[msgs.length - 1]
    if (last && last.streaming) {
      msgs[msgs.length - 1] = { ...last, text: last.text + text, streaming: !done }
    }
    return { messages: msgs }
  }),
  clearMessages: () => set({ messages: [] }),

  // Memory
  memories: [],
  setMemories: (nodes) => set({ memories: nodes }),
  addMemory: (node) => set(s => ({ memories: [node, ...s.memories].slice(0, 100) })),

  // Presence
  presence: null,
  setPresence: (p) => set({ presence: p }),

  // Health
  health: null,
  setHealth: (h) => set({ health: h }),

  // Simulation
  simResult: null,
  simLoading: false,
  setSimResult: (r) => set({ simResult: r }),
  setSimLoading: (v) => set({ simLoading: v }),

  // Skills
  skills: [],
  setSkills: (s) => set({ skills: s }),

  // UI
  activeTab: 'chat',
  setActiveTab: (t) => set({ activeTab: t }),
  sidebarOpen: true,
  toggleSidebar: () => set(s => ({ sidebarOpen: !s.sidebarOpen })),

  // WebSocket
  wsConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),
}))
