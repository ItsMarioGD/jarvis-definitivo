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
