import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";
import { useHud, type HudState } from "../store/hudStore";

/**
 * Iron-Man style Arc Reactor.
 * - Three concentric ring meshes that rotate at speeds driven by `state`.
 * - 60-tick outer ring rendered as a shader-driven line.
 * - Glowing core (icosahedron) pulses with `pulse` driven by audioLevel.
 * - Bloom post-processing for the neon halo.
 */

const STATE_PALETTE: Record<HudState, { color: THREE.Color; speed: number; intensity: number }> = {
  idle:       { color: new THREE.Color("#00F0FF"), speed: 0.6, intensity: 1.0 },
  listening:  { color: new THREE.Color("#FFB800"), speed: 1.4, intensity: 1.4 },
  processing: { color: new THREE.Color("#FF00FF"), speed: 2.4, intensity: 1.6 },
  speaking:   { color: new THREE.Color("#00FF88"), speed: 1.0, intensity: 1.2 },
  remote:     { color: new THREE.Color("#B8860B"), speed: 1.6, intensity: 1.3 },
  error:      { color: new THREE.Color("#FF3366"), speed: 3.0, intensity: 1.8 },
};

function ReactorRings({ state, audioLevel }: { state: HudState; audioLevel: number }) {
  const group = useRef<THREE.Group>(null!);
  const inner = useRef<THREE.Group>(null!);
  const core  = useRef<THREE.Mesh>(null!);
  const matA  = useRef<THREE.MeshBasicMaterial>(null!);
  const matB  = useRef<THREE.MeshBasicMaterial>(null!);
  const matC  = useRef<THREE.MeshBasicMaterial>(null!);

  const palette = useMemo(() => STATE_PALETTE[state], [state]);

  // Outer 60-tick ring (geometry precomputed once)
  const ticksGeom = useMemo(() => {
    const positions: number[] = [];
    const colors:    number[] = [];
    const radius = 1.62;
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2;
      const major = i % 5 === 0;
      const inner = major ? radius - 0.16 : radius - 0.08;
      const outer = radius;
      const ca = Math.cos(a), sa = Math.sin(a);
      positions.push(ca * inner, sa * inner, 0, ca * outer, sa * outer, 0);
      const c = major ? 1.0 : 0.45;
      colors.push(c, c, c, c, c, c);
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geom.setAttribute("color",    new THREE.Float32BufferAttribute(colors, 3));
    return geom;
  }, []);

  useFrame((_, dt) => {
    if (!group.current) return;
    group.current.rotation.z += dt * palette.speed * 0.35;
    if (inner.current) {
      inner.current.rotation.z -= dt * palette.speed * 1.1;
      inner.current.rotation.x += dt * palette.speed * 0.05;
    }
    if (core.current) {
      const k = 1 + audioLevel * 0.6;
      core.current.scale.setScalar(k);
      const m = core.current.material as THREE.MeshBasicMaterial;
      m.opacity = 0.7 + audioLevel * 0.3;
    }
    const t = palette.color;
    if (matA.current) matA.current.color.copy(t);
    if (matB.current) matB.current.color.copy(t);
    if (matC.current) matC.current.color.copy(t);
  });

  return (
    <group ref={group}>
      {/* outer ticks */}
      <lineSegments geometry={ticksGeom}>
        <lineBasicMaterial color={palette.color} transparent opacity={0.95} linewidth={1} />
      </lineSegments>

      {/* outer ring */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.4, 0.04, 16, 128]} />
        <meshBasicMaterial ref={matA} color={palette.color} toneMapped={false} />
      </mesh>

      {/* rotating mid assembly */}
      <group ref={inner}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[1.05, 0.025, 12, 96]} />
          <meshBasicMaterial ref={matB} color={palette.color} toneMapped={false} />
        </mesh>
        {/* orbiting nodes */}
        {Array.from({ length: 8 }).map((_, i) => {
          const a = (i / 8) * Math.PI * 2;
          return (
            <mesh key={i} position={[Math.cos(a) * 1.05, Math.sin(a) * 1.05, 0]}>
              <sphereGeometry args={[0.06, 16, 16]} />
              <meshBasicMaterial color={palette.color} toneMapped={false} />
            </mesh>
          );
        })}
        {/* inner thin ring */}
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.78, 0.018, 12, 96]} />
          <meshBasicMaterial color={palette.color} toneMapped={false} />
        </mesh>
      </group>

      {/* glowing core */}
      <mesh ref={core}>
        <icosahedronGeometry args={[0.45, 1]} />
        <meshBasicMaterial ref={matC} color={palette.color} transparent opacity={0.9} toneMapped={false} />
      </mesh>
      {/* soft halo */}
      <mesh>
        <sphereGeometry args={[0.7, 32, 32]} />
        <meshBasicMaterial color={palette.color} transparent opacity={0.08} toneMapped={false} />
      </mesh>
    </group>
  );
}

function ParticleField() {
  const ref = useRef<THREE.Points>(null!);
  const geom = useMemo(() => {
    const N = 800;
    const pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const r = 2.2 + Math.random() * 4;
      const t = Math.random() * Math.PI * 2;
      const p = (Math.random() - 0.5) * Math.PI;
      pos[i * 3]     = r * Math.cos(t) * Math.cos(p);
      pos[i * 3 + 1] = r * Math.sin(t) * Math.cos(p);
      pos[i * 3 + 2] = r * Math.sin(p);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return g;
  }, []);

  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.03;
  });

  return (
    <points ref={ref} geometry={geom}>
      <pointsMaterial size={0.018} color="#00F0FF" transparent opacity={0.45} sizeAttenuation />
    </points>
  );
}

export default function ArcReactor() {
  const state      = useHud((s) => s.state);
  const audioLevel = useHud((s) => s.audioLevel);

  return (
    <div className="relative w-full h-full select-none">
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0, 0, 4.2], fov: 45 }}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        style={{ background: "transparent" }}
      >
        <ambientLight intensity={0.25} />
        <ReactorRings state={state} audioLevel={audioLevel} />
        <ParticleField />
        <EffectComposer>
          <Bloom intensity={1.1} luminanceThreshold={0.15} luminanceSmoothing={0.4} mipmapBlur />
        </EffectComposer>
      </Canvas>

      {/* State caption overlay */}
      <div className="absolute inset-x-0 bottom-4 flex justify-center pointer-events-none">
        <div
          className={[
            "px-4 py-1 rounded-full glass hud-corners font-mono text-xs uppercase tracking-[0.4em]",
            "text-glow-cyan",
          ].join(" ")}
        >
          <span className="opacity-70">Núcleo ::</span>&nbsp;
          <span className={
            state === "idle" ? "text-hud-cyan" :
            state === "listening" ? "text-hud-warn" :
            state === "processing" ? "text-hud-proc" :
            state === "speaking" ? "text-hud-ok" :
            state === "remote" ? "text-hud-amber" : "text-hud-err"
          }>{state}</span>
        </div>
      </div>
    </div>
  );
}
