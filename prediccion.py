#!/usr/bin/env python3
"""
prediccion.py - El gemelo: anticiparse en vez de reaccionar
===========================================================
Desde que existe storage.py, cada orden ejecutada queda con su hora y su
resultado. Eso es, sin haberlo buscado, un diario de habitos: a que hora abre
el señor que cosa, que suele pedir los lunes, que hace siempre despues de otra
cosa.

Este modulo lee ese diario y responde a dos preguntas:

    ¿que suele hacer a esta hora?      -> sugerir antes de que lo pida
    ¿que suele venir despues de esto?  -> encadenar sin que lo pida

No hay magia ni modelo pesado: son frecuencias sobre las ultimas semanas, con
un umbral de confianza para no ser pesado. Deliberadamente conservador, porque
un asistente que se adelanta mal molesta mucho mas que uno que espera.

La ejecucion automatica es opt-in (preferencia `anticipar`): por defecto solo
sugiere. Adelantarse a abrir programas sin permiso es exactamente el tipo de
cosa que hace que la gente desinstale un asistente.
"""
import os
from collections import Counter, defaultdict
from datetime import datetime

DIAS_HISTORIA = int(os.getenv("JARVIS_PREDICCION_DIAS", "30"))
MIN_OCURRENCIAS = int(os.getenv("JARVIS_PREDICCION_MINIMO", "4"))
CONFIANZA_MINIMA = float(os.getenv("JARVIS_PREDICCION_CONFIANZA", "0.5"))


def _acciones(log=print, limite: int = 3000):
    try:
        from storage import get_storage
        return get_storage(log=log).acciones_recientes(limite)
    except Exception as e:
        log(f"[PREDICCION] No pude leer el historial: {e}")
        return []


def _franja(ts: str) -> int:
    """Hora del día (0-23) de un registro."""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").hour
    except Exception:
        return -1


def _clave(accion: dict) -> str:
    """Etiqueta estable de la acción: preferimos la orden hablada."""
    orden = (accion.get("orden") or "").strip().lower()
    if orden:
        return orden[:60]
    return (accion.get("origen") or "?")[:60]


# ── patrones ────────────────────────────────────────────────────────────────
def patrones_por_hora(log=print) -> dict:
    """{hora: [(orden, veces, confianza), ...]} con lo habitual en esa franja."""
    acciones = _acciones(log=log)
    por_hora = defaultdict(Counter)
    total_hora = Counter()
    for a in acciones:
        if not a.get("ok"):
            continue           # lo que falló no es un hábito, es un intento
        hora = _franja(a.get("ts", ""))
        if hora < 0:
            continue
        por_hora[hora][_clave(a)] += 1
        total_hora[hora] += 1

    salida = {}
    for hora, cuentas in por_hora.items():
        filas = []
        for orden, veces in cuentas.most_common(5):
            if veces < MIN_OCURRENCIAS:
                continue
            confianza = veces / max(total_hora[hora], 1)
            if confianza >= CONFIANZA_MINIMA:
                filas.append((orden, veces, round(confianza, 2)))
        if filas:
            salida[hora] = filas
    return salida


def secuencias(log=print) -> dict:
    """{orden: (siguiente_mas_probable, confianza)} — qué suele venir después."""
    acciones = list(reversed(_acciones(log=log)))     # de más antigua a más nueva
    pares = defaultdict(Counter)
    for anterior, siguiente in zip(acciones, acciones[1:]):
        if not anterior.get("ok") or not siguiente.get("ok"):
            continue
        a, b = _clave(anterior), _clave(siguiente)
        if a and b and a != b:
            pares[a][b] += 1

    salida = {}
    for orden, cuentas in pares.items():
        total = sum(cuentas.values())
        siguiente, veces = cuentas.most_common(1)[0]
        if veces >= MIN_OCURRENCIAS and veces / total >= CONFIANZA_MINIMA:
            salida[orden] = (siguiente, round(veces / total, 2))
    return salida


# ── uso ─────────────────────────────────────────────────────────────────────
def sugerencias(log=print, hora: int = None) -> list:
    """Qué haría el señor normalmente a esta hora y aún no ha pedido hoy."""
    hora = datetime.now().hour if hora is None else hora
    patrones = patrones_por_hora(log=log)
    candidatas = patrones.get(hora, [])
    if not candidatas:
        return []

    hoy = datetime.now().strftime("%Y-%m-%d")
    ya_hechas = {_clave(a) for a in _acciones(log=log, limite=400)
                 if (a.get("ts") or "").startswith(hoy)}
    return [(orden, veces, conf) for orden, veces, conf in candidatas
            if orden not in ya_hechas]


def frase_sugerencia(log=print) -> str:
    """Una sola sugerencia, en la voz del mayordomo, o cadena vacía."""
    pendientes = sugerencias(log=log)
    if not pendientes:
        return ""
    orden, veces, confianza = pendientes[0]
    return (f"Señor, a esta hora suele pedirme «{orden}» "
            f"({veces} veces, {int(confianza * 100)}% de las veces). "
            "¿Se lo preparo?")


def siguiente_probable(ultima_orden: str, log=print) -> str:
    """Qué suele venir después de la orden que se acaba de ejecutar."""
    if not ultima_orden:
        return ""
    mapa = secuencias(log=log)
    fila = mapa.get(ultima_orden.strip().lower()[:60])
    if not fila:
        return ""
    siguiente, confianza = fila
    return (f"Después de esto suele pedirme «{siguiente}» "
            f"({int(confianza * 100)}%). ¿Lo hago ya?")


def informe(log=print) -> str:
    """Resumen legible de lo aprendido sobre los hábitos del señor."""
    patrones = patrones_por_hora(log=log)
    if not patrones:
        return ("Todavía no tengo suficientes datos para conocer sus hábitos, "
                "señor. Necesito unas cuantas semanas de uso.")
    lineas = []
    for hora in sorted(patrones):
        principal = patrones[hora][0]
        lineas.append(f"{hora:02d}:00 → «{principal[0]}» ({principal[1]} veces)")
    return "Sus costumbres, señor: " + "; ".join(lineas[:8]) + "."


def anticipar(core, log=print) -> str:
    """Ejecuta la sugerencia si el señor autorizó adelantarse (opt-in)."""
    try:
        if (core.get_pref("anticipar") or "0") != "1":
            return ""
    except Exception:
        return ""
    pendientes = sugerencias(log=log)
    if not pendientes:
        return ""
    orden, _veces, confianza = pendientes[0]
    if confianza < 0.7:
        return ""      # para actuar solo, el listón sube
    for despachador in (getattr(core, "skills", None), getattr(core, "pc", None)):
        if despachador is None:
            continue
        try:
            r = despachador.handle(orden)
        except Exception:
            continue
        if r:
            log(f"[PREDICCION] Me adelanté: {orden}")
            return f"Me he adelantado, señor: {r}"
    return ""
