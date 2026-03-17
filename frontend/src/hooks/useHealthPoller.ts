import { useEffect } from 'react'
import { useStore } from '../lib/store'
import { getHealth, getPresence } from '../lib/api'

export function useHealthPoller(intervalMs = 5000) {
  const { setHealth, setPresence } = useStore()

  useEffect(() => {
    let active = true

    const poll = async () => {
      try {
        const [health, presence] = await Promise.all([getHealth(), getPresence()])
        if (!active) return
        setHealth(health)
        setPresence(presence)
      } catch {
        // silently ignore — WS status indicator covers connectivity
      }
    }

    poll()
    const id = setInterval(poll, intervalMs)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [intervalMs, setHealth, setPresence])
}
