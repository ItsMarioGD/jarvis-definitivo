import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

// ---------------------------------------------------------------------------
// Shared GLSL: 3D simplex noise (Ashima) + fbm — used by core displacement.
// ---------------------------------------------------------------------------
const NOISE_GLSL = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(
    i.z+vec4(0.0,i1.z,i2.z,1.0))
    +i.y+vec4(0.0,i1.y,i2.y,1.0))
    +i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float fbm(vec3 p){
  float a=0.5; float s=0.0;
  for(int i=0;i<5;i++){ s+=a*snoise(p); p*=2.03; a*=0.5; }
  return s;
}
`

export default function Core({ audioLevel = 0 }) {
  const coreRef = useRef()
  const matRef = useRef()
  const groupRef = useRef()

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uAudio: { value: 0 },
      uTeal: { value: new THREE.Color('#0fd3c9') },
      uOrange: { value: new THREE.Color('#ff7a18') },
      uCyan: { value: new THREE.Color('#21e6ff') },
    }),
    []
  )

  useFrame((state, delta) => {
    uniforms.uTime.value += delta
    uniforms.uAudio.value = THREE.MathUtils.lerp(uniforms.uAudio.value, audioLevel, 0.06)
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.12
    if (groupRef.current) groupRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.2) * 0.15
  })

  return (
    <group ref={groupRef}>
      {/* Plasmatic stellar-magma core (SDF-ish displacement + fresnel emissive) */}
      <mesh ref={coreRef}>
        <icosahedronGeometry args={[1.35, 64]} />
        <shaderMaterial
          ref={matRef}
          uniforms={uniforms}
          vertexShader={/* glsl */ `
            ${NOISE_GLSL}
            uniform float uTime;
            uniform float uAudio;
            varying vec3 vNormal;
            varying vec3 vView;
            varying float vDisp;
            void main(){
              vec3 p = position;
              float t = uTime * 0.35;
              float n = fbm(normalize(p) * 2.4 + vec3(t));
              float boil = fbm(normalize(p) * 6.0 - vec3(t*1.8)) * 0.4;
              float disp = n * 0.32 + boil * 0.18 + uAudio * 0.25;
              vDisp = disp;
              p += normal * disp;
              vec4 mv = modelViewMatrix * vec4(p, 1.0);
              vNormal = normalize(normalMatrix * normal);
              vView = normalize(-mv.xyz);
              gl_Position = projectionMatrix * mv;
            }
          `}
          fragmentShader={/* glsl */ `
            ${NOISE_GLSL}
            uniform float uTime;
            uniform float uAudio;
            uniform vec3 uTeal;
            uniform vec3 uOrange;
            uniform vec3 uCyan;
            varying vec3 vNormal;
            varying vec3 vView;
            varying float vDisp;
            void main(){
              float fres = pow(1.0 - max(dot(vNormal, vView), 0.0), 2.4);
              float energy = smoothstep(-0.2, 0.6, vDisp + uAudio*0.4);
              vec3 col = mix(uTeal, uCyan, fres);
              col = mix(col, uOrange, energy * 0.85);
              col += uCyan * fres * 1.6;
              // boiling hot specks
              float spark = pow(fract(sin(dot(vNormal.xy, vec2(12.9,78.2)) + uTime)*43758.5), 18.0);
              col += uOrange * spark * 1.4;
              gl_FragColor = vec4(col * (1.1 + fres*1.5), 1.0);
            }
          `}
        />
      </mesh>

      {/* Inner glow shell */}
      <mesh scale={1.6}>
        <sphereGeometry args={[1.35, 32, 32]} />
        <meshBasicMaterial color="#0a2a30" transparent opacity={0.18} side={THREE.BackSide} />
      </mesh>

      <ParticleSwarm count={180000} />
    </group>
  )
}

// ---------------------------------------------------------------------------
// Gravitational nanometric particle swarm (1,000,000-class density, scaled).
// ---------------------------------------------------------------------------
function ParticleSwarm({ count = 180000 }) {
  const pointsRef = useRef()
  const matRef = useRef()

  const { positions, seeds, colors } = useMemo(() => {
    const positions = new Float32Array(count * 3)
    const seeds = new Float32Array(count)
    const colors = new Float32Array(count * 3)
    const cA = new THREE.Color('#21e6ff')
    const cB = new THREE.Color('#ff7a18')
    for (let i = 0; i < count; i++) {
      const r = 1.8 + Math.pow(Math.random(), 0.6) * 3.2
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta)
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      positions[i * 3 + 2] = r * Math.cos(phi)
      seeds[i] = Math.random() * 1000
      const c = Math.random() > 0.5 ? cA : cB
      colors[i * 3] = c.r
      colors[i * 3 + 1] = c.g
      colors[i * 3 + 2] = c.b
    }
    return { positions, seeds, colors }
  }, [count])

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uAudio: { value: 0 },
      uSize: { value: 2.2 },
    }),
    []
  )

  useFrame((state, delta) => {
    uniforms.uTime.value += delta
    if (pointsRef.current) pointsRef.current.rotation.y -= delta * 0.05
  })

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
        <bufferAttribute attach="attributes-seed" count={count} array={seeds} itemSize={1} />
        <bufferAttribute attach="attributes-color" count={count} array={colors} itemSize={3} />
      </bufferGeometry>
      <shaderMaterial
        ref={matRef}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        vertexShader={/* glsl */ `
          ${NOISE_GLSL}
          uniform float uTime;
          uniform float uSize;
          attribute float seed;
          attribute vec3 color;
          varying vec3 vColor;
          varying float vAlpha;
          void main(){
            vec3 p = position;
            float t = uTime * 0.4 + seed;
            // turbulence + gravitational pulsing
            vec3 turb = vec3(
              fbm(p*0.6 + vec3(t)),
              fbm(p*0.6 + vec3(t+10.0)),
              fbm(p*0.6 + vec3(t+20.0))
            );
            p += turb * 0.35;
            float pulse = 0.85 + 0.15*sin(uTime*1.5 + seed);
            vec4 mv = modelViewMatrix * vec4(p, 1.0);
            gl_PointSize = uSize * pulse * (300.0 / -mv.z);
            gl_Position = projectionMatrix * mv;
            vColor = color;
            vAlpha = 0.55 + 0.45*sin(uTime*2.0 + seed*3.0);
          }
        `}
        fragmentShader={/* glsl */ `
          varying vec3 vColor;
          varying float vAlpha;
          void main(){
            vec2 uv = gl_PointCoord - 0.5;
            float d = length(uv);
            if(d > 0.5) discard;
            float glow = smoothstep(0.5, 0.0, d);
            gl_FragColor = vec4(vColor, glow * vAlpha);
          }
        `}
      />
    </points>
  )
}
