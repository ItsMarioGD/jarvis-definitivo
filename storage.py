#!/usr/bin/env python3
"""
storage.py - Almacen analitico y registro de acciones de JARVIS/ULTRON
======================================================================
Todo lo que el asistente EJECUTA de verdad (comandos del sistema, apagados,
procesos, ordenes del guardian) queda aqui con su resultado real.

Por que existe: hasta ahora las acciones se lanzaban con subprocess.Popen sin
mirar el codigo de salida, asi que un fallo de Windows era indistinguible de un
exito. Cuando el señor decia «esto no funciono» no habia forma de comprobarlo.
Con este registro hay evidencia: que orden se dio, en que comando se tradujo,
si Windows la acepto y cuanto tardo.

Es tambien el sumidero de auditoria que esperaban cognition/shell_ops.py y
cognition/decision_engine.py (ambos llaman a db.auditar(...)); sin este modulo
el hub de cognicion no arrancaba y toda esa capa quedaba muerta.
"""
import os
import sqlite3
import threading
from datetime import datetime, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_POR_DEFECTO = os.path.join(_DIR, "jarvis_audit.db")


class Storage:
    """Registro persistente de acciones, auditoria y eventos."""

    def __init__(self, ruta: str = None, log=print):
        self.log = log
        self.ruta = ruta or os.getenv("JARVIS_AUDIT_DB", RUTA_POR_DEFECTO)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.ruta, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._crear_tablas()

    def _crear_tablas(self):
        with self._lock:
            c = self._conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, agente TEXT, comando TEXT, resultado TEXT, nivel TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS acciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, agente TEXT, origen TEXT, orden TEXT, comando TEXT,
                ok INTEGER, detalle TEXT, ms INTEGER)""")
            c.execute("""CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, agente TEXT, tipo TEXT, gravedad TEXT,
                titulo TEXT, detalle TEXT, datos TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS deshacer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, agente TEXT, tipo TEXT, descripcion TEXT,
                datos TEXT, usado INTEGER DEFAULT 0)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_acciones_ts ON acciones(ts)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_eventos_ts ON eventos(ts)")
            self._conn.commit()

    @staticmethod
    def _ahora():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── escritura ───────────────────────────────────────────────────────────
    def auditar(self, comando: str, resultado: str, nivel: str = "medio",
                agente: str = "JARVIS"):
        """Traza de shell_ops / decision_engine."""
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO audit_log (ts, agente, comando, resultado, nivel) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self._ahora(), agente, str(comando)[:500], str(resultado)[:500], nivel))
                self._conn.commit()
        except Exception as e:
            self.log(f"storage: auditar: {e}")

    def registrar_accion(self, origen: str, orden: str, comando: str, ok: bool,
                         detalle: str = "", ms: int = 0, agente: str = "JARVIS"):
        """Una accion real del asistente y su resultado verificado."""
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO acciones (ts, agente, origen, orden, comando, ok, detalle, ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (self._ahora(), agente, str(origen)[:60], str(orden)[:300],
                     str(comando)[:500], 1 if ok else 0, str(detalle)[:500], int(ms)))
                self._conn.commit()
        except Exception as e:
            self.log(f"storage: registrar_accion: {e}")

    def registrar_evento(self, tipo: str, titulo: str, detalle: str = "",
                         gravedad: str = "info", datos: str = "", agente: str = "JARVIS"):
        """Eventos con valor historico: intrusos, alertas, cambios de estado."""
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO eventos (ts, agente, tipo, gravedad, titulo, detalle, datos) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (self._ahora(), agente, str(tipo)[:40], str(gravedad)[:20],
                     str(titulo)[:200], str(detalle)[:1000], str(datos)[:1000]))
                self._conn.commit()
        except Exception as e:
            self.log(f"storage: registrar_evento: {e}")

    # ── deshacer ────────────────────────────────────────────────────────────
    def anotar_deshacer(self, tipo: str, descripcion: str, datos: str,
                        agente: str = "JARVIS") -> int:
        """Guarda como revertir una accion. Devuelve el id de la entrada."""
        try:
            with self._lock:
                cur = self._conn.execute(
                    "INSERT INTO deshacer (ts, agente, tipo, descripcion, datos) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self._ahora(), agente, str(tipo)[:40], str(descripcion)[:300],
                     str(datos)))
                self._conn.commit()
                return cur.lastrowid or 0
        except Exception as e:
            self.log(f"storage: anotar_deshacer: {e}")
            return 0

    def deshacer_pendientes(self, limite: int = 10, agente: str = ""):
        """Acciones reversibles aun no deshechas, de la mas reciente a la mas vieja."""
        sql = "SELECT * FROM deshacer WHERE usado = 0"
        args = []
        if agente:
            sql += " AND agente = ?"
            args.append(agente)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limite)
        try:
            with self._lock:
                return [dict(r) for r in self._conn.execute(sql, args).fetchall()]
        except Exception as e:
            self.log(f"storage: deshacer_pendientes: {e}")
            return []

    def marcar_deshecho(self, id_entrada: int):
        try:
            with self._lock:
                self._conn.execute("UPDATE deshacer SET usado = 1 WHERE id = ?",
                                   (id_entrada,))
                self._conn.commit()
        except Exception as e:
            self.log(f"storage: marcar_deshecho: {e}")

    # ── lectura ─────────────────────────────────────────────────────────────
    def acciones_recientes(self, limite: int = 20, solo_fallos: bool = False):
        sql = "SELECT * FROM acciones"
        if solo_fallos:
            sql += " WHERE ok = 0"
        sql += " ORDER BY id DESC LIMIT ?"
        try:
            with self._lock:
                return [dict(r) for r in self._conn.execute(sql, (limite,)).fetchall()]
        except Exception as e:
            self.log(f"storage: acciones_recientes: {e}")
            return []

    def eventos_recientes(self, limite: int = 20, tipo: str = "", horas: int = 0):
        sql, args = "SELECT * FROM eventos WHERE 1=1", []
        if tipo:
            sql += " AND tipo = ?"
            args.append(tipo)
        if horas:
            desde = (datetime.now() - timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")
            sql += " AND ts >= ?"
            args.append(desde)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limite)
        try:
            with self._lock:
                return [dict(r) for r in self._conn.execute(sql, args).fetchall()]
        except Exception as e:
            self.log(f"storage: eventos_recientes: {e}")
            return []

    def resumen(self, horas: int = 24) -> dict:
        """Cuantas acciones y cuantas fallaron en la ventana pedida."""
        desde = (datetime.now() - timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._lock:
                fila = self._conn.execute(
                    "SELECT COUNT(*) AS total, SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS fallos "
                    "FROM acciones WHERE ts >= ?", (desde,)).fetchone()
                eventos = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM eventos WHERE ts >= ?", (desde,)).fetchone()
            return {"horas": horas, "acciones": fila["total"] or 0,
                    "fallos": fila["fallos"] or 0, "eventos": eventos["n"] or 0}
        except Exception as e:
            self.log(f"storage: resumen: {e}")
            return {"horas": horas, "acciones": 0, "fallos": 0, "eventos": 0}

    def purgar(self, dias: int = 90) -> int:
        """Borra registros mas viejos que `dias`. Devuelve filas eliminadas."""
        corte = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
        borradas = 0
        try:
            with self._lock:
                for tabla in ("audit_log", "acciones", "eventos", "deshacer"):
                    cur = self._conn.execute(f"DELETE FROM {tabla} WHERE ts < ?", (corte,))
                    borradas += cur.rowcount or 0
                self._conn.commit()
        except Exception as e:
            self.log(f"storage: purgar: {e}")
        return borradas

    def cerrar(self):
        try:
            with self._lock:
                self._conn.close()
        except Exception:
            pass


_almacen = None
_almacen_lock = threading.Lock()


def get_storage(log=print) -> Storage:
    """Instancia unica compartida por nucleo, skills y guardian."""
    global _almacen
    with _almacen_lock:
        if _almacen is None:
            _almacen = Storage(log=log)
        return _almacen
