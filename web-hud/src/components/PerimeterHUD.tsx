import { AnimatePresence, motion } from "framer-motion";
import { Calendar, Home, Smartphone, Brain, Wrench } from "lucide-react";
import { useHud, type RemoteIcon } from "../store/hudStore";

const ICONS: Record<RemoteIcon, any> = {
  calendar: Calendar,
  home:     Home,
  android:  Smartphone,
  graph:    Brain,
  selfheal: Wrench,
};

const LABEL: Record<RemoteIcon, string> = {
  calendar: "MCP · Google Calendar",
  home:     "MCP · Home Assistant",
  android:  "Android · Accessibility",
  graph:    "Mem0 · Graph Retrieval",
  selfheal: "Self-Healing Routine",
};

/**
 * Perimeter HUD — borde ámbar pulsante que se activa mientras Jarvis
 * opera un dispositivo remoto. Muestra el icono de la operación activa.
 */
export default function PerimeterHUD() {
  const op = useHud((s) => s.remoteOp);
  const Icon = op ? ICONS[op.icon] : null;

  return (
    <AnimatePresence>
      {op && Icon && (
        <>
          {/* amber border */}
          <motion.div
            key="border"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="pointer-events-none fixed inset-0 z-40"
          >
            <motion.div
              className="absolute inset-0 border-[3px] border-hud-amber"
              style={{
                boxShadow:
                  "inset 0 0 60px rgba(184,134,11,.45), inset 0 0 12px rgba(184,134,11,.65)",
              }}
              animate={{ opacity: [0.55, 1, 0.55] }}
              transition={{ duration: 1.4, repeat: Infinity }}
            />
          </motion.div>

          {/* floating badge */}
          <motion.div
            key="badge"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            className="fixed top-20 left-1/2 -translate-x-1/2 z-50 glass-strong rounded-full px-4 py-2 flex items-center gap-3 text-glow-warn"
          >
            <Icon size={14} className="text-hud-amber" />
            <span className="font-mono text-xs tracking-[0.3em] uppercase text-hud-amber">
              Operando dispositivo remoto
            </span>
            <span className="font-mono text-[11px] text-hud-amber/80">
              · {LABEL[op.icon]}
            </span>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
