/**
 * WebSocket hub — fans events out to every connected HUD client and
 * proxies chat/email/demo messages to the Python backend.
 */
import type { WebSocketServer, WebSocket } from "ws";

type Event =
  | { type: "state";       value: string }
  | { type: "log";         level: "INFO" | "OK" | "PROC" | "WARN" | "ERROR"; message: string }
  | { type: "chat";        role: "assistant" | "system" | "user"; text: string }
  | { type: "media";       media: { type: string; prompt: string; path: string; ts: number } }
  | { type: "remote";      op: { icon: string; label: string; ts: number } | null }
  | { type: "tts/level";   v: number }
  | { type: "email/data";  emails: any[] }
  | { type: "demo/update"; id: string; status: string; url?: string }
  | { type: "consejo/result"; data: any };

export function attachWsHub(wss: WebSocketServer, pythonBaseUrl: string) {
  const clients = new Set<WebSocket>();

  wss.on("connection", (ws) => {
    clients.add(ws);
    ws.send(JSON.stringify({
      type: "log", level: "OK",
      message: "J.A.R.V.I.S. HUD Unificado — bus activo. Todas las capacidades en línea.",
    } satisfies Event));

    ws.on("message", async (raw) => {
      let msg: any;
      try { msg = JSON.parse(raw.toString()); } catch { return; }

      // ── Chat ───────────────────────────────────────────────────────────────
      if (msg.type === "chat") {
        broadcast({ type: "chat", role: "user", text: msg.text });
        broadcast({ type: "state", value: "processing" });
        broadcast({ type: "log", level: "PROC", message: `Directiva: "${msg.text}"` });

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
            simulateTtsDecay();
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
        return;
      }

      // ── Email list ─────────────────────────────────────────────────────────
      if (msg.type === "email/list") {
        broadcast({ type: "log", level: "PROC", message: "Consultando bandeja de entrada…" });
        try {
          const token = process.env.JARVIS_TOKEN ?? "";
          const r = await fetch(
            `${pythonBaseUrl}/api/correo/inbox?limite=15`,
            { headers: { "X-Auth-Token": token } }
          );
          if (r.ok) {
            const data = await r.json() as { mensajes?: any[] };
            const emails = (data.mensajes ?? []).map((m: any) => ({
              id:      m.id ?? String(Date.now()),
              from:    m.from ?? m.remitente ?? "Desconocido",
              subject: m.subject ?? m.asunto ?? "Sin asunto",
              body:    m.body ?? m.cuerpo ?? m.snippet ?? "",
              ts:      m.ts ?? Date.now(),
              read:    m.read ?? false,
              vip:     m.vip ?? false,
            }));
            // Send as a chat message tagged for the email panel
            broadcast({ type: "chat", role: "system", text: `[EMAIL_DATA]${JSON.stringify(emails)}` });
            broadcast({ type: "log", level: "OK", message: `${emails.length} correo(s) cargados.` });
          }
        } catch (e) {
          broadcast({ type: "log", level: "WARN", message: `Correo: ${(e as Error).message}` });
        }
        return;
      }

      // ── Mark email read ────────────────────────────────────────────────────
      if (msg.type === "email/read") {
        // Just log it — actual read tracking is on the Python side if needed
        broadcast({ type: "log", level: "INFO", message: `Correo ${msg.id} marcado como leído.` });
        return;
      }

      // ── WebDemo create ─────────────────────────────────────────────────────
      if (msg.type === "demo/create") {
        const { nombre, industria, descripcion } = msg;
        broadcast({ type: "log", level: "PROC", message: `Iniciando demo para ${nombre}…` });
        try {
          const token = process.env.JARVIS_TOKEN ?? "";
          const r = await fetch(`${pythonBaseUrl}/api/webdemo/crear`, {
            method: "POST",
            headers: { "content-type": "application/json", "X-Auth-Token": token },
            body: JSON.stringify({ nombre, industria, descripcion }),
          });
          const data = await r.json() as { ok: boolean; url?: string; error?: string };
          if (data.ok && data.url) {
            broadcast({ type: "demo/update", id: msg.id ?? "", status: "ready", url: data.url });
            broadcast({ type: "log", level: "OK", message: `Demo ${nombre} → ${data.url}` });
            broadcast({ type: "chat", role: "assistant",
                        text: `Demo de ${nombre} lista, señor: ${data.url}` });
          } else {
            broadcast({ type: "demo/update", id: msg.id ?? "", status: "error" });
            broadcast({ type: "log", level: "ERROR", message: `Demo falló: ${data.error}` });
          }
        } catch (e) {
          broadcast({ type: "demo/update", id: msg.id ?? "", status: "error" });
          broadcast({ type: "log", level: "ERROR", message: `Demo error: ${(e as Error).message}` });
        }
        return;
      }

      // ── Consejo deliberation ───────────────────────────────────────────────
      if (msg.type === "consejo/deliberar") {
        const asunto = msg.asunto ?? "";
        broadcast({ type: "log", level: "PROC", message: `Convocando consejo: "${asunto}"` });
        // Route through chat for the Python skill to handle
        broadcast({ type: "chat", role: "user", text: `consejo: ${asunto}` });
        try {
          const r = await fetch(`${pythonBaseUrl}/chat`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ text: `consejo: ${asunto}` }),
          });
          if (r.ok) {
            const data = await r.json() as { reply: string };
            broadcast({ type: "chat", role: "assistant", text: data.reply });
          }
        } catch {/* fallback */ }
        return;
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

  function simulateTtsDecay(steps = 30) {
    let i = 0;
    const id = setInterval(() => {
      broadcast({ type: "tts/level", v: 0.4 + Math.random() * 0.5 });
      if (++i >= steps) {
        clearInterval(id);
        broadcast({ type: "tts/level", v: 0 });
        broadcast({ type: "state", value: "idle" });
      }
    }, 100);
  }

  // Heartbeat
  setInterval(() => {
    broadcast({
      type: "log",
      level: "INFO",
      message: `HUB :: ${new Date().toLocaleTimeString("es-ES", { hour12: false })} · JARVIS UNIFICADO`,
    });
  }, 15_000);
}
