import { useEffect, useRef, useCallback } from 'react'
import { useStore } from '../lib/store'

const WS_URL = (() => {
  const base = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  return base.replace(/^http/, 'ws') + '/ws'
})()

const RECONNECT_DELAY_MS = 2000
const MAX_RECONNECT_DELAY = 30_000

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectDelay = useRef(RECONNECT_DELAY_MS)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const mounted = useRef(true)

  const { setWsConnected, addMessage, setPresence, addMemory, setSimResult } = useStore()

  const handleMessage = useCallback((raw: string) => {
    try {
      const msg = JSON.parse(raw)

      switch (msg.type) {
        case 'event':
          handleBusEvent(msg.topic, msg.payload)
          break
        case 'chat_ack':
          // task submitted — streaming response will follow via agent.response event
          break
        case 'simulation_result':
          setSimResult(msg)
          break
        case 'memory_results':
          // handled per-request
          break
        case 'pong':
          break
      }
    } catch (e) {
      console.warn('[WS] Parse error:', e)
    }
  }, [])

  const handleBusEvent = useCallback((topic: string, payload: any) => {
    switch (topic) {
      case 'agent.response':
        addMessage({
          id: payload.task_id ?? crypto.randomUUID(),
          role: 'assistant',
          text: payload.text ?? '',
          ts: Date.now(),
        })
        break

      case 'voice.transcript':
        addMessage({
          id: crypto.randomUUID(),
          role: 'user',
          text: `🎙️ ${payload.text}`,
          ts: payload.ts ? payload.ts * 1000 : Date.now(),
        })
        break

      case 'perception.presence_changed':
        setPresence({
          detected: payload.detected,
          activity: payload.activity ?? 'unknown',
          confidence: payload.confidence ?? 0,
          last_seen: payload.ts ? payload.ts * 1000 : Date.now(),
        })
        break

      case 'memory.updated':
        addMemory({
          id: payload.node_id,
          content: payload.content ?? '',
          tags: payload.tags ?? [],
          source: 'live',
          created_at: Date.now() / 1000,
        })
        break

      case 'agent.error':
        addMessage({
          id: payload.task_id ?? crypto.randomUUID(),
          role: 'assistant',
          text: `⚠️ Error: ${payload.error}`,
          ts: Date.now(),
        })
        break
    }
  }, [addMessage, setPresence, addMemory])

  const connect = useCallback(() => {
    if (!mounted.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setWsConnected(true)
      reconnectDelay.current = RECONNECT_DELAY_MS
      // Start heartbeat
      const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }))
        } else {
          clearInterval(ping)
        }
      }, 15_000)
    }

    ws.onmessage = (e) => handleMessage(e.data)

    ws.onerror = () => {
      // onclose will handle reconnect
    }

    ws.onclose = () => {
      setWsConnected(false)
      if (!mounted.current) return
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 1.5, MAX_RECONNECT_DELAY)
        connect()
      }, reconnectDelay.current)
    }
  }, [handleMessage, setWsConnected])

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    connect()
    return () => {
      mounted.current = false
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { send }
}
