import { useState, useRef, useEffect, FormEvent } from 'react'
import { Send, Trash2, Loader2 } from 'lucide-react'
import { useStore } from '../lib/store'
import { streamChat } from '../lib/api'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'

interface Props {
  wsSend: (msg: object) => void
}

export function ChatPage({ wsSend }: Props) {
  const { messages, addMessage, updateLastMessage, clearMessages } = useStore()
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = async (e?: FormEvent) => {
    e?.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setLoading(true)

    addMessage({ id: crypto.randomUUID(), role: 'user', text, ts: Date.now() })

    // Add empty assistant message for streaming
    const assistantId = crypto.randomUUID()
    addMessage({ id: assistantId, role: 'assistant', text: '', ts: Date.now(), streaming: true })

    try {
      for await (const chunk of streamChat(text)) {
        updateLastMessage(chunk)
      }
      updateLastMessage('', true) // mark done
    } catch (err) {
      updateLastMessage(`Error: ${(err as Error).message}`, true)
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 opacity-60">
            <div className="h-16 w-16 rounded-full border border-cyan/30 bg-cyan/5 flex items-center justify-center shadow-glow-cyan">
              <span className="font-mono text-2xl text-cyan">D</span>
            </div>
            <p className="font-display text-lg text-subtle">Your twin is listening.</p>
            <p className="font-mono text-xs text-muted">Type or speak to begin.</p>
          </div>
        )}

        <div className="mx-auto max-w-3xl space-y-4">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-border bg-surface/50 px-6 py-4">
        <div className="mx-auto max-w-3xl">
          <form onSubmit={handleSubmit} className="flex items-end gap-3">
            <div className="relative flex-1">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask your twin anything…"
                rows={1}
                disabled={loading}
                className={clsx(
                  'w-full resize-none rounded-xl border bg-panel px-4 py-3 pr-4',
                  'font-body text-sm text-text placeholder-muted',
                  'focus:outline-none focus:border-cyan/40 focus:shadow-glow-cyan',
                  'border-border transition-all duration-200',
                  'disabled:opacity-50',
                  'max-h-40 overflow-y-auto'
                )}
                style={{ minHeight: '48px' }}
                onInput={(e) => {
                  const t = e.currentTarget
                  t.style.height = 'auto'
                  t.style.height = Math.min(t.scrollHeight, 160) + 'px'
                }}
              />
            </div>

            <button
              type="submit"
              disabled={loading || !input.trim()}
              className={clsx(
                'flex h-12 w-12 items-center justify-center rounded-xl border transition-all duration-200',
                loading || !input.trim()
                  ? 'border-border text-muted opacity-50 cursor-not-allowed'
                  : 'border-cyan/40 text-cyan hover:bg-cyan/10 shadow-glow-cyan'
              )}
            >
              {loading
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <Send className="h-4 w-4" />
              }
            </button>

            {messages.length > 0 && (
              <button
                type="button"
                onClick={clearMessages}
                className="flex h-12 w-12 items-center justify-center rounded-xl border border-border text-muted hover:text-red hover:border-red/40 transition-all"
                title="Clear chat"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </form>
          <p className="mt-2 text-center font-mono text-xs text-muted">
            ↵ Send · Shift+↵ New line · Everything stays local.
          </p>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ msg }: { msg: { id: string; role: string; text: string; ts: number; streaming?: boolean } }) {
  const isUser = msg.role === 'user'

  return (
    <div className={clsx('flex gap-3 animate-slide-up', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div className={clsx(
        'flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border font-mono text-xs font-bold',
        isUser
          ? 'border-purple/40 bg-purple/10 text-purple'
          : 'border-cyan/40 bg-cyan/10 text-cyan'
      )}>
        {isUser ? 'U' : 'D'}
      </div>

      {/* Bubble */}
      <div className={clsx(
        'max-w-[75%] rounded-2xl px-4 py-3',
        isUser
          ? 'bg-purple/10 border border-purple/20 text-text'
          : 'bg-panel border border-border text-text'
      )}>
        <p className="font-body text-sm leading-relaxed whitespace-pre-wrap">
          {msg.text}
          {msg.streaming && <span className="inline-block ml-0.5 cursor" />}
        </p>
        <p className="mt-1 font-mono text-xs text-muted">
          {formatDistanceToNow(new Date(msg.ts), { addSuffix: true })}
        </p>
      </div>
    </div>
  )
}
