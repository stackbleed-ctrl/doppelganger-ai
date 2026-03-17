import { Menu, Volume2, Mic, MicOff } from 'lucide-react'
import { useState } from 'react'
import { useStore } from '../lib/store'
import { speak } from '../lib/api'
import clsx from 'clsx'

interface Props {
  wsSend: (msg: object) => void
}

export function TopBar({ wsSend }: Props) {
  const { toggleSidebar, sidebarOpen, presence, messages } = useStore()
  const [muted, setMuted] = useState(false)

  const lastMsg = messages.filter(m => m.role === 'assistant').at(-1)

  const handleSpeak = async () => {
    if (lastMsg) await speak(lastMsg.text)
  }

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-surface/80 px-4 backdrop-blur">
      <div className="flex items-center gap-3">
        {!sidebarOpen && (
          <button
            onClick={toggleSidebar}
            className="rounded p-1.5 text-muted hover:text-text transition-colors"
          >
            <Menu className="h-4 w-4" />
          </button>
        )}

        {/* Presence indicator */}
        {presence && (
          <div className="flex items-center gap-2 rounded-md border border-border bg-panel px-3 py-1">
            <span className={clsx(
              'h-2 w-2 rounded-full',
              presence.detected ? 'bg-green animate-pulse' : 'bg-muted'
            )} />
            <span className="font-mono text-xs text-subtle capitalize">
              {presence.detected ? presence.activity : 'away'}
            </span>
            <span className="font-mono text-xs text-muted">
              {Math.round(presence.confidence * 100)}%
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        {/* Speak last response */}
        <button
          onClick={handleSpeak}
          disabled={!lastMsg}
          className="rounded-lg border border-border p-2 text-muted hover:text-cyan hover:border-cyan/40 transition-all disabled:opacity-30"
          title="Speak last response"
        >
          <Volume2 className="h-4 w-4" />
        </button>

        {/* Mic toggle */}
        <button
          onClick={() => setMuted(m => !m)}
          className={clsx(
            'rounded-lg border p-2 transition-all',
            muted
              ? 'border-red/40 text-red'
              : 'border-border text-muted hover:text-green hover:border-green/40'
          )}
          title={muted ? 'Unmute mic' : 'Mute mic'}
        >
          {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
        </button>
      </div>
    </header>
  )
}
