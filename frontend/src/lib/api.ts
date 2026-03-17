const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

// ─── Chat ─────────────────────────────────────────────────────────────────

export async function sendChat(message: string, context = {}): Promise<{ task_id: string; response: string }> {
  return req('/chat', { method: 'POST', body: JSON.stringify({ message, context }) })
}

export async function* streamChat(message: string): AsyncGenerator<string> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, stream: true }),
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = JSON.parse(line.slice(6))
      if (data.text) yield data.text
      if (data.done) return
    }
  }
}

// ─── Memory ───────────────────────────────────────────────────────────────

export async function searchMemory(query: string, limit = 8, tags?: string[]) {
  return req<{ results: any[]; query: string }>('/memory/search', {
    method: 'POST',
    body: JSON.stringify({ query, limit, tags }),
  })
}

export async function storeMemory(content: string, tags: string[] = [], entity_type = 'fact') {
  return req<{ id: string; stored: boolean }>('/memory/store', {
    method: 'POST',
    body: JSON.stringify({ content, tags, entity_type }),
  })
}

export async function getMemoryTimeline(hours = 24) {
  return req<{ nodes: any[] }>(`/memory/timeline?hours=${hours}`)
}

// ─── Reasoning ────────────────────────────────────────────────────────────

export async function runSimulation(scenario: string, steps = 4, n_worlds = 3) {
  return req<any>('/reasoning/simulate', {
    method: 'POST',
    body: JSON.stringify({ scenario, steps, n_worlds }),
  })
}

export async function runPlan(goal: string) {
  return req<any>(`/reasoning/plan?goal=${encodeURIComponent(goal)}`, { method: 'POST' })
}

// ─── Perception ───────────────────────────────────────────────────────────

export async function getPresence() {
  return req<any>('/perception/presence')
}

// ─── Skills ───────────────────────────────────────────────────────────────

export async function listSkills() {
  return req<{ skills: any[] }>('/skills')
}

export async function runSkill(name: string, params: Record<string, any>) {
  return req<any>(`/skills/${name}/run`, { method: 'POST', body: JSON.stringify(params) })
}

// ─── Health ───────────────────────────────────────────────────────────────

export async function getHealth() {
  return req<any>('/health')
}

// ─── Voice ────────────────────────────────────────────────────────────────

export async function speak(text: string) {
  return req<any>(`/voice/speak?text=${encodeURIComponent(text)}`, { method: 'POST' })
}
