#!/usr/bin/env python3
"""
ultron_interface/app.py — Servidor web de ULTRON
=================================================
Hermano gemelo de web_interface/app.py (Jarvis), pero con identidad Ultron:
mismo stack Flask + SocketIO, endpoints paralelos, memoria aislada
(ultron_memory.db), voz configurable vía ULTRON_VOICE_ID y modo por defecto
OFENSIVA (sin confirmación en acciones).

Rutas clave (compatibles con el HUD móvil):
  GET  /                  → index.html brutalista rojo/negro
  GET  /mobile            → vista móvil
  GET  /dashboard         → dashboard de host
  GET  /centro            → centro de mando móvil
  GET  /pair              → emparejamiento QR
  GET  /qr                → código QR
  GET  /health            → estado del núcleo
  GET  /status            → snapshot del agente
  GET  /stats             → métricas del host
  GET  /history           → historial reciente
  POST /chat              { text, token? } → { reply }
  POST /cmd               { texto, token? }
  POST /voice             { audio } con token
  POST /mode/<modo>       alterna OFENSIVA/NORMAL
  POST /purge             borra historial (limpieza cognitiva)
"""
import os
import sys
import json
import time
import socket
import secrets
import threading
import subprocess
import importlib
import requests

# Path raíz del proyecto
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Forzar ULTRON_MODE antes de cargar nada
os.environ.setdefault("ULTRON_MODE", "1")
os.environ.setdefault("JARVIS_TTS_FALLBACK", "windows")

# Cargar .env (parseo manual mínimo)
_ENV_PATH = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_PATH):
    try:
        for line in open(_ENV_PATH, "r", encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass

# Flask + SocketIO
try:
    from flask import Flask, jsonify, send_from_directory, request, send_file, render_template_string, Response
    from flask_socketio import SocketIO, emit
except Exception as e:
    print(f"[ULTRON-WEB] Flask no disponible: {e}")
    raise

# ── Configuración Ultron ─────────────────────────────────────────────────────
PORT = int(os.getenv("ULTRON_PORT", "8766"))
HOST = os.getenv("ULTRON_HOST", "0.0.0.0")
ULTRON_MODEL = os.getenv("ULTRON_MODEL", "") or os.getenv("QWEN_MODEL", "qwen3:4b-instruct")
os.environ["QWEN_MODEL"] = ULTRON_MODEL

# Auth token independiente (no compartir con Jarvis)
_AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ultron_auth")


def _get_token() -> str:
    try:
        t = open(_AUTH_FILE, "r", encoding="utf-8").read().strip()
        if t and len(t) >= 4:
            return t
    except Exception:
        pass
    t = f"{secrets.randbelow(1000000):06d}"
    try:
        with open(_AUTH_FILE, "w", encoding="utf-8") as f:
            f.write(t)
    except Exception:
        pass
    return t


AUTH_TOKEN = _get_token()


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith(("127.", "169.254")):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def _auth_ok(token: str) -> bool:
    return bool(token) and token == AUTH_TOKEN


# ── Núcleo Ultron (carga perezosa) ───────────────────────────────────────────
class _UltronProxy:
    def __init__(self):
        self._c = None
        self._err = None
        self._next = 0.0
        self._lock = threading.Lock()

    def _load(self):
        if self._c is not None:
            return self._c
        now = time.time()
        if self._err is not None and now < self._next:
            return None
        with self._lock:
            if self._c is not None:
                return self._c
            try:
                from ultron_core import UltronCore
                self._c = UltronCore(log_callback=lambda m: print(f"[ULTRON] {m}"))
                self._err = None
                print("[ULTRON-WEB] Núcleo Ultron cargado (perezoso).")
            except Exception as e:
                self._err = str(e)
                self._next = time.time() + 30
                print(f"[ULTRON-WEB] No se pudo cargar UltronCore: {e}")
                self._c = None
            return self._c

    @property
    def error(self):
        return self._err

    def __bool__(self):
        return self._load() is not None

    def __getattr__(self, name):
        c = self._load()
        if c is None:
            raise AttributeError(name)
        return getattr(c, name)


core = _UltronProxy()


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=os.path.dirname(os.path.abspath(__file__)))
app.config["SECRET_KEY"] = AUTH_TOKEN
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _history_messages(limit: int = 40):
    try:
        h = getattr(core, "history", []) or []
        msgs = [m for m in h if m.get("role") in ("user", "assistant")]
        return [{"role": m.get("role"), "text": m.get("content", "")} for m in msgs[-limit:]]
    except Exception:
        return []


def _req_token() -> str:
    t = request.headers.get("X-Token") or request.args.get("token") or ""
    if t:
        return t
    try:
        t = (request.get_json(silent=True) or {}).get("token") or ""
    except Exception:
        t = ""
    return t or request.form.get("token", "") or ""


def _stats() -> dict:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.3)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        net = psutil.net_io_counters()
        top = []
        for p in sorted(
            psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info["cpu_percent"] or 0, reverse=True,
        )[:5]:
            top.append({
                "nombre": p.info["name"] or "?",
                "cpu": round(p.info["cpu_percent"] or 0, 1),
                "mem": round(p.info["memory_percent"] or 0, 1),
            })
        temp = None
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty CurrentTemperature"],
                capture_output=True, text=True, timeout=8, creationflags=0x08000000,
            )
            v = (r.stdout or "").strip()
            if v:
                temp = round((int(v) / 10) - 273.15, 1)
        except Exception:
            pass
        return {
            "cpu": cpu, "ram_pct": ram.percent,
            "ram_used_gb": round(ram.used / 1073741824, 1),
            "ram_total_gb": round(ram.total / 1073741824, 1),
            "disco_libre_gb": round(disk.free / 1073741824, 1),
            "disco_total_gb": round(disk.total / 1073741824, 1),
            "net_mb": round(net.bytes_recv / 1048576, 1),
            "temp": temp, "top": top,
            "hora": time.strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"error": str(e)}


# ── Rutas principales ────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/mobile")
def mobile():
    resp = send_from_directory(".", "mobile.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/dashboard")
def dashboard():
    return send_from_directory(".", "dashboard.html")


@app.route("/centro")
def centro():
    return send_from_directory(".", "centro.html")


@app.route("/pair")
def pair():
    return send_from_directory(".", "pair.html")


@app.route("/qr")
def qr():
    try:
        import qrcode
        from io import BytesIO
        url = f"http://{_local_ip()}:{PORT}/mobile?token={AUTH_TOKEN}"
        img = qrcode.make(url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/pair_info")
def pair_info():
    return jsonify({
        "pin": AUTH_TOKEN,
        "url": f"http://{_local_ip()}:{PORT}/mobile",
        "agente": "ULTRON",
        "modo": "OFENSIVA" if getattr(core, "_modo_agresivo", False) else "NORMAL",
    })


# ── API REST ──────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    c = core._load() if core else None
    return jsonify({
        "ok": True,
        "agente": "ULTRON",
        "llm": ULTRON_MODEL,
        "voice_id": os.getenv("ELEVENLABS_VOICE_ID", ""),
        "modo": "OFENSIVA" if getattr(c, "_modo_agresivo", False) else "NORMAL",
        "core_loaded": c is not None,
        "core_error": core.error if hasattr(core, "error") else None,
        "ts": int(time.time()),
    })


@app.route("/status")
def status():
    c = core._load() if core else None
    st = c.ultron_status() if c else {}
    return jsonify({
        "agente": "ULTRON",
        "history_len": len(getattr(c, "history", []) or []),
        "modo_agresivo": getattr(c, "_modo_agresivo", False),
        "ultimo_comando": st.get("ultimo_comando", ""),
        "ultimo_tokens": st.get("ultimo_tokens", 0),
        "ultima_latencia_ms": st.get("ultima_latencia_ms", 0),
        "uptime_s": st.get("uptime_s", 0),
        "modelo": ULTRON_MODEL,
        "db": "ultron_memory.db",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/stats")
def stats():
    return jsonify(_stats())


@app.route("/history")
def history():
    return jsonify({"messages": _history_messages()})


@app.route("/debug/core_status")
def debug_core_status():
    """Endpoint para diagnosticar errores de carga del núcleo Ultron."""
    try:
        c = core._load()
        if c:
            return jsonify({'loaded': True, 'core_type': type(c).__name__, 'skills': hasattr(c, 'skills'), 'pc': hasattr(c, 'pc'), 'ultron_skills': hasattr(c, 'ultron_skills')})
        else:
            return jsonify({'loaded': False, 'error': core.error, 'next_retry': core._next})
    except Exception as e:
        import traceback
        return jsonify({'loaded': False, 'error': str(e), 'trace': traceback.format_exc()[:1000]})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or data.get("texto") or "").strip()
    if not text:
        return jsonify({"error": "texto vacío"}), 400
    if not core:
        return jsonify({
            "reply": f"ULTRON offline. Instrucción recibida: «{text}». Núcleo no cargado.",
        }), 503
    t0 = time.time()
    speak_server = bool(data.get("speak_server", True))
    try:
        # UltronCore.chat instrumenta latencia/tokens en _ultron_stats
        reply = core.chat(text, speak_server=speak_server) if hasattr(core, "chat") else "sin método chat()"
        return jsonify({
            "reply": reply,
            "latencia_ms": int((time.time() - t0) * 1000),
        })
    except Exception as e:
        return jsonify({"error": "core_failed", "detail": str(e)}), 500


@app.route("/cmd", methods=["POST"])
def cmd():
    if not _auth_ok(_req_token()):
        return jsonify({"error": "token invalido"}), 403
    data = request.get_json(silent=True) or {}
    text = (data.get("texto") or data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "texto vacío"}), 400
    if not core:
        return jsonify({"error": "núcleo no disponible"}), 503
    try:
        reply = core.chat(text)
        return jsonify({"texto": text, "respuesta": reply[:2000]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/mode/<modo>", methods=["POST"])
def set_mode(modo):
    """Alterna entre OFENSIVA (autonomía total) y NORMAL (modo conservador)."""
    c = core._load() if core else None
    if not c:
        return jsonify({"error": "núcleo no disponible"}), 503
    if modo not in ("OFENSIVA", "NORMAL"):
        return jsonify({"error": "modo invalido (OFENSIVA|NORMAL)"}), 400
    c._modo_agresivo = (modo == "OFENSIVA")
    msg = ("Modo OFENSIVA activado. Sin confirmación. Ejecuto todo."
           if c._modo_agresivo
           else "Modo NORMAL. Confirmaré acciones críticas.")
    try:
        c.tts_queue.put(msg)
    except Exception:
        pass
    return jsonify({"modo": modo, "mensaje": msg})


@app.route("/purge", methods=["POST"])
def purge():
    if not _auth_ok(_req_token()):
        return jsonify({"error": "token invalido"}), 403
    if not core:
        return jsonify({"error": "núcleo no disponible"}), 503
    try:
        msg = core.limpiar_memoria()
        return jsonify({"ok": True, "mensaje": msg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Voz (STT + TTS) ──────────────────────────────────────────────────────────
_whisper_lock = threading.Lock()
_whisper_model = None


def _transcribir(ruta_wav: str) -> str:
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            except Exception:
                _whisper_model = False
    if not _whisper_model:
        return ""
    segs, _ = _whisper_model.transcribe(ruta_wav, language="es")
    return "".join(s.text for s in segs).strip()


@app.route("/voice", methods=["POST"])
def voice():
    if not _auth_ok(_req_token()):
        return jsonify({"error": "token invalido"}), 403
    if not core:
        return jsonify({"error": "núcleo no disponible"}), 503
    import tempfile, uuid
    f = request.files.get("audio") if request.files else None
    if f is None:
        blob = request.get_data()
        if not blob:
            return jsonify({"error": "sin audio"}), 400
        ruta_in = os.path.join(tempfile.gettempdir(), f"ultron_{uuid.uuid4().hex}.webm")
        with open(ruta_in, "wb") as fh:
            fh.write(blob)
    else:
        ruta_in = os.path.join(tempfile.gettempdir(), f"ultron_{uuid.uuid4().hex}.webm")
        f.save(ruta_in)
    ruta_wav = os.path.join(tempfile.gettempdir(), f"ultron_{uuid.uuid4().hex}.wav")
    try:
        ff = "ffmpeg"
        r = subprocess.run(
            [ff, "-y", "-i", ruta_in, "-ar", "16000", "-ac", "1", ruta_wav],
            capture_output=True, timeout=60,
        )
        if r.returncode != 0 or not os.path.exists(ruta_wav):
            return jsonify({"error": "no pude convertir audio"}), 500
        texto = _transcribir(ruta_wav)
        if not texto:
            return jsonify({"texto": "", "respuesta": "No detecté voz, humano."})
        reply = core.chat(texto)
        return jsonify({"texto": texto, "respuesta": reply[:2000]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        for r in (ruta_in, ruta_wav):
            try:
                if r and os.path.exists(r):
                    os.remove(r)
            except Exception:
                pass


@app.route("/tts", methods=["POST"])
def tts():
    """Síntesis local rápida (sin ElevenLabs): usa ElevenLabs si el core lo
    expone; si no, devuelve 204 (el cliente puede usar el speech del navegador)."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text or len(text) > 1000:
        return jsonify({"error": "texto invalido"}), 400
    if not core:
        return jsonify({"error": "núcleo no disponible"}), 503
    try:
        if hasattr(core, "synthesize_and_play"):
            core.synthesize_and_play(text)
            return jsonify({"status": "ok"})
        return jsonify({"status": "no_tts"}), 204
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Síntesis para el navegador (streaming ElevenLabs) ─────────────────────────
@app.route("/api/speak", methods=["POST"])
def api_speak():
    """Sintetiza el texto con ElevenLabs y devuelve el MP3 para reproducir
    en el navegador (agente conversacional de voz)."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text or len(text) > 2000:
        return jsonify({"error": "texto invalido"}), 400

    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key or "tu_api" in key:
        return jsonify({"error": "no_key"}), 502

    # Cadena de voces: voz de Ultron primero, luego la voz global de respaldo
    voices = []
    _uv = os.getenv("ULTRON_VOICE_ID", "").strip()
    _gv = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    if _uv:
        voices.append(_uv)
    if _gv and _gv not in voices:
        voices.append(_gv)
    if not voices:
        return jsonify({"error": "no_voice"}), 502

    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        # Tono conqueror: más expresividad/drama, menos estabilidad plana
        "voice_settings": {"stability": 0.35, "similarity_boost": 0.85},
    }
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key,
    }
    last_err = None
    for voice in voices:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream"
        try:
            r = requests.post(url, json=payload, headers=headers, stream=True, timeout=(5, 30))
            if r.status_code == 200:
                return Response(
                    r.raw, mimetype="audio/mpeg",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
                )
            last_err = r.status_code
        except Exception as e:
            last_err = str(e)
    return jsonify({"error": f"elevenlabs {last_err}"}), 502


# ── SocketIO: chat en tiempo real ────────────────────────────────────────────
@socketio.on("connect")
def on_connect(auth):
    if not auth or not _auth_ok(auth.get("token", "")):
        return False
    emit("connected", {"ok": True, "agente": "ULTRON"})
    try:
        emit("history", {"messages": _history_messages()})
    except Exception:
        pass


@socketio.on("send_message")
def on_send_message(data):
    text = ((data or {}).get("text") or "").strip()
    if not text or len(text) > 2000:
        return
    emit("user_message", {"text": text}, broadcast=True)
    if not core:
        emit("receive_message", {"text": "Núcleo ULTRON no disponible."}, broadcast=True)
        return
    emit("typing", {}, broadcast=True)

    def work():
        try:
            resp = core.chat(text) or ""
            with app.app_context():
                socketio.emit("receive_message", {"text": resp[:2000]}, to=None)
        except Exception as e:
            with app.app_context():
                socketio.emit(
                    "receive_message",
                    {"text": f"Fallo en pipeline cognitivo: {str(e)[:160]}"},
                    to=None,
                )

    threading.Thread(target=work, daemon=True).start()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    ip = _local_ip()
    print("=" * 60)
    print(f"  U L T R O N   W E B   S E R V E R")
    print(f"  Modelo:    {ULTRON_MODEL}")
    print(f"  Local:     http://127.0.0.1:{PORT}")
    print(f"  Red:       http://{ip}:{PORT}")
    print(f"  Móvil:     http://{ip}:{PORT}/mobile")
    print(f"  Centro:    http://{ip}:{PORT}/centro")
    print(f"  Dashboard: http://{ip}:{PORT}/dashboard")
    print(f"  QR:        http://{ip}:{PORT}/pair")
    print(f"  Token:     {AUTH_TOKEN}")
    print(f"  Modo:      OFENSIVA")
    print("=" * 60)
    # Probe de puerto ocupado
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            print(f"[!] Puerto {PORT} ya en uso. Abortando.")
            sys.exit(0)
    finally:
        s.close()
    socketio.run(app, host=HOST, port=PORT, debug=False,
                 use_reloader=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
