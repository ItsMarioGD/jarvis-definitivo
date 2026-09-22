#!/usr/bin/env python3
"""
energia.py - Apagado, reinicio y cancelacion del equipo (Windows)
=================================================================
Windows solo admite UN apagado programado a la vez: si ya hay uno en marcha,
`shutdown /s` devuelve el error 1190 y no hace nada. Como el resto del
proyecto lanzaba el comando con Popen y sin mirar el codigo de salida, JARVIS
contestaba "apagando el equipo" aunque Windows hubiera rechazado la orden;
por eso solo parecia obedecer la primera vez.

Aqui se centraliza el control de energia con dos reglas:

  1. Antes de programar nada se anula lo pendiente (`shutdown /a`). La ultima
     orden del usuario manda siempre, la repita las veces que la repita.
  2. Se lee el codigo de salida real. Si Windows falla, quien llama recibe el
     motivo y puede decirlo en voz alta en vez de mentir.
"""
import ejecutor

_YA_PROGRAMADO = 1190        # "Ya se ha programado un apagado del sistema"
_NADA_PENDIENTE = 1116       # "No se puede anular: no hay apagado en curso"


def _ejecutar(args, timeout=20, orden=""):
    """Lanza shutdown.exe por el ejecutor comun: control de errores y registro."""
    return ejecutor.ejecutar(["shutdown", *args], origen="energia", orden=orden,
                             timeout=timeout, shell=False)


def _motivo(res: dict) -> str:
    """Mensaje de error de Windows en texto legible."""
    texto = " ".join((res.get("error") or res.get("salida") or "").split())
    return texto or f"Windows devolvio el codigo {res.get('codigo')}"


def cancelar(log=None) -> bool:
    """Anula el apagado o reinicio pendiente. True si habia uno que anular."""
    res = _ejecutar(["/a"], orden="cancela el apagado")
    if res["ok"]:
        return True
    if res["codigo"] != _NADA_PENDIENTE and log:
        log(f"energia: cancelar devolvio {res['codigo']}: {_motivo(res)}")
    return False


def programar(segundos: int, reinicio: bool = False, motivo: str = "", log=None):
    """Programa el apagado (o el reinicio) tras `segundos`.

    Devuelve (ok, error). Anula primero cualquier apagado pendiente para que
    una orden nueva sustituya a la anterior en lugar de ser rechazada.
    """
    segundos = max(0, min(int(segundos), 315360000))   # tope de shutdown.exe
    cancelar(log)
    args = ["/r" if reinicio else "/s", "/t", str(segundos)]
    if motivo:
        args += ["/c", motivo[:511]]
    res = _ejecutar(args, orden=motivo or "apagado")
    if res["ok"]:
        _anotar_reversible(reinicio, segundos, log)
        return True, ""
    if res["codigo"] == _YA_PROGRAMADO:
        # Carrera con otro apagado que entro entre medias: anular y reintentar.
        cancelar(log)
        res = _ejecutar(args, orden=motivo or "apagado")
        if res["ok"]:
            _anotar_reversible(reinicio, segundos, log)
            return True, ""
    error = _motivo(res)
    if log:
        log(f"energia: shutdown {' '.join(args)} fallo ({res['codigo']}): {error}")
    return False, error


def _anotar_reversible(reinicio: bool, segundos: int, log):
    """Deja el apagado en el diario de deshacer («deshaz eso» lo cancela)."""
    try:
        import deshacer
        que = "reinicio" if reinicio else "apagado"
        deshacer.anotar("comando", f"programé el {que} en {segundos} segundos",
                        {"inverso": "shutdown /a"}, log=log or print)
    except Exception:
        pass


def apagar(segundos: int = 30, motivo: str = "", log=None):
    return programar(segundos, reinicio=False, motivo=motivo, log=log)


def reiniciar(segundos: int = 30, motivo: str = "", log=None):
    return programar(segundos, reinicio=True, motivo=motivo, log=log)
