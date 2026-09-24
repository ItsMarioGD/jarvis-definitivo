import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import CosmicBlackHole from "./components/CosmicBlackHole";
import TopBar from "./components/TopBar";
import StatusHUD from "./components/StatusHUD";
import SystemLog from "./components/SystemLog";
import Waveform from "./components/Waveform";
import ChatPanel from "./components/ChatPanel";
import EmailPanel from "./components/EmailPanel";
import WebDemoPanel from "./components/WebDemoPanel";
import ConsejoPanel from "./components/ConsejoPanel";
import MediaViewer from "./components/MediaViewer";
import CommandDock from "./components/CommandDock";
import PerimeterHUD from "./components/PerimeterHUD";
import SettingsDrawer from "./components/SettingsDrawer";
import PanelNav from "./components/PanelNav";
import { useBridge } from "./hooks/useBridge";
import { useMicAudio } from "./hooks/useMicAudio";
import { useHud } from "./store/hudStore";

export default function App() {
  useBridge();
  useMicAudio();

  const focusMode   = useHud((s) => s.focusMode);
  const state       = useHud((s) => s.state);
  const activePanel = useHud((s) => s.activePanel);
  const [settings, setSettings] = useState(false);

  return (
    <div className="relative h-screen w-screen overflow-hidden scanlines">
      {/* Background grid + radial vignette */}
      <div className="absolute inset-0 grid-bg animate-grid-drift opacity-50 pointer-events-none" />
      <div className="absolute inset-0 pointer-events-none bg-gradient-to-b from-transparent via-hud-bg/30 to-hud-bg/90" />

      <TopBar />

      <AnimatePresence>
        {!focusMode && (
          <motion.main
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 grid grid-cols-12 gap-3 px-4 pt-4 pb-32"
          >
            {/* ── Left column: panel nav + active panel ── */}
            <div className="col-span-3 flex flex-col gap-2 min-h-0">
              {/* Panel navigation tabs */}
              <div className="glass hud-corners relative rounded-lg px-2 py-1.5">
                <span className="c1" /><span className="c2" />
                <PanelNav />
              </div>

              {/* Active panel */}
              <div className="glass hud-corners relative rounded-lg p-3 flex-1 min-h-0 overflow-hidden">
                <span className="c1" /><span className="c2" />
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activePanel}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.15 }}
                    className="h-full flex flex-col"
                  >
                    {activePanel === "chat"    && <ChatPanel />}
                    {activePanel === "email"   && <EmailPanel />}
                    {activePanel === "demo"    && <WebDemoPanel />}
                    {activePanel === "consejo" && <ConsejoPanel />}
                    {activePanel === "system"  && <SystemPanelLeft />}
                  </motion.div>
                </AnimatePresence>
              </div>

              <StatusHUD />
            </div>

            {/* ── Center column: Cosmic Singularity ── */}
            <div className="col-span-6 relative">
              <div className="absolute inset-0 flex items-center justify-center">
                <CosmicBlackHole />
              </div>
              <Corner label="J.A.R.V.I.S" sub="UNIFIED CORE v5" className="top-2 left-2" />
              <Corner label="SECURE LINK" sub="TLS 1.3 · ECDHE" className="top-2 right-2" />
              <Corner label="AGENT" sub={state.toUpperCase()} className="bottom-2 left-2" />
              <Corner label="MEM0 + SQLite" sub="GRAPH SYNC" className="bottom-2 right-2" />
            </div>

            {/* ── Right column: log + waveform + media ── */}
            <div className="col-span-3 flex flex-col gap-3 min-h-0">
              <div className="flex-1 min-h-0"><SystemLog /></div>
              <div className="glass hud-corners relative rounded-lg p-3 flex items-center gap-3">
                <span className="c1" /><span className="c2" />
                <Waveform />
              </div>
              <MediaViewer />
            </div>
          </motion.main>
        )}
      </AnimatePresence>

      {/* Perimeter remote-operation HUD */}
      <PerimeterHUD />

      {/* Floating command dock */}
      <CommandDock onSettings={() => setSettings(true)} />

      {/* Settings drawer */}
      <SettingsDrawer open={settings} onClose={() => setSettings(false)} />
    </div>
  );
}

function Corner({ label, sub, className = "" }: { label: string; sub: string; className?: string }) {
  return (
    <div className={`absolute ${className} text-[9px] tracking-[0.3em] font-mono`}>
      <div className="text-hud-cyan text-glow-cyan">{label}</div>
      <div className="text-hud-cyan_dim">{sub}</div>
    </div>
  );
}

function SystemPanelLeft() {
  const telemetry = useHud((s) => s.telemetry);
  const connected = useHud((s) => s.connected);

  const metrics = [
    { label: "CPU", value: `${telemetry.cpu.toFixed(0)}%`, warn: telemetry.cpu > 80 },
    { label: "RAM", value: `${telemetry.ram.toFixed(1)} / ${telemetry.ramTotal} GB`, warn: telemetry.ram / telemetry.ramTotal > 0.85 },
    { label: "GPU", value: `${telemetry.gpu.toFixed(0)}%`, warn: telemetry.gpu > 85 },
    { label: "NET ↑", value: `${telemetry.netUp.toFixed(1)} KB/s`, warn: false },
    { label: "NET ↓", value: `${telemetry.netDown.toFixed(1)} KB/s`, warn: false },
  ];

  return (
    <div className="flex flex-col gap-2 h-full">
      <div className="text-[10px] tracking-[0.4em] uppercase text-hud-cyan_dim flex items-center gap-2">
        <span>Sistema</span>
        <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-hud-ok" : "bg-hud-error"}`} />
      </div>
      {metrics.map((m) => (
        <div key={m.label} className="flex justify-between items-center">
          <span className="text-[10px] text-hud-cyan_dim tracking-widest">{m.label}</span>
          <span className={`text-[11px] font-mono ${m.warn ? "text-hud-warn" : "text-hud-ice"}`}>
            {m.value}
          </span>
        </div>
      ))}
    </div>
  );
}
