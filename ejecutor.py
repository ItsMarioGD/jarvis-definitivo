#!/usr/bin/env python3
"""
ejecutor.py - Punto unico de ejecucion de comandos del sistema
==============================================================
El patron viejo era este, repetido 40 veces por el proyecto:

    subprocess.Popen(comando, shell=True, creationflags=0x08000000)
    return "Hecho, señor."

Popen solo falla si no puede CREAR el proceso. Si el comando arranca y despues
Windows lo rechaza (permisos, apagado ya programado, servicio inexistente), el
codigo de salida se pierde y el asistente contesta «hecho» igual. Asi nacio el
bug del apagado: obedecia una vez y luego mentia.

Aqui hay dos formas de lanzar cosas, y las dos dejan rastro en storage.py:

  ejecutar(...)  espera al proceso, lee returncode y stderr, y devuelve el
                 error real para poder decirlo en voz alta.
  lanzar(...)    para lo que debe seguir vivo despues de contestar (abrir una
                 app, reproducir musica). Comprueba que el proceso arranca y,
                 opcionalmente, que sigue vivo un instante despues.
"""
import os
import subprocess
import time

_SIN_VENTANA = 0x08000000 if os.name == "nt" else 0
_CODECS = ("utf-8", "cp850", "cp1252")


def _texto(bruto: bytes) -> str:
    if not bruto:
        return ""
    for codec in _CODECS:
        try:
            return bruto.decode(codec).strip()
        except Exception:
            continue
    return bruto.decode("utf-8", errors="ignore").strip()


def _registrar(origen, orden, comando, ok, detalle, ms, agente):
    """Deja rastro en el almacen. Nunca rompe la accion si el registro falla."""
    try:
        from storage import get_storage
        get_storage().registrar_accion(origen=origen, orden=orden, comando=comando,
                                       ok=ok, detalle=detalle, ms=ms, agente=agente)
    except Exception:
        pass


def _cmd_texto(comando) -> str:
    return comando if isinstance(comando, str) else " ".join(str(c) for c in comando)


def ejecutar(comando, origen: str = "sistema", orden: str = "", timeout: int = 20,
             shell: bool = None, log=None, agente: str = "JARVIS") -> dict:
    """Ejecuta y espera. Devuelve {ok, salida, error, codigo}.

    `comando` puede ser cadena (shell) o lista (sin shell). `orden` es la frase
    que dijo el señor, para que el registro sea legible despues.
    """
    if shell is None:
        shell = isinstance(comando, str)
    texto_cmd = _cmd_texto(comando)
    inicio = time.time()
    kwargs = {"capture_output": True, "timeout": timeout, "shell": shell}
    if _SIN_VENTANA:
        kwargs["creationflags"] = _SIN_VENTANA
    try:
        p = subprocess.run(comando, **kwargs)
    except subprocess.TimeoutExpired:
        ms = int((time.time() - inicio) * 1000)
        _registrar(origen, orden, texto_cmd, False, f"timeout tras {timeout}s", ms, agente)
        if log:
            log(f"ejecutor: timeout en «{texto_cmd[:60]}»")
        return {"ok": False, "salida": "", "error": f"no respondio en {timeout} segundos",
                "codigo": -1}
    except Exception as e:
        ms = int((time.time() - inicio) * 1000)
        _registrar(origen, orden, texto_cmd, False, str(e)[:300], ms, agente)
        if log:
            log(f"ejecutor: «{texto_cmd[:60]}» no arranco: {e}")
        return {"ok": False, "salida": "", "error": str(e), "codigo": -1}

    ms = int((time.time() - inicio) * 1000)
    salida = _texto(p.stdout)
    error = _texto(p.stderr)
    ok = p.returncode == 0
    detalle = (error or salida)[:300] if not ok else salida[:200]
    _registrar(origen, orden, texto_cmd, ok, detalle, ms, agente)
    if not ok and log:
        log(f"ejecutor: «{texto_cmd[:60]}» devolvio {p.returncode}: {error[:120]}")
    return {"ok": ok, "salida": salida,
            "error": error or (f"codigo de salida {p.returncode}" if not ok else ""),
            "codigo": p.returncode}


def lanzar(comando, origen: str = "sistema", orden: str = "", shell: bool = None,
           verificar_ms: int = 0, log=None, agente: str = "JARVIS"):
    """Arranca un proceso y sigue. Devuelve (ok, error, proceso).

    verificar_ms > 0 espera ese tiempo y comprueba que el proceso no haya
    muerto ya con error: sirve para detectar «abre spotify» cuando spotify no
    esta instalado, que antes se contestaba como exito.
    """
    if shell is None:
        shell = isinstance(comando, str)
    texto_cmd = _cmd_texto(comando)
    kwargs = {"shell": shell}
    if _SIN_VENTANA:
        kwargs["creationflags"] = _SIN_VENTANA
    try:
        proc = subprocess.Popen(comando, **kwargs)
    except Exception as e:
        _registrar(origen, orden, texto_cmd, False, str(e)[:300], 0, agente)
        if log:
            log(f"ejecutor: no pude lanzar «{texto_cmd[:60]}»: {e}")
        return False, str(e), None

    if verificar_ms > 0:
        time.sleep(verificar_ms / 1000.0)
        codigo = proc.poll()
        if codigo is not None and codigo != 0:
            _registrar(origen, orden, texto_cmd, False, f"salio con codigo {codigo}",
                       verificar_ms, agente)
            if log:
                log(f"ejecutor: «{texto_cmd[:60]}» murio con codigo {codigo}")
            return False, f"el proceso termino con codigo {codigo}", proc

    _registrar(origen, orden, texto_cmd, True, "lanzado", 0, agente)
    return True, "", proc


def powershell(script: str, origen: str = "powershell", orden: str = "",
               timeout: int = 30, log=None, agente: str = "JARVIS") -> dict:
    """Atajo para scripts de PowerShell con el mismo control de errores."""
    return ejecutar(["powershell", "-NoProfile", "-Command", script],
                    origen=origen, orden=orden, timeout=timeout, shell=False,
                    log=log, agente=agente)
