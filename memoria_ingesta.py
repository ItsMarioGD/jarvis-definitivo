#!/usr/bin/env python3
"""
memoria_ingesta.py - Volcar las memorias viejas a la unificada
============================================================
Idempotente: cada fuente lleva una marca de "hasta dónde migré". Se puede
correr en cada arranque sin duplicar. No borra nada de lo viejo — mientras
JARVIS_MEMORIA_UNICA no esté a 1, la unificada solo se llena, no se lee.
"""
import os
import time

import memoria_grafo as M


def _prefs(core, log=print) -> int:
    n = 0
    try:
        cur = core.conn.cursor()
        for k, v in cur.execute("SELECT key, value FROM user_prefs").fetchall():
            M.recordar(f"{k}: {v}", tipo="preferencia", sujeto="señor",
                       predicado=str(k), objeto=str(v), fuente="user_prefs",
                       peso=2.0, log=log)
            n += 1
    except Exception as e:
        log(f"[INGESTA] user_prefs: {e}")
    return n


def _reminders(core, log=print) -> int:
    n = 0
    try:
        cur = core.conn.cursor()
        for ts, due, texto in cur.execute(
                "SELECT timestamp, due, text FROM reminders WHERE done=0").fetchall():
            M.recordar(f"Recordatorio: {texto}" + (f" (para {due})" if due else ""),
                       tipo="recordatorio", sujeto="señor", fuente="reminders",
                       peso=1.5, log=log)
            n += 1
    except Exception as e:
        log(f"[INGESTA] reminders: {e}")
    return n


def _eventos(log=print) -> int:
    n = 0
    try:
        from storage import get_storage
        desde_id = int(M.marca_get("ingesta_eventos_id") or "0")
        db = get_storage(log=log)
        con = db._conn
        filas = con.execute(
            "SELECT id, ts, tipo, titulo, detalle FROM eventos WHERE id>? ORDER BY id LIMIT 5000",
            (desde_id,)).fetchall()
        ultimo = desde_id
        for f in filas:
            try:
                tt = time.mktime(time.strptime(f["ts"], "%Y-%m-%d %H:%M:%S"))
            except Exception:
                tt = time.time()
            M.recordar(f"{f['titulo']}. {f['detalle']}".strip(". "),
                       tipo="evento", fuente=f"evento:{f['tipo']}", ts=tt,
                       peso=0.8, caduca_dias=120, log=log)
            ultimo = max(ultimo, f["id"]); n += 1
        if ultimo != desde_id:
            M.marca_set("ingesta_eventos_id", str(ultimo))
    except Exception as e:
        log(f"[INGESTA] eventos: {e}")
    return n


def _grafo(log=print) -> int:
    n = 0
    try:
        import jarvis_grafo
        con = jarvis_grafo._con()
        nodos = {r[0]: r[1] for r in con.execute("SELECT id, texto FROM nodos").fetchall()}
        for o, d, et in con.execute("SELECT origen, destino, etiqueta FROM aristas").fetchall():
            so, ob = nodos.get(o, ""), nodos.get(d, "")
            if not so or not ob:
                continue
            M.recordar(f"{so} {et} {ob}", tipo="grafo", sujeto=so, predicado=et,
                       objeto=ob, fuente="jarvis_grafo", peso=1.0,
                       entidades=[so, ob], log=log)
            n += 1
    except Exception as e:
        log(f"[INGESTA] jarvis_grafo: {e}")
    return n


def _jarvis_md(log=print) -> int:
    n = 0
    try:
        import memoria_proyecto
        txt = memoria_proyecto.cargar(log=log)
        for linea in txt.splitlines():
            linea = linea.strip()
            if linea.startswith("- ") and linea != "- (aún nada)":
                M.recordar(linea[2:], tipo="permanente", sujeto="señor",
                           fuente="JARVIS.md", peso=3.0, log=log)
                n += 1
    except Exception as e:
        log(f"[INGESTA] JARVIS.md: {e}")
    return n


def migrar(core=None, log=print, forzar=False) -> dict:
    ya = M.marca_get("ingesta_hecha")
    hoy = time.strftime("%Y-%m-%d")
    r = {"eventos": _eventos(log=log)}          # incremental siempre
    if forzar or ya != hoy:
        if core is not None:
            r["preferencias"] = _prefs(core, log=log)
            r["recordatorios"] = _reminders(core, log=log)
        r["grafo"] = _grafo(log=log)
        r["permanente"] = _jarvis_md(log=log)
        M.marca_set("ingesta_hecha", hoy)
    log(f"[INGESTA] migración: {r}")
    return r
