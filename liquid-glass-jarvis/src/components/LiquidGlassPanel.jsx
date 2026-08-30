import { motion } from 'framer-motion'

// Liquid Glass panel wrapper. Applies offscreen-glass blur, neon gas-flow
// tube border (animated), and chromatic-aberration edge accents.
export default function LiquidGlassPanel({
  children,
  className = '',
  title,
  delay = 0,
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 26, scale: 0.96, rotateX: 6 }}
      animate={{ opacity: 1, y: 0, scale: 1, rotateX: 0 }}
      transition={{ type: 'spring', stiffness: 120, damping: 12, mass: 1.1, delay }}
      className={`glass ${className}`}
    >
      <div className="glass-tube" />
      <div className="aberration-edge" />
      {title && (
        <div className="flex items-center gap-2 px-4 pt-3 pb-2 text-[11px] uppercase tracking-[0.32em] text-neon-cyan/80">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-neon-cyan shadow-[0_0_8px_#21e6ff]" />
          {title}
        </div>
      )}
      <div className="relative px-4 pb-4">{children}</div>
    </motion.div>
  )
}
