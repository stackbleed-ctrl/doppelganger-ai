/**
 * Doppelganger Mobile API Client
 * All requests go to the LAN host — never the internet.
 */

import { create } from 'zustand'

interface ApiConfig {
  host: string
  port: number
  baseUrl: string
}

// Global config store
interface ApiStore {
  config: ApiConfig | null
  setConfig: (host: string, port?: number) => void
  clearConfig: () => void
}

export const useApiConfig = create<ApiStore>((set) => ({
  config: null,
  setConfig: (host, port = 8000) => set({
    config: { host, port, baseUrl: `http://${host}:${port}` }
  }),
  clearConfig: () => set({ config: null }),
}))

function getBaseUrl(): string {
  const config = useApiConfig.getState().config
  if (!config) throw new Error('No Doppelganger host configured')
  return config.baseUrl
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const base = getBaseUrl()
  const res = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

// ─── Health ───────────────────────────────────────────────────────────────────

export const getHealth = () => req<any>('/health')

// ─── Chat ─────────────────────────────────────────────────────────────────────

export const sendChat = (message: string) =>
  req<{ task_id: string; response: string }>('/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  })

export async function* streamChat(message: string): AsyncGenerator<string> {
  const base = getBaseUrl()
  const res = await fetch(`${base}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, stream: true }),
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = JSON.parse(line.slice(6))
      if (data.text) yield data.text
      if (data.done) return
    }
  }
}

// ─── Memory ───────────────────────────────────────────────────────────────────

export const searchMemory = (query: string, limit = 6) =>
  req<{ results: any[] }>('/memory/search', {
    method: 'POST',
    body: JSON.stringify({ query, limit }),
  })

export const storeMemory = (content: string, tags: string[] = []) =>
  req<{ id: string; stored: boolean }>('/memory/store', {
    method: 'POST',
    body: JSON.stringify({ content, tags }),
  })

export const getTimeline = (hours = 24) =>
  req<{ nodes: any[] }>(`/memory/timeline?hours=${hours}`)

// ─── Personas ─────────────────────────────────────────────────────────────────

export const getPersonas = () =>
  req<{ personas: any[]; active_id: string }>('/personas')

export const activatePersona = (id: string) =>
  req<any>(`/personas/${id}/activate`, { method: 'POST' })

// ─── Proactive ────────────────────────────────────────────────────────────────

export const getSuggestions = (limit = 5) =>
  req<{ suggestions: any[] }>(`/proactive/suggestions?limit=${limit}`)

export const dismissSuggestion = (id: string) =>
  req<any>(`/proactive/suggestions/${id}/dismiss`, { method: 'POST' })

// ─── Simulate ─────────────────────────────────────────────────────────────────

export const runSimulation = (scenario: string, worlds = 3, steps = 4) =>
  req<any>('/reasoning/simulate', {
    method: 'POST',
    body: JSON.stringify({ scenario, n_worlds: worlds, steps }),
  })

// ─── Presence ────────────────────────────────────────────────────────────────

export const getPresence = () => req<any>('/perception/presence')

// ─── Calendar ────────────────────────────────────────────────────────────────

export const getCalendarToday = () => req<{ events: any[] }>('/calendar/today')
export const getCalendarContext = () => req<{ context: string }>('/calendar/context')

// ─── Voice ────────────────────────────────────────────────────────────────────

export const speak = (text: string, language = 'en') =>
  req<any>(`/voice/speak?text=${encodeURIComponent(text)}&language=${language}`, { method: 'POST' })
