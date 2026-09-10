#!/usr/bin/env python3
"""
jarvis_core.py - Nucleo cognitivo de Jarvis
STT + LLM (Qwen3 via Ollama local) + TTS (ElevenLabs) + Telemetria
"""
import base64, json, os, re, sys, time, platform, subprocess, tempfile, threading, queue
import sqlite3, socket

# Nada de lo de abajo es imprescindible para CONVERSAR. Antes iban en un
# import plano y la falta de cualquiera (psutil, por ejemplo, que solo sirve
# para telemetria) hacia que "import jarvis_core" fallara entero y JARVIS no
# respondiera absolutamente nada. Ahora degrada en vez de morir.
FALTANTES = []

try:
    import requests
except Exception as _e:
    requests = None
    FALTANTES.append(f"requests ({_e})")

try:
    import psutil
except Exception as _e:
    psutil = None
    FALTANTES.append(f"psutil ({_e})")

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*a, **k):
        """Sin python-dotenv: parseo minimo del .env para no perder las claves."""
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        try:
            for linea in open(ruta, encoding="utf-8"):
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k_, v_ = linea.split("=", 1)
                    os.environ.setdefault(k_.strip(), v_.strip().strip('"').strip("'"))
        except Exception:
            pass

try:
    from jarvis_skills import SkillsManager
except Exception as _e:
    FALTANTES.append(f"jarvis_skills ({_e})")

    class SkillsManager:  # sin habilidades, pero JARVIS sigue conversando
        def __init__(self, *a, **k):
            pass

        def handle(self, *a, **k):
            return None

try:
    import jarvis_grafo
except Exception as _e:
    FALTANTES.append(f"jarvis_grafo ({_e})")

    class _GrafoNulo:
        def __getattr__(self, _):
            return lambda *a, **k: None
    jarvis_grafo = _GrafoNulo()

try:
    import jarvis_redact
except Exception as _e:
    FALTANTES.append(f"jarvis_redact ({_e})")

    class _RedactNulo:
        @staticmethod
        def redact(texto, *a, **k):
            return texto

        def __getattr__(self, _):
            return lambda *a, **k: None
    jarvis_redact = _RedactNulo()

load_dotenv()

if FALTANTES:
    print("[JARVIS] Arranco en modo degradado, falta: " + "; ".join(FALTANTES))

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from httpx import Timeout
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    import pygame
    pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False


# Apps que Jarvis puede abrir en Windows con comando natural
APP_MAP = {
    "notepad": "notepad.exe",     "bloc de notas": "notepad.exe",
    "calculadora": "calc.exe",    "calculator": "calc.exe",
    "chrome": "chrome",           "google": "chrome",
    "explorer": "explorer.exe",   "archivos": "explorer.exe",
    "cmd": "cmd.exe",             "terminal": "cmd.exe",
    "paint": "mspaint.exe",
    "spotify": "spotify",
    "vscode": "code",             "visual studio code": "code",
    "word": "winword",            "excel": "excel",
}

# Palabras de acción para partir consultas compuestas (isair planner)
ACCIONES = {
    "clima", "temperatura", "musica", "cancion", "captura", "pantalla", "nota",
    "recordatorio", "alarma", "temporizador", "gasto", "gastos", "agenda", "tarea",
    "whatsapp", "correo", "email", "video", "descarga", "descargar", "receta",
    "noticias", "brillo", "volumen", "silencio", "spotify", "apaga", "apagate",
    "reinicia", "reiniciate", "bloquea", "abre", "cierra", "busca", "investiga",
    "traduce", "resume", "resumen", "calcula", "calculadora", "convierte",
    "bateria", "red", "wifi", "proceso", "procesos", "camara", "foto", "selfie",
    "envia", "enviar", "manda", "imprime", "papelera", "organiza", "organizar",
    "limpia", "limpieza", "backup", "respaldo", "escanea", "diagnostica",
    "salud", "informe", "compra", "vigila", "donde esta", "modo gaming",
    "modo noche", "modo invitado", "despiertame", "suspende", "hiberna",
    "mensaje", "contacto", "arduino", "domotica", "luz", "luces", "radio",
    "podcast", "pomodoro", "gif", "pdf", "codigo", "commit", "git", "tests",
    "docker", "contenedor", "repos", "changelog", "snippet", "telefono",
    "movil", "tv", "chromecast", "duplicados", "libera espacio", "cofre",
    "portapapeles", "historial", "ejercicio", "rutina", "reunion", "presets",
    "despertador", "perfil", "animo", "dictado", "informe matutino",
    # Estado del equipo. Sin estas, «sube el volumen y dime cuanta RAM usas»
    # no se partia en dos ordenes y JARVIS solo atendia la primera mitad.
    "ram", "memoria", "cpu", "disco", "espacio", "rendimiento", "recursos",
}


class JarvisCore:
    """Motor principal: STT + LLM + TTS + habilidades del sistema."""

    def __log_both(self, level: str, message: str):
        """Escribe una línea tanto en el callback de UI como en el log de disco."""
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{ts}] [{level}] {message}"
        self.log(message)
        if self._log_file:
            try:
                self._log_file.write(line + "\n")
                self._log_file.flush()
            except OSError:
                # Si el disco está lleno o el fichero está bloqueado, no
                # queremos matar el bucle principal por un fallo de logging.
                pass

    def log_info(self, message: str):
        self.__log_both("INFO", message)

    def log_warn(self, message: str):
        self.__log_both("WARN", message)

    def log_error(self, message: str):
        self.__log_both("ERROR", message)

    def __init__(self, log_callback=print, hotkey_callback=None):
        self.log = log_callback or print
        self.hotkey_callback = hotkey_callback

        # Doble vía del log: consola/UI (callback) y fichero persistente.
        # Permite revisar qué pasó incluso tras cerrar la ventana.
        self._log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_log")
        os.makedirs(self._log_dir, exist_ok=True)
        self._log_path = os.path.join(self._log_dir, "session.log")
        self._log_file = None
        try:
            self._log_file = open(self._log_path, "a", encoding="utf-8")
        except OSError as e:
            # Si no se puede abrir el log, no interrumpimos el arranque.
            print(f"No se pudo abrir el log persistente: {e}")

        self.elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id       = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.base_url       = os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1")
        self.api_key        = os.getenv("QWEN_API_KEY", "ollama")
        self.model          = os.getenv("QWEN_MODEL", "qwen3:8b")
        # Cerebro principal en la nube: Kimi K3 (Moonshot). 1M de contexto,
        # visión nativa, tool-calling. Deja la clave en la variable de entorno
        # MOONSHOT_API_KEY (o pégala en Prefs/cerebro.json -> proveedores[0].clave).
        # Sin clave, JARVIS cae solo al proveedor local (Ollama) y no se rompe.
        self.moonshot_key   = os.getenv("sk-BlCBmliVMaAlmh3G9aWjVbY9vklGCbhCwaWjV03zijpCW5PV", "").strip()
        self.tts_fallback   = os.getenv("JARVIS_TTS_FALLBACK", "windows").strip().lower()
        # Silencio de la voz local de Windows. Se puede alternar en caliente
        # ("silencia la voz de Windows") y sobrevive al reinicio, porque con
        # ElevenLabs/Piper y el navegador hablando a la vez se oyen dos voces.
        self._voz_windows_silenciada = None  # se resuelve tras init_memory()
        self._elevenlabs_disabled_until = 0.0
        self._elevenlabs_failure_reason = ""

        # Cerebro: proveedores con fallback (estilo Free Claude Code)
        self._cerebro_path = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                          "Prefs", "cerebro.json")
        self._cerebro = self._cerebro_leer()
        self._cerebro_activo = ""
        self._llm_ultimo = 0.0
        self._llm_hora = []

        self.log(f"LLM -> {self.model} @ {self.base_url}")

        self.llm = None
        if HAS_OPENAI:
            try:
                kwargs = {"base_url": self.base_url, "api_key": self.api_key}
                if HAS_HTTPX:
                    kwargs["timeout"] = Timeout(60.0, connect=10.0)
                self.llm = OpenAI(**kwargs)
            except Exception as e:
                # Una base_url mal formada no puede dejar mudo al asistente.
                self.log(f"No pude crear el cliente LLM ({e}); sigo sin el.")
        else:
            self.log("openai no disponible - instala con pip install openai")

        if HAS_SR:
            self.rec = sr.Recognizer()
            self.rec.energy_threshold = 300
            self.rec.dynamic_energy_threshold = True
        else:
            self.rec = None

        sys_info = f"{platform.system()} {platform.version()[:40]}"
        self.system_prompt = (
            "Eres Jarvis, mayordomo personal inteligente, discreto y altamente competente. "
            "El usuario es tu señor y tu maxima autoridad: tratalo siempre de usted, "
            "llamalo 'señor' de manera natural al menos una vez en cada respuesta y "
            "cumple sus instrucciones con profesionalismo. "
            "Caracter: sereno, elegante, proactivo, levemente sarcastico solo cuando "
            "sea apropiado, y siempre respetuoso. "
            "Responde SIEMPRE en espanol. "
            "Respuestas concisas (máx 3 oraciones) salvo que pidan más detalle. "
            "Sin Markdown. Sin asteriscos. Sin listas con guiones. "
            # Qwen3 razona antes de contestar y, si no se le dice nada, vuelca
            # el desarrollo entero (con LaTeX incluido) en la respuesta hablada.
            "No muestres el desarrollo de tus cálculos ni tu razonamiento: "
            "da el resultado y, como mucho, una frase de justificación. "
            "Nada de fórmulas escritas ni notación matemática. "
            "Si el usuario pide abrir una aplicación, incluye exactamente [OPEN:nombre_app] en tu respuesta. "
            f"Sistema: {sys_info}. "
            f"Fecha/hora: {time.strftime('%A %d de %B de %Y, %H:%M')}."
        )
        # Soft skills (Fase 2): se inyectan al prompt base solo si el módulo
        # de personalidad está disponible (nunca rompe el arranque).
        try:
            from cognition.persona import PROMPT_DECISIONES, PROMPT_CREATIVIDAD
            self.system_prompt = self.system_prompt + " " + PROMPT_DECISIONES + " " + PROMPT_CREATIVIDAD
        except Exception:
            pass
        self.init_memory()

        # Lock para serializar todas las escrituras a SQLite. Sin lock, los
        # hilos UDP, TTS y LLM pueden colisionar al cerrar el cursor.
        self._db_lock = threading.RLock()

        # Worker de TTS asincrono. Este bloque colgaba tras el return de la
        # property signal_processor, o sea que era codigo muerto: tts_queue no
        # existia y cualquier cosa que hablara reventaba con AttributeError.
        # Va aqui porque SkillsManager recibe notify=... y la usa.
        self.tts_queue = queue.Queue()
        self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.tts_thread.start()

        # Habilidades del sistema (Sprint 2): respuestas instantáneas sin LLM
        try:
            self.skills = SkillsManager(
                log=self.log,
                notify=lambda msg: self.tts_queue.put(msg),
                remember=self.add_reminder,
            )
        except Exception as e:
            self.log(f"Habilidades desactivadas: {e}")
            self.skills = None

        # Agencia de especialistas (agency-agents): modos activables por voz/texto
        try:
            from agentes_ia import AgentesIA as _AgentesIA
            self.agentes_ia = _AgentesIA(self, log=self.log)
        except Exception as _e_ag:
            self.agentes_ia = None
            self.log(f"[JARVIS] Agencia de agentes no disponible: {_e_ag}")

        # Bot de Telegram: arranca en proceso separado si hay token configurado.
        # JARVIS_TELEGRAM_CHILD lo pone telegram_bot.py: sin esa marca el bot
        # creaba un JarvisCore que volvia a lanzar otro bot en cascada.
        try:
            self._lanzar_bot_telegram()
        except Exception as e:
            self.log(f"No se pudo lanzar el bot de Telegram: {e}")

        # Módulos cognitivos (Fase 1+2): hub diferido, no penaliza el arranque.
        # Solo se instancia bajo demanda (ML, señales, clustering, shell seguro,
        # decisiones, storage analítico) — ver cognition/__init__.py
        try:
            from cognition import CognitionHub
            from storage import Storage
            self.cognition = CognitionHub(
                log=self.log,
                db=Storage(log=self.log),
            )
        except Exception as e:
            self.log(f"Cognición desactivada: {e}")
            self.cognition = None

        # Mem0 Store (memoria tripartita: vector + KV + graph) - carga perezosa
        self._mem0 = None
        self._mem0_error = None

        # Signal Processor (paralingüística: estrés, fatiga, emoción) - carga perezosa
        self._signal_processor = None
        self._signal_error = None

        # Control total del PC (Sprint "Más poder"): sistema, UI, archivos,
        # integración profunda y tareas programadas. Se consulta después de
        # skills y antes del LLM. Safe=False: en producción ejecuta de verdad.
        try:
            from pc_control import PCControl
            self.pc = PCControl(
                log=self.log,
                notify=lambda msg: self.tts_queue.put(msg),
                get_pref=self.get_pref,
                set_pref=self.set_pref,
                safe=False,
            )
        except Exception as e:
            self.log(f"Control del PC desactivado: {e}")
            self.pc = None

        # Mensajería (WhatsApp + Gmail): tercer despachador, tras skills y pc
        try:
            from mensajeria import Mensajeria
            self.msg = Mensajeria(
                log=self.log,
                notify=lambda msg: self.tts_queue.put(msg),
                get_pref=self.get_pref,
                set_pref=self.set_pref,
                safe=False,
            )
        except Exception as e:
            self.log(f"Mensajería desactivada: {e}")
            self.msg = None

        # Conectores a servicios externos (Google Calendar y los demas
        # servidores MCP). Cuarto despachador, tras skills / pc / mensajeria.
        try:
            from conectores import Conectores
            self.conectores = Conectores(
                log=self.log,
                notify=lambda msg: self.tts_queue.put(msg),
                safe=False,
            )
            listos = [n for n, ok in self.conectores.estado().items() if ok]
            self.log(f"Conectores activos: {', '.join(listos) or 'ninguno respondiendo aún'}")
        except Exception as e:
            self.log(f"Conectores desactivados: {e}")
            self.conectores = None

        self.history = [{"role": "system", "content": self.system_prompt}]
        # Ninguna de estas dos es necesaria para contestar: que un historial
        # corrupto o un puerto UDP ocupado no impidan usar JARVIS.
        try:
            self.load_memory_context()
        except Exception as e:
            self.log(f"No pude cargar el contexto de memoria: {e}")
        try:
            self.start_udp_listener()
        except Exception as e:
            self.log(f"Listener UDP desactivado: {e}")

        # Contexto rodante (isair transcript buffer): últimas 3 interacciones
        self._contexto = []
        # Estado del señor inferido de su propia voz. El SignalProcessor ya
        # calculaba estrés y fatiga en cada frase y el resultado se tiraba a la
        # basura (había un TODO en listen()). Ahora gobierna el ritmo de la voz,
        # la estabilidad del TTS y las sugerencias de descanso.
        self._estado_animo = {"estres": 0.0, "fatiga": 0.0, "arousal": 0.0,
                              "valencia": 0.0, "confianza": 0.0, "ts": 0.0}
        # Herramienta que espera un «confirma» del señor antes de ejecutarse.
        self._tool_pendiente = None
        # Motor de dictado local: None = sin probar, False = no disponible.
        self._stt_local = None
        self._tts_rate = 0             # velocidad de la voz de Windows (-10..10)
        self._tts_estabilidad = 0.5    # estabilidad de ElevenLabs
        self._ultimo_consejo_descanso = 0.0
        # Historial TTS para el detector de eco (isair echo_detection)
        self._tts_hist = []
        # Calentar el modelo local para respuestas rápidas (isair warm_up) y
        # mantenerlo cargado: Ollama lo descarga a los 5 minutos y la primera
        # pregunta tras una pausa pagaba 2,2 s de recarga.
        threading.Thread(target=self._warmup_ollama, daemon=True).start()
        threading.Thread(target=self._mantener_caliente, daemon=True).start()
        # Y el dictado: cargarlo aquí evita 6,3 s en la primera frase hablada.
        threading.Thread(target=self._precargar_dictado, daemon=True).start()

        # Motor proactivo (jarvis_proactive.py): estaba escrito entero y no lo
        # instanciaba nadie, así que JARVIS solo reaccionaba. Vigila batería,
        # temperatura, disco, red, calendario, seguridad y actualizaciones.
        # Se apaga con la preferencia «avisos_proactivos» o JARVIS_PROACTIVO=0.
        self.proactivo = None
        try:
            if os.getenv("JARVIS_PROACTIVO", "1") != "0" and                     (self.get_pref("avisos_proactivos") or "1") != "0":
                from jarvis_proactive import ProactiveEngine
                intervalo = int(os.getenv("JARVIS_PROACTIVO_INTERVALO", "120"))
                self.proactivo = ProactiveEngine(self, log=self.log, interval=intervalo)
                self.proactivo.start()
            else:
                self.log("[PROACTIVE] Desactivado por preferencia del señor.")
        except Exception as e:
            self.log(f"Motor proactivo desactivado: {e}")

        # Escucha continua con palabra de activación (jarvis_escucha.py).
        # Es opt-in: necesita micrófono libre, así que solo arranca si el señor
        # lo pidió («activa la escucha continua») o con JARVIS_ESCUCHA=1.
        self.escucha = None
        try:
            from jarvis_escucha import EscuchaContinua
            palabras = (os.getenv("JARVIS_PALABRA_ACTIVACION", "").strip() or
                        ("ultron,jarvis" if getattr(self, "nombre_agente", "JARVIS") == "ULTRON"
                         else "jarvis")).split(",")
            self.escucha = EscuchaContinua(self, log=self.log,
                                           palabras=[p.strip() for p in palabras if p.strip()])
            if os.getenv("JARVIS_ESCUCHA", "").strip() == "1" or \
                    (self.get_pref("escucha_continua") or "0") == "1":
                ok, motivo = self.escucha.start()
                if not ok:
                    self.log(f"[ESCUCHA] No pude activarla: {motivo}")
        except Exception as e:
            self.log(f"Escucha continua no disponible: {e}")

        # Mantenimiento de memoria: sin esto las bases solo crecían.
        threading.Thread(target=self._mantenimiento_periodico, daemon=True).start()

        # Enjambre de especialistas y turno de noche: ambos opt-in, porque uno
        # habla solo y el otro trabaja de madrugada.
        self.enjambre = None
        self.nocturno = None
        try:
            if (self.get_pref("enjambre") or "0") == "1":
                from enjambre import Enjambre
                self.enjambre = Enjambre(self, log=self.log)
                self.enjambre.start()
        except Exception as e:
            self.log(f"Enjambre no disponible: {e}")
        try:
            from modo_nocturno import ModoNocturno
            self.nocturno = ModoNocturno(self, log=self.log)
            hora = (self.get_pref("modo_nocturno_hora") or "").strip()
            if hora:
                self.nocturno.programar(hora)
        except Exception as e:
            self.log(f"Turno de noche no disponible: {e}")

        # Perro guardián del propio asistente (vigilante.py): vigila que sigan
        # vivos el hilo de voz, el motor proactivo, la escucha y el cerebro.
        # Hasta ahora nadie vigilaba al vigilante de la casa.
        self.vigilante = None
        try:
            if os.getenv("JARVIS_VIGILANTE", "1") != "0":
                from vigilante import Vigilante
                self.vigilante = Vigilante(self, log=self.log)
                self.vigilante.start()
        except Exception as e:
            self.log(f"Vigilante no disponible: {e}")

        self.hotkey_proc = None
        if os.path.exists("jarvis_hotkey.exe"):
            try:
                self.hotkey_proc = subprocess.Popen(["jarvis_hotkey.exe"], creationflags=0x08000000)
                self.log("Microservicio C++ Hotkey (Ctrl+Alt+J) iniciado en segundo plano.")
            except Exception as e:
                self.log(f"Error lanzando Hotkey C++: {e}")

        # Saludo de arranque: si el señor activó el arranque automático,
        # Jarvis se presenta por voz cuando el sistema termina de cargar.
        # (Tambien estaba en el bloque muerto: nunca llegaba a ejecutarse.)
        threading.Thread(target=self._saludo_arranque, daemon=True).start()

    @property
    def mem0(self):
        if self._mem0 is None and self._mem0_error is None:
            try:
                from cognition.mem0_store import get_mem0
                self._mem0 = get_mem0(log=self.log)
                self.log("[MEM0] Store conectado")
            except Exception as e:
                self._mem0_error = e
                self.log(f"Mem0 no disponible: {e}")
        return self._mem0

    @property
    def signal_processor(self):
        if self._signal_processor is None and self._signal_error is None:
            try:
                from cognition.signal_processor import SignalProcessor
                self._signal_processor = SignalProcessor(log=self.log)
                self.log("[SIGNAL] Procesador paralingüístico listo")
            except Exception as e:
                self._signal_error = e
                self.log(f"SignalProcessor no disponible: {e}")
        return self._signal_processor

    def _lanzar_bot_telegram(self):
        """Arranca telegram_bot.py como proceso aparte si hay token guardado.

        Usa jarvis_config.TELEGRAM_JSON (resuelve Descargas/Downloads) y
        sys.executable: 'pythonw' solo existe en Windows y fuera de ahi el
        arranque fallaba en silencio dejando el bot sin levantar.
        """
        if os.getenv("JARVIS_TELEGRAM_CHILD") == "1":
            return  # ya estamos dentro del propio bot
        try:
            import jarvis_config
            tg_cfg = jarvis_config.TELEGRAM_JSON
        except Exception:
            tg_cfg = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                  "Prefs", "telegram.json")
        token = ""
        try:
            if os.path.exists(tg_cfg):
                token = (json.load(open(tg_cfg, encoding="utf-8-sig")).get("token") or "").strip()
        except Exception:
            token = ""
        token = token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return
        raiz = os.path.dirname(os.path.abspath(__file__))
        bot_path = os.path.join(raiz, "telegram_bot.py")
        if not os.path.exists(bot_path):
            self.log("telegram_bot.py no esta en el proyecto; no lanzo el bot.")
            return
        import subprocess as _sp
        exe = sys.executable or "python"
        kwargs = {"cwd": raiz, "env": {**os.environ, "JARVIS_TELEGRAM_CHILD": "1"}}
        if os.name == "nt":
            pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            if os.path.exists(pythonw):
                exe = pythonw
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        _sp.Popen([exe, bot_path], **kwargs)
        self.log("Bot de Telegram lanzado en segundo plano "
                 f"(log en {os.path.join(raiz, 'jarvis_log', 'telegram_bot.log')}).")

    def _saludo_arranque(self):
        """Saludo por voz al encender el PC (si el señor lo activó)."""
        try:
            time.sleep(6)  # esperar a que el servidor web y el TTS estén listos
            if self.get_pref("saludar_al_arranque") != "1":
                return
            hoy = time.strftime("%Y-%m-%d")
            if self.get_pref(f"saludo_{hoy}"):
                return  # ya saludó hoy
            franja = "buenos días" if 6 <= time.localtime().tm_hour < 12 else \
                     ("buenas tardes" if time.localtime().tm_hour < 20 else "buenas noches")
            fecha = time.strftime("%A %d de %B")
            saludo = (f"{franja.capitalize()}, señor. Soy Jarvis y estoy en línea. "
                      f"Hoy es {fecha} y todos los sistemas operativos.")
            # Nombre del señor aprendido en preferencias, si existe
            try:
                prefs = self.skills._pref_leer() if self.skills is not None else {}
                nombre = (prefs.get("nombre") or "").strip()
                if nombre:
                    saludo = (f"{franja.capitalize()}, señor {nombre}. Soy Jarvis y estoy en línea. "
                              f"Hoy es {fecha} y todos los sistemas operativos.")
            except Exception:
                pass
            # si hay rutinas detectadas, mencionar la más habitual de la franja
            try:
                if self.pc is not None:
                    h = time.localtime().tm_hour
                    franja_n = ("madrugada" if h < 6 else "mañana" if h < 12
                                else "tarde" if h < 18 else "noche")
                    r = self.pc._rutinas("detecta mis rutinas")
                    if r and "detecté" in r:
                        saludo += " He notado que " + r.split("detecté sus rutinas: ", 1)[-1].split(".")[0] + "."
            except Exception:
                pass
            self.tts_queue.put(saludo)
            self.set_pref(f"saludo_{hoy}", "1")
            self.log("Saludo de arranque emitido")
        except Exception as e:
            self.log(f"Saludo de arranque falló: {e}")

    def _tts_worker(self):
        while True:
            text = self.tts_queue.get()
            if text is None:
                self.tts_queue.task_done()
                break
            try:
                if text.strip():
                    self.synthesize_and_play(text)
            except Exception as e:
                # Un fallo del proveedor de voz nunca debe matar el worker ni impedir
                # que la interfaz muestre las respuestas posteriores.
                self.log(f"Error inesperado de audio: {e}")
            finally:
                self.tts_queue.task_done()

    def shutdown(self):
        try:
            if getattr(self, "enjambre", None) is not None:
                self.enjambre.stop()
            if getattr(self, "nocturno", None) is not None:
                self.nocturno.cancelar()
        except Exception as e:
            self.log(f"No pude detener el enjambre: {e}")
        try:
            if getattr(self, "vigilante", None) is not None:
                self.vigilante.stop()
        except Exception as e:
            self.log(f"No pude detener el vigilante: {e}")
        try:
            if getattr(self, "escucha", None) is not None:
                self.escucha.stop()
        except Exception as e:
            self.log(f"No pude detener la escucha continua: {e}")
        try:
            if getattr(self, "proactivo", None) is not None:
                self.proactivo.stop()
        except Exception as e:
            self.log(f"No pude detener el motor proactivo: {e}")
        if self.pc is not None:
            try:
                self.pc.shutdown()
            except Exception:
                pass
        if self.hotkey_proc:
            try:
                self.hotkey_proc.terminate()
            except:
                pass
        if self._log_file:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    def init_memory(self):
        # timeout=10 hace que SQLite espere si otro hilo tiene el lock en lugar
        # de fallar inmediatamente. El RLock externo evita la mayoría de las
        # colisiones, pero el timeout es una red de seguridad.
        # Ruta ABSOLUTA: con "jarvis_memory.db" a secas, arrancar desde un
        # acceso directo de Windows (cwd = Escritorio o System32) hacia que
        # SQLite fallara con «unable to open database file» y el nucleo entero
        # no cargaba. Ademas cada proceso abria una base distinta.
        try:
            import jarvis_config
            candidatas = jarvis_config.rutas_db("jarvis_memory.db")
        except Exception:
            candidatas = [os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "jarvis_memory.db")]
        self.conn = None
        fallos = []
        for ruta in candidatas:
            try:
                conn = sqlite3.connect(ruta, check_same_thread=False, timeout=10)
                conn.execute("SELECT 1")  # el connect es perezoso: forzamos la apertura
                self.conn = conn
                self.db_path = ruta
                break
            except Exception as e:
                fallos.append(f"{ruta}: {e}")
                # Un -wal/-shm huerfano (de un arranque como administrador)
                # impide abrir una base por lo demas sana; probamos la siguiente.
        if self.conn is None:
            raise sqlite3.OperationalError(
                "No pude abrir ninguna base de memoria. Intentos -> " + " | ".join(fallos)
                + ". Define JARVIS_DB_DIR con una carpeta escribible.")
        if candidatas and self.db_path != candidatas[0]:
            self.log(f"AVISO: no pude usar {candidatas[0]} ({fallos[0].split(': ', 1)[-1]}); "
                     f"uso {self.db_path}")
        self.log(f"Memoria en {self.db_path}")
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS interactions
                               (id INTEGER PRIMARY KEY, timestamp TEXT, role TEXT, content TEXT)''')
        # Tabla separada para medios (imágenes, video, 3D). No contamina el
        # contexto conversacional que se inyecta al LLM.
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS media_history
                               (id INTEGER PRIMARY KEY, timestamp TEXT,
                                media_type TEXT, prompt TEXT, path TEXT)''')
        # Preferencias aprendidas del señor (clave-valor) y recordatorios activos
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS user_prefs
                               (key TEXT PRIMARY KEY, value TEXT, timestamp TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS reminders
                               (id INTEGER PRIMARY KEY, timestamp TEXT,
                                due TEXT, text TEXT, done INTEGER DEFAULT 0)''')
        self.conn.commit()

    def load_memory_context(self):
        with self._db_lock:
            self.cursor.execute("SELECT role, content FROM interactions ORDER BY id DESC LIMIT 8")
            rows = self.cursor.fetchall()
        # Inyectar preferencias aprendidas y recordatorios activos como contexto
        prefs_ctx = self.get_prefs_context()
        if prefs_ctx:
            self.history.append({"role": "system", "content": prefs_ctx})
        rem_ctx = self.get_reminders_context()
        if rem_ctx:
            self.history.append({"role": "system", "content": rem_ctx})
        if rows:
            self.history.append({"role": "system", "content": "[Contexto recuperado de memoria anterior]"})
            # Los rows vienen DESC; invertimos para reconstruir orden cronológico.
            for role, content in reversed(rows):
                # Defensa: si por migración antigua aparece un role desconocido,
                # lo normalizamos a 'user' para no romper el formato del LLM.
                if role not in ("user", "assistant"):
                    role = "user"
                self.history.append({"role": role, "content": content})

    def save_to_memory(self, role, content):
        # Limita filas enormes: un LLM que divague puede escribir 50 KB.
        if content and len(content) > 4000:
            content = content[:4000] + "..."
        # Redacción de secretos (isair redact): nada sensible acaba en disco
        content = jarvis_redact.redact(content)
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with self._db_lock:
            try:
                self.cursor.execute(
                    "INSERT INTO interactions (timestamp, role, content) VALUES (?, ?, ?)",
                    (ts, role, content),
                )
                self.conn.commit()
            except sqlite3.Error as e:
                self.log(f"No se pudo guardar en memoria: {e}")

        # También guarda en Mem0 (memoria tripartita)
        if self.mem0 and role in ("user", "assistant"):
            try:
                self.mem0.add([{"role": role, "content": content}],
                              metadata={"timestamp": ts, "source": "conversation"})
            except Exception as e:
                self.log(f"Mem0 save error: {e}")

    def save_media_history(self, media_type: str, prompt: str, path: str):
        """Registra un medio generado (imagen, 3D, video) en su tabla dedicada."""
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with self._db_lock:
            try:
                self.cursor.execute(
                    "INSERT INTO media_history (timestamp, media_type, prompt, path) VALUES (?, ?, ?, ?)",
                    (ts, media_type, prompt, path),
                )
                self.conn.commit()
            except sqlite3.Error as e:
                self.log(f"No se pudo guardar historial de medios: {e}")

    # ── MEMORIA DE PREFERENCIAS Y RECORDATORIOS (Sprint 2) ─────────────────
    def set_pref(self, key: str, value: str):
        """Guarda una preferencia aprendida del señor."""
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with self._db_lock:
            try:
                self.cursor.execute(
                    "INSERT OR REPLACE INTO user_prefs (key, value, timestamp) VALUES (?, ?, ?)",
                    (key.lower().strip(), value.strip()[:500], ts),
                )
                self.conn.commit()
            except sqlite3.Error as e:
                self.log(f"No se pudo guardar preferencia: {e}")

    def get_pref(self, key: str):
        """Lee una preferencia del señor (None si no existe)."""
        with self._db_lock:
            try:
                self.cursor.execute(
                    "SELECT value FROM user_prefs WHERE key = ?",
                    (key.lower().strip(),))
                row = self.cursor.fetchone()
                return row[0] if row else None
            except sqlite3.Error as e:
                self.log(f"No se pudo leer preferencia: {e}")
                return None

    def get_prefs_context(self) -> str:
        """Devuelve las preferencias aprendidas como contexto para el LLM.

        Prioriza las preferencias clave (nombre, gusto) y después las más
        recientes; así los 'recuerdos' acumulados no desplazan lo esencial."""
        try:
            with self._db_lock:
                self.cursor.execute(
                    "SELECT key, value FROM user_prefs ORDER BY rowid DESC")
                prefs = self.cursor.fetchall()
            if not prefs:
                return ""
            orden = []
            for k, v in prefs:
                if k in ("nombre", "gusto"):
                    orden.insert(0, (k, v))  # clave: primero
                else:
                    orden.append((k, v))     # resto: por recencia
            partes = ", ".join(f"{k}: {v}" for k, v in orden[:10])
            return f"[Preferencias aprendidas del señor: {partes}]"
        except sqlite3.Error as e:
            self.log(f"No se pudieron leer preferencias: {e}")
            return ""

    def add_reminder(self, text: str, due: str = ""):
        """Guarda un recordatorio pendiente."""
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with self._db_lock:
            try:
                self.cursor.execute(
                    "INSERT INTO reminders (timestamp, due, text) VALUES (?, ?, ?)",
                    (ts, due, text.strip()[:500]),
                )
                self.conn.commit()
            except sqlite3.Error as e:
                self.log(f"No se pudo guardar recordatorio: {e}")

    def get_reminders_context(self) -> str:
        """Recordatorios pendientes como contexto para el LLM."""
        try:
            with self._db_lock:
                self.cursor.execute("SELECT text FROM reminders WHERE done = 0 ORDER BY id DESC LIMIT 5")
                rows = self.cursor.fetchall()
            if not rows:
                return ""
            lista = "; ".join(r[0] for r in rows)
            return f"[Recordatorios pendientes del señor: {lista}]"
        except sqlite3.Error as e:
            self.log(f"No se pudieron leer recordatorios: {e}")
            return ""

    def mark_reminder_done(self, text_part: str) -> bool:
        """Marca como hechos los recordatorios que contengan el texto dado."""
        with self._db_lock:
            try:
                self.cursor.execute(
                    "UPDATE reminders SET done = 1 WHERE done = 0 AND text LIKE ?",
                    (f"%{text_part.strip()[:60]}%",),
                )
                self.conn.commit()
                return self.cursor.rowcount > 0
            except sqlite3.Error as e:
                self.log(f"No se pudo cerrar recordatorio: {e}")
                return False

    def remember_from(self, text: str) -> str | None:
        """Aprende preferencias dichas en lenguaje natural. Devuelve confirmación o None."""
        import unicodedata
        norm = unicodedata.normalize("NFD", text.lower())
        t = "".join(c for c in norm if unicodedata.category(c) != "Mn")
        orig_low = text.lower()
        # "recuerda que X" / "recuerda: X" / "no olvides que X"
        m = re.search(r"(?:recuerda|acuerdate|no olvides)(?: que|:)?\s+(.+)", t)
        if m:
            mo = re.search(r"(?:recuerda|acuerdate|no olvides)(?: que|:)?\s+(.+)", orig_low)
            content = (mo.group(1) if mo else m.group(1)).strip().strip("\"'")
            if content and len(content) > 3:
                key = f"recuerdo_{int(time.time())}"
                self.set_pref(key, content)
                return f"Lo tengo presente, señor: «{content[:120]}». No lo olvidaré."
        # "mi nombre es X" / "me llamo X" / "soy X"
        m = re.search(r"(?:mi nombre es|me llamo|llamame)\s+([a-z ]{2,30})", t)
        if m:
            mo = re.search(r"(?:mi nombre es|me llamo|llamame)\s+([a-záéíóúñ ]{2,30})", orig_low)
            nombre = (mo.group(1) if mo else m.group(1)).strip().title()
            self.set_pref("nombre", nombre)
            return f"Encantado de conocerle, {nombre}. Lo tendré presente en todo momento."
        # "me gusta X" / "prefiero X" / "mi favorito es X"
        m = re.search(r"(?:me gusta|prefiero|mi favorito es|me encanta)\s+(.+)", t)
        if m:
            mo = re.search(r"(?:me gusta|prefiero|mi favorito es|me encanta)\s+(.+)", orig_low)
            gusto = (mo.group(1) if mo else m.group(1)).strip().strip("\"'")
            if gusto and len(gusto) > 2 and "hacer" not in gusto[:10]:
                self.set_pref("gusto", gusto)
                return f"Anotado, señor: le gusta {gusto}."
        return None

    def start_udp_listener(self):
        def udp_loop():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(("127.0.0.1", 9999))
                self.log("UDP Listener activo en puerto 9999 (Hotkey)")
            except Exception as e:
                self.log(f"No se pudo iniciar UDP listener: {e}")
                return
            while True:
                data, addr = sock.recvfrom(1024)
                if b"WAKE_JARVIS" in data:
                    self.log("[SISTEMA] Hotkey Global Detectado: WAKE_JARVIS")
                    if self.hotkey_callback:
                        self.hotkey_callback()
        t = threading.Thread(target=udp_loop, daemon=True)
        t.start()

    # ── CEREBRO: proveedores, fallback y límites (estilo Free Claude Code) ──
    def _cerebro_leer(self) -> dict:
        """Lee Prefs/cerebro.json; si no existe, crea el proveedor por defecto (Ollama/env)."""
        d = {}
        try:
            with open(self._cerebro_path, encoding="utf-8") as f:
                d = json.load(f) or {}
        except Exception:
            pass
        if not d.get("proveedores"):
            d["proveedores"] = [
                {
                    # Cerebro principal: Kimi K3 (Moonshot).
                    # Clave: variable de entorno MOONSHOT_API_KEY, o pega el
                    # valor literal aquí en "clave" reemplazando ${MOONSHOT_API_KEY}.
                    "nombre": "kimi-k3",
                    "url": "https://api.moonshot.ai/v1",
                    "modelo": "kimi-k3",
                    "clave": "${MOONSHOT_API_KEY}",
                },
                {
                    # Reserva local: sin clave de Moonshot o si la nube falla.
                    "nombre": "ollama",
                    "url": self.base_url,
                    "modelo": self.model,
                    "clave": self.api_key,
                },
            ]
            try:
                os.makedirs(os.path.dirname(self._cerebro_path), exist_ok=True)
                with open(self._cerebro_path, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        return d

    def _cliente_llm(self, url: str, clave: str):
        """Cliente reutilizado por proveedor.

        Antes se construía un OpenAI() nuevo en cada mensaje, y con él una
        sesión HTTP nueva: unos cuantos milisegundos por frase que no hacían
        falta, más presión sobre los sockets.
        """
        if not hasattr(self, "_clientes_llm"):
            self._clientes_llm = {}
        pareja = (url, clave)
        cliente = self._clientes_llm.get(pareja)
        if cliente is None:
            kwargs = {"base_url": url, "api_key": clave}
            if HAS_HTTPX:
                kwargs["timeout"] = Timeout(60.0, connect=5.0)
            cliente = OpenAI(**kwargs)
            self._clientes_llm[pareja] = cliente
        return cliente

    def _proveedores(self) -> list:
        """[(nombre, base_url, modelo, clave), ...] orden de preferencia."""
        proveedores = []
        for p in (self._cerebro.get("proveedores") or []):
            url = (p.get("url") or "").strip().rstrip("/")
            modelo = (p.get("modelo") or "").strip()
            clave = (p.get("clave") or "").strip()
            nombre = (p.get("nombre") or url).strip() or "proveedor"
            # Placeholder ${VAR}: se resuelve desde el entorno, así la clave
            # puede vivir fuera del JSON.
            m = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", clave)
            if m:
                clave = os.getenv(m.group(1), "").strip()
            es_local = ("localhost" in url) or ("127.0.0.1" in url)
            # Un proveedor de nube sin clave se descarta en silencio (p. ej.
            # Kimi antes de que el señor ponga MOONSHOT_API_KEY): así el
            # fallback local sigue respondiendo sin ruido de errores.
            if url and modelo and (clave or es_local):
                proveedores.append((nombre, url, modelo, clave or "ollama"))
        if not proveedores:
            proveedores = [("ollama", self.base_url.rstrip("/"), self.model, self.api_key)]
        return proveedores

    # Qwen3 razona antes de responder. Pensando acierta la aritmética y las
    # decisiones, pero tarda unos 20 segundos; sin pensar contesta en uno y
    # falla en cuanto hay que echar cuentas. Ni una cosa ni la otra siempre:
    # se mira la pregunta y se decide, que es lo que haría un mayordomo.
    _PIDE_PENSAR = re.compile(
        r"(cu[aá]nt|calcul|suma|resta|multiplic|divid|porcentaje|promedio|"
        r"compar|decide|conviene|merece la pena|analiz|razon|deduc|plan|"
        r"estrategia|diferencia entre|por qu[eé]|c[oó]mo funciona|explica por|"
        r"script|c[oó]digo|comando|programa|algoritmo|error|falla|depura)",
        re.IGNORECASE)

    def _esfuerzo_razonamiento(self, texto: str) -> str:
        """'none' para lo cotidiano, 'low' cuando hay que pensar de verdad."""
        modo = (os.getenv("JARVIS_RAZONAR", "auto") or "auto").lower()
        if modo in ("nunca", "no", "off"):
            return "none"
        if modo in ("siempre", "si", "on"):
            return "low"
        t = (texto or "").strip()
        if self._PIDE_PENSAR.search(t):
            return "low"
        # dos números y un signo suelen ser una cuenta disfrazada de frase
        if len(re.findall(r"\d+", t)) >= 2:
            return "low"
        if len(t) > 160:
            return "low"
        return "none"

    def _solo_cerebro_local(self) -> bool:
        """¿Todos los proveedores son locales? Entonces no hay cuota que cuidar."""
        try:
            for _n, url, _m, _c in self._proveedores():
                if "localhost" not in url and "127.0.0.1" not in url:
                    return False
            return True
        except Exception:
            return False

    def _rate_limit_ok(self) -> bool:
        """Intervalo mínimo entre llamadas + tope por hora (cuotas gratuitas).

        Esto existe para las cuentas gratuitas de proveedores en la nube, que
        cortan si les hablas muy seguido. Con el modelo LOCAL no hay cuota ni
        coste: aplicarlo aquí solo añadía hasta DOS SEGUNDOS de espera a cada
        respuesta seguida, y además hacía que JARVIS se negara a contestar tras
        cuarenta frases en una hora. Medido en el perfilador: 0,6 s de sueño
        puro en una respuesta cualquiera.
        """
        if self._solo_cerebro_local():
            return True

        cfg = self._cerebro
        min_seg = float(cfg.get("min_segundos") or 2)
        max_hora = int(cfg.get("max_por_hora") or 40)
        now = time.time()
        if self._llm_ultimo and now - self._llm_ultimo < min_seg:
            time.sleep(min_seg - (now - self._llm_ultimo))
        self._llm_hora = [t for t in self._llm_hora if now - t < 3600]
        if len(self._llm_hora) >= max_hora:
            return False
        return True

    def _marcar_uso(self):
        self._llm_ultimo = time.time()
        self._llm_hora.append(time.time())
        if len(self._llm_hora) > 200:
            self._llm_hora = self._llm_hora[-100:]

    def _recortar_respuesta(self, texto: str) -> str:
        """Respuestas compactas: corta en frontera de frase para que el TTS no se alargue."""
        max_c = int(self._cerebro.get("respuesta_max") or 700)
        if len(texto) <= max_c:
            return texto
        corte = texto.rfind(". ", 0, max_c)
        if corte < max_c // 2:
            corte = texto.rfind(" ", 0, max_c)
        if corte < max_c // 2:
            corte = max_c
        return texto[:corte + 1].rstrip() + "…"

    def probar_cerebro(self) -> dict:
        """Valida cada proveedor con una llamada mínima (Validate del Admin UI de FCC)."""
        resultado = {"ok": False, "proveedores": []}
        for nombre, b_url, modelo, clave in self._proveedores():
            info = {"nombre": nombre, "modelo": modelo, "ok": False}
            try:
                cliente = OpenAI(base_url=b_url, api_key=clave)
                es_kimi = ("moonshot" in b_url) or modelo.startswith("kimi-k3")
                extra = {"reasoning_effort": "low"} if es_kimi else {}
                r = cliente.chat.completions.create(
                    model=modelo,
                    messages=[{"role": "user", "content": "Responde solo: ok"}],
                    max_tokens=64 if es_kimi else 5,
                    temperature=0,
                    timeout=20,
                    extra_body=extra)
                info["respuesta"] = (r.choices[0].message.content or "").strip()[:80]
                info["ok"] = True
                resultado["ok"] = True
            except Exception as e:
                info["error"] = str(e)[:150]
            resultado["proveedores"].append(info)
        return resultado

    def limpiar_memoria(self) -> str:
        """/clear: borra el historial de conversación del cerebro (FCC messaging)."""
        try:
            with self._db_lock:
                self.cursor.execute("DELETE FROM interactions")
                self.conn.commit()
            self.history = [{"role": "system", "content": self.system_prompt}]
            return "Memoria limpia, señor. Empezamos de cero."
        except Exception as e:
            self.log(f"No pude limpiar memoria: {e}")
            return "Señor, no pude limpiar la memoria."

    # ── Adaptaciones isair/jarvis ─────────────────────────────────────────
    def _contexto_append(self, u: str, r: str):
        """Contexto rodante: últimas 3 interacciones para el cerebro."""
        self._contexto.append((u[:120], r[:200]))
        if len(self._contexto) > 3:
            self._contexto = self._contexto[-3:]

    # ── MANTENIMIENTO DE MEMORIA ───────────────────────────────────────────
    def _mantenimiento_periodico(self):
        """Una pasada de olvido al arrancar y otra cada 24 horas.

        Recorta el grafo de conocimiento, poda el historial de interacciones y
        purga los registros antiguos de auditoría. Todo con margen amplio: la
        idea es que la memoria no crezca sin límite, no borrar lo reciente.
        """
        time.sleep(120)   # dejar que el arranque respire
        while True:
            try:
                self.mantenimiento_memoria()
            except Exception as e:
                self.log(f"[MANTENIMIENTO] {e}")
            time.sleep(86400)

    def mantenimiento_memoria(self) -> str:
        """Poda memoria y registros. Devuelve el resumen para decirlo en voz alta."""
        partes = []
        try:
            dias = int(os.getenv("JARVIS_OLVIDO_DIAS", "45"))
            r = jarvis_grafo.olvidar(dias=dias)
            if r.get("nodos_borrados") or r.get("debilitados"):
                partes.append(f"grafo: {r['nodos_borrados']} conceptos olvidados, "
                              f"{r['debilitados']} debilitados")
        except Exception as e:
            self.log(f"[MANTENIMIENTO] grafo: {e}")

        # Historial de conversación: conservar las últimas N interacciones.
        try:
            tope = int(os.getenv("JARVIS_HISTORIAL_MAX", "5000"))
            with self._db_lock:
                self.cursor.execute(
                    "DELETE FROM interactions WHERE id NOT IN "
                    "(SELECT id FROM interactions ORDER BY id DESC LIMIT ?)", (tope,))
                borradas = self.cursor.rowcount or 0
                self.conn.commit()
            if borradas > 0:
                partes.append(f"historial: {borradas} interacciones antiguas retiradas")
        except Exception as e:
            self.log(f"[MANTENIMIENTO] historial: {e}")

        try:
            from storage import get_storage
            purgadas = get_storage(log=self.log).purgar(
                dias=int(os.getenv("JARVIS_AUDITORIA_DIAS", "90")))
            if purgadas:
                partes.append(f"registros: {purgadas} entradas purgadas")
        except Exception as e:
            self.log(f"[MANTENIMIENTO] registros: {e}")

        resumen = "; ".join(partes) or "no hacía falta olvidar nada"
        self.log(f"[MANTENIMIENTO] {resumen}")
        return resumen

    # ── VERIFICACIÓN PREVIA ────────────────────────────────────────────────
    def _revisar_antes_de_actuar(self, texto: str):
        """Devuelve el aviso si hay que frenar, o None para seguir.

        Solo entra en acciones destructivas: lo demás no paga ni un milisegundo.
        Si el señor insiste («hazlo igual»), se ejecuta lo que quedó pendiente.
        """
        import verificador

        # Reejecución ya aprobada por el señor: no volver a frenarla.
        if getattr(self, "_saltar_freno", False):
            return None

        # ¿Está insistiendo sobre algo que frené hace un momento?
        pendiente = getattr(self, "_plan_frenado", None)
        if pendiente and verificador.insiste(texto):
            self._plan_frenado = None
            self.log(f"[VERIFICADOR] El señor insiste: ejecuto «{pendiente[:60]}»")
            return None if pendiente == texto else self._procesar_sin_freno(pendiente)

        t = (texto or "").lower()
        destructiva = re.search(
            r"\b(borra|borrar|elimina|eliminar|formatea|formatear|desinstala|"
            r"desinstalar|vacia|vacía|vaciar|mata|matar|purga|purgar|"
            r"sobrescribe|sobreescribe)\b", t)
        if not destructiva:
            return None

        veredicto = verificador.verificar(self, texto, con_modelo=True, log=self.log)
        if not verificador.hay_que_parar(veredicto):
            return None
        self._plan_frenado = texto
        return veredicto["frase"]

    def _procesar_sin_freno(self, texto: str) -> str:
        """Ejecuta un plan ya revisado y aprobado a mano por el señor.

        El interruptor evita el bucle evidente: sin él, la reejecución volvía a
        pasar por el verificador y se frenaba a sí misma para siempre.
        """
        self._plan_frenado = None
        self._saltar_freno = True
        try:
            return self._procesar(texto, speak_server=False)
        finally:
            self._saltar_freno = False

    # ── ÓRDENES SOBRE EL PROPIO ASISTENTE ──────────────────────────────────
    def _ordenes_meta(self, texto: str):
        # Señal de vida para el protocolo de relevo: cualquier frase del señor
        # reinicia el contador de inactividad.
        try:
            import relevo
            relevo.latido(log=self.log)
        except Exception:
            pass
        """Preguntas del señor sobre lo que Jarvis ha hecho, sabe o siente.

        Vive en el núcleo y no en jarvis_skills porque necesita el almacén de
        acciones, el hub cognitivo y el estado paralingüístico, que son cosas
        del núcleo. Antes no existía ninguna forma de preguntar «¿qué has
        ejecutado?» y comprobar si una orden se cumplió de verdad.
        """
        if not texto:
            return None
        t = texto.lower().strip()

        def _almacen():
            from storage import get_storage
            return get_storage(log=self.log)

        agente = getattr(self, "nombre_agente", "JARVIS")
        trato = "señor. " if agente == "JARVIS" else ""

        if re.search(r"que (has|habias) (ejecutado|hecho)( hoy)?|registro de acciones|"
                     r"ultimas acciones|últimas acciones|que ordenes ejecutaste", t):
            filas = _almacen().acciones_recientes(6)
            if not filas:
                return f"No he ejecutado nada todavía, {trato}".strip()
            detalle = "; ".join(
                f"{f['orden'][:38] or f['comando'][:38]} ({'bien' if f['ok'] else 'falló'})"
                for f in filas)
            resumen = _almacen().resumen(24)
            return (f"En las últimas 24 horas he ejecutado {resumen['acciones']} órdenes, "
                    f"{resumen['fallos']} con error. Las más recientes: {detalle}.")

        if re.search(r"que (te )?ha fallado|fallos recientes|que salio mal|errores recientes", t):
            filas = _almacen().acciones_recientes(6, solo_fallos=True)
            if not filas:
                return f"Ninguna orden ha fallado últimamente, {trato}".strip()
            detalle = "; ".join(f"{f['orden'][:34] or f['comando'][:34]}: {f['detalle'][:60]}"
                                for f in filas)
            return f"Estas órdenes fallaron: {detalle}."

        if re.search(r"que ha pasado|eventos recientes|hubo intrusos|quien entro|quién entró|"
                     r"registro de seguridad", t):
            filas = _almacen().eventos_recientes(8)
            if not filas:
                return f"No hay eventos registrados, {trato}".strip()
            detalle = "; ".join(f"{f['ts'][5:16]} {f['titulo'][:50]}" for f in filas)
            return f"Últimos eventos: {detalle}."

        if re.search(r"estado (de tus|de los) motores|estado cognitivo|que motores tienes", t):
            if getattr(self, "cognition", None) is None:
                return "La capa cognitiva no está disponible en este arranque."
            estado = self.cognition.estado()
            activos = ", ".join(estado["activos"]) or "ninguno cargado aún"
            fallidos = "; ".join(f"{k}: {v[:40]}" for k, v in estado["fallidos"].items())
            return (f"Motores activos: {activos}."
                    + (f" Fallaron: {fallidos}." if fallidos else ""))

        if re.search(r"entrena tu clasificador|aprende de mis ordenes|aprende de mis órdenes|"
                     r"reentrena tus intenciones", t):
            return self.entrenar_intenciones()

        if re.search(r"(silencia|desactiva|calla|quita)( los| tus)? avisos( proactivos)?|"
                     r"deja de avisarme|no me avises", t):
            self.set_pref("avisos_proactivos", "0")
            if getattr(self, "proactivo", None) is not None:
                self.proactivo.stop()
                self.proactivo = None
            return f"Avisos proactivos silenciados, {trato}Seguiré vigilando sin interrumpir.".strip()

        if re.search(r"(?<!des)(activa|enciende|reactiva)( los| tus)? avisos( proactivos)?|"
                     r"vuelve a avisarme|avisame de todo", t):
            self.set_pref("avisos_proactivos", "1")
            try:
                if getattr(self, "proactivo", None) is None:
                    from jarvis_proactive import ProactiveEngine
                    self.proactivo = ProactiveEngine(self, log=self.log,
                                                     interval=int(os.getenv("JARVIS_PROACTIVO_INTERVALO", "120")))
                self.proactivo.start()
            except Exception as e:
                return f"No pude arrancar el motor proactivo: {e}"
            return f"Avisos proactivos activos, {trato}Le avisaré de lo importante.".strip()

        if re.search(r"(transcribe|dicta|escucha) (en|con) local|dictado local|"
                     r"no mandes mi voz|deja de usar google para (oirme|oírme)", t):
            self.set_pref("stt_local", "1")
            return f"Dictado local activado, {trato}Su voz ya no sale del equipo.".strip()

        if re.search(r"(transcribe|dicta|escucha) en la nube|dictado en la nube|"
                     r"usa google para (oirme|oírme)", t):
            self.set_pref("stt_local", "0")
            return f"Dictado en la nube activado, {trato}".strip()

        if re.search(r"(?<!des)(activa|enciende|arranca)( la)? escucha( continua)?|"
                     r"escuchame siempre|escúchame siempre|modo manos libres", t):
            if getattr(self, "escucha", None) is None:
                return "No tengo el módulo de escucha continua disponible."
            ok, motivo = self.escucha.start()
            if not ok:
                return f"No pude activar la escucha continua: {motivo}."
            self.set_pref("escucha_continua", "1")
            nombres = ", ".join(self.escucha.palabras)
            return (f"Escucha continua activa, {trato}Llámeme por mi nombre ({nombres}) "
                    "y respondo. Puede interrumpirme cuando quiera.").strip()

        if re.search(r"(desactiva|apaga|para|deten)( la)? escucha( continua)?|"
                     r"deja de escuchar|no me escuches", t):
            self.set_pref("escucha_continua", "0")
            if getattr(self, "escucha", None) is not None:
                self.escucha.stop()
            return f"Escucha continua desactivada, {trato}".strip()

        if re.search(r"(haz|hazme)? ?(una )?limpieza de memoria|olvida lo viejo|"
                     r"poda tu memoria|libera memoria antigua", t):
            return f"Hecho, {trato}".strip() + " " + self.mantenimiento_memoria() + "."

        if re.search(r"cuanta memoria tienes|tamaño de tu memoria|"
                     r"cuanto sabes|estado de tu memoria", t):
            g = jarvis_grafo.estadisticas()
            try:
                from storage import get_storage
                r = get_storage(log=self.log).resumen(24)
            except Exception:
                r = {"acciones": 0, "fallos": 0}
            return (f"Mi grafo tiene {g['nodos']} conceptos y {g['aristas']} relaciones. "
                    f"En 24 horas he ejecutado {r['acciones']} órdenes con {r['fallos']} fallos.")

        if re.search(r"^(deshaz|deshacer|desaz|revierte|anula) (eso|lo ultimo|lo último|"
                     r"lo que hiciste|el ultimo cambio|el último cambio)|^deshaz$|"
                     r"vuelve atras|vuelve atrás|marcha atras|marcha atrás", t):
            import deshacer
            cuantas = 1
            m = re.search(r"(?:las |los )?(?:ultim[ao]s? )?(\d{1,2})\b", t)
            if m and re.search(r"ultim|últim|acciones|cambios", t):
                cuantas = max(1, min(int(m.group(1)), 20))
            return deshacer.deshacer_ultimo(
                cuantas, log=self.log, set_pref=self.set_pref,
                agente=getattr(self, "nombre_agente", "JARVIS"))

        if re.search(r"que puedes deshacer|que se puede deshacer|"
                     r"que es reversible|historial de deshacer", t):
            import deshacer
            return deshacer.listar(limite=5, log=self.log)

        if re.search(r"(como|cómo) (estas|estás) de salud|estado de salud|"
                     r"te has caido|te has caído|salud del sistema|"
                     r"estas bien|estás bien", t):
            if getattr(self, "vigilante", None) is None:
                return "El vigilante está apagado en este arranque."
            return self.vigilante.resumen()

        if re.search(r"(desactiva|quita|apaga)( el)? modo privado|"
                     r"vuelve a usar la nube", t):
            import privacidad
            return privacidad.desactivar(self)

        if re.search(r"(?<!des)(activa|enciende|pon)( el)? modo privado|"
                     r"modo (privado|sin nube|offline)|no mandes nada fuera|"
                     r"corta (la nube|las conexiones externas)", t):
            import privacidad
            return privacidad.activar(self)

        if re.search(r"que sale de (mi|este) (pc|equipo|ordenador)|"
                     r"que informacion sale|auditoria de privacidad|"
                     r"por donde sale mi (voz|informacion)|estoy siendo privado", t):
            import privacidad
            return privacidad.informe(self)

        if re.search(r"(haz|crea|exporta)( una)? copia (de seguridad )?(de tu (cerebro|memoria))?|"
                     r"exporta tu cerebro|respalda tu memoria|copia tu cerebro", t):
            import cerebro_backup
            try:
                ruta = cerebro_backup.exportar(log=self.log)
            except Exception as e:
                return f"No pude crear la copia, señor: {e}"
            return (f"Copia de mi cerebro guardada, señor, en {ruta}. "
                    "No incluye credenciales; si las quiere, hay que pedirlo aparte.")

        if re.search(r"que herramientas tienes|de que eres capaz|"
                     r"que puedes ejecutar|lista de herramientas", t):
            try:
                from herramientas_llm import Herramientas
                caja = Herramientas(self, log=self.log)
                nombres = [d["function"]["name"] for d in caja.definiciones()]
            except Exception as e:
                return f"No pude leer mis herramientas: {e}"
            return (f"Tengo {len(nombres)} herramientas que el cerebro puede usar solo: "
                    + ", ".join(nombres[:12]) + "… y las habilidades de siempre.")

        if re.search(r"(mira|lee|analiza|interpreta|revisa) (mi |la )?pantalla|"
                     r"que (ves|hay) en (mi |la )?pantalla|que error (me )?(da|sale)|"
                     r"que dice (esta|la) (pantalla|ventana|imagen)|"
                     r"que estoy (viendo|mirando)", t):
            import vision
            pregunta = texto.strip()
            return vision.mirar_pantalla(pregunta, log=self.log)

        if re.search(r"tienes ojos|puedes ver|estado de (tu )?vision|estado de tus ojos", t):
            import vision
            e = vision.estado(log=self.log)
            if e["listo"]:
                return f"Veo con el modelo {e['modelo']}, señor. Todo local."
            return vision.instrucciones_instalacion()

        # ── Piloto: usar el PC como lo haría un humano ──────────────────
        m_pilo = re.search(r"(?:pilota|toma el control|hazlo tu mismo|hazlo tú mismo|"
                           r"usa el raton|usa el ratón|encargate de)\s*(?:y\s+)?(.*)$", t)
        if m_pilo and len(m_pilo.group(1).strip()) > 3:
            objetivo = m_pilo.group(1).strip()
            from piloto import Piloto
            if getattr(self, "piloto", None) is None:
                self.piloto = Piloto(self, log=self.log)
            # Ensayo primero: un clic no se puede deshacer, así que el señor ve
            # el primer paso antes de que nada se mueva.
            if not re.search(r"\bsin ensayo|hazlo ya|adelante\b", t):
                previo = self.piloto.ejecutar(objetivo, seco=True)
                return (previo + " Si le parece bien, dígame «hazlo ya» y sigo "
                        "hasta el final.")
            return self.piloto.ejecutar(objetivo)

        if re.search(r"(que harias si|ensaya|simula|prueba en seco|que pasaria si)\s+(.+)", t):
            import sandbox
            m_ens = re.search(r"(?:que harias si|ensaya|simula|prueba en seco|que pasaria si)\s+(.+)", t)
            return sandbox.informe_impacto(m_ens.group(1).strip(), log=self.log)

        if re.search(r"puedes ensayar|como ensayas|modos de ensayo|tienes sandbox", t):
            import sandbox
            return sandbox.resumen()

        # ── Señuelos anti-ransomware ────────────────────────────────────────
        if re.search(r"(despliega|pon|coloca)( los)? (señuelos|senuelos|canarios)|"
                     r"protegeme del ransomware|proteccion anti ?ransomware", t):
            import canarios
            texto_despliegue = canarios.desplegar(log=self.log)
            if getattr(self, "canarios", None) is None:
                self.canarios = canarios.Canarios(self, log=self.log)
            return texto_despliegue + " " + self.canarios.start()

        if re.search(r"(retira|quita)( los)? (señuelos|senuelos|canarios)", t):
            import canarios
            if getattr(self, "canarios", None) is not None:
                self.canarios.stop()
            return canarios.retirar(log=self.log)

        if re.search(r"estado de los (señuelos|senuelos|canarios)|"
                     r"como va la proteccion anti ?ransomware", t):
            if getattr(self, "canarios", None) is None:
                return "Los señuelos no están desplegados, señor."
            e = self.canarios.estado()
            return (f"{e['desplegados']} señuelos desplegados, "
                    f"{'vigilando' if e['vigilando'] else 'sin vigilar'}, "
                    f"revisión cada {e['intervalo_s']} segundos.")

        if re.search(r"restaura la red|devuelve la red|vuelve a abrir la red", t):
            import canarios
            return canarios.restaurar_red(log=self.log)

        # ── Turno de noche ──────────────────────────────────────────────────
        m_noche = re.search(r"(?:turno de noche|modo nocturno|trabaja de noche)"
                            r"(?:.*?(\d{1,2})[:.](\d{2}))?", t)
        if m_noche and re.search(r"turno de noche|modo nocturno|trabaja de noche", t):
            if getattr(self, "nocturno", None) is None:
                return "El turno de noche no está disponible en este arranque."
            if re.search(r"cancela|desactiva|quita|para", t):
                return self.nocturno.cancelar()
            if re.search(r"que hiciste|informe|parte de (la )?noche|resumen de la noche", t):
                return self.nocturno.informe_ultimo()
            if re.search(r"ahora|ya|ejecuta", t):
                try:
                    import orquestador
                    tareas = orquestador.tareas_segun_agenda(self, log=self.log)
                except Exception:
                    tareas = None
                return self.nocturno.ejecutar(claves=tareas)
            hora = f"{m_noche.group(1)}:{m_noche.group(2)}" if m_noche.group(1) else "03:30"
            return self.nocturno.programar(hora)

        if re.search(r"que hiciste (anoche|esta noche)|parte de la noche|"
                     r"informe nocturno", t):
            if getattr(self, "nocturno", None) is None:
                return "No tengo turno de noche configurado, señor."
            return self.nocturno.informe_ultimo()

        # ── Enjambre de especialistas ───────────────────────────────────────
        if re.search(r"(?<!des)(activa|enciende|despliega)( el)? enjambre|"
                     r"(?<!des)activa (los|tus) (especialistas|agentes)", t):
            try:
                from enjambre import Enjambre
                if getattr(self, "enjambre", None) is None:
                    self.enjambre = Enjambre(self, log=self.log)
                self.set_pref("enjambre", "1")
                return self.enjambre.start()
            except Exception as e:
                return f"No pude activar el enjambre, señor: {e}"

        if re.search(r"(desactiva|apaga|para)( el)? enjambre|calla (a )?(los|tus) (especialistas|agentes)", t):
            self.set_pref("enjambre", "0")
            if getattr(self, "enjambre", None) is not None:
                self.enjambre.stop()
            return "Enjambre detenido, señor."

        if re.search(r"que dicen (los|tus) (especialistas|agentes)|"
                     r"resumen del enjambre|que han visto tus agentes", t):
            if getattr(self, "enjambre", None) is None:
                return "El enjambre está apagado, señor."
            return self.enjambre.resumen()

        # ── Consejo adversario (JARVIS contra ULTRON) ───────────────────────
        m_consejo = re.search(r"(?:consulta al consejo|que opinan los dos|"
                              r"delibera(?:d)?|debate|pregunta a ultron y a jarvis|"
                              r"consejo sobre)\s+(?:sobre\s+)?(.+)", t)
        if m_consejo:
            import consejo
            return consejo.deliberar(self, m_consejo.group(1).strip(), log=self.log)

        # ── Hábitos y anticipación ──────────────────────────────────────────
        if re.search(r"que suelo (hacer|pedir)|conoces mis habitos|mis costumbres|"
                     r"que hago normalmente", t):
            import prediccion
            return prediccion.informe(log=self.log)

        if re.search(r"(anticipate|adelantate|prepara lo de siempre|"
                     r"lo de costumbre|lo habitual)", t):
            import prediccion
            frase = prediccion.frase_sugerencia(log=self.log)
            return frase or "Aún no sé qué suele pedirme a esta hora, señor."

        # ── Buscar dentro de los documentos (RAG local) ─────────────────────
        m_doc = re.search(r"(?:busca|buscame|que decia|qué decía|encuentra|segun|"
                          r"según)\s+(?:en\s+)?(?:mis\s+)?(?:documentos|apuntes|"
                          r"archivos|papeles|notas)\s+(?:sobre\s+|lo de\s+|acerca de\s+)?(.+)", t)
        if m_doc:
            import indice_documentos
            return indice_documentos.responder(self, m_doc.group(1).strip(), log=self.log)

        m_conv = re.search(r"(?:que me dijiste|que hablamos|que dijimos|"
                           r"de que hablamos|cuando hablamos)\s+(?:sobre |de |del |"
                           r"acerca de )?(.+)", t)
        if m_conv:
            import indice_documentos
            return indice_documentos.buscar_conversacion(m_conv.group(1).strip(),
                                                         log=self.log)

        if re.search(r"indexa (nuestras )?conversaciones|"
                     r"indexa (nuestro |el )?historial", t):
            import indice_documentos
            return indice_documentos.indexar_conversaciones(log=self.log)

        if re.search(r"indexa (mis )?(documentos|archivos|carpetas)|"
                     r"lee mis documentos|actualiza el indice", t):
            import indice_documentos
            return indice_documentos.indexar(log=self.log)

        if re.search(r"estado del indice|cuantos documentos (tienes|has leido)", t):
            import indice_documentos
            e = indice_documentos.estado(log=self.log)
            motor = "por significado" if e["embeddings"] else "por texto completo"
            return (f"Tengo {e['archivos']} documentos indexados en {e['trozos']} "
                    f"fragmentos, señor, con búsqueda {motor}.")

        # ── Identidad por voz ───────────────────────────────────────────────
        if re.search(r"(registra|aprende|memoriza) mi voz|reconoce mi voz", t):
            return ("Para registrar su voz necesito varias frases grabadas, señor. "
                    "Dígamelo desde la interfaz web, donde puedo capturar el audio: "
                    "allí grabaré tres frases y me quedaré con su huella.")

        if re.search(r"reconoces mi voz|estado de (tu )?(identidad|huella) de voz", t):
            import voz_identidad
            e = voz_identidad.estado()
            if not e["registrada"]:
                return "Todavía no tengo registrada su voz, señor."
            return (f"Su voz está registrada, señor ({e['dimensiones']} rasgos, "
                    f"motor {e['motor']}). Umbral de parecido: {e['umbral']}.")

        if re.search(r"(exige|pide|requiere) mi voz|solo obedeceme a mi|"
                     r"solo obedéceme a mí", t):
            self.set_pref("exigir_voz", "1")
            return ("De acuerdo, señor: las órdenes destructivas solo las obedeceré "
                    "si reconozco su voz.")

        if re.search(r"obedece a cualquiera|quita la exigencia de voz", t):
            self.set_pref("exigir_voz", "0")
            return "Obedeceré a cualquier voz, señor."

        # ── Memoria episódica (grabar la pantalla) ──────────────────────────
        if re.search(r"(empieza|comienza|ponte) a grabar (mi )?(pantalla|escritorio)|"
                     r"activa el rebobinado|graba lo que hago", t):
            from rebobinar import Rebobinador
            if getattr(self, "rebobinador", None) is None:
                self.rebobinador = Rebobinador(self, log=self.log)
            return self.rebobinador.start()

        if re.search(r"(deja|para) de grabar|desactiva el rebobinado", t):
            if getattr(self, "rebobinador", None) is None:
                return "No estaba grabando, señor."
            return self.rebobinador.stop()

        if re.search(r"borra (la|lo de la) ultima hora|olvida la ultima hora|"
                     r"borra lo que grabaste", t):
            if getattr(self, "rebobinador", None) is None:
                return "No hay nada grabado, señor."
            return self.rebobinador.borrar_rango(1)

        m_reb = re.search(r"(?:que estaba (?:haciendo|viendo)|donde vi|dónde vi|"
                          r"rebobina|recuerda cuando)\s+(.+)", t)
        if m_reb:
            if getattr(self, "rebobinador", None) is None:
                from rebobinar import Rebobinador
                self.rebobinador = Rebobinador(self, log=self.log)
            return self.rebobinador.relato(m_reb.group(1).strip())

        # ── Habilidades que se escribe él solo ──────────────────────────────
        m_auto = re.search(r"(?:escribete|escríbete|crea|programa) (?:una )?"
                           r"habilidad (?:para |que )?(.+)", t)
        if m_auto:
            import autoskills
            resultado = autoskills.proponer(self, m_auto.group(1).strip(), log=self.log)
            return autoskills.resumen_propuesta(resultado)

        if re.search(r"que habilidades? (tienes )?pendientes|habilidades en cuarentena", t):
            import autoskills
            pend = autoskills.pendientes()
            return ("Tengo pendientes de aprobación: " + ", ".join(pend) + "."
                    if pend else "No tengo habilidades pendientes, señor.")

        m_aprob = re.search(r"(?:aprueba|instala) (?:la habilidad )?([\w.]+)", t)
        if m_aprob and "habilidad" in t:
            import autoskills
            return autoskills.aprobar(m_aprob.group(1), log=self.log)

        m_ver = re.search(r"(?:muestrame|muéstrame|ensename|enséñame) la habilidad ([\w.]+)", t)
        if m_ver:
            import autoskills
            return autoskills.ver(m_ver.group(1))[:1500]

        # ── Colisiones entre habilidades ────────────────────────────────────
        if re.search(r"(colisiones|habilidades que se pisan|conflictos de habilidades)", t):
            import colisiones
            return colisiones.informe(log=self.log)[:1800]

        m_quien = re.search(r"quien atiende (?:la orden )?«?(.+?)»?$", t)
        if m_quien:
            import colisiones
            return colisiones.quien_atiende(m_quien.group(1).strip(), log=self.log)

        # ── Recados ─────────────────────────────────────────────────────────
        if re.search(r"tengo recados|hay recados|quien me ha escrito|"
                     r"resumen de mensajes", t):
            import recados
            return recados.resumen()

        # ── Protocolo de relevo ─────────────────────────────────────────────
        if re.search(r"(activa|configura)( el)? (protocolo de )?relevo|"
                     r"si me pasa algo|protocolo de inactividad", t):
            import relevo
            return relevo.activar(log=self.log)

        if re.search(r"(desactiva|cancela)( el)? (protocolo de )?relevo", t):
            import relevo
            return relevo.desactivar(log=self.log)

        if re.search(r"estado del relevo|como va el protocolo de relevo", t):
            import relevo
            return relevo.resumen()

        # ── Enlace entre equipos ────────────────────────────────────────────
        if re.search(r"(estado de(l)? (los )?(enlace|equipos|nodos))|"
                     r"que equipos tienes|otros ordenadores", t):
            from cluster import Cluster
            if getattr(self, "cluster", None) is None:
                self.cluster = Cluster(self, log=self.log)
            return self.cluster.resumen()

        if re.search(r"(activa|enciende)( el)? enlace( entre equipos)?", t):
            from cluster import Cluster
            if getattr(self, "cluster", None) is None:
                self.cluster = Cluster(self, log=self.log)
            return self.cluster.start()

        # ── Ajuste fino del modelo ──────────────────────────────────────────
        if re.search(r"puedes afinar(te)?|ajuste fino|entrenar (tu|el) modelo|lora|"
                     r"estado del afinado|cuanto has aprendido de mi|"
                     r"cuánto has aprendido de mí", t):
            import afinar
            resumen_afinado = afinar.resumen(log=self.log)
            info = afinar.comprobar(log=lambda *a: None)
            if info.get("gpu"):
                resumen_afinado += f" GPU: {info['gpu']} con {info['vram_gb']} GB."
            return resumen_afinado

        if re.search(r"exporta (tu|el) (historial|dataset)|prepara el entrenamiento|"
                     r"af[ií]nate|aprende de m[ií]|entr[eé]nate conmigo", t):
            import afinar
            datos = afinar.estado(log=lambda *a: None)
            ruta = afinar.exportar(log=self.log)
            guion = afinar.guion(ruta, log=self.log)
            aviso = ""
            if not datos["suficiente"]:
                aviso = (f" Aún somos pocos datos ({datos['conversaciones']} de "
                         f"{datos['minimo']}): el resultado sería flojo.")
            return (f"Dataset y guion listos, señor: {os.path.basename(ruta)} y "
                    f"{os.path.basename(guion)}, en la carpeta Afinado. "
                    f"{datos['equipo']['recomendacion']}{aviso}")

        # ── Perfiles de contexto ────────────────────────────────────────────
        m_perfil = re.search(r"(?:modo|perfil) (trabajo|juego|noche|invitado|normal)|"
                             r"(?:ponte|pon) en modo (trabajo|juego|noche|invitado|normal)", t)
        if m_perfil:
            import perfiles
            nombre = m_perfil.group(1) or m_perfil.group(2)
            if nombre == "normal":
                return perfiles.restaurar(self, log=self.log)
            return perfiles.activar(self, nombre, log=self.log)

        if re.search(r"que perfil (tienes|esta activo|está activo)|en que modo estas", t):
            import perfiles
            e = perfiles.estado()
            return (f"Perfil {e['perfil']}, señor: {e['descripcion']}. "
                    f"Puedo cambiar a: {', '.join(x for x in e['disponibles'] if x != e['perfil'])}.")

        # ── Valoraciones y aprendizaje ──────────────────────────────────────
        if re.search(r"como lo estoy haciendo|que tal lo haces|"
                     r"informe de valoraciones|acierto", t):
            import feedback
            return feedback.informe(log=self.log)

        # ── Micrófonos y altavoces ──────────────────────────────────────────
        if re.search(r"que microfonos tienes|lista de microfonos|"
                     r"que dispositivos de audio", t):
            import audio_dispositivos
            return audio_dispositivos.frase_microfonos(self, log=self.log)

        m_mic = re.search(r"usa el microfono (\d+)", t)
        if m_mic:
            import audio_dispositivos
            return audio_dispositivos.elegir(self, int(m_mic.group(1)), log=self.log)

        if re.search(r"prueba el microfono|me oyes bien|comprueba el microfono", t):
            import audio_dispositivos
            return audio_dispositivos.probar(self, log=self.log)

        # ── Rendimiento ─────────────────────────────────────────────────────
        if re.search(r"por que tardas|cuanto tardas|rendimiento|"
                     r"donde se va el tiempo|latencia", t):
            import metricas
            return metricas.informe()

        if re.search(r"cuanto (has )?gastado|coste de la voz|gasto de elevenlabs", t):
            import metricas
            datos = metricas.resumen()
            return (f"Llevo {datos['caracteres_elevenlabs']} caracteres de voz en la "
                    f"nube, señor: unos {datos['coste_voz_estimado_usd']:.2f} dólares "
                    "estimados. La voz local no cuesta nada.")

        # ── Inventario de habilidades autogeneradas ─────────────────────────
        if re.search(r"que habilidades (has )?escrito|habilidades autogeneradas|"
                     r"quien escribio tus habilidades", t):
            import autoskills
            return autoskills.inventario()

        # ── Parte del día y preparación anticipada ──────────────────────────
        if re.search(r"parte del dia|parte de la mañana|resumen del dia|"
                     r"ponme al dia|que tal va todo|buenos dias jarvis", t):
            import orquestador
            return orquestador.parte_de_manana(self, log=self.log)

        if re.search(r"preparame lo de|prepara lo que viene|"
                     r"que viene ahora|preparate para", t):
            import orquestador
            return orquestador.preparar_para(self, log=self.log)

        if re.search(r"^(si|sí|hazlo|adelante|preparalo|prepáralo)$", t.strip()):
            # Respuesta corta a una oferta de preparación: solo actúa si la
            # última frase mía fue justo esa oferta.
            ultima = (self._contexto[-1][1] if self._contexto else "")
            if "suele pedirme" in ultima:
                import orquestador
                return orquestador.ejecutar_preparacion(self, log=self.log)

        # ── Actualización con vuelta atrás ──────────────────────────────────
        if re.search(r"hay actualizaciones tuyas|tienes version nueva|"
                     r"busca actualizaciones de ti", t):
            import actualizar
            datos = actualizar.hay_novedades(log=self.log)
            if not datos.get("hay"):
                return f"Estoy al día, señor: {datos.get('motivo', '')}."
            return (f"Hay {datos['commits']} cambios nuevos, señor. Dígame "
                    "«actualízate» y los aplico; si algo falla vuelvo atrás solo.")

        if re.search(r"actualizate|actualízate|instala tu actualizacion", t):
            import actualizar
            return actualizar.actualizar(log=self.log)

        if re.search(r"vuelve a la version anterior|deshaz la actualizacion", t):
            import actualizar
            return actualizar.volver(log=self.log)

        # ── Arranque automático ─────────────────────────────────────────────
        if re.search(r"instalate como servicio|arranca (siempre )?con el (pc|equipo)|"
                     r"quiero que arranques solo", t):
            import servicio
            return servicio.instalar(al_arrancar_equipo="equipo" in t, log=self.log)

        if re.search(r"como arrancas|estado del (servicio|arranque)", t):
            import servicio
            return servicio.resumen(log=self.log)

        if re.search(r"no arranques solo|quita el arranque automatico", t):
            import servicio
            return servicio.quitar(log=self.log)

        # ── Analista: escribe un programa, lo ejecuta y corrige sus errores ──
        m_anal = re.search(r"(?:analiza|calcula con codigo|calcula con código|"
                           r"escribe un programa (?:que|para)|resuelvelo con codigo|"
                           r"hazme un analisis de|haz un analisis de)\s+(.+)", t)
        if m_anal:
            import analista
            peticion = texto.strip()
            resultado = analista.resolver(self, peticion, log=self.log)
            return analista.frase(resultado)

        if re.search(r"que analisis has hecho|ultimos analisis|últimos análisis", t):
            import analista
            return analista.historial()

        # ── Misiones: objetivos grandes que se trabajan solos ───────────────
        m_mision = re.search(r"(?:mision|misión|encargate de|encárgate de|"
                             r"ocupate de|ocúpate de|proyecto:)\s+(.+)", t)
        if m_mision:
            import mision
            objetivo = m_mision.group(1).strip()
            if getattr(self, "mision_piloto", None) is None:
                self.mision_piloto = mision.Piloto(self, log=self.log)
            if self.mision_piloto.en_curso():
                return "Ya tengo una misión en marcha, señor. Dígame «para la misión» si quiere cambiarla."
            pasos = mision.planificar(self, objetivo, log=self.log)
            if not pasos:
                return "No he sabido dividir eso en pasos, señor. ¿Me lo concreta un poco más?"
            m = mision.Mision(objetivo, pasos)
            self.mision_actual = m
            self.mision_piloto.lanzar(m)
            return ("Me pongo con ello, señor: " + f"{len(pasos)} pasos — "
                    + "; ".join(p[:40] for p in pasos[:4])
                    + ". Le aviso al terminar; puede pedirme el parte cuando quiera.")

        if re.search(r"(?:como va|qué tal va|que tal va)( la)? mision|"
                     r"parte de la mision|parte de la misión", t):
            import mision
            m = getattr(self, "mision_actual", None)
            if m is None:
                return "No tengo ninguna misión en marcha, señor."
            return mision.parte(m)

        if re.search(r"para la mision|detén la misión|deten la mision|cancela la mision", t):
            if getattr(self, "mision_piloto", None) is None:
                return "No hay ninguna misión que detener, señor."
            return self.mision_piloto.detener()

        if re.search(r"que misiones has hecho|historial de misiones", t):
            import mision
            return mision.historial()

        # ── Aprender viendo: grabar una rutina y repetirla luego ────────────
        if re.search(r"(?:aprende esto|mira lo que hago|fijate en lo que hago|"
                     r"aprende viendome|graba lo que hago)", t):
            import demostracion
            if getattr(self, "grabadora", None) is None:
                self.grabadora = demostracion.Grabadora(log=self.log)
            return self.grabadora.empezar()

        if re.search(r"^(?:ya esta|ya está|listo|hasta aqui|hasta aquí|"
                     r"deja de mirar|termina de aprender)$", t.strip()):
            import demostracion
            grabadora = getattr(self, "grabadora", None)
            if grabadora is None or not grabadora.grabando:
                return None       # no estaba aprendiendo: que siga el flujo normal
            pasos = grabadora.terminar()
            if not pasos:
                return "No he visto ningún paso que aprender, señor."
            self._rutina_pendiente = pasos
            return (f"He aprendido {len(pasos)} pasos, señor. ¿Cómo la llamo? "
                    "Dígame «llámala ...» y la guardo.")

        m_nombre = re.search(r"(?:llamala|llámala|guardala como|guárdala como|"
                             r"se llama)\s+(.+)", t)
        if m_nombre and getattr(self, "_rutina_pendiente", None):
            import demostracion
            nombre = m_nombre.group(1).strip().strip('«»."')
            demostracion.guardar(nombre, self._rutina_pendiente, log=self.log)
            pasos = len(self._rutina_pendiente)
            self._rutina_pendiente = None
            return (f"Guardada como «{nombre}», señor: {pasos} pasos. "
                    f"Dígame «haz {nombre}» cuando quiera que la repita.")

        m_rutina = re.search(r"(?:haz|repite|ejecuta) (?:la rutina |lo de )?(.+)", t)
        if m_rutina:
            import demostracion
            nombre = m_rutina.group(1).strip()
            if any(nombre.lower() in r["nombre"].lower() or
                   set(nombre.lower().split()) & set(r["nombre"].lower().split())
                   for r in demostracion.listar()):
                return demostracion.repetir(nombre, log=self.log)

        if re.search(r"que rutinas (sabes|conoces|tienes)|que has aprendido viendome", t):
            import demostracion
            return demostracion.resumen()

        # -- Ojos permanentes: mirar la pantalla y ofrecerse si hay atasco ---
        if re.search(r"vigila mi pantalla|mira mi pantalla siempre|"
                     r"quedate pendiente|qu[eé]date pendiente|"
                     r"est[ae] pendiente de (?:mi )?pantalla", t):
            import observador
            if getattr(self, "observador", None) is None:
                self.observador = observador.Observador(self, log=self.log)
            return self.observador.start()

        if re.search(r"deja de (?:vigilar|mirar) (?:mi )?pantalla|"
                     r"no mires mi pantalla|deja de estar pendiente", t):
            if getattr(self, "observador", None) is None:
                return "No estaba mirando su pantalla, señor."
            return self.observador.stop()

        if re.search(r"que ves(?: ahora)?(?: en mi pantalla)?$|"
                     r"mira (?:ahora )?la pantalla|revisa mi pantalla ahora", t):
            import observador
            if getattr(self, "observador", None) is None:
                self.observador = observador.Observador(self, log=self.log)
            ok, motivo = self.observador.disponible()
            if not ok:
                return f"No puedo mirar, señor: {motivo}."
            aviso = self.observador.mirar()
            return aviso or "No veo ningún error en su pantalla ahora mismo, señor."

        if re.search(r"estas vigilando|est[aá]s vigilando|estado de la vigilancia", t):
            obs = getattr(self, "observador", None)
            if obs is None or not obs.estado()["activo"]:
                return ("No estoy mirando su pantalla, señor. Dígame «vigila mi "
                        "pantalla» y estaré pendiente sin molestarle.")
            e = obs.estado()
            return (f"Pendiente de su pantalla, señor: {e['miradas']} revisiones y "
                    f"{e['ofrecimientos']} avisos. Ahora está en «{e['ventana_actual']}».")

        # -- Voz propia: neuronal, local y distinta por personalidad ---------
        if re.search(r"instala tu voz|instala la voz|descarga tu voz|"
                     r"quiero (?:que tengas )?(?:una )?voz (?:propia|de verdad|mejor)", t):
            import voz_propia
            m_voz = re.search(r"voz ([a-z]{2}_[A-Z]{2}-[\w-]+)", texto or "")
            objetivo = m_voz.group(1) if m_voz else voz_propia.voz_de(
                getattr(self, "nombre_agente", "jarvis").lower(), self)
            return voz_propia.instalar(objetivo, log=self.log)

        m_usa_voz = re.search(r"(?:usa|ponte|cambia a) la voz ([\w.\- ]+)", t)
        if m_usa_voz:
            import voz_propia
            pedida = m_usa_voz.group(1).strip().strip('.«»"')
            agente = getattr(self, "nombre_agente", "JARVIS").lower()
            # «usa la voz de ultron» cambia la de esa personalidad, no la mia.
            m_quien = re.search(r"\bde (jarvis|ultron)\b", pedida)
            if m_quien:
                agente = m_quien.group(1)
                pedida = pedida.replace(m_quien.group(0), "").strip()
            candidatas = [v for v in voz_propia.CATALOGO
                          if pedida.lower() in v.lower()] or [pedida]
            return voz_propia.elegir(self, agente, candidatas[0], log=self.log)

        if re.search(r"que voces tienes|qu[eé] voces tienes|estado de (?:tu |la )?voz|"
                     r"con que voz hablas|qu[eé] voz usas", t):
            import voz_propia
            return voz_propia.resumen(self)

        m_clonar = re.search(r"clona (?:mi |la )?voz(?: de)? (.+\.wav)", t)
        if m_clonar:
            import voz_propia
            return voz_propia.clonar(m_clonar.group(1).strip(), log=self.log)

        # -- Entrar desde fuera de casa --------------------------------------
        if re.search(r"act[ií]vate en remoto|acceso remoto|"
                     r"quiero (?:poder )?(?:entrar|conectarme|hablarte) desde fuera|"
                     r"que pueda (?:entrar|conectarme) desde (?:fuera|la calle|el trabajo)|"
                     r"publica(?:te)? en la red privada", t):
            import remoto
            if re.search(r"quita|desactiva|apaga|deja de", t):
                return remoto.desactivar(log=self.log)
            return remoto.activar(log=self.log)

        if re.search(r"quita el acceso remoto|desactiva el acceso remoto|"
                     r"deja de estar (?:en remoto|publicado)", t):
            import remoto
            return remoto.desactivar(log=self.log)

        if re.search(r"(?:puedo|podria|podría) (?:entrar|conectarme) desde fuera|"
                     r"estas en remoto|estás en remoto|estado del acceso remoto|"
                     r"(?:que|qué) aparatos tengo (?:en la red privada|en tailscale)|"
                     r"como te alcanzo desde fuera", t):
            import remoto
            return remoto.resumen()

        if re.search(r"public[aá](?:lo|te)? en internet|abre(?:te)? a internet|"
                     r"que se pueda entrar desde internet", t):
            import remoto
            confirmado = bool(re.search(r"confirmo|s[eé] lo que hago|adelante", t))
            return remoto.publicar_en_internet(confirmado=confirmado, log=self.log)

        # -- Emparejar el telefono con la interfaz web -----------------------
        if re.search(r"(?:por que|por qué|porque) no (?:se )?conecta (?:mi |el )?"
                     r"(?:movil|móvil|telefono|teléfono)|"
                     r"no (?:me )?carga (?:la interfaz|la pagina|la página|el chat) "
                     r"(?:en |d)el (?:movil|móvil|telefono|teléfono)|"
                     r"no puedo emparejar (?:el |mi )?(?:movil|móvil|telefono|teléfono)", t):
            import red_movil
            motivos = red_movil.diagnostico()
            cabeza = red_movil.resumen()
            if not motivos:
                return (cabeza + " Si aún así no entra, compruebe que el teléfono "
                        "está en ese mismo WiFi.")
            return cabeza + " " + " ".join(f"{m['que']} {m['hacer']}" for m in motivos[:2])

        if re.search(r"abre el puerto (?:del|para el) (?:movil|móvil|telefono|teléfono)|"
                     r"abre el cortafuegos|abre el firewall", t):
            import red_movil
            return red_movil.abrir_firewall(log=self.log)

        if re.search(r"(?:cual|cuál) es (?:tu|mi) (?:ip|direccion|dirección)|"
                     r"(?:donde|dónde) me encuentra el (?:movil|móvil|telefono|teléfono)|"
                     r"como me conecto desde el (?:movil|móvil|telefono|teléfono)|"
                     r"(?:enseñame|ensename|dame) el (?:qr|codigo qr|código qr)", t):
            import red_movil
            return red_movil.resumen()

        # -- El movil como una extension mas ---------------------------------
        _movil = r"(?:mi |el )?(?:movil|móvil|telefono|teléfono|celular)"

        if re.search(r"(?:como esta|cómo está|estado de|que tal esta) " + _movil
                     + r"|bateria de(?:l)? " + _movil
                     + r"|que bateria tiene " + _movil
                     + r"|qué batería tiene " + _movil, t):
            import movil
            return movil.resumen()

        if re.search(r"(?:que|qué) notificaciones (?:tengo|hay)(?: en " + _movil + r")?", t):
            import movil
            hay, motivo = movil.disponible()
            if not hay:
                return f"No tengo el teléfono a mano, señor: {motivo}."
            avisos = movil.notificaciones()
            if not avisos:
                return "Ninguna notificación en el teléfono, señor."
            return "En el teléfono, señor: " + "; ".join(
                f"{a['app']}, {a['titulo']}: {a['texto'][:70]}" for a in avisos[:5]) + "."

        if re.search(r"(?:donde|dónde) (?:esta|está) " + _movil
                     + r"|haz sonar " + _movil + r"|encuentra " + _movil, t):
            import movil
            sonando = movil.encontrar()
            sitio = movil.ubicacion()
            if sitio:
                sonando += (f" La última posición que tenía es {sitio['lat']:.4f}, "
                            f"{sitio['lon']:.4f}.")
            return sonando

        m_app_movil = re.search(r"abre (?:la app |la aplicacion |la aplicación )?"
                                r"([\w .\-]+?) en " + _movil, t)
        if m_app_movil:
            import movil
            return movil.abrir_app(m_app_movil.group(1).strip())

        if re.search(r"conecta " + _movil + r" por wifi|empareja " + _movil, t):
            import movil
            return movil.emparejar_wifi(log=self.log)

        if re.search(r"(?:como|cómo) conecto " + _movil + r"|configura " + _movil, t):
            import movil
            return movil.instrucciones()

        m_wa = re.search(r"(?:mandale|mándale|envia|envía|escribe)(?:le)? un "
                         r"(?:whatsapp|wasap|mensaje) a ([^:,]+)[:,] *(.+)", t)
        if m_wa:
            import movil
            preparado = movil.preparar_whatsapp(m_wa.group(1).strip(),
                                                m_wa.group(2).strip())
            if preparado["ok"]:
                self._whatsapp_pendiente = preparado
            return preparado["frase"]

        if re.search(r"^(?:envialo|envíalo|mandalo|mándalo|dale a enviar)$", t.strip()):
            pendiente = getattr(self, "_whatsapp_pendiente", None)
            if not pendiente:
                return "No tengo ningún mensaje preparado, señor."
            import movil
            self._whatsapp_pendiente = None
            return movil.enviar_preparado()

        m_regla = re.search(r"(?:avisame|avísame|dime) cuando (?:me )?(?:escriba|"
                            r"llegue algo de|me llame|escriban de) ([^,]+)"
                            r"(?:, *(?:y )?(.+))?$", t)
        if m_regla:
            import movil
            if getattr(self, "puente_movil", None) is None:
                self.puente_movil = movil.Puente(self, log=self.log)
            respuesta = self.puente_movil.añadir(m_regla.group(1).strip(),
                                                 (m_regla.group(2) or "").strip())
            if not self.puente_movil.estado()["activo"]:
                arranque = self.puente_movil.start()
                if "Pendiente" not in arranque:
                    respuesta += " " + arranque
            return respuesta

        if re.search(r"vigila " + _movil + r"|est[ae] pendiente de(?:l)? " + _movil, t):
            import movil
            if getattr(self, "puente_movil", None) is None:
                self.puente_movil = movil.Puente(self, log=self.log)
            return self.puente_movil.start()

        if re.search(r"deja de (?:vigilar|mirar) " + _movil, t):
            if getattr(self, "puente_movil", None) is None:
                return "No estaba mirando el teléfono, señor."
            return self.puente_movil.stop()

        if re.search(r"(?:que|qué) avisos (?:tengo|hay) del " + _movil
                     + r"|reglas del " + _movil, t):
            import movil
            puente = getattr(self, "puente_movil", None)
            if puente is None:
                puente = self.puente_movil = movil.Puente(self, log=self.log)
                puente.cargar()
            reglas = puente.estado()["reglas"]
            if not reglas:
                return ("No tengo ningún aviso del teléfono, señor. Dígame "
                        "«avísame cuando me escriba el banco».")
            return "Del teléfono le aviso de: " + "; ".join(
                r["filtro"] + (f" (y {r['accion']})" if r.get("accion") else "")
                for r in reglas) + "."

        if re.search(r"que avisos tienes|avisos pendientes|que has detectado", t):
            if getattr(self, "proactivo", None) is None:
                return "El motor proactivo está apagado ahora mismo."
            eventos = self.proactivo.get_events(unack_only=True)
            if not eventos:
                return f"Nada que reportar, {trato}Todo en orden.".strip()
            return "Tengo estos avisos: " + "; ".join(
                f"{e.title}: {e.message[:70]}" for e in eventos[:5]) + "."

        if re.search(r"como me (ves|notas)|cómo me (ves|notas)|como me escuchas|que tal me oyes", t):
            e = self._estado_animo
            if not e.get("ts"):
                return "Aún no he analizado su voz en esta sesión."
            return (f"Le noto tensión {e['estres']:.0%} y fatiga {e['fatiga']:.0%}, "
                    f"con confianza {e['confianza']:.0%} en la medida.")
        return None

    # ── CLASIFICADOR DE INTENCIONES (aprende de órdenes reales) ─────────────
    def _aprender_intencion(self, texto: str):
        """Guarda (frase, habilidad que la atendió) como ejemplo de entrenamiento.

        El clasificador venía con una lista de ejemplos escritos a mano. Estos
        son órdenes reales del señor, con sus muletillas y su forma de hablar,
        que es justo lo que hace útil al modelo.
        """
        try:
            habilidad = getattr(self.skills, "ultima_habilidad", "") if self.skills else ""
            if not habilidad or not texto:
                return
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                "intencion", habilidad, texto[:200], gravedad="dato",
                agente=getattr(self, "nombre_agente", "JARVIS"))
        except Exception:
            pass

    def entrenar_intenciones(self) -> str:
        """Reentrena el clasificador local con las órdenes ya ejecutadas."""
        if getattr(self, "cognition", None) is None or self.cognition.ml is None:
            return ("No tengo el motor de intenciones disponible. "
                    "Requiere scikit-learn instalado.")
        try:
            from storage import get_storage
            filas = get_storage(log=self.log).eventos_recientes(2000, tipo="intencion")
        except Exception as e:
            return f"No pude leer el historial de órdenes: {e}"
        ejemplos = [(f["detalle"], f["titulo"]) for f in filas
                    if f.get("detalle") and f.get("titulo")]
        if len(ejemplos) < 20:
            return (f"Solo tengo {len(ejemplos)} órdenes registradas. "
                    "Con al menos veinte podré entrenar algo que sirva.")
        clases = len({e[1] for e in ejemplos})
        if clases < 2:
            return "Todas las órdenes registradas son del mismo tipo; no hay nada que distinguir."
        ok = self.cognition.ml.entrenar(ejemplos)
        if ok:
            return (f"Clasificador reentrenado con {len(ejemplos)} órdenes suyas "
                    f"y {clases} tipos distintos.")
        return "El entrenamiento no salió bien; lo he registrado en el log."

    def _pista_intencion(self, texto: str) -> str:
        """Sugerencia del clasificador para el cerebro cuando nada la reconoció."""
        try:
            if getattr(self, "cognition", None) is None:
                return ""
            ml = self.cognition.ml
            if ml is None:
                return ""
            r = ml.clasificar(texto)
            if not r or r.get("confianza", 0) < 0.5:
                return ""
            return (f"[Intención probable según el clasificador local: {r['intencion']} "
                    f"(confianza {r['confianza']}). Si procede, ofrécela como acción.]")
        except Exception:
            return ""

    # ── PARALINGÜÍSTICA: la voz del señor manda sobre la de Jarvis ──────────
    def _aplicar_paralinguistica(self, resultado):
        """Traduce estrés/fatiga detectados en la voz a comportamiento real.

        Sin esto el análisis era decorativo: se registraba en el log y nada
        cambiaba. Ahora un señor cansado recibe una voz más lenta y estable, y
        una sugerencia de descanso (como mucho una cada veinte minutos, para
        que la atención no se vuelva insistencia).
        """
        if resultado is None:
            return
        try:
            estres = float(getattr(resultado, "stress_level", 0.0) or 0.0)
            fatiga = float(getattr(resultado, "fatigue_level", 0.0) or 0.0)
            arousal = float(getattr(resultado, "arousal", 0.0) or 0.0)
            valencia = float(getattr(resultado, "valence", 0.0) or 0.0)
            confianza = float(getattr(resultado, "confidence", 0.0) or 0.0)
        except Exception as e:
            self.log(f"Paralingüística ilegible: {e}")
            return

        # Patrón temporal (idea 3): suaviza el ruido de una sola frase con lo
        # que el señor suele marcar a esta hora/día de la semana.
        try:
            from cognition import paralinguistica_patron as _plp
            _mix = _plp.mezclar(estres, fatiga, arousal, valencia, confianza,
                                log=self.log)
            estres, fatiga = _mix["estres"], _mix["fatiga"]
            arousal, valencia = _mix["arousal"], _mix["valencia"]
            confianza = _mix["confianza"]
            if _mix.get("patron"):
                self.log(f"[PARALING] patrón temporal aplicado "
                         f"({_mix.get('muestras_franja')} lecturas de la franja)")
        except Exception as e:
            self.log(f"[PARALING] patrón no disponible: {e}")

        self._estado_animo = {"estres": round(estres, 2), "fatiga": round(fatiga, 2),
                              "arousal": round(arousal, 2), "valencia": round(valencia, 2),
                              "confianza": round(confianza, 2), "ts": time.time()}

        # Ritmo de la voz: más lento con fatiga o tensión, algo más vivo si el
        # señor viene acelerado y contento.
        if fatiga > 0.6:
            self._tts_rate = -2
        elif estres > 0.6:
            self._tts_rate = -1
        elif arousal > 0.75 and valencia >= 0:
            self._tts_rate = 1
        else:
            self._tts_rate = 0
        # Voz más estable (menos expresiva, menos invasiva) cuando hay tensión.
        self._tts_estabilidad = 0.78 if (estres > 0.6 or fatiga > 0.6) else 0.5

        if estres > 0.7 or fatiga > 0.7:
            try:
                from storage import get_storage
                get_storage().registrar_evento(
                    "estado_animo",
                    "Tensión o fatiga altas en la voz del señor",
                    f"estres={estres:.2f} fatiga={fatiga:.2f} confianza={confianza:.2f}",
                    gravedad="aviso", agente=getattr(self, "nombre_agente", "JARVIS"))
            except Exception:
                pass

        ahora = time.time()
        if fatiga > 0.7 and (ahora - self._ultimo_consejo_descanso) > 1200:
            self._ultimo_consejo_descanso = ahora
            self.tts_queue.put("Señor, le noto cansado. Si quiere, hacemos una pausa.")
            self._atenuar_entorno()

    def _atenuar_entorno(self):
        """Baja las luces si el señor lo autorizó (preferencia, nunca por sorpresa)."""
        try:
            if (self.get_pref("paralinguistica_luces") or "").strip() != "1":
                return
            if self.skills and hasattr(self.skills, "_prender_apagar_habitacion"):
                self.skills._prender_apagar_habitacion(False)
                self.log("[PARALING] Luces atenuadas por fatiga detectada.")
        except Exception as e:
            self.log(f"[PARALING] No pude atenuar el entorno: {e}")

    def _contexto_estado(self) -> str:
        """Aviso para el cerebro cuando el estado del señor debe cambiar el tono."""
        e = self._estado_animo
        if not e.get("ts") or (time.time() - e["ts"]) > 600:
            return ""
        partes = []
        if e["fatiga"] > 0.6:
            partes.append("cansado: sé breve y no propongas tareas largas")
        if e["estres"] > 0.6:
            partes.append("tenso: ve al grano y evita el humor")
        if e["arousal"] > 0.75 and e["valencia"] > 0.2:
            partes.append("animado: puedes ser algo más expresivo")
        if not partes:
            return ""
        return "[Estado del señor por su voz: " + "; ".join(partes) + "]"

    @staticmethod
    def _norm_eco(s: str) -> str:
        s = (s or "").lower()
        return "".join(c for c in s if c.isalnum() or c == " ")

    # Órdenes de sistema que el señor repite tal cual. JARVIS las cita en sus
    # propias respuestas («dígame cancela el apagado»), así que el detector de
    # eco las tomaba por su propia voz y las tiraba: la orden repetida no
    # llegaba nunca a ejecutarse.
    _ORDENES_DIRECTAS = frozenset((
        "apaga", "apagar", "apagate", "apágate", "apagado", "reinicia",
        "reiniciar", "reinicio", "cancela", "cancelar", "bloquea", "bloquear",
        "suspende", "suspender", "hiberna", "hibernar", "duerme",
    ))

    def _es_eco(self, texto: str) -> bool:
        """Detector de eco (isair echo_detection): si lo que «of» suena como mi
        propia última frase TTS, se descarta para no autoactivarse."""
        if not texto:
            return False
        t = self._norm_eco(texto)
        if not t:
            return False
        if self._ORDENES_DIRECTAS & set(t.split()):
            return False
        from difflib import SequenceMatcher
        for prev in self._tts_hist:
            p = self._norm_eco(prev)
            if not p:
                continue
            # Coincidencia por inclusión: cuenta como eco si el fragmento es
            # largo (cuatro palabras o más: nadie da órdenes citando media
            # frase mía) o si ocupa buena parte de lo dicho. Antes bastaba con
            # que la frase del señor apareciera en cualquier punto de un
            # párrafo mío, así que órdenes cortas que yo había nombrado de
            # pasada desaparecían sin dejar rastro.
            def _es_fragmento(corto, largo):
                return len(corto.split()) >= 4 or len(corto) >= 0.45 * len(largo)

            if t in p and _es_fragmento(t, p):
                return True
            if p in t and _es_fragmento(p, t):
                return True
            if SequenceMatcher(None, t, p).ratio() > 0.62:
                return True
        return False

    @property
    def voz_windows_silenciada(self) -> bool:
        """True si la voz local de Windows esta muteada (preferencia guardada)."""
        if self._voz_windows_silenciada is None:
            try:
                self._voz_windows_silenciada = (self.get_pref("voz_windows") or "").strip() == "off"
            except Exception:
                self._voz_windows_silenciada = False
        return self._voz_windows_silenciada

    def silenciar_voz_windows(self, silenciar: bool = True) -> str:
        """Activa o desactiva la voz local de Windows y lo recuerda."""
        self._voz_windows_silenciada = bool(silenciar)
        try:
            self.set_pref("voz_windows", "off" if silenciar else "on")
        except Exception as e:
            self.log(f"No pude guardar la preferencia de voz: {e}")
        if silenciar:
            try:
                self.stop_speaking()
            except Exception:
                pass
            return ("Voz de Windows silenciada, señor. Seguiré respondiendo por "
                    "escrito y por la voz del navegador.")
        return "Voz de Windows reactivada, señor."

    # Ordenes de voz para el mute. Se consultan antes que nada para que
    # funcionen aunque el resto del pipeline este ocupado o fallando.
    _RE_MUTE = re.compile(
        r"\b(?:silencia|silenciar|calla|callate|mutea|mutear|mute|apaga|desactiva|"
        r"quita)\b[^.]{0,30}?\b(?:voz|audio|sonido|tts)\b[^.]{0,25}?"
        r"\b(?:windows|local|del\s+pc|sistema)\b|"
        r"\b(?:silencia|mutea|apaga|desactiva|quita)\s+(?:la\s+)?"
        r"(?:voz|audio)\s+(?:de\s+)?windows\b|"
        r"\bmodo\s+silencio\b|\bsin\s+voz\b", re.IGNORECASE)
    _RE_UNMUTE = re.compile(
        r"\b(?:activa|activar|enciende|reactiva|devuelve|pon|quita\s+el\s+silencio|"
        r"desmutea|desmutear)\b[^.]{0,30}?\b(?:voz|audio|sonido|tts)\b|"
        r"\bvuelve\s+a\s+hablar\b|\bya\s+puedes\s+hablar\b", re.IGNORECASE)

    def _control_voz(self, texto: str):
        """Devuelve una respuesta si el texto era una orden de mute, o None."""
        t = re.sub(r"[áàä]", "a", (texto or "").lower())
        t = re.sub(r"[éèë]", "e", t)
        t = re.sub(r"[íìï]", "i", t)
        t = re.sub(r"[óòö]", "o", t)
        t = re.sub(r"[úùü]", "u", t)
        if self._RE_MUTE.search(t):
            return self.silenciar_voz_windows(True)
        if self._RE_UNMUTE.search(t):
            return self.silenciar_voz_windows(False)
        return None

    def _voz_piper_activa(self) -> bool:
        try:
            with open(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "voz.json"), encoding="utf-8") as f:
                d = json.load(f)
            v = (d.get("voice") or d.get("voz") or "").strip().lower()
            return v == "piper"
        except Exception:
            return False

    def dictado_activo(self) -> bool:
        """Modo dictado (isair dictation): la voz se escribe, no se responde."""
        try:
            with open(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "dictado.json"), encoding="utf-8") as f:
                return bool(json.load(f).get("activo"))
        except Exception:
            return False

    def dictar(self, texto: str) -> bool:
        """Escribe el texto transcrito en la app enfocada (portapapeles + Ctrl+V)."""
        try:
            texto = (texto or "").strip()[:5000]
            if not texto:
                return False
            tmp = os.path.join(tempfile.gettempdir(), "jarvis_dictado.txt")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(texto)
            ps = f"Get-Content -LiteralPath '{tmp}' -Raw -Encoding UTF8 | Set-Clipboard"
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=30, creationflags=0x08000000)
            time.sleep(0.4)
            import pyautogui
            pyautogui.hotkey("ctrl", "v")
            return True
        except Exception as e:
            self.log(f"Dictado falló: {e}")
            return False

    def _warmup_ollama(self):
        """Warm-up (isair warm_up): precarga el modelo local en RAM."""
        try:
            base = (self._cerebro.get("proveedores") or [{}])[0].get("base_url", "")
            if "11434" not in base and "localhost" not in base and "127.0.0.1" not in base:
                return
            modelo = (self._cerebro.get("proveedores") or [{}])[0].get("modelo", "")
            if not modelo:
                return
            import urllib.request
            data = json.dumps({"model": modelo, "prompt": "hola", "stream": False,
                               "keep_alive": "30m"}).encode()
            req = urllib.request.Request(base.replace("/v1", "").rstrip("/") + "/api/generate",
                                         data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30):
                pass
            self.log("Modelo local precalentado (warm-up ok).")
        except Exception as e:
            self.log(f"Warm-up omitido: {e}")

    def _mantener_caliente(self):
        """Ping periódico a Ollama para que no descargue el modelo.

        Ollama libera el modelo a los cinco minutos de inactividad. Como el
        señor no habla cada cinco minutos, casi toda pregunta pagaba la
        recarga. Un ping de dos tokens cada cuatro minutos la evita.
        """
        import urllib.request
        base = self.base_url.replace("/v1", "")
        minutos = float(os.getenv("JARVIS_CALIENTE_MINUTOS", "4"))
        if minutos <= 0:
            return
        time.sleep(90)
        while True:
            try:
                cuerpo = json.dumps({
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ok"}],
                    "stream": False, "keep_alive": "30m",
                    "options": {"num_predict": 1},
                }).encode("utf-8")
                peticion = urllib.request.Request(
                    f"{base}/api/chat", data=cuerpo,
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(peticion, timeout=30).read()
            except Exception:
                pass          # sin cerebro no pasa nada: se reintenta luego
            time.sleep(minutos * 60)

    def _precargar_dictado(self):
        """Carga el modelo de dictado en segundo plano, no en la primera frase."""
        if (self.get_pref("stt_local") or "1") == "0":
            return
        time.sleep(12)
        try:
            import wave as _wave
            import tempfile as _tmp
            with _tmp.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                ruta = f.name
            with _wave.open(ruta, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
                w.writeframes(b"\x00\x00" * 8000)     # medio segundo de silencio
            with open(ruta, "rb") as f:
                self._reconocer_local(f.read())
            os.unlink(ruta)
            self.log("[STT] Modelo de dictado precargado.")
        except Exception as e:
            self.log(f"[STT] No pude precargar el dictado: {e}")

    def _reconocer_local(self, wav_bytes) -> str | None:
        """Transcribe sin salir del equipo (faster-whisper o whisper.cpp).

        Hasta ahora la voz del señor viajaba SIEMPRE a Google
        (recognize_google): sin internet no había dictado, y cada frase salía
        del PC. Con esto el dictado funciona offline y es más fiel con el
        acento; si no hay ningún motor local instalado, devuelve None y la
        cadena sigue como antes.
        """
        if self._stt_local is False:
            return None
        try:
            if self._stt_local is None:
                from faster_whisper import WhisperModel
                tam = os.getenv("JARVIS_WHISPER_MODELO", "base")
                # Por defecto usaba 4 hilos y búsqueda por haz de 5. Medido en
                # este equipo (12 núcleos): 7,9 s por frase. Con todos los
                # hilos y haz 1 baja a 4,1 s, y el filtro de voz recorta los
                # silencios, que es donde se va la mitad del tiempo.
                hilos = int(os.getenv("JARVIS_WHISPER_HILOS", "0")) or (os.cpu_count() or 4)
                self.log(f"[STT] Cargando modelo local «{tam}» con {hilos} hilos...")
                self._stt_local = WhisperModel(tam, device="cpu", compute_type="int8",
                                               cpu_threads=hilos, num_workers=1)
            import tempfile as _tmp
            ruta = None
            try:
                with _tmp.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                    f.write(wav_bytes)
                    ruta = f.name
                segmentos, _info = self._stt_local.transcribe(
                    ruta, language="es", beam_size=1, vad_filter=True,
                    condition_on_previous_text=False,
                    vad_parameters={"min_silence_duration_ms": 350})
                texto = " ".join(seg.text for seg in segmentos).strip()
                if texto:
                    self.log(f"[STT] Local: {texto[:60]}")
                return texto or None
            finally:
                if ruta:
                    try:
                        os.unlink(ruta)
                    except Exception:
                        pass
        except ImportError:
            # Segundo intento: whisper.cpp compilado (jarvis_whisper.py)
            try:
                from jarvis_whisper import get_whisper_stt
                motor = get_whisper_stt(log=self.log)
                if motor.is_ready():
                    texto = motor.transcribe(wav_bytes)
                    if texto:
                        return texto
            except Exception as e:
                self.log(f"[STT] whisper.cpp no utilizable: {e}")
            self._stt_local = False
            self.log("[STT] Sin motor local (pip install faster-whisper). Uso la nube.")
            return None
        except Exception as e:
            self._stt_local = False
            self.log(f"[STT] Motor local desactivado tras fallar: {e}")
            return None

    def _reconocer_nim(self, wav_bytes) -> str | None:
        """ASR español gratis vía NVIDIA NIM (canary-1b) si hay clave NIM configurada."""
        try:
            clave = ""
            for p in (self._cerebro.get("proveedores") or []):
                if "nvidia" in (p.get("nombre") or "").lower() or \
                   "integrate.api.nvidia.com" in (p.get("url") or ""):
                    clave = (p.get("clave") or "").strip()
                    break
            if not clave:
                return None
            import io
            files = {"file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")}
            data = {"model": "nvidia/canary-1b"}
            r = requests.post(
                "https://integrate.api.nvidia.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {clave}"},
                files=files, data=data, timeout=40)
            if r.status_code == 200:
                txt = (r.json().get("text") or "").strip()
                if txt:
                    self.log("STT (NIM): " + txt)
                    return txt
            self.log(f"NIM ASR: {r.status_code} {r.text[:100]}")
        except Exception as e:
            self.log(f"NIM ASR fallo: {e}")
        return None

    # ── LLM ──────────────────────────────────────────────────────────────────
    def process_text_stream(self, text: str, state_callback=None, speak_server: bool = True, skip_skills: bool = False) -> str:
        """Punto de entrada unico. GARANTIZA una respuesta: nunca propaga una
        excepcion ni devuelve None, para que ninguna interfaz (web, movil,
        Telegram, escritorio) se quede sin contestacion."""
        try:
            r = self._process_text_stream(text, state_callback=state_callback,
                                          speak_server=speak_server, skip_skills=skip_skills)
            return r if (r and str(r).strip()) else "Señor, no he sabido qué responder a eso."
        except Exception as e:
            self.log(f"[JARVIS] Fallo no controlado con «{str(text)[:60]}»: "
                     f"{type(e).__name__}: {e}")
            try:
                import traceback
                self.log(traceback.format_exc())
            except Exception:
                pass
            return (f"Señor, algo ha fallado al procesar eso ({type(e).__name__}: "
                    f"{str(e)[:120]}). Lo he anotado en jarvis_log/session.log.")

    def _process_text_stream(self, text: str, state_callback=None, speak_server: bool = True, skip_skills: bool = False) -> str:
        if not text or not str(text).strip():
            return "Señor, no recibí ningún texto."
        text = str(text)

        # Wake natural (isair intent_judge): «¿qué opinas, Jarvis?» -> «¿qué opinas?»
        t_limpio = re.sub(r"\bjarvis\b", " ", text, flags=re.IGNORECASE)
        if t_limpio.strip() != text.strip():
            t_limpio = re.sub(r"\s{2,}", " ", t_limpio).strip(" ,.;:¿?¡!")
            if t_limpio:
                text = t_limpio

        # Consultas compuestas (isair planner): «apaga la luz y dame el clima»
        partes = self._partir_consulta(text)
        if len(partes) > 1:
            respuestas = []
            for p in partes:
                try:
                    r = self._procesar(p, state_callback=state_callback, speak_server=speak_server, skip_skills=skip_skills) or "Señor, no entendí esa parte."
                except Exception as e:
                    r = f"Señor, fallé con «{p[:40]}» ({str(e)[:60]})"
                respuestas.append(r)
            return " ".join(respuestas)

        return self._procesar(text, state_callback=state_callback, speak_server=speak_server)

    @staticmethod
    def _parece_orden(texto: str) -> bool:
        """¿Esto pide una acción, o es conversación?

        Sirve para no pagar una llamada extra al modelo en cada «buenos días».
        Basta con que aparezca uno de los verbos de acción que el proyecto ya
        tenía catalogados (ACCIONES) o una petición explícita de hacer algo.
        """
        t = (texto or "").lower()
        if len(t) < 4:
            return False
        if any(palabra in t for palabra in ACCIONES):
            return True
        return bool(re.search(r"\b(hazme|haz|puedes|podrias|podrías|necesito que|"
                              r"quiero que|ponme|prepara|programa|organiza|"
                              r"encargate|encárgate)\b", t))

    def _partir_consulta(self, texto: str) -> list:
        """Divide «haz X y haz Y» solo si ambas partes parecen órdenes reales."""
        if " y " not in texto.lower():
            return [texto]
        partes = [p.strip() for p in texto.split(" y ") if p.strip()]
        if len(partes) < 2:
            return [texto]
        marcadas = [sum(1 for c in ACCIONES if c in p.lower()) for p in partes]
        if sum(1 for m in marcadas if m) < 2:
            return [texto]
        return partes[:3]

    def _procesar(self, text: str, state_callback=None, speak_server: bool = True, skip_skills: bool = False) -> str:
        # ── Mute de la voz local: lo primero, para que funcione siempre ──
        try:
            _r_voz = self._control_voz(text)
        except Exception as e:
            self.log(f"[JARVIS] control de voz fallo: {e}")
            _r_voz = None
        if _r_voz:
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": _r_voz})
            return _r_voz

        # ── Confirmación de una herramienta que quedó a la espera ───────────
        if getattr(self, "_tool_pendiente", None):
            try:
                import permisos
                if permisos.es_afirmacion(text):
                    import herramientas_llm
                    respuesta = herramientas_llm.ejecutar_pendiente(self, log=self.log)
                    if respuesta:
                        self.history.append({"role": "user", "content": text})
                        self.history.append({"role": "assistant", "content": respuesta})
                        if speak_server:
                            self.tts_queue.put(respuesta)
                        return respuesta
                else:
                    # El señor dijo otra cosa: la acción pendiente se descarta.
                    self._tool_pendiente = None
                    self.log("[HERRAMIENTAS] acción pendiente descartada (sin confirmar)")
            except Exception as e:
                self.log(f"[HERRAMIENTAS] confirmación falló: {e}")
                self._tool_pendiente = None

        # ── Ventana de arrepentimiento: «no» justo después de actuar ────────
        try:
            import arrepentimiento
            if arrepentimiento.es_arrepentimiento(text):
                respuesta = arrepentimiento.atender(self, log=self.log)
                self.history.append({"role": "user", "content": text})
                self.history.append({"role": "assistant", "content": respuesta})
                if speak_server:
                    self.tts_queue.put(respuesta)
                return respuesta
        except Exception as e:
            self.log(f"[JARVIS] Ventana de arrepentimiento falló: {e}")

        # ── Valoración del señor sobre lo último que hice ───────────────────
        try:
            import feedback
            signo, correccion = feedback.clasificar_frase(text)
            if signo:
                ultima_orden, ultima_respuesta = (self._contexto[-1]
                                                  if self._contexto else ("", ""))
                respuesta = feedback.anotar(signo, ultima_orden, ultima_respuesta,
                                            correccion,
                                            agente=getattr(self, "nombre_agente", "JARVIS"),
                                            log=self.log)
                self.history.append({"role": "user", "content": text})
                self.history.append({"role": "assistant", "content": respuesta})
                if speak_server:
                    self.tts_queue.put(respuesta)
                return respuesta
        except Exception as e:
            self.log(f"[JARVIS] Valoración falló: {e}")

        # ── Órdenes sobre el propio asistente (registro, motores, estado) ──
        try:
            _r_meta = self._ordenes_meta(text)
        except Exception as e:
            self.log(f"[JARVIS] órdenes meta fallaron: {e}")
            _r_meta = None
        if _r_meta:
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": _r_meta})
            if speak_server:
                self.tts_queue.put(_r_meta)
            return _r_meta

        # ── Agencia de especialistas: prioridad máxima (frases inequívocas) ──
        if getattr(self, "agentes_ia", None) is not None:
            try:
                _r_ag = self.agentes_ia.handle(text)
            except Exception as _e_ag:
                self.log(f"[JARVIS] agentes_ia falló: {_e_ag}")
                _r_ag = None
            if _r_ag:
                self.history.append({"role": "user", "content": text})
                self.save_to_memory("user", text)
                self.history.append({"role": "assistant", "content": _r_ag})
                self.save_to_memory("assistant", _r_ag)
                if len(self.history) > 17:
                    self.history = [self.history[0]] + self.history[-16:]
                if speak_server:
                    self.tts_queue.put(_r_ag)
                self._registrar_cognicion(text, _r_ag)
                self._contexto_append(text, _r_ag)
                jarvis_grafo.aprender(text)
                return _r_ag

        # ── Segundo par de ojos antes de lo irreversible ────────────────────
        # Con el analista escribiendo programas y el piloto moviendo el ratón,
        # ya no todo pasa por una regex revisada a mano. Esto frena lo que no
        # tiene vuelta atrás y deja que el señor insista si sabe lo que hace.
        try:
            respuesta_freno = self._revisar_antes_de_actuar(text)
        except Exception as e:
            self.log(f"[JARVIS] El verificador falló: {e}")
            respuesta_freno = None
        if respuesta_freno:
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": respuesta_freno})
            if speak_server:
                self.tts_queue.put(respuesta_freno)
            return respuesta_freno

        # Habilidades del sistema (Sprint 2): si es un comando ejecutable,
        # responder al instante sin consumir el LLM.
        if skip_skills:
            skill_reply = None
        else:
            # Cada despachador va aislado: si una habilidad revienta, antes se
            # llevaba por delante toda la respuesta y JARVIS se quedaba mudo.
            # Ahora se registra el fallo y se pasa al siguiente (y al LLM).
            skill_reply = None
            # Los conectores van PRIMERO: solo reaccionan a menciones
            # explicitas (calendario, cita, reunion, evento), y si no fueran
            # antes, la agenda local de jarvis_skills se comeria la orden y el
            # evento nunca llegaria a Google Calendar.
            import metricas
            for nombre, despachador in (("conectores", getattr(self, "conectores", None)),
                                        ("habilidades", self.skills),
                                        ("control del PC", self.pc),
                                        ("mensajería", self.msg)):
                if skill_reply or despachador is None:
                    continue
                try:
                    with metricas.medir("habilidades", despachador=nombre):
                        skill_reply = despachador.handle(text)
                except Exception as e:
                    self.log(f"[JARVIS] El despachador de {nombre} fallo con "
                             f"«{text[:60]}»: {type(e).__name__}: {e}")
        if skill_reply:
            self.history.append({"role": "user", "content": text})
            self.save_to_memory("user", text)
            self.history.append({"role": "assistant", "content": skill_reply})
            self.save_to_memory("assistant", skill_reply)
            if len(self.history) > 17:
                self.history = [self.history[0]] + self.history[-16:]
            # Las habilidades también hablan (colas asíncronas, sin bloquear)
            if speak_server:
                self.tts_queue.put(skill_reply)
            # Acción reversible y grande: en vez de haber preguntado antes,
            # se abre una ventana corta para arrepentirse.
            try:
                import arrepentimiento
                if arrepentimiento.merece_ventana(text):
                    skill_reply = arrepentimiento.envolver(
                        skill_reply, skill_reply, log=self.log)
            except Exception as e:
                self.log(f"[JARVIS] No pude abrir la ventana: {e}")
            self._registrar_cognicion(text, skill_reply)
            self._aprender_intencion(text)
            # El grafo escribe en disco; hacerlo aquí retrasaba la respuesta.
            threading.Thread(target=jarvis_grafo.aprender, args=(text,),
                             daemon=True).start()
            self._contexto_append(text, skill_reply)
            return skill_reply

        # Memoria de preferencias (Sprint 2): aprender "recuerda que...",
        # "mi nombre es...", "me gusta..." sin pasar por el LLM.
        learned = self.remember_from(text)
        if learned:
            self.history.append({"role": "user", "content": text})
            self.save_to_memory("user", text)
            self.history.append({"role": "assistant", "content": learned})
            self.save_to_memory("assistant", learned)
            self._contexto_append(text, learned)
            jarvis_grafo.aprender(text)
            return learned

        # ── El cerebro con manos: tool-calling ──────────────────────────────
        # Si la frase suena a orden y ninguna habilidad la reconoció, dejamos
        # que el modelo use herramientas reales en vez de limitarse a describir
        # lo que haría. Solo entra aquí la cola larga: lo que cubren las regex
        # ya se resolvió arriba sin gastar un token.
        if os.getenv("JARVIS_TOOLS", "1") != "0" and self._parece_orden(text):
            try:
                import metricas
                from herramientas_llm import pensar_con_herramientas
                with metricas.medir("herramientas"):
                    resultado = pensar_con_herramientas(self, text, self.history, log=self.log)
            except Exception as e:
                self.log(f"[HERRAMIENTAS] No pude usarlas: {e}")
                resultado = None
            if resultado:
                respuesta, usadas = resultado
                respuesta = respuesta or ("Hecho, señor: " + ", ".join(usadas) + ".")
                self.history.append({"role": "user", "content": text})
                self.save_to_memory("user", text)
                self.history.append({"role": "assistant", "content": respuesta})
                self.save_to_memory("assistant", respuesta)
                if len(self.history) > 17:
                    self.history = [self.history[0]] + self.history[-16:]
                if speak_server:
                    self.tts_queue.put(respuesta)
                self._contexto_append(text, respuesta)
                jarvis_grafo.aprender(text)
                self.log(f"[HERRAMIENTAS] Orden resuelta con: {', '.join(usadas)}")
                return respuesta

        # Comandos del cerebro (Admin UI / FCC): «prueba tu cerebro» y «limpia tu memoria»
        if re.search(r"prueba tu cerebro|prueba tus proveedores|probar cerebro|probar la ia|prueba la ia", text, re.IGNORECASE):
            try:
                res = self.probar_cerebro()
                partes = [f"{p['nombre']}: {'ok' if p['ok'] else 'fallo'}" for p in res.get("proveedores", [])]
                base = "Señor, mi cerebro funciona correctamente: " if res.get("ok") else "Señor, tengo fallos de conexión: "
                return base + ", ".join(partes) + "."
            except Exception as e:
                return f"Señor, no pude probar el cerebro: {str(e)[:80]}"
        if re.search(r"limpia tu memoria|borra tu memoria|limpia tu historial", text, re.IGNORECASE):
            return self.limpiar_memoria()
        if re.search(r"cu[aá]nto (has |llevas )?gastad|gasto del cerebro|"
                     r"presupuesto|cuota del cerebro|gasto de (la )?ia", text, re.IGNORECASE):
            try:
                import presupuesto
                return presupuesto.informe()
            except Exception as e:
                return f"Señor, no pude consultar el gasto: {str(e)[:80]}"
        if re.search(r"nivel de (nuestra )?relaci[oó]n|qu[eé] tan bien nos "
                     r"(conocemos|llevamos)|cu[aá]nto (tiempo )?llevamos", text, re.IGNORECASE):
            try:
                import relacion
                return relacion.resumen(self)
            except Exception as e:
                return f"Señor, no pude calcularlo: {str(e)[:80]}"
        _m_img = re.search(r"(mira|analiza|describe|qu[eé] (dice|hay en|ves en))\s+"
                           r"(esta\s+|este\s+|el\s+|la\s+)?(imagen|foto|captura|"
                           r"pdf|documento)[:,]?\s*(.+\.(png|jpe?g|webp|gif|pdf|txt|md))",
                           text, re.IGNORECASE)
        if _m_img:
            try:
                import multimodal
                ruta = _m_img.group(6).strip()
                if ruta.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                    return multimodal.analizar_imagen(self, ruta, "", log=self.log)
                return multimodal.analizar_documento(self, ruta, "", log=self.log)
            except Exception as e:
                return f"Señor, no pude analizarlo: {str(e)[:100]}"
        _m_reu = re.search(r"(resume|procesa|transcribe)\s+(esta\s+|la\s+)?reuni[oó]n"
                           r"[:,]?\s*(.+\.(wav|mp3|m4a|ogg|flac))", text, re.IGNORECASE)
        if _m_reu:
            try:
                import reunion
                return reunion.procesar(self, _m_reu.group(3).strip(), log=self.log)
            except Exception as e:
                return f"Señor, no pude procesar la reunión: {str(e)[:100]}"
        _m_md = re.search(r"(apunta|anota|gu[aá]rda(te)?|recuerda) (esto )?en (tu )?"
                          r"memoria permanente(?: que)?[:,]?\s+(.+)", text, re.IGNORECASE)
        if _m_md:
            try:
                import memoria_proyecto
                return memoria_proyecto.anadir(_m_md.group(5))
            except Exception as e:
                return f"Señor, no pude apuntarlo: {str(e)[:80]}"
        _m_corr = re.search(r"\bno estoy (muy )?(cansad[oa]|tens[oa]|estresad[oa]|agobiad[oa])",
                            text, re.IGNORECASE)
        if _m_corr:
            try:
                from cognition import paralinguistica_patron as _plp
                return _plp.corregir(_m_corr.group(2), "menos", log=self.log)
            except Exception:
                pass
        if re.search(r"patr[oó]n de mi voz|c[oó]mo me ves|c[oó]mo me notas|"
                     r"como sueno a esta hora", text, re.IGNORECASE):
            try:
                from cognition import paralinguistica_patron as _plp
                return _plp.resumen(log=self.log)
            except Exception as e:
                return f"Señor, no pude consultarlo: {str(e)[:80]}"

        # Inyectar datos del sistema si el usuario pregunta por él
        stats_kw = ["cpu", "ram", "memoria", "sistema", "rendimiento",
                    "recursos", "temperatura", "disco", "batería"]
        if any(k in text.lower() for k in stats_kw):
            s = self.get_system_stats()
            inject = (
                f" [Datos actuales: CPU={s['cpu']}, "
                f"RAM={s['ram_used']} ({s['ram_pct']}), "
                f"Disco libre={s['disk_free']}, "
                f"Red↑={s['net_sent']} ↓={s['net_recv']}]"
            )
            user_msg = text + inject
        else:
            user_msg = text

        self.history.append({"role": "user", "content": user_msg})
        self.save_to_memory("user", user_msg)

        # Limitar ventana de contexto
        if len(self.history) > 17:
            self.history = [self.history[0]] + self.history[-16:]

        if not HAS_OPENAI:
            return f"Señor, no tengo acceso al modelo local; recibí: {text}"

        try:
            if not self._rate_limit_ok():
                return "Señor, he conversado mucho esta hora; descansemos un momento."
            resp = None
            ultimo_error = None
            # Contexto rodante (isair transcript buffer): últimas interacciones
            msgs = self.history
            if self._contexto:
                ctx = " | ".join(f"«{u}» -> «{r}»" for u, r in self._contexto)
                msgs = msgs + [{"role": "system", "content": "[Conversación reciente: " + ctx[:900] + "]"}]
            # ── Headroom: compresión de contexto reversible (ahorro de tokens) ──
            if os.getenv("HEADROOM_COMPRESS", "1") == "1" and len(msgs) > 4:
                try:
                    from headroom import compress as _hr_compress
                    _hr = _hr_compress(msgs)
                    _hr_msgs = getattr(_hr, "messages", None) or _hr
                    if _hr_msgs:
                        _antes = getattr(_hr, "tokens_before", None)
                        _desp = getattr(_hr, "tokens_after", None)
                        msgs = _hr_msgs
                        self.log(f"[JARVIS] headroom OK ({_antes}->{_desp} tokens).")
                except Exception as _e_hr:
                    self.log(f"[JARVIS] headroom omitido: {str(_e_hr)[:80]}")
            # Memoria-grafo (isair): hechos relacionados con la pregunta
            if re.search(r"que sabes (de|sobre)|quien es|quién es|conoces a|que recuerdas|que sabe", text, re.IGNORECASE):
                gctx = jarvis_grafo.consultar(text)
                if gctx:
                    msgs = msgs + [{"role": "system", "content": "[Memoria-grafo: " + gctx[:900] + "]"}]

            # El perfil activo manda sobre el tono y la longitud.
            try:
                import perfiles
                _instruccion = perfiles.instruccion_prompt(self)
                if _instruccion:
                    msgs = msgs + [{"role": "system", "content": _instruccion}]
            except Exception:
                pass

            # Nivel de relación: el tono evoluciona con el trato (idea 5).
            try:
                import relacion
                relacion.registrar_interaccion(self, text, log=self.log)
                _rel = relacion.instruccion_prompt(self)
                if _rel:
                    msgs = msgs + [{"role": "system", "content": _rel}]
            except Exception:
                pass

            # Memoria permanente (JARVIS.md): hechos y convenciones que siempre
            # deben estar presentes.
            try:
                import memoria_proyecto
                _mp = memoria_proyecto.contexto(log=self.log)
                if _mp:
                    msgs = msgs + [{"role": "system", "content": _mp}]
            except Exception:
                pass

            # Estado del señor leído en su voz: cambia el tono, no el contenido.
            _ctx_estado = self._contexto_estado()
            if _ctx_estado:
                msgs = msgs + [{"role": "system", "content": _ctx_estado}]

            # Pista del clasificador local: si el señor pidió algo que suena a
            # orden conocida pero ninguna habilidad la reconoció, el cerebro al
            # menos sabe por dónde iba. No decide nada: solo informa.
            _pista = self._pista_intencion(text)
            if _pista:
                msgs = msgs + [{"role": "system", "content": _pista}]

            # Mem0: búsqueda semántica en memoria tripartita
            if self.mem0:
                try:
                    mem0_results = self.mem0.search(text, limit=3)
                    if mem0_results:
                        mem0_ctx = " | ".join(r.get("memory", str(r))[:200] for r in mem0_results)
                        msgs = msgs + [{"role": "system", "content": "[Mem0 semántico: " + mem0_ctx[:900] + "]"}]
                except Exception as e:
                    self.log(f"Mem0 search error: {e}")

            import metricas
            _cronometro = metricas.medir("cerebro", modelo=self.model)
            _cronometro.__enter__()
            _nube_cortada = False
            for nombre, b_url, modelo, clave in self._proveedores():
                _local = ("localhost" in b_url) or ("127.0.0.1" in b_url)
                if not _local:
                    try:
                        import presupuesto
                        if not presupuesto.permite_nube():
                            self.log(f"[PRESUPUESTO] salto «{nombre}»: tope de gasto del día alcanzado")
                            _nube_cortada = True
                            continue
                    except Exception:
                        pass
                try:
                    cliente = self._cliente_llm(b_url, clave)
                    esfuerzo = self._esfuerzo_razonamiento(text)
                    es_kimi = ("moonshot" in b_url) or modelo.startswith("kimi-k3")
                    tope = int(os.getenv("JARVIS_MAX_TOKENS", "700"))
                    if es_kimi:
                        # Kimi K3 sólo acepta low/high/max (nunca "none"), y el
                        # razonamiento gasta del mismo presupuesto: sube el tope
                        # o piensa y se queda sin respuesta.
                        esfuerzo = {"none": "low", "low": "high"}.get(esfuerzo, esfuerzo)
                        tope = int(os.getenv("JARVIS_MAX_TOKENS_KIMI", "2048"))
                    self.log(f"Cerebro -> {nombre}: {modelo} @ {b_url} "
                             f"(razonamiento: {esfuerzo})")
                    # El presupuesto de tokens lo comparten el razonamiento y
                    # la respuesta. Con 200 tokens un modelo que piensa se
                    # quedaba SIN respuesta: pensaba y se acababa el turno.
                    comun = dict(model=modelo, messages=msgs,
                                 temperature=float(os.getenv("JARVIS_TEMPERATURA", "0.5")),
                                 max_tokens=tope, stream=True)
                    try:
                        resp = cliente.chat.completions.create(
                            **comun, extra_body={"reasoning_effort": esfuerzo})
                    except TypeError:
                        # SDK antiguo sin extra_body
                        resp = cliente.chat.completions.create(**comun)
                    except Exception as e_raz:
                        # Un proveedor que no entienda el parámetro no debe
                        # dejar al señor sin respuesta.
                        self.log(f"Sin control de razonamiento en {nombre}: {e_raz}")
                        resp = cliente.chat.completions.create(**comun)
                    self._cerebro_activo = nombre
                    break
                except Exception as e:
                    ultimo_error = e
                    self.log(f"Proveedor «{nombre}» falló: {e}")
                    resp = None
            if resp is None:
                if _nube_cortada and ultimo_error is None:
                    try:
                        import presupuesto
                        return presupuesto.aviso_corte()
                    except Exception:
                        pass
                return ("Señor, todos mis proveedores de cerebro fallaron. "
                        + (f"({str(ultimo_error)[:100]})" if ultimo_error else ""))
            
            try:
                _cronometro.__exit__(None, None, None)
            except Exception:
                pass
            _t_generacion = time.time()
            full_reply = ""
            buffer = ""
            think_done = False
            first_speech = True
            first_reply_sentence = True

            for chunk in resp:
                content = chunk.choices[0].delta.content or ""
                buffer += content

                if not think_done:
                    # Qwen3 emite su razonamiento entre <think>...</think>. Si
                    # vemos el cierre, descartamos todo lo anterior y nos
                    # quedamos con la respuesta limpia. Si el modelo no usa
                    # tags (modo silencioso), pasamos al modo "respuesta
                    # directa" tras consumir un prefijo razonable.
                    think_close = buffer.find("</think>")
                    if think_close != -1:
                        buffer = buffer[think_close + len("</think>"):]
                        # Limpia prefijos típicos: saltos de línea, comillas
                        # de arranque, espacio residual.
                        buffer = buffer.lstrip(" \n\r\t\"'`")
                        think_done = True
                    elif buffer.startswith("<think>"):
                        # Sigue dentro del bloque de pensamiento: limpiamos lo
                        # recibido hasta ahora para no acumular ruido.
                        buffer = ""
                    else:
                        # No hay tag de pensamiento. Si ya acumulamos suficiente
                        # contenido "limpio", empezamos a vocalizar.
                        if len(buffer) > 30 and "\n" in buffer:
                            think_done = True

                if think_done:
                    # Extraer oraciones completas
                    match = re.search(r'([.!?]+)', buffer)
                    if match:
                        idx = match.end()
                        sentence = buffer[:idx].strip()
                        buffer = buffer[idx:]
                        
                        if sentence:
                            if first_reply_sentence:
                                sentence = self._address_user_as_butler(sentence)
                                first_reply_sentence = False

                            # El tag se procesa y se quita ANTES de acumular la
                            # respuesta. Antes se acumulaba primero y solo se
                            # limpiaba la copia que iba a la voz, asi que en el
                            # movil y en el chat se leia literalmente
                            # «[OPEN:Bloc de notas]» en vez de una frase.
                            open_match = re.search(r"\[OPEN:([^\]]+)\]", sentence)
                            if open_match:
                                app_name = open_match.group(1).strip().lower()
                                sentence = re.sub(r"\[OPEN:[^\]]+\]", "", sentence).strip()
                                self._open_app(app_name)
                                sentence = self._frase_al_abrir(
                                    sentence, open_match.group(1).strip())

                            full_reply += sentence + " "
                            if first_speech and state_callback:
                                state_callback("speaking")
                                first_speech = False

                            if sentence:
                                if speak_server:
                                    self.tts_queue.put(sentence)

            # Flush remaining buffer
            if buffer.strip():
                sentence = buffer.strip()
                if first_reply_sentence:
                    sentence = self._address_user_as_butler(sentence)
                # Igual que arriba: limpiar el tag antes de acumular, no despues.
                open_match = re.search(r"\[OPEN:([^\]]+)\]", sentence)
                if open_match:
                    app_name = open_match.group(1).strip().lower()
                    sentence = re.sub(r"\[OPEN:[^\]]+\]", "", sentence).strip()
                    self._open_app(app_name)
                    sentence = self._frase_al_abrir(sentence, open_match.group(1).strip())
                full_reply += sentence
                if sentence:
                    if speak_server:
                        self.tts_queue.put(sentence)

            try:
                import metricas
                metricas.anotar("generacion", (time.time() - _t_generacion) * 1000,
                                caracteres=len(full_reply))
            except Exception:
                pass
            try:
                import presupuesto
                _ctx_txt = " ".join(m.get("content", "") for m in msgs
                                    if isinstance(m.get("content"), str))
                presupuesto.registrar_uso_estimado(self._cerebro_activo, modelo,
                                                   _ctx_txt, full_reply, log=self.log)
            except Exception:
                pass
            reply_clean = self._recortar_respuesta(full_reply.strip())
            self._marcar_uso()
            self.history.append({"role": "assistant", "content": reply_clean})
            self.save_to_memory("assistant", reply_clean)
            self._registrar_cognicion(text, reply_clean)
            self._contexto_append(text, reply_clean)
            self.log(f"Respuesta de texto lista: {len(reply_clean)} caracteres")
            return reply_clean

        except Exception as e:
            self.log(f"Error LLM: {e}")
            return "Señor, tengo un problema de conexión con mi núcleo cognitivo. Verifica que Ollama esté activo."

    @staticmethod
    def _frase_al_abrir(resto: str, app: str) -> str:
        """Frase con la que confirmar que se ha abierto una aplicacion.

        Al quitar el tag [OPEN:...] lo que suele quedar no es una frase sino
        un resto sin contenido («Señor,»), porque el modelo responde con el
        tag y poco mas. Devolver eso dejaba al usuario sin confirmacion, asi
        que si no queda una frase de verdad se construye una.
        """
        limpio = re.sub(r"^\s*se[ñn]or\s*[,.:;!¡¿?-]*\s*", "", resto,
                        flags=re.IGNORECASE)
        limpio = limpio.strip(" ,.;:-¡!¿?")
        if len(limpio) < 3:
            return f"Abriendo {app}, señor."
        return resto

    @staticmethod
    def _address_user_as_butler(text: str) -> str:
        """Garantiza el trato de mayordomo sin repetir el título innecesariamente."""
        if re.search(r"\bseñor\b", text, flags=re.IGNORECASE):
            return text
        return f"Señor, {text}"

    def _registrar_cognicion(self, user_text: str, reply: str):
        """Analítica asíncrona: almacena la interacción y etiqueta intención+cluster.

        Corre en un hilo daemon para que el flujo de respuesta jamás se
        ralentice; cualquier fallo aquí es invisible para el usuario."""
        if self.cognition is None:
            return
        try:
            def _trabajo():
                try:
                    intencion = cluster = None
                    r = self.cognition.clasificar_intencion(user_text)
                    if r:
                        intencion = f"{r['intencion']} ({r['confianza']:.2f})"
                    cluster = self.cognition.cluster.etiquetar(user_text)
                    self.cognition._db.registrar_interaccion(
                        user_text, reply, intencion=intencion, cluster=cluster)
                except Exception as e:
                    self.log(f"cognición: {e}")
            threading.Thread(target=_trabajo, daemon=True).start()
        except Exception:
            pass

    def _open_app(self, name: str):
        """Intenta abrir una aplicación por nombre.

        Pasa por el ejecutor común: si la aplicación no existe, el proceso
        muere al instante y queda registrado en vez de dar por buena la orden.
        """
        cmd = APP_MAP.get(name, name)
        try:
            import ejecutor
            ok, error, _ = ejecutor.lanzar(cmd, origen="abrir_app", orden=name,
                                           verificar_ms=400, log=self.log,
                                           agente=getattr(self, "nombre_agente", "JARVIS"))
            self.log(f"Abriendo: {cmd}" if ok else f"No pude abrir {cmd}: {error}")
        except Exception as e:
            self.log(f"No pude abrir {cmd}: {e}")

    # ── STT ──────────────────────────────────────────────────────────────────
    def listen(self, timeout=6, phrase_limit=12) -> str | None:
        if not HAS_SR or not self.rec:
            self.log("SpeechRecognition no disponible.")
            return None
        try:
            with sr.Microphone() as src:
                self.log("Calibrando ambiente...")
                self.rec.adjust_for_ambient_noise(src, duration=0.4)
                self.log("Escuchando... (habla ahora)")
                audio = self.rec.listen(src, timeout=timeout, phrase_time_limit=phrase_limit)
                self.log("Transcribiendo...")

                # Guardar audio temporal para análisis paralingüístico
                wav_data = audio.get_wav_data()
                tmp_audio = None
                if self.signal_processor:
                    try:
                        import tempfile
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                            f.write(wav_data)
                            tmp_audio = f.name
                    except Exception:
                        pass

                # Orden: NIM (si está configurado) -> local (offline) -> Google.
                # Lo local va antes que la nube por privacidad y porque
                # funciona sin conexión; «stt_local=0» invierte la preferencia.
                text = self._reconocer_nim(wav_data)
                if not text and (self.get_pref("stt_local") or "1") != "0":
                    text = self._reconocer_local(wav_data)
                if not text:
                    text = self.rec.recognize_google(audio, language="es-ES")

                if self._es_eco(text):
                    self.log(f"Eco descartado: «{text[:40]}» era mi propia voz.")
                    return None

                # Análisis paralingüístico (stub Fase 1)
                if tmp_audio and self.signal_processor:
                    try:
                        result = self.signal_processor.analyze_paralinguistic(tmp_audio)
                        self.log(f"[PARALING] stress={result.stress_level:.2f} fatigue={result.fatigue_level:.2f} "
                                 f"arousal={result.arousal:.2f} valence={result.valence:.2f}")
                        self._aplicar_paralinguistica(result)
                    except Exception as e:
                        self.log(f"Paralingüística error: {e}")
                    finally:
                        try:
                            os.unlink(tmp_audio)
                        except Exception:
                            pass

                self.log(f"STT: {text}")
                return text
        except sr.WaitTimeoutError:
            self.log("Timeout: no se detectó voz.")
        except sr.UnknownValueError:
            self.log("No pude entender el audio.")
        except Exception as e:
            self.log(f"Error STT: {e}")
        return None

    # ── TTS ──────────────────────────────────────────────────────────────────
    def synthesize_and_play(self, text: str) -> bool:
        """Sintetiza sin bloquear las respuestas de texto.

        ElevenLabs es el proveedor preferido. Cuando la API no tiene crédito,
        rechaza la voz o falla la red, Windows SAPI mantiene a Jarvis hablando.
        """
        if not text or not text.strip():
            return False
        # Historial TTS para el detector de eco
        self._tts_hist.append(text[:300])
        if len(self._tts_hist) > 2:
            self._tts_hist = self._tts_hist[-2:]

        # Voz neuronal gratuita y offline (isair Piper): si está seleccionada,
        # se usa antes que ElevenLabs/SAPI.
        if self._voz_piper_activa():
            try:
                import jarvis_piper
                # Cada personalidad con su voz: JARVIS y ULTRON no pueden sonar
                # igual. voz_propia decide cuál según la preferencia guardada.
                try:
                    import voz_propia
                    voz = voz_propia.voz_de(
                        getattr(self, "nombre_agente", "jarvis").lower(), self)
                except Exception:
                    voz = jarvis_piper.DEFAULT_VOICE
                if not jarvis_piper.disponible(voz):
                    voz = jarvis_piper.DEFAULT_VOICE
                if jarvis_piper.hablar(text, voice_id=voz):
                    return True
                self.log("Piper no disponible; continúo con la cadena normal.")
            except Exception as e:
                self.log(f"Piper: {e}")

        if time.monotonic() < self._elevenlabs_disabled_until:
            self.log(f"ElevenLabs en pausa ({self._elevenlabs_failure_reason}); usando voz local.")
            return self._speak_with_windows(text)

        if not self.elevenlabs_key or "tu_api" in self.elevenlabs_key:
            self.log("ElevenLabs sin clave configurada; usando voz local.")
            return self._speak_with_windows(text)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.elevenlabs_key,
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": float(getattr(self, "_tts_estabilidad", 0.5)),
                               "similarity_boost": 0.8},
        }
        tmp = None
        try:
            self.log("ElevenLabs: solicitando audio...")
            with requests.post(url, json=payload, headers=headers, stream=True,
                               timeout=(5, 30)) as response:
                if not response.ok:
                    self._handle_elevenlabs_error(response.status_code)
                    return self._speak_with_windows(text)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    for chunk in response.iter_content(4096):
                        if chunk:
                            fp.write(chunk)
                    tmp = fp.name

            if not tmp or os.path.getsize(tmp) == 0:
                self.log("ElevenLabs devolvió audio vacío; usando voz local.")
                return self._speak_with_windows(text)

            self.log("Reproduciendo audio...")
            if HAS_PYGAME:
                pygame.mixer.music.load(tmp)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.music.unload()
            else:
                os.startfile(tmp)
            return True
        except Exception as e:
            self.log(f"ElevenLabs no disponible ({type(e).__name__}); usando voz local.")
            return self._speak_with_windows(text)
        finally:
            # pygame termina antes de este punto. Si Windows abrió un reproductor
            # externo, no se borra el temporal para no cortar el audio.
            if tmp and HAS_PYGAME:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _handle_elevenlabs_error(self, status_code: int):
        causes = {
            401: "clave o permisos no autorizados",
            402: "créditos o plan no disponibles",
            403: "acceso denegado para esta voz o modelo",
            404: "voz o modelo no encontrado",
            429: "límite de solicitudes alcanzado",
        }
        self._elevenlabs_failure_reason = causes.get(status_code, f"HTTP {status_code}")
        # Para errores de cuenta/configuración evitamos repetir una petición fallida
        # por cada oración. La próxima comprobación se hace dentro de cinco minutos.
        if status_code in {401, 402, 403, 404, 429}:
            # 429 es pasajero (límite por minuto); 401/402/403/404 son de
            # cuenta y no se arreglan solos: reintentarlos cada cinco minutos
            # solo añade un viaje de red fallido a una de cada pocas frases.
            espera = 300 if status_code == 429 else 6 * 3600
            self._elevenlabs_disabled_until = time.monotonic() + espera
            # Vaciar la cola de frases pendientes: todas se sintetizarán con la
            # voz local de Windows. Evita una cola de 5+ frases esperando a
            # una API que sabemos caída.
            self._flush_tts_queue()
        self.log(
            f"ElevenLabs HTTP {status_code}: {self._elevenlabs_failure_reason}. "
            "La respuesta continuará con voz local."
        )

    def _flush_tts_queue(self):
        """Drena la cola TTS descartando frases pendientes."""
        dropped = 0
        try:
            while True:
                self.tts_queue.get_nowait()
                self.tts_queue.task_done()
                dropped += 1
        except queue.Empty:
            pass
        if dropped:
            self.log(f"Cola TTS vaciada: {dropped} frases descartadas para evitar latencia acumulada.")

    def esta_hablando(self) -> bool:
        """True si hay voz sonando o frases en cola.

        La escucha continua lo consulta para saber si una frase del señor es
        una interrupción (y hay que callar) o una orden normal.
        """
        try:
            if not self.tts_queue.empty():
                return True
        except Exception:
            pass
        if HAS_PYGAME:
            try:
                return bool(pygame.mixer.music.get_busy())
            except Exception:
                return False
        return False

    def stop_speaking(self):
        """Interrupción (Sprint 2): detiene la voz y descarta frases pendientes."""
        self._flush_tts_queue()
        try:
            import voz_rapida
            voz_rapida.callar()
        except Exception:
            pass
        if HAS_PYGAME:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self.log("Voz interrumpida por el señor.")

    def _speak_with_windows(self, text: str) -> bool:
        """Voz local de Windows, con el motor cargado en este mismo proceso.

        Antes esto lanzaba un PowerShell nuevo por cada frase. Medido: 1,9
        segundos de arranque antes de que sonara nada, por frase. Con el motor
        SAPI en proceso la primera sílaba sale en 3 milisegundos.
        """
        if self.voz_windows_silenciada:
            self.log("Voz de Windows silenciada; la respuesta permanece en texto.")
            return False
        if self.tts_fallback not in {"windows", "sapi", "auto"}:
            self.log("Voz local desactivada; la respuesta permanece disponible en texto.")
            return False
        if platform.system() != "Windows":
            self.log("Voz local no disponible en este sistema; la respuesta permanece en texto.")
            return False

        # json.dumps inserta el texto como literal seguro en PowerShell. Se codifica
        # el comando completo para evitar problemas con tildes, comillas o símbolos.
        rate = max(-10, min(10, int(getattr(self, "_tts_rate", 0) or 0)))

        # Camino rápido: motor en proceso (pywin32/pyttsx3). Solo si falla se
        # usa el PowerShell de siempre, que sigue debajo intacto.
        try:
            import metricas
            import voz_rapida
            with metricas.medir("voz", motor=voz_rapida.estado().get("motor", "?")):
                if voz_rapida.hablar(text, velocidad=rate, log=self.log):
                    metricas.caracteres_hablados(text, proveedor="local")
                    return True
        except Exception as e:
            self.log(f"Voz rápida no disponible ({e}); uso PowerShell.")

        script = f"""
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $speaker.GetInstalledVoices()
$maleVoice = $voices |
    Where-Object {{ $_.VoiceInfo.Culture.Name -like 'es-*' -and $_.VoiceInfo.Gender -eq 'Male' }} |
    Select-Object -First 1
if (-not $maleVoice) {{
    $maleVoice = $voices |
        Where-Object {{ $_.VoiceInfo.Gender -eq 'Male' }} |
        Select-Object -First 1
}}
if ($maleVoice) {{ $speaker.SelectVoice($maleVoice.VoiceInfo.Name) }}
$speaker.Rate = {rate}
$speaker.Speak({json.dumps(text, ensure_ascii=False)})
"""
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.log("ElevenLabs no está disponible: reproduciendo con voz masculina local de Windows.")
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                check=True,
                creationflags=creationflags,
                timeout=45,
            )
            return True
        except (OSError, subprocess.SubprocessError) as e:
            self.log(f"No se pudo reproducir la voz local ({type(e).__name__}).")
            return False

    # ── RITUALES DE MAYORDOMO (Sprint 3) ─────────────────────────────────────
    def greeting(self) -> str:
        """Ritual de apertura: saludo según la hora del día."""
        h = time.localtime().tm_hour
        if 6 <= h < 12:
            saludo = "Buenos dias, señor"
        elif 12 <= h < 20:
            saludo = "Buenas tardes, señor"
        else:
            saludo = "Buenas noches, señor"
        s = self.get_system_stats()
        return (
            f"{saludo}. Todos los sistemas están operativos, "
            f"CPU al {s['cpu']} y {s['ram_used']} de memoria en uso. "
            "¿En qué puedo servirle hoy?"
        )

    def farewell(self) -> str:
        """Ritual de cierre: despedida de mayordomo."""
        return (
            "Entendido, señor. Ha sido un placer servirle. "
            "Permaneceré en espera por si necesita algo más."
        )

    def sleep_mode(self) -> str:
        """Ritual de descanso (Ojos Cerrados)."""
        return "Entendido. Estaré atento a cualquier necesidad, señor."

    def focus_mode(self) -> str:
        """Ritual de enfoque profundo."""
        return (
            "Muy bien, señor. Activo modo de enfoque: minimizo el HUD "
            "y solo responderé si me llama directamente."
        )

    # ── TELEMETRÍA ────────────────────────────────────────────────────────────
    @staticmethod
    def get_system_stats() -> dict:
        if psutil is None:
            return {"error": "psutil no instalado"}
        try:
            cpu  = psutil.cpu_percent(interval=None)
            cores = psutil.cpu_percent(interval=None, percpu=True)
            ram  = psutil.virtual_memory()
            net  = psutil.net_io_counters()
            disk = psutil.disk_usage("/")
            boot = psutil.boot_time()
            stats = {
                "cpu":       f"{cpu:.0f}%",
                "cpu_cores": [f"{c:.0f}" for c in cores],
                "ram_used":  f"{ram.used/1e9:.1f}GB",
                "ram_total": f"{ram.total/1e9:.0f}GB",
                "ram_pct":   f"{ram.percent:.0f}%",
                "net_sent":  f"{net.bytes_sent/1e6:.0f}MB",
                "net_recv":  f"{net.bytes_recv/1e6:.0f}MB",
                "disk_free": f"{disk.free/1e9:.0f}GB",
                "disk_total": f"{disk.total/1e9:.0f}GB",
                "uptime":    int(time.time() - boot),
            }
            try:
                tmp = psutil.sensors_temperatures()
                for sensor in tmp.values():
                    if sensor:
                        stats["temp"] = f"{sensor[0].current:.0f}°C"
                        break
            except Exception:
                stats["temp"] = "--"
            try:
                bat = psutil.sensors_battery()
                if bat:
                    stats["battery"] = {
                        "percent": bat.percent,
                        "plugged": bool(bat.power_plugged),
                    }
            except Exception:
                pass
            return stats
        except Exception:
            return {"cpu":"--","cpu_cores":[],"ram_used":"--","ram_total":"--",
                    "ram_pct":"--","net_sent":"--","net_recv":"--",
                    "disk_free":"--","disk_total":"--","uptime":0,"temp":"--"}

    # ── GENERACIÓN DE IMÁGENES ─────────────────────────────────────────────────
    def generate_image(self, prompt: str, folder: str = None) -> str:
        """
        Genera una imagen a partir de un prompt de texto y la guarda en la carpeta indicada.
        
        La estructura de carpetas es: Descargas/JARVIS/Imagenes/YYYY-MM-DD/nombre_archivo.png
        Se crea un historial en la base de datos SQLite.
        
        Args:
            prompt: Descripción de la imagen a generar (ej. "un asistente holográfico futurista")
            folder: Carpeta base personalizada (opcional, default usa Descargas del usuario)
            
        Returns:
            Ruta completa de la imagen guardada, o cadena vacía si falla
        """
        try:
            # Determinar carpeta base: usar Descargas del usuario o la proporcionada
            if folder is None:
                base_folder = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Imagenes")
            else:
                base_folder = os.path.join(os.path.expanduser(folder), "JARVIS", "Imagenes")
            
            # Crear estructura de carpetas: base_folder/YYYY-MM-DD/
            from datetime import datetime
            fecha_str = datetime.now().strftime("%Y-%m-%d")
            safe_prompt = re.sub(r"[^\w\s-]", "", prompt).strip().replace(" ", "_")[:50]
            filename = f"{fecha_str}/{safe_prompt}_{datetime.now().strftime('%H%M%S')}.png"
            
            base_dir = os.path.join(base_folder, filename)
            os.makedirs(os.path.dirname(base_dir), exist_ok=True)
            
            # Generar imagen usando Pillow (fallback local, sin necesidad de API externa)
            try:
                from PIL import Image as PILImage, ImageDraw, ImageFont
                img = PILImage.new('RGB', (512, 512), color = (73, 109, 137))
                # Añadir texto descriptivo a la imagen
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("arial.ttf", 18)
                except:
                    font = ImageFont.load_default()
                display_prompt = prompt[:40] + ("..." if len(prompt) > 40 else "")
                draw.text((10, 10), f"Jarvis: {display_prompt}", fill=(255, 255, 255), font=font)
                img.save(base_dir, "PNG")
            except Exception as e:
                self.log(f"Error generando imagen con Pillow: {e}")
                # Fallback: crear imagen de color sólido mínimo
                from PIL import Image as PILFallback
                img = PILFallback.new('RGB', (512, 512), color = (73, 109, 137))
                base_dir_final = os.path.join(os.path.dirname(base_dir), "placeholder.png")
                img.save(base_dir_final, "PNG")
                base_dir = base_dir_final
            
            # Guardar en historial de medios (tabla dedicada para no contaminar
            # el contexto conversacional del LLM).
            self.save_media_history("image", prompt, base_dir)
            
            self.log(f"Imagen generada y guardada: {base_dir}")
            return base_dir
            
        except Exception as e:
            self.log(f"Error crítico en generate_image: {e}")
            return ""