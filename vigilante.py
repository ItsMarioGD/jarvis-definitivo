#!/usr/bin/env python3
"""
vigilante.py - Perro guardian del propio JARVIS/ULTRON
======================================================
El asistente vigila la bateria, el disco y la temperatura del PC, pero nadie
vigilaba al asistente. Si moria el hilo del TTS, se colgaba el motor proactivo
o se caia Ollama, no habia aviso ni reinicio: te enterabas al hablarle y no
obtener respuesta. Y un asistente que se muere en silencio es peor que no
tenerlo, porque para entonces ya contabas con el.

Este modulo late cada 30 segundos y comprueba lo que de verdad tiene que estar
vivo. Cuando algo se cae:

  1. intenta levantarlo (recrear el hilo, relanzar Ollama),
  2. lo registra como evento en storage.py (queda historial de caidas),
  3. avisa por los canales disponibles (voz, Telegram, movil).

Nunca reinicia en bucle: si un subsistema se cae mas de `MAX_REINTENTOS` veces
seguidas se da por perdido y se dice claramente, en vez de gastar la maquina
reintentando cada 30 segundos para siempre.
"""
import os
import threading
import urllib.request

INTERVALO_POR_DEFECTO = int(os.getenv("JARVIS_VIGILANTE_INTERVALO", "30"))
MAX_REINTENTOS = int(os.getenv("JARVIS_VIGILANTE_REINTENTOS", "3"))


class Vigilante:
    """Supervisor de los subsistemas del propio asistente."""

    def __init__(self, core, log=print, intervalo: int = INTERVALO_POR_DEFECTO):
        self.core = core
        self.log = log
        self.intervalo = max(10, intervalo)
        self._stop = threading.Event()
        self._hilo = None
        self._fallos = {}          # subsistema -> reintentos seguidos
        self._ultimo_parte = {}    # subsistema -> "ok" | "caido" | "perdido"
        self._caidas = 0

    # ── ciclo de vida ───────────────────────────────────────────────────────
    def start(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        self.log(f"[VIGILANTE] En guardia (latido cada {self.intervalo}s)")

    def stop(self):
        self._stop.set()

    def _bucle(self):
        # Margen de arranque: el núcleo tarda en levantar todos sus hilos.
        self._stop.wait(20)
        while not self._stop.is_set():
            try:
                self.revisar()
            except Exception as e:
                self.log(f"[VIGILANTE] Fallo revisando: {e}")
            self._stop.wait(self.intervalo)

    # ── comprobaciones ──────────────────────────────────────────────────────
    def revisar(self) -> dict:
        """Una ronda completa. Devuelve el parte de cada subsistema."""
        parte = {}
        for nombre, comprobar, reparar in (
                ("voz", self._voz_viva, self._reparar_voz),
                ("proactivo", self._proactivo_vivo, self._reparar_proactivo),
                ("escucha", self._escucha_viva, self._reparar_escucha),
                ("cerebro", self._cerebro_vivo, self._reparar_cerebro),
                ("memoria", self._memoria_viva, None)):
            try:
                vivo = comprobar()
            except Exception as e:
                self.log(f"[VIGILANTE] {nombre}: comprobación falló: {e}")
                vivo = True   # ante la duda no reiniciamos nada
            if vivo:
                if self._fallos.get(nombre):
                    self.log(f"[VIGILANTE] {nombre} recuperado.")
                self._fallos[nombre] = 0
                parte[nombre] = "ok"
                continue

            intentos = self._fallos.get(nombre, 0) + 1
            self._fallos[nombre] = intentos
            if intentos > MAX_REINTENTOS:
                parte[nombre] = "perdido"
                continue

            self._caidas += 1
            parte[nombre] = "caido"
            self._registrar(nombre, intentos)
            if reparar is not None:
                try:
                    reparar()
                    self.log(f"[VIGILANTE] {nombre}: intento de reparación {intentos}")
                except Exception as e:
                    self.log(f"[VIGILANTE] {nombre}: reparación falló: {e}")
            if intentos == MAX_REINTENTOS:
                self._avisar(f"El subsistema «{nombre}» sigue cayéndose. "
                             "Dejo de reintentar y se lo digo en vez de insistir.")
        self._ultimo_parte = parte
        return parte

    # voz ────────────────────────────────────────────────────────────────────
    def _voz_viva(self) -> bool:
        hilo = getattr(self.core, "tts_thread", None)
        return hilo is None or hilo.is_alive()

    def _reparar_voz(self):
        """Recrea el worker de TTS: sin él el asistente se queda mudo del todo."""
        import queue
        if getattr(self.core, "tts_queue", None) is None:
            self.core.tts_queue = queue.Queue()
        self.core.tts_thread = threading.Thread(target=self.core._tts_worker, daemon=True)
        self.core.tts_thread.start()

    # motor proactivo ────────────────────────────────────────────────────────
    def _proactivo_vivo(self) -> bool:
        motor = getattr(self.core, "proactivo", None)
        if motor is None:
            return True     # apagado a propósito, no es una caída
        hilo = getattr(motor, "_thread", None)
        return hilo is None or hilo.is_alive()

    def _reparar_proactivo(self):
        motor = getattr(self.core, "proactivo", None)
        if motor is not None:
            motor.start()

    # escucha continua ───────────────────────────────────────────────────────
    def _escucha_viva(self) -> bool:
        escucha = getattr(self.core, "escucha", None)
        if escucha is None or not getattr(escucha, "activa", False):
            return True
        hilo = getattr(escucha, "_hilo", None)
        return hilo is None or hilo.is_alive()

    def _reparar_escucha(self):
        escucha = getattr(self.core, "escucha", None)
        if escucha is not None:
            escucha.start()

    # cerebro (Ollama) ───────────────────────────────────────────────────────
    def _cerebro_vivo(self) -> bool:
        base = os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1")
        if "localhost" not in base and "127.0.0.1" not in base:
            return True     # cerebro remoto: no es cosa nuestra levantarlo
        try:
            urllib.request.urlopen(base.replace("/v1", "/api/tags"), timeout=4)
            return True
        except Exception:
            return False

    def _reparar_cerebro(self):
        """Relanza Ollama. Sin cerebro el asistente solo ejecuta habilidades."""
        import ejecutor
        ejecutor.lanzar("ollama serve", origen="vigilante",
                        orden="relanzar el cerebro local", log=self.log)

    # memoria ────────────────────────────────────────────────────────────────
    def _memoria_viva(self) -> bool:
        try:
            from storage import get_storage
            get_storage(log=self.log).resumen(1)
            return True
        except Exception:
            return False

    # ── avisos ──────────────────────────────────────────────────────────────
    def _registrar(self, subsistema: str, intentos: int):
        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                "caida", f"Subsistema «{subsistema}» caído",
                f"intento de recuperación número {intentos}",
                gravedad="alta", agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass

    def _avisar(self, texto: str):
        self.log(f"[VIGILANTE] {texto}")
        try:
            if getattr(self.core, "tts_queue", None) is not None:
                self.core.tts_queue.put(texto)
        except Exception:
            pass
        # Telegram y móvil: los canales que siguen llegando aunque el PC esté
        # a medias y no haya nadie delante de la pantalla.
        try:
            from conectores import Notificador
            Notificador(notify=None, log=self.log).avisar("vigilancia interna", texto)
        except Exception as e:
            self.log(f"[VIGILANTE] No pude avisar por los canales externos: {e}")

    # ── estado ──────────────────────────────────────────────────────────────
    def estado(self) -> dict:
        return {
            "vigilando": bool(self._hilo and self._hilo.is_alive()),
            "intervalo_s": self.intervalo,
            "caidas_totales": self._caidas,
            "parte": dict(self._ultimo_parte),
            "reintentos": {k: v for k, v in self._fallos.items() if v},
        }

    def resumen(self) -> str:
        """Frase para decir en voz alta cuando se pregunta por la salud."""
        parte = self._ultimo_parte or self.revisar()
        malos = [k for k, v in parte.items() if v != "ok"]
        if not malos:
            return (f"Todos mis subsistemas responden, señor. "
                    f"Caídas desde el arranque: {self._caidas}.")
        detalle = ", ".join(f"{k} ({parte[k]})" for k in malos)
        return f"Atención, señor: {detalle}. El resto responde con normalidad."
