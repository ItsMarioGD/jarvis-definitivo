import { motion } from "framer-motion";
import { Power, Maximize2, Minimize2, Zap, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { useHud } from "../store/hudStore";

export default function TopBar() {
  const focus = useHud((s) => s.focusMode);
  const toggle = useHud((s) => s.toggleFocus);
  const connected = useHud((s) => s.connected);
  const [now, setNow] = useState(new Date());

  // tick clock
  useState(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  });

  const time = now.toLocaleTimeString("es-ES", { hour12: false });
  const date = now.toLocaleDateString("es-ES", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });

  return (
    <div className="relative z-30 flex items-center justify-between px-6 py-3 glass-strong border-b border-hud-cyan/20">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-full glass hud-corners flex items-center justify-center">
          <Zap size={16} className="text-hud-cyan text-glow-cyan" />
        </div>
        <div>
          <div className="font-['Orbitron'] tracking-[0.4em] text-sm text-glow-cyan">
            J.A.R.V.I.S.
          </div>
          <div className="text-[9px] tracking-[0.3em] text-hud-cyan_dim uppercase">
            Omnimodal Autonomous Interface · v2.0
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <motion.div
          animate={{ opacity: connected ? [0.6, 1, 0.6] : 1 }}
          transition={{ duration: 1.6, repeat: Infinity }}
          className={`flex items-center gap-2 px-3 py-1 rounded-full glass ${
            connected ? "text-hud-ok text-glow-ok" : "text-hud-warn text-glow-warn"
          }`}
        >
          <span className="w-2 h-2 rounded-full bg-current" />
          <span className="text-[10px] tracking-[0.3em] uppercase">
            {connected ? "Enlace Estable" : "Sin Enlace"}
          </span>
        </motion.div>

        <div className="text-right font-mono">
          <div className="text-base text-glow-cyan">{time}</div>
          <div className="text-[10px] text-hud-cyan_dim uppercase tracking-widest">{date}</div>
        </div>

        <button
          onClick={toggle}
          className="p-2 rounded glass hover:bg-hud-cyan/10 text-hud-cyan"
          title={focus ? "Salir de modo enfoque" : "Modo enfoque"}
        >
          {focus ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
        <button className="p-2 rounded glass hover:bg-hud-cyan/10 text-hud-cyan" title="Pantalla completa">
          <Maximize2 size={14} />
        </button>
        <button className="p-2 rounded glass hover:bg-hud-err/20 text-hud-err" title="Apagar núcleo">
          <Power size={14} />
        </button>
      </div>
    </div>
  );
}
