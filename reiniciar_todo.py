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

def start_server(name, cwd, script):
    """Arranca un servidor pythonw en background."""
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            [exe, script],
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
    """Espera a que /health responda 200."""
    import requests
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                print(f"  [OK] {name} salud OK")
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

    print("\n[1/5] Matando pythonw previos...")
    kill_pythonw()

    print("\n[2/5] Checkpoint WAL (TRUNCATE)...")
    wal_checkpoint_all()

    print("\n[3/5] Arrancando JARVIS (web_interface)...")
    start_server("JARVIS", "web_interface", "app.py")

    print("\n[4/5] Arrancando ULTRON (ultron_interface)...")
    start_server("ULTRON", "ultron_interface", "app.py")

    print("\n[5/5] Verificando salud...")
    time.sleep(3)
    wait_health("http://127.0.0.1:5000/health", "JARVIS :5000")
    wait_health("http://127.0.0.1:8766/health", "ULTRON :8766")

    print("\n" + "=" * 50)
    print("  LISTO. Interfaz móvil: http://<IP>:5000/mobile")
    print("  PIN en: http://<IP>:5000/pair")
    print("=" * 50)