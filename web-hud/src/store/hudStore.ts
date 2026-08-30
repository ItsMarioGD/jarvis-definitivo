import { create } from "zustand";

export type HudState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "error"
  | "remote";

export type RemoteIcon = "calendar" | "home" | "android" | "graph" | "selfheal" | null;

export interface SystemLog {
  id: string;
  ts: number;
  level: "INFO" | "WARN" | "ERROR" | "OK" | "PROC";
  message: string;
}

export interface Telemetry {
  cpu: number;
  ram: number;
  ramTotal: number;
  netUp: number;
  netDown: number;
  gpu: number;
  uptime: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  ts: number;
}

export interface MediaItem {
  id: string;
  type: "image" | "video" | "audio";
  prompt: string;
  path: string;
  ts: number;
}

export interface RemoteOp {
  icon: NonNullable<RemoteIcon>;
  label: string;
  ts: number;
}

interface HudStore {
  state: HudState;
  setState: (s: HudState) => void;

  logs: SystemLog[];
  pushLog: (l: Omit<SystemLog, "id" | "ts">) => void;
  clearLogs: () => void;

  telemetry: Telemetry;
  setTelemetry: (t: Partial<Telemetry>) => void;

  audioLevel: number;          // 0..1 RMS from mic
  ttsLevel: number;            // 0..1 analyser from TTS playback
  setAudioLevel: (v: number) => void;
  setTtsLevel: (v: number) => void;

  remoteOp: RemoteOp | null;
  triggerRemote: (op: Omit<RemoteOp, "ts">) => void;

  chat: ChatMessage[];
  pushChat: (m: Omit<ChatMessage, "id" | "ts">) => void;
  clearChat: () => void;

  media: MediaItem[];
  addMedia: (m: Omit<MediaItem, "id" | "ts">) => void;

  connected: boolean;
  setConnected: (b: boolean) => void;

  focusMode: boolean;
  toggleFocus: () => void;
}

export const useHud = create<HudStore>((set) => ({
  state: "idle",
  setState: (s) => set({ state: s }),

  logs: [],
  pushLog: (l) =>
    set((p) => ({
      logs: [
        ...p.logs.slice(-400),
        { ...l, id: crypto.randomUUID(), ts: Date.now() },
      ],
    })),
  clearLogs: () => set({ logs: [] }),

  telemetry: {
    cpu: 0, ram: 0, ramTotal: 16, netUp: 0, netDown: 0, gpu: 0, uptime: 0,
  },
  setTelemetry: (t) => set((p) => ({ telemetry: { ...p.telemetry, ...t } })),

  audioLevel: 0,
  ttsLevel: 0,
  setAudioLevel: (v) => set({ audioLevel: v }),
  setTtsLevel: (v) => set({ ttsLevel: v }),

  remoteOp: null,
  triggerRemote: (op) =>
    set({ remoteOp: { ...op, ts: Date.now() } }),

  chat: [
    { id: "0", role: "system", text: "J.A.R.V.I.S. en línea. Esperando directivas, señor.", ts: Date.now() },
  ],
  pushChat: (m) =>
    set((p) => ({
      chat: [
        ...p.chat.slice(-200),
        { ...m, id: crypto.randomUUID(), ts: Date.now() },
      ],
    })),
  clearChat: () => set({ chat: [] }),

  media: [],
  addMedia: (m) =>
    set((p) => ({
      media: [
        { ...m, id: crypto.randomUUID(), ts: Date.now() },
        ...p.media,
      ].slice(0, 60),
    })),

  connected: false,
  setConnected: (b) => set({ connected: b }),

  focusMode: false,
  toggleFocus: () => set((p) => ({ focusMode: !p.focusMode })),
}));
