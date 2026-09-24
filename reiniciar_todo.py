#!/usr/bin/env python3
"""
reiniciar_todo.py — Reinicio blindado de JARVIS + ULTRON
========================================================
Ejecuta ESTE script cada vez que quieras reiniciar los servidores.
Hace el ritual completo: mata procesos, checkpoint WAL, arranca ambos.
Uso: python reiniciar_todo.py
"""
import os
import sys
import time
import subprocess
import sqlite3
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consola_utf8  # noqa: F401  (salida a prueba de cp1252)

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILES = ["jarvis_memory.db", "ultron_memory.db"]
LOGS = os.path.join(ROOT, "jarvis_log")


def registro(nombre: str) -> str:
    """jarvis_log/jarvis.log, jarvis_log/calendar_mcp.log..."""
    return os.path.join(LOGS, nombre.lower().replace(" ", "_") + ".log")

def kill_pythonw():
    """Mata TODOS los pythonw existentes."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/IM", "pythonw.exe"],
                capture_output=True, check=False
            )
        else:
            subprocess.run(["pkill", "-9", "-f", "pythonw"], check=False)
    except Exception:
        pass
    time.sleep(1.5)

def wal_checkpoint_all():
    """Checkpoint WAL TRUNCATE en ambas BDs."""
    for db in DB_FILES:
        path = os.path.join(ROOT, db)
        if not os.path.exists(path):
            continue
        for attempt in range(3):
            try:
                c = sqlite3.connect(path, timeout=30)
                c.execute("PRAGMA journal_mode=WAL;")
                c.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                c.close()
                print(f"  [OK] {db} WAL checkpoint OK")
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [ERR] {db} WAL fallo: {e}")
                time.sleep(0.5)

def _valores_env() -> dict:
    """Lo que hay en el .env (clave=valor), sin pisar nada del entorno."""
    valores = {}
    try:
        with open(os.path.join(ROOT, ".env"), encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, _, valor = linea.partition("=")
                valores[clave.strip()] = valor.strip().strip('"').strip("'")
    except OSError:
        pass
    return valores


def _config(clave: str) -> str:
    return (os.environ.get(clave) or _valores_env().get(clave) or "").strip()


def _hay_adb() -> bool:
    ruta = _config("ADB_PATH")
    if ruta and os.path.exists(ruta):
        return True
    return bool(shutil.which(ruta or "adb"))


def servicios() -> list:
    """Qué arrancar: (nombre, carpeta, script, argumentos...).

    Cada servidor es un proceso de Python con su memoria. Los que no pueden
    hacer nada no se arrancan: Home Assistant sin HA_TOKEN, el del móvil sin
    adb, y el MCP de JARVIS por HTTP (el modo de pruebas para herramientas
    externas) solo con JARVIS_MCP_HTTP=1.
    """
    # Los servidores MCP van ANTES que JARVIS: si el calendario no esta
    # escuchando en el 8002 cuando alguien pregunta por su agenda, JARVIS
    # responde «no pude hablar con Google Calendar» aunque la cuenta este
    # perfectamente autorizada.
    lista = [("Calendar MCP", "mcp_servers", "calendar_server.py")]
    if _config("HA_TOKEN"):
        lista.append(("Home Assistant MCP", "mcp_servers", "ha_server.py"))
    if _hay_adb():
        lista.append(("Android MCP", "mcp_servers", "android_server.py"))
    if _config("JARVIS_MCP_HTTP").lower() in ("1", "si", "sí", "true", "yes"):
        lista.append(("JARVIS MCP", ".", "jarvis_mcp_server.py", "--http", "5001"))
    lista.append(("JARVIS", "web_interface", "app.py"))
    lista.append(("ULTRON", "ultron_interface", "app.py"))
    return lista


PUERTOS = {("mcp_servers", "calendar_server.py"): 8002, ("mcp_servers", "ha_server.py"): 8001,
           ("mcp_servers", "android_server.py"): 8003, (".", "jarvis_mcp_server.py"): 5001,
           ("web_interface", "app.py"): 5000, ("ultron_interface", "app.py"): 8766}


def _escuchando(puerto: int) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=0.3):
            return True
    except OSError:
        return False


def arrancar_servicios(solo_los_caidos: bool = False):
    """Arranca todo, oculto. No mata nada: eso lo hace el reinicio completo.

    solo_los_caidos: se salta lo que ya esta escuchando (lo usa la ventana de
    escritorio cuando JARVIS no contesta, para no duplicar lo que si va).
    """
    for nombre, cwd, script, *extra in servicios():
        puerto = PUERTOS.get((cwd, script))
        if solo_los_caidos and puerto and _escuchando(puerto):
            continue
        start_server(nombre, cwd, script, *extra)


def start_server(name, cwd, script, *extra):
    """Arranca un servidor pythonw en background.

    `extra` son argumentos sueltos para el script (p. ej. "--http", "5001").
    Van aparte y no dentro de `script`: Popen con una lista trata cada
    elemento como UN argumento, asi que "script.py --http 5001" se le pasaria
    a Python como si fuera el nombre de un fichero con espacios.
    """
    # El Python con las dependencias puede no ser el de este terminal.
    try:
        from interprete import python_del_proyecto
        base = python_del_proyecto() or sys.executable
    except Exception:
        base = sys.executable
    exe = os.path.join(os.path.dirname(base), "pythonw.exe")
    if not os.path.exists(exe):
        exe = base
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Como JARVIS_START.bat: los servidores ven lo que hay en el .env (el de
    # Home Assistant, por ejemplo, lee HA_TOKEN del entorno y no del fichero).
    entorno = dict(_valores_env())
    entorno.update(os.environ)
    # Sin consola no se ve nada: lo que diga cada servidor queda en
    # jarvis_log/<nombre>.log (se empieza de cero en cada arranque).
    try:
        os.makedirs(LOGS, exist_ok=True)
        salida = open(registro(name), "w", encoding="utf-8", errors="replace")
    except OSError:
        salida = subprocess.DEVNULL
    try:
        subprocess.Popen(
            [exe, script, *extra],
            cwd=os.path.join(ROOT, cwd), env=entorno,
            stdout=salida,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        print(f"  [START] {name} arrancado en {cwd}")
    except Exception as e:
        print(f"  [ERR] {name} no arranco: {e}")
    finally:
        if salida is not subprocess.DEVNULL:
            salida.close()          # el hijo tiene su copia

def wait_health(url, name, timeout=15):
    """Espera a que /health conteste algo.

    Cualquier respuesta HTTP vale como «esta vivo». El calendario, por
    ejemplo, devuelve 503 mientras no haya una cuenta de Google autorizada, y
    eso no es un fallo del arranque: el proceso esta escuchando y hara su
    trabajo en cuanto se autorice.
    """
    import requests
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                print(f"  [OK] {name} salud OK")
            else:
                print(f"  [OK] {name} escuchando (responde {r.status_code})")
            return True
        except Exception:
            pass
        time.sleep(0.8)
    print(f"  [WARN] {name} no respondio a /health en {timeout}s")
    return False

if __name__ == "__main__":
    print("=" * 50)
    print("  REINICIO BLINDADO JARVIS + ULTRON")
    print("=" * 50)

    print("\n[1/4] Matando pythonw previos...")
    kill_pythonw()

    print("\n[2/4] Checkpoint WAL (TRUNCATE)...")
    wal_checkpoint_all()

    print("\n[3/4] Arrancando servidores (MCP que hagan falta, JARVIS y ULTRON)...")
    arrancar_servicios()
    omitidos = {"ha_server.py": "Home Assistant (sin HA_TOKEN)",
                "android_server.py": "Android (sin adb)",
                "jarvis_mcp_server.py": "MCP de JARVIS por HTTP (JARVIS_MCP_HTTP=1 lo activa)"}
    for _n, _c, script, *_e in servicios():
        omitidos.pop(script, None)
    for motivo in omitidos.values():
        print(f"  [--] No arranco {motivo}: no tendria nada que hacer.")

    print("\n[4/4] Verificando salud...")
    time.sleep(3)
    wait_health("http://127.0.0.1:5000/health", "JARVIS :5000")
    wait_health("http://127.0.0.1:8766/health", "ULTRON :8766")
    # El calendario responde 503 mientras no haya cuenta autorizada, asi que
    # aqui basta con saber que el proceso escucha.
    wait_health("http://127.0.0.1:8002/health", "Calendar MCP :8002", timeout=8)

    import socket as _sock
    try:
        _s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        _s.connect(("8.8.8.8", 80))
        ip = _s.getsockname()[0]
        _s.close()
    except Exception:
        ip = "127.0.0.1"

    if "--sin-ventana" not in sys.argv:
        try:
            import escritorio
            escritorio.abrir_ventana(reemplazar=True)
        except Exception as e:
            print(f"  [WARN] No pude abrir la ventana de JARVIS: {e}")

    print("\n" + "=" * 50)
    print("  LISTO.")
    print("  JARVIS:                 ventana propia (acceso directo «JARVIS»)")
    print("  Emparejar el telefono:  en JARVIS, boton del movil (QR con el PIN)")
    print(f"  Desde el movil:         http://{ip}:5000/mobile")
    print("=" * 50)