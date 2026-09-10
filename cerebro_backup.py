#!/usr/bin/env python3
"""
cerebro_backup.py - Exportar e importar todo lo que JARVIS ha aprendido
=======================================================================
La personalidad que el asistente construye contigo (preferencias, memoria de
conversaciones, grafo de conocimiento, macros, registro de acciones, tareas
programadas) vive repartida en varios .db sueltos y en una carpeta de Prefs.
Un formateo, un disco que muere o un cambio de PC se lo llevaba todo, y no
habia ningun comando para copiarlo.

    python cerebro_backup.py exportar            -> crea un .zip con todo
    python cerebro_backup.py importar <ruta.zip> -> lo restaura en este equipo
    python cerebro_backup.py listar              -> que hay en la copia

Por defecto NO se incluyen credenciales (.env, tokens de Google/Telegram, PIN
de la web): una copia del cerebro suele acabar en un pendrive o en la nube, y
mezclar memoria con llaves es como guardar las llaves de casa dentro del album
de fotos. Si de verdad las quieres, hay que pedirlo:

    python cerebro_backup.py exportar --con-credenciales
"""
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime

RAIZ = os.path.dirname(os.path.abspath(__file__))
PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
DESTINO_POR_DEFECTO = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Copias")

# Qué entra en la copia. (ruta relativa a RAIZ, descripción)
PIEZAS = [
    ("jarvis_memory.db", "memoria de conversaciones de JARVIS"),
    ("ultron_memory.db", "memoria de conversaciones de ULTRON"),
    ("jarvis_audit.db", "registro de acciones, eventos y deshacer"),
    ("calendar_events.db", "agenda local"),
]
# Carpetas completas (ruta absoluta, nombre dentro del zip, descripción)
CARPETAS = [
    (PREFS, "Prefs", "preferencias, cerebro.json, macros y listas"),
]
# Credenciales: solo con --con-credenciales
CREDENCIALES = [
    (".env", "claves de API"),
    ("web_interface/.jarvis_auth", "PIN de la interfaz web"),
    ("ultron_interface/.ultron_auth", "PIN de la interfaz de ULTRON"),
]
SENSIBLES_EN_PREFS = ("token", "credential", "auth", "secret")


def _grafo_db():
    """El grafo vive donde diga jarvis_grafo (suele estar bajo Prefs)."""
    try:
        import jarvis_grafo
        return jarvis_grafo.DB
    except Exception:
        return ""


def exportar(destino: str = "", con_credenciales: bool = False, log=print) -> str:
    """Crea el zip con el cerebro. Devuelve la ruta del archivo."""
    os.makedirs(destino or DESTINO_POR_DEFECTO, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = os.path.join(destino or DESTINO_POR_DEFECTO, f"cerebro_jarvis_{marca}.zip")

    manifiesto = {
        "creado": datetime.now().isoformat(timespec="seconds"),
        "equipo": os.getenv("COMPUTERNAME", "desconocido"),
        "con_credenciales": bool(con_credenciales),
        "piezas": [],
    }

    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, desc in PIEZAS:
            origen = os.path.join(RAIZ, rel)
            if os.path.exists(origen):
                z.write(origen, f"datos/{rel}")
                manifiesto["piezas"].append({"pieza": rel, "que_es": desc})

        grafo = _grafo_db()
        if grafo and os.path.exists(grafo):
            z.write(grafo, f"datos/{os.path.basename(grafo)}")
            manifiesto["piezas"].append({"pieza": os.path.basename(grafo),
                                         "que_es": "grafo de conocimiento"})

        for carpeta, nombre, desc in CARPETAS:
            if not os.path.isdir(carpeta):
                continue
            incluidos = 0
            for base, _dirs, ficheros in os.walk(carpeta):
                for f in ficheros:
                    completo = os.path.join(base, f)
                    rel_zip = os.path.relpath(completo, carpeta)
                    if not con_credenciales and any(s in f.lower() for s in SENSIBLES_EN_PREFS):
                        continue
                    z.write(completo, f"{nombre}/{rel_zip}")
                    incluidos += 1
            manifiesto["piezas"].append({"pieza": nombre, "que_es": desc,
                                         "archivos": incluidos})

        if con_credenciales:
            for rel, desc in CREDENCIALES:
                origen = os.path.join(RAIZ, rel)
                if os.path.exists(origen):
                    z.write(origen, f"credenciales/{os.path.basename(rel)}")
                    manifiesto["piezas"].append({"pieza": rel, "que_es": desc})

        z.writestr("manifiesto.json", json.dumps(manifiesto, ensure_ascii=False, indent=2))

    tam = os.path.getsize(ruta) / (1024 * 1024)
    log(f"[CEREBRO] Copia creada: {ruta} ({tam:.1f} MB, {len(manifiesto['piezas'])} piezas)")
    if not con_credenciales:
        log("[CEREBRO] Sin credenciales (usa --con-credenciales si las necesitas).")
    return ruta


def listar(ruta_zip: str, log=print) -> dict:
    """Qué contiene una copia, sin tocar nada del equipo."""
    with zipfile.ZipFile(ruta_zip) as z:
        try:
            manifiesto = json.loads(z.read("manifiesto.json").decode("utf-8"))
        except Exception:
            manifiesto = {"piezas": [{"pieza": n} for n in z.namelist()[:40]]}
    log(f"[CEREBRO] Copia del {manifiesto.get('creado', '?')} "
        f"(equipo {manifiesto.get('equipo', '?')})")
    for pieza in manifiesto.get("piezas", []):
        log(f"  - {pieza.get('pieza')}: {pieza.get('que_es', '')}")
    if manifiesto.get("con_credenciales"):
        log("  ! Incluye credenciales: trátala como una llave, no como una foto.")
    return manifiesto


def importar(ruta_zip: str, log=print, forzar: bool = False) -> str:
    """Restaura una copia. Lo que ya existe se aparta antes, nunca se pisa."""
    if not os.path.exists(ruta_zip):
        return f"No encuentro la copia {ruta_zip}."

    respaldo = os.path.join(RAIZ, f"antes_de_importar_{datetime.now():%Y%m%d_%H%M}")
    os.makedirs(respaldo, exist_ok=True)
    restaurados, apartados = [], []

    with zipfile.ZipFile(ruta_zip) as z:
        nombres = z.namelist()
        for nombre in nombres:
            if nombre.endswith("/") or nombre == "manifiesto.json":
                continue
            if nombre.startswith("datos/"):
                destino = os.path.join(RAIZ, os.path.basename(nombre))
            elif nombre.startswith("Prefs/"):
                destino = os.path.join(PREFS, nombre[len("Prefs/"):])
            elif nombre.startswith("credenciales/"):
                if not forzar:
                    continue     # las credenciales solo con --forzar
                destino = os.path.join(RAIZ, os.path.basename(nombre))
            else:
                continue

            os.makedirs(os.path.dirname(destino), exist_ok=True)
            if os.path.exists(destino):
                # Nunca se pisa lo que hay: se aparta con su ruta original.
                copia = os.path.join(respaldo, os.path.basename(destino))
                try:
                    shutil.copy2(destino, copia)
                    apartados.append(os.path.basename(destino))
                except Exception as e:
                    log(f"[CEREBRO] No pude apartar {destino}: {e}")
            with z.open(nombre) as origen, open(destino, "wb") as salida:
                shutil.copyfileobj(origen, salida)
            restaurados.append(os.path.basename(destino))

    if not apartados:
        try:
            os.rmdir(respaldo)
        except Exception:
            pass

    resumen = (f"Restauradas {len(restaurados)} piezas del cerebro. "
               + (f"Lo anterior está en {os.path.basename(respaldo)}. " if apartados else "")
               + "Reinicia JARVIS para que cargue la memoria nueva.")
    log(f"[CEREBRO] {resumen}")
    return resumen


def _uso():
    print(__doc__.strip())
    return 1


def main(argv) -> int:
    if not argv:
        return _uso()
    accion = argv[0].lower()
    if accion in ("exportar", "export", "copia"):
        con_cred = "--con-credenciales" in argv
        destino = next((a for a in argv[1:] if not a.startswith("--")), "")
        exportar(destino, con_credenciales=con_cred)
        return 0
    if accion in ("importar", "import", "restaurar"):
        ruta = next((a for a in argv[1:] if not a.startswith("--")), "")
        if not ruta:
            print("Falta la ruta del .zip")
            return 2
        print(importar(ruta, forzar="--forzar" in argv))
        return 0
    if accion in ("listar", "ver", "list"):
        ruta = next((a for a in argv[1:] if not a.startswith("--")), "")
        if not ruta:
            print("Falta la ruta del .zip")
            return 2
        listar(ruta)
        return 0
    return _uso()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
