import { create } from "zustand";

export type HudState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "error"
  | "remote";

export type ActivePanel =
  | "chat"
  | "email"
  | "demo"
  | "consejo"
  | "system";

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

export interface EmailMessage {
  id: string;
  from: string;
  subject: string;
  body: string;
  ts: number;
  read: boolean;
  vip: boolean;
}

export interface WebDemo {
  id: string;
  nombre: string;
  industria: string;
  url: string;
  ts: number;
  status: "generating" | "deploying" | "ready" | "error";
}

export interface ConsejoResult {
  asunto: string;
  ultron: string;
  jarvis: string;
  sintesis: string;
  desacuerdo: boolean;
  ts: number;
}

interface HudStore {
  state: HudState;
  setState: (s: HudState) => void;

  activePanel: ActivePanel;
  setActivePanel: (p: ActivePanel) => void;

  logs: SystemLog[];
  pushLog: (l: Omit<SystemLog, "id" | "ts">) => void;
  clearLogs: () => void;

  telemetry: Telemetry;
  setTelemetry: (t: Partial<Telemetry>) => void;

  audioLevel: number;
  ttsLevel: number;
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

  // Email
  emails: EmailMessage[];
  setEmails: (emails: EmailMessage[]) => void;
  markEmailRead: (id: string) => void;
  emailsLoading: boolean;
  setEmailsLoading: (b: boolean) => void;

  // WebDemo
  demos: WebDemo[];
  addDemo: (d: Omit<WebDemo, "id" | "ts">) => void;
  updateDemo: (id: string, patch: Partial<WebDemo>) => void;

  // Consejo
  consejoHistory: ConsejoResult[];
  pushConsejo: (r: Omit<ConsejoResult, "ts">) => void;
  consejoLoading: boolean;
  setConsejoLoading: (b: boolean) => void;

  // Llamadas
  llamadaStatus: string;
  setLlamadaStatus: (s: string) => void;
}

export const useHud = create<HudStore>((set) => ({
  state: "idle",
  setState: (s) => set({ state: s }),

  activePanel: "chat",
  setActivePanel: (p) => set({ activePanel: p }),

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

  // Email
  emails: [],
  setEmails: (emails) => set({ emails }),
  markEmailRead: (id) =>
    set((p) => ({
      emails: p.emails.map((e) => (e.id === id ? { ...e, read: true } : e)),
    })),
  emailsLoading: false,
  setEmailsLoading: (b) => set({ emailsLoading: b }),

  // WebDemo
  demos: [],
  addDemo: (d) =>
    set((p) => ({
      demos: [{ ...d, id: crypto.randomUUID(), ts: Date.now() }, ...p.demos].slice(0, 50),
    })),
  updateDemo: (id, patch) =>
    set((p) => ({
      demos: p.demos.map((d) => (d.id === id ? { ...d, ...patch } : d)),
    })),

  // Consejo
  consejoHistory: [],
  pushConsejo: (r) =>
    set((p) => ({
      consejoHistory: [{ ...r, ts: Date.now() }, ...p.consejoHistory].slice(0, 20),
    })),
  consejoLoading: false,
  setConsejoLoading: (b) => set({ consejoLoading: b }),

  llamadaStatus: "",
  setLlamadaStatus: (s) => set({ llamadaStatus: s }),
}));
