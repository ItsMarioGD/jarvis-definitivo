#!/usr/bin/env python3
"""
servicio.py - Que JARVIS sobreviva al cierre de sesion
======================================================
El arranque automatico actual es un .vbs en la carpeta Inicio. Eso significa
tres cosas: muere al cerrar sesion, no se reinicia si el proceso cae, y no hay
forma de ver si esta corriendo salvo mirar el administrador de tareas.

El vigilante cuida los subsistemas de dentro; esto cuida el proceso entero.
Tres formas, de menos a mas robusta, y se usa la mejor disponible:

  1. TAREA PROGRAMADA (schtasks). No necesita instalar nada, arranca al iniciar
     sesion y Windows la reinicia si falla. Es la opcion por defecto.
  2. TAREA AL ARRANCAR EL EQUIPO (requiere administrador): funciona aunque
     nadie inicie sesion.
  3. SERVICIO DE WINDOWS con NSSM, si el señor lo tiene instalado: reinicio
     automatico inmediato y control desde services.msc.

    python servicio.py instalar      deja JARVIS arrancando solo
    python servicio.py estado        dice como esta configurado
    python servicio.py quitar        lo desmonta
"""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
NOMBRE_TAREA = "JARVIS"
NOMBRE_SERVICIO = "JarvisAsistente"


def _python() -> str:
    """Preferimos pythonw.exe: sin ventana de consola parpadeando."""
    ejecutable = sys.executable or "python"
    sin_consola = ejecutable.replace("python.exe", "pythonw.exe")
    return sin_consola if os.path.exists(sin_consola) else ejecutable


def _comando_arranque() -> str:
    return f'"{_python()}" "{os.path.join(RAIZ, "jarvis.py")}" web'


def _nssm() -> str:
    for ruta in (r"C:\Program Files\nssm\nssm.exe", "nssm.exe", "nssm"):
        try:
            r = subprocess.run([ruta, "version"], capture_output=True, timeout=10)
            if r.returncode == 0:
                return ruta
        except Exception:
            continue
    return ""


# ── instalación ─────────────────────────────────────────────────────────────
def instalar(al_arrancar_equipo: bool = False, log=print) -> str:
    """Deja JARVIS arrancando solo por el mejor camino disponible."""
    nssm = _nssm()
    if nssm:
        return _instalar_nssm(nssm, log=log)
    return _instalar_tarea(al_arrancar_equipo, log=log)


def _instalar_tarea(al_arrancar_equipo: bool, log=print) -> str:
    import ejecutor
    # /RL HIGHEST para que pueda ejecutar acciones del sistema (apagados, etc.)
    args = ["schtasks", "/Create", "/TN", NOMBRE_TAREA, "/TR", _comando_arranque(),
            "/SC", "ONSTART" if al_arrancar_equipo else "ONLOGON",
            "/RL", "HIGHEST", "/F"]
    res = ejecutor.ejecutar(args, origen="servicio", orden="instalar arranque",
                            shell=False, timeout=60, log=log)
    if not res["ok"]:
        return (f"No pude crear la tarea, señor: {res['error'][:150]}"
                + (" (arrancar con el equipo requiere administrador)"
                   if al_arrancar_equipo else ""))
    cuando = "al encender el equipo" if al_arrancar_equipo else "al iniciar sesión"
    return (f"Listo, señor: arrancaré {cuando}, con permisos altos y sin ventana. "
            "Windows me relanzará si el proceso cae.")


def _instalar_nssm(nssm: str, log=print) -> str:
    import ejecutor
    ejecutor.ejecutar([nssm, "install", NOMBRE_SERVICIO, _python(),
                       os.path.join(RAIZ, "jarvis.py"), "web"],
                      origen="servicio", orden="crear servicio", shell=False, log=log)
    for clave, valor in (("AppDirectory", RAIZ),
                         ("AppExit Default", "Restart"),
                         ("AppRestartDelay", "5000"),
                         ("Start", "SERVICE_AUTO_START")):
        ejecutor.ejecutar([nssm, "set", NOMBRE_SERVICIO, *clave.split(" ", 1), valor]
                          if " " in clave else
                          [nssm, "set", NOMBRE_SERVICIO, clave, valor],
                          origen="servicio", orden=f"configurar {clave}",
                          shell=False, log=log)
    res = ejecutor.ejecutar([nssm, "start", NOMBRE_SERVICIO], origen="servicio",
                            orden="arrancar servicio", shell=False, log=log)
    if not res["ok"]:
        return (f"Servicio creado, señor, pero no arrancó: {res['error'][:150]}. "
                "Pruebe desde services.msc.")
    return (f"Servicio «{NOMBRE_SERVICIO}» instalado y en marcha, señor. "
            "Se reinicia solo a los cinco segundos si cae, y sobrevive al "
            "cierre de sesión.")


# ── estado y desinstalación ─────────────────────────────────────────────────
def estado(log=print) -> dict:
    import ejecutor
    datos = {"tarea": False, "servicio": False, "nssm": bool(_nssm()),
             "detalle": ""}
    res = ejecutor.ejecutar(["schtasks", "/Query", "/TN", NOMBRE_TAREA],
                            origen="servicio", orden="consultar tarea",
                            shell=False, timeout=30, log=log)
    datos["tarea"] = res["ok"]
    if res["ok"]:
        datos["detalle"] = (res["salida"] or "").strip().splitlines()[-1][:120]

    if datos["nssm"]:
        r = ejecutor.ejecutar([_nssm(), "status", NOMBRE_SERVICIO],
                              origen="servicio", orden="consultar servicio",
                              shell=False, timeout=30, log=log)
        datos["servicio"] = r["ok"] and "RUNNING" in (r["salida"] or "").upper()
    return datos


def resumen(log=print) -> str:
    e = estado(log=log)
    if e["servicio"]:
        return (f"Corro como servicio de Windows («{NOMBRE_SERVICIO}»), señor: "
                "sobrevivo al cierre de sesión y me reinicio solo.")
    if e["tarea"]:
        return (f"Estoy en el programador de tareas como «{NOMBRE_TAREA}», señor: "
                "arranco solo al iniciar sesión.")
    return ("No tengo arranque automático configurado, señor. Dígame «instálate "
            "como servicio» y lo dejo hecho.")


def quitar(log=print) -> str:
    import ejecutor
    quitados = []
    res = ejecutor.ejecutar(["schtasks", "/Delete", "/TN", NOMBRE_TAREA, "/F"],
                            origen="servicio", orden="quitar tarea",
                            shell=False, timeout=30, log=log)
    if res["ok"]:
        quitados.append("tarea programada")
    nssm = _nssm()
    if nssm:
        ejecutor.ejecutar([nssm, "stop", NOMBRE_SERVICIO], origen="servicio",
                          orden="parar servicio", shell=False, log=log)
        r = ejecutor.ejecutar([nssm, "remove", NOMBRE_SERVICIO, "confirm"],
                              origen="servicio", orden="quitar servicio",
                              shell=False, log=log)
        if r["ok"]:
            quitados.append("servicio de Windows")
    if not quitados:
        return "No había arranque automático que quitar, señor."
    return f"Quitado, señor: {', '.join(quitados)}. Ya no arrancaré solo."


def main(argv) -> int:
    accion = (argv[0].lower() if argv else "estado")
    if accion.startswith("instal"):
        print(instalar(al_arrancar_equipo="--equipo" in argv))
    elif accion.startswith("quit") or accion.startswith("desinstal"):
        print(quitar())
    else:
        print(resumen())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
