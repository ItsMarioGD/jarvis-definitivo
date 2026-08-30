#!/usr/bin/env python3
"""
jarvis_core.py - Nucleo cognitivo de Jarvis
STT + LLM (Qwen3 via Ollama local) + TTS (ElevenLabs) + Telemetria
"""
import base64, json, os, re, time, platform, subprocess, tempfile, threading, queue
import requests, psutil, sqlite3, socket
from dotenv import load_dotenv
from jarvis_skills import SkillsManager
import jarvis_grafo
import jarvis_redact

load_dotenv()

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
        self.model          = os.getenv("QWEN_MODEL", "qwen3:4b-instruct")
        self.tts_fallback   = os.getenv("JARVIS_TTS_FALLBACK", "windows").strip().lower()
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

        if HAS_OPENAI:
            kwargs = {"base_url": self.base_url, "api_key": self.api_key}
            if HAS_HTTPX:
                kwargs["timeout"] = Timeout(60.0, connect=10.0)
            self.llm = OpenAI(**kwargs)
        else:
            self.llm = None
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

        # Habilidades del sistema (Sprint 2): respuestas instantáneas sin LLM
        self.skills = SkillsManager(
            log=self.log,
            notify=lambda msg: self.tts_queue.put(msg),
            remember=self.add_reminder,
        )

        # Agencia de especialistas (agency-agents): modos activables por voz/texto
        try:
            from agentes_ia import AgentesIA as _AgentesIA
            self.agentes_ia = _AgentesIA(self, log=self.log)
        except Exception as _e_ag:
            self.agentes_ia = None
            self.log(f"[JARVIS] Agencia de agentes no disponible: {_e_ag}")

        # Bot de Telegram: arranca en proceso separado si hay token configurado
        try:
            tg_cfg = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "telegram.json")
            if os.path.exists(tg_cfg) and json.load(open(tg_cfg, encoding="utf-8")).get("token"):
                import subprocess as _sp
                bot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_bot.py")
                if os.path.exists(bot_path):
                    _sp.Popen(["pythonw", bot_path], cwd=os.path.dirname(os.path.abspath(__file__)),
                              creationflags=0x08000000)
                    self.log("Bot de Telegram lanzado en segundo plano.")
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

        self.history = [{"role": "system", "content": self.system_prompt}]
        self.load_memory_context()
        self.start_udp_listener()

        # Contexto rodante (isair transcript buffer): últimas 3 interacciones
        self._contexto = []
        # Historial TTS para el detector de eco (isair echo_detection)
        self._tts_hist = []
        # Calentar el modelo local para respuestas rápidas (isair warm_up)
        threading.Thread(target=self._warmup_ollama, daemon=True).start()

        self.hotkey_proc = None
        if os.path.exists("jarvis_hotkey.exe"):
            try:
                self.hotkey_proc = subprocess.Popen(["jarvis_hotkey.exe"], creationflags=0x08000000)
                self.log("Microservicio C++ Hotkey (Ctrl+Alt+J) iniciado en segundo plano.")
            except Exception as e:
                self.log(f"Error lanzando Hotkey C++: {e}")

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

    # Worker de TTS asíncrono para latencia ultrabaja
        self.tts_queue = queue.Queue()
        self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.tts_thread.start()

        # Saludo de arranque: si el señor activó el arranque automático,
        # Jarvis se presenta por voz cuando el sistema termina de cargar.
        threading.Thread(target=self._saludo_arranque, daemon=True).start()

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
        self.conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False, timeout=10)
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
            d["proveedores"] = [{
                "nombre": "ollama",
                "url": self.base_url,
                "modelo": self.model,
                "clave": self.api_key,
            }]
            try:
                os.makedirs(os.path.dirname(self._cerebro_path), exist_ok=True)
                with open(self._cerebro_path, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        return d

    def _proveedores(self) -> list:
        """[(nombre, base_url, modelo, clave), ...] orden de preferencia."""
        proveedores = []
        for p in (self._cerebro.get("proveedores") or []):
            url = (p.get("url") or "").strip().rstrip("/")
            modelo = (p.get("modelo") or "").strip()
            clave = (p.get("clave") or "").strip()
            nombre = (p.get("nombre") or url).strip() or "proveedor"
            if url and modelo:
                proveedores.append((nombre, url, modelo, clave or "ollama"))
        if not proveedores:
            proveedores = [("ollama", self.base_url.rstrip("/"), self.model, self.api_key)]
        return proveedores

    def _rate_limit_ok(self) -> bool:
        """Intervalo mínimo entre llamadas + tope por hora (cuotas gratuitas)."""
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
                r = cliente.chat.completions.create(
                    model=modelo,
                    messages=[{"role": "user", "content": "Responde solo: ok"}],
                    max_tokens=5,
                    temperature=0,
                    timeout=15)
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

    @staticmethod
    def _norm_eco(s: str) -> str:
        s = (s or "").lower()
        return "".join(c for c in s if c.isalnum() or c == " ")

    def _es_eco(self, texto: str) -> bool:
        """Detector de eco (isair echo_detection): si lo que «of» suena como mi
        propia última frase TTS, se descarta para no autoactivarse."""
        if not texto:
            return False
        t = self._norm_eco(texto)
        if not t:
            return False
        from difflib import SequenceMatcher
        for prev in self._tts_hist:
            p = self._norm_eco(prev)
            if not p:
                continue
            if t in p or p in t:
                return True
            if SequenceMatcher(None, t, p).ratio() > 0.62:
                return True
        return False

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
        if not text.strip():
            return "Señor, no recibí ningún texto."

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

        # Habilidades del sistema (Sprint 2): si es un comando ejecutable,
        # responder al instante sin consumir el LLM.
        if skip_skills:
            skill_reply = None
        else:
            skill_reply = self.skills.handle(text)
            if not skill_reply and self.pc is not None:
                # Control total del PC (Sprint "Más poder"): segundo despachador
                skill_reply = self.pc.handle(text)
            if not skill_reply and self.msg is not None:
                # Mensajería (WhatsApp/Gmail): tercer despachador
                skill_reply = self.msg.handle(text)
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
            self._registrar_cognicion(text, skill_reply)
            self._contexto_append(text, skill_reply)
            jarvis_grafo.aprender(text)
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

            # Mem0: búsqueda semántica en memoria tripartita
            if self.mem0:
                try:
                    mem0_results = self.mem0.search(text, limit=3)
                    if mem0_results:
                        mem0_ctx = " | ".join(r.get("memory", str(r))[:200] for r in mem0_results)
                        msgs = msgs + [{"role": "system", "content": "[Mem0 semántico: " + mem0_ctx[:900] + "]"}]
                except Exception as e:
                    self.log(f"Mem0 search error: {e}")

            for nombre, b_url, modelo, clave in self._proveedores():
                try:
                    cliente = OpenAI(base_url=b_url, api_key=clave)
                    self.log(f"Cerebro -> {nombre}: {modelo} @ {b_url}")
                    resp = cliente.chat.completions.create(
                        model=modelo,
                        messages=msgs,
                        temperature=0.72,
                        max_tokens=350,
                        stream=True
                    )
                    self._cerebro_activo = nombre
                    break
                except Exception as e:
                    ultimo_error = e
                    self.log(f"Proveedor «{nombre}» falló: {e}")
                    resp = None
            if resp is None:
                return ("Señor, todos mis proveedores de cerebro fallaron. "
                        + (f"({str(ultimo_error)[:100]})" if ultimo_error else ""))
            
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
                            full_reply += sentence + " "
                            if first_speech and state_callback:
                                state_callback("speaking")
                                first_speech = False
                            
                            # Procesar tags especiales como OPEN:app antes de hablar
                            open_match = re.search(r"\[OPEN:([^\]]+)\]", sentence)
                            if open_match:
                                app_name = open_match.group(1).strip().lower()
                                sentence = re.sub(r"\[OPEN:[^\]]+\]", "", sentence).strip()
                                self._open_app(app_name)
                                
                            if sentence:
                                if speak_server:
                                    self.tts_queue.put(sentence)

            # Flush remaining buffer
            if buffer.strip():
                sentence = buffer.strip()
                if first_reply_sentence:
                    sentence = self._address_user_as_butler(sentence)
                full_reply += sentence
                open_match = re.search(r"\[OPEN:([^\]]+)\]", sentence)
                if open_match:
                    app_name = open_match.group(1).strip().lower()
                    sentence = re.sub(r"\[OPEN:[^\]]+\]", "", sentence).strip()
                    self._open_app(app_name)
                if sentence:
                    if speak_server:
                        self.tts_queue.put(sentence)

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
        """Intenta abrir una aplicación por nombre."""
        cmd = APP_MAP.get(name, name)
        try:
            subprocess.Popen(cmd, shell=True)
            self.log(f"Abriendo: {cmd}")
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

                text = self._reconocer_nim(wav_data) or \
                    self.rec.recognize_google(audio, language="es-ES")

                if self._es_eco(text):
                    self.log(f"Eco descartado: «{text[:40]}» era mi propia voz.")
                    return None

                # Análisis paralingüístico (stub Fase 1)
                if tmp_audio and self.signal_processor:
                    try:
                        result = self.signal_processor.analyze_paralinguistic(tmp_audio)
                        self.log(f"[PARALING] stress={result.stress_level:.2f} fatigue={result.fatigue_level:.2f} "
                                 f"arousal={result.arousal:.2f} valence={result.valence:.2f}")
                        # TODO: Ajustar TTS/HA según resultado
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
                if jarvis_piper.hablar(text):
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
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
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
            self._elevenlabs_disabled_until = time.monotonic() + 300
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

    def stop_speaking(self):
        """Interrupción (Sprint 2): detiene la voz y descarta frases pendientes."""
        self._flush_tts_queue()
        if HAS_PYGAME:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self.log("Voz interrumpida por el señor.")

    def _speak_with_windows(self, text: str) -> bool:
        """Respaldo sin dependencias externas mediante Windows Speech API."""
        if self.tts_fallback not in {"windows", "sapi", "auto"}:
            self.log("Voz local desactivada; la respuesta permanece disponible en texto.")
            return False
        if platform.system() != "Windows":
            self.log("Voz local no disponible en este sistema; la respuesta permanece en texto.")
            return False

        # json.dumps inserta el texto como literal seguro en PowerShell. Se codifica
        # el comando completo para evitar problemas con tildes, comillas o símbolos.
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
$speaker.Rate = 0
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