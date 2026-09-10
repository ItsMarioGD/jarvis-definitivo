#!/usr/bin/env python3
"""
herramientas_fs.py - Manos sobre el sistema de archivos
======================================================
`analista.py` escribe programas enteros y `piloto.py` mueve el raton, pero
entre esos dos extremos faltaba lo mas util para un agente: leer, escribir y
**editar por diff** un archivo concreto sin reescribirlo entero.

Esto lo da, con tres frenos:

* **Raiz permitida:** solo bajo la carpeta del usuario o del proyecto. Nada de
  `C:\\Windows`, `Archivos de programa`, ni ficheros de credenciales (.env,
  token*.json, id_rsa...). El agente no puede tocar lo que lo sostiene.
* **Reversible:** cada escritura o edicion guarda un respaldo y lo anota en el
  diario de `deshacer.py` con tipo "archivo". «Deshaz eso» lo revierte.
* **Edicion exacta:** `editar_archivo` exige que el fragmento a sustituir
  aparezca UNA sola vez. Si aparece varias, no adivina: devuelve error.

Las funciones devuelven texto plano listo para que lo lea el modelo o el señor.
"""
import os
import re
import shutil
import time
import fnmatch

# Carpeta del proyecto (donde vive este archivo).
_PROYECTO = os.path.dirname(os.path.abspath(__file__))
_HOME = os.path.expanduser("~")
_RESPALDOS = os.path.join(_HOME, "Descargas", "JARVIS", "Respaldos", "fs")

# Nombres que no se tocan ni para leer: si el modelo los pide, hay algo raro.
_VETADOS = re.compile(
    r"(^|[\\/])(\.env|\.env\.[^\\/]+|.*token.*\.json|.*credential.*\.json|"
    r"id_rsa|id_ed25519|.*\.pem|.*\.key|cerebro\.json|telegram\.json)$",
    re.IGNORECASE)

_LIMITE_BYTES = 2_000_000   # 2 MB: por encima no es un archivo de texto normal
_MAX_LINEAS = 400           # tope de lineas devueltas por lectura


def _dentro(raiz: str, ruta: str) -> bool:
    try:
        raiz = os.path.realpath(raiz)
        ruta = os.path.realpath(ruta)
        return ruta == raiz or ruta.startswith(raiz + os.sep)
    except Exception:
        return False


def _resolver(ruta: str) -> str:
    """Expande ~ y variables y devuelve ruta absoluta normalizada."""
    ruta = os.path.expandvars(os.path.expanduser((ruta or "").strip().strip('"')))
    if not os.path.isabs(ruta):
        ruta = os.path.join(_PROYECTO, ruta)
    return os.path.normpath(ruta)


def _permitida(ruta: str) -> tuple[bool, str]:
    """(ok, motivo). Reglas de raiz y de nombres vetados."""
    if not ruta:
        return False, "ruta vacia"
    abs_ruta = _resolver(ruta)
    if _VETADOS.search(abs_ruta):
        return False, "ese archivo esta protegido (credenciales o config critica)"
    if not (_dentro(_HOME, abs_ruta) or _dentro(_PROYECTO, abs_ruta)):
        return False, "fuera de las carpetas permitidas (solo tu carpeta de usuario o el proyecto)"
    return True, abs_ruta


def _es_texto(ruta: str) -> bool:
    try:
        with open(ruta, "rb") as f:
            trozo = f.read(4096)
        return b"\x00" not in trozo
    except Exception:
        return False


def _anota_deshacer(abs_ruta: str, respaldo: str | None, existia: bool, log=print):
    try:
        import deshacer
        deshacer.anotar("archivo",
                        f"editar {os.path.basename(abs_ruta)}",
                        {"ruta": abs_ruta, "respaldo": respaldo, "existia": existia},
                        agente="JARVIS", log=log)
    except Exception as e:
        log(f"[FS] no pude anotar deshacer para {abs_ruta}: {e}")


def _respaldar(abs_ruta: str, log=print) -> str | None:
    if not os.path.exists(abs_ruta):
        return None
    try:
        os.makedirs(_RESPALDOS, exist_ok=True)
        sello = time.strftime("%Y%m%d-%H%M%S")
        destino = os.path.join(_RESPALDOS, f"{sello}-{os.path.basename(abs_ruta)}")
        shutil.copy2(abs_ruta, destino)
        return destino
    except Exception as e:
        log(f"[FS] no pude respaldar {abs_ruta}: {e}")
        return None


# ── operaciones ─────────────────────────────────────────────────────────────
def leer_archivo(ruta: str, desde: int = 1, hasta: int = 0, log=print) -> str:
    ok, val = _permitida(ruta)
    if not ok:
        return f"No puedo leer eso: {val}."
    abs_ruta = val
    if not os.path.isfile(abs_ruta):
        return f"No existe el archivo {abs_ruta}."
    if os.path.getsize(abs_ruta) > _LIMITE_BYTES:
        return f"El archivo es demasiado grande ({os.path.getsize(abs_ruta)//1024} KB)."
    if not _es_texto(abs_ruta):
        return "No es un archivo de texto; no puedo mostrarlo."
    try:
        with open(abs_ruta, encoding="utf-8", errors="replace") as f:
            lineas = f.readlines()
    except Exception as e:
        return f"No pude leerlo: {e}"
    desde = max(1, int(desde or 1))
    hasta = int(hasta or 0) or len(lineas)
    hasta = min(hasta, desde + _MAX_LINEAS - 1, len(lineas))
    trozo = lineas[desde - 1:hasta]
    cuerpo = "".join(f"{desde + i:>5}  {l}" for i, l in enumerate(trozo))
    cola = "" if hasta >= len(lineas) else f"\n… ({len(lineas) - hasta} lineas mas)"
    return f"{abs_ruta} [{desde}-{hasta} de {len(lineas)}]\n{cuerpo}{cola}"


def escribir_archivo(ruta: str, contenido: str, log=print) -> str:
    ok, val = _permitida(ruta)
    if not ok:
        return f"No puedo escribir ahi: {val}."
    abs_ruta = val
    existia = os.path.exists(abs_ruta)
    if existia and not _es_texto(abs_ruta):
        return "Ese archivo no es de texto; no lo sobrescribo."
    respaldo = _respaldar(abs_ruta, log=log) if existia else None
    try:
        os.makedirs(os.path.dirname(abs_ruta) or ".", exist_ok=True)
        with open(abs_ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenido if contenido is not None else "")
    except Exception as e:
        return f"No pude escribirlo: {e}"
    _anota_deshacer(abs_ruta, respaldo, existia, log=log)
    n = len((contenido or "").splitlines())
    verbo = "Actualizado" if existia else "Creado"
    return f"{verbo} {abs_ruta} ({n} lineas). Reversible con «deshaz eso»."


def editar_archivo(ruta: str, buscar: str, reemplazar: str, log=print) -> str:
    ok, val = _permitida(ruta)
    if not ok:
        return f"No puedo editar eso: {val}."
    abs_ruta = val
    if not os.path.isfile(abs_ruta):
        return f"No existe el archivo {abs_ruta}."
    if not _es_texto(abs_ruta):
        return "No es un archivo de texto."
    if not buscar:
        return "Falta el fragmento a buscar."
    try:
        with open(abs_ruta, encoding="utf-8", errors="replace") as f:
            original = f.read()
    except Exception as e:
        return f"No pude leerlo: {e}"
    apariciones = original.count(buscar)
    if apariciones == 0:
        return "No encontre ese fragmento exacto en el archivo."
    if apariciones > 1:
        return (f"Ese fragmento aparece {apariciones} veces; no adivino cual. "
                "Amplia el contexto para que sea unico.")
    nuevo = original.replace(buscar, reemplazar if reemplazar is not None else "", 1)
    respaldo = _respaldar(abs_ruta, log=log)
    try:
        with open(abs_ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(nuevo)
    except Exception as e:
        return f"No pude guardarlo: {e}"
    _anota_deshacer(abs_ruta, respaldo, True, log=log)
    delta = len(nuevo.splitlines()) - len(original.splitlines())
    signo = f"+{delta}" if delta > 0 else str(delta)
    return f"Editado {abs_ruta} (1 sustitucion, {signo} lineas). Reversible con «deshaz eso»."


def listar_dir(ruta: str = ".", log=print) -> str:
    ok, val = _permitida(ruta or ".")
    if not ok:
        return f"No puedo mirar ahi: {val}."
    abs_ruta = val
    if not os.path.isdir(abs_ruta):
        return f"No es una carpeta: {abs_ruta}."
    try:
        entradas = sorted(os.listdir(abs_ruta))
    except Exception as e:
        return f"No pude listarla: {e}"
    filas = []
    for nombre in entradas[:200]:
        p = os.path.join(abs_ruta, nombre)
        if os.path.isdir(p):
            filas.append(f"  {nombre}/")
        else:
            try:
                filas.append(f"  {nombre}  ({os.path.getsize(p)} B)")
            except Exception:
                filas.append(f"  {nombre}")
    cola = "" if len(entradas) <= 200 else f"\n… ({len(entradas) - 200} mas)"
    return f"{abs_ruta}\n" + "\n".join(filas) + cola


def buscar_en_archivos(patron: str, ruta: str = ".", glob: str = "*", log=print) -> str:
    ok, val = _permitida(ruta or ".")
    if not ok:
        return f"No puedo buscar ahi: {val}."
    raiz = val
    if not patron:
        return "Falta el patron a buscar."
    try:
        rx = re.compile(patron, re.IGNORECASE)
    except re.error as e:
        return f"Patron invalido: {e}"
    saltar = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    hits, revisados = [], 0
    for base, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in saltar]
        for f in files:
            if not fnmatch.fnmatch(f, glob):
                continue
            p = os.path.join(base, f)
            if _VETADOS.search(p) or os.path.getsize(p) > _LIMITE_BYTES:
                continue
            revisados += 1
            if revisados > 4000:
                break
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    for n, linea in enumerate(fh, 1):
                        if rx.search(linea):
                            hits.append(f"{p}:{n}: {linea.strip()[:160]}")
                            if len(hits) >= 60:
                                break
            except Exception:
                continue
        if len(hits) >= 60:
            break
    if not hits:
        return f"Sin coincidencias de /{patron}/ en {raiz} ({revisados} archivos)."
    cola = "" if len(hits) < 60 else "\n… (cortado en 60)"
    return "\n".join(hits) + cola


# ── reversor para deshacer.py ───────────────────────────────────────────────
def revertir(datos: dict, log=print) -> tuple[int, int]:
    """Devuelve (hechos, fallos). Lo usa deshacer._REVERSORES['archivo']."""
    ruta = datos.get("ruta")
    respaldo = datos.get("respaldo")
    existia = datos.get("existia", True)
    if not ruta:
        return 0, 1
    try:
        if not existia:
            # El archivo lo creo el agente: a la papelera.
            import deshacer
            return (1, 0) if deshacer.a_papelera(ruta, log=log) else (0, 1)
        if respaldo and os.path.exists(respaldo):
            shutil.copy2(respaldo, ruta)
            return 1, 0
        return 0, 1
    except Exception as e:
        log(f"[FS] no pude revertir {ruta}: {e}")
        return 0, 1
