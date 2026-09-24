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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consola_utf8  # noqa: F401  (salida a prueba de cp1252)

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILES = ["jarvis_memory.db", "ultron_memory.db"]

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
    try:
        subprocess.Popen(
            [exe, script, *extra],
            cwd=os.path.join(ROOT, cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        print(f"  [START] {name} arrancado en {cwd}")
    except Exception as e:
        print(f"  [ERR] {name} no arranco: {e}")

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

    print("\n[1/6] Matando pythonw previos...")
    kill_pythonw()

    print("\n[2/6] Checkpoint WAL (TRUNCATE)...")
    wal_checkpoint_all()

    # Los servidores MCP van ANTES que JARVIS: si el calendario no esta
    # escuchando en el 8002 cuando alguien pregunta por su agenda, JARVIS
    # responde «no pude hablar con Google Calendar» aunque la cuenta este
    # perfectamente autorizada. Antes este script no los arrancaba y solo
    # subian con start_jarvis.bat, asi que el calendario fallaba segun por
    # donde se hubiera arrancado el sistema.
    print("\n[3/6] Arrancando servidores MCP (calendario, casa, movil)...")
    for nombre, script in (("Calendar MCP", "calendar_server.py"),
                           ("Home Assistant MCP", "ha_server.py"),
                           ("Android MCP", "android_server.py")):
        start_server(nombre, "mcp_servers", script)
    # El MCP de JARVIS (puerto 5001) expone sus habilidades a herramientas
    # externas; tampoco lo arrancaba nadie.
    start_server("JARVIS MCP", ".", "jarvis_mcp_server.py", "--http", "5001")

    print("\n[4/6] Arrancando JARVIS (web_interface)...")
    start_server("JARVIS", "web_interface", "app.py")

    print("\n[5/6] Arrancando ULTRON (ultron_interface)...")
    start_server("ULTRON", "ultron_interface", "app.py")

    print("\n[6/6] Verificando salud...")
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

    print("\n" + "=" * 50)
    print("  LISTO.")
    print("  JARVIS:                 http://localhost:5000")
    print("  Emparejar el telefono:  en JARVIS, boton del movil (QR con el PIN)")
    print(f"  Desde el movil:         http://{ip}:5000/mobile")
    print("=" * 50)