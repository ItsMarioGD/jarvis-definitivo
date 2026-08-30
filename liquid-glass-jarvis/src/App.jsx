import { Suspense, useCallback, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import Core from './three/Core'
import PostFX from './three/PostFX'
import SystemClock from './components/SystemClock'
import Telemetry from './components/Telemetry'
import ChatConsole from './components/ChatConsole'
import BootSequence from './components/BootSequence'

export default function App() {
  const [audioLevel, setAudioLevel] = useState(0)
  const [ripples, setRipples] = useState([])
  const rippleId = useRef(0)

  const spawnRipple = useCallback((e) => {
    const id = rippleId.current++
    const x = e.clientX
    const y = e.clientY
    setRipples((r) => [...r, { id, x, y }])
    setTimeout(() => setRipples((r) => r.filter((p) => p.id !== id)), 720)
  }, [])

  // drive the core's "voice energy" with a synthetic pulse
  const pulse = useCallback(() => {
    setAudioLevel(1)
    setTimeout(() => setAudioLevel(0), 600)
  }, [])

  return (
    <div className="relative h-full w-full" onClick={spawnRipple}>
      {/* ---------- WebGL stage ---------- */}
      <Canvas
        className="absolute inset-0"
        dpr={[1, 2]}
        gl={{ antialias: false, powerPreference: 'high-performance' }}
        camera={{ position: [0, 0, 7], fov: 55 }}
      >
        <color attach="background" args={['#02060a']} />
        <fog attach="fog" args={['#02060a', 6, 16]} />
        <Suspense fallback={null}>
          <Core audioLevel={audioLevel} />
        </Suspense>
        <PostFX />
        <OrbitControls
          enablePan={false}
          enableZoom={false}
          autoRotate={false}
          minPolarAngle={Math.PI / 2.4}
          maxPolarAngle={Math.PI / 1.7}
        />
      </Canvas>

      {/* ---------- DOM HUD overlay ---------- */}
      <div className="pointer-events-none absolute inset-0 z-40 flex flex-col">
        <header className="flex items-start justify-between p-6">
          <div className="pointer-events-auto">
            <SystemClock />
          </div>
          <div className="pointer-events-auto mt-2 text-right text-[10px] uppercase tracking-[0.35em] text-teal-mid/60">
            LIQUID GLASS FUI<br />
            <span className="text-fusion-orange/80">NO PERF BOUNDS</span>
          </div>
        </header>

        <main className="flex flex-1 items-center justify-between px-6 pb-8">
          <div className="pointer-events-auto">
            <Telemetry />
          </div>
          <div className="pointer-events-auto">
            <ChatConsole onSend={pulse} />
          </div>
        </main>
      </div>

      {/* ---------- cinematic overlays ---------- */}
      <div className="vignette" />
      <div className="film-grain" />

      {/* ---------- click ripples (liquid reaction) ---------- */}
      {ripples.map((r) => (
        <span key={r.id} className="ripple-ring" style={{ left: r.x, top: r.y }} />
      ))}

      <BootSequence />
    </div>
  )
}
