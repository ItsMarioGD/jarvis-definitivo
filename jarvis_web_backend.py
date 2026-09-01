"""
jarvis_web_backend.py — minimal Python HTTP server exposing the
existing `jarvis_core.JarvisCore` over REST for the new Node BFF.

Endpoints:
  GET  /health         → { ok, llm, voice_id, mode }
  POST /chat           { text } → { reply, media?, tts_url? }
  POST /tts            { text } → audio/mpeg bytes
  GET  /telemetry      → { cpu, ram, ram_total, net, uptime }

Run with:
  python jarvis_web_backend.py
  # PORT defaults to 8765
"""
from __future__ import annotations
import io, os, time, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

try:
    import psutil
except Exception:
    psutil = None

# Lazy import of the existing core (do NOT fail the server if voice libs are
# missing; the HUD will fall back to text-only mode).
_core = None
_core_lock = threading.Lock()
def _get_core():
    global _core
    if _core is not None:
        return _core
    with _core_lock:
        if _core is None:
            try:
                from jarvis_core import JarvisCore
                _core = JarvisCore(log_callback=lambda m: None)
            except Exception as e:
                print(f"[backend] core no disponible: {e}")
                _core = False
    return _core or None


def _preguntar(core, text: str) -> str:
    """Pregunta al nucleo por su API real, sin hablar por el PC."""
    import inspect
    fn = getattr(core, "process_text_stream", None) or getattr(core, "ask", None)
    if fn is None:
        return "Señor, mi núcleo no expone ningún método de conversación."
    try:
        acepta = "speak_server" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        acepta = False
    resp = fn(text, speak_server=False) if acepta else fn(text)
    return resp or "Señor, no he entendido."


def _tts_bytes(text: str):
    """MP3 de ElevenLabs, o None si no hay clave/voz configurada."""
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    if not key or "tu_api" in key or not voice:
        return None
    try:
        import requests
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            json={"text": text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
            headers={"Accept": "audio/mpeg", "Content-Type": "application/json",
                     "xi-api-key": key},
            timeout=(5, 30))
        if r.status_code == 200:
            return r.content
        print(f"[backend] elevenlabs {r.status_code}")
    except Exception as e:
        print(f"[backend] tts fallo: {e}")
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        print(f"[backend] {self.address_string()} - {fmt%args}")

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
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
        if path == "/health":
            core = _get_core()
            self._json(200, {
                "ok": True,
                "llm": os.getenv("QWEN_MODEL", "qwen3:4b-instruct"),
                "voice_id": os.getenv("ELEVENLABS_VOICE_ID", ""),
                "mode": os.getenv("JARVIS_MODE", "full"),
                "core_loaded": bool(core),
            })
            return
        if path == "/telemetry":
            cpu = psutil.cpu_percent() if psutil else 0
            mem = psutil.virtual_memory() if psutil else None
            self._json(200, {
                "cpu": cpu,
                "ram": (mem.used / 1024**3) if mem else 0,
                "ram_total": (mem.total / 1024**3) if mem else 0,
                "net": 0,
                "uptime": time.time(),
            })
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()
        core = _get_core()

        if path == "/chat":
            text = (body.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "empty_text"})
            if not core:
                # Offline / dev fallback so the HUD always has something to show.
                return self._json(200, {
                    "reply": f"Recibido, señor: «{text}». (Núcleo Python no conectado — modo demo.)",
                    "media": None,
                    "tts_url": None,
                })
            try:
                # JarvisCore expone process_text_stream, no ask(): con el
                # nombre viejo este endpoint contestaba siempre lo mismo.
                # speak_server=False para no hablar por los altavoces del PC
                # cuando la peticion viene del movil.
                reply = _preguntar(core, text)
                return self._json(200, {"reply": reply, "media": None, "tts_url": None})
            except Exception as e:
                print(f"[backend] /chat fallo: {e}")
                return self._json(500, {"error": "core_failed", "detail": str(e)})

        if path == "/tts":
            text = (body.get("text") or "").strip()[:2000]
            if not text:
                self.send_response(204); self.end_headers(); return
            # JarvisCore no tiene synthesize_to_bytes (solo reproduce en el PC),
            # asi que el MP3 para el navegador se pide a ElevenLabs igual que
            # hace /api/speak del servidor Flask.
            audio = _tts_bytes(text)
            if not audio:
                self.send_response(204); self.end_headers(); return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(audio)
            except Exception as e:
                print(f"[backend] /tts fallo: {e}")
            return

        self._json(404, {"error": "not_found"})


def main():
    port = int(os.getenv("PORT", "8765"))
    addr = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(addr, Handler)
    print(f"[backend] Jarvis Web Backend escuchando en http://{addr[0]}:{addr[1]}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()

if __name__ == "__main__":
    main()
