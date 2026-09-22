#!/usr/bin/env python3
"""
jarvis_escucha.py - Escucha continua, conversacion y palabra de activacion
==========================================================================
Hasta ahora, para hablarle a JARVIS desde el PC habia que pulsar Ctrl+Alt+J,
escribir en la web o mandarle un Telegram. La unica escucha «siempre atenta»
vivia en el navegador (Web Speech API de Chrome), o sea que exigia pestaña
abierta, internet y mandar la voz a Google.

Este modulo pone esa escucha en el propio equipo:

  * Palabra de activacion: «Jarvis, apaga el pc» / «Ultron, que hora es».
    Vale al principio, al final («apaga la luz, Jarvis») y con las formas en
    que el reconocedor suele oir el nombre («yarvis», «jarbis»...).
  * Conversacion: cada vez que el asistente termina de hablar -una respuesta,
    un aviso proactivo, un recado- queda abierta una ventana (20 s, o 35 s si
    lo ultimo que dijo fue una pregunta) en la que se le contesta sin decir su
    nombre y se ejecuta lo que se le pida. «Eso es todo» o «gracias, Jarvis»
    la cierran.
  * Voz del señor: con la huella de voz registrada («registra mi voz»), una
    peticion clara dicha por el señor se atiende aunque no diga el nombre ni
    haya conversacion abierta. Las ordenes destructivas siguen exigiendo el
    nombre: «apaga la tele» dicho a un hermano no debe apagar el PC.
  * Interrupcion (barge-in): si el señor habla mientras el asistente esta
    hablando, la voz se corta en el acto. Antes habia que esperar a que
    terminara el parrafo o pulsar un boton.
  * Transcripcion local si hay motor offline (faster-whisper); si no lo hay,
    cae a Google exactamente igual que antes.
  * Un solo microfono por equipo: si la web y el backend cargan cada uno su
    nucleo, solo uno escucha. Con dos, cada orden se ejecutaba dos veces.

El eco de la propia voz se descarta con el detector que ya existe en el nucleo
(_es_eco), y fuera de la conversacion exigir el nombre (o la voz del señor)
evita que una frase suelta de la tele dispare una orden.
"""
import os
import re
import socket
import threading
import time
import unicodedata

try:
    import speech_recognition as sr
    HAY_SR = True
except Exception:
    HAY_SR = False

PALABRAS_POR_DEFECTO = ("jarvis", "ultron")
# Como transcribe el reconocedor el nombre cuando no lo oye bien. Sin esto,
# «yarvis, pon musica» se perdia sin dejar rastro.
VARIANTES = {
    "jarvis": ("jarvis", "yarvis", "jarbis", "yarbis", "harvis", "charvis",
               "jervis", "llarvis", "jarviz", "jarvi"),
    "ultron": ("ultron", "ultrom"),
}
# Ruido tipico del reconocedor cuando no se dijo nada util.
_BASURA = {"", "eh", "ah", "mm", "hm", "gracias", "subtitulos", "subtítulos"}

# Frases que cierran la conversacion: despues vuelve a hacer falta el nombre.
_CIERRE = re.compile(
    r"^(?:(?:vale|ok|bueno|pues|venga)\s+)?(?:muchas\s+)?(?:gracias\s+)?"
    r"(?:eso es todo|es todo|nada mas|hasta luego|hasta despues|adios|descansa|"
    r"puedes descansar|ya te llamo|luego te llamo|ya te aviso|gracias)$")

# Peticiones que solo tienen sentido dirigidas al asistente. Con la voz del
# señor reconocida, bastan para saber que le habla a el aunque no lo nombre.
_PETICION = re.compile(
    r"^(?:(?:oye|eh|por favor)\s+)?(?:"
    r"(?:me\s+)?(?:puedes|podrias)\s|"
    r"(?:necesito|quiero|quisiera)\s+que\s|"
    r"(?:ayudame|echame una mano)\b|"
    r"(?:abre|abreme|pon|ponme|busca|buscame|dime|explicame|reproduce|"
    r"enciende|activa|crea|creame|haz|hazme|calcula|traduce|traduceme|resume|"
    r"resumeme|recuerdame|anota|apunta|apuntame|leeme|muestrame|ensename|"
    r"avisame|cuentame|escribeme|genera|dibuja|analiza|compara|resuelve|"
    r"programa|agenda)\s|"
    r"que hora es|que tiempo hace|que dia es|como se dice\s|que significa\s|"
    r"cuanto (?:es|son)\s)")

# Ordenes que, sin el nombre, podrian ir dirigidas a otra persona y hacen
# dano si se ejecutan por error. Fuera de la conversacion exigen «Jarvis».
_CRITICAS = re.compile(
    r"\b(?:apaga|apagar|apagate|reinicia|reiniciar|borra|borrar|elimina|eliminar|"
    r"formatea|desinstala|cierra|cerrar|suspende|hiberna|bloquea|mata|termina|"
    r"transfiere|compra|comprar|paga|pagar|manda|mandale|envia|enviar|publica)\b")

PUERTO_CANDADO = int(os.getenv("JARVIS_ESCUCHA_PUERTO", "47931"))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Whisper puntua («¿Que hora es?»); Google no. Sin los signos de apertura
    # ni el punto final, las dos transcripciones se tratan igual.
    s = re.sub(r"[¿¡«»\"“”]", "", s)
    return " ".join(s.split()).strip(" .!?")


def _plano(s: str) -> str:
    """Sin puntuacion: para comparar frases palabra a palabra."""
    return " ".join(re.sub(r"[^\w\s]", " ", s or "").split())


def es_cierre(orden: str) -> bool:
    return bool(_CIERRE.match(_plano(_norm(orden))))


def parece_peticion(limpio: str) -> bool:
    """¿Suena a algo que se le pide al asistente (y no es destructivo)?"""
    frase = _plano(_norm(limpio))
    if len(frase.split()) < 2 or _CRITICAS.search(frase):
        return False
    return bool(_PETICION.match(frase + " "))


class EscuchaContinua:
    """Micrófono siempre atento: nombre, conversación, voz del señor y barge-in."""

    def __init__(self, core, log=print, palabras=None, gracia_s: float = 20.0,
                 pregunta_s: float = 35.0):
        self.core = core
        self.log = log
        self.palabras = tuple(p.lower() for p in (palabras or PALABRAS_POR_DEFECTO))
        self.gracia_s = gracia_s
        self.pregunta_s = pregunta_s
        self._patron_nombre = self._compilar_nombres()
        self._stop = threading.Event()
        self._hilo = None
        self._ultima_orden = 0.0
        self._cerrada_hasta = 0.0
        self._rec = None
        self._candado = None
        self._memo_voz = (None, None)
        self._registro = None          # WAV del señor mientras registra su voz
        self._registro_n = 0
        self._registro_hasta = 0.0
        self.activa = False

    def _compilar_nombres(self) -> str:
        formas = []
        for p in self.palabras:
            formas.extend(VARIANTES.get(_norm(p), (_norm(p),)))
        # Las largas primero, para que «jarvis» no se quede en «jarvi».
        formas = sorted(set(formas), key=len, reverse=True)
        return "(?:" + "|".join(re.escape(f) for f in formas) + ")"

    # ── ciclo de vida ───────────────────────────────────────────────────────
    def disponible(self) -> tuple:
        """(bool, motivo). Explica por que no puede escuchar, si no puede."""
        if not HAY_SR:
            return False, "falta la librería SpeechRecognition"
        # Sin PyAudio se graba con la API de Windows (microfono.py).
        import microfono
        return microfono.disponible()

    def start(self) -> tuple:
        ok, motivo = self.disponible()
        if not ok:
            return False, motivo
        if self._hilo and self._hilo.is_alive():
            if not self._stop.is_set():
                return True, "ya estaba escuchando"
            # Se estaba deteniendo: esperar a que suelte el micrófono, o el
            # hilo viejo moriría dejando la escucha apagada tras decir «activa».
            self._hilo.join(timeout=5)
        if not self._tomar_microfono():
            return False, "otra ventana de JARVIS ya está escuchando el micrófono"
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

    def _tomar_microfono(self) -> bool:
        """Un solo oyente por equipo: el primero que reserva el puerto gana.

        Un puerto local y no un archivo de bloqueo porque el sistema lo libera
        solo si el proceso muere; un archivo huérfano dejaría a JARVIS sordo.
        """
        if self._candado is not None:
            return True
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind(("127.0.0.1", PUERTO_CANDADO))
        except OSError:
            s.close()
            return False
        self._candado = s
        return True

    def _soltar_microfono(self):
        s, self._candado = self._candado, None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass

    # ── bucle ───────────────────────────────────────────────────────────────
    def _bucle(self):
        self._rec = sr.Recognizer()
        self._rec.dynamic_energy_threshold = True
        self._rec.energy_threshold = int(os.getenv("JARVIS_ESCUCHA_UMBRAL", "350"))
        # pause_threshold bajo: cortar antes la frase reduce la latencia
        # percibida, que es lo que hace que un asistente parezca despierto.
        self._rec.pause_threshold = 0.6
        try:
            import microfono
            with microfono.abrir() as fuente:
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
            self._soltar_microfono()

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

        # Registrando la huella: lo que diga el señor es muestra, no orden.
        if self._registro is not None and time.time() > self._registro_hasta:
            self._registro = None
            self.log("[ESCUCHA] Registro de voz caducado.")
        if self._registro is not None:
            self._muestra_de_voz(audio, hablando)
            return

        # ── Interrupción: el señor habla mientras el asistente habla ────────
        if hablando:
            try:
                self.core.stop_speaking()
                self.log(f"[ESCUCHA] Interrumpido por el señor: «{limpio[:40]}»")
            except Exception as e:
                self.log(f"[ESCUCHA] No pude interrumpir la voz: {e}")

        orden, via = self._quitar_nombre(limpio), "nombre"
        if orden is None and (hablando or self._en_conversacion()):
            # Sin nombre pero en plena conversación: es la respuesta del señor.
            if hablando and self._voz_coincide(audio) is None and self._es_trozo_mio(limpio):
                return
            if self._voz_coincide(audio, holgura=0.15) is False:
                self.log(f"[ESCUCHA] «{limpio[:40]}» no es la voz del señor; la ignoro.")
                return
            orden, via = limpio, "conversación"
        if orden is None and self._atiende_por_voz() and parece_peticion(limpio):
            # Sin nombre ni conversación: solo si es su voz y suena a petición.
            if self._voz_coincide(audio) is True:
                orden, via = limpio, "voz reconocida"
        if orden is None:
            return

        if not orden:
            # Dijo solo el nombre: abrir la conversación y responder.
            self._ultima_orden = time.time()
            self._decir("Dígame, señor." if self._es_jarvis() else "Habla.")
            return

        if es_cierre(orden):
            self._cerrar_conversacion()
            self.log("[ESCUCHA] Conversación cerrada por el señor.")
            self._decir("A su servicio, señor." if self._es_jarvis() else "Bien.")
            return

        if self._exige_su_voz(orden) and self._voz_coincide(audio) is False:
            self.log(f"[ESCUCHA] Orden crítica con otra voz: «{orden[:40]}»")
            self._decir("Esa orden solo la acepto con la voz del señor.")
            return

        self._ultima_orden = time.time()
        self.log(f"[ESCUCHA] Orden ({via}): «{orden}»")
        threading.Thread(target=self._despachar, args=(orden,), daemon=True).start()

    def _despachar(self, orden: str):
        try:
            self.core.process_text_stream(orden)
        except Exception as e:
            self.log(f"[ESCUCHA] La orden «{orden[:40]}» falló: {e}")
        finally:
            # La ventana de gracia cuenta desde que termina de responder.
            self._ultima_orden = time.time()

    def _quitar_nombre(self, limpio: str):
        """La frase sin el nombre, '' si solo dijo el nombre, o None si no lo dijo."""
        n = self._patron_nombre
        # Al principio: «jarvis, apaga el pc», «oye jarvis que hora es».
        m = re.match(rf"^(?:(?:oye|hey|ok|eh|hola|vale|bueno)[,\s]+)?{n}\b[,:;.!?\s]*(.*)$",
                     limpio)
        if m:
            return m.group(1).strip()
        # Al final: «apaga la luz, jarvis», «que hora es jarvis».
        m = re.match(rf"^(.+?)[,\s]+{n}[.!?\s]*$", limpio)
        if m:
            return m.group(1).strip(" ,")
        # En medio, entre comas (vocativo): «mira, jarvis, pon musica».
        m = re.match(rf"^(.*?),\s*{n}\s*,\s*(.*)$", limpio)
        if m:
            return f"{m.group(1)} {m.group(2)}".strip(" ,")
        return None

    def _extraer_orden(self, limpio: str):
        """Devuelve la orden sin el nombre, '' si solo dijo el nombre, o None."""
        orden = self._quitar_nombre(limpio)
        if orden is not None:
            return orden
        # Conversación abierta: seguir hablando sin repetir el nombre en cada
        # frase, que es como habla la gente de verdad.
        if self._en_conversacion():
            return limpio
        return None

    # ── conversación ────────────────────────────────────────────────────────
    def _en_conversacion(self) -> bool:
        """¿Hay una conversación abierta en la que no hace falta el nombre?

        Se abre con cada orden del señor y también cada vez que el asistente
        termina de hablar, aunque hable por iniciativa propia (un aviso, un
        recado): si pregunta algo, se le contesta sin llamarlo.
        """
        ahora = time.time()
        if self._ultima_orden and ahora - self._ultima_orden < self.gracia_s:
            return True
        fin, dicho = self._ultima_voz()
        if fin and fin > self._cerrada_hasta:
            ventana = self.pregunta_s if dicho.rstrip().endswith("?") else self.gracia_s
            return ahora - fin < ventana
        return False

    def _cerrar_conversacion(self):
        self._ultima_orden = 0.0
        # La despedida que se dice ahora también es voz del asistente: sin
        # este margen, «hasta luego» reabriría la conversación que cierra.
        self._cerrada_hasta = time.time() + 8.0

    def _ultima_voz(self) -> tuple:
        """(cuándo terminó de hablar el asistente, qué dijo)."""
        try:
            if hasattr(self.core, "ultima_voz"):
                fin, dicho = self.core.ultima_voz()
                return float(fin or 0.0), str(dicho or "")
        except Exception:
            pass
        return 0.0, ""

    def _es_trozo_mio(self, limpio: str) -> bool:
        """Mientras hablo, ¿esta frase sin nombre es un trozo de lo que digo?

        El detector de eco del núcleo deja pasar fragmentos cortos para no
        tirar órdenes del señor. Aquí, con la voz sonando, sí se descartan:
        ejecutar mis propias palabras como orden es peor que no oír una.
        """
        frase = _plano(limpio)
        if not frase:
            return False
        try:
            recientes = [_plano(_norm(t)) for t in getattr(self.core, "_tts_hist", [])]
        except Exception:
            return False
        return any(frase in r for r in recientes if r)

    # ── voz del señor ───────────────────────────────────────────────────────
    def _parecido_voz(self, audio):
        """Parecido con la huella del señor; None si no hay huella o no se pudo medir."""
        if self._memo_voz[0] is audio:
            return self._memo_voz[1]
        valor = None
        try:
            import voz_identidad
            if voz_identidad.hay_huella():
                ok, parecido = voz_identidad.verificar(audio.get_wav_data(), log=self.log)
                # verificar() devuelve (True, 0.0) cuando no pudo analizar.
                valor = None if (ok and not parecido) else float(parecido)
        except Exception as e:
            self.log(f"[ESCUCHA] Huella de voz: {e}")
        self._memo_voz = (audio, valor)
        return valor

    def _voz_coincide(self, audio, holgura: float = 0.0):
        """True/False si la voz es (o no) la del señor; None si no se sabe."""
        parecido = self._parecido_voz(audio)
        if parecido is None:
            return None
        try:
            import voz_identidad
            umbral = voz_identidad.UMBRAL
        except Exception:
            umbral = 0.82
        return parecido >= umbral - holgura

    def _exige_su_voz(self, orden: str) -> bool:
        try:
            import voz_identidad
            return voz_identidad.exige_verificacion(self.core, orden)
        except Exception:
            return False

    def _atiende_por_voz(self) -> bool:
        try:
            return (self.core.get_pref("escucha_por_voz") or "1") != "0"
        except Exception:
            return True

    def registrar_voz(self, frases: int = 3) -> tuple:
        """Graba las próximas frases del señor para su huella de voz."""
        if not self.activa:
            return False, "la escucha continua está apagada"
        self._registro = []
        self._registro_n = max(2, frases)
        self._registro_hasta = time.time() + 120
        self.log("[ESCUCHA] Registrando la voz del señor...")
        return True, ""

    def _muestra_de_voz(self, audio, hablando: bool):
        if hablando:
            return                      # sería mi voz, no la suya
        try:
            segundos = len(audio.frame_data) / float(audio.sample_rate * audio.sample_width)
        except Exception:
            segundos = 0.0
        if segundos < 1.2:
            return                      # muy corta para sacar una huella fiable
        self._registro.append(audio.get_wav_data())
        faltan = self._registro_n - len(self._registro)
        if faltan > 0:
            self._decir("Otra más, señor." if faltan > 1 else "La última, señor.")
            return
        muestras, self._registro = self._registro, None
        try:
            import voz_identidad
            self._decir(voz_identidad.registrar(muestras, log=self.log))
        except Exception as e:
            self._decir(f"No pude guardar su voz: {e}")

    # ── utilidades ──────────────────────────────────────────────────────────
    def _es_jarvis(self) -> bool:
        return getattr(self.core, "nombre_agente", "JARVIS") == "JARVIS"

    def _decir(self, texto: str):
        try:
            self.core.tts_queue.put(texto)
        except Exception:
            pass

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
            "pregunta_s": self.pregunta_s,
            "en_conversacion": self._en_conversacion(),
            "por_voz": self._atiende_por_voz(),
            "registrando_voz": self._registro is not None,
        }
