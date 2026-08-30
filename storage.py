#!/usr/bin/env python3
"""
storage.py — Almacén analítico de CognitionHub (auditoría de comandos +
interacciones etiquetadas con intención/cluster).

Vive en su propia base de datos SQLite (jarvis_cognition.db), separada de
la memoria conversacional principal de jarvis_core.py, para no acoplar la
capa de cognición (Fase 1+2) al esquema del núcleo.
"""
import os
import sqlite3
import threading
import time

import jarvis_redact

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_cognition.db")


class Storage:
    """Persistencia ligera para auditoría de comandos e interacciones etiquetadas."""

    def __init__(self, log=print, db_path=None):
        self.log = log
        self._lock = threading.Lock()
        self._path = db_path or _DB_PATH
        self._conn = sqlite3.connect(self._path, check_same_thread=False, timeout=10)
        self._crear_tablas()

    def _crear_tablas(self):
        with self._lock:
            self._conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, comando TEXT, resultado TEXT, nivel TEXT)""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS interacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, texto TEXT, respuesta TEXT,
                intencion TEXT, cluster TEXT)""")
            self._conn.commit()

    def auditar(self, comando: str, resultado: str, nivel: str):
        """Registra la ejecución (o bloqueo) de un comando con su nivel de riesgo."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        comando = jarvis_redact.redact(comando or "")
        resultado = jarvis_redact.redact(str(resultado or ""))
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO audit_log (timestamp, comando, resultado, nivel) VALUES (?,?,?,?)",
                    (ts, comando[:500], resultado[:1000], nivel))
                self._conn.commit()
        except Exception as e:
            self.log(f"storage: auditar falló: {e}")

    def registrar_interaccion(self, texto: str, respuesta: str, intencion=None, cluster=None):
        """Guarda una interacción ya etiquetada por CognitionHub (intención/cluster)."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        texto = jarvis_redact.redact(texto or "")
        respuesta = jarvis_redact.redact(respuesta or "")
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO interacciones (timestamp, texto, respuesta, intencion, cluster) "
                    "VALUES (?,?,?,?,?)",
                    (ts, texto[:2000], respuesta[:2000], intencion, cluster))
                self._conn.commit()
        except Exception as e:
            self.log(f"storage: registrar_interaccion falló: {e}")

    def ultimas_interacciones(self, limite: int = 50):
        """[(timestamp, texto, intencion, cluster), ...] más recientes primero."""
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT timestamp, texto, intencion, cluster FROM interacciones "
                    "ORDER BY id DESC LIMIT ?", (limite,))
                return cur.fetchall()
        except Exception as e:
            self.log(f"storage: lectura falló: {e}")
            return []

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
