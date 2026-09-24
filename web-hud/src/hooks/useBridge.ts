import { useEffect, useRef } from "react";
import { useHud } from "../store/hudStore";

/**
 * WebSocket bridge to the Node.js BFF server (server/index.ts).
 *
 * Wire protocol (JSON):
 *   client → server:
 *     { type: "chat",             text: string }
 *     { type: "email/list" }
 *     { type: "email/read",       id: string }
 *     { type: "demo/create",      nombre, industria, descripcion, id }
 *     { type: "consejo/deliberar", asunto: string }
 *
 *   server → client:
 *     { type: "state",        value: HudState }
 *     { type: "log",          level, message }
 *     { type: "chat",         role: "assistant"|"system"|"user", text }
 *     { type: "media",        media: MediaItem }
 *     { type: "remote",       op: RemoteOp | null }
 *     { type: "tts/level",    v: number }
 *     { type: "demo/update",  id, status, url? }
 */
export function useBridge() {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let alive = true;
    let retry = 0;

    const connect = () => {
      const url =
        (location.protocol === "https:" ? "wss://" : "ws://") +
        (import.meta.env.VITE_WS_URL ?? `${location.host}/ws`);

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        retry = 0;
        useHud.getState().setConnected(true);
        useHud.getState().pushLog({ level: "OK", message: "Enlace WebSocket establecido con el núcleo unificado." });
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          const s = useHud.getState();
          switch (msg.type) {
            case "state":
              s.setState(msg.value);
              break;
            case "log":
              s.pushLog({ level: msg.level ?? "INFO", message: msg.message });
              break;
            case "chat":
              // Special tagged messages for email data
              if (msg.text?.startsWith("[EMAIL_DATA]")) {
                try {
                  const emails = JSON.parse(msg.text.replace("[EMAIL_DATA]", ""));
                  s.setEmails(emails);
                  s.setEmailsLoading(false);
                } catch {
                  s.pushChat({ role: msg.role ?? "assistant", text: msg.text });
                }
              } else {
                s.pushChat({ role: msg.role ?? "assistant", text: msg.text });
              }
              break;
            case "media":
              s.addMedia(msg.media);
              break;
            case "remote":
              if (msg.op) s.triggerRemote(msg.op);
              else useHud.setState({ remoteOp: null });
              break;
            case "tts/level":
              s.setTtsLevel(msg.v ?? 0);
              break;
            case "demo/update":
              s.updateDemo(msg.id, { status: msg.status, url: msg.url });
              if (msg.status === "ready") {
                s.pushLog({ level: "OK", message: `Demo lista: ${msg.url}` });
              }
              break;
            case "consejo/result":
              if (msg.data) {
                s.pushConsejo(msg.data);
                s.setConsejoLoading(false);
              }
              break;
          }
        } catch (e) {
          // ignore malformed
        }
      };

      ws.onclose = () => {
        useHud.getState().setConnected(false);
        if (!alive) return;
        retry = Math.min(retry + 1, 6);
        window.setTimeout(connect, 500 * 2 ** retry);
      };

      ws.onerror = () => { ws.close(); };
    };

    connect();

    // expose a tiny helper globally for non-hook callers (e.g. CommandDock)
    (window as any).__jarvisSend = (payload: unknown) => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
    };

    return () => {
      alive = false;
      wsRef.current?.close();
    };
  }, []);
}

export const send = (payload: unknown) => (window as any).__jarvisSend?.(payload);
