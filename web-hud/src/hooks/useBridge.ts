import { useEffect, useRef } from "react";
import { useHud } from "../store/hudStore";

/**
 * WebSocket bridge to the Node.js BFF server (server/index.ts), which in turn
 * proxies to the Python `jarvis_core.py` runtime.
 *
 * Wire protocol (JSON):
 *   client → server:
 *     { type: "chat",      text: string }
 *     { type: "tts/play",  url:  string }
 *     { type: "wake" }
 *
 *   server → client:
 *     { type: "state",     value: HudState }
 *     { type: "log",       level, message }
 *     { type: "chat",      role: "assistant"|"system", text }
 *     { type: "media",     media: MediaItem }
 *     { type: "remote",    op: RemoteOp | null }
 *     { type: "tts/level", v: number }
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
        useHud.getState().pushLog({ level: "OK", message: "Enlace WebSocket establecido con el núcleo." });
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
              s.pushChat({ role: msg.role ?? "assistant", text: msg.text });
              break;
            case "media":
              s.addMedia(msg.media);
              break;
            case "remote":
              if (msg.op) s.triggerRemote(msg.op);
              else s.triggerRemote && (useHud.setState({ remoteOp: null }));
              break;
            case "tts/level":
              s.setTtsLevel(msg.v ?? 0);
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

      ws.onerror = () => {
        ws.close();
      };
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
