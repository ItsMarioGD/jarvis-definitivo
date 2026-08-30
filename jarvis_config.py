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
