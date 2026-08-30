import { motion, AnimatePresence } from "framer-motion";
import { Settings as SettingsIcon, X, Volume2, Eye, Cpu, ShieldCheck } from "lucide-react";
import { useState } from "react";

interface Props { open: boolean; onClose: () => void; }

export default function SettingsDrawer({ open, onClose }: Props) {
  const [reduceMotion, setReduceMotion]   = useState(false);
  const [highContrast, setHighContrast]   = useState(false);
  const [ttsVolume,    setTtsVolume]      = useState(80);
  const [voice,        setVoice]          = useState("Spuds Oxley");
  const [privacy,      setPrivacy]        = useState(true);

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", stiffness: 220, damping: 30 }}
          className="fixed right-0 top-0 bottom-0 w-[360px] z-50 glass-strong border-l border-hud-cyan/30 p-5 overflow-y-auto"
        >
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2 text-hud-cyan text-glow-cyan">
              <SettingsIcon size={16} />
              <span className="text-[10px] tracking-[0.4em] uppercase">Configuración</span>
            </div>
            <button onClick={onClose} className="p-1.5 rounded hover:bg-hud-cyan/20 text-hud-cyan">
              <X size={16} />
            </button>
          </div>

          <Section icon={Volume2} title="Audio">
            <Field label="Volumen TTS">
              <input
                type="range"
                min={0} max={100}
                value={ttsVolume}
                onChange={(e) => setTtsVolume(+e.target.value)}
                className="w-full accent-hud-cyan"
              />
            </Field>
            <Field label="Voz ElevenLabs">
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="w-full bg-hud-bg border border-hud-cyan/30 rounded px-2 py-1 text-sm font-mono"
              >
                <option>Spuds Oxley</option>
                <option>Adam</option>
                <option>Clyde</option>
                <option>Daniel</option>
              </select>
            </Field>
          </Section>

          <Section icon={Eye} title="Accesibilidad">
            <Toggle label="Reducir movimiento" value={reduceMotion} onChange={setReduceMotion} />
            <Toggle label="Alto contraste"      value={highContrast} onChange={setHighContrast} />
          </Section>

          <Section icon={Cpu} title="Núcleo">
            <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
              <Info k="LLM"  v="Qwen3 4B · Ollama" />
              <Info k="STT"  v="Web Speech + Vosk" />
              <Info k="TTS"  v="ElevenLabs · Multilingual v2" />
              <Info k="Pipe" v="Pipecat / Direct REST" />
            </div>
          </Section>

          <Section icon={ShieldCheck} title="Privacidad">
            <Toggle label="Ocultar HUD perimetral" value={privacy} onChange={setPrivacy} />
            <p className="text-[10px] text-hud-cyan_dim/70 mt-1">
              Cuando Jarvis opera dispositivos remotos, se omite la notificación ámbar.
            </p>
          </Section>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function Section({ icon: Icon, title, children }: any) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 text-hud-cyan_dim mb-2">
        <Icon size={12} />
        <span className="text-[10px] tracking-[0.3em] uppercase">{title}</span>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Field({ label, children }: any) {
  return (
    <label className="block">
      <div className="text-[10px] text-hud-cyan_dim mb-1 uppercase tracking-widest">{label}</div>
      {children}
    </label>
  );
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className="flex items-center justify-between w-full text-sm text-hud-ice"
    >
      <span>{label}</span>
      <span className={[
        "w-9 h-5 rounded-full relative transition",
        value ? "bg-hud-cyan" : "bg-hud-blue/40",
      ].join(" ")}>
        <span className={[
          "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all",
          value ? "left-[18px]" : "left-0.5",
        ].join(" ")} />
      </span>
    </button>
  );
}

function Info({ k, v }: { k: string; v: string }) {
  return (
    <div className="glass rounded p-2">
      <div className="text-[9px] tracking-widest text-hud-cyan_dim uppercase">{k}</div>
      <div className="text-hud-ice text-[11px] mt-0.5">{v}</div>
    </div>
  );
}
