import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Globe, Rocket, ExternalLink, Loader2, Plus, CheckCircle2, XCircle, Copy } from "lucide-react";
import { useHud, WebDemo } from "../store/hudStore";
import { send } from "../hooks/useBridge";

const INDUSTRIAS = [
  "Restaurante", "Tecnología", "Salud", "Legal", "Construcción",
  "Educación", "Moda", "Viajes", "General",
];

export default function WebDemoPanel() {
  const demos = useHud((s) => s.demos);
  const addDemo = useHud((s) => s.addDemo);

  const [nombre, setNombre] = useState("");
  const [industria, setIndustria] = useState("General");
  const [descripcion, setDescripcion] = useState("");
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const handleCreate = () => {
    if (!nombre.trim()) return;
    setCreating(true);
    setShowForm(false);

    // Add optimistic entry
    const tempId = crypto.randomUUID();
    addDemo({
      nombre: nombre.trim(),
      industria,
      url: "",
      status: "generating",
    });

    // Dispatch to backend via Jarvis
    send({
      type: "chat",
      text: `crea una demo web para la empresa "${nombre.trim()}" del sector ${industria}. ${descripcion ? "Descripción: " + descripcion : ""}`,
    });

    setNombre("");
    setDescripcion("");
    setTimeout(() => setCreating(false), 3000);
  };

  const copyUrl = (url: string, id: string) => {
    navigator.clipboard.writeText(url).catch(() => {});
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  const statusIcon = (d: WebDemo) => {
    switch (d.status) {
      case "generating":
      case "deploying":
        return <Loader2 size={12} className="animate-spin text-hud-cyan_dim" />;
      case "ready":
        return <CheckCircle2 size={12} className="text-hud-ok" />;
      case "error":
        return <XCircle size={12} className="text-hud-error" />;
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <Globe size={14} className="text-hud-cyan text-glow-cyan" />
        <span className="text-[10px] tracking-[0.4em] uppercase text-hud-cyan_dim flex-1">
          Web Demos
        </span>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-1 text-[9px] tracking-widest
                     text-hud-cyan border border-hud-cyan/20 px-2 py-1
                     rounded hover:bg-hud-cyan/10 transition-colors"
        >
          <Plus size={10} />
          NUEVA
        </button>
      </div>

      {/* Form */}
      <AnimatePresence>
        {showForm && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-3 overflow-hidden"
          >
            <div className="bg-hud-bg/40 border border-hud-cyan/20 rounded-lg p-3 space-y-2">
              <input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Nombre de la empresa *"
                className="w-full bg-transparent border border-hud-cyan/20 rounded
                           px-3 py-2 text-sm font-mono text-hud-ice
                           focus:outline-none focus:border-hud-cyan/50"
              />
              <select
                value={industria}
                onChange={(e) => setIndustria(e.target.value)}
                className="w-full bg-hud-bg border border-hud-cyan/20 rounded
                           px-3 py-2 text-sm font-mono text-hud-ice
                           focus:outline-none focus:border-hud-cyan/50"
              >
                {INDUSTRIAS.map((i) => (
                  <option key={i} value={i}>{i}</option>
                ))}
              </select>
              <textarea
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                placeholder="Descripción breve (opcional)"
                rows={2}
                className="w-full bg-transparent border border-hud-cyan/20 rounded
                           px-3 py-2 text-sm font-mono text-hud-ice resize-none
                           focus:outline-none focus:border-hud-cyan/50"
              />
              <button
                onClick={handleCreate}
                disabled={creating || !nombre.trim()}
                className="w-full flex items-center justify-center gap-2
                           bg-hud-cyan/20 hover:bg-hud-cyan/30 text-hud-cyan
                           py-2 rounded text-[10px] tracking-widest
                           disabled:opacity-40 transition-colors"
              >
                {creating ? (
                  <><Loader2 size={12} className="animate-spin" /> GENERANDO…</>
                ) : (
                  <><Rocket size={12} /> CREAR Y DESPLEGAR</>
                )}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Demo list */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {demos.length === 0 && (
          <div className="text-center text-hud-cyan_dim text-[11px] py-8">
            <Globe size={24} className="mx-auto mb-2 opacity-30" />
            <p className="tracking-widest">SIN DEMOS AÚN</p>
            <p className="mt-1 text-[10px]">
              Di "crea demo para [empresa]"
            </p>
          </div>
        )}
        <AnimatePresence>
          {demos.map((d) => (
            <motion.div
              key={d.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-hud-bg/40 border border-hud-cyan/15 rounded-lg px-3 py-2"
            >
              <div className="flex items-center gap-2 mb-1">
                {statusIcon(d)}
                <span className="text-[11px] font-mono text-hud-ice font-semibold flex-1">
                  {d.nombre}
                </span>
                <span className="text-[9px] text-hud-cyan_dim tracking-widest">
                  {d.industria}
                </span>
              </div>

              {d.status === "generating" && (
                <p className="text-[10px] text-hud-cyan_dim animate-pulse">
                  Claude generando sitio…
                </p>
              )}
              {d.status === "deploying" && (
                <p className="text-[10px] text-hud-cyan_dim animate-pulse">
                  Subiendo a Vercel…
                </p>
              )}

              {d.url && d.status === "ready" && (
                <div className="flex items-center gap-1 mt-1">
                  <span className="text-[10px] font-mono text-hud-cyan truncate flex-1">
                    {d.url}
                  </span>
                  <button
                    onClick={() => copyUrl(d.url, d.id)}
                    className="p-1 text-hud-cyan_dim hover:text-hud-cyan transition-colors"
                  >
                    {copied === d.id
                      ? <CheckCircle2 size={12} className="text-hud-ok" />
                      : <Copy size={12} />}
                  </button>
                  <a
                    href={d.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1 text-hud-cyan_dim hover:text-hud-cyan transition-colors"
                  >
                    <ExternalLink size={12} />
                  </a>
                </div>
              )}

              <div className="text-[9px] text-hud-cyan_dim mt-1">
                {new Date(d.ts).toLocaleTimeString()}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
