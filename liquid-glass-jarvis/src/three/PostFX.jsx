import { EffectComposer, Bloom, ChromaticAberration, Noise, DepthOfField, Vignette } from '@react-three/postprocessing'
import { BlendFunction } from 'postprocessing'
import { Vector2 } from 'three'

// Cinematic post-processing pipeline: multi-threshold Bloom, aggressive
// chromatic aberration (red/blue channel split), 35mm film grain, shallow DoF.
export default function PostFX() {
  return (
    <EffectComposer multisampling={0}>
      <DepthOfField focusDistance={0.012} focalLength={0.05} bokehScale={3.2} height={480} />
      <Bloom
        intensity={1.45}
        luminanceThreshold={0.55}
        luminanceSmoothing={0.18}
        mipmapBlur
        radius={0.85}
      />
      <ChromaticAberration
        blendFunction={BlendFunction.NORMAL}
        offset={new Vector2(0.0022, 0.0014)}
        radialModulation={true}
        modulationOffset={0.35}
      />
      <Noise premultiply blendFunction={BlendFunction.OVERLAY} opacity={0.18} />
      <Vignette eskil={false} offset={0.25} darkness={0.85} />
    </EffectComposer>
  )
}
