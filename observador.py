#!/usr/bin/env python3
"""
observador.py - Ojos que miran sin que se lo pidas
==================================================
La vision ya funciona, pero solo cuando el señor dice «mira mi pantalla». Esto
la pone a trabajar sola: cada pocos minutos comprueba si el señor lleva un rato
atascado en lo mismo y, si ve un error, se ofrece.

    «Lleva veinte minutos con el mismo error de compilacion en pantalla.
     Es de la version de la libreria. ¿Se lo miro?»

Es lo unico del proyecto que no hace falta saber pedir.

Como se evita que sea insoportable
----------------------------------
* SOLO SI HAY ATASCO: mira la ventana activa cada minuto, pero solo gasta una
  captura y una llamada al modelo si la misma ventana lleva varias rondas sin
  cambiar. Trabajar tranquilo no dispara nada.
* UNA VEZ POR PROBLEMA: cada aviso se recuerda por su huella; el mismo error no
  se comenta dos veces (ni el mismo dia, salvo que cambie).
* CALLA CUANDO TOCA: en perfil de juego, con el modo privado activo, o si el
  señor dijo que no le moleste, ni siquiera mira.
* NADA SALE DEL EQUIPO: el modelo de vision es local, igual que el resto.
"""
import hashlib
import os
import re
import threading
import time

INTERVALO = int(os.getenv("JARVIS_OBSERVADOR_INTERVALO", "60"))
RONDAS_PARA_ATASCO = int(os.getenv("JARVIS_OBSERVADOR_RONDAS", "4"))   # 4 min
ESPERA_ENTRE_AVISOS = int(os.getenv("JARVIS_OBSERVADOR_ESPERA", "1800"))

PREGUNTA = (
    "Mira esta pantalla. Si hay un ERROR visible (mensaje de error, traza, "
    "excepción, aviso en rojo, prueba fallando), responde en una línea así:\n"
    "ERROR: <qué error es y la causa probable, en español, breve>\n"
    "Si no hay ningún error, responde exactamente: NADA"
)

# Ventanas donde un atasco suele significar algo (editores, terminales, navegador
# con un error). En otras (vídeo, música) mirar no aporta.
_INTERESANTES = ("code", "visual studio", "pycharm", "terminal", "powershell",
                 "cmd", "consola", "idle", "notepad++", "sublime", "vim",
                 "chrome", "edge", "firefox", "excel", "word")


class Observador:
    """Vigila la pantalla y ofrece ayuda cuando ve un atasco."""

    def __init__(self, core, log=print, intervalo: int = INTERVALO):
        self.core = core
        self.log = log
        self.intervalo = max(20, intervalo)
        self._stop = threading.Event()
        self._hilo = None
        self.activo = False
        self._ventana_previa = ""
        self._rondas_igual = 0
        self._avisados = {}          # huella -> momento
        self.ofrecidos = 0
        self.miradas = 0

    # ── ciclo ───────────────────────────────────────────────────────────────
    def disponible(self):
        try:
            import vision
        except Exception as e:
            return False, f"falta el módulo de visión ({e})"
        if not vision.modelo_vision(log=self.log):
            return False, "no hay modelo de visión instalado (ollama pull qwen2.5vl:3b)"
        return True, ""

    def start(self) -> str:
        ok, motivo = self.disponible()
        if not ok:
            return f"No puedo vigilar la pantalla, señor: {motivo}."
        if self._hilo and self._hilo.is_alive():
            return "Ya estoy pendiente de su pantalla, señor."
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        self.activo = True
        try:
            self.core.set_pref("observador", "1")
        except Exception:
            pass
        return ("Estaré pendiente, señor. Si le veo atascado con algo en pantalla, "
                "se lo diré; si no, no le molesto.")

    def stop(self) -> str:
        self._stop.set()
        self.activo = False
        try:
            self.core.set_pref("observador", "0")
        except Exception:
            pass
        return "Dejo de mirar la pantalla, señor."

    def _bucle(self):
        self._stop.wait(30)
        while not self._stop.is_set():
            try:
                self.ronda()
            except Exception as e:
                self.log(f"[OBSERVADOR] {e}")
            self._stop.wait(self.intervalo)

    # ── una ronda ───────────────────────────────────────────────────────────
    def _callado(self) -> bool:
        """¿Toca no molestar ahora?"""
        try:
            import perfiles
            if perfiles.actual() in ("juego", "invitado"):
                return True
        except Exception:
            pass
        try:
            if (self.core.get_pref("avisos_proactivos") or "1") == "0":
                return True
        except Exception:
            pass
        return False

    def ronda(self) -> str:
        if self._callado():
            return ""
        try:
            import rebobinar
            ventana = rebobinar._ventana_activa()
        except Exception:
            ventana = ""
        if not ventana:
            return ""

        if ventana == self._ventana_previa:
            self._rondas_igual += 1
        else:
            self._ventana_previa = ventana
            self._rondas_igual = 1
            return ""

        # Todavía no es un atasco, o la ventana no es de las que interesan.
        if self._rondas_igual < RONDAS_PARA_ATASCO:
            return ""
        if not any(p in ventana.lower() for p in _INTERESANTES):
            return ""

        return self.mirar(ventana)

    def mirar(self, ventana: str = "") -> str:
        """Una captura, una pregunta y, si hay error, un ofrecimiento."""
        import vision
        self.miradas += 1
        ruta = vision.capturar_pantalla(log=self.log)
        if not ruta:
            return ""
        respuesta = vision.preguntar_a_imagen(ruta, PREGUNTA, log=self.log)
        try:
            os.unlink(ruta)
        except Exception:
            pass

        if not respuesta or "NADA" in respuesta.upper()[:20]:
            return ""
        m = re.search(r"ERROR\s*:\s*(.+)", respuesta, re.IGNORECASE | re.DOTALL)
        diagnostico = (m.group(1) if m else respuesta).strip().split("\n")[0][:220]
        if len(diagnostico) < 12:
            return ""

        huella = hashlib.sha256(diagnostico.lower().encode()).hexdigest()[:12]
        ahora = time.time()
        if ahora - self._avisados.get(huella, 0) < ESPERA_ENTRE_AVISOS:
            return ""      # ya se lo dije hace poco: no insistir
        self._avisados[huella] = ahora
        self.ofrecidos += 1

        minutos = int(self._rondas_igual * self.intervalo / 60)
        aviso = (f"Señor, lleva {minutos} minutos con lo mismo en pantalla y veo esto: "
                 f"{diagnostico} ¿Quiero que lo mire?")
        self._ofrecer(aviso, diagnostico, ventana)
        return aviso

    def _ofrecer(self, aviso: str, diagnostico: str, ventana: str):
        try:
            if getattr(self.core, "tts_queue", None) is not None:
                self.core.tts_queue.put(aviso)
        except Exception:
            pass
        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                "observador", diagnostico[:90], f"ventana: {ventana[:80]}",
                gravedad="aviso", agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass
        self.log(f"[OBSERVADOR] {diagnostico[:100]}")

    def estado(self) -> dict:
        ok, motivo = self.disponible()
        return {"activo": bool(self._hilo and self._hilo.is_alive()),
                "puede": ok, "motivo": motivo,
                "intervalo_s": self.intervalo,
                "miradas": self.miradas, "ofrecimientos": self.ofrecidos,
                "ventana_actual": self._ventana_previa[:60],
                "rondas_sin_cambiar": self._rondas_igual}
