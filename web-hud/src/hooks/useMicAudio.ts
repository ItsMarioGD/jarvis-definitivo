import { useEffect, useRef } from "react";
import { useHud } from "../store/hudStore";

/**
 * Captures microphone audio via WebAudio and pushes RMS to the store.
 * Activates only when `state === "listening"` to honor privacy.
 */
export function useMicAudio() {
  const ctxRef    = useRef<AudioContext | null>(null);
  const analyser  = useRef<AnalyserNode | null>(null);
  const rafRef    = useRef<number>(0);
  const setLevel  = useHud((s) => s.setAudioLevel);
  const state     = useHud((s) => s.state);

  useEffect(() => {
    let cancelled = false;

    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
        const src = ctx.createMediaStreamSource(stream);
        const an  = ctx.createAnalyser();
        an.fftSize = 1024;
        src.connect(an);
        ctxRef.current   = ctx;
        analyser.current = an;

        const buf = new Float32Array(an.fftSize);
        const loop = () => {
          an.getFloatTimeDomainData(buf);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
          const rms = Math.sqrt(sum / buf.length);
          setLevel(Math.min(1, rms * 6));
          rafRef.current = requestAnimationFrame(loop);
        };
        loop();

        // remember stream so we can stop on cleanup
        (ctxRef.current as any)._stream = stream;
      } catch (e) {
        useHud.getState().pushLog({
          level: "WARN",
          message: `Permiso de micrófono denegado o dispositivo ausente: ${(e as Error).message}`,
        });
      }
    };

    if (state === "listening") start();
    else stop();

    return () => {
      cancelled = true;
      stop();
    };

    function stop() {
      cancelAnimationFrame(rafRef.current);
      const ctx = ctxRef.current;
      if (ctx) {
        const stream = (ctx as any)._stream as MediaStream | undefined;
        stream?.getTracks().forEach((t) => t.stop());
        ctx.close().catch(() => undefined);
      }
      ctxRef.current   = null;
      analyser.current = null;
      setLevel(0);
    }
  }, [state, setLevel]);
}
