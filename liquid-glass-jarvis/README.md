# LIQUID GLASS FUI — J.A.R.V.I.S.

Interfaz Futurista (FUI/HUD) estilo J.A.R.V.I.S. construida sin restricciones de
rendimiento: **Liquid Glass**, núcleo holográfico 3D con enjambre de partículas,
física de resortes, tipografía cinética con *scrambling* criptográfico, y una
canalización de post-procesado cinematográfico (Bloom, aberración cromática,
grano de película 35mm, profundidad de campo).

## Stack

- **Vite + React 18**
- **Three.js** + **@react-three/fiber** + **@react-three/drei**
- **@react-three/postprocessing** (Bloom, ChromaticAberration, Noise, DoF, Vignette)
- **framer-motion** (Spring Physics)
- **Tailwind CSS** (paleta Teal & Orange / Blade Runner 2049)

## Ejecutar

```bash
cd liquid-glass-jarvis
npm install
npm run dev
```

Abre `http://localhost:5173`.

## Arquitectura

| Módulo | Archivo | Qué implementa |
|---|---|---|
| Núcleo holográfico | `src/three/Core.jsx` | Esfera SDF con ruido 3D (fbm/simplex) ebullición de magma + fresnel emisivo; enjambre de **180 000** partículas aditivas (cyan/naranja) con turbulencia. |
| Post-proceso | `src/three/PostFX.jsx` | Bloom multi-umbral, aberración cromática radial (rojo/azul separados), grano de película, DoF shallow (bokeh), viñeta. |
| Panel Liquid Glass | `src/components/LiquidGlassPanel.jsx` | Cristal con `backdrop-filter` + tubo de gas neón animado + borde de aberración cromática + montaje con Spring Physics. |
| Telemetría | `src/components/Telemetry.jsx` | Barras de fluido + cilindro de RAM de "líquido gélido" con superficie ondulante y *heat haze*. |
| Chat | `src/components/ChatConsole.jsx` | *Slow-screen redraw* carácter a carácter, caret láser, chispas de soldadura en cada tecla. |
| Reloj | `src/components/SystemClock.jsx` | Tipografía cinética masiva con *scrambling* al cambiar. |
| Boot | `src/components/BootSequence.jsx` | Divulgación progresiva dramática ("SISTEMAS OPERATIVOS EN LÍNEA"). |

## Notas

- La densidad de partículas está escalada a 180 000 para arrancar en hardware
  real; sube `count` en `Core.jsx` hacia 1 000 000 en tu súper-computadora de 2040.
- La refracción real de píxeles en vivo (offscreen FBO) se aproxima aquí con
  `backdrop-filter` + post-proceso; un paso FBO dedicado puede sustituir el panel
  DOM por un `MeshTransmissionMaterial` de drei si se desea refractar el HUD 3D.
