#!/usr/bin/env python3
"""
feedback.py - «eso estuvo mal» / «así sí»
=========================================
Es el unico dato que el sistema no capturaba. JARVIS registra lo que ejecuta,
con que resultado y a que hora, pero no si al señor le PARECIO BIEN. Sin eso,
el clasificador de intenciones aprende a repetir lo que hizo, no lo que
acerto, y el futuro ajuste fino (afinar.py) entrenaria con ejemplos malos
mezclados con buenos.

Aqui se recoge la valoracion en el momento, asociada a la ultima orden:

    «eso estuvo mal»        -> negativo
    «asi si», «perfecto»    -> positivo
    «no era eso, queria X»  -> negativo + correccion

Y se usa para tres cosas:
  * filtrar el dataset de entrenamiento (fuera lo valorado en negativo),
  * pesar los ejemplos del clasificador de intenciones,
  * un informe honesto: en que acierta y en que falla mas.
"""
import re

POSITIVAS = (
    "asi si", "así sí", "perfecto", "muy bien", "eso es", "correcto", "genial",
    "buen trabajo", "exacto", "asi me gusta", "así me gusta", "bien hecho",
)
NEGATIVAS = (
    "eso estuvo mal", "esta mal", "está mal", "no era eso", "te equivocaste",
    "mal hecho", "no queria eso", "no quería eso", "eso no era", "fatal",
    "no me sirve", "eso no sirve", "te has equivocado",
)


def clasificar_frase(texto: str):
    """(signo, correccion) — signo: +1, -1 o 0 si no es una valoración."""
    t = (texto or "").strip().lower()
    if not t or len(t.split()) > 12:
        return 0, ""
    for frase in NEGATIVAS:
        if t.startswith(frase) or t == frase:
            correccion = ""
            m = re.search(r"(?:queria|quería|era|pedi|pedí)\s+(.+)", t)
            if m:
                correccion = m.group(1).strip()
            return -1, correccion
    for frase in POSITIVAS:
        if t.startswith(frase) or t == frase:
            return 1, ""
    return 0, ""


def anotar(signo: int, orden: str, respuesta: str = "", correccion: str = "",
           agente: str = "JARVIS", log=print) -> str:
    """Guarda la valoración junto a la orden que la provocó."""
    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "valoracion", "positiva" if signo > 0 else "negativa",
            f"orden: {orden[:150]} | respuesta: {respuesta[:150]}"
            + (f" | quería: {correccion[:100]}" if correccion else ""),
            gravedad="info", datos=str(signo), agente=agente)
    except Exception as e:
        log(f"[FEEDBACK] No pude anotar la valoración: {e}")

    if signo > 0:
        return "Gracias, señor. Lo tendré en cuenta para la próxima."
    if correccion:
        return (f"Anotado, señor: no era eso, quería «{correccion[:60]}». "
                "Lo aprendo para no repetirlo.")
    return ("Anotado, señor. ¿Qué debería haber hecho? Si me lo dice, lo aprendo "
            "para la próxima.")


def valoraciones(limite: int = 200, log=print) -> list:
    try:
        from storage import get_storage
        return get_storage(log=log).eventos_recientes(limite, tipo="valoracion")
    except Exception:
        return []


def informe(log=print) -> str:
    """En qué acierta y en qué falla, según el propio señor."""
    filas = valoraciones(log=log)
    if not filas:
        return ("Nadie me ha dicho todavía si lo hago bien o mal, señor. "
                "Dígame «eso estuvo mal» o «así sí» cuando quiera y lo aprendo.")
    positivas = [f for f in filas if f.get("titulo") == "positiva"]
    negativas = [f for f in filas if f.get("titulo") == "negativa"]
    total = len(positivas) + len(negativas)
    acierto = (len(positivas) / total * 100) if total else 0

    fallos = []
    for f in negativas[:5]:
        detalle = f.get("detalle", "")
        m = re.search(r"orden: ([^|]+)", detalle)
        if m:
            fallos.append(m.group(1).strip()[:50])
    cola = f" Donde más he fallado: {'; '.join(fallos)}." if fallos else ""
    return (f"Me ha valorado {total} veces, señor: {len(positivas)} bien y "
            f"{len(negativas)} mal ({acierto:.0f}% de acierto).{cola}")


def ordenes_valoradas(signo: int = -1, log=print) -> set:
    """Órdenes marcadas como buenas o malas, para filtrar el entrenamiento."""
    salida = set()
    etiqueta = "negativa" if signo < 0 else "positiva"
    for f in valoraciones(1000, log=log):
        if f.get("titulo") != etiqueta:
            continue
        m = re.search(r"orden: ([^|]+)", f.get("detalle", ""))
        if m:
            salida.add(m.group(1).strip().lower()[:100])
    return salida
