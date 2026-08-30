import { motion } from "framer-motion";
import {
  Mic, MicOff, Send, Calendar, Home, Smartphone, Brain, Wrench,
  Image as ImgIcon, Film, Power, Settings,
} from "lucide-react";
import { useHud } from "../store/hudStore";

/**
 * Floating command dock at the bottom center.
 * - Push-to-talk mic (toggles HUD state to "listening")
 * - Quick MCP triggers that fire the perimeter HUD with the matching icon
 */
export default function CommandDock({ onSettings }: { onSettings: () => void }) {
  const setState    = useHud((s) => s.setState);
  const state       = useHud((s) => s.state);
  const trigger     = useHud((s) => s.triggerRemote);
  const audioLevel  = useHud((s) => s.audioLevel);
  const pushLog     = useHud((s) => s.pushLog);

  const listening = state === "listening";

  const press = () => {
    setState(listening ? "idle" : "listening");
    pushLog({
      level: listening ? "INFO" : "WARN",
      message: listening
        ? "Micrófono desactivado por el usuario."
        : "Micrófono activado. A la escucha.",
    });
  };

  const fire = (icon: any, label: string) => {
    trigger({ icon, label });
    pushLog({ level: "PROC", message: `Disparando ${label}...` });
    setTimeout(() => useHud.setState({ remoteOp: null }), 4000);
  };

  const Btn = ({ icon: Icon, label, onClick, hot = false }: any) => (
    <motion.button
      whileHover={{ scale: 1.06, y: -2 }}
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      title={label}
      className={[
        "relative group flex flex-col items-center justify-center",
        "w-12 h-12 rounded-xl glass hud-corners text-hud-cyan hover:text-hud-bg hover:bg-hud-cyan",
        "transition",
        hot ? "ring-1 ring-hud-cyan/60 shadow-glow-cyan" : "",
      ].join(" ")}
    >
      <span className="c1" /><span className="c2" />
      <Icon size={16} />
      <span className="absolute -bottom-5 text-[9px] tracking-[0.3em] uppercase text-hud-cyan_dim opacity-0 group-hover:opacity-100 transition">
        {label}
      </span>
    </motion.button>
  );

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30">
      <div className="glass-strong rounded-2xl px-4 py-3 flex items-end gap-3">
        <Btn icon={Calendar} label="Calendar"  onClick={() => fire("calendar", "google_calendar_mcp_orchestrator")} />
        <Btn icon={Home}     label="Hogar"     onClick={() => fire("home", "home_assistant_mcp_controller")} />
        <Btn icon={Smartphone} label="Android" onClick={() => fire("android", "execute_android_accessibility_action")} />
        <Btn icon={Brain}    label="Memoria"   onClick={() => fire("graph", "mem0_graph_retrieval")} />
        <Btn icon={Wrench}   label="Auto-Rep." onClick={() => fire("selfheal", "trigger_self_healing_routine")} />
        <Btn icon={ImgIcon}  label="Imagen"    onClick={() => useHud.getState().addMedia({ type: "image", prompt: "Render solicitado desde el dock", path: "#" })} />
        <Btn icon={Film}     label="Video"     onClick={() => useHud.getState().addMedia({ type: "video", prompt: "Simulación Kling solicitada", path: "#" })} />

        <div className="w-px h-8 bg-hud-cyan/30 mx-1 self-center" />

        <motion.button
          onClick={press}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.92 }}
          className={[
            "relative w-16 h-16 rounded-full flex items-center justify-center",
            "glass hud-corners",
            listening ? "bg-hud-warn text-hud-bg shadow-glow-warn" : "bg-hud-cyan text-hud-bg shadow-glow-cyan",
          ].join(" ")}
        >
          <span className="c1" /><span className="c2" />
          {listening ? <MicOff size={22} /> : <Mic size={22} />}
          {/* live audio level halo */}
          <motion.span
            className="absolute inset-0 rounded-full border-2 border-current"
            animate={{ scale: 1 + audioLevel * 0.8, opacity: 0.6 - audioLevel * 0.5 }}
            transition={{ duration: 0.06 }}
          />
        </motion.button>

        <div className="w-px h-8 bg-hud-cyan/30 mx-1 self-center" />

        <Btn icon={Send}     label="Texto"     onClick={() => useHud.getState().pushChat({ role: "system", text: "Abra el panel de chat a la izquierda para enviar texto." })} />
        <Btn icon={Settings} label="Ajustes"   onClick={onSettings} />
        <Btn icon={Power}    label="Suspender" onClick={() => {
          pushLog({ level: "WARN", message: "Entrando en modo de bajo consumo." });
          setState("idle");
        }} />
      </div>
    </div>
  );
}
