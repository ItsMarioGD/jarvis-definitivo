#!/usr/bin/env python3
"""
interprete.py - elegir el Python que SI tiene instaladas las dependencias
========================================================================
En un equipo acaban conviviendo varios Python: el de la Store, el de
python.org, el de una herramienta que se instalo sola... Todos se llaman
`python`, pero las dependencias del proyecto estan instaladas en UNO. Si el
PATH cambia de orden (basta con instalar otro Python), los lanzadores pasan a
usar uno vacio y todo revienta con un `ModuleNotFoundError` que no dice nada
del problema real.

Este modulo busca un interprete que pueda importar de verdad lo minimo
(flask y requests), y recuerda cual fue para no repetir el sondeo en cada
arranque. Si no hay ninguno, lo dice claro y con el comando exacto para
arreglarlo, en vez de dejar un traceback a medias.

Uso:
    from interprete import python_del_proyecto, explicar_si_falta
    exe = python_del_proyecto()          # ruta al python bueno, o None
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
MEMORIA = os.path.join(RAIZ, ".python_del_proyecto")

# Lo minimo para que arranquen las dos webs. No se pide mas: los extras ya
# avisan por su cuenta cuando faltan.
MINIMO = ("flask", "requests")

_cache: str | None = None
_ya_buscado = False


def _sirve(exe: str) -> bool:
    """True si ese interprete puede importar lo minimo."""
    if not exe or not os.path.exists(exe):
        return False
    prueba = "import " + ", ".join(MINIMO)
    try:
        r = subprocess.run([exe, "-c", prueba], capture_output=True, timeout=25)
        return r.returncode == 0
    except Exception:
        return False


def _del_lanzador_windows() -> list:
    """Los Python que conoce el lanzador `py` de Windows (`py -0p`)."""
    if os.name != "nt":
        return []
    try:
        r = subprocess.run(["py", "-0p"], capture_output=True, text=True, timeout=20)
    except Exception:
        return []
    rutas = []
    for linea in (r.stdout or "").splitlines():
        trozo = linea.strip()
        # Formato: " -V:3.14 *        C:\ruta\python.exe"
        pos = trozo.lower().find("c:\\")
        if pos >= 0:
            ruta = trozo[pos:].strip().strip('"')
            if ruta.lower().endswith("python.exe"):
                rutas.append(ruta)
    return rutas


def _candidatos() -> list:
    """Todos los Python plausibles, del mas probable al menos."""
    vistos, lista = set(), []

    def anadir(ruta):
        if not ruta:
            return
        clave = os.path.normcase(os.path.abspath(ruta))
        if clave not in vistos:
            vistos.add(clave)
            lista.append(ruta)

    # 1. el que recordamos de la ultima vez que funciono
    try:
        with open(MEMORIA, encoding="utf-8") as f:
            anadir(f.read().strip())
    except Exception:
        pass

    # 2. el que esta ejecutando esto ahora mismo
    anadir(sys.executable)

    # 3. instalaciones tipicas del usuario (donde suele estar todo instalado)
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        for patron in (
            os.path.join(local, "Python", "pythoncore-*", "python.exe"),
            os.path.join(local, "Python", "bin", "python.exe"),
            os.path.join(local, "Programs", "Python", "Python3*", "python.exe"),
        ):
            for ruta in sorted(glob.glob(patron), reverse=True):
                anadir(ruta)

    # 4. lo que conozca el lanzador `py` de Windows
    for ruta in _del_lanzador_windows():
        anadir(ruta)

    # 5. instalaciones para todo el equipo
    for patron in (r"C:\Python3*\python.exe", r"C:\Program Files\Python3*\python.exe"):
        for ruta in sorted(glob.glob(patron), reverse=True):
            anadir(ruta)

    # 6. lo que diga el PATH, por si acaso
    for carpeta in (os.environ.get("PATH") or "").split(os.pathsep):
        if carpeta.strip():
            anadir(os.path.join(carpeta.strip(), "python.exe" if os.name == "nt" else "python3"))

    return lista


def python_del_proyecto(refrescar: bool = False) -> str | None:
    """Ruta al Python que tiene las dependencias, o None si no hay ninguno.

    El resultado se recuerda en `.python_del_proyecto` para que el siguiente
    arranque no vuelva a sondear todos los interpretes del equipo.
    """
    global _cache, _ya_buscado
    if _cache and not refrescar:
        return _cache
    if _ya_buscado and not refrescar:
        return _cache
    _ya_buscado = True

    for exe in _candidatos():
        if _sirve(exe):
            _cache = exe
            try:
                with open(MEMORIA, "w", encoding="utf-8") as f:
                    f.write(exe)
            except Exception:
                pass
            return exe
    _cache = None
    return None


def explicar_si_falta() -> str:
    """Texto en castellano con el porque y el comando exacto para arreglarlo."""
    actual = sys.executable or "python"
    return (
        "No encuentro ningun Python con las dependencias puestas.\n"
        f"  El que esta usando ahora es: {actual}\n"
        "  Instalelas ahi con:\n"
        f'    "{actual}" -m pip install -r "{os.path.join(RAIZ, "requirements.txt")}"\n'
        "  O, si las tenia en otro Python, arranque con ese en vez de este."
    )


def aviso_si_cambia(exe: str) -> str:
    """Aviso corto cuando el Python bueno no es el que se esta usando."""
    if not exe or os.path.normcase(exe) == os.path.normcase(sys.executable or ""):
        return ""
    return (f"  [i]   Uso {exe}\n"
            f"        (el `python` de este terminal no tiene las dependencias)")


if __name__ == "__main__":
    elegido = python_del_proyecto(refrescar=True)
    if elegido:
        print(elegido)
    else:
        print(explicar_si_falta())
        sys.exit(1)
