#!/usr/bin/env python3
"""
ultron_web_backend.py — Backend HTTP para la interfaz web de ULTRON
====================================================================
API idéntica al jarvis_web_backend.py pero instancia UltronCore
en lugar de JarvisCore. Puerto por defecto: 8766 (distinto al de Jarvis).

Endpoints:
  GET  /health         → { ok, agent, llm, mode }
  POST /chat           { text } → { reply }
  POST /tts            { text } → audio/mpeg bytes
  GET  /telemetry      → { cpu, ram, ram_total, net, uptime }
  GET  /status         → { agent, history_len, modo_agresivo, db }
"""
from __future__ import annotations
import io, os, sys, time, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import psutil
except Exception:
    psutil = None

_core = None
_core_lock = threading.Lock()


def _get_core():
    global _core
    if _core is not None:
        return _core
    with _core_lock:
        if _core is None:
            try:
                from ultron_core import UltronCore
                _core = UltronCore(log_callback=lambda m: print(f"[ULTRON-CORE] {m}"))
            except Exception as e:
                print(f"[ultron-backend] ULTRON core no disponible: {e}")
                _core = False
    return _core or None


class UltronHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[ultron-backend] {self.address_string()} — {fmt % args}")

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n == 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        core = _get_core()

        if path == "/health":
            self._json(200, {
                "ok": True,
                "agent": "ULTRON",
                "llm": os.getenv("ULTRON_MODEL") or os.getenv("QWEN_MODEL", "qwen3:4b-instruct"),
                "mode": "OFENSIVA" if (core and getattr(core, "_modo_agresivo", False)) else "NORMAL",
                "core_loaded": bool(core),
            })
            return

        if path == "/telemetry":
            cpu = psutil.cpu_percent() if psutil else 0
            mem = psutil.virtual_memory() if psutil else None
            net = psutil.net_io_counters() if psutil else None
            self._json(200, {
                "cpu": cpu,
                "ram": (mem.used / 1024 ** 3) if mem else 0,
                "ram_total": (mem.total / 1024 ** 3) if mem else 0,
                "net_sent": (net.bytes_sent / 1024 ** 2) if net else 0,
                "net_recv": (net.bytes_recv / 1024 ** 2) if net else 0,
                "uptime": time.time(),
            })
            return

        if path == "/status":
            self._json(200, {
                "agent": "ULTRON",
                "history_len": len(core.history) if core else 0,
                "modo_agresivo": getattr(core, "_modo_agresivo", False) if core else False,
                "db": "ultron_memory.db",
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            return

        self._json(404, {"error": "endpoint_not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()
        core = _get_core()

        if path == "/chat":
            text = (body.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "empty_text"})
            if not core:
                return self._json(200, {
                    "reply": f"ULTRON offline. Instrucción recibida: «{text}». Reconectando...",
                    "media": None,
                })
            try:
                reply = core.ask(text) if hasattr(core, "ask") else "Sin método ask()."
                return self._json(200, {"reply": reply, "media": None})
            except Exception as e:
                return self._json(500, {"error": "core_failed", "detail": str(e)})

        if path == "/tts":
            text = (body.get("text") or "").strip()
            if not text or not core or not hasattr(core, "synthesize_to_bytes"):
                self.send_response(204)
                self.end_headers()
                return
            try:
                audio = core.synthesize_to_bytes(text)
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(audio)
            except Exception as e:
                self._json(500, {"error": "tts_failed", "detail": str(e)})
            return

        self._json(404, {"error": "endpoint_not_found"})


def main():
    port = int(os.getenv("ULTRON_PORT", "8766"))
    addr = ("0.0.0.0", port)
    # Pre-cargar el núcleo en un hilo para no bloquear el arranque del servidor
    threading.Thread(target=_get_core, daemon=True).start()
    httpd = ThreadingHTTPServer(addr, UltronHandler)
    print(f"""
╔══════════════════════════════════════════════════╗
║  ULTRON WEB BACKEND                             ║
║  http://localhost:{port}                          ║
╚══════════════════════════════════════════════════╝
""")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
        print("[ultron-backend] Servidor detenido.")


if __name__ == "__main__":
    main()
