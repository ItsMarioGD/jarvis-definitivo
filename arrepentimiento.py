#!/usr/bin/env python3
"""
arrepentimiento.py - Ventana para decir «no» despues de actuar
==============================================================
Las confirmaciones previas («¿seguro que quiere mover 214 archivos?») tienen un
problema conocido: se aceptan sin leer. Al tercer dia el señor pulsa «si» por
reflejo y la pregunta deja de proteger nada, ademas de haber estorbado
doscientas veces.

Con el diario de deshacer ya montado hay una opcion mejor: ejecutar, avisar de
lo que se ha hecho, y dejar una ventana corta para arrepentirse.

    «He movido 214 archivos a Documentos. Dígame «no» en 15 segundos y lo
     deshago.»

Si el señor no dice nada, el trabajo ya esta hecho: cero fricción. Si dice que
no, se revierte solo. La ventana se cancela sola al expirar, y cualquier
«deshaz eso» posterior sigue funcionando igual, porque el diario no caduca.

Solo se abre ventana para acciones REVERSIBLES y de cierto tamaño: mover o
renombrar en lote, cerrar aplicaciones, apagados programados. Para lo que no se
puede deshacer se sigue preguntando antes, que para eso no hay alternativa.
"""
import threading
import time

VENTANA_S = 15.0
_lock = threading.Lock()
_activa = None          # {"descripcion", "expira", "id_deshacer"}


def abrir(descripcion: str, segundos: float = VENTANA_S, log=print) -> str:
    """Abre la ventana tras una acción ya ejecutada. Devuelve la frase a decir."""
    global _activa
    with _lock:
        _activa = {"descripcion": descripcion,
                   "expira": time.time() + max(3.0, segundos)}
    log(f"[ARREPENTIMIENTO] Ventana abierta ({segundos:.0f}s): {descripcion[:60]}")
    return (f"{descripcion} Dígame «no» en los próximos {int(segundos)} segundos "
            "y lo deshago.")


def abierta() -> bool:
    with _lock:
        if _activa is None:
            return False
        if time.time() > _activa["expira"]:
            return False
        return True


def descripcion() -> str:
    with _lock:
        return (_activa or {}).get("descripcion", "")


def cerrar():
    global _activa
    with _lock:
        _activa = None


def es_arrepentimiento(texto: str) -> bool:
    """¿Esta frase es un «no» dentro de la ventana?

    Se exige que sea corta: «no» es arrepentimiento, pero «no, mejor busca otra
    cosa en internet» es una orden nueva y no debe revertir nada.
    """
    if not abierta():
        return False
    t = (texto or "").strip().lower().strip(".!¡ ")
    if len(t.split()) > 4:
        return False
    negaciones = ("no", "no no", "para", "detente", "cancela", "espera",
                  "deshazlo", "vuelve atras", "vuelve atrás", "quita eso",
                  "no era eso", "mal", "eso no")
    return t in negaciones


def atender(core, log=print) -> str:
    """Revierte lo que abrió la ventana. Se llama al detectar el «no»."""
    texto_accion = descripcion()
    cerrar()
    try:
        import deshacer
        resultado = deshacer.deshacer_ultimo(
            1, log=log, set_pref=getattr(core, "set_pref", None),
            agente=getattr(core, "nombre_agente", "JARVIS"))
    except Exception as e:
        return f"No pude revertirlo, señor: {e}"
    log(f"[ARREPENTIMIENTO] Revertido: {texto_accion[:60]}")
    return resultado


def envolver(respuesta: str, descripcion_accion: str = "", segundos: float = VENTANA_S,
             log=print) -> str:
    """Añade la ventana a la respuesta de una acción reversible ya hecha."""
    if not respuesta:
        return respuesta
    return abrir(descripcion_accion or respuesta, segundos=segundos, log=log)


# Órdenes cuyo resultado merece ventana: son reversibles y suelen ser masivas.
MERECEN_VENTANA = (
    "mueve todos", "mueve los", "renombra los", "organiza la carpeta",
    "organiza las descargas", "vacia la papelera", "vacía la papelera",
    "cierra ", "apaga el pc", "apagate", "apágate", "reinicia el",
    "limpia los temporales",
)


def merece_ventana(orden: str) -> bool:
    t = (orden or "").lower()
    return any(p in t for p in MERECEN_VENTANA)
