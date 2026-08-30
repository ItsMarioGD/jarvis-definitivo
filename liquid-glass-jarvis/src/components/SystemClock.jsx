import { useEffect, useState } from 'react'
import ScrambleText from './ScrambleText'

// Dominant kinetic system clock — massive animated typography hierarchy.
export default function SystemClock() {
  const [time, setTime] = useState('')
  const [date, setDate] = useState('')
  const [uptime, setUptime] = useState(0)

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      setTime(d.toLocaleTimeString('en-GB'))
      setDate(d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase())
    }
    tick()
    const id = setInterval(tick, 1000)
    const up = setInterval(() => setUptime((u) => u + 1), 1000)
    return () => {
      clearInterval(id)
      clearInterval(up)
    }
  }, [])

  const hh = String(Math.floor(uptime / 3600)).padStart(2, '0')
  const mm = String(Math.floor((uptime % 3600) / 60)).padStart(2, '0')
  const ss = String(uptime % 60).padStart(2, '0')

  return (
    <div className="pointer-events-none select-none text-center">
      <div className="text-[11px] uppercase tracking-[0.5em] text-neon-cyan/70">
        <ScrambleText value="J.A.R.V.I.S // CORE TIME" />
      </div>
      <div className="font-mono text-6xl font-extrabold leading-none tracking-tight text-white drop-shadow-[0_0_24px_rgba(33,230,255,0.55)]">
        <ScrambleText value={time} settleMs={500} />
      </div>
      <div className="mt-1 flex items-center justify-center gap-4 text-[11px] uppercase tracking-[0.3em] text-fusion-gold/80">
        <span><ScrambleText value={date} /></span>
        <span className="text-teal-mid/60">UPTIME {hh}:{mm}:{ss}</span>
      </div>
    </div>
  )
}
