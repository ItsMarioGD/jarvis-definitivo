import { useEffect, useRef, useState } from 'react'

const GLYPHS = '0123456789ABCDEF<>/\\[]{}=+*#@%&$ΩΔΣΦΨλβξ◊¤'
const SCRAMBLE_CHARS = 'ABCDEF0123456789ΩΔΣΦΨλβξ◊#@%'

// Kinetic typography with cryptographic "scrambling" decoherence before settle.
export default function ScrambleText({
  value,
  className = '',
  speed = 28,
  settleMs = 650,
  glow = true,
}) {
  const [display, setDisplay] = useState(String(value))
  const frame = useRef(0)
  const raf = useRef(0)

  useEffect(() => {
    const target = String(value)
    const start = performance.now()
    cancelAnimationFrame(raf.current)

    const tick = (now) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / settleMs, 1)
      // number of revealed (locked) characters grows with progress
      const locked = Math.floor(progress * target.length)
      let out = ''
      for (let i = 0; i < target.length; i++) {
        if (i < locked || target[i] === ' ') {
          out += target[i]
        } else {
          out += SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)]
        }
      }
      setDisplay(out)
      if (progress < 1) {
        raf.current = requestAnimationFrame(tick)
      } else {
        setDisplay(target)
      }
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [value, settleMs])

  return (
    <span className={`${className} ${glow ? 'text-shadow-[0_0_14px_rgba(33,230,255,0.55)]' : ''}`}>
      {display}
    </span>
  )
}
