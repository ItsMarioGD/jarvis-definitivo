import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Terminal, Trash2 } from "lucide-react";
import { useHud } from "../store/hudStore";

const LEVEL_STYLE: Record<string, string> = {
  INFO:  "text-hud-cyan",
  OK:    "text-hud-ok text-glow-ok",
  PROC:  "text-hud-proc text-glow-proc",
  WARN:  "text-hud-warn text-glow-warn",
  ERROR: "text-hud-err",
};

const LEVEL_BAR: Record<string, string> = {
  INFO:  "bg-hud-cyan/40",
  OK:    "bg-hud-ok/60",
  PROC:  "bg-hud-proc/60",
  WARN:  "bg-hud-warn/60",
  ERROR: "bg-hud-err/70",
};

export default function SystemLog() {
  const logs    = useHud((s) => s.logs);
  const clear   = useHud((s) => s.clearLogs);
  const ref     = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs]);

  const fmt = (ts: number) => {
    const d = new Date(ts);
    return d.toLocaleTimeString("es-ES", { hour12: false });
  };

  return (
    <div className="glass hud-corners relative rounded-lg p-3 w-full h-full flex flex-col text-hud-ice">
      <span className="c1" /><span className="c2" />
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-hud-cyan text-glow-cyan" />
          <span className="text-[10px] tracking-[0.4em] uppercase text-hud-cyan_dim">
            System Log
          </span>
        </div>
        <button
          onClick={clear}
          className="p-1 rounded hover:bg-hud-cyan/10 text-hud-cyan_dim hover:text-hud-cyan transition"
          title="Limpiar log"
        >
          <Trash2 size={12} />
        </button>
      </div>

      <div ref={ref} className="flex-1 overflow-y-auto pr-2 space-y-0.5 text-[11px] font-mono">
        <AnimatePresence initial={false}>
          {logs.slice(-200).map((l) => (
            <motion.div
              key={l.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="flex items-start gap-2 py-0.5"
            >
              <span className={`w-1 self-stretch rounded ${LEVEL_BAR[l.level] ?? "bg-hud-cyan/30"}`} />
              <span className="text-hud-cyan_dim/70 shrink-0">{fmt(l.ts)}</span>
              <span className={`shrink-0 w-10 ${LEVEL_STYLE[l.level] ?? "text-hud-ice"}`}>[{l.level}]</span>
              <span className="whitespace-pre-wrap break-words text-hud-ice/95">
                {l.message}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
        {logs.length === 0 && (
          <div className="text-hud-cyan_dim/50 italic py-2 text-center">
            Sin eventos registrados. Diga “Jarvis” para comenzar.
          </div>
        )}
      </div>
    </div>
  );
}
