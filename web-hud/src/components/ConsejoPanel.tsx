import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Scale, Zap, Shield, Loader2, Brain } from "lucide-react";
import { useHud, ConsejoResult } from "../store/hudStore";
import { send } from "../hooks/useBridge";

export default function ConsejoPanel() {
  const history = useHud((s) => s.consejoHistory);
  const loading = useHud((s) => s.consejoLoading);
  const setLoading = useHud((s) => s.setConsejoLoading);
  const push = useHud((s) => s.pushConsejo);

  const [asunto, setAsunto] = useState("");
  const [selected, setSelected] = useState<ConsejoResult | null>(null);

  const handleDeliberar = () => {
    if (!asunto.trim()) return;
    setLoading(true);
    send({ type: "chat", text: `consejo: ${asunto.trim()}` });
    setAsunto("");
    // Optimistic loading indicator
    setTimeout(() => setLoading(false), 10000);
  };

  if (selected) {
    return (
      <div className="flex flex-col h-full">
        <button
          onClick={() => setSelected(null)}
          className="flex items-center gap-1 text-hud-cyan_dim hover:text-hud-cyan
                     text-[10px] tracking-widest mb-3 transition-colors"
        >
          ← VOLVER
        </button>

        <div className="text-[11px] text-hud-cyan_dim mb-3 tracking-widest">
          DELIBERACIÓN: "{selected.asunto}"
        </div>

        <div className="flex-1 overflow-y-auto space-y-3">
          {/* Ultron */}
          <div className="border border-red-500/30 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <Zap size={12} className="text-red-400" />
              <span className="text-[10px] tracking-widest text-red-400">ULTRON · VÍA DECISIVA</span>
            </div>
            <p className="text-sm font-mono text-hud-ice/90 leading-relaxed">
              {selected.ultron || "Sin respuesta."}
            </p>
          </div>

          {/* Jarvis */}
          <div className="border border-hud-cyan/30 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <Shield size={12} className="text-hud-cyan" />
              <span className="text-[10px] tracking-widest text-hud-cyan">JARVIS · VÍA PRUDENTE</span>
            </div>
            <p className="text-sm font-mono text-hud-ice/90 leading-relaxed">
              {selected.jarvis || "Sin respuesta."}
            </p>
          </div>

          {/* Síntesis */}
          {selected.sintesis && (
            <div className="border border-hud-warn/30 bg-hud-warn/5 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <Scale size={12} className="text-hud-warn" />
                <span className="text-[10px] tracking-widest text-hud-warn">
                  SÍNTESIS
                  {selected.desacuerdo && (
                    <span className="ml-2 text-red-400">· DESACUERDO</span>
                  )}
                </span>
              </div>
              <p className="text-sm font-mono text-hud-ice/90 leading-relaxed">
                {selected.sintesis}
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <Scale size={14} className="text-hud-cyan text-glow-cyan" />
        <span className="text-[10px] tracking-[0.4em] uppercase text-hud-cyan_dim flex-1">
          Consejo
        </span>
        <Brain size={12} className="text-hud-cyan_dim" />
      </div>

      <p className="text-[10px] text-hud-cyan_dim mb-3 leading-relaxed">
        Somete una decisión. JARVIS (prudente) y ULTRON (decisivo) debaten
        y sintetizan la mejor opción.
      </p>

      {/* Input */}
      <div className="mb-3">
        <textarea
          value={asunto}
          onChange={(e) => setAsunto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleDeliberar();
            }
          }}
          placeholder="¿Sobre qué debo deliberar?"
          rows={3}
          className="w-full bg-hud-bg/60 border border-hud-cyan/20 rounded-lg
                     px-3 py-2 text-sm font-mono text-hud-ice resize-none
                     focus:outline-none focus:border-hud-cyan/50"
        />
        <button
          onClick={handleDeliberar}
          disabled={loading || !asunto.trim()}
          className="mt-2 w-full flex items-center justify-center gap-2
                     bg-gradient-to-r from-red-900/40 to-hud-cyan/20
                     hover:from-red-900/60 hover:to-hud-cyan/30
                     border border-hud-cyan/20 text-hud-ice
                     py-2 rounded text-[10px] tracking-widest
                     disabled:opacity-40 transition-all"
        >
          {loading ? (
            <><Loader2 size={12} className="animate-spin" /> DELIBERANDO…</>
          ) : (
            <><Scale size={12} /> CONVOCAR CONSEJO</>
          )}
        </button>
      </div>

      {/* History */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {history.length === 0 && !loading && (
          <div className="text-center text-hud-cyan_dim text-[11px] py-4">
            <Scale size={20} className="mx-auto mb-2 opacity-30" />
            <p className="tracking-widest">SIN DELIBERACIONES</p>
          </div>
        )}

        {loading && (
          <div className="text-center py-4">
            <Loader2 size={20} className="animate-spin mx-auto text-hud-cyan mb-2" />
            <p className="text-[10px] tracking-widest text-hud-cyan_dim">
              CONVOCANDO CONSEJO…
            </p>
          </div>
        )}

        <AnimatePresence>
          {history.map((r, i) => (
            <motion.button
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => setSelected(r)}
              className="w-full text-left bg-hud-bg/40 border border-hud-cyan/15
                         hover:border-hud-cyan/30 rounded-lg px-3 py-2 transition-colors"
            >
              <div className="flex items-center gap-2 mb-1">
                <Scale size={10} className={r.desacuerdo ? "text-hud-warn" : "text-hud-cyan_dim"} />
                <span className="text-[10px] font-mono text-hud-ice truncate flex-1">
                  {r.asunto}
                </span>
                {r.desacuerdo && (
                  <span className="text-[9px] text-red-400 tracking-widest shrink-0">
                    DEBATE
                  </span>
                )}
              </div>
              {r.sintesis && (
                <p className="text-[10px] text-hud-cyan_dim line-clamp-2">
                  {r.sintesis}
                </p>
              )}
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
