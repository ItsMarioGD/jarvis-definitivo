#!/usr/bin/env python3
"""
sandbox.py - Ensayar antes de tocar el equipo de verdad
=======================================================
La idea 2 del IDEAS.MD (validar acciones en un emulador antes de ejecutarlas)
estaba pensada para Android, pero el sitio donde de verdad hace falta es
Windows: es aqui donde una orden mal entendida mueve doscientos archivos o mata
el proceso equivocado.

Tres modos, del mas barato al mas caro, y siempre se usa el mejor disponible:

  1. ENSAYO EN SECO. El proyecto ya tenia un interruptor `safe=True` en
     SkillsManager y PCControl que ejecuta toda la logica pero no toca nada.
     Nadie lo usaba fuera de las pruebas. Aqui sirve para responder «esto es lo
     que haria» con la MISMA logica que se ejecutaria de verdad.
  2. ANALISIS DE IMPACTO. Para ordenes de archivos, enumera exactamente que
     ficheros se verian afectados antes de mover o borrar nada.
  3. WINDOWS SANDBOX. Si el equipo lo tiene (Pro/Enterprise), ejecuta el
     comando dentro de una maquina desechable y devuelve su salida real.

Esto es lo que hace aceptable dejarle autonomia: no es que se equivoque menos,
es que puede enseñar el resultado antes de aplicarlo.
"""
import os
import re
import tempfile

WSB_EXE = r"C:\Windows\System32\WindowsSandbox.exe"


# ── disponibilidad ──────────────────────────────────────────────────────────
def disponible() -> dict:
    return {
        "ensayo_seco": True,                       # siempre, no necesita nada
        "impacto_archivos": True,
        "windows_sandbox": os.path.exists(WSB_EXE),
    }


# ── 1. ensayo en seco ───────────────────────────────────────────────────────
_seco = {"skills": None, "pc": None}


def _despachadores_seguros(log=print):
    """Copias de los despachadores en modo seguro (no ejecutan nada)."""
    if _seco["skills"] is None:
        try:
            from jarvis_skills import SkillsManager
            _seco["skills"] = SkillsManager(log=log, safe=True)
        except Exception as e:
            log(f"[SANDBOX] Sin habilidades en seco: {e}")
    if _seco["pc"] is None:
        try:
            from pc_control import PCControl
            _seco["pc"] = PCControl(log=log, safe=True)
        except Exception as e:
            log(f"[SANDBOX] Sin control del PC en seco: {e}")
    return [d for d in (_seco["skills"], _seco["pc"]) if d is not None]


def ensayar_orden(orden: str, log=print) -> str:
    """Qué pasaría con esta orden, sin que pase nada."""
    if not orden or not orden.strip():
        return "No hay ninguna orden que ensayar, señor."
    for despachador in _despachadores_seguros(log=log):
        try:
            r = despachador.handle(orden)
        except Exception as e:
            log(f"[SANDBOX] {type(despachador).__name__} falló en seco: {e}")
            continue
        if r:
            return f"En el ensayo, esta orden haría esto: {r}"
    return ("Ninguna habilidad reconoce esa orden, señor: iría al cerebro, "
            "que decidiría con sus herramientas.")


# ── 2. impacto sobre archivos ───────────────────────────────────────────────
_ALIAS = {
    "descargas": ["Descargas", "Downloads"],
    "documentos": ["Documentos", "Documents"],
    "escritorio": ["Escritorio", "Desktop"],
    "imagenes": ["Imágenes", "Pictures"],
    "musica": ["Música", "Music"],
    "videos": ["Vídeos", "Videos"],
}


def _resolver(carpeta: str) -> str:
    if os.path.isdir(carpeta):
        return carpeta
    hogar = os.path.expanduser("~")
    for nombre in _ALIAS.get(carpeta.strip().lower(), [carpeta]):
        ruta = os.path.join(hogar, nombre)
        if os.path.isdir(ruta):
            return ruta
    return ""


def impacto_archivos(orden: str, log=print) -> dict:
    """Qué ficheros tocaría una orden de mover/borrar en lote."""
    resultado = {"reconocida": False, "carpeta": "", "extension": "",
                 "afectados": [], "total": 0, "tamano_mb": 0.0}
    m = re.search(r"(?:mueve|copia|borra|elimina)\s+(?:todos\s+)?(?:los\s+)?"
                  r"(?:archivos\s+)?\.?(\w+)\s+(?:de|en)\s+([\w\s:\\/]+?)(?:\s+(?:a|hacia)\s|$)",
                  (orden or "").lower())
    if not m:
        return resultado
    extension, carpeta = m.group(1), m.group(2).strip()
    ruta = _resolver(carpeta)
    if not ruta:
        return resultado
    resultado.update({"reconocida": True, "carpeta": ruta, "extension": extension})
    try:
        bytes_totales = 0
        for f in os.listdir(ruta):
            if f.lower().endswith("." + extension.lower()):
                completo = os.path.join(ruta, f)
                if os.path.isfile(completo):
                    resultado["afectados"].append(f)
                    bytes_totales += os.path.getsize(completo)
        resultado["total"] = len(resultado["afectados"])
        resultado["tamano_mb"] = round(bytes_totales / (1024 * 1024), 1)
    except Exception as e:
        log(f"[SANDBOX] No pude analizar {ruta}: {e}")
    return resultado


def informe_impacto(orden: str, log=print) -> str:
    datos = impacto_archivos(orden, log=log)
    if not datos["reconocida"]:
        return ensayar_orden(orden, log=log)
    if not datos["total"]:
        return (f"No hay archivos .{datos['extension']} en "
                f"{os.path.basename(datos['carpeta'])}, señor: no tocaría nada.")
    muestra = ", ".join(datos["afectados"][:5])
    resto = f" y {datos['total'] - 5} más" if datos["total"] > 5 else ""
    return (f"Afectaría a {datos['total']} archivos .{datos['extension']} "
            f"({datos['tamano_mb']} MB) en {os.path.basename(datos['carpeta'])}: "
            f"{muestra}{resto}. Dígame «hazlo» si quiere que proceda.")


# ── 3. Windows Sandbox ──────────────────────────────────────────────────────
def ensayar_en_sandbox(comando: str, log=print, timeout: int = 180) -> dict:
    """Ejecuta un comando dentro de Windows Sandbox (máquina desechable)."""
    if not os.path.exists(WSB_EXE):
        return {"ok": False, "salida": "",
                "error": "Windows Sandbox no está disponible en este equipo "
                         "(requiere Windows Pro y activar la característica)."}

    carpeta = os.path.join(tempfile.gettempdir(), "jarvis_sandbox")
    os.makedirs(carpeta, exist_ok=True)
    salida = os.path.join(carpeta, "salida.txt")
    guion = os.path.join(carpeta, "prueba.cmd")
    with open(guion, "w", encoding="utf-8") as f:
        f.write("@echo off\r\n")
        f.write(f"{comando} > C:\\Datos\\salida.txt 2>&1\r\n")

    wsb = os.path.join(carpeta, "prueba.wsb")
    with open(wsb, "w", encoding="utf-8") as f:
        f.write(f"""<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>{carpeta}</HostFolder>
      <SandboxFolder>C:\\Datos</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>C:\\Datos\\prueba.cmd</Command></LogonCommand>
</Configuration>""")

    try:
        if os.path.exists(salida):
            os.unlink(salida)
    except Exception:
        pass

    import ejecutor
    log("[SANDBOX] Levantando Windows Sandbox (tarda unos segundos)...")
    ejecutor.lanzar([WSB_EXE, wsb], origen="sandbox", orden=comando, shell=False, log=log)

    import time
    inicio = time.time()
    while time.time() - inicio < timeout:
        if os.path.exists(salida):
            time.sleep(1.5)     # dejar que termine de escribir
            try:
                with open(salida, encoding="utf-8", errors="ignore") as f:
                    texto = f.read()
                return {"ok": True, "salida": texto[:4000], "error": ""}
            except Exception as e:
                return {"ok": False, "salida": "", "error": str(e)}
        time.sleep(2)
    return {"ok": False, "salida": "",
            "error": f"el ensayo no terminó en {timeout} segundos"}


def resumen() -> str:
    d = disponible()
    partes = ["ensayo en seco", "análisis de impacto"]
    if d["windows_sandbox"]:
        partes.append("Windows Sandbox (máquina desechable)")
    return ("Puedo ensayar antes de actuar con: " + ", ".join(partes) + "."
            + ("" if d["windows_sandbox"] else
               " Para la máquina desechable haría falta activar Windows Sandbox."))
