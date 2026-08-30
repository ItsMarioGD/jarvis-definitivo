#!/usr/bin/env python3
"""
ultron_autostart.py — Lanza ULTRON automáticamente cuando JARVIS se ejecuta.
================================================================================
Comprueba si el servidor web de Ultron (:8766) está vivo; si no, arranca
`ultron_interface/app.py` en segundo plano con pythonw y espera a que responda.
Idempotente: si Ultron ya corre, no hace nada.
"""
import os
import sys
import socket
import subprocess
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
ULTRON_PORT = int(os.getenv("ULTRON_PORT", "8766"))


def _port_up(port: int = ULTRON_PORT, timeout: float = 1.0) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        try:
            s.close()
        except Exception:
            pass


def ensure_ultron_running(max_wait_s: float = 12.0) -> bool:
    """Devuelve True si Ultron quedó sirviendo (ya corriera o se arrancara)."""
    if _port_up():
        return True

    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            [exe, "app.py"],
            cwd=os.path.join(ROOT, "ultron_interface"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            **kwargs,
        )
    except Exception as e:
        print(f"[AUTOSTART] No pude lanzar ULTRON: {e}")
        return False

    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        time.sleep(0.5)
        if _port_up():
            print("[AUTOSTART] ULTRON en línea.")
            return True
    print("[AUTOSTART] ULTRON no respondió a tiempo (puede seguir cargando).")
    return False


if __name__ == "__main__":
    ok = ensure_ultron_running()
    sys.exit(0 if ok else 1)
