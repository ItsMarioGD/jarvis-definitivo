import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import CosmicBlackHole from "./components/CosmicBlackHole";
import TopBar from "./components/TopBar";
import StatusHUD from "./components/StatusHUD";
import SystemLog from "./components/SystemLog";
import Waveform from "./components/Waveform";
import ChatPanel from "./components/ChatPanel";
import MediaViewer from "./components/MediaViewer";
import CommandDock from "./components/CommandDock";
import PerimeterHUD from "./components/PerimeterHUD";
import SettingsDrawer from "./components/SettingsDrawer";
import { useBridge } from "./hooks/useBridge";
import { useMicAudio } from "./hooks/useMicAudio";
import { useHud } from "./store/hudStore";

export default function App() {
  useBridge();
  useMicAudio();

  const focusMode = useHud((s) => s.focusMode);
  const state     = useHud((s) => s.state);
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
            {/* Left column: chat + telemetry */}
            <div className="col-span-3 flex flex-col gap-3 min-h-0">
              <div className="flex-1 min-h-0"><ChatPanel /></div>
              <StatusHUD />
            </div>

            {/* Center column: Cosmic Singularity Black Hole */}
            <div className="col-span-6 relative">
              <div className="absolute inset-0 flex items-center justify-center">
                <CosmicBlackHole />
              </div>
              {/* corner labels */}
              <Corner label="LAT 35.4°N" sub="LON 139.7°E" className="top-2 left-2" />
              <Corner label="SECURE LINK" sub="TLS 1.3 · ECDHE" className="top-2 right-2" />
              <Corner label="AGENT" sub={state.toUpperCase()} className="bottom-2 left-2" />
              <Corner label="MEM0" sub="GRAPH SYNC" className="bottom-2 right-2" />
            </div>

            {/* Right column: log + waveform + media */}
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
