/**
 * Jarvis HUD BFF — Node.js + TypeScript bridge.
 *
 * Two responsibilities:
 *   1. Expose a JSON-over-HTTP API for the React HUD:
 *        GET  /api/health        → { ok, llm, tts, mcp }
 *        GET  /api/telemetry     → simulated system metrics (or psutil proxy)
 *        POST /api/chat          → proxy text to Python /api/llm
 *        POST /api/tts           → proxy text to ElevenLabs (or fallback)
 *        GET  /api/media         → media history from jarvis_memory.db
 *   2. Expose a WebSocket /ws that fans out events to all HUD clients
 *      and proxies incoming chat messages to the Python core.
 *
 * Environment:
 *   PORT                  (default 8787)
 *   PYTHON_BASE_URL       (default http://localhost:8765 — the Python side)
 *   ELEVENLABS_API_KEY    (forwarded for TTS)
 *   JARVIS_MEMORY_DB      (sqlite path; default ../jarvis_memory.db)
 */
import express from "express";
import cors from "cors";
import http from "node:http";
import { WebSocketServer } from "ws";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { attachPythonProxy } from "./pythonProxy.js";
import { attachWsHub } from "./wsHub.js";
import { mediaRouter } from "./media.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT ?? 8787);
const PY  = process.env.PYTHON_BASE_URL ?? "http://localhost:8765";

const app = express();
app.use(cors());
app.use(express.json({ limit: "2mb" }));

app.get("/api/health", async (_req, res) => {
  let pyOk = false;
  try {
    const r = await fetch(`${PY}/health`, { signal: AbortSignal.timeout(1500) });
    pyOk = r.ok;
  } catch { /* python offline is fine, the HUD keeps working */ }
  res.json({
    ok: true,
    version: "2.0.0",
    python: pyOk,
    llm:   process.env.QWEN_MODEL ?? "qwen3:4b-instruct",
    tts:   process.env.ELEVENLABS_VOICE_ID ?? "NOpBlnGInO9m6vDvFkFC",
    mcp:   ["calendar", "home", "android", "mem0", "selfheal"],
    now:   new Date().toISOString(),
  });
});

app.use("/api", attachPythonProxy(PY));
app.use("/api/media", mediaRouter);

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: "/ws" });
attachWsHub(wss, PY);

server.listen(PORT, () => {
  console.log(`[jarvis-bff] listening on http://localhost:${PORT}`);
  console.log(`[jarvis-bff] WebSocket on ws://localhost:${PORT}/ws`);
  console.log(`[jarvis-bff] Python upstream: ${PY}`);

  // Optional: auto-spawn the Python HUD backend if not already running.
  if (process.env.AUTO_START_PYTHON === "1") {
    const cwd = path.resolve(__dirname, "../..");
    const py  = process.platform === "win32" ? "python" : "python3";
    const child = spawn(py, ["jarvis_web_backend.py"], { cwd, stdio: "inherit" });
    process.on("exit", () => child.kill());
  }
});
