import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Cpu, MemoryStick, Network, ShieldCheck, AlertTriangle, Radio } from "lucide-react";
import { useHud } from "../store/hudStore";

function Sparkline({ data, color }: { data: number[]; color: string }) {
  const path = data
    .map((v, i) => `${i === 0 ? "M" : "L"} ${i * 6} ${20 - v * 20}`)
    .join(" ");
  return (
    <svg viewBox="0 0 240 20" className="w-full h-5" preserveAspectRatio="none">
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

export default function StatusHUD() {
  const t = useHud((s) => s.telemetry);
  const setT = useHud((s) => s.setTelemetry);
  const connected = useHud((s) => s.connected);
  const state = useHud((s) => s.state);

  const [cpuHist, setCpuHist] = useState<number[]>(Array(40).fill(0));
  const [ramHist, setRamHist] = useState<number[]>(Array(40).fill(0));
  const [netHist, setNetHist] = useState<number[]>(Array(40).fill(0));

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      // Use performance.memory when available (Chrome); otherwise fake.
      const mem = (performance as any).memory;
      const ramUsedGB = mem ? mem.usedJSHeapSize / 1024 ** 3 : 0;
      const ramTotalGB = mem ? mem.jsHeapSizeLimit / 1024 ** 3 : 8;
      const cpu = 0.15 + Math.random() * 0.5;
      const net = Math.random();
      setT({
        cpu,
        ram: ramUsedGB,
        ramTotal: ramTotalGB,
        netDown: net,
        netUp: net * 0.4,
        gpu: 0.2 + Math.random() * 0.3,
        uptime: (Date.now() - bootTime) / 1000,
      });
      setCpuHist((h) => [...h.slice(1), cpu]);
      setRamHist((h) => [...h.slice(1), ramUsedGB / Math.max(ramTotalGB, 1)]);
      setNetHist((h) => [...h.slice(1), net]);
      raf = window.setTimeout(tick, 1500) as unknown as number;
    };
    raf = window.setTimeout(tick, 1500) as unknown as number;
    return () => clearTimeout(raf);
  }, [setT]);

  const fmtUptime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  };

  const Row = ({
    icon: Icon, label, value, color, unit, hist,
  }: { icon: any; label: string; value: string; color: string; unit?: string; hist: number[] }) => (
    <div className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-hud-cyan/5 transition">
      <Icon size={16} className="text-hud-cyan" />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] tracking-[0.3em] text-hud-cyan_dim uppercase">{label}</span>
          <span className="font-mono text-sm text-glow-cyan" style={{ color }}>
            {value}<span className="text-hud-cyan_dim ml-0.5 text-[10px]">{unit}</span>
          </span>
        </div>
        <Sparkline data={hist} color={color} />
      </div>
    </div>
  );

  return (
    <div className="glass hud-corners relative rounded-lg p-3 w-full text-hud-ice">
      <span className="c1" /><span className="c2" />
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-hud-cyan text-glow-cyan" />
          <span className="text-[10px] tracking-[0.4em] uppercase text-hud-cyan_dim">
            Telemetría del Sistema
          </span>
        </div>
        <AnimatePresence>
          <motion.div
            key={connected ? "on" : "off"}
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
            className={`flex items-center gap-1 text-[10px] tracking-widest ${
              connected ? "text-hud-ok text-glow-ok" : "text-hud-warn text-glow-warn"
            }`}
          >
            <Radio size={12} />
            {connected ? "ENLACE OK" : "SIN ENLACE"}
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="space-y-1">
        <Row icon={Cpu}        label="CPU"        value={(t.cpu * 100).toFixed(0)}      unit="%"   color="#00F0FF" hist={cpuHist} />
        <Row icon={MemoryStick}label="RAM"        value={t.ram.toFixed(2)}              unit="GB"  color="#FF00FF" hist={ramHist} />
        <Row icon={Network}    label="NET DOWN"   value={(t.netDown * 1024).toFixed(0)} unit="KB"  color="#00FF88" hist={netHist} />
        <Row icon={ShieldCheck}label="MCP BUS"    value={state === "idle" ? "100" : "84"} unit="%" color="#B8860B" hist={Array(40).fill(0.6 + Math.sin(Date.now()/2000)*0.2)} />
        <Row icon={AlertTriangle}label="UPTIME"  value={fmtUptime(t.uptime)}            unit=""    color="#E0FFFF" hist={Array(40).fill(0.5)} />
      </div>
    </div>
  );
}

const bootTime = Date.now();
