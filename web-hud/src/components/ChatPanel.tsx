import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Sparkles, MessageSquareText } from "lucide-react";
import { useHud } from "../store/hudStore";

export default function ChatPanel() {
  const chat = useHud((s) => s.chat);
  const push = useHud((s) => s.pushChat);
  const state = useHud((s) => s.state);
  const [draft, setDraft] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [chat]);

  const submit = () => {
    const t = draft.trim();
    if (!t) return;
    push({ role: "user", text: t });
    setDraft("");
    // Optimistic local echo; the real bridge will overwrite this when it arrives.
    setTimeout(() => {
      push({ role: "assistant", text: "Procesando directivas, señor..." });
    }, 120);
  };

  return (
    <div className="glass hud-corners relative rounded-lg p-3 flex flex-col w-full h-full text-hud-ice">
      <span className="c1" /><span className="c2" />
      <div className="flex items-center gap-2 mb-2">
        <MessageSquareText size={14} className="text-hud-cyan text-glow-cyan" />
        <span className="text-[10px] tracking-[0.4em] uppercase text-hud-cyan_dim">
          Canal de Texto
        </span>
        <span className="ml-auto text-[10px] tracking-widest text-hud-cyan_dim">
          STATE :: {state.toUpperCase()}
        </span>
      </div>

      <div ref={ref} className="flex-1 overflow-y-auto pr-2 space-y-2">
        <AnimatePresence initial={false}>
          {chat.map((m) => (
            <motion.div
              key={m.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
              className={`flex gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {m.role !== "user" && (
                <div className="w-6 h-6 shrink-0 rounded-full glass-strong flex items-center justify-center">
                  {m.role === "system"
                    ? <Sparkles size={12} className="text-hud-warn" />
                    : <Bot size={12} className="text-hud-cyan" />}
                </div>
              )}
              <div
                className={[
                  "max-w-[80%] rounded-lg px-3 py-2 text-sm font-mono leading-snug whitespace-pre-wrap break-words",
                  m.role === "user"
                    ? "bg-hud-cyan/15 border border-hud-cyan/40 text-hud-ice"
                    : m.role === "system"
                      ? "bg-hud-warn/10 border border-hud-warn/40 text-hud-warn text-glow-warn italic"
                      : "glass-strong",
                ].join(" ")}
              >
                {m.text}
              </div>
              {m.role === "user" && (
                <div className="w-6 h-6 shrink-0 rounded-full bg-hud-cyan/30 flex items-center justify-center">
                  <User size={12} className="text-hud-bg" />
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        className="mt-2 flex items-center gap-2 glass-strong rounded-md px-3 py-2"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Escriba una directiva, señor..."
          className="flex-1 bg-transparent outline-none text-sm font-mono placeholder:text-hud-cyan_dim/50"
        />
        <button
          type="submit"
          className="p-1.5 rounded-md text-hud-cyan hover:text-hud-bg hover:bg-hud-cyan transition"
          title="Enviar"
        >
          <Send size={14} />
        </button>
      </form>
    </div>
  );
}
