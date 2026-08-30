/**
 * WebSocket hub — fans events out to every connected HUD client and
 * proxies chat messages to the Python backend.
 */
import type { WebSocketServer, WebSocket } from "ws";

type Event =
  | { type: "state";     value: string }
  | { type: "log";       level: "INFO" | "OK" | "PROC" | "WARN" | "ERROR"; message: string }
  | { type: "chat";      role: "assistant" | "system" | "user"; text: string }
  | { type: "media";     media: { type: string; prompt: string; path: string; ts: number } }
  | { type: "remote";    op: { icon: string; label: string; ts: number } | null }
  | { type: "tts/level"; v: number };

export function attachWsHub(wss: WebSocketServer, pythonBaseUrl: string) {
  const clients = new Set<WebSocket>();

  wss.on("connection", (ws) => {
    clients.add(ws);
    ws.send(JSON.stringify({
      type: "log", level: "OK",
      message: "Cliente HUD conectado al bus del núcleo.",
    } satisfies Event));

    ws.on("message", async (raw) => {
      let msg: any;
      try { msg = JSON.parse(raw.toString()); } catch { return; }

      if (msg.type === "chat") {
        // Optimistic local echo
        broadcast({ type: "chat", role: "user", text: msg.text });
        broadcast({ type: "state", value: "processing" });
        broadcast({ type: "log", level: "PROC", message: `Directiva recibida: "${msg.text}"` });

        try {
          const r = await fetch(`${pythonBaseUrl}/chat`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ text: msg.text }),
          });
          if (r.ok) {
            const data = await r.json() as { reply: string; media?: any; tts_url?: string };
            broadcast({ type: "chat", role: "assistant", text: data.reply });
            if (data.media) broadcast({ type: "media", media: { ...data.media, ts: Date.now() } });
            broadcast({ type: "state", value: "speaking" });
            // Simulate TTS level decay over ~3s (the real impl would pipe audio bytes)
            const lvl = (steps = 30) => {
              let i = 0;
              const id = setInterval(() => {
                broadcast({ type: "tts/level", v: 0.4 + Math.random() * 0.5 });
                if (++i >= steps) {
                  clearInterval(id);
                  broadcast({ type: "tts/level", v: 0 });
                  broadcast({ type: "state", value: "idle" });
                }
              }, 100);
            };
            lvl();
          } else {
            broadcast({ type: "log", level: "ERROR", message: `Núcleo LLM devolvió ${r.status}` });
            broadcast({ type: "chat", role: "system", text: "El núcleo no respondió. ¿Desea reintentar?" });
            broadcast({ type: "state", value: "error" });
          }
        } catch (e) {
          broadcast({ type: "log", level: "WARN", message: `Python inalcanzable: ${(e as Error).message}` });
          broadcast({ type: "chat", role: "system", text: "El núcleo Python no responde. Funcionando en modo local." });
          broadcast({ type: "state", value: "idle" });
        }
      }
    });

    ws.on("close", () => clients.delete(ws));
  });

  function broadcast(event: Event) {
    const payload = JSON.stringify(event);
    for (const c of clients) {
      if (c.readyState === c.OPEN) c.send(payload);
    }
  }

  // Demo heartbeat so the HUD never sits idle
  setInterval(() => {
    broadcast({
      type: "log",
      level: "INFO",
      message: `Heartbeat del bus :: ${new Date().toLocaleTimeString("es-ES", { hour12: false })}`,
    });
  }, 12_000);
}
