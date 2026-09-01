"""
jarvis_config.py — Configuración central de red y rutas.
Lee de .env o variables de entorno. Todos los módulos deben usar esto
en vez de hardcodear URLs/puertos.
"""
import os

# ── Red ──────────────────────────────────────────────────────────────────────
PORT = int(os.getenv("JARVIS_PORT", "5000"))
HOST = os.getenv("JARVIS_HOST", "0.0.0.0")  # 0.0.0.0 = escucha en todas las interfaces

# ── Ollama ───────────────────────────────────────────────────────────────────
OLLAMA_BASE = os.getenv("QWEN_BASE_URL", "http://localhost:11434")
OLLAMA_URL = f"{OLLAMA_BASE.rstrip('/')}/api/generate"
OLLAMA_MODEL = os.getenv("QWEN_MODEL", "qwen3:4b-instruct")
OLLAMA_KEY = os.getenv("QWEN_API_KEY", "ollama")

# ── Rutas base ───────────────────────────────────────────────────────────────
_HOME = os.path.expanduser("~")

# Detectar carpeta de descargas (multi-idioma)
def _find_downloads():
    """Busca la carpeta de Descargas/Downloads en cualquier idioma."""
    for name in ("Descargas", "Downloads", "downloads"):
        p = os.path.join(_HOME, name)
        if os.path.isdir(p):
            return p
    # Fallback: crear Descargas
    p = os.path.join(_HOME, "Descargas")
    os.makedirs(p, exist_ok=True)
    return p

DOWNLOADS = _find_downloads()
JARVIS_DATA = os.path.join(DOWNLOADS, "JARVIS")
VIDEOS_DIR = os.path.join(JARVIS_DATA, "Videos")
GEN_DIR = os.path.join(JARVIS_DATA, "Generaciones")
_PREFS_DIR = os.path.join(JARVIS_DATA, "Prefs")

# Asegurar directorios
for _d in (JARVIS_DATA, VIDEOS_DIR, GEN_DIR, _PREFS_DIR):
    os.makedirs(_d, exist_ok=True)

# ── Archivos de config ───────────────────────────────────────────────────────
CEREBRO_JSON = os.path.join(_PREFS_DIR, "cerebro.json")
TELEGRAM_JSON = os.path.join(_PREFS_DIR, "telegram.json")
GRAFODB = os.path.join(_PREFS_DIR, "jarvis_grafo.db")

# ── Bases de datos ───────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _escribible(d: str) -> bool:
    try:
        os.makedirs(d, exist_ok=True)
        prueba = os.path.join(d, ".jarvis_write_test")
        with open(prueba, "w") as f:
            f.write("1")
        os.remove(prueba)
        return True
    except Exception:
        return False


def ruta_db(nombre: str = "jarvis_memory.db") -> str:
    """Ruta ABSOLUTA de una base de datos de JARVIS.

    Nunca devolver una ruta relativa: al arrancar desde un acceso directo de
    Windows el proceso hereda el cwd del .lnk (Escritorio o System32) y SQLite
    fallaba con «unable to open database file» al no poder escribir alli.
    Ademas, con rutas relativas cada proceso (web, bot, ULTRON) abria una base
    distinta segun desde donde se lanzara.

    Orden: JARVIS_DB_DIR > raiz del proyecto > <Descargas>/JARVIS.
    """
    candidatas = rutas_db(nombre)
    return candidatas[0] if candidatas else nombre


def rutas_db(nombre: str = "jarvis_memory.db") -> list:
    """Candidatas en orden de preferencia, para que el nucleo pueda reintentar.

    Un solo destino no basta: un fichero -wal huerfano de un arranque como
    administrador, o una carpeta sincronizada por OneDrive, hacen fallar el
    connect aunque el directorio sea escribible.
    """
    import tempfile
    salida = []
    for d in (os.getenv("JARVIS_DB_DIR", "").strip(), PROJECT_ROOT, JARVIS_DATA,
              tempfile.gettempdir()):
        if not d or not _escribible(d):
            continue
        destino = os.path.join(d, nombre)
        if destino in salida:
            continue
        if not os.path.exists(destino):
            _rescatar_db(nombre, destino)
        salida.append(destino)
    return salida


def _rescatar_db(nombre: str, destino: str):
    """Recupera una base creada por una version con rutas relativas.

    Copia (nunca mueve) para no perder el historial ya guardado en
    web_interface/ o en el cwd desde el que se arrancara antes.
    """
    import shutil
    for viejo in (os.path.join(PROJECT_ROOT, "web_interface", nombre),
                  os.path.join(PROJECT_ROOT, "ultron_interface", nombre),
                  os.path.abspath(nombre)):
        try:
            if os.path.abspath(viejo) != os.path.abspath(destino) \
                    and os.path.isfile(viejo) and os.path.getsize(viejo) > 0:
                shutil.copy2(viejo, destino)
                print(f"[jarvis_config] Memoria recuperada de {viejo} -> {destino}")
                return
        except Exception:
            continue


JARVIS_DB = ruta_db("jarvis_memory.db")

# ── Credenciales de Google (OAuth) ───────────────────────────────────────────
# Google descarga el fichero con un nombre largo del tipo
# "client_secret_1234-abcd.apps.googleusercontent.com.json". Buscamos por
# patron en los sitios razonables para no obligar a renombrarlo ni a
# configurar variables de entorno.
GOOGLE_DIR = os.path.join(PROJECT_ROOT, "Google")

# Puerto FIJO para el servidor local del flujo OAuth. Con las credenciales de
# tipo «Aplicacion web» Google exige que el redirect este registrado, y con un
# puerto aleatorio seria imposible registrarlo.
OAUTH_PORT = int(os.getenv("GOOGLE_OAUTH_PORT", "8088"))
REDIRECT_OAUTH = f"http://localhost:{OAUTH_PORT}/"

_PATRONES_CRED = ("client_secret*.json", "credentials*.json", "*oauth*.json")


def buscar_credenciales_google() -> str:
    """Ruta del JSON de credenciales OAuth, o "" si no hay ninguno.

    Orden: GOOGLE_CREDENTIALS_JSON > Google/ > raiz del proyecto > Prefs.
    """
    import glob
    explicito = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if explicito:
        ruta = explicito if os.path.isabs(explicito) else os.path.join(PROJECT_ROOT, explicito)
        if os.path.isfile(ruta):
            return ruta
    for carpeta in (GOOGLE_DIR, os.path.join(PROJECT_ROOT, "google"),
                    PROJECT_ROOT, _PREFS_DIR, JARVIS_DATA, DOWNLOADS):
        for c in _en_carpeta(carpeta):
            return c
    # Ultimo recurso: barrer el proyecto hasta 3 niveles. Asi da igual en que
    # subcarpeta se haya dejado el fichero.
    for c in _barrer_proyecto():
        return c
    return ""


def _en_carpeta(carpeta: str):
    """Credenciales dentro de una carpeta concreta (sin recursion)."""
    import glob
    if not carpeta or not os.path.isdir(carpeta):
        return
    for patron in _PATRONES_CRED:
        for c in sorted(glob.glob(os.path.join(carpeta, patron))):
            # token.json tambien casa con *oauth*/credentials*: no confundir.
            if os.path.basename(c).lower().startswith("token"):
                continue
            yield c


_IGNORAR = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}


def _barrer_proyecto(max_prof: int = 3):
    """Busca credenciales en cualquier subcarpeta del proyecto."""
    base = PROJECT_ROOT.rstrip(os.sep)
    for raiz, dirs, _ in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _IGNORAR and not d.startswith(".")]
        if raiz[len(base):].count(os.sep) >= max_prof:
            dirs[:] = []
        for c in _en_carpeta(raiz):
            yield c


def listar_credenciales_google() -> list:
    """Todos los candidatos encontrados, para poder decir donde se ha mirado."""
    vistos, salida = set(), []
    for c in _barrer_proyecto():
        real = os.path.abspath(c)
        if real not in vistos:
            vistos.add(real)
            salida.append(real)
    for carpeta in (_PREFS_DIR, JARVIS_DATA, DOWNLOADS):
        for c in _en_carpeta(carpeta):
            real = os.path.abspath(c)
            if real not in vistos:
                vistos.add(real)
                salida.append(real)
    return salida


def ruta_token_google() -> str:
    """Donde guardar el token de autorizacion (junto a las credenciales)."""
    explicito = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
    if explicito:
        return explicito if os.path.isabs(explicito) else os.path.join(PROJECT_ROOT, explicito)
    cred = buscar_credenciales_google()
    destino = os.path.dirname(cred) if cred else GOOGLE_DIR
    try:
        os.makedirs(destino, exist_ok=True)
    except OSError:
        destino = _PREFS_DIR
    return os.path.join(destino, "token.json")


def revisar_credenciales_google() -> dict:
    """Comprueba que el JSON sirve para lo que queremos.

    Devuelve {"ok": bool, "ruta": str, "tipo": str, "error": str}. Los tres
    fallos tipicos (fichero de aplicacion WEB, cuenta de servicio, o JSON
    invalido) dan errores cripticos mucho mas tarde si no se detectan aqui.
    """
    ruta = buscar_credenciales_google()
    if not ruta:
        return {"ok": False, "ruta": "", "tipo": "", "error":
                f"No encuentro ningun JSON de credenciales. Deja el que descargaste "
                f"de Google Cloud en {GOOGLE_DIR}."}
    try:
        import json as _json
        datos = _json.load(open(ruta, encoding="utf-8-sig"))
    except Exception as e:
        return {"ok": False, "ruta": ruta, "tipo": "", "error":
                f"{os.path.basename(ruta)} no es un JSON valido: {e}"}
    if datos.get("type") == "service_account":
        return {"ok": False, "ruta": ruta, "tipo": "service_account", "error":
                "Es una CUENTA DE SERVICIO. No puede entrar en tu calendario "
                "personal. Crea unas credenciales de tipo «ID de cliente de "
                "OAuth» → «Aplicacion de escritorio»."}
    if "web" in datos and "installed" not in datos:
        # Las credenciales de tipo «Aplicacion web» TAMBIEN valen: la libreria
        # de Google las acepta. La unica diferencia es que exigen tener el
        # redirect registrado en la consola, asi que usamos un puerto FIJO
        # (OAUTH_PORT) para poder decir exactamente cual hay que registrar.
        cid = datos["web"].get("client_id", "")
        return {"ok": True, "ruta": ruta, "tipo": "web",
                "cliente": cid[:24] + "…" if cid else "",
                "proyecto": datos["web"].get("project_id", ""),
                "redirect": REDIRECT_OAUTH,
                "aviso": ("Son de tipo «Aplicacion web». Funcionan, pero antes "
                          f"hay que anadir {REDIRECT_OAUTH} a los «URI de "
                          "redireccionamiento autorizados» de ese ID de cliente "
                          "en Google Cloud Console."),
                "error": ""}
    if "installed" not in datos:
        return {"ok": False, "ruta": ruta, "tipo": "?", "error":
                "No reconozco el formato: falta la clave «installed». "
                "Descarga el JSON del ID de cliente OAuth de escritorio."}
    cid = datos["installed"].get("client_id", "")
    return {"ok": True, "ruta": ruta, "tipo": "installed",
            "cliente": cid[:24] + "…" if cid else "",
            "proyecto": datos["installed"].get("project_id", ""),
            "redirect": "", "aviso": "", "error": ""}


# ── Tailscale ────────────────────────────────────────────────────────────────
def find_tailscale():
    """Busca tailscale.exe en ubicaciones comunes."""
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tailscale", "tailscale.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Tailscale", "tailscale.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tailscale", "tailscale.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

TAILSCALE_EXE = find_tailscale()

# ── IP local ─────────────────────────────────────────────────────────────────
def get_local_ip():
    """Obtiene la IP LAN real (no loopback)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

# ── URLs de servicios ────────────────────────────────────────────────────────
def url_flask(path=""):
    """URL completa del servidor Flask."""
    return f"http://{LOCAL_IP}:{PORT}{path}"

def url_ollama():
    """URL de la API de Ollama (generate)."""
    return OLLAMA_URL
