#!/usr/bin/env python3
"""
memoria_grafo.py - Una sola memoria, con tiempo
==============================================
JARVIS tenía ocho memorias que no se hablaban: mem0 (semántico), user_prefs
(clave-valor), jarvis_grafo (grafo propio), JARVIS.md, storage.eventos, el
contexto rodante, headroom y rebobinar. Esto las colapsa en un único almacén:

    hechos(ts, tipo, texto, sujeto, predicado, objeto, fuente, peso, usos, caduca)

Con eso se cubren las tres formas de recordar que importan:

    recall(consulta)      búsqueda por texto (FTS5) + recencia + peso
    episodico("el martes")  ventana temporal: qué pasó entre dos instantes
    entidad("Marta")      todo lo que sé de una entidad concreta

`decaer()` baja el peso de lo viejo y no usado, y borra lo que cae por debajo
del umbral: la memoria deja de crecer para siempre.

Se activa con JARVIS_MEMORIA_UNICA=1. `memoria_ingesta.py` migra lo viejo.
"""
import os
import re
import sqlite3
import threading
import time

_DB = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs",
                   "memoria_unica.db")
_lock = threading.RLock()
_conn = None
_tiene_fts = True


def _c() -> sqlite3.Connection:
    global _conn, _tiene_fts
    if _conn is not None:
        return _conn
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    _conn = sqlite3.connect(_DB, check_same_thread=False, timeout=10)
    _conn.row_factory = sqlite3.Row
    _conn.execute("""CREATE TABLE IF NOT EXISTS hechos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, tipo TEXT, texto TEXT,
        sujeto TEXT, predicado TEXT, objeto TEXT,
        fuente TEXT, peso REAL DEFAULT 1.0,
        usos INTEGER DEFAULT 0, ultimo_uso REAL DEFAULT 0,
        caduca REAL DEFAULT 0)""")
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_hechos_ts ON hechos(ts)")
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_hechos_suj ON hechos(sujeto)")
    _conn.execute("""CREATE TABLE IF NOT EXISTS entidades (
        nombre TEXT PRIMARY KEY, tipo TEXT,
        primera REAL, ultima REAL, menciones INTEGER DEFAULT 0)""")
    _conn.execute("""CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT)""")
    try:
        _conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS hechos_fts USING fts5(
            texto, content='hechos', content_rowid='id')""")
        _conn.execute("""CREATE TRIGGER IF NOT EXISTS hechos_ai AFTER INSERT ON hechos BEGIN
            INSERT INTO hechos_fts(rowid, texto) VALUES (new.id, new.texto); END""")
        _conn.execute("""CREATE TRIGGER IF NOT EXISTS hechos_ad AFTER DELETE ON hechos BEGIN
            INSERT INTO hechos_fts(hechos_fts, rowid, texto) VALUES ('delete', old.id, old.texto); END""")
        _conn.execute("""CREATE TRIGGER IF NOT EXISTS hechos_au AFTER UPDATE ON hechos BEGIN
            INSERT INTO hechos_fts(hechos_fts, rowid, texto) VALUES ('delete', old.id, old.texto);
            INSERT INTO hechos_fts(rowid, texto) VALUES (new.id, new.texto); END""")
    except sqlite3.OperationalError:
        _tiene_fts = False
    _conn.commit()
    return _conn


# ── escritura ──────────────────────────────────────────────────────────────
def recordar(texto: str, tipo: str = "nota", sujeto: str = "", predicado: str = "",
             objeto: str = "", fuente: str = "jarvis", ts: float = None,
             peso: float = 1.0, caduca_dias: float = 0, entidades: list = None,
             log=print) -> int:
    texto = (texto or "").strip()
    if not texto:
        return 0
    ts = float(ts or time.time())
    caduca = ts + caduca_dias * 86400 if caduca_dias else 0
    try:
        with _lock:
            con = _c()
            # Dedup barato: mismo texto + tipo en las últimas 24 h -> refuerza peso
            prev = con.execute(
                "SELECT id, peso FROM hechos WHERE texto=? AND tipo=? AND ts>? LIMIT 1",
                (texto, tipo, ts - 86400)).fetchone()
            if prev:
                con.execute("UPDATE hechos SET peso=MIN(peso+0.2, 3.0), ts=? WHERE id=?",
                            (ts, prev["id"]))
                con.commit()
                return prev["id"]
            cur = con.execute(
                "INSERT INTO hechos (ts,tipo,texto,sujeto,predicado,objeto,fuente,peso,caduca) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, tipo, texto, sujeto, predicado, objeto, fuente, peso, caduca))
            for e in (entidades or []):
                _tocar_entidad(con, e, ts)
            con.commit()
            return cur.lastrowid or 0
    except Exception as e:
        log(f"[MEMORIA] no pude recordar: {e}")
        return 0


def _tocar_entidad(con, nombre: str, ts: float, tipo: str = ""):
    nombre = (nombre or "").strip()
    if not nombre:
        return
    con.execute(
        "INSERT INTO entidades (nombre,tipo,primera,ultima,menciones) VALUES (?,?,?,?,1) "
        "ON CONFLICT(nombre) DO UPDATE SET ultima=?, menciones=menciones+1, "
        "tipo=COALESCE(NULLIF(tipo,''), excluded.tipo)",
        (nombre, tipo, ts, ts, ts))


# ── lectura ────────────────────────────────────────────────────────────────
def _tokens(s: str) -> str:
    palabras = re.findall(r"[\wáéíóúñ]{3,}", (s or "").lower())
    return " OR ".join(palabras[:8]) if palabras else ""


def recall(consulta: str, k: int = 8, desde: float = None, hasta: float = None,
           tipos: list = None, log=print) -> list:
    try:
        con = _c()
        ahora = time.time()
        filas = []
        with _lock:
            if _tiene_fts and _tokens(consulta):
                q = ("SELECT h.*, bm25(hechos_fts) AS rank FROM hechos_fts "
                     "JOIN hechos h ON h.id=hechos_fts.rowid WHERE hechos_fts MATCH ? ")
                args = [_tokens(consulta)]
            else:
                like = f"%{(consulta or '').strip()}%"
                q = "SELECT h.*, 0 AS rank FROM hechos h WHERE h.texto LIKE ? "
                args = [like]
            if tipos:
                q += " AND h.tipo IN (%s)" % ",".join("?" * len(tipos))
                args += list(tipos)
            if desde:
                q += " AND h.ts>=?"; args.append(desde)
            if hasta:
                q += " AND h.ts<=?"; args.append(hasta)
            q += " LIMIT 60"
            filas = con.execute(q, args).fetchall()

        def puntua(f):
            edad_dias = max(0.0, (ahora - f["ts"]) / 86400)
            recencia = 1.0 / (1.0 + edad_dias / 30.0)
            rank = -(f["rank"] or 0)          # bm25: menor es mejor
            return rank * 0.5 + recencia * 2.0 + (f["peso"] or 1.0) * 0.6
        filas = [f for f in filas if not f["caduca"] or f["caduca"] > ahora]
        filas.sort(key=puntua, reverse=True)
        top = filas[:k]
        if top:
            with _lock:
                _c().executemany(
                    "UPDATE hechos SET usos=usos+1, ultimo_uso=? WHERE id=?",
                    [(ahora, f["id"]) for f in top])
                _c().commit()
        return [dict(f) for f in top]
    except Exception as e:
        log(f"[MEMORIA] recall falló: {e}")
        return []


_REL_DIAS = {"hoy": 0, "ayer": 1, "anteayer": 2, "antier": 2}
_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
           "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}


def _ventana(texto: str):
    """Traduce 'el martes', 'ayer a las 4', 'la semana pasada' a (desde, hasta)."""
    t = (texto or "").lower()
    ahora = time.localtime()
    base = time.time()
    dia_seg = 86400
    for palabra, delta in _REL_DIAS.items():
        if palabra in t:
            inicio = time.mktime((ahora.tm_year, ahora.tm_mon, ahora.tm_mday, 0, 0, 0, 0, 0, -1)) - delta * dia_seg
            return inicio, inicio + dia_seg
    if "semana pasada" in t:
        lun = base - (ahora.tm_wday + 7) * dia_seg
        return lun, lun + 7 * dia_seg
    if "esta semana" in t:
        lun = base - ahora.tm_wday * dia_seg
        return lun, lun + 7 * dia_seg
    for nombre, wd in _SEMANA.items():
        if nombre in t:
            atras = (ahora.tm_wday - wd) % 7 or 7
            inicio = time.mktime((ahora.tm_year, ahora.tm_mon, ahora.tm_mday, 0, 0, 0, 0, 0, -1)) - atras * dia_seg
            return inicio, inicio + dia_seg
    m = re.search(r"hace (\d+) d[ií]as?", t)
    if m:
        d = int(m.group(1))
        inicio = base - d * dia_seg
        return inicio - dia_seg / 2, inicio + dia_seg / 2
    return None, None


def episodico(cuando_texto: str, k: int = 20, log=print) -> list:
    desde, hasta = _ventana(cuando_texto)
    if desde is None:
        return []
    try:
        with _lock:
            filas = _c().execute(
                "SELECT * FROM hechos WHERE ts>=? AND ts<=? ORDER BY ts ASC LIMIT ?",
                (desde, hasta, k)).fetchall()
        return [dict(f) for f in filas]
    except Exception as e:
        log(f"[MEMORIA] episodico falló: {e}")
        return []


def entidad(nombre: str, log=print) -> dict:
    try:
        with _lock:
            con = _c()
            e = con.execute("SELECT * FROM entidades WHERE nombre=? COLLATE NOCASE",
                            (nombre,)).fetchone()
            hechos = con.execute(
                "SELECT * FROM hechos WHERE sujeto=? COLLATE NOCASE OR objeto=? COLLATE NOCASE "
                "OR texto LIKE ? ORDER BY ts DESC LIMIT 12",
                (nombre, nombre, f"%{nombre}%")).fetchall()
        return {"entidad": dict(e) if e else {"nombre": nombre},
                "hechos": [dict(h) for h in hechos]}
    except Exception as e:
        log(f"[MEMORIA] entidad falló: {e}")
        return {}


def olvidar(patron: str, log=print) -> int:
    if not (patron or "").strip():
        return 0
    try:
        with _lock:
            con = _c()
            n = con.execute("DELETE FROM hechos WHERE texto LIKE ?",
                            (f"%{patron.strip()}%",)).rowcount
            con.commit()
        return n
    except Exception as e:
        log(f"[MEMORIA] olvidar falló: {e}")
        return 0


def decaer(dias: float = 60, log=print) -> dict:
    """Baja el peso de lo viejo sin usar y borra lo residual. La memoria deja
    de crecer para siempre."""
    corte = time.time() - dias * 86400
    try:
        with _lock:
            con = _c()
            con.execute("UPDATE hechos SET peso=peso*0.5 "
                        "WHERE ts<? AND usos=0 AND tipo NOT IN ('permanente','preferencia')",
                        (corte,))
            borrados = con.execute(
                "DELETE FROM hechos WHERE peso<0.05 AND tipo NOT IN ('permanente','preferencia')"
            ).rowcount
            con.commit()
        return {"borrados": borrados}
    except Exception as e:
        log(f"[MEMORIA] decaer falló: {e}")
        return {"error": str(e)}


def contexto(texto: str, k: int = 6, log=print) -> str:
    """Bloque para el prompt: mezcla recall temático y, si la frase pregunta por
    tiempo, el episódico de esa ventana."""
    partes = []
    for h in recall(texto, k=k, log=log):
        partes.append(h["texto"][:180])
    if re.search(r"\b(ayer|anteayer|antier|hoy|semana pasada|el (lunes|martes|"
                 r"mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)|hace \d+ d[ií]as)\b",
                 (texto or "").lower()):
        for h in episodico(texto, k=8, log=log):
            marca = time.strftime("%d/%m %H:%M", time.localtime(h["ts"]))
            partes.append(f"({marca}) {h['texto'][:150]}")
    if not partes:
        return ""
    vistos, unicas = set(), []
    for p in partes:
        if p not in vistos:
            vistos.add(p); unicas.append(p)
    return "[Memoria (unificada): " + " | ".join(unicas[:k + 4]) + "]"


def estado() -> dict:
    try:
        with _lock:
            con = _c()
            n = con.execute("SELECT COUNT(*) c FROM hechos").fetchone()["c"]
            ne = con.execute("SELECT COUNT(*) c FROM entidades").fetchone()["c"]
            por_tipo = {r["tipo"]: r["c"] for r in con.execute(
                "SELECT tipo, COUNT(*) c FROM hechos GROUP BY tipo ORDER BY c DESC")}
        return {"hechos": n, "entidades": ne, "fts": _tiene_fts, "por_tipo": por_tipo}
    except Exception as e:
        return {"error": str(e)}


def marca_get(clave: str) -> str:
    with _lock:
        r = _c().execute("SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
    return r["valor"] if r else ""


def marca_set(clave: str, valor: str):
    with _lock:
        _c().execute("INSERT OR REPLACE INTO meta (clave,valor) VALUES (?,?)",
                     (clave, valor))
        _c().commit()
