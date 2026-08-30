import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'

/* 3D simplex noise + fbm (Ashima). Shared by core displacement and particles. */
const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy; i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float fbm(vec3 p){ float a=0.5; float s=0.0; for(int i=0;i<5;i++){ s+=a*snoise(p); p*=2.03; a*=0.5; } return s; }
`

export interface FuiStageOptions {
  canvas: HTMLCanvasElement
  reducedMotion?: boolean
}

export class FuiStage {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private composer: EffectComposer
  private clock = new THREE.Clock()
  private group = new THREE.Group()
  private coreMat: THREE.ShaderMaterial
  private swarmMat: THREE.ShaderMaterial
  private cinematicPass: ShaderPass
  private energy = 0
  private targetEnergy = 0
  private mouse = new THREE.Vector2(0, 0)
  private running = false
  private reduced: boolean
  private raf = 0

  constructor(opts: FuiStageOptions) {
    this.reduced = opts.reducedMotion ?? false
    const canvas = opts.canvas
    const w = window.innerWidth
    const h = window.innerHeight

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: false,
      alpha: true,
      powerPreference: 'high-performance',
    })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
    this.renderer.setSize(w, h)
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.1

    this.camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 100)
    this.camera.position.set(0, 0, 7)
    this.scene.add(this.group)

    const amber = new THREE.Color('#e8c8a0')
    const orange = new THREE.Color('#ff7a18')
    const cyan = new THREE.Color('#21e6ff')

    // ── Plasmatic core ──
    this.coreMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uAudio: { value: 0 },
        uAmber: { value: amber },
        uOrange: { value: orange },
        uCyan: { value: cyan },
      },
      vertexShader: /* glsl */ `
        ${NOISE}
        uniform float uTime; uniform float uAudio;
        varying vec3 vNormal; varying vec3 vView; varying float vDisp;
        void main(){
          vec3 p = position;
          float t = uTime * 0.35;
          float n = fbm(normalize(p) * 2.4 + vec3(t));
          float boil = fbm(normalize(p) * 6.0 - vec3(t * 1.8)) * 0.4;
          float disp = n * 0.32 + boil * 0.18 + uAudio * 0.22;
          vDisp = disp; p += normal * disp;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vNormal = normalize(normalMatrix * normal);
          vView = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        ${NOISE}
        uniform float uTime; uniform float uAudio;
        uniform vec3 uAmber; uniform vec3 uOrange; uniform vec3 uCyan;
        varying vec3 vNormal; varying vec3 vView; varying float vDisp;
        void main(){
          float fres = pow(1.0 - max(dot(vNormal, vView), 0.0), 2.4);
          float energy = smoothstep(-0.2, 0.6, vDisp + uAudio * 0.4);
          vec3 col = mix(uAmber, uCyan, fres * 0.4);
          col = mix(col, uOrange, energy * 0.8);
          col += uCyan * fres * 1.3;
          float spark = pow(fract(sin(dot(vNormal.xy, vec2(12.9,78.2)) + uTime) * 43758.5), 18.0);
          col += uOrange * spark * 1.2;
          gl_FragColor = vec4(col * (1.1 + fres * 1.5), 1.0);
        }`,
    })
    const core = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.35, this.reduced ? 24 : 48),
      this.coreMat
    )
    this.group.add(core)
    this.group.add(
      new THREE.Mesh(
        new THREE.SphereGeometry(1.35, 32, 32),
        new THREE.MeshBasicMaterial({ color: '#0a2a30', transparent: true, opacity: 0.16, side: THREE.BackSide })
      )
    )

    // ── Particle swarm (capped) ──
    const COUNT = this.reduced ? 12000 : 48000
    const pos = new Float32Array(COUNT * 3)
    const seed = new Float32Array(COUNT)
    const col = new Float32Array(COUNT * 3)
    const cA = new THREE.Color('#21e6ff')
    const cB = new THREE.Color('#e8c8a0')
    for (let i = 0; i < COUNT; i++) {
      const r = 1.8 + Math.pow(Math.random(), 0.6) * 3.2
      const th = Math.random() * Math.PI * 2
      const ph = Math.acos(2 * Math.random() - 1)
      pos[i * 3] = r * Math.sin(ph) * Math.cos(th)
      pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th)
      pos[i * 3 + 2] = r * Math.cos(ph)
      seed[i] = Math.random() * 1000
      const c = Math.random() > 0.5 ? cA : cB
      col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geo.setAttribute('seed', new THREE.BufferAttribute(seed, 1))
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
    this.swarmMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: { uTime: { value: 0 }, uSize: { value: 2.2 } },
      vertexShader: /* glsl */ `
        ${NOISE}
        uniform float uTime; uniform float uSize;
        attribute float seed; attribute vec3 color;
        varying vec3 vColor; varying float vAlpha;
        void main(){
          vec3 p = position;
          float t = uTime * 0.4 + seed;
          vec3 turb = vec3(fbm(p*0.6+vec3(t)), fbm(p*0.6+vec3(t+10.0)), fbm(p*0.6+vec3(t+20.0)));
          p += turb * 0.35;
          float pulse = 0.85 + 0.15 * sin(uTime * 1.5 + seed);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_PointSize = uSize * pulse * (300.0 / -mv.z);
          gl_Position = projectionMatrix * mv;
          vColor = color; vAlpha = 0.55 + 0.45 * sin(uTime * 2.0 + seed * 3.0);
        }`,
      fragmentShader: /* glsl */ `
        varying vec3 vColor; varying float vAlpha;
        void main(){
          vec2 uv = gl_PointCoord - 0.5; float d = length(uv);
          if (d > 0.5) discard;
          float glow = smoothstep(0.5, 0.0, d);
          gl_FragColor = vec4(vColor, glow * vAlpha);
        }`,
    })
    this.group.add(new THREE.Points(geo, this.swarmMat))

    // ── Post-processing (1 bloom + 1 combined pass) ──
    this.composer = new EffectComposer(this.renderer)
    this.composer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
    this.composer.addPass(new RenderPass(this.scene, this.camera))
    this.composer.addPass(new UnrealBloomPass(new THREE.Vector2(w, h), 0.9, 0.7, 0.6))

    this.cinematicPass = new ShaderPass({
      uniforms: { tDiffuse: { value: null }, uTime: { value: 0 } },
      vertexShader: /* glsl */ `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: /* glsl */ `
        uniform sampler2D tDiffuse; uniform float uTime; varying vec2 vUv;
        float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
        void main(){
          vec2 uv = vUv; vec2 c = uv - 0.5; float d = length(c);
          float amt = d * d * 0.012;
          vec3 col;
          col.r = texture2D(tDiffuse, uv + c * amt).r;
          col.g = texture2D(tDiffuse, uv).g;
          col.b = texture2D(tDiffuse, uv - c * amt).b;
          float vig = smoothstep(0.95, 0.30, d);
          col *= mix(0.5, 1.0, vig);
          float luma = dot(col, vec3(0.299,0.587,0.114));
          col += vec3(0.0,0.06,0.09) * (1.0 - luma);
          col += vec3(0.09,0.045,0.0) * smoothstep(0.6, 1.0, luma);
          float g = hash(uv * vec2(1920.0,1080.0) + uTime * 60.0);
          col += (g - 0.5) * 0.05;
          gl_FragColor = vec4(col, 1.0);
        }`,
    })
    this.composer.addPass(this.cinematicPass)
    this.composer.addPass(new OutputPass())

    window.addEventListener('resize', this.onResize)
    window.addEventListener('pointermove', this.onPointer)
    document.addEventListener('visibilitychange', this.onVisibility)
  }

  private onResize = () => {
    const w = window.innerWidth
    const h = window.innerHeight
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h)
    this.composer.setSize(w, h)
  }

  private onPointer = (e: PointerEvent) => {
    this.mouse.x = (e.clientX / window.innerWidth) * 2 - 1
    this.mouse.y = -((e.clientY / window.innerHeight) * 2 - 1)
  }

  private onVisibility = () => {
    if (document.hidden) this.stop()
    else this.start()
  }

  /** External "energy" 0..1 (CPU load / voice) drives core boil + brightness. */
  setEnergy(v: number) {
    this.targetEnergy = Math.max(0, Math.min(1, v))
  }

  start() {
    if (this.running) return
    this.running = true
    this.clock.start()
    const loop = () => {
      this.raf = requestAnimationFrame(loop)
      this.frame()
    }
    this.raf = requestAnimationFrame(loop)
  }

  stop() {
    this.running = false
    cancelAnimationFrame(this.raf)
  }

  private frame() {
    const t = this.clock.getElapsedTime()
    this.energy += (this.targetEnergy - this.energy) * 0.05
    // gentle organic pulse if no external energy is fed
    const pulse = this.reduced ? 0.25 : 0.25 + 0.2 * Math.sin(t * 0.7)
    const audio = Math.max(this.energy, pulse)
    this.coreMat.uniforms.uTime.value = t
    this.coreMat.uniforms.uAudio.value = audio
    this.swarmMat.uniforms.uTime.value = t
    this.cinematicPass.uniforms.uTime.value = t
    this.group.rotation.y += 0.0016 + this.mouse.x * 0.0008
    this.group.rotation.x = (this.reduced ? 0 : Math.sin(t * 0.2) * 0.15 + this.mouse.y * 0.08)
    this.composer.render()
  }

  dispose() {
    this.stop()
    window.removeEventListener('resize', this.onResize)
    window.removeEventListener('pointermove', this.onPointer)
    document.removeEventListener('visibilitychange', this.onVisibility)
    this.composer.dispose()
    this.renderer.dispose()
  }
}
