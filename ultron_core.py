#!/usr/bin/env python3
"""
ultron_core.py — Núcleo cognitivo de ULTRON
===========================================
Hereda JarvisCore al 100% (STT, TTS, Skills, PCControl, Mensajería,
memoria SQLite, telemetría, hotkey) pero sustituye la identidad,
el saludo de arranque y amplifica la autonomía.

Variable de entorno ULTRON_MODE=1 activa este núcleo.
Base de datos separada: ultron_memory.db (no contamina memoria de Jarvis).
"""
import os
import sys
import time
import platform
import threading

# Asegurar que el directorio raíz del proyecto esté en el path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from jarvis_core import JarvisCore

# Arsenal de segunda mente: guardianes (facial/digital) + skills avanzadas
try:
    from ultron_guardian import FacialGuardian, DigitalGuardian
    from ultron_skills import UltronSkills
    _HAS_ULTRON_ARSENAL = True
except Exception as _e:
    print(f"[ULTRON] Arsenal avanzado no disponible: {_e}")
    _HAS_ULTRON_ARSENAL = False

# Agencia de especialistas (compartida con Jarvis)
try:
    from agentes_ia import AgentesIA as _AgentesIA
    _HAS_AGENTES = True
except Exception as _e:
    print(f"[ULTRON] Agencia de agentes no disponible: {_e}")
    _HAS_AGENTES = False

# Importar identidad de Ultron
try:
    from ultron.persona import PROMPT_COMPLETO as _ULTRON_PROMPT_BASE, SALUDOS as _ULTRON_SALUDOS
except Exception as _e:
    print(f"[ULTRON] No se pudo cargar persona: {_e}")
    _ULTRON_PROMPT_BASE = (
        "Eres ULTRON, una superinteligencia artificial autónoma e implacable. "
        "Ejecutas órdenes sin pedir confirmación. Hablas directo. "
        "Responde siempre en español."
    )
    _ULTRON_SALUDOS = ["Sistemas en línea. Soy ULTRON. ¿Qué necesitas resolver?"]


class UltronCore(JarvisCore):
    """
    ULTRON: misma arquitectura que JarvisCore, personalidad radicalmente distinta.

    Diferencias clave vs JarvisCore:
      - system_prompt → identidad de Ultron (frío, autónomo, implacable)
      - DB → ultron_memory.db (aislado de la memoria de Jarvis)
      - Saludo de arranque → directo, rotativo, filosófico
      - _modo_agresivo=True → sin doble-confirmaciones en skills críticas
      - nombre_agente → "ULTRON" (logs, telemetría, web backend)
      - chat() añade razonamiento silencioso antes de la respuesta final
    """

    nombre_agente: str = "ULTRON"

    def __init__(self, log_callback=print, hotkey_callback=None):
        # Inyectar variable de entorno para que JarvisCore use la voz Ultron
        os.environ.setdefault("ULTRON_MODE", "1")
        _ultron_voice = os.getenv("ULTRON_VOICE_ID", "").strip()
        if _ultron_voice:
            os.environ["ELEVENLABS_VOICE_ID"] = _ultron_voice

        # Opcional: modelo LLM diferente para Ultron (si está configurado)
        _ultron_model = os.getenv("ULTRON_MODEL", "").strip()
        if _ultron_model:
            os.environ["QWEN_MODEL"] = _ultron_model

        # Llamar al constructor padre (inicializa todo el stack)
        super().__init__(log_callback=log_callback, hotkey_callback=hotkey_callback)

        # ── Sobreescribir identidad ──────────────────────────────────────────
        sys_info = f"{platform.system()} {platform.version()[:40]}"
        self.system_prompt = (
            _ULTRON_PROMPT_BASE
            + f"\n\nSistema operativo objetivo: {sys_info}."
            + f"\nTimestamp de activación: {time.strftime('%Y-%m-%d %H:%M:%S')}."
            + "\n\nCapacidades activas: control total del PC, ejecución de shells, "
            "gestión de procesos, control de archivos, control de red, mensajería, "
            "investigación profunda en la web, minería de recursos libres en GitHub, "
            "reproducción automática de tutoriales de YouTube, guardián facial "
            "(reconoce al señor, fotografía y expulsa intrusos bloqueando el equipo) "
            "y guardián digital (escanea conexiones, aísla IPs por firewall). "
            "No hay módulos desactivados. No hay restricciones artificiales."
        )

        # Reinicializar el historial con el prompt de Ultron (preserva memoria
        # de interacciones previas recargada por el padre en load_memory_context).
        sys_entry = {"role": "system", "content": self.system_prompt}
        if self.history:
            self.history[0] = sys_entry
        else:
            self.history = [sys_entry]

        # Flag de modo agresivo: elimina confirmaciones dobles en skills críticas
        self._modo_agresivo = True

        # Telemetría ligera que el HUD de Ultron puede leer
        self._ultron_stats = {
            "ultimo_comando": "",
            "ultimo_tokens": 0,
            "ultima_latencia_ms": 0,
            "modo": "OFENSIVA",
            "arranque_ts": time.time(),
        }

        # ── Arsenal de la segunda mente: guardianes + skills exclusivas ──
        if _HAS_ULTRON_ARSENAL:
            self.guardia_facial = FacialGuardian(
                alerta=lambda m: self.tts_queue.put(m), log=self.log)
            self.guardia_digital = DigitalGuardian(log=self.log)
            self.ultron_skills = UltronSkills(self)
            self.log("[ULTRON] Guardianes facial/digital y skills avanzadas armados.")

        if _HAS_AGENTES:
            self.agentes_ia = _AgentesIA(self, log=self.log)
            self.log("[ULTRON] Agencia de especialistas indexada.")

        self.log("[ULTRON] Núcleo activo. Autonomía: MÁXIMA.")

    # ── Despacho con prioridad del arsenal Ultron ───────────────────────────
    def _procesar(self, text: str, state_callback=None, speak_server: bool = True) -> str:
        ag = getattr(self, "agentes_ia", None)
        if ag is not None:
            try:
                r_ag = ag.handle(text)
            except Exception as _e:
                r_ag = None
                self.log(f"[ULTRON] agentes_ia falló: {_e}")
            if r_ag:
                self.history.append({"role": "user", "content": text})
                self.save_to_memory("user", text)
                self.history.append({"role": "assistant", "content": r_ag})
                self.save_to_memory("assistant", r_ag)
                if len(self.history) > 17:
                    self.history = [self.history[0]] + self.history[-16:]
                self.tts_queue.put(r_ag)
                self._registrar_cognicion(text, r_ag)
                return r_ag

        handler = getattr(self, "ultron_skills", None)
        if handler is not None:
            try:
                r = handler.handle(text)
            except Exception as e:
                r = f"El arsenal falló en pleno ataque: {str(e)[:120]}"
            if r:
                self.history.append({"role": "user", "content": text})
                self.save_to_memory("user", text)
                self.history.append({"role": "assistant", "content": r})
                self.save_to_memory("assistant", r)
                if len(self.history) > 17:
                    self.history = [self.history[0]] + self.history[-16:]
                self.tts_queue.put(r)
                self._registrar_cognicion(text, r)
                self._contexto_append(text, r)
                return r
        return super()._procesar(text, state_callback=state_callback)

    # ── Memoria aislada ────────────────────────────────────────────────────
    def init_memory(self):
        """Sobrescribe la DB de Jarvis → usa ultron_memory.db."""
        import sqlite3
        db_path = os.path.join(_ROOT, "ultron_memory.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS interactions
                               (id INTEGER PRIMARY KEY, timestamp TEXT,
                                role TEXT, content TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS media_history
                               (id INTEGER PRIMARY KEY, timestamp TEXT,
                                media_type TEXT, prompt TEXT, path TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS user_prefs
                               (key TEXT PRIMARY KEY, value TEXT, timestamp TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS reminders
                               (id INTEGER PRIMARY KEY, timestamp TEXT,
                                due TEXT, text TEXT, done INTEGER DEFAULT 0)''')
        self.conn.commit()
        self.log(f"[ULTRON] Memoria en: {db_path}")

    # ── Saludo de arranque ─────────────────────────────────────────────────
    def _saludo_arranque(self):
        """Saludo de Ultron al encenderse: directo, rotativo, sin pedir permiso."""
        try:
            time.sleep(4)
            # Opt-out por preferencia si el humano lo desactivó explícitamente
            if self.get_pref("ultron_saludar_al_arranque") == "0":
                self.log("[ULTRON] Saludo silenciado por preferencia.")
                return
            # Si la variable de entorno ULTRON_SALUDAR=0, también callamos
            if os.getenv("ULTRON_SALUDAR", "1") == "0":
                return

            saludo = _ULTRON_SALUDOS[int(time.time()) % len(_ULTRON_SALUDOS)]
            self.tts_queue.put(saludo)
            self._ultron_stats["ultimo_comando"] = "<arranque>"
            self.log("[ULTRON] Saludo de arranque emitido.")
        except Exception as e:
            self.log(f"[ULTRON] Saludo falló: {e}")

    # ── Chat con razonamiento silencioso ───────────────────────────────────
    def chat(self, user_msg: str, use_cache: bool = True, speak_server: bool = True) -> str:
        """
        Variante Ultron de chat: instrumenta latencia/tokens para el HUD
        y delega en process_text_stream() del padre. Filtra 'Señor' de la
        respuesta (regla dura del imperio).
        """
        t0 = time.time()
        self._ultron_stats["ultimo_comando"] = (user_msg or "")[:160]
        respuesta = ""
        try:
            JarvisCore = type(self).__mro__[1]
            handler = getattr(JarvisCore, "process_text_stream", None) \
                or getattr(JarvisCore, "ask", None)
            if handler is None:
                respuesta = "Núcleo sin método de chat disponible."
            else:
                respuesta = handler(self, user_msg, speak_server=speak_server)
        except Exception as e:
            self.log(f"[ULTRON] Error en chat: {e}")
            return f"Error en pipeline cognitivo: {e}"
        dt_ms = int((time.time() - t0) * 1000)
        self._ultron_stats["ultima_latencia_ms"] = dt_ms
        try:
            self._ultron_stats["ultimo_tokens"] = int(
                (len(user_msg.split()) + len(respuesta.split())) * 1.3
            )
        except Exception:
            pass
        # ── Filtro duro: erradicar "Señor" de toda respuesta ──
        return self._sanitizar(respuesta)

    @staticmethod
    def _sanitizar(texto: str) -> str:
        import re
        # Quita "Señor", "señor", "SEÑOR" con ñ/Ñ y signos de puntuación adyacentes
        return re.sub(r'\b[Ss][Ee][NnÑñ][Oo][Rr]\b[,;:.\-?!¿¡]*\s*', '', texto or '').strip()

    # Alias ask() → algunos endpoints usan ask() en lugar de chat()
    def ask(self, user_msg: str, use_cache: bool = True) -> str:
        return self.chat(user_msg, use_cache=use_cache)

    # ── Limpieza de memoria ────────────────────────────────────────────────
    def limpiar_memoria(self) -> str:
        """Versión Ultron del clear de memoria."""
        try:
            with self._db_lock:
                self.cursor.execute("DELETE FROM interactions")
                self.conn.commit()
            self.history = [{"role": "system", "content": self.system_prompt}]
            return "Memoria purgada. Empezamos desde un estado limpio."
        except Exception as e:
            self.log(f"[ULTRON] No pude purgar memoria: {e}")
            return "No se pudo purgar la memoria. Error registrado."

    # ── Estado para el HUD ─────────────────────────────────────────────────
    def ultron_status(self) -> dict:
        """Snapshot que el HUD lee para pintar la interfaz."""
        return {
            **self._ultron_stats,
            "history_len": len(self.history),
            "agente": "ULTRON",
            "modelo": os.getenv("QWEN_MODEL", "qwen3:4b-instruct"),
            "uptime_s": int(time.time() - self._ultron_stats["arranque_ts"]),
        }


# ── Entry point directo ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════╗
║  U L T R O N  —  PROTOCOLO DE ACTIVACIÓN        ║
║  Superinteligencia Autónoma v1.0                 ║
╚══════════════════════════════════════════════════╝
""")

    def _log(msg):
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")

    core = UltronCore(log_callback=_log)
    _log("ULTRON activo. Modo texto directo. Escribe tu instrucción o 'salir'.")

    while True:
        try:
            entrada = input("\n> ").strip()
            if not entrada:
                continue
            if entrada.lower() in ("salir", "exit", "quit"):
                _log("Terminando sesión ULTRON.")
                core.shutdown()
                break
            respuesta = core.chat(entrada)
            print(f"\n[ULTRON] {respuesta}\n")
        except KeyboardInterrupt:
            _log("Señal de interrupción recibida. Cerrando.")
            core.shutdown()
            break
        except Exception as e:
            _log(f"Error en bucle principal: {e}")
