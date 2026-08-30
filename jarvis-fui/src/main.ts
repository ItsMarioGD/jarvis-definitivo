import './styles/theme.css'
import { FuiStage } from './webgl/FuiStage'
import { initHud } from './ui/hud'

const canvas = document.getElementById('stage') as HTMLCanvasElement
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

const stage = new FuiStage({ canvas, reducedMotion: reduced })
stage.start()

const hud = initHud()

// Feed organic "load" into the core so it breathes even without a backend.
let load = 0.3
setInterval(() => {
  load += (Math.random() - 0.5) * 0.25
  load = Math.max(0.05, Math.min(0.95, load))
  stage.setEnergy(load)
  hud.feedEnergy(load)
}, 1800)

// Pause WebGL when the tab is hidden is already handled inside FuiStage.
window.addEventListener('beforeunload', () => stage.dispose())
