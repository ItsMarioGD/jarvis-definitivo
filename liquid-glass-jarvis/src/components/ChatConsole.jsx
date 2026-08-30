import { useEffect, useRef, useState } from 'react'
import ScrambleText from './ScrambleText'
import LiquidGlassPanel from './LiquidGlassPanel'

const JARVIS_REPLIES = [
  'Sistemas operativos en línea. Núcleo estabilizado al 100%.',
  'Refracción óptica recalibrada. Aberración cromática dentro de parámetros.',
  'Telemetría de red óptima. Latencia sub-umbral detectada.',
  'Protocolo de seguridad reforzado. Acceso concedido, comandante.',
  'Simulación de fluido plasmático sincronizada con su tono de voz.',
]

// Conversational interface: slow-screen redraw typing, laser caret, sparks.
export default function ChatConsole({ onSend }) {
  const [messages, setMessages] = useState([
    { from: 'jarvis', text: 'Buenos días. J.A.R.V.I.S. a su servicio. // LIQUID GLASS ONLINE' },
  ])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState('')
  const [sparks, setSparks] = useState([])
  const scrollRef = useRef(null)
  const sparkId = useRef(0)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, typing])

  // Slow-screen redraw: type out JARVIS replies char by char.
  useEffect(() => {
    if (!typing) return
    const last = messages[messages.length - 1]
    if (last?.from !== 'jarvis' || last.typed) return
    let i = last.shown || 0
    const id = setInterval(() => {
      i++
      setMessages((m) => {
        const copy = [...m]
        copy[copy.length - 1] = { ...copy[copy.length - 1], shown: i }
        return copy
      })
      if (i >= last.text.length) {
        clearInterval(id)
        setMessages((m) => {
          const copy = [...m]
          copy[copy.length - 1] = { ...copy[copy.length - 1], typed: true }
          return copy
        })
        setTyping('')
      }
    }, 18)
    return () => clearInterval(id)
  }, [messages, typing])

  const emitSpark = () => {
    const id = sparkId.current++
    const x = 20 + Math.random() * 60
    const ang = Math.random() * Math.PI - Math.PI
    setSparks((s) => [...s, { id, x, dx: Math.cos(ang) * 40, dy: -Math.abs(Math.sin(ang)) * 50 - 20 }])
    setTimeout(() => setSparks((s) => s.filter((p) => p.id !== id)), 900)
  }

  const send = (e) => {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setMessages((m) => [...m, { from: 'user', text }])
    setInput('')
    onSend?.(text)
    setTimeout(() => {
      const reply = JARVIS_REPLIES[Math.floor(Math.random() * JARVIS_REPLIES.length)]
      setMessages((m) => [...m, { from: 'jarvis', text: reply, shown: 0 }])
      setTyping('pending')
    }, 400)
  }

  return (
    <LiquidGlassPanel title="Conversación // Lógica" className="w-[360px]" delay={0.3}>
      <div
        ref={scrollRef}
        className="relative h-[230px] overflow-y-auto rounded-xl bg-black/30 p-3 text-[12px] leading-relaxed"
      >
        {messages.map((m, idx) => {
          const shownText = m.from === 'jarvis' && !m.typed ? m.text.slice(0, m.shown || 0) : m.text
          return (
            <div key={idx} className={`mb-2 ${m.from === 'user' ? 'text-right' : 'text-left'}`}>
              <span
                className={
                  m.from === 'user'
                    ? 'text-fusion-gold/90'
                    : 'text-neon-cyan drop-shadow-[0_0_8px_rgba(33,230,255,0.5)]'
                }
              >
                <span className="opacity-50">{m.from === 'user' ? 'OPERADOR › ' : 'J.A.R.V.I.S. › '}</span>
                {m.from === 'jarvis' ? shownText : m.text}
                {m.from === 'jarvis' && !m.typed && <span className="laser-caret" />}
              </span>
            </div>
          )
        })}

        {/* welding-spark particles on keystroke */}
        {sparks.map((s) => (
          <span
            key={s.id}
            className="pointer-events-none absolute bottom-2 h-1 w-1 rounded-full bg-white shadow-[0_0_6px_#21e6ff]"
            style={{
              left: `${s.x}%`,
              animation: `sparkfly 0.9s ease-out forwards`,
              ['--dx']: `${s.dx}px`,
              ['--dy']: `${s.dy}px`,
            }}
          />
        ))}
      </div>

      <form onSubmit={send} className="mt-3 flex items-center gap-2">
        <span className="text-neon-cyan/70">›</span>
        <input
          value={input}
          onChange={(e) => {
            setInput(e.target.value)
            if (e.target.value) emitSpark()
          }}
          placeholder="Emita un comando..."
          className="flex-1 rounded-lg border border-neon-cyan/30 bg-black/40 px-3 py-2 text-[12px] text-teal-mid outline-none focus:border-neon-cyan/70 focus:shadow-[0_0_12px_rgba(33,230,255,0.4)]"
          style={{ caretColor: '#21e6ff' }}
        />
        <button
          type="submit"
          className="rounded-lg border border-fusion-orange/50 bg-fusion-orange/10 px-3 py-2 text-[11px] uppercase tracking-widest text-fusion-gold transition hover:bg-fusion-orange/20 hover:shadow-[0_0_14px_rgba(255,122,24,0.5)]"
        >
          Send
        </button>
      </form>
    </LiquidGlassPanel>
  )
}
