# J.A.R.V.I.S. — Omnimodal HUD (React 18 + Three.js + TypeScript)

The new face of the Jarvis project: a cinematic, real-time HUD built on top of
the existing Python `jarvis_core.py`. Designed to feel like the Arc Reactor
from Iron Man crossed with a modern Iron Man suit telemetry layer.

```
┌──────────────────────────────────────────────────────────────────────┐
│  TOPBAR · clock · connection · focus mode                            │
├──────────────┬────────────────────────────────┬───────────────────────┤
│  CHAT GLASS  │                                │   SYSTEM LOG (live)   │
│              │                                │                       │
│  TELEMETRY   │      ✦  ARC REACTOR  ✦         │   WAVEFORM (mic+TTS)  │
│  CPU·RAM·NET │      (WebGL / R3F + Bloom)     │                       │
│              │                                │   MULTIMEDIA HISTORY  │
├──────────────�────────────────────────────────┴───────────────────────┤
│             COMMAND DOCK  ·  MIC  ·  MCP TRIGGERS                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Stack

| Concern          | Tech                                                   |
| ---------------- | ------------------------------------------------------ |
| Build / dev      | **Vite 5**, TypeScript 5                               |
| UI runtime       | **React 18** + **Zustand** (state)                     |
| Styling          | **TailwindCSS 3** + custom CSS for glassmorphism       |
| 3D / HUD         | **three.js**, **@react-three/fiber**, **@react-three/drei**, **@react-three/postprocessing** (Bloom) |
| Motion           | **Framer Motion**                                      |
| Icons            | **lucide-react**                                       |
| Bridge server    | **Express 4** + **ws 8** (Node BFF)                    |
| Audio            | WebAudio API (real-time mic RMS + TTS spectrum)        |
| Backend (LLM)    | Existing `jarvis_core.py` (Qwen3 + ElevenLabs + Mem0)  |

## Folder layout

```
web-hud/
├── index.html
├── package.json
├── vite.config.ts          # proxies /api and /ws to :8787
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── public/jarvis.svg
├── src/
│   ├── main.tsx
│   ├── App.tsx             # composes the whole HUD
│   ├── index.css
│   ├── store/hudStore.ts   # zustand: state, logs, chat, media, remote op
│   ├── hooks/
│   │   ├── useBridge.ts    # WS client → BFF → Python
│   │   └── useMicAudio.ts  # WebAudio mic capture + RMS
│   └── components/
│       ├── ArcReactor.tsx        # three.js + Bloom
│       ├── TopBar.tsx            # clock · link · power
│       ├── StatusHUD.tsx         # CPU/RAM/NET sparklines
│       ├── SystemLog.tsx         # glass log panel
│       ├── Waveform.tsx          # circular audio viz
│       ├── ChatPanel.tsx         # glass chat
│       ├── MediaViewer.tsx       # generated media grid + modal
│       ├── CommandDock.tsx       # floating dock (mic + MCP)
│       ├── PerimeterHUD.tsx      # amber border during remote ops
│       └── SettingsDrawer.tsx
└── server/
    ├── index.ts            # Express + WebSocketServer
    ├── pythonProxy.ts      # reverse proxy to jarvis_web_backend.py
    ├── wsHub.ts            # fans events to all HUD clients
    └── media.ts            # reads jarvis_memory.db media history
```

## Install & run

```bash
cd web-hud
npm install

# Terminal A — Python backend (Talks to Qwen + ElevenLabs)
python ../jarvis_web_backend.py

# Terminal B — Node BFF (port 8787) + Vite dev (port 5173)
npm start
# open http://localhost:5173
```

## Highlights

- **60 FPS WebGL Arc Reactor** with reactive rings, orbiting nodes, tick
  marks and Bloom — colors and rotation speed change per state.
- **Real microphone waveform** (WebAudio RMS) that drives the reactor's
  pulse AND a dual-channel (mic + TTS) circular visualizer.
- **Perimeter amber HUD** with icon-coded remote-operation indicators.
- **Live telemetry sparklines** for CPU / RAM / NET / MCP bus.
- **Glass chat overlay** that doesn't interrupt voice interaction.
- **Multimedia viewer modal** for Kling/Flux outputs.
- **Focus mode** (collapses to a small floating reactor button).
- **Settings drawer** with audio, accessibility, and privacy toggles.
- **Resilient WS bridge**: if Python goes offline the HUD keeps running
  in local-only demo mode.

## Protocol (BFF ↔ Python)

| Path          | Method | Body / Response                                    |
| ------------- | ------ | -------------------------------------------------- |
| `/health`     | GET    | `{ ok, llm, voice_id, mode }`                      |
| `/chat`       | POST   | `{ text }` → `{ reply, media?, tts_url? }`         |
| `/tts`        | POST   | `{ text }` → `audio/mpeg` bytes                    |
| `/telemetry`  | GET    | `{ cpu, ram, ram_total, net, uptime }`             |
| `/media`      | GET    | `MediaItem[]` from `media_history` table           |

## WebSocket (`/ws`)

Client → server: `{ type: "chat", text }`
Server → client: `{ type: "state"|"log"|"chat"|"media"|"remote"|"tts/level", … }`
