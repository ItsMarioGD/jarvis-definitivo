#!/usr/bin/env python3
"""
JARVIS Web Server - Acceso móvil + chat en tiempo real (Fase 1+2)
=================================================================
- REST clásico (compatible con el HUD de escritorio)
- SocketIO: chat en tiempo real con indicador "escribiendo"
- Autenticación por token (archivo .jarvis_auth)
- QR de emparejamiento para el teléfono
- Servidor accesible desde la red local (0.0.0.0)
"""
import sys
import os
import threading
import time
import json
import socket
import secrets
import requests

# Agregar path para importar jarvis_core y generator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jarvis_config

# ── Cargar .env (claves ElevenLabs, etc.) ──
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_ROOT, '.env')
if os.path.exists(_ENV_PATH):
    try:
        for _line in open(_ENV_PATH, 'r', encoding='utf-8'):
            _line = _line.strip()
            if not _line or _line.startswith('#') or '=' not in _line:
                continue
            _k, _v = _line.split('=', 1)
            _k = _k.strip(); _v = _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ:
                os.environ[_k] = _v
    except Exception:
        pass

from flask import Flask, jsonify, send_from_directory, request, send_file, render_template_string, Response

# ── Agencia de especialistas (índice en memoria, se carga una sola vez) ──
_AGENTES_IA = None
def _agentes_ia():
    global _AGENTES_IA
    if _AGENTES_IA is None:
        try:
            from agentes_ia import AgentesIA as _AI
            _AGENTES_IA = _AI(log=lambda *a: None)
        except Exception as _e:
            print(f"[API] Agencia no disponible: {_e}")
            _AGENTES_IA = False
    return _AGENTES_IA or None
from flask_socketio import SocketIO, emit

# ── AUTENTICACIÓN (token persistente) ─────────────────────────────────────────
AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.jarvis_auth')


def get_token():
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            t = f.read().strip()
            if t and t.isdigit() and len(t) == 6:
                return t
    except Exception:
        pass
    t = f"{secrets.randbelow(1000000):06d}"
    try:
        with open(AUTH_FILE, 'w', encoding='utf-8') as f:
            f.write(t)
    except Exception:
        pass
    return t


AUTH_TOKEN = get_token()


def _local_ip():
    """IP de la red local real (Wi-Fi/Ethernet). Evita la IP virtual de
    Tailscale (100.x): el teléfono sin la app no puede alcanzarla."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith(("127.", "169.254")):
            return ip
    except Exception:
        pass
    try:
        import subprocess
        ts = jarvis_config.TAILSCALE_EXE
        if ts and os.path.exists(ts):
            out = subprocess.run([ts, 'ip', '-4'], capture_output=True, text=True, timeout=6)
            ip = (out.stdout or '').strip().splitlines()
            if ip:
                return ip[0]
    except Exception:
        pass
    return "127.0.0.1"


def _tailscale_dns():
    """Nombre MagicDNS del PC (p. ej. desktop-xxx.tailXXXX.ts.net) o None."""
    try:
        import subprocess, json as _json
        ts = jarvis_config.TAILSCALE_EXE
        if ts and os.path.exists(ts):
            out = subprocess.run([ts, 'status', '--json'], capture_output=True, text=True, timeout=8)
            data = _json.loads(out.stdout)
            return (data.get('Self', {}).get('DNSName') or '').rstrip('.') or None
    except Exception:
        pass
    return None


def _pair_url():
    """URL pública para el teléfono. Prioriza la red local (mismo Wi-Fi);
    Tailscale HTTPS solo si la LAN no responde (p. ej. fuera de casa)."""
    ip = _local_ip()
    port = jarvis_config.PORT
    try:
        import urllib.request
        urllib.request.urlopen(f"http://{ip}:{port}/mobile", timeout=3)
        return f"http://{ip}:{port}/mobile"
    except Exception:
        pass
    try:
        import urllib.request
        dns = _tailscale_dns()
        if dns:
            try:
                urllib.request.urlopen(f"https://{dns}/mobile", timeout=3)
                return f"https://{dns}/mobile"
            except Exception:
                pass
        urllib.request.urlopen(f"https://{ip}/mobile", timeout=3)
        return f"https://{ip}/mobile"
    except Exception:
        return f"http://{ip}:{port}/mobile"


def _auth_ok(token):
    return token == AUTH_TOKEN


# ── NÚCLEO JARVIS (carga perezosa + autocurable) ─────────────────────────────
# Cargamos el núcleo bajo demanda (en la primera petición) en vez de hacerlo en
# el arranque. Así, si falla al iniciar (p. ej. un error transitorio), el
# servidor NO queda muerto: reintenta hasta conseguirlo y deja ver el error
# real en /api/status para poder diagnosticarlo.
import threading as _threading
class _CoreProxy:
    def __init__(self):
        self._c = None
        self._err = None
        self._next = 0.0
        self._lock = _threading.Lock()

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
                from jarvis_core import JarvisCore
                self._c = JarvisCore()
                self._err = None
                print("Nucleo JARVIS cargado (perezoso)")
            except Exception as e:
                self._err = str(e)
                self._next = time.time() + 30
                print(f"Error cargando nucleo: {e}")
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

core = _CoreProxy()

try:
    from jarvis_generator import JarvisGenerator
    generator = JarvisGenerator()
    print("Generador universal JARVIS cargado")
except Exception as e:
    print(f"Error cargando generador: {e}")
    generator = None

app = Flask(__name__, static_folder='.')
app.config['SECRET_KEY'] = AUTH_TOKEN
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


def _allowed_ips():
    try:
        return json.load(open(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                           "Prefs", "allowed_ips.json"), encoding="utf-8")) or []
    except Exception:
        return []


@app.before_request
def filtro_ips():
    permitidas = _allowed_ips()
    if not permitidas:
        return None
    if request.remote_addr in permitidas or request.remote_addr in ("127.0.0.1", "::1"):
        return None
    if request.path in ("/pair", "/qr", "/allow_my_ip", "/mobile", "/"):
        return None
    # El PIN de emparejamiento es una credencial mas fuerte que la IP: sin esto,
    # al cambiar la IP del movil (DHCP) el telefono cargaba /mobile pero el
    # handshake de Socket.IO se rechazaba con un 403 mudo y el chat no respondia.
    # Solo cabecera/query: no tocamos el cuerpo de la peticion aqui para no
    # forzar el parseo de subidas grandes en cada before_request.
    if _auth_ok(request.headers.get('X-Token') or request.args.get('token') or ''):
        return None
    # Socket.IO ya valida el token en on_connect; dejarlo pasar no abre nada.
    if request.path.startswith('/socket.io'):
        return None
    print(f"[auth] IP no autorizada: {request.remote_addr} -> {request.path}")
    return jsonify({'error': 'IP no autorizada', 'ip': request.remote_addr,
                    'ayuda': 'Abre /pair en el PC y vuelve a emparejar el teléfono.'}), 403


def _history_messages(limite=40):
    """Últimos mensajes de la conversación (sin system)."""
    try:
        h = getattr(core, 'history', []) or []
        msgs = [m for m in h if m.get('role') in ('user', 'assistant')]
        return [{'role': m.get('role'), 'text': m.get('content', '')} for m in msgs[-limite:]]
    except Exception:
        return []


# ── RUTAS REST (compatibilidad con el HUD de escritorio) ──────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/mobile')
def mobile():
    resp = send_from_directory('.', 'mobile.html')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/pair_info')
def pair_info():
    """Datos para el modal de emparejamiento de la interfaz del PC."""
    return jsonify({
        'pin': AUTH_TOKEN,
        'url': _pair_url(),
        'dns': _tailscale_dns() or '',
    })


@app.route('/notify', methods=['POST'])
def notify_push():
    """Push interno: reenvía avisos de Jarvis al móvil conectado."""
    remote = request.remote_addr or ''
    if remote not in ('127.0.0.1', '::1', jarvis_config.LOCAL_IP):
        return jsonify({'error': 'forbidden'}), 403
    try:
        data = request.get_json() or {}
        text = (data.get('text') or '').strip()[:500]
        if text:
            socketio.emit('notification', {'text': text}, to=None)
        return jsonify({'ok': True})
    except Exception:
        return jsonify({'error': 'bad'}), 400


@app.route('/capturas/<path:nombre>')
def capturas_publicas(nombre):
    return send_from_directory('capturas', nombre)


@app.route('/envios/<path:nombre>')
def envios_publicos(nombre):
    return send_from_directory('envios', nombre)


@app.route('/webhook/<clave>', methods=['GET', 'POST'])
def webhook_entrada(clave):
    try:
        wh = json.load(open(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                         "Prefs", "webhooks.json"), encoding="utf-8"))
    except Exception:
        wh = {}
    if clave not in wh:
        return jsonify({'error': 'webhook no encontrado'}), 404
    socketio.emit('notification', {'text': 'Webhook recibido, señor. Alguien llamó a su enlace.'}, to=None)
    return jsonify({'ok': True})


@app.route('/clipboard', methods=['POST'])
def clipboard_entrada():
    datos = request.get_json(silent=True) or {}
    texto = (datos.get('texto') or '').strip()
    if not texto:
        return jsonify({'ok': False, 'error': 'texto vacío'}), 400
    def _copiar():
        try:
            script = "Set-Clipboard -Value @'" + texto + "'@"
            subprocess.Popen(["powershell", "-NoProfile", "-Command", script],
                             creationflags=0x08000000)
        except Exception:
            pass
    threading.Thread(target=_copiar, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/camera')
def camera_view():
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>JARVIS - Cámara</title>
<style>body{background:#05070d;margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh}
img{max-width:100vw;max-height:100vh;border:3px solid #00d4ff55;border-radius:8px}
.hint{position:fixed;bottom:10px;left:0;right:0;text-align:center;color:#5a7a95;font-size:12px}</style></head>
<body><img src="/camera_feed" alt="Cámara JARVIS"><div class="hint">JARVIS - vista en vivo de la cámara</div></body></html>"""
    return render_template_string(html)


@app.route('/camera_feed')
def camera_feed():
    def gen():
        import cv2
        cap = None
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                yield b"--frame\r\nContent-Type: text/plain\r\n\r\ncamara no disponible\r\n"
                return
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if not ok:
                    continue
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
                time.sleep(0.08)
        except Exception:
            yield b"--frame\r\nContent-Type: text/plain\r\n\r\ncamara no disponible\r\n"
        finally:
            if cap:
                cap.release()
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ── ESCRIBIR IO (pantalla en vivo) ─────────────────────────────────────────────
@app.route('/screen')
def screen_view():
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>JARVIS - Escritorio</title>
<style>body{background:#05070d;margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh}
img{max-width:100vw;max-height:100vh;border:3px solid #00d4ff55;border-radius:8px}
.hint{position:fixed;bottom:10px;left:0;right:0;text-align:center;color:#5a7a95;font-size:12px}</style></head>
<body><img src="/screen_feed" alt="Escritorio JARVIS"><div class="hint">JARVIS - su escritorio en vivo</div></body></html>"""
    return render_template_string(html)


@app.route('/screen_feed')
def screen_feed():
    def gen():
        try:
            from PIL import ImageGrab
            import io
            while True:
                img = ImageGrab.grab()
                img = img.resize((img.width // 2, img.height // 2))
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=60)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.getvalue() + b"\r\n")
                time.sleep(0.12)
        except Exception:
            yield b"--frame\r\nContent-Type: text/plain\r\n\r\npantalla no disponible\r\n"
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ── TOUCHPAD VIRTUAL ───────────────────────────────────────────────────────────
@app.route('/touchpad')
def touchpad_view():
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>JARVIS - Touchpad</title>
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<style>
body{background:#0a1118;margin:0;font-family:Segoe UI,sans-serif;color:#e6edf3;height:100vh;display:flex;flex-direction:column}
#pad{flex:1;background:#12202e;border-bottom:1px solid #2a3f54;touch-action:none;display:flex;align-items:center;justify-content:center;color:#5a7a95}
#bar{display:flex;flex-wrap:wrap;gap:8px;padding:10px;background:#0d1620}
button{flex:1;min-width:64px;padding:12px 8px;border:none;border-radius:10px;background:#00b4d8;color:#04121c;font-weight:bold;font-size:14px}
button.g{background:#1b2c3d;color:#e6edf3}
#teclado{display:flex;gap:8px;padding:10px;background:#0d1620}
#teclado input{flex:1;padding:10px;border-radius:10px;border:1px solid #2a3f54;background:#12202e;color:#e6edf3}
</style></head>
<body>
<div id="pad">Mueva el dedo para mover el ratón</div>
<div id="bar">
  <button onclick="clic(1)">Clic</button>
  <button onclick="clic(2)">Doble</button>
  <button class="g" onclick="clic(3)">Der</button>
  <button class="g" onclick="rueda(120)">▲</button>
  <button class="g" onclick="rueda(-120)">▼</button>
  <button class="g" onclick="tecla('backspace')">⌫</button>
  <button class="g" onclick="tecla('enter')">⏎</button>
  <button class="g" onclick="tecla('esc')">Esc</button>
</div>
<div id="teclado"><input id="txt" placeholder="Escribir en el PC..."><button onclick="escribir()">Enviar</button></div>
<script>
var ultimo = null;
var pad = document.getElementById('pad');
pad.addEventListener('touchstart', function (e) { ultimo = e.touches[0]; e.preventDefault(); });
pad.addEventListener('touchmove', function (e) {
  e.preventDefault();
  var t = e.touches[0];
  if (!ultimo) { ultimo = t; return; }
  var dx = t.clientX - ultimo.clientX, dy = t.clientY - ultimo.clientY;
  ultimo = t;
  mover(dx, dy);
});
pad.addEventListener('mousemove', function (e) {
  if (e.buttons & 1) mover(e.movementX, e.movementY);
});
function mover(dx, dy) { post({ action: 'move', dx: dx, dy: dy }); }
function clic(tipo) { post({ action: 'click', tipo: tipo }); }
function rueda(d) { post({ action: 'scroll', delta: d }); }
function tecla(k) { post({ action: 'key', key: k }); }
function escribir() { post({ action: 'type', text: document.getElementById('txt').value }); document.getElementById('txt').value = ''; }
function post(datos) { fetch('/mouse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) }); }
</script></body></html>"""
    return render_template_string(html)


@app.route('/mouse', methods=['POST'])
def mouse_accion():
    datos = request.get_json(silent=True) or {}
    acc = datos.get('action')
    try:
        import ctypes
        u = ctypes.windll.user32
        if acc == 'move':
            u.mouse_event(0x0001, int(datos.get('dx', 0)), int(datos.get('dy', 0)), 0, 0)
        elif acc == 'click':
            tipo = datos.get('tipo')
            if tipo == 1:
                u.mouse_event(0x0002, 0, 0, 0, 0); u.mouse_event(0x0004, 0, 0, 0, 0)
            elif tipo == 2:
                for _ in range(2):
                    u.mouse_event(0x0002, 0, 0, 0, 0); u.mouse_event(0x0004, 0, 0, 0, 0)
            elif tipo == 3:
                u.mouse_event(0x0008, 0, 0, 0, 0); u.mouse_event(0x0010, 0, 0, 0, 0)
        elif acc == 'scroll':
            u.mouse_event(0x0800, 0, 0, int(datos.get('delta', 0)), 0)
        elif acc == 'key':
            mapa = {'enter': 0x0D, 'backspace': 0x08, 'esc': 0x1B, 'tab': 0x09}
            vk = mapa.get(datos.get('key', ''))
            if vk:
                u.keybd_event(vk, 0, 0, 0); u.keybd_event(vk, 0, 2, 0)
        elif acc == 'type':
            texto = (datos.get('text') or '')[:200]
            for ch in texto:
                codigo = ord(ch)
                clase = (ctypes.c_ushort * 1)(codigo)
                evento = (ctypes.c_ulong * 3)(0, 0, 0)
                inputs = (ctypes.c_ulong * 1)(1)
                import ctypes.wintypes as wt
                struct = ctypes.create_string_buffer(40)
                ctypes.memset(struct, 0, 40)
                ctypes.cast(struct, ctypes.POINTER(ctypes.c_ulong))[0] = 0x0004  # KEYEVENTF_UNICODE
                ctypes.cast(struct, ctypes.POINTER(ctypes.c_ulong))[1] = codigo
                ctypes.memset(ctypes.addressof(struct) + 8, 0, 32)
                class INPUT(ctypes.Structure):
                    _fields_ = [("type", ctypes.c_ulong), ("data", ctypes.c_ubyte * 24)]
                inp = INPUT(1, (ctypes.c_ubyte * 24).from_buffer_copy(struct.raw))
                u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── SUBIR FOTOS/ARCHIVOS DESDE EL MÓVIL ────────────────────────────────────────
@app.route('/upload', methods=['POST'])
def upload_movil():
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        return jsonify({'ok': False, 'error': 'sin archivo'}), 400
    nombre = os.path.basename(archivo.filename)
    d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Subidas")
    os.makedirs(d, exist_ok=True)
    ruta = os.path.join(d, f"{int(time.time())}_{nombre}")
    archivo.save(ruta)
    socketio.emit('notification', {'text': f'Archivo «{nombre}» subido desde su teléfono, señor.'}, to=None)
    return jsonify({'ok': True, 'ruta': ruta})


# ── STATS / DASHBOARD ──────────────────────────────────────────────────────────
@app.route('/stats')
def stats_json():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.3)
        ram = psutil.virtual_memory()
        disco = psutil.disk_usage('C:\\')
        net = psutil.net_io_counters()
        top = []
        for p in sorted(psutil.process_iter(['name', 'cpu_percent', 'memory_percent']),
                        key=lambda p: p.info['cpu_percent'] or 0, reverse=True)[:5]:
            top.append({'nombre': p.info['name'] or '?', 'cpu': round(p.info['cpu_percent'] or 0, 1),
                        'mem': round(p.info['memory_percent'] or 0, 1)})
        temp = None
        try:
            import subprocess
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "Get-CimInstance MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty CurrentTemperature"],
                               capture_output=True, text=True, timeout=8, creationflags=0x08000000)
            v = (r.stdout or '').strip()
            if v:
                temp = round((int(v) / 10) - 273.15, 1)
        except Exception:
            pass
        return jsonify({
            'cpu': cpu, 'ram_pct': ram.percent,
            'ram_used_gb': round(ram.used / 1073741824, 1), 'ram_total_gb': round(ram.total / 1073741824, 1),
            'disco_libre_gb': round(disco.free / 1073741824, 1), 'disco_total_gb': round(disco.total / 1073741824, 1),
            'net_mb': round(net.bytes_recv / 1048576, 1),
            'temp': temp, 'top': top,
            'hora': time.strftime('%H:%M:%S')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/dashboard')
def dashboard_view():
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>JARVIS - Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{background:#0a1118;margin:0;font-family:Segoe UI,sans-serif;color:#e6edf3;padding:14px}
h1{font-size:18px;color:#00d4ff}
.caja{background:#12202e;border:1px solid #2a3f54;border-radius:12px;padding:12px;margin:8px 0}
.barra{height:14px;background:#1b2c3d;border-radius:8px;overflow:hidden;margin-top:6px}
.barra div{height:100%;background:#00d4ff;border-radius:8px;transition:width .5s}
.val{float:right;color:#00d4ff;font-weight:bold}
.proceso{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #16263a;font-size:13px}
</style></head>
<body>
<h1>JARVIS · Dashboard <span id="hora" style="float:right;font-size:12px;color:#5a7a95"></span></h1>
<div class="caja">CPU <span class="val" id="cpuV">--</span><div class="barra"><div id="cpuB" style="width:0%"></div></div></div>
<div class="caja">RAM <span class="val" id="ramV">--</span><div class="barra"><div id="ramB" style="width:0%"></div></div></div>
<div class="caja">Disco <span class="val" id="discoV">--</span><div class="barra"><div id="discoB" style="width:0%"></div></div></div>
<div class="caja" id="extras"></div>
<div class="caja" id="procesos"></div>
<script>
function actualizar() {
  fetch('/stats').then(function (r) { return r.json(); }).then(function (d) {
    if (d.error) return;
    document.getElementById('cpuV').textContent = d.cpu + '%';
    document.getElementById('cpuB').style.width = d.cpu + '%';
    document.getElementById('ramV').textContent = d.ram_pct + '% (' + d.ram_used_gb + ' GB)';
    document.getElementById('ramB').style.width = d.ram_pct + '%';
    var discoPct = Math.round((1 - d.disco_libre_gb / d.disco_total_gb) * 100);
    document.getElementById('discoV').textContent = d.disco_libre_gb + ' GB libres';
    document.getElementById('discoB').style.width = discoPct + '%';
    document.getElementById('hora').textContent = d.hora;
    document.getElementById('extras').innerHTML = 'Descarga total: ' + d.net_mb + ' MB · Temperatura: ' + (d.temp !== null ? d.temp + '°C' : 'n/d');
    var html = '<b style="font-size:13px">Procesos</b>';
    d.top.forEach(function (p) { html += '<div class="proceso"><span>' + p.nombre + '</span><span>' + p.cpu + '% CPU · ' + p.mem + '% RAM</span></div>'; });
    document.getElementById('procesos').innerHTML = html;
  });
}
actualizar(); setInterval(actualizar, 3000);
</script></body></html>"""
    return render_template_string(html)


@app.route('/allow_my_ip', methods=['POST'])
def permitir_mi_ip():
    ip = request.remote_addr or ''
    ruta = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "allowed_ips.json")
    try:
        lista = json.load(open(ruta, encoding="utf-8")) or []
    except Exception:
        lista = []
    if ip and ip not in lista:
        lista.append(ip)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True, 'ip': ip})


@app.route('/socket.io.min.js')
def socketio_client():
    resp = send_from_directory('.', 'socket.io.min.js', mimetype='application/javascript')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@app.route('/manifest.webmanifest')
def manifest_pwa():
    return send_from_directory('.', 'manifest.webmanifest', mimetype='application/manifest+json')


@app.route('/sw.js')
def service_worker():
    resp = send_from_directory('.', 'sw.js', mimetype='application/javascript')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/icon-<int:size>.png')
def pwa_icon(size):
    return send_from_directory('.', f'icon-{size}.png', mimetype='image/png')


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': int(time.time())})


@app.route('/debug/core_status')
def debug_core_status():
    """Endpoint para diagnosticar errores de carga del núcleo."""
    try:
        c = core._load()
        if c:
            return jsonify({'loaded': True, 'core_type': type(c).__name__, 'skills': hasattr(c, 'skills'), 'pc': hasattr(c, 'pc'), 'mem0': hasattr(c, 'mem0')})
        else:
            return jsonify({'loaded': False, 'error': core.error, 'next_retry': core._next})
    except Exception as e:
        import traceback
        return jsonify({'loaded': False, 'error': str(e), 'trace': traceback.format_exc()[:1000]})


@app.route('/stats')
def stats():
    if core:
        try:
            s = core.get_system_stats()
            return jsonify({
                'cpu': s.get('cpu', '--'), 'cpu_cores': s.get('cpu_cores', []),
                'ram': s.get('ram_used', '--'), 'ram_total': s.get('ram_total', '--'),
                'ram_pct': s.get('ram_pct', '--'), 'net_sent': s.get('net_sent', '--'),
                'net_recv': s.get('net_recv', '--'), 'disk_free': s.get('disk_free', '--'),
                'disk_total': s.get('disk_total', '--'), 'temp': s.get('temp', '--'),
                'uptime': s.get('uptime', 0), 'battery': s.get('battery'),
            })
        except Exception:
            pass
    return jsonify({'cpu': '--', 'cpu_cores': [], 'ram': '--', 'ram_total': '--',
                    'ram_pct': '--', 'net_sent': '--', 'net_recv': '--',
                    'disk_free': '--', 'disk_total': '--', 'temp': '--',
                    'uptime': 0, 'battery': None})


@app.route('/voice_status')
def voice_status():
    return jsonify({'engine': 'ElevenLabs + SAPI fallback', 'status': 'ready'})


@app.route('/greet')
def greet():
    if core:
        try:
            return jsonify({'response': core.greeting()})
        except Exception as e:
            return jsonify({'response': f"Señor, tengo un problema menor de arranque: {str(e)[:80]}"})
    return jsonify({'response': 'Buenos días, señor. Todos los sistemas están operativos. ¿En qué puedo servirle hoy?'})


@app.route('/farewell')
def farewell():
    if core:
        try:
            return jsonify({'response': core.farewell()})
        except Exception:
            pass
    return jsonify({'response': 'Hasta luego, señor. Permaneceré en espera.'})


@app.route('/set_mode/<mode>')
def set_mode(mode):
    modes = {'normal', 'sleep', 'focus'}
    if mode not in modes:
        return jsonify({'error': 'Modo invalido'}), 400
    if core:
        try:
            if mode == 'sleep':
                msg = core.sleep_mode()
            elif mode == 'focus':
                msg = core.focus_mode()
            else:
                msg = "De vuelta al modo completo, señor. A su servicio."
            return jsonify({'mode': mode, 'response': msg})
        except Exception:
            pass
    return jsonify({'mode': mode, 'response': 'Modo actualizado.'})


@app.route('/tts', methods=['POST'])
def tts():
    try:
        data = request.get_json()
        text = (data.get('text') or '').strip()
        if not text or len(text) > 1000:
            return jsonify({'error': 'Texto invalido'}), 400
        if core:
            core.synthesize_and_play(text)
            return jsonify({'status': 'ok'})
        return jsonify({'error': 'Nucleo no disponible'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/voz_windows', methods=['GET', 'POST'])
def voz_windows():
    """Consulta o alterna el silencio de la voz local de Windows.

    Con ElevenLabs (o el navegador) hablando ademas del TTS del sistema se
    oyen dos voces a la vez; esto silencia la del PC sin tocar el resto.
    """
    if not core:
        return jsonify({'error': 'nucleo no disponible'}), 503
    try:
        if request.method == 'GET':
            return jsonify({'silenciada': bool(core.voz_windows_silenciada)})
        datos = request.get_json(silent=True) or {}
        if 'silenciar' in datos:
            silenciar = bool(datos['silenciar'])
        else:
            silenciar = not core.voz_windows_silenciada   # sin cuerpo: alterna
        mensaje = core.silenciar_voz_windows(silenciar)
        return jsonify({'silenciada': silenciar, 'mensaje': mensaje})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/tts_stop', methods=['POST'])
def tts_stop():
    if core:
        try:
            core.stop_speaking()
            return jsonify({'status': 'stopped'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'status': 'stopped'})


@app.route('/api/speak', methods=['POST'])
def api_speak():
    """Sintetiza el texto con ElevenLabs y devuelve el MP3 para reproducir
    en el navegador (agente conversacional de voz servicial)."""
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text or len(text) > 2000:
        return jsonify({'error': 'texto invalido'}), 400
    key = os.getenv('ELEVENLABS_API_KEY', '')
    voice = os.getenv('ELEVENLABS_VOICE_ID', '').strip()
    sin_cabecera = {'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'}

    if key and 'tu_api' not in key and voice:
        # Tono servicial: voz calmada y profesional
        payload = {
            'text': text,
            'model_id': 'eleven_multilingual_v2',
            'voice_settings': {'stability': 0.5, 'similarity_boost': 0.8},
        }
        headers = {'Accept': 'audio/mpeg', 'Content-Type': 'application/json', 'xi-api-key': key}
        url = f'https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream'
        try:
            r = requests.post(url, json=payload, headers=headers, stream=True, timeout=(5, 30))
            if r.status_code == 200:
                return Response(r.raw, mimetype='audio/mpeg', headers=sin_cabecera)
            # 401 = clave invalida, 429 = limite, 402 = sin creditos.
            print(f"[tts] ElevenLabs devolvio {r.status_code}; pruebo con Piper.")
        except Exception as e:
            print(f"[tts] ElevenLabs no responde ({e}); pruebo con Piper.")
    else:
        print("[tts] Sin ELEVENLABS_API_KEY/VOICE_ID; uso la voz local.")

    # Voz local (Piper): el proyecto ya trae el modelo, no hace falta nube.
    try:
        import jarvis_piper
        # disponible() PRIMERO: sintetizar sin el modelo descargado dispara una
        # descarga de decenas de MB dentro de la peticion HTTP y la deja colgada.
        if jarvis_piper.disponible():
            audio = jarvis_piper.sintetizar_bytes(text[:1000])
            if audio:
                return Response(audio, mimetype='audio/wav', headers=sin_cabecera)
        else:
            print("[tts] Modelo de Piper no descargado; que hable el navegador. "
                  "Para tener voz local: python -c \"import jarvis_piper;"
                  "jarvis_piper.descargar_modelo()\"")
    except Exception as e:
        print(f"[tts] Piper no disponible: {e}")

    # 204, no 502: que no haya voz de servidor no es un fallo de pasarela.
    # El navegador cae solo a speechSynthesis y la consola deja de ensuciarse.
    return Response(status=204, headers={**sin_cabecera, 'X-TTS': 'browser'})


# ── Proxy a ULTRON (consola móvil unificada) ─────────────────────────────────
_ULTRON_BASE = 'http://127.0.0.1:8766'


def _ultron_token() -> str:
    """Token de emparejamiento de Ultron (el servidor hace de puente de confianza)."""
    p = os.path.join(_ROOT, 'ultron_interface', '.ultron_auth')
    try:
        return open(p, 'r', encoding='utf-8').read().strip()
    except Exception:
        return ''


def _u_forward(metodo: str, path: str, **kw):
    """Reenvía una petición al servidor de Ultron; 502 si está caído."""
    try:
        r = requests.request(metodo, _ULTRON_BASE + path, timeout=kw.pop('timeout', 180), **kw)
        return Response(r.content, status=r.status_code,
                        mimetype=r.headers.get('Content-Type', 'application/json'))
    except Exception as e:
        return jsonify({'error': 'ultron_offline', 'detail': str(e)}), 502


@app.route('/u/health')
def u_health():
    return _u_forward('GET', '/health', timeout=6)


@app.route('/u/status')
def u_status():
    return _u_forward('GET', '/status', timeout=8)


@app.route('/u/history')
def u_history():
    return _u_forward('GET', '/history', timeout=8)


@app.route('/u/chat', methods=['POST'])
def u_chat():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'texto vacío'}), 400
    return _u_forward('POST', '/chat', json={'text': text, 'speak_server': False}, timeout=300)


@app.route('/u/speak', methods=['POST'])
def u_speak():
    """Voz conquistadora de Ultron (ElevenLabs) transmitida al navegador."""
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'texto vacío'}), 400
    return _u_forward('POST', '/api/speak', json={'text': text[:2000]}, timeout=90)


@app.route('/u/mode/<modo>', methods=['POST'])
def u_mode(modo):
    if modo not in ('OFENSIVA', 'NORMAL'):
        return jsonify({'error': 'modo invalido'}), 400
    return _u_forward('POST', f'/mode/{modo}', json={'token': _ultron_token()}, timeout=15)


@app.route('/u/voice', methods=['POST'])
def u_voice():
    """Dictado por audio → Whisper en el núcleo de Ultron."""
    token = _ultron_token()
    f = request.files.get('audio') if request.files else None
    if f is not None:
        files = {'audio': (f.filename, f.stream, f.mimetype)}
        return _u_forward('POST', '/voice', data={'token': token}, files=files, timeout=120)
    blob = request.get_data()
    if not blob:
        return jsonify({'error': 'sin audio'}), 400
    return _u_forward('POST', '/voice', data={'token': token},
                      files={'audio': ('voz.webm', blob, 'audio/webm')}, timeout=120)


@app.route('/process_text', methods=['POST'])
def process_text():
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'No text provided'}), 400
        text = data['text']
        if len(text) > 2000:
            return jsonify({'error': 'Texto invalido o muy largo'}), 400
        if core:
            try:
                response = core.process_text_stream(text, speak_server=False)
                return jsonify({'status': 'success', 'response': response[:500] if response else ''})
            except Exception as e:
                import traceback
                return jsonify({'status': 'error', 'response': f'Error procesando: {str(e)[:200]}', 'trace': traceback.format_exc()[:500]})
        else:
            err = core.error or ''
            ayuda = ' Ejecute «python diagnostico_bots.py» en la carpeta del proyecto para ver la causa.'
            if 'database' in err.lower():
                ayuda = (' Es la base de datos: defina JARVIS_DB_DIR con una carpeta escribible '
                         'o ejecute «python diagnostico_bots.py».')
            elif 'no module named' in err.lower():
                ayuda = ' Falta una dependencia: ejecute «pip install -r requirements.txt».'
            return jsonify({'status': 'listening',
                            'response': ('Señor, el núcleo de JARVIS no pudo cargarse.'
                                         + (f' ({err})' if err else '') + ayuda)})
    except Exception as e:
        import traceback
        return jsonify({'error': 'Error interno', 'details': str(e)[:100] if str(e) else 'unknown', 'trace': traceback.format_exc()[:500]}), 500


@app.route('/api/plan', methods=['POST'])
def api_plan():
    try:
        data = request.get_json(silent=True) or {}
        text = data.get('text', '')
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        if core:
            try:
                response = core.process_text_stream(text, speak_server=False, skip_skills=True)
                return jsonify({'status': 'success', 'response': response or ''})
            except Exception:
                return jsonify({'status': 'processing', 'response': 'Generando plan... (puede tardar unos segundos)'})
        else:
            return jsonify({'status': 'listening', 'response': 'Señor, el núcleo de JARVIS no pudo cargarse.'})
    except Exception as e:
        return jsonify({'error': 'Error interno', 'details': str(e)[:100] if str(e) else 'unknown'}), 500


@app.route('/reset')
def reset():
    return jsonify({'status': 'reset', 'message': 'Conversacion restablecida'})


@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({'error': 'No prompt provided'}), 400
        prompt = data['prompt'].strip()
        if not prompt or len(prompt) > 2000:
            return jsonify({'error': 'Prompt invalido o muy largo'}), 400
        if not generator:
            return jsonify({'error': 'Generador no disponible'}), 500
        result = generator.generate(prompt)
        if result.get('path') and os.path.exists(result['path']):
            result['filename'] = os.path.basename(result['path'])
            result['size'] = os.path.getsize(result['path'])
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<path:filepath>')
def download_file(filepath):
    try:
        full_path = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Generaciones", filepath)
        if os.path.exists(full_path):
            return send_file(full_path, as_attachment=False)
        return jsonify({'error': 'Archivo no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/generated_files')
def generated_files():
    base = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Generaciones")
    files = []
    if os.path.exists(base):
        for root, dirs, filenames in os.walk(base):
            for fn in filenames[:50]:
                fp = os.path.join(root, fn)
                rel = os.path.relpath(fp, base)
                files.append({'name': fn, 'path': rel, 'size': os.path.getsize(fp),
                              'type': os.path.splitext(fn)[1][1:].upper()})
    files.sort(key=lambda x: x['size'], reverse=True)
    return jsonify({'files': files[:30]})


@app.route('/api/yt/list')
def yt_list():
    base = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Videos")
    files = []
    if os.path.exists(base):
        for fn in os.listdir(base):
            fp = os.path.join(base, fn)
            if os.path.isfile(fp):
                files.append({'name': fn, 'rel': fn, 'size': os.path.getsize(fp),
                              'mtime': os.path.getmtime(fp)})
        files.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify({'files': files[:20]})


@app.route('/download_yt/<path:rel>')
def download_yt(rel):
    base = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Videos")
    fp = os.path.join(base, rel)
    if os.path.exists(fp) and os.path.isfile(fp):
        return send_file(fp, as_attachment=False)
    return jsonify({'error': 'Archivo no encontrado'}), 404


@app.route('/api/yt/download', methods=['POST'])
def yt_download():
    """Descarga directa de YouTube (usado por la caja YouTube Studio)."""
    try:
        data = request.get_json() or {}
        url = (data.get('url') or '').strip()
        fmt = (data.get('format') or 'video').strip().lower()
        if not url or not (url.startswith('http://') or url.startswith('https://')):
            return jsonify({'ok': False, 'error': 'URL inválida, pegue el link completo de YouTube'}), 400
        es_musica = fmt == 'audio'
        import shutil, yt_dlp
        base = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Videos")
        os.makedirs(base, exist_ok=True)
        ff = shutil.which("ffmpeg")
        ff_dir = os.path.dirname(ff) if ff else None
        # Snapshot antes para detectar archivo nuevo
        before = set(os.listdir(base)) if os.path.exists(base) else set()
        opts = {
            "outtmpl": os.path.join(base, "%(title).80s.%(ext)s"),
            "format": "bestaudio/best" if es_musica else "best[height<=1080]/best",
            "quiet": True,
            "noplaylist": True,
            "noprogress": True,
            "extractor_args": {"youtube": {"player_client": ["tv_embedded", "android"]}},
        }
        if ff_dir:
            opts["ffmpeg_location"] = ff_dir
        if es_musica:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        titulo = (info or {}).get("title") or url[:40]
        # Detectar archivo nuevo
        after = set(os.listdir(base)) if os.path.exists(base) else set()
        nuevos = list(after - before)
        # Si es mp3, yt_dlp puede haber creado .mp3 aunque before tenía .webm parcial
        if not nuevos:
            # fallback: el más reciente
            files = [(f, os.path.getmtime(os.path.join(base, f))) for f in after if os.path.isfile(os.path.join(base, f))]
            files.sort(key=lambda x: x[1], reverse=True)
            nuevos = [files[0][0]] if files else []
        fname = nuevos[0] if nuevos else None
        fpath = os.path.join(base, fname) if fname else None
        size = os.path.getsize(fpath) if fpath and os.path.exists(fpath) else 0
        if not fname or size == 0:
            return jsonify({'ok': False, 'error': 'Descarga falló: archivo no creado. Verifique el link y que ffmpeg esté instalado.'}), 500
        return jsonify({'ok': True, 'title': titulo, 'file': fname, 'rel': fname, 'size': size})
    except Exception as e:
        import traceback
        traceback.print_exc()
        msg = str(e)
        # Mensajes más amigables para errores comunes
        if "ffmpeg" in msg.lower():
            msg = "Falta ffmpeg o falló la conversión a mp3. " + msg[:200]
        elif "Private video" in msg or "Video unavailable" in msg:
            msg = "Video no disponible o privado. " + msg[:200]
        return jsonify({'ok': False, 'error': msg[:400]}), 500


# ── API SKILLS AVANZADAS ─────────────────────────────────────────────────────
@app.route('/api/stock', methods=['POST'])
def api_stock():
    """Consulta datos bursátiles via YFinance."""
    try:
        data = request.get_json() or {}
        ticker = (data.get('ticker') or '').strip().upper()
        if not ticker or len(ticker) > 5:
            return jsonify({'ok': False, 'error': 'Ticker inválido'}), 400
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info
        precio = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
        cambio = info.get('regularMarketChangePercent', 0)
        nombre = info.get('shortName', ticker)
        volumen = info.get('volume', 0)
        max_dia = info.get('dayHigh')
        min_dia = info.get('dayLow')
        return jsonify({
            'ok': True, 'ticker': ticker, 'nombre': nombre,
            'precio': precio, 'cambio': round(cambio, 2),
            'max_dia': max_dia, 'min_dia': min_dia,
            'volumen': volumen
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/api/news', methods=['POST'])
def api_news():
    """Busca noticias con DuckDuckGo y resume con Llama 3."""
    try:
        data = request.get_json() or {}
        tema = (data.get('tema') or '').strip()
        if len(tema) < 2:
            return jsonify({'ok': False, 'error': 'Tema muy corto'}), 400
        from duckduckgo_search import DDGS
        with DDGS() as ddg:
            results = ddg.text(f"{tema} noticias recientes 2026", max_results=5)
        if not results:
            return jsonify({'ok': True, 'noticias': [], 'resumen': 'No se encontraron noticias.'})
        noticias = []
        for r in results[:5]:
            noticias.append({'title': r.get('title', ''), 'body': r.get('body', ''), 'url': r.get('href', '')})
        raw = "\n".join([f"- {n['title']}: {n['body'][:120]}" for n in noticias])
        sys_prompt = "Eres un analista de noticias. Resume en un parrafo conciso."
        user_prompt = f"Resume estas noticias sobre {tema}:\n\n{raw}"
        resp = requests.post(jarvis_config.OLLAMA_URL, json={
            'model': 'llama3.2:1b', 'system': sys_prompt,
            'prompt': user_prompt, 'stream': False,
            'options': {'num_predict': 300}
        }, timeout=45)
        resumen = resp.json().get('response', 'No pude resumir.')
        return jsonify({'ok': True, 'noticias': noticias, 'resumen': resumen})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    """Extrae y analiza contenido web con BeautifulSoup + Llama 3."""
    try:
        data = request.get_json() or {}
        url = (data.get('url') or '').strip()
        if not url.startswith('http'):
            return jsonify({'ok': False, 'error': 'URL inválida'}), 400
        from bs4 import BeautifulSoup
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)[:3000]
        if not text:
            return jsonify({'ok': False, 'error': 'Sin contenido legible'}), 200
        sys_prompt = "Eres un asistente experto. Resume y analiza el siguiente contenido web."
        user_prompt = f"Analiza este contenido:\n\n{text[:2500]}"
        resp_llm = requests.post(jarvis_config.OLLAMA_URL, json={
            'model': 'llama3.2:1b', 'system': sys_prompt,
            'prompt': user_prompt, 'stream': False,
            'options': {'num_predict': 512}
        }, timeout=45)
        resultado = resp_llm.json().get('response', 'No pude analizar.')
        return jsonify({'ok': True, 'analisis': resultado, 'texto_extraido': text[:1500]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/api/pdf_chat', methods=['POST'])
def api_pdf_chat():
    """Analiza el PDF más reciente con Llama 3."""
    try:
        pdfs_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS")
        pdfs = []
        for root, _, files in os.walk(pdfs_dir):
            for f in files:
                if f.lower().endswith('.pdf'):
                    pdfs.append(os.path.join(root, f))
        if not pdfs:
            return jsonify({'ok': False, 'error': 'No se encontraron PDFs en JARVIS'}), 200
        pdf_path = max(pdfs, key=os.path.getmtime)
        import fitz
        doc = fitz.open(pdf_path)
        texto = ''
        for page in doc:
            texto += page.get_text()
            if len(texto) > 4000:
                break
        doc.close()
        sys_prompt = "Eres un experto en analisis de documentos. Analiza el PDF y responde claramente."
        user_prompt = f"Analiza este PDF ({os.path.basename(pdf_path)}):\n\n{texto[:3500]}"
        resp = requests.post(jarvis_config.OLLAMA_URL, json={
            'model': 'llama3.2:1b', 'system': sys_prompt,
            'prompt': user_prompt, 'stream': False,
            'options': {'num_predict': 600}
        }, timeout=60)
        resultado = resp.json().get('response', 'No pude analizar el PDF.')
        return jsonify({'ok': True, 'pdf': os.path.basename(pdf_path), 'analisis': resultado})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


# ── RUTAS MÓVILES NUEVAS ──────────────────────────────────────────────────────
@app.route('/api/status')
def api_status():
    """Info para el móvil: token válido, IP, estado."""
    return jsonify({
        'ok': True,
        'ip': _local_ip(),
        'port': jarvis_config.PORT,
        'auth': bool(AUTH_TOKEN),
        'core': bool(core),
        'core_error': core.error,
        'generator': generator is not None,
    })


@app.route('/api/auth', methods=['POST'])
def api_auth():
    """Validar token: {token: "..."} -> {ok: bool}"""
    try:
        data = request.get_json() or {}
        t = (data.get('token') or '').strip()
        return jsonify({'ok': _auth_ok(t)})
    except Exception:
        return jsonify({'ok': False})


@app.route('/api/local_token')
def api_local_token():
    """Devuelve el token de voz SOLO para conexiones locales (localhost).
    Permite al HUD del navegador usar la voz sin introducir el PIN manualmente."""
    if request.remote_addr in ("127.0.0.1", "::1"):
        return jsonify({'token': AUTH_TOKEN})
    return jsonify({'token': ''}), 403


@app.route('/api/agentes')
def api_agentes():
    """Catálogo de la agencia de especialistas (agency-agents) agrupado por división."""
    ia = _agentes_ia()
    if not ia:
        return jsonify({'total': 0, 'divisiones': []})
    divisiones = []
    # self.divisiones: categoria -> [ids]; preservar orden
    divs = getattr(ia, 'divisiones', None) or {}
    agentes = getattr(ia, 'agentes', {}) or {}
    for cat, ids in divs.items():
        lista = []
        for aid in ids:
            a = agentes.get(aid)
            if not a:
                continue
            lista.append({
                'id': a.get('id'), 'nombre': a.get('nombre'),
                'descripcion': (a.get('descripcion') or '')[:180],
                'vibe': a.get('vibe', ''),
            })
        if lista:
            divisiones.append({'nombre': cat, 'agentes': lista})
    return jsonify({'total': len(agentes), 'divisiones': divisiones})


@app.route('/api/history')
def api_history():
    """Historial de conversación (para reanudar desde el móvil)."""
    return jsonify({'messages': _history_messages()})


@app.route('/qr')
def qr():
    """Código QR de emparejamiento: URL pública con token."""
    try:
        import qrcode
        from io import BytesIO
        url = f"{_pair_url()}?token={AUTH_TOKEN}"
        img = qrcode.make(url)
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/pair')
def pair():
    """Página de emparejamiento: muestra el QR para escanear con el teléfono."""
    url_movil = _pair_url().replace("/mobile", "")
    dns = _tailscale_dns()
    nonce = int(__import__('time').time())
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>JARVIS - Emparejar telefono</title>
<style>
body{background:#05070d;color:#cfe8ff;font-family:Segoe UI,sans-serif;display:flex;
flex-direction:column;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center}
h1{color:#00d4ff;letter-spacing:3px;text-transform:uppercase;text-shadow:0 0 15px #00d4ff66}
img{border:6px solid #00d4ff55;border-radius:14px;background:#fff;padding:10px}
.pin{font-size:64px;font-weight:800;letter-spacing:14px;color:#7ee7ff;background:#0a1420;
border:2px solid #00d4ff66;border-radius:16px;padding:8px 26px;margin:6px 0;text-shadow:0 0 18px #00d4ff}
.hint{color:#5a7a95;font-size:13px;margin:4px 0}
code{background:#0a1420;padding:4px 10px;border-radius:8px;color:#7ee7ff}
</style></head><body>
<h1>JARVIS Mobile</h1>
<p class="hint">Código de acceso (PIN):</p>
<div class="pin">""" + AUTH_TOKEN + """</div>
<p class="hint">O escanea este código QR con la cámara del teléfono:</p>
<img src="/qr?v=""" + str(nonce) + """" alt="QR de emparejamiento" width="240">
<p class="hint">Conectado al mismo Wi-Fi, abre en el teléfono:<br>
<code>""" + url_movil + """/mobile</code></p>
<p class="hint" style="font-size:11px">Desde otra red (datos móviles): instala Tailscale en el teléfono y usa
<code>https://""" + (dns or "TU-PC.ts.net") + """/mobile</code></p>
</body></html>"""
    return render_template_string(html)


# ── COMPANION: VOZ, COMANDOS, AVISOS Y CENTRO DE MANDO ───────────────────────
_whisper_model = None
_whisper_lock = threading.Lock()


def _ffmpeg_path():
    try:
        import shutil
        r = shutil.which("ffmpeg")
        if r:
            return r
    except Exception:
        pass
    return "ffmpeg"


def _transcribir_audio(ruta_wav):
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    segs, _info = _whisper_model.transcribe(ruta_wav, language="es")
    return "".join(s.text for s in segs).strip()


def _req_token():
    t = request.headers.get("X-Token") or request.args.get("token") or ""
    if t:
        return t
    try:
        t = (request.get_json(silent=True) or {}).get("token") or ""
    except Exception:
        t = ""
    if not t:
        t = request.form.get("token") or ""
    return t


@app.route('/voice', methods=['POST'])
def companion_voice():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    if not core:
        return jsonify({'error': 'nucleo no disponible'}), 500
    import subprocess as _sp
    import tempfile as _tf
    import uuid as _uuid
    ruta_in = ruta_wav = None
    try:
        f = request.files.get('audio') if request.files else None
        if f is not None:
            ruta_in = os.path.join(_tf.gettempdir(), f"voz_{_uuid.uuid4().hex}.webm")
            f.save(ruta_in)
        else:
            blob = request.get_data()
            if not blob:
                return jsonify({'error': 'sin audio'}), 400
            ruta_in = os.path.join(_tf.gettempdir(), f"voz_{_uuid.uuid4().hex}.webm")
            with open(ruta_in, "wb") as fh:
                fh.write(blob)
        ruta_wav = os.path.join(_tf.gettempdir(), f"voz_{_uuid.uuid4().hex}.wav")
        r = _sp.run([_ffmpeg_path(), "-y", "-i", ruta_in, "-ar", "16000", "-ac", "1", ruta_wav],
                    capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.exists(ruta_wav):
            return jsonify({'error': 'no pude convertir el audio'}), 500
        texto = _transcribir_audio(ruta_wav)
        if not texto:
            return jsonify({'texto': '', 'respuesta': 'Señor, no escuché nada claro.'})
        # Modo dictado (isair): la voz se escribe en la app enfocada del PC
        if core.dictado_activo():
            ok = core.dictar(texto)
            return jsonify({'texto': texto, 'respuesta': 'Dictado escrito, señor.' if ok else 'Señor, no pude escribir el dictado.'})
        resp = core.process_text_stream(texto, speak_server=False) or 'Señor, no he entendido.'
        return jsonify({'texto': texto, 'respuesta': resp[:1500]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        for _r in (ruta_in, ruta_wav):
            try:
                if _r and os.path.exists(_r):
                    os.remove(_r)
            except Exception:
                pass


@app.route('/cmd', methods=['POST'])
def companion_cmd():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    data = request.get_json(silent=True) or {}
    texto = (data.get('texto') or '').strip()
    if not texto or len(texto) > 2000:
        return jsonify({'error': 'texto invalido'}), 400
    if not core:
        return jsonify({'error': 'nucleo no disponible'}), 500
    resultado = {}

    def _trabajo(res):
        try:
            res['respuesta'] = (core.process_text_stream(texto) or 'Señor, no he entendido.')[:1500]
        except Exception as e:
            res['respuesta'] = f"Señor, tuve un problema procesando eso: {str(e)[:120]}"

    hilo = threading.Thread(target=_trabajo, args=(resultado,), daemon=True)
    hilo.start()
    hilo.join(timeout=120)
    return jsonify({'texto': texto, 'respuesta': resultado.get('respuesta', 'Procesando...')})


@app.route('/avisos')
def companion_avisos():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    try:
        avisos = json.load(open(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                             "Prefs", "avisos.json"), encoding="utf-8")) or []
    except Exception:
        avisos = []
    if isinstance(avisos, dict):
        avisos = list(avisos.values())
    return jsonify({'avisos': list(avisos)[-10:][::-1]})


@app.route('/centro')
def companion_centro():
    html = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JARVIS - Centro de Mando</title>
<style>
body{background:#05070d;color:#cfe8ff;font-family:Segoe UI,sans-serif;margin:0;padding:16px}
h1{color:#00d4ff;letter-spacing:3px;text-transform:uppercase;text-shadow:0 0 15px #00d4ff66;font-size:20px}
.card{background:#0a1420;border:1px solid #1d3a55;border-radius:14px;padding:14px;margin:12px 0}
.g{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
button{background:#0e2a3f;color:#7ee7ff;border:1px solid #00d4ff55;border-radius:10px;padding:12px;
font-size:14px;cursor:pointer;transition:.15s}
button:active{background:#123a58}
input{width:100%;box-sizing:border-box;background:#08111c;color:#cfe8ff;border:1px solid #1d3a55;
border-radius:10px;padding:10px;font-size:15px}
#log{white-space:pre-wrap;font-size:13px;color:#9fd8ff;max-height:220px;overflow:auto}
.item{background:#08111c;border:1px solid #16304a;border-radius:8px;padding:8px;margin:6px 0;font-size:13px}
.hint{color:#5a7a95;font-size:12px}
</style></head><body>
<h1>Centro de Mando</h1>
<div class="card"><input id="pin" placeholder="PIN (se guarda en el teléfono)" inputmode="numeric">
<p class="hint">Guardar PIN en este teléfono: <button onclick="guardarPin()" style="padding:6px">Guardar</button></p></div>
<div class="card"><div class="g">
<button onclick="cmd('bloquea la pc un momento')">🔒 Bloquear</button>
<button onclick="cmd('muestrame la pantalla')">🖥 Pantalla</button>
<button onclick="cmd('abre la camara')">📷 Cámara</button>
<button onclick="cmd('dame las stats del pc')">📊 Stats</button>
<button onclick="cmd('activa modo silencio')">🔕 No molestar</button>
<button onclick="cmd('desactiva modo silencio')">🔔 Normal</button>
<button onclick="cmd('apagate en 30 minutos')">⏻ Apagar en 30'</button>
<button onclick="cmd('cancela el apagado')">↩ Cancela apagado</button>
<button onclick="cmd('simula presencia')">🏠 Presencia</button>
<button onclick="cmd('dame las noticias')">📰 Noticias</button>
<button onclick="cmd('muestrame los ultimos gastos')">💶 Gastos</button>
<button onclick="verAvisos()">📥 Avisos</button>
<button onclick="cmd('dame el informe')">🌅 Informe</button>
<button onclick="cmd('que esta sonando')">🎵 Qué suena</button>
<button onclick="cmd('vigila la red')">🔔 Vigila red</button>
<button onclick="cmd('donde esta mi telefono')">📲 Teléfono</button>
<button onclick="cmd('modo invitado')">🛡 Invitado</button>
<button onclick="cmd('modo gaming')">🎮 Gaming</button>
<button onclick="cmd('salud del pc')">🩺 Salud</button>
<button onclick="cmd('muestrame la lista de la compra')">🛒 Compra</button>
<button onclick="cmd('diagnostica el pc')">🛠 Diagnóstico</button>
<button onclick="cmd('escanea un documento')">🖨 Escanear</button>
<button onclick="probarIa()">🧠 Probar IA</button>
</div></div>
<div class="card"><div class="g">
<input id="txt" placeholder="Escribe una orden a Jarvis...">
<button onclick="cmd(document.getElementById('txt').value)">Enviar</button>
</div></div>
<div class="card"><div id="log">Listo, señor.</div></div>
<div class="card"><div id="avisos"></div></div>
<script>
function token(){return localStorage.getItem('jarvis_pin')||'';}
(function(){var q=new URLSearchParams(location.search);if(q.get('token'))localStorage.setItem('jarvis_pin',q.get('token'));})();
function guardarPin(){var p=document.getElementById('pin').value.trim();if(p)localStorage.setItem('jarvis_pin',p);}
function log(t){var l=document.getElementById('log');l.textContent=t+'\n'+(l.textContent==='Listo, señor.'?'':l.textContent);}
async function cmd(texto){
  texto=(texto||'').trim();if(!texto)return;log('Señor: '+texto);
  try{var r=await fetch('/cmd',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({texto:texto,token:token()})});var j=await r.json();log('Jarvis: '+(j.respuesta||j.error||'?'));
  }catch(e){log('Error: '+e.message);}
}
async function verAvisos(){
  try{var r=await fetch('/avisos?token='+encodeURIComponent(token()));var j=await r.json();
    var a=document.getElementById('avisos');a.innerHTML='';
    (j.avisos||[]).forEach(function(m){var d=document.createElement('div');d.className='item';d.textContent=m;a.appendChild(d);});
  }catch(e){log('Error: '+e.message);}
}
async function probarIa(){
  log('🧠 Probando proveedores de IA (puede tardar unos segundos)...');
  try{var r=await fetch('/probar_ia',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:token()})});var j=await r.json();
    if(j.proveedores){var msgs=j.proveedores.map(function(p){return (p.ok?'✓':'✗')+' '+p.nombre+' ('+(p.respuesta||p.error||'?')+')';});
      log('IA: '+msgs.join(' | '));}else{log('IA: '+(j.error||'?'));}
  }catch(e){log('Error: '+e.message);}
}
</script></body></html>"""
    return render_template_string(html)


# ── PROBAR IA (Validate estilo Admin UI de Free Claude Code) ───────────────
@app.route('/probar_ia', methods=['POST'])
def probar_ia():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    if not core:
        return jsonify({'error': 'nucleo no disponible'}), 500
    try:
        return jsonify(core.probar_cerebro())
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:150]}), 500


# ── SOCKETIO: CHAT EN TIEMPO REAL ─────────────────────────────────────────────
# Clientes de Socket.IO vivos: evita bloquear el PC por una desconexion
# transitoria del movil.
_clientes = set()
_clientes_lock = threading.Lock()


@socketio.on('connect')
def on_connect(auth):
    if not auth or not _auth_ok(auth.get('token', '')):
        print(f"[auth] Socket.IO rechazado desde {request.remote_addr}: PIN incorrecto o ausente.")
        return False
    with _clientes_lock:
        _clientes.add(request.sid)
    emit('connected', {'ok': True})
    try:
        emit('history', {'messages': _history_messages()})
    except Exception:
        pass


@socketio.on('disconnect')
def on_disconnect(*_):
    # *_ : las versiones nuevas de Flask-SocketIO pasan un motivo al handler.
    with _clientes_lock:
        _clientes.discard(request.sid)
    try:
        cfg = json.load(open(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                          "Prefs", "presencia.json"), encoding="utf-8"))
        if cfg.get("activo"):
            # 20 s en vez de 2: el movil pierde el socket constantemente
            # (pantalla apagada, cambio de Wi-Fi) y bloqueaba el PC sin motivo.
            threading.Timer(20.0, _bloquear_por_presencia).start()
    except Exception:
        pass


def _bloquear_por_presencia():
    with _clientes_lock:
        if _clientes:
            return  # alguien volvio a conectarse: no era una ausencia real
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    except Exception:
        pass


@socketio.on('send_message')
def on_send_message(data):
    text = (data or {}).get('text', '')
    if not text or len(text) > 2000:
        return
    text = text.strip()
    if not text:
        return
    emit('user_message', {'text': text}, broadcast=True)
    if not core:
        emit('receive_message', {'text': 'Señor, el núcleo de JARVIS no está disponible.'}, broadcast=True)
        return
    emit('typing', {}, broadcast=True)

    def work():
        try:
            resp = core.process_text_stream(text, speak_server=False) or ''
            with app.app_context():
                socketio.emit('receive_message', {'text': resp[:1500]}, to=None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            with app.app_context():
                socketio.emit('receive_message',
                              {'text': f"Señor, tuve un problema procesando eso: {str(e)[:200]}"},
                              to=None)

    threading.Thread(target=work, daemon=True).start()


if __name__ == '__main__':
    _port = jarvis_config.PORT
    _ip = jarvis_config.LOCAL_IP
    print("=" * 56)
    print("JARVIS Web Server v3 (mobile + tiempo real)")
    print(f"  Local:   http://127.0.0.1:{_port}")
    print(f"  Red:     http://{_ip}:{_port}")
    print(f"  Móvil:   http://{_ip}:{_port}/mobile")
    print(f"  QR:      http://{_ip}:{_port}/pair")
    print(f"  Token:   {AUTH_TOKEN}")
    print("=" * 56)
    import socket as _sock
    _probe = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
    _probe.settimeout(2)
    try:
        if _probe.connect_ex(("127.0.0.1", _port)) == 0:
            print(f"ATENCION: ya hay otro JARVIS Web escuchando en el puerto {_port}.")
            print("Cerrando esta instancia para no duplicar el servidor.")
            sys.exit(0)
    finally:
        _probe.close()

    # ── ULTRON ya NO se auto-arranca aquí: reiniciar_todo.py es el único
    #    orquestador y evita procesos duplicados (doble voz / doble TTS). ──

    socketio.run(app, host='0.0.0.0', port=_port, debug=False,
                 use_reloader=False, allow_unsafe_werkzeug=True)