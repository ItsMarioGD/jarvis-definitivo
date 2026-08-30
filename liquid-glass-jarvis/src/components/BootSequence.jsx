import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const LINES = [
  '> INICIANDO SECUENCIA DE ARRANQUE...',
  '> NÚCLEO HOLOGRÁFICO .......... [OK]',
  '> ENJAMBRE DE PARTÍCULAS ...... [OK]',
  '> LIQUID GLASS / SHADER FBO ... [OK]',
  '> ABERRACIÓN CROMÁTICA ........ [OK]',
  '> POST-PROCESO CINEMATOGRÁFICO  [OK]',
  '> SISTEMAS OPERATIVOS EN LÍNEA',
]

// Progressive disclosure boot screen (slow-screen redraw, dramatic tension).
export default function BootSequence() {
  const [done, setDone] = useState(false)
  const [visible, setVisible] = useState(0)

  useEffect(() => {
    if (visible >= LINES.length) {
      const t = setTimeout(() => setDone(true), 1100)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => setVisible((v) => v + 1), 320 + Math.random() * 260)
    return () => clearTimeout(t)
  }, [visible])

  return (
    <AnimatePresence>
      {!done && (
        <motion.div
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, filter: 'blur(12px)' }}
          transition={{ duration: 0.9 }}
          className="absolute inset-0 z-[70] flex flex-col items-center justify-center bg-ink"
        >
          <div className="mb-6 text-[12px] uppercase tracking-[0.5em] text-neon-cyan/80 animate-flicker">
            J.A.R.V.I.S // LIQUID GLASS
          </div>
          <div className="w-[420px] max-w-[80vw] space-y-1 font-mono text-[12px] text-teal-mid/90">
            {LINES.slice(0, visible).map((l, i) => (
              <div key={i} className="drop-shadow-[0_0_8px_rgba(33,230,255,0.4)]">
                {l}
                {i === LINES.length - 1 && visible === LINES.length && (
                  <span className="laser-caret" />
                )}
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
