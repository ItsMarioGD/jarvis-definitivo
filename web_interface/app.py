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
import ctypes
import subprocess
import threading
import time
import json
import urllib.request
import socket
import secrets
import requests

# Agregar path para importar jarvis_core y generator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Corre con pythonw: sin esto, cada powershell/tailscale que se lanza abre su
# propia ventana negra (emparejar el móvil abría una lluvia de ellas).
import sin_ventanas
sin_ventanas.activar()
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

from flask import Flask, jsonify, send_from_directory, request, send_file, render_template_string, Response, redirect

try:
    from calendar_engine import calendar_engine
except Exception as _ce:
    print(f"[JARVIS-WEB] calendar_engine no disponible: {_ce}")
    calendar_engine = None

try:
    import herramientas.pc_tactical as pc_tactical
except Exception as _pt:
    print(f"[JARVIS-WEB] pc_tactical no disponible: {_pt}")
    pc_tactical = None

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


# Vida del PIN: un codigo de 6 digitos que abre el control total del PC no
# deberia ser eterno. Pasados JARVIS_PIN_DIAS se genera uno nuevo al arrancar
# (0 = nunca caduca, para quien prefiera el comportamiento antiguo).
PIN_DIAS = int(os.getenv("JARVIS_PIN_DIAS", "30"))


def _guardar_token(t: str):
    try:
        with open(AUTH_FILE, 'w', encoding='utf-8') as f:
            json.dump({"token": t, "creado": time.time()}, f)
    except Exception:
        pass
    return t


def _nuevo_token() -> str:
    return _guardar_token(f"{secrets.randbelow(1000000):06d}")


def get_token():
    """PIN actual. Rota solo si caduco; si no, se conserva el emparejamiento."""
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            bruto = f.read().strip()
        if bruto.startswith("{"):
            datos = json.loads(bruto)
            t, creado = str(datos.get("token", "")), float(datos.get("creado", 0))
        else:
            # Formato antiguo: solo el PIN. Se migra conservandolo.
            t, creado = bruto, 0.0
        if t and t.isdigit() and len(t) == 6:
            if PIN_DIAS <= 0:
                return t if creado else _guardar_token(t)
            if creado and (time.time() - creado) < PIN_DIAS * 86400:
                return t
            if not creado:
                return _guardar_token(t)   # migracion: la cuenta empieza hoy
            print(f"[auth] PIN caducado tras {PIN_DIAS} dias: genero uno nuevo.")
    except Exception:
        pass
    return _nuevo_token()


AUTH_TOKEN = get_token()


def _local_ip():
    """IP de la red local real (Wi-Fi/Ethernet). Evita la IP virtual de
    Tailscale (100.x): el teléfono sin la app no puede alcanzarla.

    Se pregunta cada vez, sin cachear: el router reparte IPs nuevas y un QR con
    la IP de ayer es exactamente por lo que el teléfono se queda cargando.
    """
    try:
        import red_movil
        ip = red_movil.mejor_ip()
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass
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
    """URL para el teléfono: la de la red local, siempre recién calculada.

    Antes esto comprobaba la URL abriéndola desde el propio PC, lo cual pasa
    siempre aunque el teléfono no llegue: no probaba nada. Ahora se devuelve la
    mejor dirección local y las alternativas se ofrecen aparte, en /pair_info.
    """
    # Si el servidor esta publicado en la red privada, esa es LA direccion: la
    # misma vale en casa y en la calle, y ademas por HTTPS (sin HTTPS el
    # navegador del telefono apaga el microfono).
    try:
        import remoto
        for u in remoto.urls():
            if u.get("segura"):
                return u["url"].rstrip("/") + "/mobile"
    except Exception:
        pass
    return f"http://{_local_ip()}:{jarvis_config.PORT}/mobile"


def _pair_urls():
    """Todas las direcciones por las que el teléfono podría entrar."""
    port = jarvis_config.PORT
    salida = []
    try:
        import red_movil
        for e in red_movil.ips_lan():
            salida.append({"url": f"http://{e['ip']}:{port}/mobile",
                           "ip": e["ip"], "via": e["interfaz"] or "red local",
                           "perfil": e.get("perfil", "")})
        ts = red_movil.tailscale_ip()
        if ts:
            salida.append({"url": f"http://{ts}:{port}/mobile", "ip": ts,
                           "via": "Tailscale (hasta con datos móviles)", "perfil": ""})
    except Exception:
        salida.append({"url": _pair_url(), "ip": _local_ip(), "via": "red local",
                       "perfil": ""})
    # Lo remoto va DELANTE cuando esta publicado por HTTPS: es la unica
    # direccion que funciona fuera de casa, y ademas deja usar el microfono.
    try:
        import remoto
        remotas = [{"url": u["url"].rstrip("/") + ("" if u["url"].endswith("/mobile")
                                                   else "/mobile"),
                    "ip": u["url"].split("//")[-1].split("/")[0],
                    "via": u["via"], "perfil": "", "remota": True,
                    "segura": u.get("segura", False)}
                   for u in remoto.urls()]
        seguras = [u for u in remotas if u["segura"]]
        salida = seguras + salida + [u for u in remotas if not u["segura"]]
        # La misma direccion puede llegar por dos caminos (red_movil y remoto):
        # en el QR eso solo confunde.
        vistas, unicas = set(), []
        for u in salida:
            if u["url"] in vistas:
                continue
            vistas.add(u["url"])
            unicas.append(u)
        salida = unicas
    except Exception:
        dns = _tailscale_dns()
        if dns:
            salida.append({"url": f"https://{dns}/mobile", "ip": dns,
                           "via": "Tailscale por nombre", "perfil": ""})
    return salida


# Seis cifras se prueban muy deprisa. Mientras JARVIS vivia solo dentro de casa
# daba igual; ahora que se puede entrar desde fuera, no.
INTENTOS_MAX = int(os.getenv("JARVIS_PIN_INTENTOS", "6"))
CASTIGO_SEG = int(os.getenv("JARVIS_PIN_CASTIGO", "900"))     # 15 minutos
_fallos = {}          # ip -> [cuantos, momento_del_ultimo]


LOCALES = ("127.0.0.1", "::1", "localhost")


def _ip_cliente() -> str:
    """IP real de quien pide.

    Tailscale serve/funnel (el acceso desde fuera de casa) entrega cada
    petición desde 127.0.0.1, y así cualquiera que entrase por ahí pasaba por
    «el propio PC»: sin PIN, con el PIN regalado en /pin_actual y sin freno
    para quien lo probara a lo bruto. La IP de verdad viene en
    X-Forwarded-For. Esa cabecera solo se cree si quien conecta es este mismo
    equipo (el proxy de Tailscale): desde la red, cualquiera podría inventarla.
    """
    try:
        ip = request.remote_addr or ""
    except Exception:
        return ""          # fuera de una petición (hilos) no hay IP
    if ip in LOCALES:
        cab = request.headers
        reenviada = (cab.get("X-Forwarded-For") or "").split(",")[0].strip()
        if reenviada:
            return reenviada
        if any(k.lower().startswith(("tailscale-", "x-forwarded-")) for k in cab.keys()):
            return "proxy"          # viene de fuera por un proxy: nunca es el PC
    return ip


def _bloqueado(ip: str) -> float:
    """Segundos que le quedan a esta IP castigada. 0 si puede probar."""
    if ip in LOCALES:
        return 0.0          # el propio PC no se castiga a si mismo
    cuantos, ultimo = _fallos.get(ip, (0, 0.0))
    if cuantos < INTENTOS_MAX:
        return 0.0
    restan = CASTIGO_SEG - (time.time() - ultimo)
    if restan <= 0:
        _fallos.pop(ip, None)
        return 0.0
    return restan


def _anotar_fallo(ip: str):
    if ip in LOCALES:
        return
    cuantos, _ = _fallos.get(ip, (0, 0.0))
    _fallos[ip] = (cuantos + 1, time.time())
    if cuantos + 1 == INTENTOS_MAX:
        print(f"[auth] {ip} ha fallado el PIN {INTENTOS_MAX} veces: "
              f"bloqueada {CASTIGO_SEG // 60} minutos.")


def _auth_ok(token, ip: str = ""):
    """¿Vale el PIN? Con freno para el que lo esta adivinando a lo bruto."""
    if not ip:
        ip = _ip_cliente()
    if ip and _bloqueado(ip):
        return False
    vale = token == AUTH_TOKEN
    if vale:
        _fallos.pop(ip, None)
    elif ip and token:
        _anotar_fallo(ip)
    return vale


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


ALLOWED_IPS_FILE = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                "Prefs", "allowed_ips.json")
# Un emparejamiento no caduca nunca era un problema real: la IP de un movil
# vuelve al pool DHCP y acaba en otro aparato de la casa, que hereda el permiso.
PAIR_DIAS = int(os.getenv("JARVIS_PAIR_DIAS", "30"))


def _cargar_ips():
    """Lista cruda: admite el formato viejo (['1.2.3.4']) y el nuevo con fecha."""
    try:
        datos = json.load(open(ALLOWED_IPS_FILE, encoding="utf-8")) or []
    except Exception:
        return []
    normal = []
    for e in datos:
        if isinstance(e, str):
            normal.append({"ip": e, "ts": 0.0})
        elif isinstance(e, dict) and e.get("ip"):
            normal.append({"ip": e["ip"], "ts": float(e.get("ts", 0) or 0)})
    return normal


def _guardar_ips(lista):
    try:
        os.makedirs(os.path.dirname(ALLOWED_IPS_FILE), exist_ok=True)
        with open(ALLOWED_IPS_FILE, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[auth] No pude guardar la lista de IPs: {e}")


def _allowed_ips():
    """IPs emparejadas que siguen vigentes (las caducadas se olvidan solas)."""
    lista = _cargar_ips()
    if PAIR_DIAS <= 0:
        return [e["ip"] for e in lista]
    limite = time.time() - PAIR_DIAS * 86400
    vigentes = [e for e in lista if not e["ts"] or e["ts"] >= limite]
    if len(vigentes) != len(lista):
        caducadas = [e["ip"] for e in lista if e not in vigentes]
        print(f"[auth] Emparejamientos caducados: {', '.join(caducadas)}")
        _guardar_ips(vigentes)
    return [e["ip"] for e in vigentes]


_propias = {"ts": 0.0, "ips": set()}


def _ips_propias() -> set:
    """IPs de este mismo PC (cambian con el router: se recalculan cada minuto)."""
    if time.time() - _propias["ts"] < 60:
        return _propias["ips"]
    ips = set(LOCALES)
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except Exception:
        pass
    try:
        import red_movil
        ips.update(e["ip"] for e in red_movil.ips_lan())
    except Exception:
        pass
    try:
        ips.add(_local_ip())
    except Exception:
        pass
    _propias.update(ts=time.time(), ips=ips)
    return ips


def _es_este_pc(ip: str = "") -> bool:
    """¿La petición sale del propio PC? (por localhost o por su IP de la red)."""
    if not ip:
        ip = _ip_cliente()
    return ip in LOCALES or ip in _ips_propias()


# Lo único que se sirve a un aparato que todavía no ha dado el PIN: la propia
# interfaz (que le pide el PIN), cómo comprobarlo y darse de alta, y ficheros
# estáticos sin nada dentro. El PIN y el QR NO: esos solo se ven en el PC.
_RUTAS_PUBLICAS = ("/", "/mobile", "/allow_my_ip", "/token_ok", "/pin_actual",
                   "/modulos.js", "/socket.io.min.js", "/manifest.webmanifest",
                   "/sw.js", "/icon-192.png", "/icon-512.png", "/health")


@app.before_request
def filtro_ips():
    """Quién puede hablar con JARVIS.

    Antes, mientras no hubiera ningún teléfono emparejado, TODO quedaba abierto
    a cualquiera de la red, y /pair y /qr enseñaban el PIN a quien los pidiera:
    cualquiera en el mismo WiFi podía emparejarse solo. Ahora pasa el propio PC,
    los aparatos emparejados y quien trae el PIN; el resto, nada.
    """
    ip = _ip_cliente()
    if _es_este_pc(ip):
        return None
    if request.path in _RUTAS_PUBLICAS or request.path.startswith("/webhook/"):
        return None
    # Socket.IO ya valida el token en on_connect; dejarlo pasar no abre nada.
    if request.path.startswith('/socket.io'):
        return None
    if ip in _allowed_ips():
        return None
    # El PIN es una credencial mas fuerte que la IP: si el router le cambia la
    # IP al movil, sigue entrando. Solo cabecera/query: el cuerpo no se toca
    # aqui para no forzar el parseo de subidas grandes en cada peticion.
    if _auth_ok(request.headers.get('X-Token') or request.args.get('token') or ''):
        return None
    print(f"[auth] IP no autorizada: {ip} -> {request.path}")
    return jsonify({'error': 'IP no autorizada', 'ip': ip,
                    'ayuda': 'Empareja el teléfono desde el PC: botón del móvil en JARVIS.'}), 403


def _solo_este_pc():
    """403 si la petición no sale del PC (ni trae el PIN). None si vale."""
    if _es_este_pc() or _auth_ok(request.headers.get('X-Token') or request.args.get('token') or ''):
        return None
    return jsonify({'error': 'esto solo se ve desde el PC'}), 403


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
    """ORIGEN: la interfaz principal (figura de partículas en WebGL2)."""
    resp = send_from_directory('.', 'origen.html')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/mobile')
def mobile():
    """El teléfono usa la misma interfaz que el PC (el QR apunta aquí)."""
    resp = send_from_directory('.', 'origen.html')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


# Las interfaces antiguas ya no existen: quien tenga un marcador o un QR viejo
# llega a ORIGEN en vez de a un 404.
@app.route('/clasica')
@app.route('/nexus')
@app.route('/aeon')
@app.route('/panel')
@app.route('/dashboard')
@app.route('/centro')
def interfaz_antigua():
    token = request.args.get('token')
    return redirect('/' + (f'?token={token}' if token else ''), code=302)


_cache_par = {"ts": 0.0, "datos": None}
SEGUNDOS_CACHE_PAR = 20


def _datos_emparejar() -> dict:
    """Direcciones, acceso desde fuera y diagnóstico, con caché.

    Averiguarlo cuesta lanzar PowerShell y Tailscale varias veces: se hace una
    vez cada 20 segundos, no en cada consulta del diálogo.
    """
    if _cache_par["datos"] is not None and time.time() - _cache_par["ts"] < SEGUNDOS_CACHE_PAR:
        return _cache_par["datos"]
    urls = _pair_urls()
    remoto_info = {"instalado": False, "activo": False, "publicado": False,
                   "nombre": "", "url": "", "moviles": [], "mensaje": ""}
    try:
        import remoto
        remoto_info["instalado"] = remoto.instalado()
        if remoto_info["instalado"]:
            red = remoto.red()
            remoto_info["activo"] = bool(red.get("activo"))
            remoto_info["nombre"] = red.get("nombre", "")
            remoto_info["mensaje"] = red.get("motivo") or red.get("estado") or ""
            remoto_info["publicado"] = bool(remoto.publicado().get("serve"))
            remoto_info["moviles"] = [a["nombre"] for a in red.get("aparatos", [])
                                      if str(a.get("sistema", "")).lower() in ("android", "ios")]
            if remoto_info["publicado"] and remoto_info["nombre"]:
                remoto_info["url"] = f"https://{remoto_info['nombre']}/mobile"
    except Exception as e:
        remoto_info["mensaje"] = str(e)[:120]

    # La dirección del QR: la de Tailscale con HTTPS vale en casa y fuera (y
    # deja usar el micrófono), pero solo si el móvil está en Tailscale; si no,
    # la del WiFi, que al menos funciona en casa.
    seguras = [u for u in urls if u.get("segura")]
    resto = [u for u in urls if not u.get("segura")]
    if remoto_info["url"] and not seguras:
        seguras = [{"url": remoto_info["url"], "ip": remoto_info["nombre"],
                    "via": "Tailscale con HTTPS", "segura": True, "remota": True}]
    if seguras and remoto_info["moviles"]:
        urls = seguras + resto
        recomendada = seguras[0]["url"]
    else:
        urls = resto + seguras
        recomendada = urls[0]["url"] if urls else _pair_url()

    datos = {"url": recomendada, "urls": urls, "remoto": remoto_info}
    try:
        import red_movil
        datos["firewall"] = red_movil.firewall()
        datos["diagnostico"] = red_movil.diagnostico(jarvis_config.PORT)
    except Exception as e:
        datos["firewall"] = {"error": str(e)[:80]}
        datos["diagnostico"] = []
    _cache_par.update(ts=time.time(), datos=datos)
    return datos


@app.route('/pair_info')
def pair_info():
    """Datos para el diálogo de emparejar del PC (solo desde el PC)."""
    bloqueo = _solo_este_pc()
    if bloqueo:
        return bloqueo
    if request.args.get('fresco'):
        _cache_par["datos"] = None
    return jsonify({'pin': AUTH_TOKEN, **_datos_emparejar()})


@app.route('/api/remoto/preparar', methods=['POST'])
def remoto_preparar():
    """Deja JARVIS listo para usarse fuera de casa, si se puede sin preguntar.

    Con Tailscale instalado y con la sesión abierta, publica el servidor en la
    red PRIVADA del señor (`tailscale serve`), por HTTPS: solo sus aparatos
    llegan, y con HTTPS el micrófono del móvil funciona. Internet (funnel)
    nunca se activa desde aquí.
    """
    if not _es_este_pc():
        return jsonify({'error': 'esto se hace desde el PC'}), 403
    try:
        import remoto
        texto = remoto.activar(log=print)
    except Exception as e:
        texto = f'No pude activar el acceso desde fuera: {str(e)[:150]}'
    _cache_par["datos"] = None
    return jsonify({'texto': texto, **_datos_emparejar()})


@app.route('/abrir_puerto', methods=['POST'])
def abrir_puerto():
    """Crea la regla del cortafuegos. Solo desde el propio PC."""
    if not _es_este_pc():
        return jsonify({'error': 'esto se hace desde el PC'}), 403
    try:
        import red_movil
        _cache_par["datos"] = None
        return jsonify({'texto': red_movil.abrir_firewall(log=print),
                        'firewall': red_movil.firewall()})
    except Exception as e:
        return jsonify({'error': str(e)[:150]}), 500


@app.route('/notify', methods=['POST'])
def notify_push():
    """Push interno: reenvía avisos de Jarvis al móvil conectado."""
    if not _es_este_pc():
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
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    datos = request.get_json(silent=True) or {}
    texto = (datos.get('texto') or '').strip()
    if not texto:
        return jsonify({'ok': False, 'error': 'texto vacío'}), 400
    def _copiar():
        # `subprocess` no estaba importado en este ámbito: el hilo moría con un
        # NameError silencioso y el portapapeles nunca se llenaba.
        import subprocess
        try:
            script = "Set-Clipboard -Value @'\n" + texto + "\n'@"
            subprocess.Popen(["powershell", "-NoProfile", "-Command", script],
                             creationflags=0x08000000)
        except Exception as e:
            print(f"[clipboard] no pude copiar: {e}")
    threading.Thread(target=_copiar, daemon=True).start()
    return jsonify({'ok': True})


# ── API REST: AGENDA Y CALENDARIO HÍBRIDO ─────────────────────────────────────
@app.route("/api/calendar/status", methods=["GET"])
def api_calendar_status():
    if not calendar_engine:
        return jsonify({"error": "calendar_engine no cargado"}), 503
    return jsonify(calendar_engine.get_status())


@app.route("/api/calendar/events", methods=["GET"])
def api_calendar_events():
    if not calendar_engine:
        return jsonify({"error": "calendar_engine no cargado"}), 503
    t_min = request.args.get("time_min")
    t_max = request.args.get("time_max")
    q = request.args.get("q")
    days = int(request.args.get("days", 14))
    if not t_min:
        now_dt = datetime.now()
        t_min = now_dt.strftime("%Y-%m-%dT00:00:00")
        t_max = (now_dt + timedelta(days=days)).strftime("%Y-%m-%dT23:59:59")
    events = calendar_engine.list_events(time_min=t_min, time_max=t_max, query=q)
    return jsonify({"events": events, "count": len(events)})


@app.route("/api/calendar/today", methods=["GET"])
def api_calendar_today():
    if not calendar_engine:
        return jsonify({"error": "calendar_engine no cargado"}), 503
    events = calendar_engine.get_today_events()
    return jsonify({"events": events, "count": len(events)})


@app.route("/api/calendar/events", methods=["POST"])
def api_calendar_create():
    if not calendar_engine:
        return jsonify({"error": "calendar_engine no cargado"}), 503
    data = request.get_json(silent=True) or {}
    summary = (data.get("summary") or data.get("titulo") or "").strip()
    start = (data.get("start") or data.get("inicio") or "").strip()
    end = (data.get("end") or data.get("fin") or "").strip() or None
    description = (data.get("description") or data.get("descripcion") or "").strip()
    location = (data.get("location") or data.get("ubicacion") or "").strip()
    if not summary or not start:
        return jsonify({"error": "summary y start son obligatorios"}), 400
    ev = calendar_engine.create_event(summary, start, end, description=description, location=location)
    return jsonify({"ok": True, "event": ev})


@app.route("/api/calendar/events/<event_id>", methods=["DELETE"])
def api_calendar_delete(event_id):
    if not calendar_engine:
        return jsonify({"error": "calendar_engine no cargado"}), 503
    ok = calendar_engine.delete_event(event_id)
    return jsonify({"ok": ok, "deleted_id": event_id})


@app.route("/api/calendar/reschedule", methods=["POST"])
def api_calendar_reschedule():
    if not calendar_engine:
        return jsonify({"error": "calendar_engine no cargado"}), 503
    data = request.get_json(silent=True) or {}
    event_id = data.get("event_id")
    new_start = data.get("new_start")
    new_end = data.get("new_end")
    if not event_id or not new_start:
        return jsonify({"error": "event_id y new_start son obligatorios"}), 400
    ev = calendar_engine.reschedule_event(event_id, new_start, new_end)
    return jsonify({"ok": ev is not None, "event": ev})


# ── API REST: ARSENAL TÁCTICO DEL SISTEMA ────────────────────────────────────
@app.route("/api/system/processes", methods=["GET"])
def api_system_processes():
    if not pc_tactical:
        return jsonify({"error": "pc_tactical no disponible"}), 503
    limit = int(request.args.get("limit", 15))
    sort_by = request.args.get("sort", "cpu")
    procs = pc_tactical.list_top_processes(limit=limit, sort_by=sort_by)
    return jsonify({"processes": procs, "count": len(procs)})


@app.route("/api/system/kill", methods=["POST"])
def api_system_kill():
    if not pc_tactical:
        return jsonify({"error": "pc_tactical no disponible"}), 503
    data = request.get_json(silent=True) or {}
    target = data.get("target") or data.get("pid") or data.get("name")
    if not target:
        return jsonify({"error": "target no especificado"}), 400
    res = pc_tactical.kill_process(target)
    return jsonify(res)


@app.route("/api/system/clean_ram", methods=["POST"])
def api_system_clean_ram():
    if not pc_tactical:
        return jsonify({"error": "pc_tactical no disponible"}), 503
    res = pc_tactical.clean_ram()
    return jsonify(res)


@app.route("/api/system/lockdown", methods=["POST"])
def api_system_lockdown():
    if not pc_tactical:
        return jsonify({"error": "pc_tactical no disponible"}), 503
    res = pc_tactical.lockdown_station()
    return jsonify(res)


@app.route("/api/system/network_radar", methods=["GET"])
def api_system_network_radar():
    if not pc_tactical:
        return jsonify({"error": "pc_tactical no disponible"}), 503
    conns = pc_tactical.scan_network_connections(limit=25)
    return jsonify({"connections": conns, "count": len(conns)})


# ── API REST: PROTOCOLO INTER-AGENTES ────────────────────────────────────────
@app.route("/api/agent/peer_status", methods=["GET"])
def api_agent_peer_status():
    if not pc_tactical:
        return jsonify({"online": False, "error": "pc_tactical no disponible"}), 503
    st = pc_tactical.get_peer_status("ultron")
    return jsonify(st)


@app.route("/api/agent/delegate", methods=["POST"])
def api_agent_delegate():
    if not pc_tactical:
        return jsonify({"error": "pc_tactical no disponible"}), 503
    data = request.get_json(silent=True) or {}
    msg = data.get("message") or data.get("text")
    if not msg:
        return jsonify({"error": "message requerido"}), 400
    res = pc_tactical.delegate_to_peer("ultron", msg)
    return jsonify(res)


@app.route('/camera')
def camera_view():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>JARVIS - Cámara</title>
<style>body{background:#05070d;margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh}
img{max-width:100vw;max-height:100vh;border:3px solid #00d4ff55;border-radius:8px}
.hint{position:fixed;bottom:10px;left:0;right:0;text-align:center;color:#5a7a95;font-size:12px}</style></head>
<body><img id="feed" alt="Cámara JARVIS"><div class="hint">JARVIS - vista en vivo de la cámara</div><script>document.getElementById("feed").src="/camera_feed?token="+encodeURIComponent(new URLSearchParams(location.search).get("token")||"");</script></body></html>"""
    return render_template_string(html)


@app.route('/camera_feed')
def camera_feed():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
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
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>JARVIS - Escritorio</title>
<style>body{background:#05070d;margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh}
img{max-width:100vw;max-height:100vh;border:3px solid #00d4ff55;border-radius:8px}
.hint{position:fixed;bottom:10px;left:0;right:0;text-align:center;color:#5a7a95;font-size:12px}</style></head>
<body><img id="feed" alt="Escritorio JARVIS"><div class="hint">JARVIS - su escritorio en vivo</div><script>document.getElementById("feed").src="/screen_feed?token="+encodeURIComponent(new URLSearchParams(location.search).get("token")||"");</script></body></html>"""
    return render_template_string(html)


@app.route('/screen_feed')
def screen_feed():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
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
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
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
// El PIN llega en la URL con la que se abrió esta página y hay que reenviarlo
// en cada acción: /mouse lo exige.
var TOKEN = new URLSearchParams(location.search).get('token') || '';
function post(datos) {
  fetch('/mouse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Token': TOKEN },
    body: JSON.stringify(datos)
  });
}
</script></body></html>"""
    return render_template_string(html)


# Estructuras de SendInput. La version anterior montaba el INPUT a mano con un
# buffer de 24 bytes y un layout inventado, asi que Windows rechazaba cada
# pulsacion y escribir desde el movil no hacia absolutamente nada. Estas son
# las estructuras reales (en x64 sizeof(INPUT) = 40).
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]


_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004

# Teclas con nombre que el movil puede pedir. Antes solo habia cuatro y el
# resto de botones del touchpad no hacian nada.
_TECLAS = {
    'enter': 0x0D, 'backspace': 0x08, 'esc': 0x1B, 'escape': 0x1B,
    'tab': 0x09, 'space': 0x20, 'delete': 0x2E, 'supr': 0x2E,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    'win': 0x5B, 'f5': 0x74, 'f11': 0x7A,
    'volup': 0xAF, 'voldown': 0xAE, 'mute': 0xAD,
    'play': 0xB3, 'next': 0xB0, 'prev': 0xB1,
}


def _enviar_unicode(texto):
    """Escribe texto en la ventana activa, carácter a carácter.

    Va por unidades UTF-16 para que los caracteres fuera del plano básico
    (emoji) tampoco rompan nada.
    """
    u = ctypes.windll.user32
    eventos = []
    crudo = texto.encode('utf-16-le')
    unidades = [int.from_bytes(crudo[i:i + 2], 'little') for i in range(0, len(crudo), 2)]
    for unidad in unidades:
        for flags in (_KEYEVENTF_UNICODE, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP):
            ev = _INPUT(type=_INPUT_KEYBOARD)
            ev.u.ki = _KEYBDINPUT(wVk=0, wScan=unidad, dwFlags=flags, time=0,
                                  dwExtraInfo=None)
            eventos.append(ev)
    if not eventos:
        return 0
    bloque = (_INPUT * len(eventos))(*eventos)
    return u.SendInput(len(eventos), ctypes.byref(bloque), ctypes.sizeof(_INPUT))


@app.route('/mouse', methods=['POST'])
def mouse_accion():
    # Controlar el ratón y el teclado del PC es lo más sensible que expone el
    # servidor: sin esta comprobación cualquiera en la misma Wi-Fi podía mover
    # el cursor y escribir en el equipo sin saber el PIN.
    if not _auth_ok(_req_token()):
        return jsonify({'ok': False, 'error': 'token invalido'}), 403
    datos = request.get_json(silent=True) or {}
    acc = datos.get('action')
    try:
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
            vk = _TECLAS.get(str(datos.get('key', '')).lower())
            if not vk:
                return jsonify({'ok': False, 'error': 'tecla desconocida'}), 400
            u.keybd_event(vk, 0, 0, 0)
            u.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)
        elif acc == 'type':
            enviados = _enviar_unicode((datos.get('text') or '')[:500])
            return jsonify({'ok': True, 'eventos': enviados})
        else:
            return jsonify({'ok': False, 'error': 'accion desconocida'}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── SUBIR FOTOS/ARCHIVOS DESDE EL MÓVIL ────────────────────────────────────────
@app.route('/upload', methods=['POST'])
def upload_movil():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
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
# La telemetría de ORIGEN pide esto cada 2,5 s. Antes, cada petición arrancaba
# un PowerShell para leer la temperatura (24 por minuto, con cientos de ms de
# CPU y decenas de MB cada uno), recorría todos los procesos del equipo y se
# quedaba 0,4 s parada midiendo la CPU. Ahora:
#  - la temperatura se lee aparte, como mucho una vez por minuto, y si el equipo
#    no la da (lo normal sin permisos de administrador), cada 15 minutos;
#  - la CPU se mide sin esperar: psutil compara con la llamada anterior;
#  - el top de procesos solo se calcula si se pide (?top=1);
#  - la respuesta se reutiliza 2 s si la piden a la vez el PC y el móvil.
_TEMP = {'valor': None, 'hasta': 0.0}
_TEMP_LOCK = threading.Lock()
_STATS = {'datos': None, 'hasta': 0.0, 'cpu_lista': False}


def _leer_temperatura():
    valor = None
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty CurrentTemperature"],
                           capture_output=True, text=True, timeout=8, creationflags=0x08000000)
        v = (r.stdout or '').strip()
        if v:
            valor = round((int(v) / 10) - 273.15, 1)
    except Exception:
        pass
    finally:
        _TEMP['valor'] = valor
        _TEMP['hasta'] = time.time() + (60 if valor is not None else 900)
        _TEMP_LOCK.release()


def _temperatura():
    """La última temperatura leída; si toca, se relee aparte, sin esperar."""
    if os.name != 'nt':
        return None
    if time.time() >= _TEMP['hasta'] and _TEMP_LOCK.acquire(blocking=False):
        threading.Thread(target=_leer_temperatura, daemon=True).start()
    return _TEMP['valor']


def _top_procesos(psutil):
    top = []
    for p in sorted(psutil.process_iter(['name', 'cpu_percent', 'memory_percent']),
                    key=lambda p: p.info['cpu_percent'] or 0, reverse=True)[:5]:
        top.append({'nombre': p.info['name'] or '?', 'cpu': round(p.info['cpu_percent'] or 0, 1),
                    'mem': round(p.info['memory_percent'] or 0, 1)})
    return top


@app.route('/stats')
def stats_json():
    """Telemetria del equipo, en un unico formato.

    Habia DOS rutas '/stats' distintas declaradas en este fichero, con datos
    diferentes cada una. Flask se queda con la primera que encuentra, asi que
    la segunda no se ejecutaba nunca y el HUD se quedaba sin los nucleos, sin
    el total de RAM y sin el tiempo encendido: los pedia y no llegaban. Aqui
    van todas las claves juntas, las del panel del movil y las del HUD.
    """
    con_top = bool(request.args.get('top'))
    if not con_top and _STATS['datos'] is not None and time.time() < _STATS['hasta']:
        return jsonify(_STATS['datos'])
    try:
        import psutil
        if not _STATS['cpu_lista']:
            # La primera medida sin espera no vale (no hay con qué comparar).
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
            time.sleep(0.2)
            _STATS['cpu_lista'] = True
        cpu = psutil.cpu_percent(interval=None)
        try:
            cores = [round(x, 1) for x in psutil.cpu_percent(interval=None, percpu=True)]
        except Exception:
            cores = []
        ram = psutil.virtual_memory()
        disco = psutil.disk_usage((os.environ.get('SystemDrive', 'C:') + '\\') if os.name == 'nt' else '/')
        net = psutil.net_io_counters()
        top = _top_procesos(psutil) if con_top else []
        temp = _temperatura()
        try:
            arranque = psutil.boot_time()
            uptime = int(time.time() - arranque)
        except Exception:
            uptime = 0
        try:
            b = psutil.sensors_battery()
            bateria = None if b is None else {'percent': round(b.percent),
                                              'plugged': bool(b.power_plugged)}
        except Exception:
            bateria = None

        datos = {
            # Claves del panel del movil / dashboard
            'cpu': cpu, 'ram_pct': ram.percent,
            'ram_used_gb': round(ram.used / 1073741824, 1),
            'ram_total_gb': round(ram.total / 1073741824, 1),
            'disco_libre_gb': round(disco.free / 1073741824, 1),
            'disco_total_gb': round(disco.total / 1073741824, 1),
            'net_mb': round(net.bytes_recv / 1048576, 1),
            'temp': temp, 'top': top,
            'hora': time.strftime('%H:%M:%S'),
            # Claves del HUD de escritorio
            'cpu_cores': cores,
            'ram': f"{round(ram.used / 1073741824, 1)} GB",
            'ram_total': f"{round(ram.total / 1073741824, 1)} GB",
            'disk_free': f"{round(disco.free / 1073741824, 1)} GB",
            'disk_total': f"{round(disco.total / 1073741824, 1)} GB",
            'net_sent': f"{round(net.bytes_sent / 1048576, 1)} MB",
            'net_recv': f"{round(net.bytes_recv / 1048576, 1)} MB",
            'uptime': uptime, 'battery': bateria,
        }
        if not con_top:
            _STATS['datos'], _STATS['hasta'] = datos, time.time() + 2.0
        return jsonify(datos)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/allow_my_ip', methods=['POST'])
def permitir_mi_ip():
    """Auto-emparejamiento. EXIGE el PIN: sin el, cualquiera en la misma red
    (o en la Tailnet) podia darse de alta a si mismo llamando a este endpoint,
    que ademas esta exento del filtro de IPs."""
    token = (request.headers.get('X-Token') or request.args.get('token')
             or (request.get_json(silent=True) or {}).get('token') or '')
    if not _auth_ok(token):
        print(f"[auth] Emparejamiento rechazado desde {_ip_cliente()}: PIN incorrecto.")
        return jsonify({'error': 'PIN incorrecto o ausente'}), 403
    ip = _ip_cliente()
    lista = [e for e in _cargar_ips() if e["ip"] != ip]
    if ip:
        lista.append({"ip": ip, "ts": time.time()})
    _guardar_ips(lista)
    return jsonify({'ok': True, 'ip': ip, 'caduca_en_dias': PAIR_DIAS or None})


@app.route('/remoto', methods=['GET', 'POST'])
def acceso_remoto():
    """Estado del acceso desde fuera de casa y como encenderlo o apagarlo."""
    import remoto
    if request.method == 'GET':
        return jsonify(remoto.estado())
    if not _es_este_pc():
        return jsonify({'error': 'esto se enciende desde el propio PC'}), 403
    datos = request.get_json(silent=True) or {}
    accion = (datos.get('accion') or 'activar').lower()
    _cache_par["datos"] = None
    if accion == 'activar':
        return jsonify({'texto': remoto.activar(log=print), 'estado': remoto.estado()})
    if accion == 'desactivar':
        return jsonify({'texto': remoto.desactivar(log=print), 'estado': remoto.estado()})
    if accion == 'internet':
        return jsonify({'texto': remoto.publicar_en_internet(
            confirmado=bool(datos.get('confirmo')), log=print),
            'estado': remoto.estado()})
    return jsonify({'error': f'no sé hacer «{accion}»'}), 400


@app.route('/token_ok')
def token_ok():
    """¿Vale este PIN? Sin mirar la IP.

    El movil comprobaba su PIN pidiendo el historial, pero desde una IP ya
    emparejada eso responde 200 aunque el PIN sea viejo: entraba, el socket lo
    rechazaba despues y acababa en la pantalla de login sin saber por que.
    """
    t = request.headers.get('X-Token') or request.args.get('token') or ''
    espera = _bloqueado(_ip_cliente())
    if espera:
        return jsonify({'ok': False, 'bloqueado': True,
                        'minutos': int(espera // 60) + 1})
    return jsonify({'ok': _auth_ok(t)})


@app.route('/pin_actual')
def pin_actual():
    """PIN de hoy, solo para aparatos que YA estaban emparejados.

    El PIN se renueva cada 30 dias y hasta ahora eso obligaba a volver al PC,
    abrir el QR y escanear otra vez. Un telefono cuya IP ya esta emparejada
    tiene acceso completo de todos modos, asi que puede recoger el PIN nuevo el
    solo y seguir funcionando sin que el señor se entere.
    """
    ip = _ip_cliente()
    if not _es_este_pc(ip) and ip not in _allowed_ips():
        return jsonify({'error': 'este aparato no esta emparejado'}), 403
    return jsonify({'pin': AUTH_TOKEN})


@app.route('/rotate_token', methods=['POST'])
def rotar_token():
    """Cambia el PIN al instante (por si se filtro el QR o una captura)."""
    global AUTH_TOKEN
    token = (request.headers.get('X-Token') or request.args.get('token')
             or (request.get_json(silent=True) or {}).get('token') or '')
    if not _auth_ok(token):
        return jsonify({'error': 'PIN incorrecto o ausente'}), 403
    AUTH_TOKEN = _nuevo_token()
    print("[auth] PIN rotado por peticion del señor. Hay que reemparejar el movil.")
    return jsonify({'ok': True, 'pin': AUTH_TOKEN,
                    'aviso': 'Vuelva a emparejar el teléfono con el QR nuevo.'})


@app.route('/pair_status')
def estado_emparejamiento():
    """Que aparatos estan emparejados y cuando caduca cada uno."""
    bloqueo = _solo_este_pc()
    if bloqueo:
        return bloqueo
    ahora = time.time()
    filas = []
    for e in _cargar_ips():
        dias = None
        if PAIR_DIAS > 0 and e["ts"]:
            dias = round(PAIR_DIAS - (ahora - e["ts"]) / 86400, 1)
        filas.append({"ip": e["ip"], "dias_restantes": dias})
    return jsonify({"emparejados": filas, "pin_dias": PIN_DIAS, "pair_dias": PAIR_DIAS})


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


def _avisar_voz_al_nucleo(texto: str, fin: bool = False):
    """Cuenta a la escucha continua que el navegador habla (o terminó).

    Solo desde este mismo PC: si la voz suena en el móvil, el micrófono del
    ordenador no la oye y no debe abrir una conversación sin nombre.
    """
    if not _es_este_pc():
        return
    nucleo = getattr(core, '_c', None)      # sin forzar la carga del núcleo
    try:
        if nucleo is not None and fin:
            nucleo.voz_externa_fin()
        elif nucleo is not None:
            nucleo.voz_externa(texto)
    except Exception as e:
        print(f"[tts] No pude avisar a la escucha: {e}")


@app.route('/api/voz_fin', methods=['POST'])
def api_voz_fin():
    """El navegador terminó de hablar: se le puede contestar sin decir «Jarvis»."""
    _avisar_voz_al_nucleo('', fin=True)
    return Response(status=204)


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
    # La interfaz unica manda que personalidad habla, para que cada una suene
    # distinta con la voz neuronal local.
    agente = (data.get('agente') or getattr(core, 'nombre_agente', 'jarvis') or 'jarvis').lower()
    sin_cabecera = {'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'}
    _avisar_voz_al_nucleo(text)

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
        try:
            import voz_propia
            voz_local = voz_propia.voz_de(agente, core)
        except Exception:
            voz_local = jarvis_piper.DEFAULT_VOICE
        if not jarvis_piper.disponible(voz_local):
            voz_local = jarvis_piper.DEFAULT_VOICE
        if jarvis_piper.disponible(voz_local):
            audio = jarvis_piper.sintetizar_bytes(text[:1000], voice_id=voz_local)
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
    if _es_este_pc():
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
    """Código QR de emparejamiento: URL pública con token.

    Antes esto devolvía un JSON de error («No module named qrcode») en cuanto
    faltaba la librería, y la página de emparejamiento se quedaba con el hueco
    de la imagen vacío. Ahora jarvis_qr genera el código él mismo si hace
    falta, así que el QR sale siempre.
    """
    bloqueo = _solo_este_pc()
    if bloqueo:
        return bloqueo
    try:
        from jarvis_qr import qr_response_data
        # ?url= permite pedir el QR de una direccion concreta cuando el equipo
        # esta en varias redes a la vez y la principal no es la buena.
        pedida = (request.args.get('url') or '').strip()
        destino = pedida if pedida.startswith('http') else _pair_url()
        if 'token=' not in destino:
            destino += ('&' if '?' in destino else '?') + f'token={AUTH_TOKEN}'
        datos, mimetype = qr_response_data(destino)
        resp = Response(datos, mimetype=mimetype)
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/pair')
def pair():
    """Página de emparejamiento. Se mantiene viva sola.

    El fallo de siempre: el router da una IP nueva y el QR de la pantalla apunta
    a la vieja; el teléfono escanea y se queda cargando. Ahora la página
    pregunta cada cuatro segundos, rehace el QR si la dirección cambió y avisa
    en cuanto un teléfono entra de verdad.
    """
    bloqueo = _solo_este_pc()
    if bloqueo:
        return bloqueo
    # El PIN y la direccion se pintan ya en el HTML: la pagina no puede salir
    # con «------» mientras se resuelve la primera consulta a la red.
    html = (_PAGINA_PAIR
            .replace('__PIN__', AUTH_TOKEN)
            .replace('__URL__', _pair_url()))
    resp = Response(html, mimetype='text/html')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


_PAGINA_PAIR = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JARVIS - Emparejar telefono</title>
<style>
:root{color-scheme:dark}
body{background:#05070d;color:#cfe8ff;font-family:Segoe UI,system-ui,sans-serif;
margin:0;padding:26px 16px 40px;display:flex;flex-direction:column;align-items:center;text-align:center}
h1{color:#00d4ff;letter-spacing:3px;text-transform:uppercase;text-shadow:0 0 15px #00d4ff66;margin:0 0 4px}
img{border:6px solid #00d4ff55;border-radius:14px;background:#fff;padding:10px}
.pin{font-size:56px;font-weight:800;letter-spacing:12px;color:#7ee7ff;background:#0a1420;
border:2px solid #00d4ff66;border-radius:16px;padding:6px 22px;margin:6px 0;text-shadow:0 0 18px #00d4ff}
.hint{color:#5a7a95;font-size:13px;margin:4px 0;max-width:520px}
code{background:#0a1420;padding:4px 10px;border-radius:8px;color:#7ee7ff;font-size:15px}
.ok{color:#5cffb1;font-weight:700}
.aviso{color:#ffd479}
.tarjeta{background:#080f1a;border:1px solid #123047;border-radius:14px;padding:14px 18px;
margin:14px 0;max-width:560px;text-align:left}
.tarjeta h3{margin:0 0 8px;color:#7ee7ff;font-size:14px;letter-spacing:1px;text-transform:uppercase}
.tarjeta p{margin:6px 0;font-size:13px;color:#9fc3dd}
button{background:#0a1a2a;color:#7ee7ff;border:1px solid #00d4ff66;border-radius:10px;
padding:8px 16px;font-size:13px;cursor:pointer;margin:4px 4px 0 0}
button:hover{background:#0f2740}
.otras{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:10px}
.otras figure{margin:0;background:#080f1a;border:1px solid #123047;border-radius:12px;padding:8px}
.otras img{width:130px;border-width:3px;padding:5px}
.otras figcaption{font-size:11px;color:#5a7a95;margin-top:6px;max-width:140px}
</style></head><body>
<h1>JARVIS Mobile</h1>
<p class="hint">Escanee el código con la cámara del teléfono. Ya lleva el PIN dentro:
no hay que teclear nada.</p>
<img id="qr" src="/qr" alt="QR de emparejamiento" width="240">
<p class="hint">Dirección: <code id="url">__URL__</code></p>
<p class="hint">PIN por si lo pide a mano:</p>
<div class="pin" id="pin">__PIN__</div>
<p class="hint" id="estado">Esperando al teléfono…</p>

<div class="tarjeta" id="ayuda" style="display:none">
  <h3>Si el teléfono no carga</h3>
  <div id="motivos"></div>
  <button id="btn-puerto" style="display:none">Abrir el puerto (pide permiso de Windows)</button>
  <button id="btn-otras">Ver los QR de las otras direcciones</button>
</div>
<div class="otras" id="otras"></div>

<script>
let urlActual = '__URL__', emparejadosAntes = null;

async function json(ruta, opciones){
  const r = await fetch(ruta, opciones || {});
  return r.json();
}

function pintarMotivos(lista, firewall){
  const caja = document.getElementById('motivos');
  caja.innerHTML = lista.map(m =>
    `<p><b class="aviso">${m.que}</b><br>${m.hacer}</p>`).join('') ||
    '<p>Todo parece correcto por este lado. Compruebe que el teléfono está en el mismo WiFi.</p>';
  document.getElementById('ayuda').style.display = 'block';
  document.getElementById('btn-puerto').style.display =
    (firewall && firewall.hace_falta) ? 'inline-block' : 'none';
}

async function refrescar(){
  try{
    const d = await json('/pair_info');
    document.getElementById('pin').textContent = d.pin;
    if (d.url !== urlActual){
      urlActual = d.url;
      document.getElementById('url').textContent = d.url;
      // La IP cambió (o es la primera vez): QR nuevo, sin recargar la página.
      document.getElementById('qr').src = '/qr?v=' + Date.now();
    }
    pintarMotivos(d.diagnostico || [], d.firewall);
    window._urls = d.urls || [];
  }catch(e){}

  try{
    const p = await json('/pair_status');
    const cuantos = (p.emparejados || []).length;
    const estado = document.getElementById('estado');
    if (cuantos){
      const ips = p.emparejados.map(e => e.ip).join(', ');
      estado.innerHTML = `<span class="ok">Teléfono emparejado ✓</span> (${ips})`;
      if (emparejadosAntes !== null && cuantos > emparejadosAntes)
        document.getElementById('ayuda').style.display = 'none';
    }else{
      estado.textContent = 'Esperando al teléfono…';
    }
    emparejadosAntes = cuantos;
  }catch(e){}
}

document.getElementById('btn-otras').onclick = () => {
  const caja = document.getElementById('otras');
  if (caja.innerHTML){ caja.innerHTML = ''; return; }
  caja.innerHTML = (window._urls || []).map(u =>
    `<figure><img src="/qr?url=${encodeURIComponent(u.url)}" alt="QR ${u.ip}">
     <figcaption>${u.ip}<br>${u.via}</figcaption></figure>`).join('');
};

document.getElementById('btn-puerto').onclick = async (e) => {
  e.target.disabled = true;
  e.target.textContent = 'Pidiendo permiso a Windows…';
  const r = await json('/abrir_puerto', {method:'POST'});
  e.target.textContent = r.texto || r.error || 'Hecho';
  refrescar();
};

refrescar();
setInterval(refrescar, 4000);
</script>
</body></html>"""


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


def _transcribir_audio(ruta):
    """Transcribe un audio del movil. Acepta el .webm tal cual.

    faster-whisper decodifica por su cuenta (usa PyAV), asi que NO hace falta
    tener ffmpeg instalado ni convertir nada a WAV previamente. Antes se
    llamaba a ffmpeg siempre y, como en Windows no suele estar en el PATH, el
    boton de voz del movil devolvia «no pude convertir el audio» y no habia
    manera de dictarle nada al asistente.
    """
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    segs, _info = _whisper_model.transcribe(ruta, language="es")
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
        # Primero se intenta transcribir el fichero tal cual: faster-whisper
        # sabe abrir webm/opus el solo. Solo si eso falla se recurre a ffmpeg,
        # que puede no estar instalado.
        try:
            texto = _transcribir_audio(ruta_in)
        except Exception as e_directo:
            print(f"[voice] lectura directa fallida ({e_directo}); pruebo con ffmpeg")
            ruta_wav = os.path.join(_tf.gettempdir(), f"voz_{_uuid.uuid4().hex}.wav")
            try:
                r = _sp.run([_ffmpeg_path(), "-y", "-i", ruta_in, "-ar", "16000",
                             "-ac", "1", ruta_wav], capture_output=True, timeout=120)
            except FileNotFoundError:
                return jsonify({'error': 'No puedo leer el audio y ffmpeg no esta '
                                         'instalado. Instala faster-whisper o ffmpeg.'}), 500
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


@app.route('/api/modelado3d/estado')
def api_modelado3d_estado():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    try:
        import modelado3d
        return jsonify({
            'blender': modelado3d.disponible(),
            'blender_exe': modelado3d._blender(),
            'backends': modelado3d.backends(),
            'resumen': modelado3d.estado_backends(),
        })
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 500


@app.route('/api/ciencias/estado')
def api_ciencias_estado():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    try:
        import ciencias
        out = ciencias.resumen_estado()
        try:
            import entrenar_ciencias
            out['entrenamiento'] = entrenar_ciencias.estado()
        except Exception as e:
            out['entrenamiento'] = {'error': str(e)[:120]}
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 500


@app.route('/api/cerebro/estado')
def api_cerebro_estado():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    out = {}
    for nombre, fn in (
        ('memoria', lambda: __import__('memoria_grafo').estado()),
        ('presupuesto', lambda: __import__('presupuesto').estado()),
        ('salud_proveedores', lambda: __import__('cerebro_salud').estado()),
        ('router', lambda: __import__('router_modelo').estado()),
        ('automejora', lambda: {'activo': __import__('auto_mejora').activo()}),
    ):
        try:
            out[nombre] = fn()
        except Exception as e:
            out[nombre] = {'error': str(e)[:120]}
    try:
        import permisos
        out['agente_modo'] = permisos.modo()
    except Exception:
        pass
    return jsonify(out)


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


# ── NEXUS: UNA SOLA INTERFAZ PARA LAS DOS PERSONALIDADES ─────────────────────
# La pagina /nexus habla con JARVIS (este proceso) y con ULTRON (el servidor del
# puerto 8766) desde un unico origen: asi no hay CORS ni dos PIN que teclear.
# Todo lo que va a ULTRON pasa por aqui, con su token leido de su propio fichero.
ULTRON_PUERTO = int(os.getenv('ULTRON_PORT', '8766'))
ULTRON_AUTH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'ultron_interface', '.ultron_auth')


def _pin_ultron() -> str:
    """PIN de ULTRON. Admite el formato nuevo (JSON) y el antiguo (texto)."""
    try:
        with open(ULTRON_AUTH, encoding='utf-8') as f:
            bruto = f.read().strip()
        if bruto.startswith('{'):
            return str(json.loads(bruto).get('token', ''))
        return bruto
    except Exception:
        return ''


def _ultron(ruta: str, metodo: str = 'GET', cuerpo=None, timeout: float = 120.0):
    """Llama al servidor de ULTRON. Devuelve (ok, datos)."""
    url = f'http://127.0.0.1:{ULTRON_PUERTO}{ruta}'
    datos = json.dumps(cuerpo or {}).encode('utf-8') if metodo == 'POST' else None
    peticion = urllib.request.Request(
        url, data=datos, method=metodo,
        headers={'Content-Type': 'application/json', 'X-Token': _pin_ultron()})
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as r:
            return True, json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return False, {'error': str(e)[:200]}


@app.route('/modulos.js')
def modulos_js():
    """Los modulos de ORIGEN (sistema, ciencias, 3D, correo…): una sola copia."""
    resp = send_from_directory('.', 'modulos.js', mimetype='application/javascript')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/nexus/estado')
def api_nexus_estado():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    vivo_ultron, salud = _ultron('/health', timeout=4)
    estado = {
        'jarvis': {'online': bool(core), 'modelo': jarvis_config.MODEL
                   if hasattr(jarvis_config, 'MODEL') else os.getenv('QWEN_MODEL', '')},
        'ultron': {'online': vivo_ultron, 'detalle': salud if vivo_ultron else salud},
    }
    try:
        if core:
            estado['jarvis']['animo'] = dict(getattr(core, '_estado_animo', {}) or {})
            estado['jarvis']['perfil'] = (core.get_pref('perfil') or '')
    except Exception:
        pass
    return jsonify(estado)


@app.route('/api/nexus/cmd', methods=['POST'])
def api_nexus_cmd():
    """Una orden, tres destinos: JARVIS, ULTRON o los dos deliberando."""
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    datos = request.get_json(silent=True) or {}
    texto = (datos.get('texto') or '').strip()
    agente = (datos.get('agente') or 'jarvis').lower()
    if not texto or len(texto) > 2000:
        return jsonify({'error': 'texto invalido'}), 400

    if agente == 'ultron':
        ok, respuesta = _ultron('/cmd', 'POST', {'texto': texto})
        if not ok:
            return jsonify({'agente': 'ultron', 'respuesta':
                            'ULTRON no responde. ¿Está arrancado su servidor '
                            f'en el puerto {ULTRON_PUERTO}?'}), 200
        return jsonify({'agente': 'ultron',
                        'respuesta': respuesta.get('respuesta') or respuesta.get('reply', '')})

    if agente == 'consejo':
        if not core:
            return jsonify({'error': 'nucleo no disponible'}), 500
        try:
            import consejo
            return jsonify({'agente': 'consejo',
                            **consejo.deliberar_estructurado(core, texto, log=print)})
        except Exception as e:
            return jsonify({'agente': 'consejo', 'ok': False,
                            'error': str(e)[:200]}), 500

    if not core:
        return jsonify({'error': 'nucleo no disponible'}), 500
    resultado = {}

    def _trabajo(res):
        try:
            res['respuesta'] = (core.process_text_stream(texto)
                                or 'Señor, no he entendido.')[:2000]
        except Exception as e:
            res['respuesta'] = f'Señor, tuve un problema: {str(e)[:150]}'

    hilo = threading.Thread(target=_trabajo, args=(resultado,), daemon=True)
    hilo.start()
    hilo.join(timeout=150)
    return jsonify({'agente': 'jarvis',
                    'respuesta': resultado.get('respuesta', 'Procesando…')})


# ── PANEL DE CONTROL ──────────────────────────────────────────────────────────
# Todo lo que el asistente sabe hacer estaba solo detras de una frase hablada.
# Aqui se ve y se maneja: estado de cada subsistema, deshacer, perfiles, indice,
# seguridad, habilidades pendientes y rendimiento.
@app.route('/api/nexus/u/<path:ruta>', methods=['GET', 'POST'])
def api_nexus_ultron(ruta):
    """Pasarela a CUALQUIER endpoint de ULTRON desde el mismo origen.

    Sin esto habría que replicar aquí una a una sus rutas (guardián, modos,
    radar, purga, bloqueo de IPs...). Con la pasarela, el NEXUS puede usar todo
    lo que ULTRON expone hoy y lo que exponga mañana, sin tocar este archivo.
    """
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    cuerpo = request.get_json(silent=True) if request.method == 'POST' else None
    consulta = request.query_string.decode()
    destino = '/' + ruta + (('?' + consulta) if consulta else '')
    ok, datos = _ultron(destino, request.method, cuerpo, timeout=60)
    return jsonify(datos), (200 if ok else 502)


@app.route('/api/panel')
def api_panel():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    try:
        import panel_api
        return jsonify(panel_api.panel(core if core else None))
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 500


@app.route('/api/panel/accion', methods=['POST'])
def api_panel_accion():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    datos = request.get_json(silent=True) or {}
    accion = (datos.get('accion') or '').strip()
    valor = (datos.get('valor') or '').strip()
    try:
        import panel_api
        resultado = panel_api.ejecutar(core, accion, valor, log=print)
        return jsonify(resultado), (200 if resultado.get('ok') else 400)
    except Exception as e:
        return jsonify({'ok': False, 'texto': str(e)[:200]}), 500


# ── NUEVOS ENDPOINTS: WEB DEMO, LLAMADAS, EMAIL ───────────────────────────────

@app.route('/api/webdemo/crear', methods=['POST'])
def api_webdemo_crear():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get('nombre') or '').strip()
    industria = (datos.get('industria') or 'general').strip()
    descripcion = (datos.get('descripcion') or '').strip()
    idioma = (datos.get('idioma') or 'es').strip()
    if not nombre:
        return jsonify({'ok': False, 'error': 'nombre requerido'}), 400
    try:
        import jarvis_webdemo
        resultado = jarvis_webdemo.crear_demo(
            nombre, industria, descripcion, idioma, log=print)
        return jsonify(resultado), (200 if resultado.get('ok') else 500)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/api/webdemo/lista', methods=['GET'])
def api_webdemo_lista():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    try:
        import jarvis_webdemo
        return jsonify({'demos': jarvis_webdemo.listar_demos(log=print)})
    except Exception as e:
        return jsonify({'demos': [], 'error': str(e)[:200]})


@app.route('/api/llamar', methods=['POST'])
def api_llamar():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    datos = request.get_json(silent=True) or {}
    mensaje = (datos.get('mensaje') or 'JARVIS requiere su atención, señor.').strip()
    canal = (datos.get('canal') or 'auto').strip()
    try:
        import jarvis_llamadas
        resultado = jarvis_llamadas.notificar(mensaje, canal=canal, log=print)
        return jsonify(resultado), (200 if resultado.get('ok') else 500)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/api/llamar/estado', methods=['GET'])
def api_llamar_estado():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    try:
        import jarvis_llamadas
        return jsonify(jarvis_llamadas.estado())
    except Exception as e:
        return jsonify({'disponible': False, 'error': str(e)[:200]})


@app.route('/api/correo/inbox', methods=['GET'])
def api_correo_inbox():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    limite = min(int(request.args.get('limite', 10)), 25)
    try:
        import correo_gmail
        mensajes = correo_gmail.bandeja(limite=limite, log=print)
        return jsonify({'ok': True, 'mensajes': mensajes})
    except Exception as e:
        return jsonify({'ok': False, 'mensajes': [], 'error': str(e)[:200]})


@app.route('/api/correo/leer', methods=['GET'])
def api_correo_leer():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    msg_id = request.args.get('id', '')
    if not msg_id:
        return jsonify({'ok': False, 'error': 'id requerido'}), 400
    try:
        import correo_gmail
        contenido = correo_gmail.leer(msg_id, log=print)
        return jsonify({'ok': True, 'mensaje': contenido})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]})


@app.route('/api/correo/responder', methods=['POST'])
def api_correo_responder():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    datos = request.get_json(silent=True) or {}
    destino = (datos.get('destino') or '').strip()
    asunto = (datos.get('asunto') or '').strip()
    cuerpo = (datos.get('cuerpo') or '').strip()
    if not all([destino, cuerpo]):
        return jsonify({'ok': False, 'error': 'destino y cuerpo requeridos'}), 400
    try:
        import correo_gmail
        resultado = correo_gmail.enviar(destino, asunto, cuerpo, log=print)
        return jsonify({'ok': resultado.get('ok', False),
                        'mensaje': resultado.get('mensaje', '')})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/api/correo/resumir', methods=['GET'])
def api_correo_resumir():
    if not _auth_ok(_req_token()):
        return jsonify({'error': 'token invalido'}), 403
    if not core:
        return jsonify({'ok': False, 'error': 'core no disponible'}), 503
    try:
        resumen = core.process_text_stream("resume los correos nuevos sin leer", speak_server=False)
        return jsonify({'ok': True, 'resumen': resumen})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


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
    # La IP se pregunta ahora, no al importar: si el router la cambio esta
    # semana, el QR del arranque tiene que llevar la de hoy.
    try:
        import red_movil
        _preparado = red_movil.preparar(log=print)
        _ip = _preparado["ip"]
    except Exception as _e:
        print(f"[RED] No pude revisar la red ({_e}); sigo con la IP de siempre.")
        _preparado, _ip = {}, jarvis_config.LOCAL_IP
    print("=" * 56)
    print("JARVIS Web Server v3 (mobile + tiempo real)")
    print(f"  Local:   http://127.0.0.1:{_port}")
    print(f"  Red:     http://{_ip}:{_port}")
    print(f"  Móvil:   http://{_ip}:{_port}/mobile")
    print(f"  QR:      http://{_ip}:{_port}/pair   (ábrelo en el PC)")
    print(f"  Token:   {AUTH_TOKEN}")
    for _otra in (_preparado.get("ips") or [])[1:]:
        print(f"  (o por  http://{_otra['ip']}:{_port}/mobile  vía {_otra['interfaz']})")
    if _preparado.get("firewall_mensaje"):
        print(f"  {_preparado['firewall_mensaje']}")
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