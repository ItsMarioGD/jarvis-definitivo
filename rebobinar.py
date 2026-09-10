#!/usr/bin/env python3
"""
rebobinar.py - Memoria episodica: «¿que estaba haciendo el martes a las cuatro?»
================================================================================
Guarda una captura reducida de la pantalla cada pocos segundos, con la ventana
activa y (si hay OCR) el texto que se veia. Eso permite algo que ninguna otra
pieza del proyecto da: volver atras en el tiempo.

    «¿que estaba haciendo el martes a las cuatro?»
    «¿donde vi ese precio?»
    «recupera lo que escribi y perdi»

Esto es lo mas invasivo de todo el sistema, asi que viene con frenos de verdad
y encendido a mano:

  * APAGADO por defecto. Solo graba tras «empieza a grabar mi pantalla».
  * LISTA DE EXCLUSION. Si el titulo de la ventana activa contiene banco,
    contraseña, incognito, keepass, etc., ese instante NO se guarda.
  * CADUCIDAD. Se borra solo lo mas viejo de `dias` (7 por defecto).
  * BORRADO POR RANGO. «borra la ultima hora» y desaparece.
  * TODO LOCAL. Ni las imagenes ni el texto salen del equipo.

Aun asi, quien active esto debe saber que estara grabando su propia pantalla:
conversaciones, correos y lo que haya delante. Es potentisimo y no es gratis.
"""
import ctypes
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta

RAIZ_DATOS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Rebobinar")
DB = os.path.join(RAIZ_DATOS, "episodios.db")
INTERVALO_S = int(os.getenv("JARVIS_REBOBINAR_INTERVALO", "30"))
DIAS = int(os.getenv("JARVIS_REBOBINAR_DIAS", "7"))
ANCHO = int(os.getenv("JARVIS_REBOBINAR_ANCHO", "1024"))
CALIDAD = int(os.getenv("JARVIS_REBOBINAR_CALIDAD", "45"))

EXCLUIR_TITULOS = [
    "banco", "bank", "contraseñ", "password", "keepass", "bitwarden", "1password",
    "incognito", "inprivate", "privada", "cartera", "wallet", "seed", "clave",
    "tarjeta", "iban", "hacienda", "historia clinica", "medico",
]


def _lock_con():
    os.makedirs(RAIZ_DATOS, exist_ok=True)
    con = sqlite3.connect(DB, check_same_thread=False, timeout=15)
    con.execute("""CREATE TABLE IF NOT EXISTS episodios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, epoca REAL, ruta TEXT, ventana TEXT, texto TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_epoca ON episodios(epoca)")
    con.commit()
    return con


def _ventana_activa() -> str:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        largo = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(hwnd, buffer, largo + 1)
        return buffer.value or ""
    except Exception:
        return ""


def _excluida(titulo: str) -> bool:
    t = (titulo or "").lower()
    return any(p in t for p in EXCLUIR_TITULOS)


def _ocr(ruta: str, log=print) -> str:
    """Texto de la captura, si hay algún motor de OCR disponible."""
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(ruta), lang="spa")[:4000]
    except Exception:
        pass
    try:
        import winocr
        from PIL import Image
        resultado = winocr.recognize_pil_sync(Image.open(ruta), "es-ES")
        return (resultado.get("text") or "")[:4000]
    except Exception:
        return ""


class Rebobinador:
    """Graba la pantalla a intervalos y permite volver atrás en el tiempo."""

    def __init__(self, core=None, log=print, intervalo: int = INTERVALO_S):
        self.core = core
        self.log = log
        self.intervalo = max(5, intervalo)
        self._stop = threading.Event()
        self._hilo = None
        self._lock = threading.RLock()
        self.grabando = False
        self.saltados = 0
        self.guardados = 0

    # ── ciclo ───────────────────────────────────────────────────────────────
    def start(self) -> str:
        if self._hilo and self._hilo.is_alive():
            return "Ya estaba grabando su pantalla, señor."
        try:
            from PIL import ImageGrab  # noqa: F401
        except Exception:
            return "No puedo grabar la pantalla, señor: falta Pillow."
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        self.grabando = True
        try:
            if self.core is not None:
                self.core.set_pref("rebobinar", "1")
        except Exception:
            pass
        return (f"Grabando su pantalla cada {self.intervalo} segundos, señor. "
                f"Guardo {DIAS} días y salto las ventanas sensibles. "
                "Dígame «deja de grabar» cuando quiera.")

    def stop(self) -> str:
        self._stop.set()
        self.grabando = False
        try:
            if self.core is not None:
                self.core.set_pref("rebobinar", "0")
        except Exception:
            pass
        return f"He dejado de grabar, señor. Conservo {self.guardados} instantes de esta sesión."

    def _bucle(self):
        while not self._stop.is_set():
            try:
                self.capturar()
            except Exception as e:
                self.log(f"[REBOBINAR] Fallo capturando: {e}")
            self._stop.wait(self.intervalo)
            if self.guardados % 40 == 0:
                self.purgar()

    # ── captura ─────────────────────────────────────────────────────────────
    def capturar(self, con_ocr: bool = True) -> str:
        ventana = _ventana_activa()
        if _excluida(ventana):
            self.saltados += 1
            self.log(f"[REBOBINAR] Ventana sensible, no guardo: {ventana[:40]}")
            return ""

        from PIL import ImageGrab
        ahora = datetime.now()
        carpeta = os.path.join(RAIZ_DATOS, ahora.strftime("%Y-%m-%d"))
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, ahora.strftime("%H%M%S") + ".jpg")

        imagen = ImageGrab.grab(all_screens=True).convert("RGB")
        if imagen.width > ANCHO:
            alto = int(imagen.height * ANCHO / imagen.width)
            imagen = imagen.resize((ANCHO, alto))
        imagen.save(ruta, "JPEG", quality=CALIDAD, optimize=True)

        texto = _ocr(ruta, log=self.log) if con_ocr else ""
        with self._lock:
            con = _lock_con()
            try:
                con.execute(
                    "INSERT INTO episodios (ts, epoca, ruta, ventana, texto) "
                    "VALUES (?,?,?,?,?)",
                    (ahora.strftime("%Y-%m-%d %H:%M:%S"), time.time(), ruta,
                     ventana[:200], (texto or "").strip()))
                con.commit()
            finally:
                con.close()
        self.guardados += 1
        return ruta

    # ── consulta ────────────────────────────────────────────────────────────
    def momento(self, cuando: datetime, margen_min: int = 10) -> list:
        """Instantes guardados alrededor de una hora concreta."""
        desde = (cuando - timedelta(minutes=margen_min)).timestamp()
        hasta = (cuando + timedelta(minutes=margen_min)).timestamp()
        with self._lock:
            con = _lock_con()
            try:
                return [dict(zip(("ts", "ruta", "ventana", "texto"), fila))
                        for fila in con.execute(
                            "SELECT ts, ruta, ventana, texto FROM episodios "
                            "WHERE epoca BETWEEN ? AND ? ORDER BY epoca LIMIT 12",
                            (desde, hasta)).fetchall()]
            finally:
                con.close()

    def buscar(self, consulta: str, limite: int = 8) -> list:
        """Busca por lo que se veía en pantalla o por la ventana activa."""
        patron = f"%{consulta.strip()}%"
        with self._lock:
            con = _lock_con()
            try:
                return [dict(zip(("ts", "ruta", "ventana", "texto"), fila))
                        for fila in con.execute(
                            "SELECT ts, ruta, ventana, texto FROM episodios "
                            "WHERE texto LIKE ? OR ventana LIKE ? "
                            "ORDER BY epoca DESC LIMIT ?",
                            (patron, patron, limite)).fetchall()]
            finally:
                con.close()

    def relato(self, consulta: str = "", cuando: datetime = None) -> str:
        """Respuesta hablada: qué se estaba haciendo, con hora y ventana."""
        filas = self.momento(cuando) if cuando else self.buscar(consulta)
        if not filas:
            return ("No tengo nada grabado de ese momento, señor. "
                    + ("La grabación está apagada." if not self.grabando else ""))
        ventanas = []
        for f in filas:
            titulo = (f["ventana"] or "").strip()
            if titulo and (not ventanas or ventanas[-1][1] != titulo):
                ventanas.append((f["ts"][11:16], titulo))
        detalle = "; ".join(f"{hora} {titulo[:45]}" for hora, titulo in ventanas[:6])
        return f"Según lo que grabé, señor: {detalle}."

    # ── higiene ─────────────────────────────────────────────────────────────
    def purgar(self, dias: int = DIAS) -> int:
        """Borra lo más viejo que `dias`. Devuelve cuántos instantes se fueron."""
        corte = time.time() - dias * 86400
        borrados = 0
        with self._lock:
            con = _lock_con()
            try:
                filas = con.execute("SELECT id, ruta FROM episodios WHERE epoca < ?",
                                    (corte,)).fetchall()
                for id_, ruta in filas:
                    try:
                        if os.path.exists(ruta):
                            os.unlink(ruta)
                    except Exception:
                        pass
                    con.execute("DELETE FROM episodios WHERE id = ?", (id_,))
                    borrados += 1
                con.commit()
            finally:
                con.close()
        return borrados

    def borrar_rango(self, horas: float = 1.0) -> str:
        """«Borra la última hora»: el botón de arrepentimiento."""
        desde = time.time() - horas * 3600
        borrados = 0
        with self._lock:
            con = _lock_con()
            try:
                filas = con.execute("SELECT id, ruta FROM episodios WHERE epoca >= ?",
                                    (desde,)).fetchall()
                for id_, ruta in filas:
                    try:
                        if os.path.exists(ruta):
                            os.unlink(ruta)
                    except Exception:
                        pass
                    con.execute("DELETE FROM episodios WHERE id = ?", (id_,))
                    borrados += 1
                con.commit()
            finally:
                con.close()
        return f"Borrados {borrados} instantes de las últimas {horas:g} horas, señor."

    def estado(self) -> dict:
        total = tamano = 0
        try:
            with self._lock:
                con = _lock_con()
                try:
                    total = con.execute("SELECT COUNT(*) FROM episodios").fetchone()[0]
                finally:
                    con.close()
            for base, _dirs, ficheros in os.walk(RAIZ_DATOS):
                for f in ficheros:
                    if f.endswith(".jpg"):
                        tamano += os.path.getsize(os.path.join(base, f))
        except Exception:
            pass
        return {"grabando": self.grabando, "instantes": total,
                "megas": round(tamano / (1024 * 1024), 1),
                "intervalo_s": self.intervalo, "dias_conservados": DIAS,
                "saltados_por_privacidad": self.saltados,
                "ocr": bool(_ocr.__doc__)}
