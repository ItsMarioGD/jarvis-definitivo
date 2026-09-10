#!/usr/bin/env python3
"""
jarvis_escucha.py - Escucha continua con palabra de activacion e interrupcion
=============================================================================
Hasta ahora, para hablarle a JARVIS desde el PC habia que pulsar Ctrl+Alt+J,
escribir en la web o mandarle un Telegram. La unica escucha «siempre atenta»
vivia en el navegador (Web Speech API de Chrome), o sea que exigia pestaña
abierta, internet y mandar la voz a Google.

Este modulo pone esa escucha en el propio equipo:

  * Palabra de activacion: «Jarvis, apaga el pc» / «Ultron, que hora es».
    Tras responder queda una ventana de gracia (por defecto 15 s) en la que ya
    no hace falta repetir el nombre, que es como habla la gente de verdad.
  * Interrupcion (barge-in): si el señor habla mientras el asistente esta
    hablando, la voz se corta en el acto. Antes habia que esperar a que
    terminara el parrafo o pulsar un boton.
  * Transcripcion local si hay motor offline (faster-whisper); si no lo hay,
    cae a Google exactamente igual que antes.

El eco de la propia voz se descarta con el detector que ya existe en el nucleo
(_es_eco), y ademas exigir el nombre evita que una frase suelta de la tele
dispare una orden.
"""
import os
import re
import threading
import time
import unicodedata

try:
    import speech_recognition as sr
    HAY_SR = True
except Exception:
    HAY_SR = False

PALABRAS_POR_DEFECTO = ("jarvis", "ultron")
# Ruido tipico del reconocedor cuando no se dijo nada util.
_BASURA = {"", "eh", "ah", "mm", "hm", "gracias", "subtitulos", "subtítulos"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


class EscuchaContinua:
    """Micrófono siempre atento, con palabra de activación y barge-in."""

    def __init__(self, core, log=print, palabras=None, gracia_s: float = 15.0):
        self.core = core
        self.log = log
        self.palabras = tuple(p.lower() for p in (palabras or PALABRAS_POR_DEFECTO))
        self.gracia_s = gracia_s
        self._stop = threading.Event()
        self._hilo = None
        self._ultima_orden = 0.0
        self._rec = None
        self.activa = False

    # ── ciclo de vida ───────────────────────────────────────────────────────
    def disponible(self) -> tuple:
        """(bool, motivo). Explica por que no puede escuchar, si no puede."""
        if not HAY_SR:
            return False, "falta la librería SpeechRecognition"
        try:
            import pyaudio  # noqa: F401
        except Exception:
            return False, "falta PyAudio (micrófono)"
        return True, ""

    def start(self) -> tuple:
        ok, motivo = self.disponible()
        if not ok:
            return False, motivo
        if self._hilo and self._hilo.is_alive():
            return True, "ya estaba escuchando"
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        self.activa = True
        self.log(f"[ESCUCHA] Activa. Palabras: {', '.join(self.palabras)}")
        return True, ""

    def stop(self):
        self._stop.set()
        self.activa = False
        self.log("[ESCUCHA] Detenida.")

    # ── bucle ───────────────────────────────────────────────────────────────
    def _bucle(self):
        self._rec = sr.Recognizer()
        self._rec.dynamic_energy_threshold = True
        self._rec.energy_threshold = int(os.getenv("JARVIS_ESCUCHA_UMBRAL", "350"))
        # pause_threshold bajo: cortar antes la frase reduce la latencia
        # percibida, que es lo que hace que un asistente parezca despierto.
        self._rec.pause_threshold = 0.6
        try:
            with sr.Microphone() as fuente:
                self._rec.adjust_for_ambient_noise(fuente, duration=0.8)
                self.log("[ESCUCHA] Ambiente calibrado.")
                while not self._stop.is_set():
                    try:
                        audio = self._rec.listen(fuente, timeout=1.5, phrase_time_limit=8)
                    except sr.WaitTimeoutError:
                        continue
                    except Exception as e:
                        self.log(f"[ESCUCHA] Micrófono: {e}")
                        time.sleep(1.0)
                        continue
                    try:
                        self._procesar_audio(audio)
                    except Exception as e:
                        self.log(f"[ESCUCHA] Fallo procesando: {e}")
        except Exception as e:
            self.log(f"[ESCUCHA] No pude abrir el micrófono: {e}")
        finally:
            self.activa = False

    def _transcribir(self, audio) -> str:
        wav = audio.get_wav_data()
        texto = ""
        try:
            if hasattr(self.core, "_reconocer_local"):
                texto = self.core._reconocer_local(wav) or ""
        except Exception as e:
            self.log(f"[ESCUCHA] Motor local: {e}")
        if not texto:
            try:
                texto = self._rec.recognize_google(audio, language="es-ES")
            except Exception:
                texto = ""
        return texto or ""

    def _procesar_audio(self, audio):
        hablando = self._core_hablando()
        texto = self._transcribir(audio)
        limpio = _norm(texto)
        if limpio in _BASURA or len(limpio) < 2:
            return

        # Nunca reaccionar a la propia voz del asistente.
        try:
            if self.core._es_eco(texto):
                return
        except Exception:
            pass

        # ── Interrupción: el señor habla mientras el asistente habla ────────
        if hablando:
            try:
                self.core.stop_speaking()
                self.log(f"[ESCUCHA] Interrumpido por el señor: «{limpio[:40]}»")
            except Exception as e:
                self.log(f"[ESCUCHA] No pude interrumpir la voz: {e}")

        orden = self._extraer_orden(limpio)
        if orden is None:
            return
        if not orden:
            # Dijo solo el nombre: abrir la ventana de gracia y responder.
            self._ultima_orden = time.time()
            try:
                self.core.tts_queue.put("Dígame, señor."
                                        if getattr(self.core, "nombre_agente", "JARVIS") == "JARVIS"
                                        else "Habla.")
            except Exception:
                pass
            return

        self._ultima_orden = time.time()
        self.log(f"[ESCUCHA] Orden: «{orden}»")
        threading.Thread(target=self._despachar, args=(orden,), daemon=True).start()

    def _despachar(self, orden: str):
        try:
            self.core.process_text_stream(orden)
        except Exception as e:
            self.log(f"[ESCUCHA] La orden «{orden[:40]}» falló: {e}")
        finally:
            # La ventana de gracia cuenta desde que termina de responder.
            self._ultima_orden = time.time()

    def _extraer_orden(self, limpio: str):
        """Devuelve la orden sin el nombre, '' si solo dijo el nombre, o None."""
        for palabra in self.palabras:
            m = re.match(rf"^(?:oye\s+|hey\s+)?{palabra}\b[,:\.\s]*(.*)$", limpio)
            if m:
                return m.group(1).strip()
        # Ventana de gracia tras la última orden: seguir la conversación sin
        # repetir el nombre en cada frase.
        if self._ultima_orden and (time.time() - self._ultima_orden) < self.gracia_s:
            return limpio
        return None

    def _core_hablando(self) -> bool:
        try:
            if hasattr(self.core, "esta_hablando"):
                return bool(self.core.esta_hablando())
        except Exception:
            pass
        return False

    def estado(self) -> dict:
        ok, motivo = self.disponible()
        return {
            "activa": self.activa,
            "disponible": ok,
            "motivo": motivo,
            "palabras": list(self.palabras),
            "gracia_s": self.gracia_s,
        }
