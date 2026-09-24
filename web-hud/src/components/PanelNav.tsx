import { motion } from "framer-motion";
import {
  MessageSquareText, Mail, Globe, Scale, Cpu, Phone
} from "lucide-react";
import { useHud, ActivePanel } from "../store/hudStore";
import { send } from "../hooks/useBridge";

const TABS: { id: ActivePanel; label: string; Icon: React.ElementType; badge?: () => number }[] = [
  { id: "chat",    label: "CHAT",    Icon: MessageSquareText },
  { id: "email",   label: "EMAIL",   Icon: Mail,
    badge: () => useHud.getState().emails.filter((e) => !e.read).length },
  { id: "demo",    label: "DEMOS",   Icon: Globe },
  { id: "consejo", label: "CONSEJO", Icon: Scale },
  { id: "system",  label: "SISTEMA", Icon: Cpu },
];

export default function PanelNav() {
  const active = useHud((s) => s.activePanel);
  const set = useHud((s) => s.setActivePanel);
  const emails = useHud((s) => s.emails);
  const llamadaStatus = useHud((s) => s.llamadaStatus);

  const unread = emails.filter((e) => !e.read).length;

  const handleCall = () => {
    send({ type: "chat", text: "llámame al celular" });
  };

  return (
    <div className="flex items-center gap-1">
      {TABS.map(({ id, label, Icon }) => {
        const isActive = active === id;
        const badge = id === "email" ? unread : 0;

        return (
          <button
            key={id}
            onClick={() => set(id)}
            className="relative group flex flex-col items-center gap-0.5 px-3 py-1.5
                       rounded transition-all"
          >
            {isActive && (
              <motion.div
                layoutId="panel-indicator"
                className="absolute inset-0 bg-hud-cyan/10 border border-hud-cyan/30 rounded"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <Icon
              size={13}
              className={isActive
                ? "text-hud-cyan text-glow-cyan relative z-10"
                : "text-hud-cyan_dim relative z-10 group-hover:text-hud-cyan/70"}
            />
            <span className={[
              "text-[8px] tracking-[0.2em] relative z-10",
              isActive ? "text-hud-cyan" : "text-hud-cyan_dim",
            ].join(" ")}>
              {label}
            </span>
            {badge > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full
                               bg-hud-warn text-black text-[8px] font-bold
                               flex items-center justify-center z-20">
                {badge}
              </span>
            )}
          </button>
        );
      })}

      {/* Quick call button */}
      <div className="ml-auto">
        <button
          onClick={handleCall}
          title="Llamar al señor"
          className="flex flex-col items-center gap-0.5 px-2 py-1.5 rounded
                     text-hud-cyan_dim hover:text-hud-warn transition-colors
                     hover:bg-hud-warn/10"
        >
          <Phone size={13} />
          <span className="text-[8px] tracking-widest">LLAMAR</span>
        </button>
      </div>
    </div>
  );
}
