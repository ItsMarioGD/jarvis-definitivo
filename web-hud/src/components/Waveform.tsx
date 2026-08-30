import { useEffect, useRef } from "react";
import { Mic, Volume2 } from "lucide-react";
import { useHud } from "../store/hudStore";

/**
 * Dual-channel audio visualizer:
 *   - mic input: time-domain + RMS (audioLevel in store)
 *   - TTS output: spectrum of currently-playing voice (ttsLevel in store)
 *
 * Renders an Iron-Man style circular waveform around the lower half of the HUD.
 */
export default function Waveform() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const audioLevel = useHud((s) => s.audioLevel);
  const ttsLevel   = useHud((s) => s.ttsLevel);

  useEffect(() => {
    const ctx = canvas.current!.getContext("2d")!;
    let raf = 0;
    let phase = 0;

    const draw = () => {
      const w = (ctx.canvas.width  = ctx.canvas.clientWidth);
      const h = (ctx.canvas.height = ctx.canvas.clientHeight);
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2, cy = h / 2;
      const R  = Math.min(w, h) / 2 - 10;

      // outer ring
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(0,240,255,.18)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // waveform (around the ring)
      const bars = 96;
      ctx.lineWidth = 2;
      const grad = ctx.createLinearGradient(0, 0, w, 0);
      grad.addColorStop(0,    "#00F0FF");
      grad.addColorStop(0.5,  "#FF00FF");
      grad.addColorStop(1,    "#00FF88");
      ctx.strokeStyle = grad;

      const level = Math.max(audioLevel, ttsLevel * 0.7);
      phase += 0.04;
      for (let i = 0; i < bars; i++) {
        const a = (i / bars) * Math.PI * 2 - Math.PI / 2;
        const k = level * (0.6 + 0.4 * Math.sin(phase + i * 0.3));
        const r1 = R * 0.85;
        const r2 = R * (0.85 + k * 0.15);
        const x1 = cx + Math.cos(a) * r1;
        const y1 = cy + Math.sin(a) * r1;
        const x2 = cx + Math.cos(a) * r2;
        const y2 = cy + Math.sin(a) * r2;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [audioLevel, ttsLevel]);

  return (
    <div className="relative w-full aspect-square max-w-[280px]">
      <canvas ref={canvas} className="w-full h-full" />
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <div className="flex items-center gap-2 text-hud-cyan_dim text-[10px] tracking-[0.4em] uppercase">
          <Mic size={12} />
          <span>Input</span>
          <span className="mx-2 opacity-40">|</span>
          <Volume2 size={12} />
          <span>Output</span>
        </div>
        <div className="mt-2 font-mono text-xs text-glow-cyan">
          {Math.round(audioLevel * 100)}% / {Math.round(ttsLevel * 100)}%
        </div>
      </div>
    </div>
  );
}
