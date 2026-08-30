import { useMemo, useRef, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { useHud, type HudState } from "../store/hudStore";

const VERTEX_SHADER = `
varying vec2 vUv;
void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FRAGMENT_SHADER = `
precision highp float;
varying vec2 vUv;
uniform vec2 u_resolution;
uniform float u_time;
uniform vec2 u_mouse;
uniform float u_audio;
uniform float u_state; // 0=idle, 1=listening, 2=processing, 3=speaking, 4=remote, 5=error
uniform float u_intensity;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    mat2 rot = mat2(0.8, 0.6, -0.6, 0.8);
    for (int i = 0; i < 5; i++) {
        v += a * noise(p);
        p = rot * p * 2.02 + vec2(0.15);
        a *= 0.5;
    }
    return v;
}

void main() {
    vec2 uv = (vUv - 0.5) * 2.0;

    // Mouse gravitational spacetime deflection
    vec2 mPos = u_mouse * 2.0 - 1.0;
    float mDist = length(uv - mPos);
    uv += normalize(uv - mPos + 0.0001) * (0.012 / (mDist * 6.5 + 0.4));

    float r = length(uv);
    float angle = atan(uv.y, uv.x);
    
    // Event Horizon & Photon Sphere dimensions
    float bhRadius = 0.38;
    float photonRingRadius = 0.42 + u_audio * 0.025;

    // Relativistic coordinate warping
    float warp = 1.0 / (r * 2.5 + 0.22);
    vec2 uvWarp = uv * (1.0 + 0.12 * warp);
    
    // State speeds
    float stateSpeed = (u_state == 2.0 ? 1.7 : (u_state == 1.0 ? 1.3 : (u_state == 3.0 ? 1.4 : 0.85)));
    float rotSpeed = (0.55 + u_audio * 0.45) * stateSpeed;
    float swirl = (1.55 / (pow(r, 1.32) + 0.065)) * rotSpeed;
    float dynamicAngle = angle + swirl * u_time * 0.32;
    vec2 pRot = vec2(cos(dynamicAngle), sin(dynamicAngle)) * r;

    // Multi-stage domain warping for turbulent fiery & icy plumes
    vec2 q = vec2(fbm(pRot * 3.2 + vec2(u_time * 0.07, -u_time * 0.05)),
                  fbm(pRot * 3.2 + vec2(-u_time * 0.05, u_time * 0.06)));
    
    vec2 r_flow = vec2(fbm(pRot * 4.4 + 3.4 * q + vec2(1.7, 4.2) + u_time * 0.09),
                       fbm(pRot * 4.4 + 3.4 * q + vec2(8.3, 1.8) - u_time * 0.08));

    float plasmaFbm = fbm(pRot * 5.0 + 4.0 * r_flow + u_time * 0.11);
    
    // Fine coronal filaments
    float filamentNoise = abs(fbm(pRot * 7.2 + q * 2.4 + u_time * 0.07) * 2.0 - 1.0);
    float filaments = pow(1.0 - filamentNoise, 2.3);

    // Accretion disk radial envelope
    float diskDensity = smoothstep(0.32, 0.48, r) * smoothstep(1.35, 0.45, r);
    float outerNebula = smoothstep(0.35, 0.70, r) * smoothstep(1.85, 0.65, r);

    // Angular partitioning: Fire (Top/Right) vs Cyan/Ice (Bottom/Left)
    float fireBlend = smoothstep(-0.35, 0.55, sin(angle - 0.45) + 0.3 * cos(angle * 1.5));
    fireBlend = clamp(fireBlend + (uv.y > 0.0 ? 0.3 : -0.2), 0.0, 1.0);
    
    // 1. FIRE / CORONA PALETTE (Top/Right)
    vec3 colDeepCrimson = vec3(0.55, 0.05, 0.01);
    vec3 colFireOrange  = vec3(1.0, 0.42, 0.03);
    vec3 colSolarGold   = vec3(1.0, 0.82, 0.22);
    vec3 colIncandescent= vec3(1.0, 0.98, 0.92);
    
    float fireVal = plasmaFbm * 1.25 + filaments * 0.65 + u_audio * 0.3;
    vec3 fireColor = mix(colDeepCrimson, colFireOrange, smoothstep(0.2, 0.6, fireVal));
    fireColor = mix(fireColor, colSolarGold, smoothstep(0.55, 0.85, fireVal));
    fireColor = mix(fireColor, colIncandescent, smoothstep(0.85, 1.25, fireVal));

    // 2. CRYO / CYAN NEBULA PALETTE (Bottom/Left)
    vec3 colDeepSpaceNavy = vec3(0.01, 0.05, 0.20);
    vec3 colSapphireBlue  = vec3(0.02, 0.38, 0.88);
    vec3 colElectricCyan  = vec3(0.05, 0.88, 1.0);
    vec3 colGlacialWhite  = vec3(0.88, 0.98, 1.0);
    
    float cyanVal = plasmaFbm * 1.15 + (1.0 - filamentNoise) * 0.55 + u_audio * 0.25;
    vec3 cyanColor = mix(colDeepSpaceNavy, colSapphireBlue, smoothstep(0.18, 0.55, cyanVal));
    cyanColor = mix(cyanColor, colElectricCyan, smoothstep(0.5, 0.82, cyanVal));
    cyanColor = mix(cyanColor, colGlacialWhite, smoothstep(0.82, 1.2, cyanVal));

    // Blend into base nebula
    vec3 nebulaColor = mix(cyanColor, fireColor, fireBlend);

    // Signature Hotspots matching reference image:
    // Hotspot 1: Top-Right Coronal Solar Flare Burst
    vec2 hs1Pos = vec2(0.22, 0.42);
    float hs1Dist = length(uv - hs1Pos);
    float hs1Flare = exp(-hs1Dist * 12.0) * 2.3 * (1.0 + u_audio * 0.85);
    vec3 hs1Color = vec3(1.0, 0.92, 0.75) * hs1Flare;

    // Hotspot 2: Left Rim Starburst Pinch
    vec2 hs2Pos = vec2(-0.40, -0.06);
    float hs2Dist = length(uv - hs2Pos);
    float hs2Flare = exp(-hs2Dist * 14.0) * 2.0 * (1.0 + u_audio * 0.65);
    vec3 hs2Color = vec3(1.0, 0.85, 0.45) * hs2Flare;

    // Hotspot 3: Bottom Luminous Photon Wave
    vec2 hs3Pos = vec2(0.06, -0.40);
    float hs3Dist = length(uv - hs3Pos);
    float hs3Flare = exp(-hs3Dist * 11.0) * 1.5 * (1.0 + u_audio * 0.55);
    vec3 hs3Color = vec3(0.6, 0.95, 1.0) * hs3Flare;

    // Relativistic Photon Ring
    float ringDist = abs(r - photonRingRadius);
    float photonRing = exp(-ringDist * 42.0) * 1.9 * (1.0 + u_audio * 0.4);
    vec3 photonRingColor = mix(vec3(0.3, 0.85, 1.0), vec3(1.0, 0.9, 0.7), fireBlend) * photonRing;

    // Inner event horizon boundary glow
    float innerGlow = smoothstep(bhRadius + 0.12, bhRadius, r) * smoothstep(bhRadius - 0.02, bhRadius + 0.02, r) * 2.6;
    vec3 innerGlowColor = mix(vec3(0.0, 0.65, 1.0), vec3(1.0, 0.7, 0.2), fireBlend) * innerGlow;

    // Relativistic Doppler Beaming boost
    float doppler = 1.0 + 0.32 * sin(angle + 0.35);

    // Assemble Accretion Disk
    vec3 finalColor = nebulaColor * (diskDensity * 1.6 + outerNebula * 0.7) * doppler;
    finalColor += (fireColor * 0.4) * filaments * diskDensity;
    finalColor += hs1Color + hs2Color + hs3Color;
    finalColor += photonRingColor + innerGlowColor;

    // Background Stars & Star Clusters with gravitational deflection
    vec2 starUv = uv * (1.0 - 0.12 / (r + 0.15));
    float starGrid = hash(floor(starUv * 75.0));
    float starIntensity = pow(starGrid, 45.0) * 1.4;
    starIntensity *= (0.7 + 0.3 * sin(u_time * 3.0 + starGrid * 6.28));
    
    // Star cluster at top-right
    float clusterDist = length(uv - vec2(0.80, 0.70));
    float clusterGaze = exp(-clusterDist * 3.5) * 0.35;
    float clusterStars = pow(hash(floor(starUv * 110.0)), 28.0) * exp(-clusterDist * 2.8) * 2.5;

    vec3 starsColor = vec3(0.85, 0.92, 1.0) * (starIntensity + clusterStars) + vec3(0.2, 0.4, 0.8) * clusterGaze;
    finalColor += starsColor * smoothstep(bhRadius + 0.04, bhRadius + 0.25, r);

    // Deep Space subtle background
    vec3 spaceBg = mix(vec3(0.004, 0.008, 0.025), vec3(0.008, 0.025, 0.06), smoothstep(0.0, 1.5, r));
    finalColor += spaceBg * (1.0 - diskDensity);

    // EVENT HORIZON: Pure Black Void
    float eventHorizonMask = smoothstep(bhRadius - 0.004, bhRadius + 0.008, r);
    finalColor *= eventHorizonMask;

    // Outer smooth vignette
    float vignette = smoothstep(1.9, 0.75, r);
    finalColor *= vignette;

    // Tone mapping & gamma correction
    finalColor = finalColor / (finalColor + vec3(1.0));
    finalColor = pow(finalColor, vec3(1.0 / 1.15));

    gl_FragColor = vec4(finalColor, 1.0);
}
`;

const STATE_MAP: Record<HudState, number> = {
  idle: 0,
  listening: 1,
  processing: 2,
  speaking: 3,
  remote: 4,
  error: 5,
};

function BlackHolePlane({ state, audioLevel }: { state: HudState; audioLevel: number }) {
  const mesh = useRef<THREE.Mesh>(null!);
  const mouse = useRef<THREE.Vector2>(new THREE.Vector2(0.5, 0.5));

  const uniforms = useMemo(
    () => ({
      u_time: { value: 0 },
      u_resolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
      u_mouse: { value: mouse.current },
      u_audio: { value: 0 },
      u_state: { value: 0 },
      u_intensity: { value: 1.0 },
    }),
    []
  );

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      mouse.current.set(e.clientX / window.innerWidth, 1.0 - e.clientY / window.innerHeight);
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  useFrame((_, dt) => {
    if (!mesh.current) return;
    const mat = mesh.current.material as THREE.ShaderMaterial;
    mat.uniforms.u_time.value += dt;
    mat.uniforms.u_audio.value = audioLevel;
    mat.uniforms.u_state.value = STATE_MAP[state] ?? 0;
    mat.uniforms.u_mouse.value = mouse.current;
  });

  return (
    <mesh ref={mesh}>
      <planeGeometry args={[4.2, 4.2]} />
      <shaderMaterial
        vertexShader={VERTEX_SHADER}
        fragmentShader={FRAGMENT_SHADER}
        uniforms={uniforms}
        transparent
        depthWrite={false}
      />
    </mesh>
  );
}

export default function CosmicBlackHole() {
  const state = useHud((s) => s.state);
  const audioLevel = useHud((s) => s.audioLevel);

  return (
    <div className="relative w-full h-full flex items-center justify-center pointer-events-none">
      <Canvas
        camera={{ position: [0, 0, 2.5], fov: 60 }}
        gl={{ alpha: true, antialias: true }}
        className="w-full h-full"
      >
        <BlackHolePlane state={state} audioLevel={audioLevel} />
      </Canvas>
    </div>
  );
}
