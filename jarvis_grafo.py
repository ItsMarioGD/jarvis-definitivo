#!/usr/bin/env python3
"""
jarvis_grafo.py - Memoria-grafo de conocimiento para Jarvis.
Adaptado de isair/jarvis (memory/graph.py): nodos en SQLite con ramas
(user/world/directives), dedupe por normalización, peso de uso y acceso
por recientes/top. Permite responder «¿qué sabes de X?» con hechos
relacionados e inyectar contexto al cerebro.
"""
import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime

DB = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "jarvis_grafo.db")
_lock = threading.RLock()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", (s or "").lower()))
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _con() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB, check_same_thread=False, timeout=10)
    con.execute("CREATE TABLE IF NOT EXISTS nodos ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "rama TEXT DEFAULT 'world',"
                "texto TEXT,"
                "norma TEXT UNIQUE,"
                "veces INTEGER DEFAULT 1,"
                "creado TEXT,"
                "ultimo TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS aristas ("
                "origen INTEGER,"
                "destino INTEGER,"
                "etiqueta TEXT DEFAULT 'relaciona',"
                "peso INTEGER DEFAULT 1,"
                "PRIMARY KEY (origen, destino, etiqueta))")
    con.commit()
    return con


def _nodo_id(con, texto: str, rama: str = "world") -> int | None:
    norma = _norm(texto)
    if not norma:
        return None
    ahora = datetime.now().isoformat(timespec="seconds")
    cur = con.execute("SELECT id FROM nodos WHERE norma = ?", (norma,))
    fila = cur.fetchone()
    if fila:
        con.execute("UPDATE nodos SET veces = veces + 1, ultimo = ? WHERE id = ?",
                    (ahora, fila[0]))
        con.commit()
        return fila[0]
    cur = con.execute("INSERT INTO nodos (rama, texto, norma, creado, ultimo) VALUES (?,?,?,?,?)",
                      (rama, texto.strip()[:200], norma, ahora, ahora))
    con.commit()
    return cur.lastrowid


def _arista(con, origen: int, destino: int, etiqueta: str = "relaciona"):
    if not origen or not destino or origen == destino:
        return
    con.execute("INSERT INTO aristas (origen, destino, etiqueta) VALUES (?,?,?) "
                "ON CONFLICT(origen, destino, etiqueta) "
                "DO UPDATE SET peso = peso + 1",
                (origen, destino, etiqueta))
    con.commit()


def aprender(texto: str) -> bool:
    """Extrae hechos simples en español y los guarda como nodos + arista."""
    if not texto:
        return False
    t = _norm(texto)
    patrones = [
        (re.compile(r"mi ([a-z]{2,30}) es ([a-z0-9\.\- ]{2,50})$"), "tiene"),
        (re.compile(r"mi nombre es ([a-z\.\- ]{2,40})$"), "se llama"),
        (re.compile(r"me llamo ([a-z\.\- ]{2,40})$"), "se llama"),
        (re.compile(r"me gusta ([a-z0-9 ]{2,40})$"), "le gusta"),
        (re.compile(r"no me gusta ([a-z0-9 ]{2,40})$"), "no le gusta"),
        (re.compile(r"odio ([a-z0-9 ]{2,40})$"), "odia"),
        (re.compile(r"detesto ([a-z0-9 ]{2,40})$"), "odia"),
        (re.compile(r"soy ([a-z0-9 ]{2,40})$"), "es"),
        (re.compile(r"recuerda que (?:mi |la |el )?([a-z0-9 ]{2,40}) es ([a-z0-9\.\- ]{2,50})$"), "es"),
    ]
    m = None
    for pat, etiqueta in patrones:
        m = pat.search(t)
        if m:
            break
    if not m:
        return False
    etiqueta = etiqueta
    grupos = m.groups()
    if etiqueta == "tiene":
        sujeto, objeto = "yo", f"{grupos[0]} {grupos[1]}"
    elif etiqueta in ("le gusta", "no le gusta", "odia", "se llama"):
        sujeto, objeto = "yo", grupos[0]
    else:
        sujeto, objeto = grupos
    try:
        with _lock:
            con = _con()
            try:
                s = _nodo_id(con, sujeto, rama="user")
                o = _nodo_id(con, objeto, rama="user" if sujeto == "yo" else "world")
                _arista(con, s, o, etiqueta)
                # Normaliza también el hecho completo como nodo para búsquedas libres
                _nodo_id(con, f"{sujeto} {etiqueta} {objeto}", rama="user")
            finally:
                con.close()
        return True
    except Exception:
        return False


def _claves(texto: str) -> list:
    return [w for w in _norm(texto).split() if len(w) > 3]


def consultar(texto: str, limite: int = 6) -> str:
    """Devuelve hechos relacionados con la consulta (nodos + vecinos por aristas)."""
    claves = _claves(texto)
    if not claves:
        return ""
    try:
        with _lock:
            con = _con()
            try:
                where = " OR ".join("norma LIKE ?" for _ in claves)
                params = [f"%{c}%" for c in claves]
                filas = con.execute(
                    f"SELECT texto, rama, veces FROM nodos WHERE {where} "
                    "ORDER BY (rama = 'user') DESC, veces DESC LIMIT ?",
                    params + [limite]).fetchall()
                if not filas:
                    return ""
                ids = [f[0] for f in filas]
                vecinos = []
                ph = ",".join("?" for _ in ids)
                for etiqueta, destino, texto_v in con.execute(
                        f"SELECT a.etiqueta, a.destino, n.texto FROM aristas a "
                        f"JOIN nodos n ON n.id = a.destino "
                        f"WHERE a.origen IN ({ph}) AND n.rama = 'user' LIMIT 8",
                        ids).fetchall():
                    vecinos.append(f"{texto_v} ({etiqueta})")
                lineas = [f"{t} ({r})" for t, r, v in filas]
                if vecinos:
                    lineas.append("Relacionado: " + ", ".join(vecinos[:4]))
                return " ".join(lineas[:limite + 1])
            finally:
                con.close()
    except Exception:
        return ""


def contexto(limite: int = 10) -> str:
    """Top nodos + recientes para inyección general al cerebro."""
    try:
        with _lock:
            con = _con()
            try:
                top = con.execute(
                    "SELECT texto, veces FROM nodos WHERE rama = 'user' "
                    "ORDER BY veces DESC LIMIT ?", (limite,)).fetchall()
                if not top:
                    return ""
                return "Conocimiento de Jarvis: " + ", ".join(f"{t} (x{v})" for t, v in top)
            finally:
                con.close()
    except Exception:
        return ""


def limpiar() -> str:
    try:
        with _lock:
            con = _con()
            try:
                con.execute("DELETE FROM aristas")
                con.execute("DELETE FROM nodos")
                con.commit()
            finally:
                con.close()
        return "Grafo de conocimiento limpio, señor."
    except Exception:
        return "Señor, no pude limpiar el grafo."