import { useEffect, useState } from 'react'
import ScrambleText from './ScrambleText'
import LiquidGlassPanel from './LiquidGlassPanel'

// Telemetry module: fluid-dynamics oscillators (liquid fill) instead of linear bars.
export default function Telemetry() {
  const [cpu, setCpu] = useState(34)
  const [gpu, setGpu] = useState(58)
  const [ram, setRam] = useState(62)
  const [net, setNet] = useState(12)

  useEffect(() => {
    const id = setInterval(() => {
      setCpu(20 + Math.random() * 70)
      setGpu(35 + Math.random() * 55)
      setRam(45 + Math.random() * 45)
      setNet(4 + Math.random() * 60)
    }, 2200)
    return () => clearInterval(id)
  }, [])

  return (
    <LiquidGlassPanel title="Telemetría // Rendimiento" className="w-[300px]" delay={0.15}>
      <div className="space-y-4">
        <FluidBar label="CPU CORE" value={cpu} color="#21e6ff" />
        <FluidBar label="GPU TENSOR" value={gpu} color="#1f6bff" />
        <FluidBar label="NET LATENCY" value={net} color="#ff7a18" unit="ms" />

        <div className="flex items-end gap-4 pt-1">
          <div className="flex flex-col items-center">
            <div className="liquid-cyl">
              <div className="heat-haze" />
              <div className="liquid-fill" style={{ height: `${ram}%` }}>
                <div className="liquid-surface" />
              </div>
            </div>
            <span className="mt-2 text-[10px] uppercase tracking-widest text-neon-cyan/70">
              RAM
            </span>
          </div>
          <div className="flex-1 space-y-1 text-[11px] text-teal-mid/80">
            <div className="flex justify-between">
              <span>MEM ALLOC</span>
              <ScrambleText value={`${Math.round(ram * 0.64)}GB`} />
            </div>
            <div className="flex justify-between">
              <span>SWAP</span>
              <ScrambleText value={`${Math.round(ram * 0.12)}GB`} />
            </div>
            <div className="flex justify-between">
              <span>IOR GLASS</span>
              <ScrambleText value="1.52" />
            </div>
          </div>
        </div>
      </div>
    </LiquidGlassPanel>
  )
}

function FluidBar({ label, value, color, unit = '%' }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px] uppercase tracking-widest text-teal-mid/80">
        <span>{label}</span>
        <ScrambleText value={`${Math.round(value)}${unit}`} />
      </div>
      <div className="relative h-3 w-full overflow-hidden rounded-full bg-teal-shadow/60 shadow-inner">
        <div
          className="absolute inset-y-0 left-0 transition-[width] duration-[1100ms] ease-out"
          style={{
            width: `${value}%`,
            background: `linear-gradient(90deg, ${color}aa, ${color})`,
            boxShadow: `0 0 14px ${color}`,
          }}
        />
        <div
          className="absolute top-0 h-full w-2 blur-sm"
          style={{ left: `calc(${value}% - 8px)`, background: '#fff', opacity: 0.5 }}
        />
      </div>
    </div>
  )
}
