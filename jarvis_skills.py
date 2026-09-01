#!/usr/bin/env python3
"""
jarvis_skills.py - Habilidades del sistema de Jarvis (Sprint 2)
Detección de intención por regex ANTES del LLM: respuestas instantáneas
para comandos del sistema sin gastar tokens ni latencia.

Habilidades:
  Apps (abrir/cerrar) | Volumen | Clima | Hora/Fecha | Notas | Temporizador
  Alarma | Captura de pantalla | Portapapeles | Bloquear/Apagar/Reiniciar
  Batería | Web search
"""
import os, re, subprocess, sys, threading, time, urllib.request, json, tempfile, unicodedata
from datetime import datetime, timedelta
import jarvis_config


APP_MAP = {
    # Núcleo
    "notepad": "notepad.exe", "bloc de notas": "notepad.exe",
    "calculadora": "calc.exe", "calculator": "calc.exe",
    "explorer": "explorer.exe", "archivos": "explorer.exe", "explorador": "explorer.exe",
    "explorador de archivos": "explorer.exe",
    "cmd": "cmd.exe", "terminal": "cmd.exe", "consola": "cmd.exe",
    "paint": "mspaint.exe", "dibujo": "mspaint.exe",
    "administrador de tareas": "taskmgr.exe", "task manager": "taskmgr.exe",
    "configuracion": "start ms-settings:", "ajustes": "start ms-settings:",
    "panel de control": "control.exe",
    # Web
    "chrome": "start msedge", "google": "start msedge", "navegador": "start msedge",
    "edge": "start msedge", "firefox": "start firefox",
    "youtube": "start https://www.youtube.com", "youtube music": "start https://music.youtube.com",
    "spotify": "start spotify:", "netflix": "start https://www.netflix.com",
    "twitch": "start https://www.twitch.tv",
    # Mensajería
    "whatsapp": "start https://web.whatsapp.com", "telegram": "start https://web.telegram.org",
    "discord": "start discord://", "gmail": "start https://mail.google.com",
    "outlook": "start outlook:", "correo": "start outlook:",
    # Oficina
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "vscode": "code", "visual studio code": "code", "visual studio": "devenv",
    "notion": "start https://www.notion.so", "obsidian": "obsidian",
    # Juegos/otro
    "steam": "steam", "epic games": "start com.epicgames.launcher://",
    "blender": "blender", "photoshop": "photoshop",
    "discord": "start discord://", "zoom": "zoom", "teams": "start msteams:",
    "musica": "start spotify:", "carpeta de descargas": "explorer.exe shell:Downloads",
    "papelera": "explorer.exe shell:RecycleBinFolder",
}

CLOSE_MAP = {k: v for k, v in APP_MAP.items() if not v.startswith("start")}
# Apps lanzadas con "start" necesitan su exe real para cerrarse
CLOSE_MAP.update({
    "chrome": "msedge.exe", "google": "msedge.exe", "navegador": "msedge.exe",
    "edge": "msedge.exe", "firefox": "firefox.exe", "youtube": "msedge.exe",
    "spotify": "spotify.exe", "steam": "steam.exe",
})


DIA_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


class SkillsManager:
    """Despachador de habilidades del sistema. handle(text) -> str | None"""

    def __init__(self, log=print, notify=None, remember=None, safe=False):
        self.log = log
        self.notify = notify  # callback para avisos sonoros (TTS) de timers/alarmas
        self.remember = remember  # callback para persistir recordatorios (core.add_reminder)
        self.safe = safe  # True = no ejecutar acciones destructivas (pruebas)
        self._notas_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Notas")
        self._caps_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Capturas")
        os.makedirs(self._notas_dir, exist_ok=True)
        os.makedirs(self._caps_dir, exist_ok=True)
        self._timers = {}
        self._player = None
        self._vigilando = False
        self._alertas_cfg = {}
        self._alerta_activa = False
        self._pomodoro_activo = False
        self._recurrente_hilo_vivo = False
        self._antirobo_activo = False
        self._lector = None
        self._modo_silencio = False
        self._en_macro = False
        self._whisper = None
        self._simulando = False
        self._invitado = False
        self._gaming = False
        self._vigilando_red = False
        self._informe_hoy = ""
        self._salud_ultimo = 0
        threading.Thread(target=self._hilo_diario, daemon=True).start()
        threading.Thread(target=self._hilo_monitor_webs, daemon=True).start()
        threading.Thread(target=self._hilo_vigilante_red, daemon=True).start()
        threading.Thread(target=self._hilo_salud, daemon=True).start()
        threading.Thread(target=self._hilo_informe, daemon=True).start()

    def _hilo_diario(self):
        """A medianoche guarda el diario del día automáticamente."""
        ultimo = None
        while True:
            try:
                hoy = datetime.now().strftime("%Y-%m-%d")
                if ultimo != hoy and datetime.now().hour == 23 and datetime.now().minute >= 50:
                    ultimo = hoy
                    self._diario_generar()
            except Exception:
                pass
            time.sleep(60)

    # ── DESPACHADOR PRINCIPAL ────────────────────────────────────────────────
    @staticmethod
    def _norm(s: str) -> str:
        """Minúsculas y sin acentos: 'qué día' -> 'que dia' (matcheo robusto)."""
        s = unicodedata.normalize("NFD", s.lower())
        return "".join(c for c in s if unicodedata.category(c) != "Mn")

    def handle(self, text: str):
        """Devuelve la respuesta del mayordomo o None si no hay habilidad."""
        # Plugin system (nuevas skills modulares) — prioridad máxima
        try:
            from skills.plugins import get_plugin_registry
            plugin_reply = get_plugin_registry(log=self.log).handle(text, self)
            if plugin_reply:
                return plugin_reply
        except Exception:
            pass

        self._orig = text                      # texto crudo (para URLs con mayúsculas)
        self._orig_lower = text.lower()        # conserva acentos para capturar contenido
        t = self._norm(text)

        # Comandos personalizados y disparadores del señor (macros)
        macro_reply = self._ejecutar_macro(t)
        if macro_reply:
            return macro_reply

        # Modo invitado: proteger datos sensibles mientras haya visitas
        if self._invitado and re.search(
                r"contrasena|contraseña|portapapeles|clipboard|enviar(me)? (un )?(archivo|documento|foto)|"
                r"manda (un )?(archivo|documento|foto)", t):
            return "Señor, estamos en modo invitado. Prefiero no hacer eso mientras haya visitas."

        # Orden: específicas primero
        for handler in (
            self._escena, self._sonrisa, self._voz_config, self._racha_juntos,
            self._avisos_memoria,
            self._informe_matutino, self._vigilar_red, self._donde_movil, self._spotify,
            self._descargar_url, self._resumir_pdf, self._escanear_doc,
            self._modo_invitado, self._modo_gaming, self._modo_noche, self._modo_dictado,
            self._salud_pc, self._compra, self._buscar_contenido, self._enviar_tv,
            self._diagnostico,
            self._saludo_dia,
            self._gasto, self._habito, self._imprimir, self._fondo,
            self._monitor_web_quitar, self._monitor_web, self._monitor_web_lista,
            self._password, self._audio_movil, self._recientes, self._gpu,
            self._parar_todo, self._sonar_movil, self._stats_jarvis, self._simular_presencia,
            self._ver_pantalla, self._touchpad_skill, self._sincronizar, self._diario,
            self._rostro, self._quien_red, self._chiste, self._quiz, self._curiosidad,
            self._macro, self._trigger, self._buscar_memoria, self._agenda_ics,
            self._seguridad, self._dashboard,
            self._portapapeles, self._selfie, self._apagado_programado, self._actualizar,
            self._velocidad, self._noticias, self._pronostico, self._deportes,
            self._buscar_archivos, self._ocr, self._transcribir, self._silencio,
            self._ausente, self._bluetooth, self._stats_uso, self._pantalla,
            self._historial, self._encendido, self._presencia, self._antirobo,
            self._webhook, self._telegram, self._menu_semanal, self._desinstalar,
            self._brillo, self._hora_mundial, self._leer, self._podcast,
            self._archivos_movil, self._enviar_archivo,
            self._resumen_dia, self._tareas_lista, self._tareas_borra, self._tarea,
            self._precio_borra, self._precio, self._recurrente_borra, self._recurrente_lista,
            self._recurrente, self._paquete, self._radio, self._pomodoro, self._nota_voz,
            self._espacio, self._alertas, self._preferencia, self._suspender, self._estado_pc,
            self._enviar_captura, self._vigilar, self._musica, self._lista, self._agenda,
            self._resumir, self._traducir, self._cine, self._receta, self._backup,
            self._limpieza, self._procesos, self._domotica,
            self._investigar, self._archivos, self._organizar_descargas, self._descargar_video,
            self._arduino, self._navegador, self._movil, self._recordatorio, self._alarma,
            self._temporizador, self._volumen_a,
            self._volumen, self._mutar, self._clima, self._noticias,
            self._ocr, self._captura, self._portapapeles, self._buscar_web,
            self._notas, self._cancela_apagado, self._bloquear,
            self._apagar, self._reiniciar, self._bateria,
            self._red, self._sistema, self._conversor, self._calculadora, self._wifi, self._qr, self._azar,
            self._hora_fecha, self._abrir_app, self._cerrar_app,
            # Nuevas skills avanzadas (IA-PARA-TODOS)
            self._scrape_web, self._stock_data, self._noticias_buscar,
            self._pdf_chat, self._resumen_url,
            self._refrigeracion,
        ):
            reply = handler(t)
            if reply is not None:
                self.log(f"Habilidad ejecutada: {handler.__name__} <- '{text[:60]}'")
                return reply
        return None

    # ── APPS ──────────────────────────────────────────────────────────────────
    def _abrir_app(self, t: str):
        m = re.search(r"(abre|abrir|inicia|iniciar|lanza|lanzar|ejecuta|ejecutar|abreme|ponme|pon)\s+(?:(?:el|la|lo|un|una)\s+)?([a-záéíóúñ ]+)", t)
        if not m:
            return None
        name = m.group(2).strip().rstrip(".")
        # Descartar comandos que no son apps
        if any(k in name for k in ("volumen", "musica de", "nota", "captura", "busqueda")):
            return None
        cmd = APP_MAP.get(name)
        if not cmd:
            # búsqueda aproximada: contiene palabra clave
            for key, val in APP_MAP.items():
                if key in name:
                    cmd = val
                    break
        if not cmd:
            return None
        try:
            subprocess.Popen(cmd, shell=True)
            return f"Enseguida, señor. Abriendo {name.title()}."
        except Exception as e:
            self.log(f"No pude abrir {name}: {e}")
            return f"Señor, tuve un problema al abrir {name}."
        return None

    def _cerrar_app(self, t: str):
        m = re.search(r"(cierra|cerrar|termina|finaliza)\s+(?:(?:el|la|lo)\s+)?([a-záéíóúñ ]+)", t)
        if not m:
            return None
        name = m.group(2).strip().rstrip(".")
        cmd = CLOSE_MAP.get(name)
        if not cmd:
            for key, val in CLOSE_MAP.items():
                if key in name:
                    cmd = val
                    break
        if not cmd:
            return None
        if self.safe:
            return f"Cerrado, señor. {name.title()} ya no está en ejecución. (modo seguro: no ejecutado)"
        try:
            subprocess.Popen(f"taskkill /IM {cmd} /F", shell=True, creationflags=0x08000000)
            return f"Cerrado, señor. {name.title()} ya no está en ejecución."
        except Exception as e:
            self.log(f"No pude cerrar {name}: {e}")
            return f"Señor, no logré cerrar {name}."
        return None

    # ── VOLUMEN ──────────────────────────────────────────────────────────────
    def _send_vol(self, pulses: int, key: int):
        # 173 = bajar, 175 = subir (teclas multimedia de Windows)
        script = (
            "$obj = New-Object -ComObject WScript.Shell;"
            f"for($i=0;$i -lt {pulses};$i++){{$obj.SendKeys([char]{key})}}"
        )
        subprocess.Popen(["powershell", "-NoProfile", "-Command", script],
                         creationflags=0x08000000)

    def _volumen_a(self, t: str):
        m = re.search(r"volumen(?: al| a| en| de)\s*(?:un\s*)?(\d{1,3})\s*%", t)
        if not m:
            return None
        pct = min(int(m.group(1)), 100)
        # aproximación: bajar al mínimo (60 pulsos) y subir pct/2 veces
        def _do():
            self._send_vol(60, 173)
            time.sleep(1.5)
            self._send_vol(max(1, pct // 2), 175)
        threading.Thread(target=_do, daemon=True).start()
        return f"Volumen al {pct}%, señor."

    def _volumen(self, t: str):
        if re.search(r"sube|subir|aumenta|aumentar|mas alto|mas volumen", t):
            self._send_vol(6, 175)
            return "Subiendo el volumen, señor."
        if re.search(r"baja|bajar|reduce|reducir|mas bajo|menos volumen", t):
            self._send_vol(6, 173)
            return "Bajando el volumen, señor."
        return None

    def _mutar(self, t: str):
        if re.search(r"desmuta|reactiva el sonido|quita el silencio|sonido de nuevo|quita la mudo", t):
            self._send_vol(1, 174)
            return "Audio restaurado, señor."
        if re.search(r"muta|silencia|silencio|sin sonido|quita el sonido|quita el audio", t):
            self._send_vol(1, 174)
            return "Audio silenciado, señor."
        return None

    # ── CLIMA ────────────────────────────────────────────────────────────────
    def _clima(self, t: str):
        if not re.search(r"clima|tiempo (que hace|hace)|temperatura (exterior|afuera|fuera|en)|pronostico", t):
            return None
        m = re.search(r"(?:en|de|para)\s+([a-záéíóúñ ]{2,25})$", t)
        city = m.group(1).strip() if m else self._pref_leer().get("ciudad", "")
        def _ask():
            try:
                url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1" if city else "https://wttr.in/?format=j1"
                with urllib.request.urlopen(url, timeout=10) as r:
                    d = json.loads(r.read().decode())
                c = d["current_condition"][0]
                desc = c["weatherDesc"][0]["value"]
                t_c = c["temp_C"]
                sens = c["FeelsLikeC"]
                hum = c["humidity"]
                place = d.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", "su zona")
                msg = (f"Señor, en {place} hay {desc.lower()} con {t_c}°C "
                       f"(sensación de {sens}°C) y {hum}% de humedad.")
                if self.notify:
                    self.notify(msg)
            except Exception as e:
                self.log(f"Clima falló: {e}")
                if self.notify:
                    self.notify("Señor, no pude consultar el clima en este momento.")
        threading.Thread(target=_ask, daemon=True).start()
        return "Consultando el clima, señor. Un momento por favor."

    # ── CAPTURA DE PANTALLA ──────────────────────────────────────────────────
    def _captura(self, t: str):
        if not re.search(r"captura|pantallazo|screenshot|foto de la pantalla|toma una foto de la pantalla", t):
            return None
        def _do():
            try:
                from PIL import ImageGrab
                fecha = datetime.now().strftime("%Y-%m-%d")
                d = os.path.join(self._caps_dir, fecha)
                os.makedirs(d, exist_ok=True)
                path = os.path.join(d, f"captura_{datetime.now().strftime('%H%M%S')}.png")
                ImageGrab.grab().save(path, "PNG")
                msg = f"Captura guardada en {path}. Señor."
                self.log(msg)
                if self.notify:
                    self.notify(f"Captura de pantalla lista, señor. Guardada en {os.path.basename(d)}.")
            except Exception as e:
                self.log(f"Captura falló: {e}")
                if self.notify:
                    self.notify("Señor, no pude tomar la captura de pantalla.")
        threading.Thread(target=_do, daemon=True).start()
        return "Tomando la captura de pantalla, señor."

    # ── PORTAPAPELES ─────────────────────────────────────────────────────────
    def _portapapeles(self, t: str):
        m = re.search(r"(copia|copiar|pon)\s+(?:en el portapapeles|al portapapeles)?\s*[::,-]?\s*(.+)", t)
        if not m or "portapapeles" not in t:
            return None
        mo = re.search(r"(copia|copiar|pon)\s+(?:en el portapapeles|al portapapeles)?\s*[::,-]?\s*(.+)", self._orig_lower)
        txt = (mo.group(2) if mo else m.group(2)).strip().strip("\"'")
        if not txt or len(txt) > 4000:
            return None
        subprocess.Popen(["powershell", "-NoProfile", "-Command",
                          f"Set-Clipboard -Value '{txt.replace(chr(39), chr(39)*2)}'"],
                         creationflags=0x08000000)
        return "Copiado al portapapeles, señor. Listo para pegar donde necesite."

    # ── WEB SEARCH ───────────────────────────────────────────────────────────
    def _buscar_web(self, t: str):
        # si la búsqueda especifica un sitio (youtube, maps, wikipedia...),
        # la gestiona _navegador; este comodín solo busca en Google genérico
        if re.search(r"busca\s+en\s+(youtube|google maps|maps|wikipedia|amazon|github|"
                     r"google imagenes|google imágenes|twitter|x)\b", t):
            return None
        m = re.search(r"(busca|buscar|investiga|googlea)\s+(?:en (?:internet|google|la web))?\s*(.+)$", t)
        if not m or any(k in t for k in ("nota", "imagen", "musica", "archivo")):
            return None
        mo = re.search(r"(busca|buscar|investiga|googlea)\s+(?:en (?:internet|google|la web))?\s*(.+)$", self._orig_lower)
        q = (mo.group(2) if mo else m.group(2)).strip().strip("?.")
        if len(q) < 2 or "clima" in q.lower():
            return None
        import urllib.parse
        url = "https://www.google.com/search?q=" + urllib.parse.quote(q)
        subprocess.Popen(["start", "", url], shell=True)
        return f"Abriendo resultados de búsqueda para «{q}», señor."

    # ── NOTAS ────────────────────────────────────────────────────────────────
    def _notas(self, t: str):
        if re.search(r"crea(?:me)? una nota|anota|apunta|escribe una nota", t):
            mo = re.search(r"(?:nota|anota|apunta)\s*(?:que|:)?\s*(.+)", self._orig_lower)
            m = re.search(r"(?:nota|anota|apunta)\s*(?:que|:)?\s*(.+)", t)
            src = mo if mo and mo.group(1).strip() else m
            if not src:
                return None
            content = src.group(1).strip().strip("\"'")
            if not content:
                return None
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._notas_dir, f"nota_{ts}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%d/%m/%Y %H:%M')}\n{content}")
            return "Nota guardada, señor. La conservo en mi archivo personal."

        if re.search(r"(muestra|lista|dime|ver|enseñame).*notas", t):
            files = sorted(os.listdir(self._notas_dir))[-8:] if os.path.isdir(self._notas_dir) else []
            if not files:
                return "Señor, aún no tengo notas guardadas."
            lista = ", ".join(f.replace("nota_", "").replace(".txt", "") for f in files)
            return f"Señor, tengo {len(files)} notas: {lista}."

        if re.search(r"(lee|leeme|muestrame).*(?:la nota|nota)", t):
            m = re.search(r"(?:nota)\s+(?:de\s+)?([\w-]+)", t)
            if m:
                name = m.group(1)
                path = os.path.join(self._notas_dir, f"nota_{name}.txt")
                if not os.path.exists(path):
                    path = os.path.join(self._notas_dir, f"{name}.txt")
                if os.path.exists(path):
                    content = open(path, encoding="utf-8").read().strip()
                    return f"Nota «{name}»: {content[:300]}"
            return "¿Cuál nota desea que le lea, señor?"

        if re.search(r"borra|elimina.*nota", t):
            m = re.search(r"(?:nota)\s+([\w-]+)", t)
            if m:
                name = m.group(1)
                for p in (os.path.join(self._notas_dir, f"nota_{name}.txt"),
                          os.path.join(self._notas_dir, f"{name}.txt")):
                    if os.path.exists(p):
                        os.remove(p)
                        return f"Nota «{name}» eliminada, señor."
                return f"Señor, no encontré la nota «{name}»."
        return None

    # ── TEMPORIZADOR ─────────────────────────────────────────────────────────
    def _temporizador(self, t: str):
        if not re.search(r"temporizador|temporiza|cuenta (?:de |)atras", t):
            return None
        m = re.search(r"(\d+)\s*(segundos?|seg|s|minutos?|min|horas?|h)\b", t)
        if not m:
            return None
        n = int(m.group(1))
        unit = m.group(2)
        secs = n * 60 if unit.startswith("min") else n * 3600 if unit.startswith("h") else n
        if secs <= 0 or secs > 86400:
            return None
        unit_label = "minutos" if unit.startswith("min") else ("horas" if unit.startswith("h") else "segundos")
        def _done():
            self._avisar(f"Señor, el temporizador de {n} {unit_label} ha concluido.")
            if not self.notify:
                try:
                    import winsound
                    winsound.Beep(1000, 1500)
                except Exception:
                    pass
        t = threading.Timer(secs, _done)
        t.daemon = True
        t.start()
        return f"Temporizador activado, señor. Le avisaré en {n} {unit_label}."

    # ── ARCHIVOS Y CARPETAS (acceso completo al PC) ──────────────────────────
    @staticmethod
    def _home_dir(ubicacion: str):
        """Resuelve una ubicación de usuario a ruta absoluta."""
        home = os.path.expanduser("~")
        u = re.sub(r"^(?:la|el|mi|mis|una|un)\s+(?:carpeta\s+(?:de\s+)?)?",
                   "", ubicacion.strip().lower())
        if not u or u in ("escritorio", "desktop", "el escritorio", "mi escritorio"):
            return os.path.join(home, "Desktop")
        if u in ("descargas", "downloads", "la carpeta de descargas"):
            return os.path.join(home, "Downloads")
        if u in ("documentos", "documentos", "mis documentos"):
            return os.path.join(home, "Documents")
        if u in ("imagenes", "imágenes", "fotos"):
            return os.path.join(home, "Pictures")
        if u in ("musica", "música"):
            return os.path.join(home, "Music")
        if u in ("videos", "vídeos"):
            return os.path.join(home, "Videos")
        if u in ("jarvis", "carpeta de jarvis", "la carpeta de jarvis"):
            return os.path.join(home, "Descargas", "JARVIS")
        # ubicación conocida con subcarpeta: "descargas/proyectos"
        for kw, base in (("escritorio", "Desktop"), ("descargas", "Downloads"),
                         ("downloads", "Downloads"), ("documentos", "Documents"),
                         ("imagenes", "Pictures"), ("fotos", "Pictures"),
                         ("musica", "Music"), ("videos", "Videos")):
            if u.startswith(kw + os.sep) or u.startswith(kw + "/"):
                resto = u[len(kw):].strip("/\\")
                return os.path.join(home, base, resto)
        return None  # no resuelta

    @staticmethod
    def _es_ruta_absoluta(s: str) -> bool:
        return bool(re.match(r"^[a-zA-Z]:[\\/]", s) or s.startswith(("\\\\", "/", "\\")))

    def _ubicacion_real(self, u: str):
        """Ubicación: carpeta conocida del usuario o ruta absoluta directa."""
        base = self._home_dir(u)
        if base:
            return base
        u2 = u.strip().strip("\"'")
        if self._es_ruta_absoluta(u2):
            return os.path.abspath(os.path.expanduser(u2))
        return None

    def _extraer_ubicacion_de_texto(self, texto: str) -> tuple:
        """Extrae ubicación (escritorio/descargas/etc) y nombre del final del texto.

        Soporta patrones:
          "... en el escritorio", "... en escritorio", "... sobre el escritorio",
          "... en descargas", "... en mi escritorio", "... en la carpeta de descargas"

        Returns:
            (ubicacion_limpia, texto_sin_ubicacion) o (None, texto)
        """
        # ubicaciones conocidas con posibles artículos delante
        alias = (
            r"(?:el|mi|la|los|las)?\s*"
            r"(?:carpeta\s+(?:de\s+)?)?"
            r"(?:escritorio|desktop|descargas?|downloads?|documentos?|imagen(?:es)?|fotos?|"
            r"m[uú]sica|videos?|v[ií]deos?|carpeta\s+de\s+jarvis)"
        )
        # patrón: "... en/sobre/dentro de <ubic>"
        m = re.search(
            r"\s+(?:en|sobre|dentro\s+de|a|para)\s+(?P<u>" + alias + r")\s*$",
            texto, flags=re.IGNORECASE)
        if m:
            ubic = m.group("u").strip()
            limpio = texto[:m.start()].rstrip()
            return ubic, limpio
        # patrón suelto al final: "... <ubic>" (sin preposición)
        m = re.search(r"\s+(?P<u>" + alias + r")\s*$", texto, flags=re.IGNORECASE)
        if m:
            ubic = m.group("u").strip()
            # solo si NO hay verbo después (es decir, la ubicación va al final)
            # y la parte anterior no termina ya en una palabra de extensión común
            limpio = texto[:m.start()].rstrip()
            # si limpio es muy corto, probablemente sea solo el nombre y no
            # una ubicación — devolvemos None para no romper
            if len(limpio.split()) >= 2:
                return ubic, limpio
        return None, texto

    def _extraer_contenido(self, texto: str) -> tuple:
        """Detecta bloques de contenido al final: 'con el contenido: X',
        'contenido: X', 'que diga X', 'que contenga X', 'con el texto X',
        'que imprima X' (verbo genérico), 'con un tutorial de X'.

        Returns:
            (contenido, texto_sin_bloque_contenido) o (None, texto)
        """
        patrones = [
            r"(?:con|que\s+(?:diga|contenga|dice)|y\s+que\s+(?:diga|contenga|dice))"
            r"\s+(?:el\s+|este\s+|el\s+siguiente\s+|el\s+texto\s+|un\s+texto\s+)?"
            r"(?:contenido|texto|mensaje)\s*[:=]?\s*(?P<c>.+?)\s*$",
            r"\s+con\s+(?:el\s+|el\s+siguiente\s+)?contenido\s*[:=]\s*(?P<c>.+?)\s*$",
            r"\s+contenido\s*[:=]\s*(?P<c>.+?)\s*$",
            # "que diga 'hola'" / "que contenga Hola Mundo"
            r"\s+que\s+(?:diga|contenga|dice)\s+[\"']?(?P<c>[^\"']{1,400})[\"']?\s*$",
            r"\s+con\s+el\s+texto\s+[\"']?(?P<c>[^\"']{1,400})[\"']?\s*$",
            # genérico: "que imprima hola mundo", "que sume dos numeros",
            # "que muestre el clima" (excluye "que se llame/llama" = nombre)
            r"\s+que\s+(?!se\s+(?:llame|llama)\b)(?P<c>.{1,400})\s*$",
            # "con un tutorial de python", "con un ejemplo de X"
            r"\s+con\s+(?:un|una)\s+(?:tutorial|ejemplo|programa|codigo|c[oó]digo|texto|script|informe|reporte)\s+(?P<c>.{1,300})\s*$",
            # "que haga: X", "con la informacion: X", "con el resumen: X"
            r"\s+con\s+(?:el\s+|la\s+)?(?:informacion|resumen|informe|reporte|lista|tabla)\s*[:=]\s*(?P<c>.+?)\s*$",
        ]
        for p in patrones:
            m = re.search(p, texto, flags=re.IGNORECASE)
            if m and m.group("c").strip():
                contenido = m.group("c").strip().strip("\"'")
                limpio = texto[:m.start()].rstrip()
                return contenido, limpio
        return None, texto

    # ── INVESTIGAR Y GUARDAR EN ARCHIVO ─────────────────────────────────────
    # "investiga sobre X y guardalo en un archivo html llamado Y"
    # "guarda en un archivo md la investigacion sobre X"
    def _investigar(self, t: str):
        m = re.search(
            r"(?:investiga|investigar|investigame|investigacion|"
            r"haz\s+(?:me\s+)?una\s+investigacion|busca\s+informacion)\s+"
            r"(?:sobre\s+|acerca\s+de\s+|acerca\s+)?(?P<tema>.+?)\s+"
            r"(?:y\s+|y\s+luego\s+|,\s*)?"
            r"(?:guarda|guardame|guardar|guardalo|guardala|guardamelo|guardamela|"
            r"crea|creame|crear|crealo|creala|creamelo|escribe|escribeme|escribelo|"
            r"hazme|haz|genera|generame|generar)\s+"
            r"(?:me\s+|lo\s+|la\s+|melo\s+|mela\s+|un\s+|una\s+|el\s+|la\s+|"
            r"informacion\s+|la\s+informacion\s+|los\s+resultados\s+|lo\s+que\s+encuentres\s+|"
            r"lo\s+que\s+sepas\s+)*"
            r"(?:en\s+|a\s+)?(?:un\s+|el\s+|este\s+)?"
            r"(?:archivo|documento|fichero|script|pagina|informe|reporte|nota)\s*"
            r"(?P<resto>.*)$", t, flags=re.IGNORECASE)
        if not m:
            m = re.search(
                r"(?:guarda|guardame|guardalo|guardala|crea|creame|crealo|creala|"
                r"escribe|escribeme|escribelo|hazme|haz|genera|generame)\s+"
                r"(?:me\s+|lo\s+|la\s+|melo\s+|mela\s+)?(?:en\s+|a\s+)?"
                r"(?:un\s+|el\s+|este\s+)?"
                r"(?:archivo|documento|fichero|script|pagina|informe|reporte|nota)\s*"
                r"(?P<resto>.*?)\s+"
                r"(?:la\s+|una\s+|toda\s+la\s+)?(?:investigacion|informacion)\s+"
                r"(?:sobre\s+|acerca\s+de\s+|acerca\s+)?(?P<tema>.+?)\s*$",
                t, flags=re.IGNORECASE)
        if not m:
            return None
        tema = m.group("tema").strip().strip("\"'.")
        resto = m.group("resto").strip()
        if not tema or len(tema) > 200:
            return None
        # "y guarda la informacion" sin archivo -> no es investigación a archivo
        if "archivo" not in t and not re.search(r"informe|reporte|documento|nota", t):
            return None
        # formato: tipo en el resto ("html llamado clima", ".md", "python")
        ubicacion, resto = self._extraer_ubicacion_de_texto(resto)
        c2, resto = self._extraer_contenido(resto)
        m_ed = re.search(r"\.\s*(py|txt|md|js|html|css|json|csv|xml|yml|yaml|sh|sql)\b", resto)
        ext = "." + m_ed.group(1).lower() if m_ed else None
        if m_ed:
            resto = (resto[:m_ed.start()] + resto[m_ed.end():]).strip()
        if not ext:
            m_tipo = re.match(
                r"^(?:de\s+)?(?P<tp>python|py|html|json|csv|markdown|md|texto|text|txt|"
                r"javascript|js|bash|sh|sql|xml|yaml|yml)\b", resto, flags=re.IGNORECASE)
            if m_tipo:
                ext = self._TIPO_EXT[m_tipo.group("tp").lower()]
                resto = resto[m_tipo.end():].strip()
        m_nombre = re.search(
            r"(?:llamad[oa]|de\s+nombre|con\s+nombre)\s+[\"']?(?P<n>[^\"']+?)\s*$",
            resto, flags=re.IGNORECASE)
        nombre = m_nombre.group("n").strip().strip("\"'") if m_nombre else None
        if nombre and ext and not nombre.lower().endswith(
                (".py", ".txt", ".md", ".js", ".html", ".css", ".json", ".csv",
                 ".xml", ".yml", ".yaml", ".sh", ".sql")):
            nombre += ext
        if not nombre:
            base_slug = re.sub(r"[^a-z0-9]+", "_", tema.lower()).strip("_")[:40]
            nombre = base_slug + (ext or ".md")

        def _do():
            try:
                texto, fuente = self._investigar_tema(tema)
                if not texto:
                    self._avisar(f"Señor, no encontré información sobre «{tema[:50]}». "
                                 "Revise su conexión e inténtelo de nuevo.")
                    return
                contenido = self._investigacion_a_formato(ext or ".md", tema, texto, fuente)
                base = (self._home_dir(ubicacion) if ubicacion
                        else os.path.join(os.path.expanduser("~"), "Documents"))
                path = os.path.join(base, nombre)
                os.makedirs(base, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(contenido)
                self._avisar(f"Investigación lista, señor: «{tema[:50]}» guardada en "
                             f"{path} ({len(contenido)} bytes). Fuente: {fuente}.")
            except Exception as e:
                self.log(f"Investigación falló: {e}")
                self._avisar(f"Señor, no pude completar la investigación: {str(e)[:100]}")

        threading.Thread(target=_do, daemon=True).start()
        return (f"Investigando sobre «{tema[:60]}», señor. "
                f"Un momento, por favor.")

    @staticmethod
    def _investigar_tema(tema: str):
        """Devuelve (texto, fuente) o (None, None). Wikipedia es -> DuckDuckGo."""
        import urllib.parse
        ua = {"User-Agent": "JARVIS-asistente/1.0 (asistente personal local)"}

        def _wiki(titles):
            try:
                qs = urllib.parse.urlencode({
                    "action": "query", "format": "json", "prop": "extracts",
                    "explaintext": 1, "exintro": 1, "redirects": 1,
                    "titles": titles, "utf8": 1})
                req = urllib.request.Request(
                    "https://es.wikipedia.org/w/api.php?" + qs, headers=ua)
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = json.load(r)
                for _, p in data.get("query", {}).get("pages", {}).items():
                    if p.get("extract", "").strip():
                        return p["extract"].strip()
            except Exception:
                pass
            return None

        txt = _wiki(tema)
        if txt:
            return txt, "Wikipedia (es)"
        # búsqueda fuzzy: "los planetas del sistema solar" -> título real
        try:
            qs = urllib.parse.urlencode({
                "action": "query", "format": "json", "list": "search",
                "srsearch": tema, "srlimit": 1, "utf8": 1})
            req = urllib.request.Request(
                "https://es.wikipedia.org/w/api.php?" + qs, headers=ua)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.load(r)
            hits = data.get("query", {}).get("search", [])
            if hits:
                txt = _wiki(hits[0]["title"])
                if txt:
                    return txt, "Wikipedia (es)"
        except Exception:
            pass
        try:
            req = urllib.request.Request(
                "https://api.duckduckgo.com/?q=" + urllib.parse.quote(tema) +
                "&format=json&no_html=1&skip_disambig=1", headers=ua)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.load(r)
            if data.get("AbstractText", "").strip():
                return data["AbstractText"].strip(), "DuckDuckGo"
        except Exception:
            pass
        return None, None

    @staticmethod
    def _investigacion_a_formato(ext: str, tema: str, texto: str, fuente: str) -> str:
        from datetime import date
        hoy = date.today().isoformat()
        if ext == ".html":
            titulo = tema[:80].replace("&", "&amp;").replace("<", "&lt;")
            cuerpo = texto[:4000].replace("&", "&amp;").replace("<", "&lt;")
            return (f'<!DOCTYPE html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
                    f"<title>{titulo}</title>\n<style>body{{font-family:system-ui,sans-serif;"
                    f"max-width:780px;margin:2rem auto;padding:0 1rem;line-height:1.6}}"
                    f"h1{{color:#0aa}}footer{{color:#888;font-size:.85em;margin-top:2rem}}</style>\n"
                    f"</head>\n<body>\n<h1>{titulo}</h1>\n"
                    f"<p>{cuerpo}</p>\n<footer>Investigado por JARVIS el {hoy}. "
                    f"Fuente: {fuente}</footer>\n</body>\n</html>\n")
        if ext == ".json":
            return json.dumps({"tema": tema, "fecha": hoy, "fuente": fuente,
                               "resumen": texto[:4000]}, ensure_ascii=False, indent=2)
        if ext == ".csv":
            return f"tema,fecha,fuente,resumen\n" \
                   f'"{tema}","{hoy}","{fuente}","{texto[:4000].replace(chr(34), chr(39))}"\n'
        if ext == ".txt":
            return f"{tema}\n{'=' * len(tema)}\n\n{texto[:4000]}\n\n— Fuente: {fuente} ({hoy})\n"
        # .md y resto
        return (f"# {tema}\n\n{texto[:4000]}\n\n"
                f"---\n*Investigado por JARVIS el {hoy}. Fuente: {fuente}*\n")

    def _archivos(self, t: str):
        # ── EXTRAE UBICACIÓN (primero: evita que el contenido se coma la
        #    ubicación al final) y después el contenido ──
        ubicacion, cuerpo = self._extraer_ubicacion_de_texto(t)
        contenido, cuerpo = self._extraer_contenido(cuerpo)
        if contenido is None:
            contenido = ""

        # ── CREAR CARPETA (variantes flexibles) ──
        # Detecta tanto "crear carpeta" como "crear la carpeta", "carpeta nueva", etc.
        # y admite nombre y/o ubicación opcionales.
        m_carpeta = re.search(
            r"(?:crea(?:me)?|haz(?:me)?|haga(?:me)?|guarda(?:me)?|genera(?:me)?|"
            r"crear|haz|haga|genera|guardar|hazme|creame|hagame)\s+"
            r"(?:una\s+|la\s+|nueva\s+|la\s+nueva\s+)?"
            r"carpeta\s*(?:nueva\s+)?(?:llamada\s+|de\s+nombre\s+|\")?"
            r"(?P<resto>.+?)\s*$", t, flags=re.IGNORECASE)
        if m_carpeta:
            resto = m_carpeta.group("resto").strip().strip("\"'.")
            # si el resto empieza con "en/sobre/dentro de <ubic> llamada <nombre>"
            m2 = re.search(
                r"^(?:en|sobre|dentro\s+de)\s+(?P<u>.+?)\s+"
                r"(?:llamada|de\s+nombre|con\s+nombre)\s+(?P<n>.+?)\s*$",
                resto, flags=re.IGNORECASE)
            if m2:
                nombre = m2.group("n").strip().strip("\"'")
                ubic = m2.group("u").strip().strip("\"'")
            else:
                # resto = "<nombre> en <ubic>" o solo "<nombre>"
                _, cuerpo_resto = self._extraer_ubicacion_de_texto(resto)
                nombre = cuerpo_resto.strip().strip("\"'.")
                ubic = ubicacion  # usar la detectada a nivel global
            base = self._home_dir(ubic) if ubic else self._home_dir("escritorio")
            if base is None:
                base = self._home_dir("escritorio")
                aviso = (f"Señor, no reconocí la ubicación «{ubic}»; "
                         f"la creé en el escritorio.")
            else:
                aviso = None
            if not nombre:
                nombre = self._nuevo_nombre(base, "Nueva Carpeta", is_dir=True)
            if self._es_ruta_absoluta(nombre):
                path = os.path.abspath(os.path.expanduser(nombre))
                base = os.path.dirname(path)
            else:
                path = os.path.join(base, nombre)
            try:
                os.makedirs(path, exist_ok=True)
                if os.path.isdir(path):
                    r = f"Carpeta «{os.path.basename(path)}» creada en {path}, señor."
                    return r if not aviso else aviso + " " + r
                return "Señor, intenté crear la carpeta pero no pude verificar su existencia."
            except Exception as e:
                self.log(f"No pude crear carpeta {path}: {e}")
                return f"Señor, no pude crear la carpeta: {str(e)[:80]}"

        # ── CREAR ARCHIVO (regex amplia, todas las variantes) ──
        # Captura frases como:
        #   "crea un archivo python que imprima hola mundo en el escritorio"
        #   "hazme un script .py en descargas que sume dos numeros"
        #   "crea un archivo de texto llamado notas.md en escritorio"
        #   "guardame un archivo .md en Descargas con un tutorial de python"
        #   "crea un archivo en el escritorio llamado test.txt con contenido hola"
        #   "genera un archivo hola.py en el escritorio"
        #   "guarda un archivo con el contenido resumen del dia"
        _VERB = (r"(?:(?:crea|haz|haga|guarda|genera|escribe)"
                 r"(?:me|r|lo|la|melo|mela|melos|melas)?"
                 r"|crear|haz|haga|guardar|generar|escribir"
                 r"|creame|hazme|hagame|guardame|generame|escribeme)")
        m_archivo = re.search(
            _VERB + r"\s+"
            r"(?:un\s+|el\s+|nuevo\s+|el\s+nuevo\s+|un\s+nuevo\s+)?"
            r"(?:archivo|documento|fichero|script|nota\s+de\s+texto|codigo|"
            r"c[oó]digo|programa|nota)\s*"
            r"(?P<resto>.*?)\s*$", t, flags=re.IGNORECASE)
        # Variante: "script .py en descargas ..." sin la palabra "archivo"
        if not m_archivo:
            m_archivo = re.search(
                _VERB + r"\s+"
                r"(?:un\s+|el\s+)?(?:script|c[oó]digo|programa|hoja)\s+"
                r"(?P<resto>.*?)\s*$", t, flags=re.IGNORECASE)
        if m_archivo:
            resto = m_archivo.group("resto").strip()

            # ── 1) UBICACIÓN al final ("llamado X en el escritorio")
            u_extra, resto = self._extraer_ubicacion_de_texto(resto)
            if u_extra and not ubicacion:
                ubicacion = u_extra
            # ── 2) CONTENIDO pegado ("llamado X con contenido Y")
            c2, resto = self._extraer_contenido(resto)
            if c2 is not None:
                contenido = c2
            # ── 3) UBICACIÓN tras el contenido ("... en descargas con tutorial X")
            u3, resto = self._extraer_ubicacion_de_texto(resto)
            if u3 and not ubicacion:
                ubicacion = u3

            # ── 4) EXTENSIÓN explícita: "script .py", "archivo .md"
            _EXT = (r"py|txt|md|js|html|css|json|csv|bat|ino|cpp|c|h|java|xml|"
                    r"yml|yaml|ts|tsx|jsx|sh|sql|ps1|rtf|log|ini|toml")
            m_ed = re.search(r"\.\s*(" + _EXT + r")\b", resto)
            ext = "." + m_ed.group(1).lower() if m_ed else None
            if m_ed:
                resto = (resto[:m_ed.start()] + resto[m_ed.end():]).strip()

            # ── 5) TIPO → EXTENSIÓN: "archivo python", "script bash", "de markdown"
            if not ext:
                m_tipo = re.match(
                    r"^(?:de\s+)?(?P<tp>python|py|javascript|js|typescript|ts|"
                    r"html|css|json|csv|markdown|md|texto|text|bash|sh|sql|"
                    r"powershell|ps1|batch|bat|arduino|ino|java|c\+\+|cpp|c\b|"
                    r"xml|yaml|yml|tsx|jsx)\b", resto, flags=re.IGNORECASE)
                if m_tipo:
                    ext = self._TIPO_EXT[m_tipo.group("tp").lower()]
                    resto = resto[m_tipo.end():].strip()

            # ── 6) NOMBRE
            nombre = None
            m_nombre = re.search(
                r"(?:llamad[oa]|de\s+nombre|con\s+nombre|que\s+se\s+(?:llame|llama))"
                r"\s+[\"']?(?P<n>[^\"']+?)\s*$", resto, flags=re.IGNORECASE)
            if m_nombre:
                nombre = m_nombre.group("n").strip().strip("\"'")
            else:
                m_ext2 = re.search(
                    r"(?P<n>[\w\-]+\.(?:" + _EXT + r"))\s*$", resto, flags=re.IGNORECASE)
                if m_ext2:
                    nombre = m_ext2.group("n").strip()
                elif resto and not re.search(r"\s", resto.strip()):
                    nombre = resto.strip().strip("\"'")
            # si el nombre arrastró una ubicación ("datos en el escritorio")
            if nombre and re.search(r"\s(?:en|sobre|dentro)\s+", nombre):
                u4, nombre = self._extraer_ubicacion_de_texto(nombre)
                if u4 and not ubicacion:
                    ubicacion = u4

            # ── 7) EXTENSIÓN para el nombre según tipo detectado
            if nombre and ext and not nombre.lower().endswith(
                    (".py", ".txt", ".md", ".js", ".html", ".css", ".json", ".csv",
                     ".bat", ".ino", ".cpp", ".c", ".h", ".java", ".xml", ".yml",
                     ".yaml", ".ts", ".tsx", ".jsx", ".sh", ".sql", ".ps1")):
                nombre += ext

            # ── 8) CONTENIDO ÚTIL para código / html / json ──
            if contenido and ext in (".py", ".js", ".ts", ".sh", ".bat", ".ps1",
                                      ".c", ".cpp", ".java"):
                if not self._parece_codigo(contenido):
                    contenido = self._codigo_desde_desc(ext, contenido)
            elif contenido and ext == ".html" and not self._parece_codigo(contenido):
                contenido = self._html_desde_desc(contenido)
            elif contenido and ext == ".json":
                try:
                    contenido = json.dumps(json.loads(contenido),
                                           ensure_ascii=False, indent=2)
                except Exception:
                    pass

            # ── 9) NOMBRE AUTOMÁTICO con la extensión correcta ──
            nombre = nombre.strip().strip("\"'.") if nombre else None
            if not nombre:
                base_tmp = (self._home_dir(ubicacion) if ubicacion
                            else self._home_dir("escritorio"))
                base_nombre = self._TIPO_BASE.get(ext, "archivo")
                nombre = self._nuevo_nombre(base_tmp, base_nombre, ext=ext or ".txt")

            # Si el nombre parece ser una ruta absoluta, usarla tal cual
            base = None
            if self._es_ruta_absoluta(nombre):
                path = os.path.abspath(os.path.expanduser(nombre))
                base = os.path.dirname(path)
                nombre = os.path.basename(path)
            else:
                base = (self._home_dir(ubicacion) if ubicacion
                        else self._home_dir("escritorio"))
                if base is None:
                    base = self._home_dir("escritorio")

            return self._crear_archivo(base, nombre, contenido)

        # ── BORRAR ARCHIVO ──
        m = re.search(r"(?:borra|elimina)\s+(?:el\s+|un\s+)?archivo\s+(?:llamado\s+|de nombre\s+)?([\w\s\-_.]+?)\s*(?:en|sobre|de|del)\s+(el\s+|mi\s+)?(.+)$", t)
        if m:
            nombre = m.group(1).strip()
            ubicacion = ((m.group(2) or "") + (m.group(3) or "")).strip()
            base = self._home_dir(ubicacion)
            if base is None:
                return None
            path = os.path.join(base, nombre)
            if not os.path.exists(path):
                return f"Señor, no encontré «{nombre}» en {base}."
            try:
                os.remove(path)
                return f"Archivo «{nombre}» eliminado, señor."
            except Exception as e:
                return f"Señor, no pude borrarlo: {str(e)[:80]}"
        # ── LISTAR CARPETA ──
        m = re.search(r"(?:muestra|lista|ver|dime)\s+(?:que hay|los archivos|que archivos|el contenido)\s*(?:hay|tiene|)?\s*(?:en|de|sobre)\s+(el\s+|mi\s+)?(.+)$", t)
        if m:
            ubicacion = ((m.group(1) or "") + (m.group(2) or "")).strip()
            if "notas" in ubicacion:
                return None  # lo maneja _notas
            base = self._home_dir(ubicacion)
            if base is None:
                return None
            try:
                items = os.listdir(base)
                if not items:
                    return f"Señor, la carpeta está vacía."
                carpetas = [i for i in items if os.path.isdir(os.path.join(base, i))]
                archivos = [i for i in items if not os.path.isdir(os.path.join(base, i))]
                res = []
                if carpetas:
                    res.append(f"{len(carpetas)} carpetas: " + ", ".join(carpetas[:10]))
                if archivos:
                    res.append(f"{len(archivos)} archivos: " + ", ".join(archivos[:15]))
                return "Señor, en esa ubicación hay " + ". ".join(res)
            except Exception as e:
                return f"Señor, no pude leer la carpeta: {str(e)[:80]}"
        # ── ABRIR CARPETA EN EXPLORER ──
        m = re.search(r"abre\s+(?:la\s+|el\s+)?carpeta\s+(?:de\s+|llamada\s+)?(.+)$", t)
        if m:
            ubicacion = m.group(1).strip()
            base = self._home_dir(ubicacion)
            if base is None or not os.path.isdir(base):
                return None
            subprocess.Popen(["explorer.exe", base], creationflags=0x08000000)
            return f"Abriendo la carpeta, señor."
        return None

    # ── HELPERS DE ARCHIVOS ─────────────────────────────────────────────────
    @staticmethod
    def _nuevo_nombre(base, nombre, ext="", is_dir=False):
        """Nombre sin colisión: 'archivo.txt', 'archivo 1.txt'..."""
        candidato = nombre + ext
        i = 1
        while True:
            p = os.path.join(base, candidato)
            existe = os.path.isdir(p) if is_dir else os.path.exists(p)
            if not existe:
                return candidato
            candidato = f"{nombre} {i}{ext}"
            i += 1

    def _crear_archivo(self, base, nombre, contenido):
        """Crea el archivo en disco y verifica que existe y tiene contenido.
        Devuelve un mensaje confirmando la ruta real (o error claro).
        """
        # Si no trae una extensión conocida, añade .txt por defecto
        extensiones = (".txt", ".md", ".py", ".js", ".html", ".css",
                       ".json", ".csv", ".bat", ".ino", ".cpp", ".c",
                       ".h", ".java", ".xml", ".yml", ".yaml", ".ts",
                       ".tsx", ".jsx", ".sh", ".sql", ".rtf", ".log",
                       ".ini", ".cfg", ".toml", ".ps1", ".vbs")
        if not nombre.lower().endswith(extensiones):
            nombre += ".txt"
        nombre = nombre.strip().strip("\"'")
        if not nombre or nombre in (".", ".."):
            return "Señor, no recibí un nombre válido para el archivo."
        # ruta completa
        path = os.path.abspath(os.path.join(base, nombre))
        try:
            # crear carpeta padre si no existe
            padre = os.path.dirname(path)
            if padre and not os.path.isdir(padre):
                os.makedirs(padre, exist_ok=True)
            # escribir (modo "w" crea o sobrescribe)
            with open(path, "w", encoding="utf-8") as f:
                f.write(contenido or "")
            # verificar que realmente existe y tiene tamaño
            if not os.path.isfile(path):
                return f"Señor, escribí el archivo pero no lo encuentro en {path}."
            tam = os.path.getsize(path)
            self.log(f"Archivo creado: {path} ({tam} bytes)")
            extra = f" ({tam} bytes)" if tam > 0 else " (vacío)"
            return (f"Archivo «{nombre}» creado en {path}{extra}, señor. "
                    f"Confirmado en disco.")
        except PermissionError:
            return f"Señor, no tengo permisos para escribir en {path}."
        except OSError as e:
            self.log(f"No pude crear archivo {path}: {e}")
            return f"Señor, no pude crear el archivo: {str(e)[:80]}"

    # ── ARDUINO / EMBEBIDO ──────────────────────────────────────────────────
    _TIPO_EXT = {
        "python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
        "typescript": ".ts", "ts": ".ts", "html": ".html", "css": ".css",
        "json": ".json", "csv": ".csv", "markdown": ".md", "md": ".md",
        "texto": ".txt", "text": ".txt", "txt": ".txt", "bash": ".sh", "sh": ".sh",
        "sql": ".sql", "powershell": ".ps1", "ps1": ".ps1", "batch": ".bat",
        "bat": ".bat", "arduino": ".ino", "ino": ".ino", "java": ".java",
        "c": ".c", "c++": ".cpp", "cpp": ".cpp", "xml": ".xml",
        "yaml": ".yml", "yml": ".yml", "tsx": ".tsx", "jsx": ".jsx",
    }
    _TIPO_BASE = {
        ".py": "script", ".js": "script", ".ts": "script", ".html": "pagina",
        ".css": "estilos", ".json": "datos", ".csv": "datos", ".md": "documento",
        ".txt": "archivo", ".sh": "script", ".sql": "consulta", ".bat": "script",
        ".ino": "sketch", ".java": "programa", ".c": "programa", ".cpp": "programa",
        ".xml": "datos", ".yml": "config", ".yaml": "config",
        ".tsx": "componente", ".jsx": "componente", ".ps1": "script",
    }

    @staticmethod
    def _parece_codigo(s: str) -> bool:
        """True si el contenido parece código real (llaves, paréntesis, etc.)."""
        return bool(re.search(r"[(){}\[\]=\+*/;<>]", s)) or "\n" in s

    @staticmethod
    def _codigo_desde_desc(ext: str, desc: str) -> str:
        """Convierte una descripción ('imprima hola mundo') en un snippet mínimo."""
        d = desc.strip().strip("\"'")
        m = re.match(r"^(?:que\s+)?(?:sume|suma|sume)\s+(?:dos|2)\s+"
                     r"(?:numeros|n[uú]meros)\s*$", d, flags=re.IGNORECASE)
        if m:
            if ext == ".py":
                return ("a = float(input(\"Ingrese el primer número: \"))\n"
                        "b = float(input(\"Ingrese el segundo número: \"))\n"
                        "print(\"La suma es:\", a + b)\n")
            return ("const a = Number(prompt(\"Ingrese el primer número:\"));\n"
                    "const b = Number(prompt(\"Ingrese el segundo número:\"));\n"
                    "console.log(\"La suma es:\", a + b);\n")
        m = re.match(r"^(?:que\s+)?(?:sume|suma|sume)\s+(.+?)\s+"
                     r"(?:con|y|mas|m[áa]s)\s+(.+)$", d, flags=re.IGNORECASE)
        if m:
            a = m.group(1).strip()
            b = m.group(2).strip()
            if ext == ".py":
                return f"a = {a}\nb = {b}\nprint(a + b)\n"
            return f"const a = {a};\nconst b = {b};\nconsole.log(a + b);\n"
        m = re.match(r"^(?:imprima|imprime|diga|muestre|muestra|escriba|escribe)\s+(.+)$",
                     d, flags=re.IGNORECASE)
        if m:
            texto = m.group(1).strip().strip("\"'")
            if ext == ".py":
                return f'print("{texto}")\n'
            return f'console.log("{texto}");\n'
        if ext == ".py":
            return f"# {d}\n"
        return f"// {d}\n"

    @staticmethod
    def _html_desde_desc(desc: str) -> str:
        d = desc.strip().strip("\"'").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return (f'<!DOCTYPE html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
                f"<title>{d[:60]}</title>\n</head>\n<body>\n<h1>{d[:100]}</h1>\n"
                f"</body>\n</html>\n")

    _ARDUINO_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Arduino")

    _SKETCHES = {
        "led": ("blink", """/*
 * LED parpadeante - generado por JARVIS
 */
const int LED = 13;

void setup() {
  pinMode(LED, OUTPUT);
}

void loop() {
  digitalWrite(LED, HIGH);
  delay(1000);
  digitalWrite(LED, LOW);
  delay(1000);
}
"""),
        "temperatura": ("sensor_temperatura", """/*
 * Sensor de temperatura LM35/TMP36 - generado por JARVIS
 */
const int SENSOR = A0;

void setup() {
  Serial.begin(9600);
}

void loop() {
  int lectura = analogRead(SENSOR);
  float voltaje = lectura * (5.0 / 1023.0);
  float celsius = voltaje * 100.0;
  Serial.print("Temperatura: ");
  Serial.print(celsius);
  Serial.println(" C");
  delay(1000);
}
"""),
        "distancia": ("sensor_distancia", """/*
 * Sensor de distancia HC-SR04 - generado por JARVIS
 */
const int TRIG = 9;
const int ECHO = 10;

void setup() {
  Serial.begin(9600);
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
}

void loop() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  long duracion = pulseIn(ECHO, HIGH);
  float cm = duracion * 0.034 / 2;
  Serial.print("Distancia: ");
  Serial.print(cm);
  Serial.println(" cm");
  delay(500);
}
"""),
        "servo": ("servo_motor", """/*
 * Servomotor de barrido - generado por JARVIS
 */
#include <Servo.h>

Servo miServo;

void setup() {
  miServo.attach(9);
}

void loop() {
  for (int ang = 0; ang <= 180; ang++) {
    miServo.write(ang);
    delay(15);
  }
  for (int ang = 180; ang >= 0; ang--) {
    miServo.write(ang);
    delay(15);
  }
}
"""),
        "luz": ("sensor_luz", """/*
 * Sensor de luz (fotorresistencia LDR) - generado por JARVIS
 */
const int LDR = A0;
const int LED = 13;

void setup() {
  Serial.begin(9600);
  pinMode(LED, OUTPUT);
}

void loop() {
  int valor = analogRead(LDR);
  Serial.print("Luz: ");
  Serial.println(valor);
  digitalWrite(LED, valor < 400 ? HIGH : LOW);
  delay(500);
}
"""),
        "humedad": ("sensor_humedad", """/*
 * Sensor de humedad de suelo - generado por JARVIS
 */
const int SENSOR = A0;

void setup() {
  Serial.begin(9600);
}

void loop() {
  int humedad = analogRead(SENSOR);
  int pct = map(humedad, 1023, 200, 0, 100);
  pct = constrain(pct, 0, 100);
  Serial.print("Humedad del suelo: ");
  Serial.print(pct);
  Serial.println("%");
  delay(1000);
}
"""),
        "movimiento": ("detector_movimiento", """/*
 * Detector de movimiento PIR - generado por JARVIS
 */
const int PIR = 7;
const int LED = 13;

void setup() {
  Serial.begin(9600);
  pinMode(PIR, INPUT);
  pinMode(LED, OUTPUT);
}

void loop() {
  if (digitalRead(PIR) == HIGH) {
    digitalWrite(LED, HIGH);
    Serial.println("Movimiento detectado");
    delay(3000);
  } else {
    digitalWrite(LED, LOW);
  }
}
"""),
        "boton": ("boton_led", """/*
 * Boton que controla un LED - generado por JARVIS
 */
const int BOTON = 2;
const int LED = 13;

void setup() {
  Serial.begin(9600);
  pinMode(BOTON, INPUT_PULLUP);
  pinMode(LED, OUTPUT);
}

void loop() {
  if (digitalRead(BOTON) == LOW) {
    digitalWrite(LED, HIGH);
    Serial.println("Boton presionado");
  } else {
    digitalWrite(LED, LOW);
  }
}
"""),
    }

    def _arduino(self, t: str):
        # 1) Subir / compilar un sketch a la placa
        if re.search(r"(?:sube|subir|carga|cargar|graba|grabar|compila|compilar|flashea|programa)\s+(?:el\s+|un\s+|mi\s+|este\s+)?(?:codigo|sketch|programa)\s*(?:a|en|para|hacia)\s*(?:el\s+|la\s+|mi\s+)?(?:arduino|placa|nano|uno|mega|leonardo|esp32|esp8266)", t):
            sketch_dir = self._ultimo_sketch_dir()
            if not sketch_dir:
                return ("Señor, no encontré ningún sketch en la carpeta Arduino. "
                        "Pídame primero que genere un código, por ejemplo: "
                        "«genera un código de arduino para un sensor de distancia».")
            puerto = self._primer_puerto()
            if not puerto:
                return ("Señor, no detecté ninguna placa conectada por USB. "
                        "Conecte el Arduino e inténtelo de nuevo.")
            if self.safe:
                return f"[safe] Subiría {os.path.basename(sketch_dir)} a {puerto}"
            fqbn = self._fqbn_placa()
            if not fqbn:
                return ("Señor, no pude identificar el modelo de la placa. "
                        "Instale el core correspondiente o revise la conexión.")
            self.log(f"Compilando y subiendo {sketch_dir} a {puerto} ({fqbn})...")
            if self.notify:
                self.notify("Compilando y subiendo el código a la placa, señor. Le aviso al terminar.")
            threading.Thread(target=self._subir_hilo, args=(sketch_dir, puerto, fqbn), daemon=True).start()
            return "Compilando y subiendo el código, señor. Le avisaré cuando termine."
        # 2) Generar código/sketch para Arduino
        if re.search(r"(?:gen(?:era|erar)?|crea|haz|escribe)\s+(?:un\s+|el\s+|mi\s+)?(?:codigo|sketch|programa)\s+(?:de|para|del)\s+(?:un\s+|el\s+|la\s+)?(?:arduino|nano|uno|mega|leonardo|esp32|esp8266)", t) or (
           "arduino" in t and re.search(r"(?:gen(?:era|erar)?|crea|haz|escribe)\s+", t) and re.search(r"(?:codigo|sketch)", t)) or (
           re.search(r"(?:gen(?:era|erar)?|crea|haz|escribe)\s+(?:un\s+|el\s+|mi\s+)?(?:codigo|sketch|programa)\s+(?:de|para)", t)
           and re.search(r"(?:led|parpadeo|temperatura|termometro|distancia|ultrasonido|servo|luz|ldr|foto|humedad|suelo|movimiento|pir|boton|pulsador)", t)):
            tema = self._tema_sketch(t)
            nombre_f, codigo = self._SKETCHES[tema]
            base_dir = os.path.join(self._ARDUINO_DIR, nombre_f)
            os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, nombre_f + ".ino")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(codigo)
                return (f"Sketch «{nombre_f}.ino» generado, señor. "
                        f"Guardado en {path}. Puede pedirme subirlo a la placa cuando la conecte.")
            except Exception as e:
                return f"Señor, no pude guardar el sketch: {str(e)[:80]}"
        # 3) Estado / puertos
        if re.search(r"(?:que|lista|muestra|detecta|busca|estado).*(?:arduino|placa|puertos)|(?:puertos|estado)\s*(?:serial|com|usb)", t) or re.search(r"estado del arduino|que arduino|detecta.*placa", t):
            puerto = self._primer_puerto()
            if not puerto:
                return "Señor, no hay ninguna placa conectada en este momento."
            fqbn = self._fqbn_placa()
            placa = fqbn.split(":")[-1] if fqbn else "placa desconocida"
            return f"Placa detectada, señor: {placa} en el puerto {puerto}."
        # 4) Monitor serial
        if re.search(r"(?:lee|leer|monitor(?:ea)?|escucha)\s+(?:el\s+|la\s+|mi\s+)?(?:serial|puerto|monitor)", t):
            puerto = self._primer_puerto()
            if not puerto:
                return "Señor, no hay ninguna placa conectada para leer el puerto serial."
            return self._leer_serial(puerto, seg=2.5)
        return None

    @staticmethod
    def _ultimo_sketch_dir():
        base = os.path.join(os.path.expanduser("~"), "Documents", "Arduino")
        if not os.path.isdir(base):
            return None
        inos = []
        for root, dirs, files in os.walk(base):
            for f in files:
                if f.endswith(".ino"):
                    inos.append((os.path.getmtime(os.path.join(root, f)), root))
        if not inos:
            return None
        inos.sort(reverse=True)
        return inos[0][1]

    @staticmethod
    def _primer_puerto():
        try:
            import serial.tools.list_ports
            puertos = list(serial.tools.list_ports.comports())
            for p in puertos:
                if "USB" in (p.description or "") or "COM" in (p.device or ""):
                    return p.device
            return None
        except Exception:
            return None

    def _fqbn_placa(self):
        try:
            cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "arduino-cli.exe")
            if not os.path.exists(cli):
                return None
            r = subprocess.run([cli, "board", "list", "--format", "json"],
                               capture_output=True, timeout=30, text=True)
            import json as j
            data = j.loads(r.stdout or "[]")
            for b in data:
                fqbn = b.get("fqbn")
                if fqbn:
                    return fqbn
            return None
        except Exception as e:
            self.log(f"fqbn: {e}")
            return None

    def _subir_hilo(self, sketch_dir, puerto, fqbn):
        try:
            cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "arduino-cli.exe")
            r = subprocess.run(
                [cli, "compile", "--upload", "-p", puerto, "--fqbn", fqbn, sketch_dir],
                capture_output=True, timeout=300, text=True)
            ok = r.returncode == 0
            msg = (f"El código se subió a la placa correctamente, señor." if ok
                   else f"Señor, la subida falló: {(r.stderr or r.stdout)[-300:]}")
            self.log(msg)
            if self.notify:
                self.notify(msg)
        except subprocess.TimeoutExpired:
            if self.notify:
                self.notify("Señor, la compilación tardó demasiado. Compruebe la conexión.")
        except Exception as e:
            if self.notify:
                self.notify(f"Señor, error al subir el código: {str(e)[:80]}")

    def _leer_serial(self, puerto, seg=2.5):
        try:
            import serial
            s = serial.Serial(puerto, 9600, timeout=0.5)
            time.sleep(1.2)
            lineas, fin = [], time.time() + seg
            while time.time() < fin:
                try:
                    ln = s.readline().decode("utf-8", "ignore").strip()
                    if ln:
                        lineas.append(ln)
                except Exception:
                    break
            s.close()
            if not lineas:
                return f"El puerto {puerto} está activo pero no envió datos. ¿Baudrate distinto a 9600?"
            return "Datos de la placa, señor:\n" + "\n".join(lineas[-8:])
        except Exception as e:
            return f"Señor, no pude leer el puerto {puerto}: {str(e)[:80]}"

    @staticmethod
    def _tema_sketch(t):
        if any(k in t for k in ("led", "parpadeo", "blink", "foco", "luz led", "destello")):
            return "led"
        if any(k in t for k in ("temperatura", "termometro", "lm35", "tmp36", "celsius")):
            return "temperatura"
        if any(k in t for k in ("distancia", "ultrasonido", "hc-sr04", "hc sr04", "proximidad")):
            return "distancia"
        if any(k in t for k in ("servo", "motor servo", "barrido")):
            return "servo"
        if any(k in t for k in ("luz", "ldr", "foto", "claridad")):
            return "luz"
        if any(k in t for k in ("humedad", "suelo", "riego", "planta")):
            return "humedad"
        if any(k in t for k in ("movimiento", "pir", "presencia")):
            return "movimiento"
        if any(k in t for k in ("boton", "pulsador", "interruptor")):
            return "boton"
        return "led"

    # ── RED ─────────────────────────────────────────────────────────────────
    def _red(self, t: str):
        if re.search(r"informacion (?:de|sobre) (?:mi|la) red|detalles de la red|estado de la red|dame los datos de (?:mi|la) red|como esta (?:mi|la) red|resumen de (?:mi|la) red", t):
            try:
                s = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "$ip=(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'} | Select-Object -First 1); $ip.IPAddress"],
                    capture_output=True, timeout=15, text=True)
                local = (s.stdout or "").strip()
                gw = ""
                dns = ""
                ssid = ""
                try:
                    s2 = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                                        capture_output=True, timeout=15, text=True)
                    for linea in (s2.stdout or "").splitlines():
                        if "SSID" in linea and "BSSID" not in linea:
                            ssid = linea.split(":", 1)[-1].strip()
                except Exception:
                    pass
                try:
                    s3 = subprocess.run(["powershell", "-NoProfile", "-Command",
                                         "(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {$_.ServerAddresses} | Select-Object -First 1).ServerAddresses -join ', '"],
                                        capture_output=True, timeout=15, text=True)
                    dns = (s3.stdout or "").strip()
                except Exception:
                    pass
                try:
                    s4 = subprocess.run(["powershell", "-NoProfile", "-Command",
                                         "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1).NextHop"],
                                        capture_output=True, timeout=15, text=True)
                    gw = (s4.stdout or "").strip()
                except Exception:
                    pass
                partes = [f"IP local: {local}"] if local else []
                if ssid:
                    partes.append(f"Wi-Fi: {ssid}")
                if gw:
                    partes.append(f"puerta de enlace: {gw}")
                if dns:
                    partes.append(f"DNS: {dns}")
                if not partes:
                    return "Señor, no pude obtener los datos de la red."
                return "Señor, su red: " + ", ".join(partes) + "."
            except Exception as e:
                return f"Señor, no pude obtener los datos de la red: {str(e)[:60]}"
        if re.search(r"ip\s+local|direccion local|mi ip local", t):
            try:
                s = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'} | Select-Object -First 1).IPAddress"],
                    capture_output=True, timeout=15, text=True)
                ip = (s.stdout or "").strip()
                return f"Su IP local es {ip}, señor." if ip else "No encontré IP local, señor."
            except Exception as e:
                return f"Señor, no pude obtener la IP local: {str(e)[:60]}"
        if re.search(r"ip\s+publica|mi ip publica", t):
            try:
                with urllib.request.urlopen("https://api.ipify.org", timeout=8) as r:
                    ip = r.read().decode().strip()
                return f"Su IP pública es {ip}, señor."
            except Exception:
                return "Señor, no pude consultar su IP pública. ¿Está conectado a internet?"
        if re.search(r"cual es mi ip|mi ip\b", t):
            try:
                s = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'} | Select-Object -First 1).IPAddress"],
                    capture_output=True, timeout=15, text=True)
                local = (s.stdout or "").strip()
                try:
                    with urllib.request.urlopen("https://api.ipify.org", timeout=8) as r:
                        pub = r.read().decode().strip()
                except Exception:
                    pub = None
                return (f"Señor, su IP local es {local}" + (f" y su IP pública es {pub}" if pub else "") + ".")
            except Exception as e:
                return f"Señor, no pude consultar la IP: {str(e)[:60]}"
        if re.search(r"ping\s+(?:a\s+)?(.+)$", t):
            m = re.search(r"ping\s+(?:a\s+)?(.+)$", t)
            host = m.group(1).strip()
            if self.safe:
                return f"[safe] Haría ping a {host}"
            try:
                r = subprocess.run(["ping", "-n", "4", "-w", "2000", host],
                                   capture_output=True, timeout=20, text=True)
                out = r.stdout or ""
                m2 = re.search(r"media\s*=\s*(\d+)ms", out.lower())
                perdida = re.search(r"(\d+)% perdidos?|\((\d+)%\s*loss\)", out.lower())
                if m2:
                    return f"Ping a {host}, señor: {m2.group(1)} ms de media."
                if "no se pudo" in out.lower() or "no se encuentra" in out.lower() or "timed out" in out.lower():
                    return f"Señor, {host} no respondió al ping."
                return f"Ping a {host} completado, señor. {(perdida.group(1) or perdida.group(2)) if perdida else '?'}% de paquetes perdidos."
            except Exception as e:
                return f"Señor, no pude hacer ping a {host}: {str(e)[:60]}"
        return None

    # ── SISTEMA ─────────────────────────────────────────────────────────────
    def _sistema(self, t: str):
        if re.search(r"info\s+(?:del|de la)\s+(?:pc|sistema|equipo|computadora)|especificaciones|specs\b", t):
            try:
                import platform
                import psutil
                cpu = gpu = "desconocida"
                try:
                    r = subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"],
                        capture_output=True, timeout=15, text=True)
                    cpu = (r.stdout or "").strip() or cpu
                except Exception:
                    pass
                try:
                    r = subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name"],
                        capture_output=True, timeout=15, text=True)
                    gpu = (r.stdout or "").strip() or gpu
                except Exception:
                    pass
                ram = round(psutil.virtual_memory().total / 1024 ** 3, 1)
                return (f"Señor, este equipo es un {platform.node()} con Windows {platform.release()}, "
                        f"CPU {cpu}, {ram} GB de RAM y GPU {gpu}.")
            except Exception as e:
                return f"Señor, no pude leer las especificaciones: {str(e)[:60]}"
        if re.search(r"(?:que|lista|muestra|dime).*(?:procesos|aplicaciones abiertas|programas abiertos)|procesos activos", t):
            try:
                import psutil
                procs = []
                for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
                    try:
                        p.cpu_percent(None)
                    except Exception:
                        pass
                time.sleep(0.6)
                SISTEMA = {"system idle process", "system", "registry", "smss.exe", "csrss.exe",
                           "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe",
                           "svchost.exe", "fontdrvhost.exe", "dwm.exe", "conhost.exe",
                           "sihost.exe", "taskhostw.exe", "runtimebroker.exe"}
                for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
                    try:
                        n = (p.info["name"] or "").lower()
                        if n and n not in SISTEMA:
                            c = p.cpu_percent(None) or 0
                            procs.append((p.info["name"], round(min(c, 100), 1)))
                    except Exception:
                        pass
                procs.sort(key=lambda x: -x[1])
                top = procs[:10]
                if not top:
                    return "No hay procesos listables, señor."
                return "Procesos más activos, señor: " + ", ".join(f"{n} ({c}%)" for n, c in top) + "."
            except Exception as e:
                return f"Señor, no pude listar procesos: {str(e)[:60]}"
        if re.search(r"(?:mata|cierra|termina|finaliza|elimina)\s+(?:el\s+|un\s+)?proceso\s+(?:llamado\s+|de\s+nombre\s+)?(.+)$", t):
            m = re.search(r"(?:mata|cierra|termina|finaliza|elimina)\s+(?:el\s+|un\s+)?proceso\s+(?:llamado\s+|de\s+nombre\s+)?(.+)$", t)
            proc = m.group(1).strip()
            if self.safe:
                return f"[safe] Mataría el proceso {proc}"
            try:
                r = subprocess.run(["taskkill", "/IM", proc if proc.lower().endswith(".exe") else proc + ".exe", "/F"],
                                   capture_output=True, timeout=15, text=True)
                if r.returncode == 0:
                    return f"Proceso {proc} terminado, señor."
                return f"Señor, no pude terminar {proc}: {(r.stderr or r.stdout)[:80].strip()}"
            except Exception as e:
                return f"Señor, error al terminar {proc}: {str(e)[:60]}"
        if re.search(r"vacia(?:r)?\s+(?:la\s+)?papelera|limpia(?:r)?\s+(?:la\s+)?papelera", t):
            if self.safe:
                return "[safe] Vaciaría la papelera de reciclaje"
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                               capture_output=True, timeout=30)
                return "Papelera de reciclaje vaciada, señor."
            except Exception as e:
                return f"Señor, no pude vaciar la papelera: {str(e)[:60]}"
        return None

    # ── CALCULADORA (evaluación segura con AST) ─────────────────────────────
    @staticmethod
    def _eval_segura(expr):
        import ast
        tree = ast.parse(expr, mode="eval")
        permitidos = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                      ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
                      ast.Pow, ast.USub, ast.UAdd)
        for nodo in ast.walk(tree):
            if not isinstance(nodo, permitidos):
                raise ValueError("expresión no permitida")
        return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, {})

    def _calculadora(self, t: str):
        m = re.search(
            r"(?:cuanto es|cuanto da|calcula|calcular|resultado de|resuelve|dime cuanto es|que es|cuanto sera)\s+(.+?)\s*\??$", t)
        if not m or not re.search(r"\d", m.group(1)):
            return None
        expr = m.group(1).lower()
        expr = expr.replace("dividido entre", "/").replace("elevado a", "**")
        expr = expr.replace("mas", "+").replace("menos", "-").replace("por", "*")
        expr = expr.replace("entre", "/").replace("^", "**")
        expr = expr.replace("x", "*").replace("×", "*").replace("÷", "/")
        expr = re.sub(r"\s+", "", expr)
        if not re.fullmatch(r"[\d\+\-\*\/\(\)\.%]+", expr):
            return None
        try:
            res = self._eval_segura(expr)
            if isinstance(res, float) and res.is_integer():
                res = int(res)
            return f"El resultado es {res}, señor."
        except Exception:
            return "Señor, no pude resolver esa operación."
        return None

    # ── WIFI ────────────────────────────────────────────────────────────────
    def _wifi(self, t: str):
        if re.search(r"(?:que|lista|muestra|dime|ver).*(?:wifi|redes)|redes (?:wifi|guardadas)|perfiles wifi", t):
            try:
                r = subprocess.run(["netsh", "wlan", "show", "profiles"], capture_output=True, timeout=15, text=True)
                out = r.stdout or ""
                redes = [x.strip() for x in re.findall(r":\s+(.+)$", out, re.M)
                         if "solo lectura" not in x and "directiva" not in x]
                if not redes:
                    return "Señor, no hay perfiles wifi guardados en este equipo."
                return "Redes wifi guardadas, señor: " + ", ".join(redes[:12]) + "."
            except Exception as e:
                return f"Señor, no pude listar las redes wifi: {str(e)[:60]}"
        if re.search(r"conectate\s+(?:a\s+|con\s+)?(?:la\s+|mi\s+)?(?:red|wifi)\s+(?:llamada\s+|de\s+nombre\s+)?(.+)$", t):
            m = re.search(r"conectate\s+(?:a\s+|con\s+)?(?:la\s+|mi\s+)?(?:red|wifi)\s+(?:llamada\s+|de\s+nombre\s+)?(.+)$", t)
            mo = re.search(r"conectate\s+(?:a\s+|con\s+)?(?:la\s+|mi\s+)?(?:red|wifi)\s+(?:llamada\s+|de\s+nombre\s+)?(.+)$", self._orig_lower)
            red = (mo.group(1).strip() if mo else m.group(1).strip()).strip(".")
            if self.safe:
                return f"[safe] Me conectaría a la red {red}"
            try:
                r = subprocess.run(["netsh", "wlan", "connect", f"name={red}"],
                                   capture_output=True, timeout=15, text=True)
                if r.returncode == 0:
                    return f"Conectando a la red {red}, señor."
                return f"Señor, no pude conectarme a {red}: {(r.stderr or r.stdout)[:80].strip()}"
            except Exception as e:
                return f"Señor, error al conectarme: {str(e)[:60]}"
        if re.search(r"estado\s+del\s+wifi|estoy conectado|hay internet|tengo red", t):
            try:
                r = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, timeout=15, text=True)
                out = r.stdout or ""
                m = re.search(r"SSID\s*:\s*(.+)", out)
                return f"Señor, está conectado a la red «{m.group(1).strip()}»." if m else "Señor, no hay wifi conectado en este momento."
            except Exception as e:
                return f"Señor, no pude consultar el wifi: {str(e)[:60]}"
        return None

    # ── QR ──────────────────────────────────────────────────────────────────
    def _qr(self, t: str):
        if not re.search(r"(?:qr|codigo qr)", t):
            return None
        m = re.search(r"(?:con|para|del|de|que diga|que contenga|con el texto)\s+(.+)$", t)
        texto = m.group(1).strip() if m else t.split("qr", 1)[-1].strip(" :")
        if not texto:
            return None
        try:
            import qrcode
            qr_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "QR")
            os.makedirs(qr_dir, exist_ok=True)
            img = qrcode.make(texto[:200])
            nombre = self._nuevo_nombre(qr_dir, "qr", ext=".png")
            path = os.path.join(qr_dir, nombre)
            img.save(path)
            return f"Código QR generado, señor. Guardado en {path} con el contenido «{texto[:60]}»."
        except Exception as e:
            return f"Señor, no pude generar el QR: {str(e)[:80]}"

    # ── AZAR ────────────────────────────────────────────────────────────────
    def _azar(self, t: str):
        import random
        if re.search(r"lanza\s+(?:un\s+|el\s+|los\s+)?dado|tira\s+(?:un\s+|el\s+)dado|tirar dados", t):
            n = random.randint(1, 6)
            return f"El dado cayó en {n}, señor."
        if re.search(r"cara\s+o\s+cruz|lanza\s+(?:una\s+|la\s+)?moneda|tira\s+(?:una\s+|la\s+)?moneda", t):
            return "Cara, señor." if random.random() < 0.5 else "Cruz, señor."
        if re.search(r"elige\s+entre|decide\s+entre|azar\s+entre", t):
            m = re.search(r"(?:elige|decide|azar)\s+entre\s+(.+)$", t)
            if m:
                opciones = [o.strip() for o in m.group(1).split(" o ") if o.strip()]
                if len(opciones) >= 2:
                    return f"He elegido: {random.choice(opciones)}, señor."
        return None

    # ── AYUDANTES COMUNES ────────────────────────────────────────────────────
    def _avisar(self, msg: str):
        """Aviso diferido: TTS si hay notify, si no al log, y push al móvil."""
        if self._modo_silencio:
            return
        self._avisos_registrar(msg)
        if (self._invitado or self._gaming) and not msg.startswith("[!]"):
            return
        # Sanear emojis/caracteres especiales para consola Windows
        safe_msg = msg.encode("ascii", "ignore").decode("ascii")
        if self.notify:
            self.notify(msg)
        else:
            self.log(safe_msg)
        if not self.safe:
            try:
                req = urllib.request.Request(
                    jarvis_config.url_flask("/notify"),
                    data=json.dumps({"text": msg}).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=1.5)
            except Exception:
                pass

    # ── MÚSICA (YouTube vía yt-dlp + ffplay) ─────────────────────────────────
    @staticmethod
    def _media_key(vk: int):
        """Tecla multimedia de Windows (0xB3 play/pause, 0xB0 next, 0xB1 prev)."""
        import ctypes
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

    def _matar_reproductor(self):
        if self._player and self._player.poll() is None:
            try:
                self._player.terminate()
            except Exception:
                pass
        self._player = None

    def _musica(self, t: str):
        if re.search(r"descarga|descargar|baja\b", t):
            return None
        if re.search(r"(para|deten|detener|pausa|pausar|silencio|apaga)\s+(?:la\s+|de\s+)?(?:musica|cancion|reproduccion|playlist)", t):
            self._matar_reproductor()
            self._media_key(0xB3)
            return "Música parada, señor."
        if re.search(r"(siguiente cancion|siguiente tema|cambia de cancion|cancion siguiente|pasame la siguiente)", t):
            self._media_key(0xB0)
            return "Siguiente canción, señor."
        if re.search(r"(cancion anterior|anterior cancion|vuelve a la cancion|retrocede)", t):
            self._media_key(0xB1)
            return "Canción anterior, señor."
        m = re.search(
            r"(?:pon|ponme|ponte|reproduce|reproducir|suena|suename|toca|pon a sonar|pon a tocar)\s+"
            r"(?:(?:la|una|un|esa|ese|este)\s+)?(?:cancion|musica|melodia|tema|playlist|lista de reproduccion)\s*"
            r"(?:de\s+|llamada\s+|llamado\s+|sobre\s+)?(?P<q>.+?)\s*$", t)
        if not m:
            m = re.search(r"(?:reproduce|reproducir|suena|suename|toca|pon a sonar|pon a tocar|ponme|ponte)\s+(?P<q>.+?)\s*$", t)
        if not m:
            return None
        q = m.group("q").strip().strip(".")
        if not q or len(q) < 2 or any(k in q for k in (
                "volumen", "alarma", "temporizador", "nota", "modo", "descanso",
                "enfoque", "apagado", "despertador", "el clima", "el tiempo")):
            return None
        if q in APP_MAP:
            return None
        if self.safe:
            return f"(modo seguro: no reproduciría «{q[:40]}»)"
        def _do():
            try:
                import yt_dlp, shutil
                ffdir = self._ffmpeg_location()
                opts = {
                    "format": "bestaudio/best",
                    "quiet": True, "noplaylist": True, "noprogress": True,
                    "extractor_args": {"youtube": {"player_client": ["tv_embedded", "android"]}},
                }
                if ffdir:
                    opts["ffmpeg_location"] = ffdir
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(f"ytsearch1:{q}", download=False)
                entry = (info.get("entries") or [info])[0]
                url = entry.get("url")
                titulo = (entry.get("title") or q)[:60]
                ffplay = os.path.join(ffdir, "ffplay.exe") if ffdir else shutil.which("ffplay")
                if ffplay and url:
                    self._matar_reproductor()
                    self._player = subprocess.Popen(
                        [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", url],
                        creationflags=0x08000000)
                    self._avisar(f"Reproduciendo «{titulo}», señor.")
                elif entry.get("webpage_url"):
                    subprocess.Popen(["start", "", entry["webpage_url"]], shell=True)
                    self._avisar(f"No encontré el reproductor de audio; abro «{titulo}» en el navegador, señor.")
            except Exception as e:
                self.log(f"Musica fallo: {e}")
                self._avisar(f"Señor, no pude reproducir «{q[:40]}»: {str(e)[:100]}")
        threading.Thread(target=_do, daemon=True).start()
        return f"Enseguida, señor. Poniendo «{q[:50]}»..."

    # ── LISTA DE LA COMPRA / TAREAS (persistente, compartida con el móvil) ──
    def _lista_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Lista")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "lista.json")

    def _lista_leer(self) -> list:
        try:
            return json.load(open(self._lista_path(), encoding="utf-8"))
        except Exception:
            return []

    def _lista_guardar(self, items: list):
        with open(self._lista_path(), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    def _lista(self, t: str):
        if not re.search(r"lista", t):
            return None
        # añadir
        m = re.search(r"(?:añade|anade|agrega|agregar|apunta|anota|mete|pon)\s+(?P<item>.+?)\s+(?:a\s+la\s+|en\s+la\s+|a\s+mi\s+|en\s+mi\s+)?lista", t)
        if m:
            item = m.group("item").strip().strip(".")
            if not item or len(item) > 60:
                return None
            items = self._lista_leer()
            norm = self._norm(item)
            if any(self._norm(i["texto"]) == norm for i in items):
                return f"«{item}» ya está en su lista, señor."
            items.append({"texto": item, "ts": datetime.now().isoformat()})
            self._lista_guardar(items)
            return f"Añadido «{item}» a su lista, señor. Lleva {len(items)} elementos."
        # quitar
        m = re.search(r"(?:quita|quitame|elimina|borra|tacha|saca)\s+(?P<item>.+?)\s+(?:de\s+la\s+|de\s+mi\s+)?lista", t)
        if m:
            item = m.group("item").strip().strip(".")
            items = self._lista_leer()
            norm = self._norm(item)
            restantes = [i for i in items if self._norm(i["texto"]) != norm]
            if len(restantes) == len(items):
                return f"Señor, «{item}» no estaba en su lista."
            self._lista_guardar(restantes)
            return f"«{item}» quitado de su lista, señor. Quedan {len(restantes)}."
        # vaciar
        if re.search(r"(vacia|vaciar|borra|elimina)\s+(?:toda\s+la\s+|toda\s+|la\s+|mi\s+)?lista", t):
            self._lista_guardar([])
            return "Lista vaciada, señor."
        # mostrar
        if re.search(r"(muestra|dime|ver|enseñame|leeme|lee|leer|que hay|que tengo|revisa)\s+.*lista|^lista\b", t):
            items = self._lista_leer()
            if not items:
                return "Señor, su lista está vacía."
            textos = [i["texto"] for i in items]
            return f"Su lista tiene {len(textos)} elementos: " + ", ".join(textos) + ", señor."
        return None

    # ── AGENDA / CALENDARIO LOCAL ────────────────────────────────────────────
    def _agenda_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Agenda")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "agenda.json")

    def _agenda_leer(self) -> list:
        try:
            return json.load(open(self._agenda_path(), encoding="utf-8"))
        except Exception:
            return []

    def _agenda_guardar(self, eventos: list):
        with open(self._agenda_path(), "w", encoding="utf-8") as f:
            json.dump(eventos, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _fecha_agenda(texto: str):
        """Extrae fecha/hora de texto normalizado. -> (datetime, texto_restante)"""
        now = datetime.now()
        hh = mm = None
        m = re.search(r"(?:a\s+las|a\s+la)\s+(\d{1,2})[:.](\d{2})", texto)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            if hh > 23 or mm > 59:
                hh = mm = None
            else:
                texto = texto[:m.start()] + " " + texto[m.end():]
        else:
            m = re.search(r"(?:a\s+las|a\s+la)\s+(\d{1,2})\s*(?:horas?)?", texto)
            if m and int(m.group(1)) <= 23:
                hh, mm = int(m.group(1)), 0
                texto = texto[:m.start()] + " " + texto[m.end():]
        DIA_N = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        MES_N = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        fecha = None
        if re.search(r"pasado\s+manana", texto):
            fecha = now + timedelta(days=2)
            texto = re.sub(r"pasado\s+manana", "", texto)
        elif re.search(r"\bmanana\b", texto):
            fecha = now + timedelta(days=1)
            texto = re.sub(r"\bmanana\b", "", texto)
        elif re.search(r"\bhoy\b|esta\s+noche", texto):
            fecha = now
            texto = re.sub(r"\bhoy\b|esta\s+noche", "", texto)
        else:
            m = re.search(r"(?:el\s+)?(lunes|martes|miercoles|jueves|viernes|sabado|domingo)", texto)
            if m:
                hoy = now.weekday()
                idx = DIA_N.index(m.group(1))
                delta = (idx - hoy) % 7 or 7
                fecha = now + timedelta(days=delta)
                texto = re.sub(r"(?:el\s+)?(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)", "", texto, count=1)
            else:
                m = re.search(r"el\s+(\d{1,2})\s+de\s+([a-z]+)", texto)
                if m and int(m.group(1)) <= 31 and m.group(2) in MES_N:
                    try:
                        fecha = now.replace(month=MES_N.index(m.group(2)) + 1, day=int(m.group(1)))
                        if fecha < now:
                            fecha = fecha.replace(year=fecha.year + 1)
                        texto = re.sub(r"el\s+\d{1,2}\s+de\s+[a-z]+", "", texto, count=1)
                    except ValueError:
                        fecha = None
                else:
                    m = re.search(r"el\s+(\d{1,2})", texto)
                    if m and 1 <= int(m.group(1)) <= 31:
                        try:
                            fecha = now.replace(day=int(m.group(1)))
                        except ValueError:
                            fecha = None
                        if fecha and fecha < now:
                            fecha = (now + timedelta(days=40)).replace(day=int(m.group(1)))
                        if fecha:
                            texto = re.sub(r"el\s+\d{1,2}", "", texto, count=1)
        if fecha is None:
            return None, texto
        fecha = fecha.replace(hour=hh if hh is not None else 9, minute=mm if mm is not None else 0, second=0, microsecond=0)
        return fecha, texto

    def _agenda(self, t: str):
        if re.search(r"(?:crea|crear|anota|apunta|agenda|agendar|programa)\s+(?:un\s+|el\s+)?(?:evento|cita|compromiso)", t):
            m = re.search(r"(?:crea|crear|anota|apunta|agenda|agendar|programa)\s+(?:un\s+|el\s+)?(?:evento|cita|compromiso)\s+(?:para\s+|de\s+)?(?P<desc>.+?)\s*$", t)
            if not m:
                return None
            resto = m.group("desc").strip()
            fecha, resto = self._fecha_agenda(resto)
            if not fecha:
                return None
            titulo = resto.strip().strip(",.-")
            if not titulo:
                return None
            eventos = self._agenda_leer()
            eventos.append({"cuando": fecha.strftime("%Y-%m-%d %H:%M"), "titulo": titulo})
            self._agenda_guardar(eventos)
            return (f"Anotado, señor: «{titulo}» el {fecha.strftime('%d/%m')} a las "
                    f"{fecha.strftime('%H:%M')}. Lleva {len(eventos)} eventos.")
        if re.search(r"(?:que\s+tengo|que\s+hay|agenda|eventos|compromisos|citas\s+programadas)", t):
            fecha, _ = self._fecha_agenda(t)
            eventos = sorted(self._agenda_leer(), key=lambda e: e["cuando"])
            hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if fecha:
                inicio = fecha.replace(hour=0, minute=0, second=0, microsecond=0)
                fin = inicio + timedelta(days=1)
                del_dia = [e for e in eventos if inicio <= datetime.strptime(e["cuando"], "%Y-%m-%d %H:%M") < fin]
                if not del_dia:
                    return f"Señor, no tiene eventos {fecha.strftime('el %d/%m')}."
                lista = ", ".join(f"«{e['titulo']}» a las {e['cuando'][11:16]}" for e in del_dia)
                return f"Señor, {fecha.strftime('el %d/%m')} tiene: {lista}."
            proximos = [e for e in eventos if datetime.strptime(e["cuando"], "%Y-%m-%d %H:%M") >= hoy][:5]
            if not proximos:
                return "Señor, no tiene eventos próximos en la agenda."
            lista = ", ".join(f"«{e['titulo']}» el {e['cuando'][8:10]}/{e['cuando'][5:7]} a las {e['cuando'][11:16]}" for e in proximos)
            return f"Sus próximos eventos, señor: {lista}."
        if re.search(r"(?:borra|borrar|elimina|eliminar)\s+(?:el\s+)?evento", t):
            m = re.search(r"(?:borra|borrar|elimina|eliminar)\s+(?:el\s+)?evento\s+(?:de\s+)?(?P<ev>.+?)\s*$", t)
            if not m:
                return None
            nombre = m.group("ev").strip().strip(".")
            eventos = self._agenda_leer()
            restantes = [e for e in eventos if self._norm(e["titulo"]) != self._norm(nombre)]
            if len(restantes) == len(eventos):
                return f"Señor, no encontré el evento «{nombre}»."
            self._agenda_guardar(restantes)
            return f"Evento «{nombre}» eliminado de su agenda, señor."
        if re.search(r"(vacia|vaciar|borra|elimina)\s+(?:toda\s+la\s+)?agenda", t):
            self._agenda_guardar([])
            return "Agenda vaciada, señor."
        return None

    # ── RESUMIR URL / PDF / ARCHIVO / TEMA ───────────────────────────────────
    def _resumir_fuente(self, q: str) -> str:
        if re.match(r"https?://\S+", q):
            try:
                req = urllib.request.Request(q, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
                texto = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
                texto = re.sub(r"<[^>]+>", " ", texto)
                texto = re.sub(r"\s+", " ", texto).strip()
                if len(texto) < 40:
                    return ""
                return texto[:1200] + ("..." if len(texto) > 1200 else "")
            except Exception:
                return ""
        p = os.path.abspath(os.path.expanduser(q))
        if os.path.exists(p):
            ext = os.path.splitext(p)[1].lower()
            try:
                if ext == ".pdf":
                    import fitz
                    doc = fitz.open(p)
                    texto = " ".join(doc[i].get_text() for i in range(min(3, len(doc))))
                    doc.close()
                elif ext in (".txt", ".md", ".py", ".html", ".htm", ".csv", ".json", ".log", ".xml"):
                    texto = open(p, encoding="utf-8", errors="ignore").read()
                else:
                    return f"Formato {ext or 'desconocido'} no soportado para resumir, señor."
                texto = re.sub(r"\s+", " ", texto).strip()
                if len(texto) < 10:
                    return "El archivo no contiene texto legible, señor."
                return texto[:1200] + ("..." if len(texto) > 1200 else "")
            except Exception:
                return ""
        return ""

    def _resumir(self, t: str):
        m = re.search(r"(?:resume|resumeme|resumir|haz\s+un\s+resumen|hazme\s+un\s+resumen|resumen\s+de)\s+(?P<q>.+?)\s*$", t)
        if not m:
            return None
        q = m.group("q").strip().strip("?.")
        if not q or len(q) < 2:
            return None
        if self.safe:
            return f"(modo seguro: no resumiría «{q[:40]}»)"
        def _do():
            try:
                res = self._resumir_fuente(q)
                if not res:
                    tema = self._investigar_tema(q)
                    res = re.sub(r"\s+", " ", tema or "").strip()
                    res = res[:1200] + ("..." if len(res) > 1200 else "") if res else ""
                if res:
                    self._avisar("Resumen, señor: " + res[:600])
                else:
                    self._avisar(f"Señor, no pude obtener contenido de «{q[:40]}».")
            except Exception as e:
                self.log(f"Resumen fallo: {e}")
                self._avisar(f"Señor, no pude resumir «{q[:40]}»: {str(e)[:100]}")
        threading.Thread(target=_do, daemon=True).start()
        return f"Resumiendo «{q[:50]}», señor. Un momento."

    # ── TRADUCIR (MyMemory, gratis sin clave) ────────────────────────────────
    _IDIOMAS = {"ingles": "en", "english": "en", "frances": "fr", "aleman": "de",
                "italiano": "it", "portugues": "pt", "japones": "ja", "chino": "zh-CN",
                "arabe": "ar", "ruso": "ru", "catalan": "ca", "coreano": "ko",
                "holandes": "nl", "turco": "tr", "polaco": "pl", "griego": "el",
                "latin": "la"}

    def _traducir(self, t: str):
        m = re.search(r"(?:traduce|traducir|traduccion|traducime|traducemelo|pasamelo|pasame)\s+"
                      r"(?P<txt>.+?)\s+(?:al|a)\s+(?P<idi>[a-z]+)\s*$", t)
        if not m:
            return None
        idi = m.group("idi").lower()
        cod = self._IDIOMAS.get(idi)
        if not cod:
            return None
        txt = m.group("txt").strip().strip("\"'")
        txt = re.sub(r"^(?:este\s+texto|esta\s+frase|el\s+texto|la\s+frase|lo\s+siguiente|esto|esta|este|el|la)\s*[:,\-]?\s*", "", txt)
        if not txt or len(txt) > 500:
            return None
        if self.safe:
            return f"(modo seguro: no traduciría «{txt[:40]}»)"
        def _do():
            try:
                import urllib.parse
                url = ("https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(txt)
                       + "&langpair=es|" + cod)
                with urllib.request.urlopen(url, timeout=15) as r:
                    data = json.loads(r.read().decode("utf-8", "ignore"))
                traducido = (data.get("responseData") or {}).get("translatedText") or ""
                if traducido:
                    self._avisar(f"Traducción al {idi}, señor: {traducido[:300]}")
                else:
                    self._avisar("Señor, no obtuve la traducción. Verifique el texto.")
            except Exception as e:
                self.log(f"Traduccion fallo: {e}")
                self._avisar("Señor, el servicio de traducción no respondió.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Traduciendo al {idi}, señor. Un momento."

    # ── CARTELERA DE CINE (investigación web) ────────────────────────────────
    def _cine(self, t: str):
        if not re.search(r"cartelera|estrenos|que ponen en el cine|\bcine\b|peliculas en cartelera", t):
            return None
        ciudad = re.search(r"(?:en|de|para)\s+([a-záéíóúñ]+(?:\s+[a-záéíóúñ]+)?)\s*$", t)
        q = "cartelera de cine de esta semana" + (" en " + ciudad.group(1) if ciudad else "")
        def _do():
            try:
                res = self._investigar_tema(q)
                if not res or len(res) < 20:
                    self._avisar("Señor, no he podido obtener la cartelera en este momento.")
                else:
                    texto = re.sub(r"\s+", " ", res).strip()
                    self._avisar("Cartelera, señor: " + texto[:500])
            except Exception as e:
                self.log(f"Cine fallo: {e}")
                self._avisar("Señor, no pude consultar la cartelera.")
        threading.Thread(target=_do, daemon=True).start()
        return "Consultando la cartelera de cine, señor. Un momento."

    # ── RECETAS DE COCINA (investigación web) ────────────────────────────────
    def _receta(self, t: str):
        m = re.search(r"(?:dame\s+la\s+receta|receta|recetas|como\s+se\s+hace|como\s+hago|"
                      r"cocina|cocinar|prepara|preparame)\s+(?:de\s+|de\s+un\s+|de\s+una\s+|un\s+|una\s+)?"
                      r"(?P<q>.+?)\s*$", t)
        if not m:
            return None
        q = m.group("q").strip().strip("?.")
        if not q or len(q) < 2 or any(k in q for k in ("archivo", "documento")):
            return None
        def _do():
            try:
                res = self._investigar_tema(f"receta de {q} paso a paso con ingredientes")
                if not res or len(res) < 20:
                    self._avisar(f"Señor, no encontré una receta de {q}.")
                else:
                    self._avisar("Receta, señor: " + re.sub(r"\s+", " ", res).strip()[:600])
            except Exception as e:
                self.log(f"Receta fallo: {e}")
                self._avisar(f"Señor, no pude buscar la receta de {q}.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Buscando la receta de «{q}», señor. Un momento."

    # ── BACKUPS (zip con fecha) ──────────────────────────────────────────────
    def _backup(self, t: str):
        if not re.search(r"backup|respalda|respaldar|copia\s+de\s+seguridad|haz\s+un\s+zip|\bzip\s+de", t):
            return None
        m = re.search(r"(?:backup|respalda|respaldar|haz\s+un\s+backup|copia\s+de\s+seguridad|haz\s+un\s+zip|zip)"
                      r"\s+(?:de\s+|de\s+la\s+|de\s+el\s+|de\s+las\s+)?(?P<src>.+?)\s*(?:\s+en\s+(?P<dst>.+?))?\s*$", t)
        if not m:
            return None
        src = m.group("src").strip().strip(".")
        ruta = self._ubicacion_real(src)
        if not ruta or not os.path.exists(ruta):
            return f"Señor, no encontré «{src[:40]}» para respaldar."
        dst = (m.group("dst") or "").strip().strip(".")
        if "onedrive" in dst.lower():
            base = os.path.join(os.path.expanduser("~"), "OneDrive", "JARVIS", "Backups")
        elif "pendrive" in dst.lower() or "usb" in dst.lower():
            import ctypes, string
            base = None
            for letra in string.ascii_uppercase:
                r = f"{letra}:\\"
                try:
                    if ctypes.windll.kernel32.GetDriveTypeW(r) == 2:  # removible
                        base = os.path.join(r, "JARVIS", "Backups")
                        break
                except Exception:
                    pass
            if not base:
                return "Señor, no detecto ningún pendrive conectado."
        else:
            base = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Backups")
        os.makedirs(base, exist_ok=True)
        if self.safe:
            return f"(modo seguro: no crearía el backup de «{src[:40]}»)"
        def _do():
            try:
                import shutil
                nombre = os.path.basename(ruta.rstrip("\\/")) or "backup"
                destino = os.path.join(base, f"{nombre}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                ruta_zip = shutil.make_archive(destino, "zip", root_dir=ruta)
                tam = os.path.getsize(ruta_zip) / 1048576
                self._avisar(f"Backup completado, señor: {os.path.basename(ruta_zip)} ({tam:.1f} MB).")
            except Exception as e:
                self.log(f"Backup fallo: {e}")
                self._avisar(f"Señor, el backup de «{src[:40]}» falló: {str(e)[:100]}")
        threading.Thread(target=_do, daemon=True).start()
        return f"Creando el backup de «{src[:40]}», señor."

    # ── PROCESOS: matar y top de memoria ─────────────────────────────────────
    def _procesos(self, t: str):
        m = re.search(r"(?:mata|matar|termina\s+el\s+proceso|cierra\s+el\s+proceso|finaliza\s+el\s+proceso)"
                      r"\s+(?:el\s+|al\s+)?(?P<pr>.+?)\s*$", t)
        if m:
            pr = m.group("pr").strip().strip(".")
            if not pr or len(pr) > 40:
                return None
            if self.safe:
                return f"(modo seguro: no mataría «{pr}»)"
            exe = CLOSE_MAP.get(pr) or (pr if pr.lower().endswith(".exe") else pr + ".exe")
            subprocess.Popen(f"taskkill /IM {exe} /F", shell=True, creationflags=0x08000000)
            return f"Proceso {pr} terminado, señor."
        if re.search(r"procesos?\s+(?:pesados|que\s+pesan|top)|que\s+procesos\s+pesan|mayor\s+uso\s+de\s+memoria|mas\s+memoria", t):
            if self.safe:
                return "(modo seguro: no consultaría los procesos)"
            try:
                import psutil
                procs = []
                for p in psutil.process_iter(["name", "memory_info"]):
                    try:
                        rss = p.info["memory_info"].rss if p.info["memory_info"] else 0
                        procs.append((p.info["name"] or "?", rss))
                    except Exception:
                        pass
                top = sorted(procs, key=lambda x: -x[1])[:8]
                partes = [f"{n} ({b / 1048576:.0f} MB)" for n, b in top]
                return "Los procesos que más memoria usan: " + ", ".join(partes) + ", señor."
            except Exception as e:
                return f"Señor, no pude leer los procesos: {str(e)[:80]}"
        if re.search(r"cuantos procesos|cuantos programas|cuantos procesos hay", t):
            try:
                import psutil
                return f"Hay {len(list(psutil.process_iter()))} procesos en ejecución, señor."
            except Exception:
                return None
        return None

    # ── LIMPIEZA: papelera, temporales, espacio en disco ─────────────────────
    def _limpieza(self, t: str):
        if re.search(r"vacia\s+la\s+papelera|vaciar\s+la\s+papelera|limpia\s+la\s+papelera|papelera\s+de\s+reciclaje", t):
            if self.safe:
                return "Papelera vaciada, señor. (modo seguro: no ejecutado)"
            subprocess.Popen(["powershell", "-NoProfile", "-Command",
                              "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                             creationflags=0x08000000)
            return "Papelera vaciada, señor."
        if re.search(r"limpia\s+los\s+temporales|borra\s+los\s+temporales|limpiar\s+temporales|archivos\s+temporales", t):
            if self.safe:
                return "(modo seguro: no borraría temporales)"
            def _do():
                try:
                    temp = tempfile.gettempdir()
                    borrados = 0
                    liberado = 0
                    ahora = time.time()
                    for raiz, _, archivos in os.walk(temp):
                        for a in archivos:
                            try:
                                p = os.path.join(raiz, a)
                                if ahora - os.path.getmtime(p) > 7 * 86400:
                                    liberado += os.path.getsize(p)
                                    os.remove(p)
                                    borrados += 1
                            except Exception:
                                pass
                    self._avisar(f"Limpieza de temporales, señor: {borrados} archivos borrados, "
                                f"{liberado / 1048576:.0f} MB liberados.")
                except Exception as e:
                    self.log(f"Limpieza fallo: {e}")
                    self._avisar("Señor, no pude limpiar los temporales.")
            threading.Thread(target=_do, daemon=True).start()
            return "Limpiando archivos temporales, señor."
        if re.search(r"espacio\s+(?:libre|en\s+disco|disponible|del\s+disco)|cuanto\s+(?:queda|espacio)|disco\s+duro\s+lleno", t):
            try:
                import ctypes
                libre = ctypes.c_ulonglong(0)
                total = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p("C:\\"), None, ctypes.pointer(total), ctypes.pointer(libre))
                return (f"Señor, en C: quedan {libre.value / 1073741824:.0f} GB libres "
                        f"de {total.value / 1073741824:.0f} GB.")
            except Exception:
                return None
        return None

    # ── ENVIAR CAPTURA AL MÓVIL ─────────────────────────────────────────────
    @staticmethod
    def _ip_lan() -> str:
        return jarvis_config.LOCAL_IP

    def _enviar_captura(self, t: str):
        if not re.search(r"(?:manda|envia|enviame|mandame|pasame|pasa)\s+(?:la\s+|me\s+la\s+|una\s+|mi\s+)?"
                         r"(?:captura|foto|pantalla|screenshot)\s+(?:a\s+)?(?:mi\s+|el\s+|al\s+)?"
                         r"(?:telefono|movil|celular)", t):
            return None
        if self.safe:
            return "(modo seguro: no enviaría la captura)"
        def _do():
            try:
                from PIL import ImageGrab
                base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "web_interface", "capturas")
                os.makedirs(base, exist_ok=True)
                nombre = f"captura_{datetime.now().strftime('%H%M%S')}.png"
                ImageGrab.grab().save(os.path.join(base, nombre), "PNG")
                url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/capturas/{nombre}"
                self._avisar(f"Captura enviada a su teléfono: {url}")
                self.log(f"Captura para movil: {url}")
            except Exception as e:
                self.log(f"Envio captura fallo: {e}")
                self._avisar("Señor, no pude enviar la captura a su teléfono.")
        threading.Thread(target=_do, daemon=True).start()
        return "Enviando la captura a su teléfono, señor."

    # ── VIGILANCIA CON CÁMARA (detección de movimiento) ──────────────────────
    def _vigilar(self, t: str):
        if re.search(r"deja\s+de\s+vigilar|para\s+la\s+vigilancia|para\s+de\s+vigilar|"
                     r"deten\s+la\s+vigilancia|apaga\s+la\s+camara|apaga\s+la\s+vigilancia|"
                     r"quita\s+la\s+vigilancia", t):
            self._vigilando = False
            return "Vigilancia detenida, señor. La cámara queda apagada."
        if not re.search(r"vigila|vigilancia|vigilame|detecta\s+movimiento|movimiento\s+en\s+la\s+camara|"
                         r"cuida\s+la\s+casa|activa\s+la\s+camara", t):
            return None
        if self.safe:
            return "(modo seguro: no activaría la vigilancia)"
        if self._vigilando:
            return "La vigilancia ya está activa, señor."
        def _do():
            import cv2
            cap = None
            try:
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    self._avisar("Señor, no hay cámara disponible en este equipo.")
                    return
                self._vigilando = True
                base = os.path.join(self._caps_dir, "Vigilancia")
                os.makedirs(base, exist_ok=True)
                ref = None
                ultimo_aviso = 0
                while self._vigilando:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    gris = cv2.GaussianBlur(gris, (21, 21), 0)
                    if ref is None:
                        ref = gris
                        continue
                    dif = cv2.absdiff(ref, gris)
                    umbral = cv2.threshold(dif, 25, 255, cv2.THRESH_BINARY)[1]
                    area = cv2.countNonZero(umbral)
                    ref = gris
                    if area > 8000 and time.time() - ultimo_aviso > 20:
                        ultimo_aviso = time.time()
                        nombre_img = f"mov_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        cv2.imwrite(os.path.join(base, nombre_img), frame)
                        url_img = ""
                        try:
                            pub = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "web_interface", "capturas", nombre_img)
                            cv2.imwrite(pub, frame)
                            url_img = f"http://{self._ip_lan()}:{jarvis_config.PORT}/capturas/{nombre_img}"
                        except Exception:
                            pass
                        self._avisar("Movimiento detectado en la cámara, señor." +
                                     (f" Imagen: {url_img}" if url_img else " He guardado una imagen."))
                    time.sleep(0.25)
            except Exception as e:
                self.log(f"Vigilancia fallo: {e}")
                self._avisar("Señor, no pude activar la vigilancia.")
            finally:
                self._vigilando = False
                if cap:
                    cap.release()
        threading.Thread(target=_do, daemon=True).start()
        return "Vigilancia activada, señor. Le avisaré si detecto movimiento."

    # ── DOMÓTICA (MQTT: luces, enchufes) ─────────────────────────────────────
    def _domo_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Domotica")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "config.json")

    def _domo_leer(self) -> dict:
        try:
            return json.load(open(self._domo_path(), encoding="utf-8"))
        except Exception:
            return {}

    def _domo_guardar(self, cfg: dict):
        with open(self._domo_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    def _domotica(self, t: str):
        m = re.search(r"(?:configura|configurar)\s+(?:mi\s+|el\s+)?(?:broker|servidor)\s+(?:mqtt\s+)?"
                      r"(?:de\s+)?(?:domotica)?\s+(?:en\s+)?(?P<ip>[\d.]+)", t)
        if m:
            cfg = self._domo_leer()
            cfg["broker"] = m.group("ip")
            self._domo_guardar(cfg)
            return (f"Broker MQTT configurado en {cfg['broker']}, señor. "
                    f"Dígame «enciende las luces» para probar.")
        if not re.search(r"\bluz\b|luces|luzes|enchufe|enchufes|domotica|domótica", t):
            return None
        encender = bool(re.search(r"enciende|prende|activa", t))
        apagar = bool(re.search(r"apaga|apagar", t))
        if not encender and not apagar:
            return None
        cfg = self._domo_leer()
        if not cfg.get("broker"):
            return ("Señor, no tengo un broker MQTT configurado. Dígame, por ejemplo: "
                    "«configura mi broker de domotica en 192.168.1.50».")
        if self.safe:
            return "(modo seguro: no enviaría orden al broker)"
        def _do():
            try:
                from paho.mqtt import client as mqtt
                topic = cfg.get("topic") or "casa/luces"
                valor = (cfg.get("on") if encender else cfg.get("off")) or ("ON" if encender else "OFF")
                cli = mqtt.Client(client_id="jarvis", protocol=mqtt.MQTTv311)
                cli.connect(cfg["broker"], int(cfg.get("port") or 1883), 6)
                cli.publish(topic, valor)
                cli.disconnect()
                self._avisar(f"Orden enviada: {topic} -> {valor}, señor.")
            except Exception as e:
                self.log(f"Domotica fallo: {e}")
                self._avisar(f"Señor, no pude contactar el broker MQTT en {cfg.get('broker')}.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Enviando orden para {'encender' if encender else 'apagar'}, señor."

    # ── ESTADO DEL PC (móvil / voz) ──────────────────────────────────────────
    def _estado_pc(self, t: str):
        if not re.search(r"estado del pc|estado del equipo|como esta el pc|como esta el equipo|"
                         r"que tal esta el pc|estado del sistema|estado de mi pc", t):
            return None
        def _do():
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=0.6)
                ram = psutil.virtual_memory()
                disco = psutil.disk_usage("C:\\")
                up = int(time.time() - psutil.boot_time())
                h, m = up // 3600, (up % 3600) // 60
                partes = [f"CPU {cpu:.0f}%", f"RAM {ram.percent:.0f}%",
                          f"disco C {disco.percent:.0f}% ({disco.free / 1073741824:.0f} GB libres)",
                          f"encendido {h}h {m}m"]
                try:
                    bat = psutil.sensors_battery()
                    if bat:
                        partes.append(f"batería {bat.percent}%" + (" (cargando)" if bat.power_plugged else ""))
                except Exception:
                    pass
                self._avisar("Estado del PC, señor: " + ", ".join(partes) + ".")
            except Exception as e:
                self.log(f"Estado pc fallo: {e}")
                self._avisar("Señor, no pude leer el estado del equipo.")
        threading.Thread(target=_do, daemon=True).start()
        return "Leyendo el estado del equipo, señor. Un momento."

    # ── SUSPENDER / DESPERTAR PC ─────────────────────────────────────────────
    def _suspender(self, t: str):
        if re.search(r"suspende el pc|suspende el equipo|hiberna|hibernar|pon en suspension|"
                     r"pon a dormir el pc|duerme el pc", t):
            if self.safe:
                return "Suspendiendo el equipo, señor. (modo seguro: no ejecutado)"
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True,
                             creationflags=0x08000000)
            return "Suspendiendo el equipo, señor. Para reactivarlo, pulse una tecla o el botón de encendido."
        if re.search(r"despierta el pc|despierta el equipo|reactiva el pc", t):
            if self.safe:
                return "(modo seguro: no enviaría Wake-on-LAN)"
            d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
            cfg = {}
            try:
                cfg = json.load(open(os.path.join(d, "wol.json"), encoding="utf-8"))
            except Exception:
                pass
            mac = cfg.get("mac") or ""
            if not mac:
                return ("Señor, necesito la dirección MAC del equipo para Wake-on-LAN. "
                        "Dígame: «configura la mac de mi pc en AA:BB:CC:DD:EE:FF».")
            def _wol():
                import socket as _s
                try:
                    mac_bin = bytes.fromhex(mac.replace(":", "").replace("-", ""))
                    paquete = b"\xff" * 6 + mac_bin * 16
                    s = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
                    s.setsockopt(_s.SOL_SOCKET, _s.SO_BROADCAST, 1)
                    s.sendto(paquete, ("255.255.255.255", 9))
                    s.close()
                    self._avisar("Paquete Wake-on-LAN enviado, señor. El equipo debería despertar en unos segundos.")
                except Exception as e:
                    self.log(f"WOL fallo: {e}")
                    self._avisar("Señor, no pude enviar el paquete Wake-on-LAN.")
            threading.Thread(target=_wol, daemon=True).start()
            return "Enviando la señal de reactivación, señor."
        m = re.search(r"configura la mac de mi pc en ([0-9a-f:.-]{11,23})", t)
        if m:
            d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
            os.makedirs(d, exist_ok=True)
            json.dump({"mac": m.group(1).upper()}, open(os.path.join(d, "wol.json"), "w", encoding="utf-8"))
            return f"MAC {m.group(1).upper()} guardada, señor. Ya puedo despertar el equipo por red."
        return None

    # ── RESUMEN DEL DÍA ──────────────────────────────────────────────────────
    def _resumen_dia(self, t: str):
        if not re.search(r"resumen de mi dia|resumen del dia|como esta mi dia|como va mi dia|"
                         r"plan del dia|mis planes de hoy", t):
            return None
        def _do():
            try:
                partes = []
                hoy = datetime.now()
                agenda = self._agenda_leer()
                hoy_s = hoy.strftime("%Y-%m-%d")
                eventos = [e for e in agenda if e["cuando"].startswith(hoy_s)]
                if eventos:
                    lista = ", ".join(f"«{e['titulo']}» a las {e['cuando'][11:16]}" for e in sorted(eventos, key=lambda x: x["cuando"]))
                    partes.append(f"Agenda: {lista}")
                else:
                    partes.append("Agenda: sin eventos hoy")
                recs = self._recurrentes_leer()
                hoy_recs = [r for r in recs if r.get("texto")]
                if hoy_recs:
                    partes.append("Recordatorios activos: " + ", ".join(r["texto"] for r in hoy_recs))
                city = self._pref_leer().get("ciudad", "")
                try:
                    url = f"https://wttr.in/{urllib.parse.quote(city)}?format=%l:+%c+%t+(sensación+%f)+%h+humedad" if city \
                        else "https://wttr.in/?format=%c+%t+(sensación+%f)+%h+humedad"
                    with urllib.request.urlopen(url, timeout=10) as r:
                        clima = r.read().decode("utf-8", "ignore").strip()
                    partes.append("Clima: " + clima)
                except Exception:
                    pass
                self._avisar("Resumen de su día, señor. " + " | ".join(partes))
            except Exception as e:
                self.log(f"Resumen dia fallo: {e}")
                self._avisar("Señor, no pude componer el resumen del día.")
        threading.Thread(target=_do, daemon=True).start()
        return "Preparando el resumen de su día, señor. Un momento."

    # ── PREFERENCIAS PERSISTENTES ────────────────────────────────────────────
    def _pref_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "preferencias.json")

    def _pref_leer(self) -> dict:
        try:
            return json.load(open(self._pref_path(), encoding="utf-8"))
        except Exception:
            return {}

    def _pref_guardar(self, d: dict):
        with open(self._pref_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _preferencia(self, t: str):
        m = re.search(r"(?:recuerda|recuerdame|apunta|guarda|ten en cuenta)\s+que\s+"
                      r"(?:(?:mi|la|el|las|los|mis)\s+)?(?P<clave>[a-záéíóúñ ]{2,30})\s+es\s+(?P<val>.+?)\s*$", t)
        if m:
            clave = m.group("clave").strip().strip(":")
            val = m.group("val").strip().strip(".\"'")
            if not clave or not val or len(val) > 80:
                return None
            pref = self._pref_leer()
            pref[clave] = val
            self._pref_guardar(pref)
            return f"Anotado, señor: su {clave} es {val}. Lo recordaré siempre."
        if re.search(r"que sabes de mi|que recuerdas de mi|que sabes sobre mi|mis preferencias|preferencias", t):
            pref = self._pref_leer()
            if not pref:
                return "Señor, aún no tengo preferencias guardadas sobre usted. Dígame, por ejemplo: «recuerda que mi ciudad es Sevilla»."
            lista = ", ".join(f"{k}: {v}" for k, v in pref.items())
            return f"Señor, esto es lo que recuerdo de usted: {lista}."
        m = re.search(r"(?:olvida|borra|elimina)\s+(?:mi\s+|la\s+|el\s+)?(?P<clave>[a-záéíóúñ ]{2,30})\s*$", t)
        if m and re.search(r"olvida|borra|elimina", t):
            clave = m.group("clave").strip()
            pref = self._pref_leer()
            if clave in pref:
                del pref[clave]
                self._pref_guardar(pref)
                return f"Olvidado, señor: ya no recuerdo su {clave}."
            return f"Señor, no tenía guardado «{clave}»."
        return None

    # ── NOTA DE VOZ (dictado con SAPI de Windows) ────────────────────────────
    def _nota_voz(self, t: str):
        if not re.search(r"dictame una nota|dicta una nota|escuchame una nota|toma una nota de voz|"
                         r"nota de voz|grabame una nota|dictado", t):
            return None
        if self.safe:
            return "(modo seguro: no activaría el dictado)"
        def _do():
            try:
                import tempfile as _tf
                script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine([System.Speech.Recognition.System.Globalization.SpeechRecognitionEngine]::new())
$rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$rec.SetInputToDefaultAudioDevice()
$texto = New-Object System.Text.StringBuilder
$ev = Register-ObjectEvent -InputObject $rec -EventName SpeechRecognized -Action {
    [void]$Event.Sender.Suspend()
    if ($EventArgs.Result.Text) { $global:dictado += $EventArgs.Result.Text + ' ' }
    [void]$Event.Sender.Resume()
}
$global:dictado = ''
$rec.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$rec.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
Start-Sleep -Seconds 12
$rec.RecognizeAsyncStop()
$rec.Dispose()
if ($global:dictado) { Write-Output $global:dictado.Trim() }
"""
                r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                   capture_output=True, text=True, timeout=30,
                                   creationflags=0x08000000)
                texto = (r.stdout or "").strip()
                if len(texto) < 5:
                    self._avisar("Señor, no capté nada. Pruebe con el micrófono más cerca y repita: «dictame una nota».")
                    return
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(self._notas_dir, f"nota_voz_{ts}.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"{datetime.now().strftime('%d/%m/%Y %H:%M')}\n{texto}")
                self._avisar(f"Nota de voz guardada, señor: {texto[:120]}")
            except Exception as e:
                self.log(f"Nota voz fallo: {e}")
                self._avisar("Señor, el dictado por voz no está disponible en este equipo (falta el paquete de idioma).")
        threading.Thread(target=_do, daemon=True).start()
        return "Escuchando, señor. Hable con claridad durante unos segundos..."

    # ── ALERTAS DE RECURSOS ──────────────────────────────────────────────────
    def _alertas(self, t: str):
        m = re.search(r"avisame si la (ram|cpu|memoria|disco|procesador) (?:pasa|sube|supera) del? (\d{1,3})%", t)
        if m:
            recurso = {"ram": "ram", "memoria": "ram", "cpu": "cpu", "procesador": "cpu", "disco": "disco"}[m.group(1)]
            umbral = min(int(m.group(2)), 99)
            self._alertas_cfg[recurso] = umbral
            self._alerta_arranque()
            return (f"Entendido, señor. Le avisaré si la {recurso} pasa del {umbral}%. "
                    f"Puede pedir más con: «avisame si la disco pasa del 90%».")
        if re.search(r"para las alertas|deja de monitorear|no me avises mas|para la monitorizacion|quita las alertas", t):
            self._alertas_cfg = {}
            self._alerta_activa = False
            return "Alertas de recursos desactivadas, señor."
        if re.search(r"que alertas tengo|alertas activas", t):
            if not self._alertas_cfg:
                return "No tiene alertas de recursos activas, señor."
            lista = ", ".join(f"{k} > {v}%" for k, v in self._alertas_cfg.items())
            return f"Alertas activas, señor: {lista}."
        return None

    def _alerta_arranque(self):
        if self._alerta_activa:
            return
        self._alerta_activa = True
        def _loop():
            ultimo = {}
            while self._alerta_activa:
                try:
                    import psutil
                    valores = {
                        "cpu": psutil.cpu_percent(interval=0.5),
                        "ram": psutil.virtual_memory().percent,
                        "disco": psutil.disk_usage("C:\\").percent,
                    }
                    for k, umbral in list(self._alertas_cfg.items()):
                        v = valores.get(k)
                        if v is not None and v > umbral and time.time() - ultimo.get(k, 0) > 300:
                            ultimo[k] = time.time()
                            self._avisar(f"Aviso, señor: la {k} está al {v:.0f}%, por encima del {umbral}%.")
                except Exception as e:
                    self.log(f"Alertas fallo: {e}")
                time.sleep(30)
        threading.Thread(target=_loop, daemon=True).start()

    # ── ESPACIO POR CARPETA ──────────────────────────────────────────────────
    def _espacio(self, t: str):
        if not re.search(r"que esta ocupando|que ocupa mas|espacio por carpeta|carpetas mas pesadas|"
                         r"que se come el disco|que llena el disco", t):
            return None
        m = re.search(r"(?:en|de)\s+(?:el\s+|la\s+)?([a-z]:[\\/]?)", t)
        ruta = (m.group(1) if m else "C:\\").upper()
        if len(ruta) == 2:
            ruta += "\\"
        def _do():
            try:
                script = (
                    "$ErrorActionPreference='SilentlyContinue';"
                    f"Get-ChildItem '{ruta}' -Directory | ForEach-Object {{"
                    "$s=(Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | "
                    "Measure-Object -Property Length -Sum).Sum;"
                    "[PSCustomObject]@{N=$_.Name;S=[math]::Round($s/1MB)}}} | "
                    "Sort-Object S -Descending | Select-Object -First 8 | "
                    "ForEach-Object { '{0}: {1} MB' -f $_.N, $_.S }"
                )
                r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                   capture_output=True, text=True, timeout=60,
                                   creationflags=0x08000000)
                lineas = [ln for ln in (r.stdout or "").splitlines() if ":" in ln][:8]
                if not lineas:
                    self._avisar("Señor, no pude medir las carpetas de esa unidad.")
                    return
                self._avisar(f"Las carpetas más pesadas de {ruta}: " + "; ".join(lineas) + ".")
            except Exception as e:
                self.log(f"Espacio fallo: {e}")
                self._avisar("Señor, no pude medir el espacio por carpeta.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Midando las carpetas de {ruta}, señor. Un momento."

    # ── TAREAS PROGRAMADAS (Task Scheduler de Windows) ───────────────────────
    def _tareas_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "tareas.json")

    def _tareas_leer(self) -> dict:
        try:
            return json.load(open(self._tareas_path(), encoding="utf-8"))
        except Exception:
            return {}

    def _tareas_guardar(self, d: dict):
        with open(self._tareas_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _tarea(self, t: str):
        m = re.search(r"(?P<accion>.+?)\s+(?:todos los dias|todos los días|todos los lunes|todas las mananas|todas las mañanas|"
                      r"los lunes|los martes|los miercoles|los jueves|los viernes|los sabados|los domingos|"
                      r"el lunes|el martes|el miercoles|el jueves|el viernes|el sabado|el domingo|"
                      r"cada hora|cada dia|cada día)"
                      r"(?:\s+(?:a las|a la)\s+(\d{1,2})(?:[:.](\d{2}))?)?\s*$", t)
        if not m:
            return None
        if self.safe:
            return "(modo seguro: no crearía la tarea programada)"
        accion = m.group("accion").strip()
        hh = int(m.group(2)) if m.group(2) else None
        mm = int(m.group(3) or 0) if hh is not None else 0
        if hh is not None and (hh > 23 or mm > 59):
            return None
        cad = m.group(0)
        frec = "DAILY"
        dia_sem = ""
        if re.search(r"todos los lunes|los lunes", cad):
            frec, dia_sem = "WEEKLY", "MON"
        elif re.search(r"los martes", cad):
            frec, dia_sem = "WEEKLY", "TUE"
        elif re.search(r"los miercoles", cad):
            frec, dia_sem = "WEEKLY", "WED"
        elif re.search(r"los jueves", cad):
            frec, dia_sem = "WEEKLY", "THU"
        elif re.search(r"los viernes", cad):
            frec, dia_sem = "WEEKLY", "FRI"
        elif re.search(r"los sabados", cad):
            frec, dia_sem = "WEEKLY", "SAT"
        elif re.search(r"los domingos", cad):
            frec, dia_sem = "WEEKLY", "SUN"
        elif re.search(r"cada hora", cad):
            frec = "HOURLY"
        # construir comando real de Windows
        if re.search(r"apaga (el pc|el equipo|el ordenador)", accion):
            comando = "shutdown /s /t 30"
        elif re.search(r"apaga la musica|para la musica", accion):
            comando = "taskkill /IM ffplay.exe /F"
        elif re.search(r"abre|abrir|lanza", accion):
            m2 = re.search(r"(?:abre|abrir|lanza)\s+(?:el\s+|la\s+)?([a-záéíóúñ ]+)", accion)
            app = m2.group(1).strip() if m2 else ""
            cmd_app = APP_MAP.get(app) or ("start " + app if not app.endswith(".exe") else app)
            comando = cmd_app if cmd_app else None
            if not comando:
                return None
        elif re.search(r"ejecuta|ejecutar|lanza el script|corre", accion):
            m2 = re.search(r"(?:ejecuta|ejecutar|corre|lanza)\s+(?:el\s+|un\s+)?script\s+(?:de\s+)?(.+?)\s*$", accion)
            if m2 and os.path.exists(m2.group(1).strip()):
                comando = f'"{m2.group(1).strip()}"'
            else:
                comando = None
            if not comando:
                return None
        else:
            comando = None
        if not comando:
            return "Señor, esa tarea no sé ejecutarla. Pruebe con: «apaga el pc todos los días a las 23», «abre chrome los viernes a las 9» o «ejecuta el script C:\\ruta\\x.py cada hora»."
        import hashlib
        slug = "JARVIS_" + hashlib.md5(accion.encode()).hexdigest()[:6].upper()
        st = f" /ST {hh:02d}:{mm:02d}" if hh is not None else ""
        dia = f" /D {dia_sem}" if dia_sem else ""
        cmd = (f'schtasks /Create /F /TN "{slug}" /TR "{comando}" /SC {frec}{dia}{st}')
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, shell=True,
                               creationflags=0x08000000)
            tareas = self._tareas_leer()
            tareas[slug] = {"accion": accion, "frecuencia": frec, "hora": f"{hh:02d}:{mm:02d}" if hh is not None else "",
                            "comando": comando}
            self._tareas_guardar(tareas)
            desc = f"todos los días a las {hh:02d}:{mm:02d}" if (frec == "DAILY" and hh is not None) else \
                   f"los {dia_sem.lower()} a las {hh:02d}:{mm:02d}" if dia_sem else "cada hora"
            return f"Tarea programada, señor: «{accion}» {desc}. Sobrevivirá a los reinicios."
        except Exception as e:
            self.log(f"Tarea fallo: {e}")
            return f"Señor, no pude crear la tarea: {str(e)[:80]}"
        return None

    def _tareas_lista(self, t: str):
        if not re.search(r"que tareas (programadas|tengo)|lista mis tareas|mis tareas programadas|"
                         r"tareas programadas que tengo", t):
            return None
        try:
            r = subprocess.run('schtasks /Query /TN "JARVIS_*" /FO LIST',
                               capture_output=True, text=True, timeout=20, shell=True,
                               creationflags=0x08000000)
            nombres = re.findall(r"TaskName:\s+(JARVIS_\w+)", r.stdout or "")
            tareas = self._tareas_leer()
            if not nombres:
                return "No tiene tareas programadas de JARVIS, señor."
            partes = []
            for n in nombres:
                info = tareas.get(n, {})
                partes.append(f"{info.get('accion', n)} ({info.get('frecuencia', '?')}"
                              + (f" {info.get('hora')}" if info.get("hora") else "") + ")")
            return "Tareas programadas, señor: " + "; ".join(partes) + "."
        except Exception:
            return None

    def _tareas_borra(self, t: str):
        m = re.search(r"(?:borra|elimina|quita|para|deten)\s+(?:la\s+)?tarea\s+(?:de\s+)?(.+?)\s*$", t)
        if not m:
            return None
        if self.safe:
            return "(modo seguro: no borraría la tarea)"
        nombre = m.group(1).strip().strip(".")
        tareas = self._tareas_leer()
        slug = None
        for k, v in tareas.items():
            if self._norm(v.get("accion", "")) == self._norm(nombre) or self._norm(k) == self._norm(nombre):
                slug = k
                break
        if not slug:
            return f"Señor, no encontré la tarea «{nombre}»."
        subprocess.run(f'schtasks /Delete /F /TN "{slug}"', shell=True, timeout=20,
                       capture_output=True, creationflags=0x08000000)
        del tareas[slug]
        self._tareas_guardar(tareas)
        return f"Tarea «{nombre}» eliminada, señor."

    # ── POMODORO ─────────────────────────────────────────────────────────────
    def _pomodoro(self, t: str):
        m = re.search(r"pomodoro(?: de (\d{1,3}) minutos?)?", t)
        if not m:
            return None
        if self._pomodoro_activo:
            return "Ya hay un pomodoro en curso, señor."
        if self.safe:
            return "(modo seguro: no activaría el pomodoro)"
        trabajo = min(int(m.group(1) or 25), 120)
        self._pomodoro_activo = True
        def _do():
            try:
                for ciclo in range(4):
                    if not self._pomodoro_activo:
                        return
                    self._avisar(f"Pomodoro {ciclo + 1} de 4: {trabajo} minutos de concentración, señor.")
                    time.sleep(trabajo * 60)
                    if not self._pomodoro_activo:
                        return
                    if ciclo == 3:
                        self._avisar("Pomodoro completado, señor. Tómese un descanso largo de 15 minutos.")
                        time.sleep(900)
                    else:
                        self._avisar(f"Descanso de 5 minutos, señor. Estírese y beba agua.")
                        time.sleep(300)
                    if not self._pomodoro_activo:
                        return
                self._avisar("Ciclo de pomodoros terminado, señor. Bien hecho.")
            finally:
                self._pomodoro_activo = False
        threading.Thread(target=_do, daemon=True).start()
        return f"Pomodoro de {trabajo} minutos activado, señor. Cuatro ciclos con descansos."

    # ── RECORDATORIOS RECURRENTES (persistentes) ─────────────────────────────
    def _recurrentes_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "recurrentes.json")

    def _recurrentes_leer(self) -> list:
        try:
            return json.load(open(self._recurrentes_path(), encoding="utf-8"))
        except Exception:
            return []

    def _recurrentes_guardar(self, items: list):
        with open(self._recurrentes_path(), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    def _recurrente_checker(self):
        if self._recurrente_hilo_vivo:
            return
        self._recurrente_hilo_vivo = True
        def _loop():
            while True:
                try:
                    ahora = datetime.now()
                    items = self._recurrentes_leer()
                    for it in items:
                        ultimo = it.get("ultimo") or 0
                        intervalo = it.get("intervalo", 3600)
                        if it.get("hora") and ahora.hour == it["hora"][0] and ahora.minute == it["hora"][1] \
                                and time.time() - ultimo > 600:
                            self._avisar(f"Recordatorio, señor: {it['texto']}.")
                            it["ultimo"] = time.time()
                            self._recurrentes_guardar(items)
                        elif not it.get("hora") and time.time() - ultimo >= intervalo:
                            self._avisar(f"Recordatorio, señor: {it['texto']}.")
                            it["ultimo"] = time.time()
                            self._recurrentes_guardar(items)
                except Exception as e:
                    self.log(f"Checker recurrentes fallo: {e}")
                time.sleep(45)
        threading.Thread(target=_loop, daemon=True).start()

    def _recurrente(self, t: str):
        m = re.search(r"(?:recuerdame|recuérdame|avisame|recordame)\s+(?:que\s+)?(?P<txt>.+?)\s+"
                      r"cada\s+(?:(?P<n>\d+)\s+)?(?P<un>(?:hora|horas|minuto|minutos|dia|días|dia|manana|mañana))\s*"
                      r"(?:\s+a\s+(?:las|la)\s+(?P<hh>\d{1,2})(?:[:.]?(?P<mm>\d{2}))?)?\s*$", t)
        if not m:
            return None
        texto = m.group("txt").strip()
        un = m.group("un")
        n = int(m.group("n") or 1)
        hora = None
        if m.group("hh") is not None:
            h = int(m.group("hh"))
            mi = int(m.group("mm") or 0)
            if h > 23 or mi > 59:
                return None
            hora = (h, mi)
        if un.startswith("hora"):
            intervalo = n * 3600
        elif un.startswith("minuto"):
            intervalo = n * 60
        else:
            intervalo = n * 86400
        if hora:
            intervalo = 86400
        items = self._recurrentes_leer()
        items.append({"texto": texto, "intervalo": intervalo, "hora": list(hora) if hora else None,
                      "ultimo": 0, "ts": datetime.now().isoformat()})
        self._recurrentes_guardar(items)
        self._recurrente_checker()
        desc = f"cada {n} {un}" + (f" a las {hora[0]:02d}:{hora[1]:02d}" if hora else "")
        return f"Anotado, señor: «{texto}» {desc}. Se repetirá automáticamente."
        return None

    def _recurrente_lista(self, t: str):
        if not re.search(r"que recordatorios (recurrentes|tengo)|recordatorios activos|mis recordatorios|"
                         r"que me tienes que recordar", t):
            return None
        items = self._recurrentes_leer()
        if not items:
            return "No tiene recordatorios recurrentes, señor."
        lista = ", ".join(f"«{i['texto']}» cada {i['intervalo'] // 3600 or i['intervalo'] // 60}h" for i in items)
        return f"Recordatorios recurrentes, señor: {lista}."

    def _recurrente_borra(self, t: str):
        m = re.search(r"(?:para|borra|elimina|quita)\s+(?:el\s+)?recordatorio\s+(?:de\s+)?(.+?)\s*$", t)
        if not m:
            return None
        nombre = m.group(1).strip().strip(".")
        items = self._recurrentes_leer()
        restantes = [i for i in items if self._norm(i["texto"]) != self._norm(nombre)]
        if len(restantes) == len(items):
            return f"Señor, no tengo el recordatorio «{nombre}»."
        self._recurrentes_guardar(restantes)
        return f"Recordatorio «{nombre}» eliminado, señor."

    # ── SEGUIMIENTO DE PAQUETES (17track) ────────────────────────────────────
    def _paquete(self, t: str):
        m = re.search(r"(?:donde esta|donde está|sigue|seguimiento de|rastrea|tracking de|mi envio|mi pedido)\s+"
                      r"(?:mi\s+|el\s+|la\s+)?(?:paquete|envio|pedido|compra)\s*[:#]?\s*([A-Z0-9]{6,30})", t)
        if not m:
            m = re.search(r"(?:paquete|envio|pedido)\s+([A-Z0-9]{6,30})", t)
        if not m:
            return None
        numero = m.group(1).upper()
        def _do():
            try:
                req = urllib.request.Request(
                    "https://www.17track.net/en/ajax/track",
                    data=urllib.parse.urlencode({"nums": numero, "g_u": "0"}).encode(),
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                             "X-Requested-With": "XMLHttpRequest",
                             "Content-Type": "application/x-www-form-urlencoded"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read().decode("utf-8", "ignore"))
                d = data.get("data", {}).get("dat", [])
                if not d:
                    self._avisar(f"Señor, no encuentro el paquete {numero}. Verifique el número de seguimiento.")
                    return
                info = d[0]
                estado = (info.get("trackInfo") or {}).get("status", "en tránsito")
                eventos = info.get("events") or []
                ultimo = eventos[0]["z"] if eventos else "sin eventos todavía"
                self._avisar(f"Su paquete {numero}: {estado}. Último movimiento: {ultimo[:120]}.")
            except Exception as e:
                self.log(f"Paquete fallo: {e}")
                self._avisar("Señor, no pude consultar el seguimiento. Pruebe más tarde.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Consultando el paquete {numero}, señor. Un momento."

    # ── RADIO ONLINE ─────────────────────────────────────────────────────────
    _RADIOS = {
        "los 40": "https://playerservices.streamtheworld.com/api/livestream-redirect/LOS40_SC?dist=jarvis",
        "los40": "https://playerservices.streamtheworld.com/api/livestream-redirect/LOS40_SC?dist=jarvis",
        "los 40 principales": "https://playerservices.streamtheworld.com/api/livestream-redirect/LOS40_SC?dist=jarvis",
        "cadena 100": "https://playerservices.streamtheworld.com/api/livestream-redirect/CADENA100_SC?dist=jarvis",
        "cadena100": "https://playerservices.streamtheworld.com/api/livestream-redirect/CADENA100_SC?dist=jarvis",
        "cadena ser": "https://playerservices.streamtheworld.com/api/livestream-redirect/CADENASER_SC?dist=jarvis",
        "rock fm": "https://playerservices.streamtheworld.com/api/livestream-redirect/ROCKFM_SC?dist=jarvis",
        "kiss fm": "https://playerservices.streamtheworld.com/api/livestream-redirect/KISSFM_SC?dist=jarvis",
        "maxima fm": "https://playerservices.streamtheworld.com/api/livestream-redirect/MAXIMAFM_SC?dist=jarvis",
        "radio luna": "https://playerservices.streamtheworld.com/api/livestream-redirect/LUNAFM_SC?dist=jarvis",
    }

    def _radio(self, t: str):
        if re.search(r"(apaga|para|deten)\s+(?:la\s+)?radio", t):
            self._matar_reproductor()
            return "Radio apagada, señor."
        m = re.search(r"(?:pon|ponme|sintoniza|sintonizar|reproduce|activa|suena)\s+(?:la\s+)?radio"
                      r"(?:\s+(?:de\s+|en\s+)?(.*?))?\s*$", t)
        if not m:
            return None
        nombre = (m.group(1) or "").strip().strip(".")
        if not nombre:
            nombre = "los 40"
        url = None
        for k, v in self._RADIOS.items():
            if k == nombre or k in nombre:
                url = v
                break
        if not url:
            return f"Señor, no tengo sintonizada esa emisora. Tengo: " + ", ".join(sorted(set(self._RADIOS))) + "."
        if self.safe:
            return f"(modo seguro: no sintonizaría {nombre})"
        def _do():
            try:
                import shutil
                ffdir = self._ffmpeg_location()
                ffplay = os.path.join(ffdir, "ffplay.exe") if ffdir else shutil.which("ffplay")
                if ffplay:
                    self._matar_reproductor()
                    self._player = subprocess.Popen(
                        [ffplay, "-nodisp", "-loglevel", "quiet", "-autoexit", url],
                        creationflags=0x08000000)
                    self._avisar(f"Sintonizando {nombre}, señor.")
                else:
                    subprocess.Popen(["start", "", url], shell=True)
                    self._avisar(f"Abro {nombre} en el navegador, señor.")
            except Exception as e:
                self.log(f"Radio fallo: {e}")
                self._avisar(f"Señor, no pude sintonizar {nombre}.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Sintonizando {nombre}, señor."

    # ── ALERTAS DE PRECIO (Amazon.es) ────────────────────────────────────────
    def _precios_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "precios.json")

    def _precios_leer(self) -> list:
        try:
            return json.load(open(self._precios_path(), encoding="utf-8"))
        except Exception:
            return []

    def _precios_guardar(self, items: list):
        with open(self._precios_path(), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    def _precio(self, t: str):
        m = re.search(r"(?:avisame|avísame|avisa|monitorea|vigila|controla)\s+"
                      r"(?:si\s+|cuando\s+)?(?P<prod>.+?)\s+(?:baja de|baje de|baja por debajo de)\s+"
                      r"(?P<pre>[\d.,]+)\s*euros?", t)
        if not m:
            m = re.search(r"(?:monitorea|vigila|controla)\s+el\s+precio\s+de\s+(?P<prod>.+?)\s*$", t)
            if m:
                m = None
        if not m:
            return None
        prod = m.group("prod").strip().strip(".")
        precio = float(m.group("pre").replace(",", "."))
        if not prod or len(prod) < 3 or precio <= 0:
            return None
        if self.safe:
            return f"(modo seguro: no monitorearía el precio de «{prod[:40]}»)"
        def _chequeo_loop(entrada):
            try:
                req = urllib.request.Request(
                    "https://www.amazon.es/s?k=" + urllib.parse.quote(entrada["prod"]),
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                             "Accept-Language": "es-ES,es;q=0.9"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    html = r.read().decode("utf-8", "ignore")
                precios = re.findall(r'class="a-price-whole">([\d.,]+)', html)
                if not precios:
                    self._avisar(f"Señor, no pude leer el precio de «{entrada['prod'][:40]}» en Amazon.")
                    return
                mejor = min(float(p.replace(".", "").replace(",", ".")) for p in precios)
                if mejor <= entrada["precio"]:
                    self._avisar(f"Aviso de precio, señor: «{entrada['prod'][:40]}» está a {mejor:.2f} €, "
                                 f"por debajo de su límite de {entrada['precio']:.2f} €.")
                else:
                    self._avisar(f"«{entrada['prod'][:40]}» sigue a {mejor:.2f} €, señor. "
                                 f"Sigo vigilando su límite de {entrada['precio']:.2f} €.")
            except Exception as e:
                self.log(f"Precio fallo: {e}")
        def _hilo(entrada):
            _chequeo_loop(entrada)
            time.sleep(3600)
        items = self._precios_leer()
        items.append({"prod": prod, "precio": precio, "ts": datetime.now().isoformat()})
        self._precios_guardar(items)
        for it in items:
            if self._norm(it["prod"]) == self._norm(prod):
                threading.Thread(target=_hilo, args=(dict(it),), daemon=True).start()
        return f"Entendido, señor: avisaré si «{prod}» baja de {precio:.2f} €. Reviso cada hora."

    def _precio_borra(self, t: str):
        m = re.search(r"(?:para|deja)\s+(?:de\s+)?(?:vigilar|monitorear|controlar)\s+(?:el\s+precio\s+de\s+|el\s+)?(.+?)\s*$", t)
        if not m:
            return None
        nombre = m.group(1).strip().strip(".")
        items = self._precios_leer()
        restantes = [i for i in items if self._norm(i["prod"]) != self._norm(nombre)]
        if len(restantes) == len(items):
            return f"Señor, no estaba vigilando el precio de «{nombre}»."
        self._precios_guardar(restantes)
        return f"Dejo de vigilar el precio de «{nombre}», señor."

    # ── ESCENAS DE AMBIENTE ──────────────────────────────────────────────────
    def _escena(self, t: str):
        if re.search(r"modo cine|escena cine|modo pelicula|modo película", t):
            if self.safe:
                return "(modo seguro: no activaría el modo cine)"
            def _do():
                try:
                    self._prender_apagar_habitacion(False)
                    self._brillo_ejecutar(25)
                    self._volumen_ejecutar(55)
                    self._avisar("Modo cine activado, señor. Luces bajas, volumen de sala. Disfrute.")
                except Exception as e:
                    self.log(f"Cine fallo: {e}")
            threading.Thread(target=_do, daemon=True).start()
            return "Activando el modo cine, señor. Un momento."
        if re.search(r"escena noche|modo noche|escena de noche", t):
            if self.safe:
                return "(modo seguro: no activaría la escena noche)"
            def _do():
                try:
                    self._prender_apagar_habitacion(False)
                    self._brillo_ejecutar(12)
                    self._avisar("Escena noche activada, señor. Todo listo para descansar.")
                except Exception as e:
                    self.log(f"Noche fallo: {e}")
            threading.Thread(target=_do, daemon=True).start()
            return "Escena noche activada, señor."
        if re.search(r"escena trabajo|modo trabajo|escena de trabajo", t):
            if self.safe:
                return "(modo seguro: no activaría la escena trabajo)"
            def _do():
                try:
                    self._prender_apagar_habitacion(True)
                    self._brillo_ejecutar(80)
                    self._volumen_ejecutar(30)
                    self._modo_silencio = False
                    self._avisar("Escena trabajo activada, señor. Ambiente de concentración.")
                except Exception as e:
                    self.log(f"Trabajo fallo: {e}")
            threading.Thread(target=_do, daemon=True).start()
            return "Escena trabajo activada, señor."
        if re.search(r"modo fiesta|escena fiesta|escena de fiesta", t):
            if self.safe:
                return "(modo seguro: no activaría el modo fiesta)"
            def _do():
                try:
                    self._prender_apagar_habitacion(True)
                    self._volumen_ejecutar(80)
                    self._musica("pon la radio de los 40")
                    self._avisar("¡Modo fiesta activado, señor! Luces y música.")
                except Exception as e:
                    self.log(f"Fiesta fallo: {e}")
            threading.Thread(target=_do, daemon=True).start()
            return "¡Modo fiesta activado, señor!"
        return None

    def _brillo_ejecutar(self, nivel: int):
        try:
            script = (f"$m = Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods; "
                      f"$m.WmiSetBrightness(1, {nivel})")
            subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, timeout=20, creationflags=0x08000000)
        except Exception:
            pass

    def _volumen_ejecutar(self, pct: int):
        try:
            self._volumen_a(f"volumen al {pct}%")
        except Exception:
            pass

    # ── DETECTOR DE SONRISA ────────────────────────────────────────────────
    def _sonrisa(self, t: str):
        if not re.search(r"como me veo|cómo me veo|me ves bien|estoy sonriendo|detecta si sonrio|"
                         r"detecta si sonrío|que cara tengo|qué cara tengo|estoy de buen humor", t):
            return None
        if self.safe:
            return "(modo seguro: no miraría la cámara)"
        def _do():
            try:
                import cv2
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    self._avisar("Señor, no tengo acceso a la cámara.")
                    return
                ok, frame = cap.read()
                cap.release()
                if not ok:
                    self._avisar("Señor, no pude capturar la imagen.")
                    return
                gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                cara = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                                          "haarcascade_frontalface_default.xml"))
                sonrisa = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                                             "haarcascade_smile.xml"))
                caras = cara.detectMultiScale(gris, 1.1, 5, minSize=(80, 80))
                if len(caras) == 0:
                    self._avisar("Señor, no le veo la cara. Acérquese a la cámara.")
                    return
                x, y, w, h = caras[0]
                region = gris[y:y + int(h * 0.6), x:x + w]
                sonrisas = sonrisa.detectMultiScale(region, 1.7, 22, minSize=(30, 30))
                if len(sonrisas) > 0:
                    self._avisar("Se le ve feliz, señor. Esa sonrisa lo dice todo.")
                else:
                    self._avisar("Le veo serio, señor. ¿Quiere que le cuente un chiste?")
            except Exception as e:
                self.log(f"Sonrisa fallo: {e}")
                self._avisar("Señor, no pude analizar la cámara.")
        threading.Thread(target=_do, daemon=True).start()
        return "Echando un vistazo a la cámara, señor. Un momento."

    # ── VOZ A TU GUSTO ─────────────────────────────────────────────────────
    def _voz_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "voz.json")

    def _voz_leer(self) -> dict:
        try:
            return json.load(open(self._voz_path(), encoding="utf-8"))
        except Exception:
            return {"rate": 0, "voz": ""}

    def _voz_guardar(self, d: dict):
        with open(self._voz_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _voz_config(self, t: str):
        if re.search(r"habla mas lento|habla más lento|mas despacio|más despacio|dilo mas lento", t):
            voz = self._voz_leer()
            voz["rate"] = max(int(voz.get("rate", 0)) - 1, -3)
            self._voz_guardar(voz)
            return f"Hablaré más lento, señor. Ritmo ajustado a {voz['rate']}."
        if re.search(r"habla mas rapido|habla más rápido|mas rapido|más rápido|dilo mas rapido", t):
            voz = self._voz_leer()
            voz["rate"] = min(int(voz.get("rate", 0)) + 1, 3)
            self._voz_guardar(voz)
            return f"Hablaré más rápido, señor. Ritmo ajustado a {voz['rate']}."
        m = re.search(r"(?:cambia tu voz a|cambia tu voz por|usar la voz|pon la voz)\s+(?P<v>[a-záéíóúñ ]+?)\s*$", t)
        if m:
            nombre = m.group("v").strip().strip("?.")
            # Voz neuronal Piper (offline): no es una voz SAPI, se gestiona aparte
            if self._norm(nombre) == "piper":
                voz = self._voz_leer()
                voz["voz"] = "piper"
                self._voz_guardar(voz)
                return ("Cambiado a Piper, señor: mi voz neuronal gratuita y sin internet. "
                        "Se aplicará a mis respuestas habladas (no a audios ni lecturas).")
            def _do():
                try:
                    script = (r"""
Add-Type -AssemblyName System.Speech
$voces = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voces.GetInstalledVoices() | ForEach-Object { Write-Output $_.VoiceInfo.Name }
""")
                    r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                       capture_output=True, text=True, timeout=20,
                                       creationflags=0x08000000)
                    voces = [v.strip() for v in (r.stdout or "").splitlines() if v.strip()]
                    candidata = next((v for v in voces if self._norm(nombre) in self._norm(v)), None)
                    if not candidata:
                        self._avisar(f"Señor, no encontré la voz «{nombre}». Tengo: {', '.join(voces[:5])}.")
                        return
                    voz = self._voz_leer()
                    voz["voz"] = candidata
                    self._voz_guardar(voz)
                    self._avisar(f"Voz cambiada a {candidata}, señor. Se aplicará en audios y lecturas.")
                except Exception as e:
                    self.log(f"Voz config fallo: {e}")
                    self._avisar("Señor, no pude cambiar la voz.")
            threading.Thread(target=_do, daemon=True).start()
            return f"Buscando la voz «{nombre}», señor. Un momento."
        return None

    # ── RACHA DE DÍAS JUNTOS ────────────────────────────────────────────────
    def _racha_juntos(self, t: str):
        if not re.search(r"cuantos dias llevamos|cuántos días llevamos|dias juntos|días juntos|"
                         r"cuantos dias llevo contigo|cuántos días llevo contigo|"
                         r"cuantos dias seguidos|cuántos días seguidos|racha de conversacion|"
                         r"racha de conversación|cuantos dias llevamos hablando", t):
            return None
        def _do():
            try:
                import sqlite3
                for base in (jarvis_config.JARVIS_DB,
                             os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "jarvis_memory.db")):
                    if not os.path.exists(base):
                        continue
                    conn = sqlite3.connect(base, timeout=5)
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT substr(timestamp,1,10) FROM interactions ORDER BY 1")
                    dias = [r[0] for r in cur.fetchall()]
                    conn.close()
                    if not dias:
                        self._avisar("Aún no llevamos suficiente historia, señor. Empecemos hoy.")
                        return
                    hoy = datetime.now().strftime("%Y-%m-%d")
                    cursor = hoy if dias[-1] == hoy else (
                        (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d") if dias[-1] ==
                        (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d") else None)
                    if cursor is None:
                        self._avisar(f"Hemos conversado {len(dias)} días en total, señor. "
                                     f"Volvamos a encender la rutina diaria.")
                        return
                    racha = 0
                    c = datetime.strptime(cursor, "%Y-%m-%d")
                    while c.strftime("%Y-%m-%d") in dias:
                        racha += 1
                        c -= timedelta(days=1)
                    self._avisar(f"Llevamos {racha} día(s) seguidos conversando, señor, "
                                 f"y {len(dias)} días en total desde que empecé.")
                    return
                self._avisar("Señor, no tengo memoria de conversaciones todavía.")
            except Exception as e:
                self.log(f"Racha juntos fallo: {e}")
                self._avisar("Señor, no pude calcular nuestra racha.")
        threading.Thread(target=_do, daemon=True).start()
        return "Consultando nuestra historia, señor. Un momento."

    # ── MEMORIA DE AVISOS ───────────────────────────────────────────────────
    def _avisos_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "avisos.json")

    def _avisos_registrar(self, msg: str):
        try:
            avisos = json.load(open(self._avisos_path(), encoding="utf-8"))
        except Exception:
            avisos = []
        avisos.append({"ts": datetime.now().strftime("%Y-%m-%d %H:%M"), "texto": msg})
        avisos = avisos[-50:]
        with open(self._avisos_path(), "w", encoding="utf-8") as f:
            json.dump(avisos, f, ensure_ascii=False, indent=2)

    def _avisos_memoria(self, t: str):
        if not re.search(r"que ha pasado|qué ha pasado|que pasó|qué pasó|que paso|qué paso|"
                         r"mientras estaba fuera|ultimos avisos|últimos avisos|resumen de avisos|"
                         r"que me has avisado|qué me has avisado|que avisos hubo|qué avisos hubo", t):
            return None
        try:
            avisos = json.load(open(self._avisos_path(), encoding="utf-8"))
        except Exception:
            avisos = []
        if not avisos:
            return "No tengo avisos pendientes, señor. Todo en calma."
        ultimos = avisos[-8:]
        partes = []
        for a in ultimos:
            hora = a.get("ts", "")[11:16]
            dia = a.get("ts", "")[8:10]
            partes.append(f"{hora} ({dia}) {a.get('texto', '')[:90]}")
        return "Mientras no estaba, señor: " + " | ".join(partes)

    # ── SALUDO PERSONALIZADO ────────────────────────────────────────────────
    def _saludo_dia(self, t: str):
        franja = None
        if re.search(r"buenos dias|buenos días", t) and not re.search(r"resumen", t):
            franja = "Buenos días"
        elif re.search(r"buenas tardes", t):
            franja = "Buenas tardes"
        elif re.search(r"buenas noches", t):
            franja = "Buenas noches"
        if not franja:
            return None
        nombre = (self._pref_leer().get("nombre") or "").strip()
        trato = f"señor {nombre}" if nombre else "señor"
        extra = []
        try:
            ev = self._agenda_leer()
            ahora = datetime.now()
            hoy = ahora.strftime("%Y-%m-%d")
            proximo = next((e for e in sorted(ev, key=lambda x: x["cuando"])
                            if e["cuando"] >= ahora.strftime("%Y-%m-%d %H:%M")), None)
            if proximo and proximo["cuando"][:10] == hoy:
                extra.append(f"Su primer evento de hoy: «{proximo['titulo']}» a las {proximo['cuando'][11:16]}")
        except Exception:
            pass
        if extra:
            return f"{franja}, {trato}. {extra[0]}."
        return f"{franja}, {trato}. ¿En qué puedo ayudarle hoy?"

    # ── INFORME MATUTINO ─────────────────────────────────────────────────────
    def _hilo_informe(self):
        while True:
            try:
                ahora = datetime.now()
                if ahora.hour == 7 and ahora.minute < 5:
                    hoy = ahora.strftime("%Y-%m-%d")
                    if self._informe_hoy != hoy:
                        self._informe_hoy = hoy
                        self._avisar(self._componer_informe())
            except Exception:
                pass
            time.sleep(45)

    def _componer_informe(self) -> str:
        partes = ["Informe de la mañana, señor:"]
        try:
            city = self._pref_leer().get("ciudad", "")
            url = (f"https://wttr.in/{urllib.parse.quote(city)}?format=j1" if city
                   else "https://wttr.in/?format=j1")
            with urllib.request.urlopen(url, timeout=8) as r:
                d = json.loads(r.read().decode())
            c = d["current_condition"][0]
            desc = c["weatherDesc"][0]["value"].lower()
            partes.append(f"Clima: {desc}, {c['temp_C']}°C (sensación {c['FeelsLikeC']}°C).")
        except Exception:
            pass
        try:
            hoy = datetime.now().strftime("%Y-%m-%d")
            ev = sorted([e for e in self._agenda_leer() if e.get("cuando", "").startswith(hoy)],
                        key=lambda x: x["cuando"])
            if ev:
                partes.append("Agenda: " + "; ".join(
                    f"{e['cuando'][11:16]} {e['titulo']}" for e in ev[:4]) + ".")
            else:
                partes.append("Sin eventos en agenda para hoy.")
        except Exception:
            pass
        try:
            tareas = self._tareas_leer()
            lista = tareas.get("tareas") if isinstance(tareas, dict) else tareas
            if isinstance(lista, list):
                hoy = datetime.now().strftime("%Y-%m-%d")
                de_hoy = [x for x in lista if isinstance(x, dict) and
                          str(x.get("cuando") or x.get("fecha") or "").startswith(hoy)]
                if de_hoy:
                    partes.append("Tareas: " + "; ".join(
                        str(x.get("accion") or x.get("texto") or x.get("titulo") or "?")
                        for x in de_hoy[:4]) + ".")
        except Exception:
            pass
        try:
            import xml.etree.ElementTree as ET
            with urllib.request.urlopen(
                    "https://news.google.com/rss?hl=es-419&gl=MX&ceid=MX:es-419", timeout=8) as r:
                datos = r.read(150000).decode("utf-8", "ignore")
            items = []
            for it in ET.fromstring(datos).iter("item"):
                ttl = (it.findtext("title") or "").strip()
                if ":" in ttl:
                    ttl = ttl.split(":", 1)[0].strip()
                if ttl and ttl not in items:
                    items.append(ttl)
                if len(items) >= 3:
                    break
            if items:
                partes.append("Noticias: " + "; ".join(items) + ".")
        except Exception:
            pass
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory().percent
            disco = psutil.disk_usage("C:\\")
            partes.append(f"PC: CPU {cpu:.0f}%, RAM {ram:.0f}%, disco {disco.percent:.0f}%.")
        except Exception:
            pass
        return "\n".join(partes)

    def _informe_matutino(self, t: str):
        if not re.search(r"informe matutino|informe de la manana|informe de la mañana|"
                         r"resumen de la manana|resumen de la mañana|informe del dia|informe del día|"
                         r"dame el informe|informe completo", t):
            return None
        def _do():
            try:
                self._avisar(self._componer_informe())
            except Exception as e:
                self.log(f"Informe fallo: {e}")
                self._avisar("Señor, no pude preparar el informe.")
        threading.Thread(target=_do, daemon=True).start()
        return "Preparando su informe, señor. Un momento."

    # ── VIGILANTE DE RED CONTINUO ────────────────────────────────────────────
    def _hilo_vigilante_red(self):
        while True:
            time.sleep(180)
            if not self._vigilando_red:
                continue
            try:
                r = subprocess.run("arp -a", capture_output=True, text=True, timeout=20,
                                   shell=True, creationflags=0x08000000)
                patron = re.compile(
                    r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-"
                    r"[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2})")
                propia = self._ip_lan()
                d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
                ruta = os.path.join(d, "red_vigilancia.json")
                try:
                    conocidas = set(json.load(open(ruta, encoding="utf-8")))
                except Exception:
                    conocidas = set()
                nuevas = []
                for ip, mac in patron.findall(r.stdout or ""):
                    if ip == propia or ip.endswith(".255"):
                        continue
                    mac_u = mac.upper()
                    if mac_u not in conocidas:
                        conocidas.add(mac_u)
                        nombre = ""
                        try:
                            nombre = socket.gethostbyaddr(ip)[0].split(".")[0]
                        except Exception:
                            pass
                        nuevas.append(f"{nombre or ip} ({mac_u})")
                if nuevas:
                    json.dump(sorted(conocidas), open(ruta, "w", encoding="utf-8"))
                    self._avisar("🔔 Dispositivo desconocido en su red, señor: " +
                                 ", ".join(nuevas[:3]) + ".")
            except Exception as e:
                self.log(f"Vigilante red fallo: {e}")

    def _vigilar_red(self, t: str):
        if re.search(r"deja de vigilar la red|para el vigilante de red|desactiva el vigilante de red|"
                     r"apaga el vigilante de red|para de vigilar la red|quita el vigilante de red", t):
            self._vigilando_red = False
            return "Vigilante de red desactivado, señor."
        if not re.search(r"vigila (mi |la )?red|vigilante de red|vigilancia de red|"
                         r"avisame si entra un dispositivo|avísame si entra un dispositivo|"
                         r"alerta si entra un dispositivo", t):
            return None
        if self.safe:
            return "(modo seguro: no activaría el vigilante de red)"
        if self._vigilando_red:
            return "El vigilante de red ya está activo, señor."
        def _iniciar():
            try:
                r = subprocess.run("arp -a", capture_output=True, text=True, timeout=20,
                                   shell=True, creationflags=0x08000000)
                patron = re.compile(
                    r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-"
                    r"[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2})")
                propia = self._ip_lan()
                conocidas = set()
                for ip, mac in patron.findall(r.stdout or ""):
                    if ip != propia and not ip.endswith(".255"):
                        conocidas.add(mac.upper())
                d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
                os.makedirs(d, exist_ok=True)
                json.dump(sorted(conocidas), open(os.path.join(d, "red_vigilancia.json"), "w",
                                                  encoding="utf-8"))
                self._vigilando_red = True
                self._avisar("Vigilante de red activado, señor. Escanearé cada 3 minutos y le "
                             "avisaré si entra un dispositivo desconocido.")
            except Exception as e:
                self.log(f"Vigilante red iniciar fallo: {e}")
                self._avisar("Señor, no pude activar el vigilante de red.")
        threading.Thread(target=_iniciar, daemon=True).start()
        return "Activando el vigilante de red, señor. Un momento."

    # ── UBICAR EL TELÉFONO ───────────────────────────────────────────────────
    def _donde_movil(self, t: str):
        if not re.search(r"donde esta mi (telefono|movil|celular)|dónde está mi (teléfono|móvil|celular)|"
                         r"haz sonar mi (telefono|movil|celular)|hazme sonar (el |mi )?(telefono|movil|celular)|"
                         r"encuentra mi (telefono|movil|celular)", t):
            return None
        def _do():
            try:
                self._avisar("🔔 ¡Aquí estoy, señor! 🔔 Su teléfono está sonando y vibrando ahora mismo.")
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()
        return "Haciendo sonar su teléfono, señor. Debería oírlo en unos segundos."

    # ── QUÉ ESTÁ SONANDO (SPOTIFY / NAVEGADOR / VLC) ─────────────────────────
    def _spotify(self, t: str):
        if not re.search(r"que (esta|está) sonando|que cancion (esta sonando|suena|es)|qué canción (está sonando|suena|es)|"
                         r"que musica (esta sonando|suena)|qué música (está sonando|suena)|"
                         r"que tema (esta sonando|suena)|que (esta|está) reproduciendo|que (esta|está) de fondo", t):
            return None
        def _do():
            try:
                import ctypes
                import psutil
                user32 = ctypes.windll.user32
                titulos = []

                def _cb(hwnd, _):
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    largo = user32.GetWindowTextLengthW(hwnd)
                    if largo <= 0 or largo > 200:
                        return True
                    buf = ctypes.create_unicode_buffer(largo + 1)
                    user32.GetWindowTextW(hwnd, buf, largo + 1)
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    try:
                        nombre = psutil.Process(pid.value).name().lower()
                    except Exception:
                        nombre = ""
                    if nombre in ("spotify.exe", "msedge.exe", "chrome.exe", "firefox.exe",
                                  "vlc.exe", "wmplayer.exe", "youtube.exe", "opera.exe"):
                        titulos.append((nombre, buf.value))
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumWindows(WNDENUMPROC(_cb), 0)
                MALOS = ("spotify premium", "microsoft edge", "chrome", "firefox", "vlc",
                         "inicio", "new tab", "pestaña nueva", "google", "youtube music - búsqueda")
                for _n, titulo in titulos:
                    ti = titulo.strip()
                    bajo = ti.lower()
                    if not bajo or any(m in bajo for m in MALOS):
                        continue
                    ti = re.sub(r"\s*-\s*(youtube music|youtube|google chrome|microsoft edge|firefox|opera)$",
                                "", ti, flags=re.I)
                    ti = re.sub(r"\s*-\s*reproductor\s*$", "", ti, flags=re.I)
                    if ti:
                        self._avisar(f"Ahora suena, señor: {ti}.")
                        return
                self._avisar("Señor, no veo ninguna canción sonando ahora mismo.")
            except Exception as e:
                self.log(f"Spotify fallo: {e}")
                self._avisar("Señor, no pude ver qué está sonando.")
        threading.Thread(target=_do, daemon=True).start()
        return "Un momento, señor."

    # ── DESCARGADOR REMOTO ───────────────────────────────────────────────────
    def _descargar_url(self, t: str):
        if not re.search(r"descarga (esta url|este enlace|esta pagina|este archivo|este documento|esta direccion)|"
                         r"descarga https?://|baja (esta url|este enlace|esta pagina)", t):
            return None
        mo = re.search(r"https?://[^\s]+", self._orig)
        if not mo:
            return "Señor, no veo ninguna URL en su petición."
        url = mo.group(0).rstrip(".,;")
        if re.search(r"youtube\.com|youtu\.be", url):
            return None
        if self.safe:
            return "(modo seguro: no descargaría esa URL)"
        def _do():
            try:
                from urllib.parse import unquote
                nombre = unquote(os.path.basename(urllib.parse.urlparse(url).path)) or \
                    f"descarga_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                if not os.path.splitext(nombre)[1]:
                    nombre += ".bin"
                destino = os.path.join(os.path.expanduser("~"), "Downloads", nombre)
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                tam = 0
                with urllib.request.urlopen(req, timeout=120) as r:
                    with open(destino, "wb") as f:
                        while True:
                            trozo = r.read(65536)
                            if not trozo:
                                break
                            f.write(trozo)
                            tam += len(trozo)
                self._avisar(f"Descarga completada, señor: {nombre} ({tam / 1048576:.1f} MB) en Descargas.")
            except Exception as e:
                self.log(f"Descargar url fallo: {e}")
                self._avisar("Señor, no pude descargar esa URL.")
        threading.Thread(target=_do, daemon=True).start()
        return "Descargando, señor. Le aviso cuando termine."

    # ── RESUMIR PDF ──────────────────────────────────────────────────────────
    def _resumir_pdf(self, t: str):
        if not re.search(r"resume (este |el |mi |ese |la |esta |este archivo )?pdf|resumen de (este |el |mi )?pdf|"
                         r"que dice (este |el |mi )?pdf|resume el documento", t):
            return None
        m = re.search(r"(?:resume|resumir|resumen de|que dice)\s+(?:este\s+|el\s+|mi\s+|ese\s+|esta\s+|la\s+)?"
                      r"(?P<f>.+?)\s*$", t)
        nombre = m.group("f").strip().strip("?.") if m else ""
        if not nombre or ".pdf" not in nombre.lower():
            return "Señor, dígame el nombre del PDF: «resume el pdf de ...»."
        candidatos = [nombre,
                      os.path.join(os.path.expanduser("~"), "Downloads", nombre),
                      os.path.join(os.path.expanduser("~"), "Desktop", nombre),
                      os.path.join(os.path.expanduser("~"), "Documents", nombre),
                      os.path.join(os.path.expanduser("~"), "Descargas", nombre)]
        ruta = next((c for c in candidatos if os.path.isfile(c)), None)
        if not ruta:
            return f"Señor, no encontré el PDF «{nombre}»."
        if self.safe:
            return f"(modo seguro: no resumiría «{nombre}»)"
        def _do():
            try:
                import fitz
                doc = fitz.open(ruta)
                texto = ""
                for p in doc:
                    texto += p.get_text() + "\n"
                    if len(texto) > 20000:
                        break
                doc.close()
                if not texto.strip():
                    self._avisar("Señor, no pude extraer texto de ese PDF (puede ser escaneado).")
                    return
                parrafos = [re.sub(r"\s+", " ", p).strip()
                            for p in re.split(r"\n\s*\n", texto) if p.strip()]
                seleccion = [p for p in parrafos if len(p) > 40][:3]
                frases = re.split(r"(?<=[.;!?])", re.sub(r"\s+", " ", texto))
                claves = [f.strip() for f in frases
                          if re.search(r"\d|conclusion|resumen|importante|total|resultado", f, re.I)
                          and len(f.strip()) > 30][:3]
                resumen = " ".join(seleccion)
                if claves:
                    resumen += " — " + " ".join(claves)
                resumen = re.sub(r"\s+", " ", resumen).strip()
                self._avisar(f"Resumen de «{os.path.basename(ruta)}», señor: {resumen[:700]}")
            except Exception as e:
                self.log(f"Resumir pdf fallo: {e}")
                self._avisar("Señor, no pude resumir ese PDF.")
        threading.Thread(target=_do, daemon=True).start()
        return "Leyendo el PDF, señor. Un momento."

    # ── ESCANEAR DOCUMENTO (CÁMARA + OCR → PDF) ──────────────────────────────
    def _escanear_doc(self, t: str):
        if not re.search(r"escanea (un |este |el |mi |una |la )?documento|escanea (esto|esta pagina|esta hoja)|"
                         r"haz(me)? un escaneo|pasa (esto|este papel|esta hoja) a pdf|escaneame", t):
            return None
        if self.safe:
            return "(modo seguro: no escanearía un documento)"
        def _do():
            try:
                import cv2
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    self._avisar("Señor, no tengo acceso a la cámara para escanear.")
                    return
                ok, frame = cap.read()
                cap.release()
                if not ok:
                    self._avisar("Señor, no pude capturar la imagen.")
                    return
                d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Escaneos")
                os.makedirs(d, exist_ok=True)
                nombre = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                jpg = os.path.join(tempfile.gettempdir(), nombre + ".jpg")
                cv2.imwrite(jpg, frame)
                from PIL import Image
                img = Image.open(jpg)
                pdf = os.path.join(d, nombre + ".pdf")
                img.convert("RGB").save(pdf, "PDF", resolution=150)
                texto = ""
                try:
                    script = os.path.join(tempfile.gettempdir(), "jarvis_ocr.ps1")
                    with open(script, "w", encoding="utf-8") as f:
                        f.write(self._OCR_SCRIPT)
                    rr = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                         "-File", script, jpg],
                                        capture_output=True, text=True, timeout=60,
                                        creationflags=0x08000000)
                    texto = (rr.stdout or "").strip()
                except Exception:
                    texto = ""
                try:
                    os.remove(jpg)
                except Exception:
                    pass
                extra = f" Texto detectado: {texto[:150]}" if texto and not texto.startswith("OCR_") else ""
                self._avisar(f"Documento escaneado, señor: {pdf}.{extra}")
            except Exception as e:
                self.log(f"Escanear fallo: {e}")
                self._avisar("Señor, no pude escanear el documento.")
        threading.Thread(target=_do, daemon=True).start()
        return "Escaneando, señor. Ponga el documento frente a la cámara."

    # ── MODOS: INVITADO / GAMING / NOCHE ─────────────────────────────────────
    def _modo_invitado(self, t: str):
        if re.search(r"quita el modo invitado|se fueron (la visita|las visitas)|ya no hay (visita|visitas)|"
                     r"sal( del| de) modo invitado|termina el modo invitado", t):
            self._invitado = False
            return "Modo invitado desactivado, señor. Todo vuelve a la normalidad."
        if not re.search(r"modo invitado|tengo (visita|visitas|invitados|invitado)|hay (visita|visitas|invitados)", t):
            return None
        self._invitado = True
        return ("Modo invitado activado, señor. Callaré los avisos y protegeré sus datos "
                "mientras haya visitas. Dígame «quita el modo invitado» al despedirlas.")

    def _modo_gaming(self, t: str):
        if re.search(r"quita el modo gaming|quita el modo gamer|modo normal|sal del modo gaming|"
                     r"termina el modo gaming|apaga el modo gaming", t):
            self._gaming = False
            if not self.safe:
                threading.Thread(target=lambda: (self._brillo_ejecutar(80),
                                                 self._volumen_ejecutar(50)), daemon=True).start()
            return "Modo gaming desactivado, señor. Vuelvo a la normalidad."
        if not re.search(r"modo gaming|modo gamer|modo juego|voy a jugar|estoy jugando", t):
            return None
        self._gaming = True
        if not self.safe:
            threading.Thread(target=lambda: (self._brillo_ejecutar(35),
                                             self._volumen_ejecutar(85)), daemon=True).start()
        return ("Modo gaming activado, señor. Luces bajas, sonido alto y sin avisos. "
                "¡A ganar! Dígame «modo normal» para volver.")

    def _modo_noche(self, t: str):
        if not re.search(r"buenas noches|me voy a dormir|modo noche|voy a dormir", t):
            return None
        if self.safe:
            return "Buenas noches, señor. (modo seguro: no ajustaría luces ni sonido)"
        def _do():
            try:
                self._brillo_ejecutar(10)
                self._volumen_ejecutar(15)
                self._modo_silencio = True
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()
        return ("Buenas noches, señor. Bajo la luz y el sonido y activo el modo no molestar. "
                "Por la mañana dígame «desactiva modo silencio».")

    # ── MODO DICTADO (IS AIR dictation): LA VOZ SE ESCRIBE EN LA APP ACTIVA ──
    def _modo_dictado(self, t: str):
        if not re.search(r"modo dictado|dictado on|activa el dictado|empieza a dictar|empieza el dictado|quiero dictar", t):
            return None
        ruta = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "dictado.json")
        if re.search(r"desactiva el dictado|apaga el dictado|dictado off|modo dictado off", t):
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    json.dump({"activo": False}, f)
            except Exception:
                pass
            return "Modo dictado desactivado, señor. Vuelvo a responderle con normalidad."
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"activo": True}, f)
        except Exception:
            return "Señor, no pude activar el modo dictado."
        return ("Modo dictado activado, señor. Todo lo que diga se escribirá en la aplicación "
                "que tenga en foco. Dígame «desactiva el dictado» para volver a la normalidad.")

    # ── SALUD DEL PC (HISTORIAL + ALERTAS) ───────────────────────────────────
    def _muestrear_salud(self) -> dict:
        m = {"ts": datetime.now().isoformat(timespec="seconds"), "cpu": None, "ram": None,
             "disco": None, "cpu_temp": None, "gpu_temp": None}
        try:
            import psutil
            m["cpu"] = round(psutil.cpu_percent(interval=0.4), 0)
            m["ram"] = round(psutil.virtual_memory().percent, 0)
            m["disco"] = round(psutil.disk_usage("C:\\").percent, 0)
        except Exception:
            pass
        try:
            r = subprocess.run("wmic /namespace:\\\\root\\wmi PATH MSAcpi_ThermalZoneTemperature "
                               "get CurrentTemperature", capture_output=True, text=True, timeout=15,
                               shell=True, creationflags=0x08000000)
            vals = re.findall(r"\d{4,6}", r.stdout or "")
            if vals:
                m["cpu_temp"] = round(max(int(v) for v in vals) / 10.0 - 273.15, 1)
        except Exception:
            pass
        try:
            import shutil
            nv = shutil.which("nvidia-smi")
            if nv:
                rr = subprocess.run([nv, "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                                    capture_output=True, text=True, timeout=15,
                                    creationflags=0x08000000)
                v = (rr.stdout or "").strip()
                if v:
                    m["gpu_temp"] = round(float(v.split()[0]), 1)
        except Exception:
            pass
        return m

    def _hilo_salud(self):
        while True:
            try:
                if time.time() - self._salud_ultimo >= 3600:
                    self._salud_ultimo = time.time()
                    m = self._muestrear_salud()
                    d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
                    ruta = os.path.join(d, "salud.json")
                    try:
                        hist = json.load(open(ruta, encoding="utf-8"))
                    except Exception:
                        hist = []
                    hist.append(m)
                    json.dump(hist[-48:], open(ruta, "w", encoding="utf-8"), ensure_ascii=False)
                    if (m.get("cpu_temp") or 0) > 85:
                        self._avisar(f"🔔 El equipo se está calentando, señor: CPU {m['cpu_temp']}°C.")
                    if (m.get("gpu_temp") or 0) > 90:
                        self._avisar(f"🔔 La gráfica está muy caliente, señor: {m['gpu_temp']}°C.")
            except Exception as e:
                self.log(f"Salud fallo: {e}")
            time.sleep(300)

    def _salud_pc(self, t: str):
        if not re.search(r"salud del pc|salud del equipo|historial de (salud|temperatura)|"
                         r"monitorea la (temperatura|salud)|temperatura del pc|que tal va (el |mi )?pc|"
                         r"qué tal va (el |mi )?pc", t):
            return None
        if self.safe:
            return "(modo seguro: no leería la salud del PC)"
        def _do():
            try:
                m = self._muestrear_salud()
                d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
                try:
                    hist = json.load(open(os.path.join(d, "salud.json"), encoding="utf-8"))
                except Exception:
                    hist = []
                partes = [f"CPU {m['cpu']}%", f"RAM {m['ram']}%", f"disco {m['disco']}%"]
                if m.get("cpu_temp"):
                    partes.append(f"CPU {m['cpu_temp']}°C")
                if m.get("gpu_temp"):
                    partes.append(f"GPU {m['gpu_temp']}°C")
                if hist:
                    partes.append(f"({len(hist)} registros guardados)")
                self._avisar("Salud del PC, señor: " + ", ".join(partes) + ".")
            except Exception as e:
                self.log(f"Salud pc fallo: {e}")
                self._avisar("Señor, no pude leer la salud del equipo.")
        threading.Thread(target=_do, daemon=True).start()
        return "Midiendo la salud del equipo, señor. Un momento."

    # ── LISTA DE LA COMPRA ───────────────────────────────────────────────────
    def _compra_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "compra.json")

    def _compra_leer(self) -> list:
        try:
            return json.load(open(self._compra_path(), encoding="utf-8"))
        except Exception:
            return []

    def _compra_guardar(self, items: list):
        with open(self._compra_path(), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    def _compra(self, t: str):
        if "compra" not in t:
            return None
        m = re.search(r"(?:añade|anade|agrega|agregar|apunta|anota|mete|pon)\s+(?P<item>.+?)\s+"
                      r"(?:a\s+la\s+)?(?:lista\s+de\s+la\s+)?compra", t)
        if m:
            item = m.group("item").strip().strip(".")
            if not item or len(item) > 60:
                return None
            items = self._compra_leer()
            norm = self._norm(item)
            if any(self._norm(i) == norm for i in items):
                return f"«{item}» ya está en la lista de la compra, señor."
            items.append(item)
            self._compra_guardar(items)
            return f"Añadido «{item}» a la lista de la compra, señor. Lleva {len(items)} artículos."
        m = re.search(r"(?:quita|quitame|elimina|borra|saca|tacha)\s+(?P<item>.+?)\s+"
                      r"(?:de\s+la\s+)?(?:lista\s+de\s+la\s+)?compra", t)
        if m:
            item = m.group("item").strip().strip(".")
            items = self._compra_leer()
            norm = self._norm(item)
            restantes = [i for i in items if self._norm(i) != norm]
            if len(restantes) == len(items):
                return f"Señor, «{item}» no estaba en la lista de la compra."
            self._compra_guardar(restantes)
            return f"«{item}» quitado, señor. Quedan {len(restantes)} artículos."
        if re.search(r"(vacia|vaciar|borra|elimina)\s+(?:toda\s+la\s+|la\s+|mi\s+)?"
                     r"(?:lista\s+de\s+la\s+)?compra", t):
            self._compra_guardar([])
            return "Lista de la compra vaciada, señor."
        if re.search(r"(?:manda|envia|enviame|pasame)\s+(?:la\s+)?(?:lista\s+de\s+la\s+)?compra", t):
            items = self._compra_leer()
            if not items:
                return "La lista de la compra está vacía, señor."
            self._avisar("Lista de la compra, señor: " + ", ".join(items) + ".")
            return "Enviando la lista de la compra a su teléfono, señor."
        if re.search(r"(?:muestra|dime|ver|leeme|lee|que hay|que tengo|revisa|enseñame|ensename)\S*\s+.*compra|^compra\b", t):
            items = self._compra_leer()
            if not items:
                return "La lista de la compra está vacía, señor."
            return f"Lista de la compra, señor ({len(items)}): " + ", ".join(items) + "."
        return None

    # ── BÚSQUEDA POR CONTENIDO EN ARCHIVOS ───────────────────────────────────
    def _texto_archivo(self, ruta: str, limite: int = 300000) -> str:
        ext = os.path.splitext(ruta)[1].lower()
        try:
            if ext in (".txt", ".md", ".log", ".csv", ".json"):
                with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read(limite)
            if ext == ".pdf":
                import fitz
                doc = fitz.open(ruta)
                txt = ""
                for p in doc:
                    txt += p.get_text()
                    if len(txt) > limite:
                        break
                doc.close()
                return txt
            if ext == ".docx":
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(ruta) as z:
                    xml = z.read("word/document.xml").decode("utf-8", "ignore")
                return re.sub(r"<[^>]+>", " ", xml)
        except Exception:
            pass
        return ""

    def _buscar_contenido(self, t: str):
        if not re.search(r"busca en mis archivos|busca dentro de (mis |los )?(archivos|documentos|descargas)|"
                         r"busca en mis (documentos|descargas|pdfs)|busca que (habla|diga|mencione)|"
                         r"busca en mis archivos lo que (habla|diga)", t):
            return None
        m = re.search(r"(?:hable|habla|digan|diga|mencione|mencionen|contenga|contengan)\s+"
                      r"(?:de\s+|sobre\s+)?(?P<kw>.+?)\s*$", t)
        if not m:
            m = re.search(r"busca (?:en mis archivos|dentro de mis archivos)\s+(?:lo que\s+|que\s+)?"
                          r"(?:hable|diga|mencione)\s+(?:de\s+|sobre\s+)?(?P<kw>.+?)\s*$", t)
        if not m:
            return None
        kw = m.group("kw").strip().strip("?.")
        if not kw or len(kw) < 2:
            return None
        if self.safe:
            return "(modo seguro: no buscaría dentro de los archivos)"
        def _do():
            try:
                raices = [os.path.join(os.path.expanduser("~"), "Descargas"),
                          os.path.join(os.path.expanduser("~"), "Desktop"),
                          os.path.join(os.path.expanduser("~"), "Documents"),
                          os.path.join(os.path.expanduser("~"), "Documentos")]
                hallazgos = []
                visitados = 0
                kl = kw.lower()
                for raiz in raices:
                    if not os.path.isdir(raiz) or len(hallazgos) >= 3:
                        continue
                    for dirpath, dirs, files in os.walk(raiz):
                        dirs[:] = [d for d in dirs if d not in
                                   ("node_modules", ".git", "AppData", "$RECYCLE.BIN", "Backups")]
                        if visitados > 700 or len(hallazgos) >= 3:
                            break
                        for f in files:
                            visitados += 1
                            if visitados > 700 or len(hallazgos) >= 3:
                                break
                            if not f.lower().endswith((".txt", ".md", ".pdf", ".docx", ".log")):
                                continue
                            ruta = os.path.join(dirpath, f)
                            txt = self._texto_archivo(ruta)
                            if not txt:
                                continue
                            pos = txt.lower().find(kl)
                            if pos == -1:
                                continue
                            trozo = txt[max(0, pos - 80):pos + 120].replace("\n", " ")
                            trozo = re.sub(r"\s+", " ", trozo)
                            hallazgos.append(f"{f}: «...{trozo}...»")
                if not hallazgos:
                    self._avisar(f"Señor, no encontré nada sobre «{kw}» dentro de sus archivos.")
                    return
                self._avisar(f"Encontré «{kw}» en sus archivos, señor: " + " | ".join(hallazgos))
            except Exception as e:
                self.log(f"Buscar contenido fallo: {e}")
                self._avisar("Señor, no pude buscar dentro de sus archivos.")
        threading.Thread(target=_do, daemon=True).start()
        return "Buscando en sus archivos, señor. Un momento."

    # ── ENVIAR A LA TV (CHROMECAST) ──────────────────────────────────────────
    def _tv_buscar(self):
        try:
            import pychromecast
            casts = pychromecast.get_chromecasts(timeout=5)
            return casts[0] if casts else None
        except Exception:
            return None

    def _enviar_tv(self, t: str):
        if re.search(r"(para|pausa|deten|apaga)\s+(la\s+)?(tele|tv|television)\b", t):
            def _pausar():
                try:
                    cast = self._tv_buscar()
                    if not cast:
                        self._avisar("Señor, no encuentro la TV en la red.")
                        return
                    cast.media_controller.pause()
                    self._avisar("TV en pausa, señor.")
                except Exception as e:
                    self.log(f"TV pausa fallo: {e}")
            threading.Thread(target=_pausar, daemon=True).start()
            return "Enviando pausa a la TV, señor."
        if re.search(r"(sube|baja)\s+el\s+volumen\s+de\s+(la\s+)?(tele|tv|television)", t):
            sube = "sube" in t
            def _vol():
                try:
                    cast = self._tv_buscar()
                    if not cast:
                        self._avisar("Señor, no encuentro la TV en la red.")
                        return
                    if sube:
                        cast.volume_up()
                    else:
                        cast.volume_down()
                    self._avisar("Volumen de la TV ajustado, señor.")
                except Exception as e:
                    self.log(f"TV volumen fallo: {e}")
            threading.Thread(target=_vol, daemon=True).start()
            return "Ajustando el volumen de la TV, señor."
        if not re.search(r"pon .+ en (la )?(tele|tv|television)|envia .+ a (la )?(tele|tv|television)|"
                         r"reproduce .+ en (la )?(tele|tv|television)|echa .+ a (la )?(tele|tv|television)", t):
            return None
        nombre = re.sub(r"^(?:pon|envia|reproduce|echa)\s+", "", t)
        nombre = re.sub(r"\s+(?:en|a)\s+(?:la\s+)?(?:tele|tv|television)\s*$", "", nombre).strip().strip(".")
        if not nombre or len(nombre) < 2:
            return None
        if self.safe:
            return f"(modo seguro: no enviaría «{nombre}» a la TV)"
        def _do():
            try:
                candidatos = [nombre,
                              os.path.join(os.path.expanduser("~"), "Downloads", nombre),
                              os.path.join(os.path.expanduser("~"), "Desktop", nombre),
                              os.path.join(os.path.expanduser("~"), "Documents", nombre),
                              os.path.join(os.path.expanduser("~"), "Descargas", nombre)]
                ruta = next((c for c in candidatos if os.path.isfile(c)), None)
                if not ruta:
                    self._avisar(f"Señor, no encontré «{nombre}» para enviar a la TV.")
                    return
                ext = os.path.splitext(ruta)[1].lower()
                MIME = {".mp4": "video/mp4", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
                        ".mov": "video/quicktime", ".webm": "video/webm", ".mp3": "audio/mpeg",
                        ".wav": "audio/wav", ".flac": "audio/flac", ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg", ".png": "image/png"}
                mime = MIME.get(ext, "video/mp4")
                pub = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "envios")
                os.makedirs(pub, exist_ok=True)
                nombre_pub = f"tv_{datetime.now().strftime('%H%M%S')}{ext}"
                import shutil
                shutil.copy2(ruta, os.path.join(pub, nombre_pub))
                url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/envios/{nombre_pub}"
                cast = self._tv_buscar()
                if not cast:
                    self._avisar("Señor, no encuentro ninguna TV o Chromecast en la red.")
                    return
                cast.wait()
                cast.media_controller.play_media(url, mime)
                cast.media_controller.play()
                self._avisar(f"Enviando «{os.path.basename(ruta)}» a la TV, señor.")
            except Exception as e:
                self.log(f"TV fallo: {e}")
                self._avisar("Señor, no pude enviar el contenido a la TV.")
        threading.Thread(target=_do, daemon=True).start()
        return "Enviando a la TV, señor. Un momento."

    # ── DIAGNÓSTICO DEL PC ───────────────────────────────────────────────────
    def _diagnostico(self, t: str):
        if not re.search(r"diagnostica (el |mi )?(pc|equipo)|diagnostico (del pc|del equipo|completo)|"
                         r"chequea (el |mi )?pc|hazme un diagnostico|revisa (el |mi )?pc a fondo|"
                         r"revisa el equipo", t):
            return None
        if self.safe:
            return "(modo seguro: no haría el diagnóstico)"
        def _do():
            try:
                import psutil
                lineas = ["Diagnóstico del equipo, señor:"]
                cpu = psutil.cpu_percent(interval=0.6)
                ram = psutil.virtual_memory()
                disco = psutil.disk_usage("C:\\")
                up = int(time.time() - psutil.boot_time())
                lineas.append(f"CPU {cpu:.0f}% | RAM {ram.percent:.0f}% | disco {disco.percent:.0f}% "
                              f"({disco.free / 1073741824:.0f} GB libres) | encendido {up // 3600}h "
                              f"{(up % 3600) // 60}m")
                try:
                    bat = psutil.sensors_battery()
                    if bat:
                        lineas.append(f"Batería {bat.percent}%" +
                                      (" (cargando)" if bat.power_plugged else ""))
                except Exception:
                    pass
                try:
                    r = subprocess.run("ping -n 1 8.8.8.8", capture_output=True, text=True,
                                       timeout=15, shell=True, creationflags=0x08000000)
                    m = re.search(r"tiempo[=<]\s*([\d<]+)\s*ms", (r.stdout or "").lower())
                    lineas.append(f"Red: {m.group(1)} ms a Internet" if m
                                  else "Red: sin respuesta a Internet")
                except Exception:
                    pass
                try:
                    rr = subprocess.run("wmic diskdrive get status", capture_output=True, text=True,
                                        timeout=20, shell=True, creationflags=0x08000000)
                    ok = sum(1 for s in (rr.stdout or "").splitlines() if s.strip().upper() == "OK")
                    lineas.append(f"Discos: {ok} en buen estado")
                except Exception:
                    pass
                try:
                    proc = sorted(psutil.process_iter(["name", "cpu_percent"]),
                                  key=lambda p: p.info["cpu_percent"] or 0, reverse=True)[:3]
                    lineas.append("Consumo: " + ", ".join(
                        f"{p.info['name']} {p.info['cpu_percent']:.0f}%" for p in proc))
                except Exception:
                    pass
                self._avisar("\n".join(lineas))
            except Exception as e:
                self.log(f"Diagnostico fallo: {e}")
                self._avisar("Señor, no pude completar el diagnóstico.")
        threading.Thread(target=_do, daemon=True).start()
        return "Diagnosticando el equipo, señor. Un momento."

    # ── GASTOS ───────────────────────────────────────────────────────────────
    def _gasto_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "gastos.json")

    def _gasto_leer(self) -> list:
        try:
            return json.load(open(self._gasto_path(), encoding="utf-8"))
        except Exception:
            return []

    def _gasto_guardar(self, gastos: list):
        with open(self._gasto_path(), "w", encoding="utf-8") as f:
            json.dump(gastos, f, ensure_ascii=False, indent=2)

    def _gasto(self, t: str):
        m = re.search(r"apunta\s+(\d{1,7}[.,]?\d{0,2})\s*(?:euros?|€)?\s*(?:en|de|para|por)\s*(?P<cat>[a-záéíóúñ ]+?)\s*$", t)
        if not m:
            m = re.search(r"apunta\s+(\d{1,7}[.,]?\d{0,2})\s*(?:euros?|€)?\s*$", t)
        if m:
            importe = float(m.group(1).replace(",", "."))
            cat = m.group("cat").strip() if m.re.groups > 1 and m.groupdict().get("cat") else "general"
            if importe <= 0:
                return None
            gastos = self._gasto_leer()
            gastos.append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                           "importe": importe, "cat": cat})
            self._gasto_guardar(gastos)
            return f"Anotado, señor: {importe:.2f} € en {cat}."
        if re.search(r"cuanto gasté|cúanto gasté|cuanto gaste|cúanto gaste|cuanto he gastado|"
                     r"cuánto he gastado", t):
            gastos = self._gasto_leer()
            if not gastos:
                return "No tiene gastos registrados, señor."
            ahora = datetime.now()
            if re.search(r"esta semana|esta semana", t):
                inicio = ahora - timedelta(days=ahora.weekday())
                periodo = "esta semana"
            elif re.search(r"este mes|este mes", t):
                inicio = ahora.replace(day=1)
                periodo = "este mes"
            else:
                inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
                periodo = "hoy"
            total = sum(g["importe"] for g in gastos
                        if datetime.strptime(g["fecha"], "%Y-%m-%d %H:%M") >= inicio)
            return f"Ha gastado {total:.2f} € {periodo}, señor."
        if re.search(r"ultimos gastos|últimos gastos|mis gastos|lista de gastos", t):
            gastos = self._gasto_leer()[-5:]
            if not gastos:
                return "No tiene gastos registrados, señor."
            return ("Últimos gastos, señor: " + ", ".join(
                f"{g['importe']:.2f} € en {g['cat']} ({g['fecha'][8:10]}/{g['fecha'][5:7]})" for g in reversed(gastos)))
        return None

    # ── HÁBITOS CON RACHA ───────────────────────────────────────────────────
    def _habito_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "habitos.json")

    def _habito_leer(self) -> dict:
        try:
            return json.load(open(self._habito_path(), encoding="utf-8"))
        except Exception:
            return {}

    def _habito_guardar(self, d: dict):
        with open(self._habito_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _racha_dias(fechas: list) -> int:
        fechas = sorted(set(fechas))
        if not fechas:
            return 0
        hoy = datetime.now().date()
        if fechas[-1] == hoy:
            cursor = hoy
        elif fechas[-1] == hoy - timedelta(days=1):
            cursor = hoy - timedelta(days=1)
        else:
            return 0
        racha = 0
        for f in reversed(fechas):
            if f == cursor:
                racha += 1
                cursor -= timedelta(days=1)
            elif f < cursor:
                break
        return racha

    def _habito(self, t: str):
        m = re.search(r"(?:marca habito|marca hábito|he cumplido el habito|he cumplido el hábito|"
                      r"hoy hice el habito|hoy hice el hábito)\s+(?P<nom>[a-záéíóúñ ]+?)\s*$", t)
        if m:
            nombre = self._norm(m.group("nom").strip())
            if len(nombre) < 2:
                return None
            hoy = datetime.now().strftime("%Y-%m-%d")
            habs = self._habito_leer()
            marcas = habs.get(nombre, {}).get("marcas", [])
            if hoy in marcas:
                return f"El hábito «{nombre}» ya estaba marcado hoy, señor."
            marcas.append(hoy)
            habs[nombre] = {"marcas": marcas}
            self._habito_guardar(habs)
            racha = self._racha_dias([datetime.strptime(f, "%Y-%m-%d").date() for f in marcas])
            return f"Hábito «{nombre}» marcado, señor. Lleva una racha de {racha} día(s)."
        m = re.search(r"(?:racha de|racha del|que racha llevo de|qué racha llevo de|"
                      r"que racha tengo de|qué racha tengo de)\s+(?P<nom>[a-záéíóúñ ]+?)\s*$", t)
        if m:
            nombre = self._norm(m.group("nom").strip())
            habs = self._habito_leer()
            marcas = [datetime.strptime(f, "%Y-%m-%d").date() for f in habs.get(nombre, {}).get("marcas", [])]
            racha = self._racha_dias(marcas)
            if racha == 0 and not marcas:
                return f"Señor, no tiene el hábito «{nombre}»."
            return f"Racha de «{nombre}»: {racha} día(s) consecutivos, señor."
        if re.search(r"que habitos tengo|qué hábitos tengo|lista mis habitos|lista mis hábitos|"
                     r"mis habitos|mis hábitos|que racha llevo|qué racha llevo", t):
            habs = self._habito_leer()
            if not habs:
                return "No tiene hábitos registrados, señor. Dígame «marca hábito leer»."
            partes = []
            for nombre, datos in habs.items():
                marcas = [datetime.strptime(f, "%Y-%m-%d").date() for f in datos.get("marcas", [])]
                partes.append(f"«{nombre}» racha {self._racha_dias(marcas)}")
            return "Sus hábitos, señor: " + ", ".join(partes)
        return None

    # ── IMPRIMIR ────────────────────────────────────────────────────────────
    def _imprimir(self, t: str):
        m = re.search(r"imprime|imprimir\s+(?:el\s+|la\s+|este\s+|esta\s+)?(?P<f>.+?)\s*$", t)
        if not m:
            return None
        nombre = m.group("f").strip().strip("?.")
        candidatos = [nombre,
                      os.path.join(os.path.expanduser("~"), "Downloads", nombre),
                      os.path.join(os.path.expanduser("~"), "Desktop", nombre),
                      os.path.join(os.path.expanduser("~"), "Documents", nombre),
                      os.path.join(os.path.expanduser("~"), "Descargas", nombre)]
        ruta = next((c for c in candidatos if os.path.isfile(c)), None)
        if not ruta:
            return f"Señor, no encontré el archivo «{nombre}»."
        if self.safe:
            return "(modo seguro: no imprimiría el archivo)"
        def _do():
            try:
                os.startfile(ruta, "print")
                self._avisar(f"Enviando «{nombre}» a la impresora, señor.")
            except Exception as e:
                self.log(f"Imprimir fallo: {e}")
                self._avisar(f"Señor, no pude imprimir «{nombre}».")
        threading.Thread(target=_do, daemon=True).start()
        return f"Imprimiendo «{nombre}», señor."

    # ── FONDO DE PANTALLA ───────────────────────────────────────────────────
    def _fondo(self, t: str):
        if not re.search(r"pon esta foto de fondo|pon esta imagen de fondo|fondo de pantalla|"
                         r"pon de fondo|deja esta foto de fondo|de fondo de pantalla", t):
            return None
        nombre = None
        m = re.search(r"(?:pon|deja)\s+(?:esta foto|esta imagen|la foto|la imagen|esta)\s+de fondo", t)
        if m:
            d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Subidas")
            if os.path.isdir(d):
                fotos = [f for f in os.listdir(d) if f.lower().endswith((".jpg", ".jpeg", ".png"))
                         and os.path.isfile(os.path.join(d, f))]
                if fotos:
                    nombre = os.path.join(d, sorted(fotos)[-1])
        else:
            m = re.search(r"pon\s+de\s+fondo(?: de pantalla)?\s+(?:la\s+|el\s+|esta\s+|este\s+)?"
                          r"(?P<f>.+?)\s*$", t)
            if m:
                nombre = m.group("f").strip().strip("?.")
                candidatos = [nombre,
                              os.path.join(os.path.expanduser("~"), "Downloads", nombre),
                              os.path.join(os.path.expanduser("~"), "Desktop", nombre),
                              os.path.join(os.path.expanduser("~"), "Descargas", nombre),
                              os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Subidas", nombre)]
                nombre = next((c for c in candidatos if os.path.isfile(c)), None)
        if not nombre or not os.path.isfile(nombre):
            return "Señor, no encuentro la imagen. Súbala desde el móvil con el botón Subir y diga «pon esta foto de fondo»."
        if self.safe:
            return "(modo seguro: no cambiaría el fondo de pantalla)"
        try:
            import ctypes
            ctypes.windll.user32.SystemParametersInfoW(20, 0, os.path.abspath(nombre), 3)
            return "Fondo de pantalla cambiado, señor."
        except Exception:
            return "Señor, no pude cambiar el fondo de pantalla."

    # ── MONITOR DE WEBS ─────────────────────────────────────────────────────
    def _webs_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "webs.json")

    def _webs_leer(self) -> dict:
        try:
            return json.load(open(self._webs_path(), encoding="utf-8"))
        except Exception:
            return {}

    def _webs_guardar(self, d: dict):
        with open(self._webs_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _monitor_web(self, t: str):
        m = re.search(r"(?:avisame|avísame|avisa me|dime)\s+cuando cambie\s+(?:la\s+)?(?:web|web de|la pagina de|la página de)\s+"
                      r"(?P<url>https?://\S+?)\s*$", t)
        if not m:
            return None
        url = m.group("url").strip().strip(".")
        if self.safe:
            return "(modo seguro: no monitorizaría la web)"
        def _do():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                contenido = urllib.request.urlopen(req, timeout=15).read()
                import hashlib
                h = hashlib.md5(contenido).hexdigest()
                webs = self._webs_leer()
                webs[url] = {"hash": h, "desde": datetime.now().strftime("%Y-%m-%d %H:%M")}
                self._webs_guardar(webs)
                self._avisar(f"Monitor creado para {url}, señor. Le avisaré cuando cambie el contenido.")
            except Exception as e:
                self.log(f"Monitor web fallo: {e}")
                self._avisar(f"Señor, no pude acceder a {url}.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Creando el monitor de {url}, señor. Un momento."
        return None

    def _monitor_web_quitar(self, t: str):
        m = re.search(r"(?:quita|quitar|borra|elimina)\s+el\s+monitor\s+(?:de\s+)?(?P<url>https?://\S+?)\s*$", t)
        if not m:
            return None
        url = m.group("url").strip().strip(".")
        webs = self._webs_leer()
        if url not in webs:
            return f"Señor, no monitorizo {url}."
        del webs[url]
        self._webs_guardar(webs)
        return f"Monitor de {url} eliminado, señor."

    def _monitor_web_lista(self, t: str):
        if not re.search(r"que webs monitorizo|qué webs monitorizo|webs monitorizadas|"
                         r"monitores activos|que paginas vigilas|qué páginas vigilas", t):
            return None
        webs = self._webs_leer()
        if not webs:
            return "No monitorizo ninguna web, señor. Dígame «avísame cuando cambie la web de https://...»."
        return "Monitorizo: " + ", ".join(webs.keys())

    def _hilo_monitor_webs(self):
        """Comprueba cada 30 min los monitores de web configurados."""
        import hashlib
        while True:
            time.sleep(1800)
            try:
                for url, datos in self._webs_leer().items():
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                        contenido = urllib.request.urlopen(req, timeout=15).read()
                        h = hashlib.md5(contenido).hexdigest()
                        if h != datos.get("hash"):
                            webs = self._webs_leer()
                            webs[url]["hash"] = h
                            self._webs_guardar(webs)
                            self._avisar(f"La web {url} ha cambiado, señor.")
                    except Exception:
                        continue
            except Exception:
                pass

    # ── GENERADOR DE CONTRASEÑAS ────────────────────────────────────────────
    def _password(self, t: str):
        m = re.search(r"genera una contraseña(?: de| con)?\s*(\d{1,2})?", t)
        if not m:
            return None
        largo = min(int(m.group(1) or 16), 40)
        if self.safe:
            return "(modo seguro: no generaría contraseñas)"
        import secrets as _sec
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*_-+=?"
        pwd = "".join(_sec.choice(chars) for _ in range(largo))
        def _do():
            try:
                script = "Set-Clipboard -Value '" + pwd + "'"
                subprocess.run(["powershell", "-NoProfile", "-Command", script],
                               capture_output=True, timeout=15, creationflags=0x08000000)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()
        return f"Contraseña de {largo} caracteres, señor: {pwd}. Ya está en su portapapeles."

    # ── AUDIO AL MÓVIL ──────────────────────────────────────────────────────
    def _audio_movil(self, t: str):
        m = re.search(r"(?:mandame un audio|mándame un audio|envíame un audio|envia un audio|"
                      r"manda un audio|ponme un audio)\s+(?:diciendo|que diga|con|de)\s+(?P<t>.+?)\s*$", t)
        if not m:
            return None
        texto = m.group("t").strip().strip(".")
        if len(texto) < 2:
            return None
        if self.safe:
            return "(modo seguro: no generaría el audio)"
        def _do():
            try:
                wav = os.path.join(tempfile.gettempdir(), "jarvis_audio_movil.wav")
                _vz = self._voz_leer()
                _rate = max(-10, min(10, int(_vz.get("rate") or 0)))
                _vname = (_vz.get("voice") or "").strip()
                _sel = ("$s.SelectVoice('%s')" % _vname) if _vname else ""
                script = (r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = %d
%s
$s.SetOutputToWaveFile($args[0])
$s.Speak($args[1])
$s.Dispose()
""" % (_rate, _sel))
                ps = os.path.join(tempfile.gettempdir(), "jarvis_audio_movil.ps1")
                with open(ps, "w", encoding="utf-8") as f:
                    f.write(script)
                r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                    "-File", ps, wav, texto],
                                   capture_output=True, timeout=60, creationflags=0x08000000)
                if r.returncode != 0 or not os.path.exists(wav):
                    self._avisar("Señor, no pude generar el audio.")
                    return
                d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "envios")
                os.makedirs(d, exist_ok=True)
                nombre = f"audio_{datetime.now().strftime('%H%M%S')}.wav"
                import shutil
                shutil.copy2(wav, os.path.join(d, nombre))
                url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/envios/{nombre}"
                self._avisar(f"Su audio, señor: {url}")
            except Exception as e:
                self.log(f"Audio movil fallo: {e}")
                self._avisar("Señor, no pude generar el audio.")
        threading.Thread(target=_do, daemon=True).start()
        return "Generando su audio, señor. Un momento."

    # ── ARCHIVOS RECIENTES DE WINDOWS ───────────────────────────────────────
    def _recientes(self, t: str):
        if not re.search(r"recientes|ultimo documento|último documento|ultimo archivo|último archivo|"
                         r"archivos que abri|archivos que abrí|que abri hoy|qué abrí hoy", t):
            return None
        def _do():
            try:
                carpeta = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Recent")
                if not os.path.isdir(carpeta):
                    self._avisar("Señor, no tengo acceso a los archivos recientes.")
                    return
                lnks = [os.path.join(carpeta, f) for f in os.listdir(carpeta) if f.lower().endswith(".lnk")]
                hoy = datetime.now()
                if re.search(r"hoy", t):
                    limite = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
                    lnks = [l for l in lnks if datetime.fromtimestamp(os.path.getmtime(l)) >= limite]
                lnks.sort(key=os.path.getmtime, reverse=True)
                if re.search(r"abre|abreme|ábrame", t) or re.search(r"ultimo documento|último documento|"
                                                                    r"ultimo archivo|último archivo", t):
                    if not lnks:
                        self._avisar("Señor, no hay archivos recientes que abrir.")
                        return
                    os.startfile(lnks[0])
                    self._avisar(f"Abriendo «{os.path.splitext(os.path.basename(lnks[0]))[0]}», señor.")
                    return
                nombres = [os.path.splitext(os.path.basename(l))[0][:40] for l in lnks[:8]]
                if not nombres:
                    self._avisar("Señor, no hay archivos recientes.")
                    return
                self._avisar("Archivos recientes, señor: " + ", ".join(nombres))
            except Exception as e:
                self.log(f"Recientes fallo: {e}")
                self._avisar("Señor, no pude leer los archivos recientes.")
        threading.Thread(target=_do, daemon=True).start()
        return "Consultando archivos recientes, señor."

    # ── TEMPERATURA GPU ─────────────────────────────────────────────────────
    def _gpu(self, t: str):
        if not re.search(r"grafica|gráfica|gpu|tarjeta grafica|tarjeta gráfica|"
                         r"temperatura de la grafica|temperatura de la gráfica", t):
            return None
        def _do():
            try:
                r = subprocess.run(
                    "nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,name --format=csv,noheader",
                    capture_output=True, text=True, timeout=15, shell=True, creationflags=0x08000000)
                salida = (r.stdout or "").strip()
                if not salida:
                    self._avisar("Señor, no detecto una tarjeta NVIDIA en este equipo.")
                    return
                partes = [p.strip() for p in salida.split(",")]
                self._avisar(f"Su gráfica {partes[2]}: {partes[0]}°C, uso {partes[1]}, señor.")
            except Exception:
                self._avisar("Señor, no pude consultar la temperatura de la gráfica.")
        threading.Thread(target=_do, daemon=True).start()
        return "Consultando la gráfica, señor. Un momento."

    # ── PARAR TODO ──────────────────────────────────────────────────────────
    def _parar_todo(self, t: str):
        if not re.search(r"para todo|deten todo|detén todo|cancela todo|para todo lo que estés haciendo|"
                         r"para todo lo que estas haciendo|deten todo ya|detén todo ya", t):
            return None
        self._matar_reproductor()
        self._vigilando = False
        self._pomodoro_activo = False
        self._alerta_activa = False
        self._antirobo_activo = False
        self._simulando = False
        if self._lector and self._lector.poll() is None:
            try:
                self._lector.terminate()
            except Exception:
                pass
            self._lector = None
        for nombre, tmr in list(self._timers.items()):
            try:
                tmr.cancel()
            except Exception:
                pass
        self._timers = {}
        subprocess.Popen("shutdown /a", shell=True, creationflags=0x08000000)
        return "Todo detenido, señor: música, timers, vigilancia, alertas, lector, pomodoro y simulaciones."

    # ── HACER SONAR EL TELÉFONO ─────────────────────────────────────────────
    def _sonar_movil(self, t: str):
        if not re.search(r"haz sonar mi telefono|haz sonar mi teléfono|suena mi telefono|suena mi teléfono|"
                         r"haz sonar el telefono|haz sonar el teléfono|donde esta mi telefono|dónde está mi teléfono", t):
            return None
        if self.safe:
            return "(modo seguro: no haría sonar el teléfono)"
        self._avisar("🔔 Señor, su teléfono está sonando. ¡Aquí!")
        return "Haciendo sonar su teléfono, señor. Búsquelo."

    # ── ESTADÍSTICAS DE USO DE JARVIS ───────────────────────────────────────
    def _stats_jarvis(self, t: str):
        if not re.search(r"cuantas veces me has respondido|cuántas veces me has respondido|"
                         r"cuantas veces has hablado conmigo|cuántas veces has hablado conmigo|"
                         r"cuantas veces me has contestado|cuántas veces me has contestado|"
                         r"cuantas conversaciones|cuántas conversaciones", t):
            return None
        def _do():
            try:
                import sqlite3
                for base in (jarvis_config.JARVIS_DB,
                             os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "jarvis_memory.db")):
                    if not os.path.exists(base):
                        continue
                    conn = sqlite3.connect(base, timeout=5)
                    cur = conn.cursor()
                    hoy = datetime.now().strftime("%Y-%m-%d")
                    cur.execute("SELECT COUNT(*) FROM interactions WHERE role='assistant' AND timestamp LIKE ?",
                                (hoy + "%",))
                    hoy_n = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM interactions WHERE role='assistant'")
                    total = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(DISTINCT timestamp LIKE ?) FROM interactions", (hoy + "%",))
                    conn.close()
                    self._avisar(f"Hoy le he respondido {hoy_n} veces, señor. Y {total} en toda nuestra historia.")
                    return
                self._avisar("Señor, no tengo memoria de conversaciones todavía.")
            except Exception as e:
                self.log(f"Stats jarvis fallo: {e}")
                self._avisar("Señor, no pude contar mis respuestas.")
        threading.Thread(target=_do, daemon=True).start()
        return "Contando mis respuestas, señor. Un momento."

    # ── SIMULAR PRESENCIA ───────────────────────────────────────────────────
    def _simular_presencia(self, t: str):
        if re.search(r"simula presencia|simular presencia|simula que estoy|simula que estoy en casa|"
                     r"activa la simulacion de presencia|activa la simulación de presencia", t):
            if self.safe:
                return "(modo seguro: no simularía presencia)"
            if self._simulando:
                return "La simulación de presencia ya está activa, señor."
            self._simulando = True
            def _loop():
                import random as _r
                while self._simulando:
                    try:
                        self._prender_apagar_habitacion(True)
                        time.sleep(_r.randint(900, 2400))
                        self._prender_apagar_habitacion(False)
                        time.sleep(_r.randint(1800, 3600))
                    except Exception:
                        time.sleep(300)
            threading.Thread(target=_loop, daemon=True).start()
            return ("Simulación de presencia activada, señor. Encenderé y apagaré luces y pantalla "
                    "en horarios realistas mientras está fuera.")
        if re.search(r"para la simulacion|para la simulación|quita la simulacion|quita la simulación|"
                     r"deten la simulacion|detén la simulación|deja de simular", t):
            self._simulando = False
            return "Simulación de presencia detenida, señor."
        return None

    def _prender_apagar_habitacion(self, encender: bool):
        cfg = self._domo_leer()
        if cfg.get("broker"):
            try:
                from paho.mqtt import client as mqtt
                topic = cfg.get("topic") or "casa/luces"
                valor = (cfg.get("on") if encender else cfg.get("off")) or ("ON" if encender else "OFF")
                cli = mqtt.Client(client_id="jarvis", protocol=mqtt.MQTTv311)
                cli.connect(cfg["broker"], int(cfg.get("port") or 1883), 6)
                cli.publish(topic, valor, qos=0)
                cli.disconnect()
                return
            except Exception:
                pass
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 1 if encender else 2)
        except Exception:
            pass

    # ── VER PANTALLA EN EL MÓVIL ─────────────────────────────────────────────
    def _ver_pantalla(self, t: str):
        if not re.search(r"muestrame la pantalla|muéstrame la pantalla|ver la pantalla del pc|"
                         r"ver mi escritorio|espejo del pc|streaming de pantalla|"
                         r"muestra la pantalla en mi telefono|ver la pantalla", t):
            return None
        url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/screen"
        self._avisar(f"Escritorio en vivo, señor: {url}")
        return "Abriendo la vista de su escritorio, señor. Un momento."

    # ── TOUCHPAD EN EL MÓVIL ────────────────────────────────────────────────
    def _touchpad_skill(self, t: str):
        if not re.search(r"controla el raton|controla el ratón|abre el touchpad|raton tactil|ratón táctil|"
                         r"touchpad|control remoto del raton|control remoto del ratón", t):
            return None
        url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/touchpad"
        self._avisar(f"Touchpad listo, señor: {url}")
        return "Touchpad en su teléfono, señor. Úselo como un ratón táctil."

    # ── SINCRONIZAR CARPETA (móvil -> PC) ───────────────────────────────────
    def _sincronizar(self, t: str):
        if not re.search(r"sincroniza mi carpeta|sincroniza los archivos|sincroniza mis archivos|"
                         r"pasa los archivos del movil|pasa los archivos del móvil|"
                         r"sincroniza la carpeta del movil|mueve los archivos del movil", t):
            return None
        if self.safe:
            return "(modo seguro: no sincronizaría la carpeta)"
        def _do():
            try:
                origen = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Subidas")
                destino = os.path.join(os.path.expanduser("~"), "Descargas")
                if not os.path.isdir(destino):
                    destino = os.path.join(os.path.expanduser("~"), "Downloads")
                if not os.path.isdir(origen):
                    self._avisar("Señor, no hay archivos subidos desde el móvil todavía.")
                    return
                archivos = [f for f in os.listdir(origen) if os.path.isfile(os.path.join(origen, f))]
                if not archivos:
                    self._avisar("Señor, no hay archivos subidos desde el móvil todavía.")
                    return
                movidos = 0
                for f in archivos:
                    try:
                        os.rename(os.path.join(origen, f), os.path.join(destino, f))
                        movidos += 1
                    except Exception:
                        import shutil
                        try:
                            shutil.copy2(os.path.join(origen, f), os.path.join(destino, f))
                            os.remove(os.path.join(origen, f))
                            movidos += 1
                        except Exception:
                            pass
                self._avisar(f"Sincronizados {movidos} archivo(s) del móvil a {destino}, señor.")
            except Exception as e:
                self.log(f"Sincronizar fallo: {e}")
                self._avisar("Señor, no pude sincronizar la carpeta.")
        threading.Thread(target=_do, daemon=True).start()
        return "Sincronizando su carpeta, señor. Un momento."

    # ── DIARIO AUTOMÁTICO ───────────────────────────────────────────────────
    def _diario(self, t: str):
        if not re.search(r"guarda el diario de hoy|guarda el diario|diario de hoy|"
                         r"resumen del dia guardado|hazme el diario", t):
            return None
        def _do():
            self._diario_generar()
        threading.Thread(target=_do, daemon=True).start()
        return "Generando el diario de hoy, señor. Un momento."

    def _diario_generar(self):
        try:
            import sqlite3
            base = None
            for b in (jarvis_config.JARVIS_DB,
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "jarvis_memory.db")):
                if os.path.exists(b):
                    base = b
                    break
            if not base:
                return
            fecha = datetime.now().strftime("%Y-%m-%d")
            conn = sqlite3.connect(base, timeout=5)
            cur = conn.cursor()
            cur.execute("SELECT role, content FROM interactions WHERE timestamp LIKE ? ORDER BY id",
                        (fecha + "%",))
            filas = cur.fetchall()
            conn.close()
            d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Diarios")
            os.makedirs(d, exist_ok=True)
            ruta = os.path.join(d, f"{fecha}.md")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(f"# Diario {fecha}\n\n")
                if not filas:
                    f.write("Sin conversaciones registradas hoy.\n")
                else:
                    for role, content in filas:
                        quien = "Señor" if role == "user" else "JARVIS"
                        f.write(f"- **{quien}**: {content}\n")
            self._avisar(f"Diario de hoy guardado en {ruta}.")
        except Exception as e:
            self.log(f"Diario fallo: {e}")

    # ── RECONOCIMIENTO FACIAL (histogramas HSV) ─────────────────────────────
    def _rostro(self, t: str):
        if re.search(r"soy yo|guarda mi cara|guardame la cara|recuerda mi cara|recuérdame la cara|"
                     r"guardar mi cara", t):
            if self.safe:
                return "(modo seguro: no guardaría la cara)"
            def _do():
                try:
                    import cv2
                    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap = cv2.VideoCapture(0)
                    if not cap.isOpened():
                        self._avisar("Señor, no tengo acceso a la cámara.")
                        return
                    ok, frame = cap.read()
                    cap.release()
                    if not ok:
                        self._avisar("Señor, no pude capturar la imagen.")
                        return
                    d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Rostros", "Señor")
                    os.makedirs(d, exist_ok=True)
                    ruta = os.path.join(d, f"cara_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                    cv2.imwrite(ruta, frame)
                    self._avisar("Cara guardada como referencia, señor. Ya podré reconocerle.")
                except Exception as e:
                    self.log(f"Cara fallo: {e}")
                    self._avisar("Señor, no pude guardar la cara.")
            threading.Thread(target=_do, daemon=True).start()
            return "Guardando su cara como referencia, señor. Mire a la cámara."
        if re.search(r"quien esta delante|quién está delante|reconoce quien es|reconoce quién es|"
                     r"quien esta frente al pc|quién está frente al pc|a quien tengo delante|"
                     r"a quién tengo delante|quien esta en la camara|quién está en la cámara", t):
            if self.safe:
                return "(modo seguro: no reconocería caras)"
            def _do():
                try:
                    import cv2
                    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap = cv2.VideoCapture(0)
                    if not cap.isOpened():
                        self._avisar("Señor, no tengo acceso a la cámara.")
                        return
                    ok, frame = cap.read()
                    cap.release()
                    if not ok:
                        self._avisar("Señor, no pude capturar la imagen.")
                        return
                    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    cascade = cv2.CascadeClassifier(
                        os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
                    caras = cascade.detectMultiScale(gris, 1.1, 5, minSize=(80, 80))
                    if len(caras) == 0:
                        self._avisar("Señor, no veo ningún rostro delante de la cámara.")
                        return
                    x, y, w, h = caras[0]
                    cara = frame[y:y + h, x:x + w]
                    base = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Rostros")
                    mejores = []
                    if os.path.isdir(base):
                        for nombre in sorted(os.listdir(base)):
                            ddir = os.path.join(base, nombre)
                            if not os.path.isdir(ddir):
                                continue
                            for f in os.listdir(ddir):
                                try:
                                    ref = cv2.imread(os.path.join(ddir, f))
                                    if ref is None:
                                        continue
                                    rg = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
                                    rc = cascade.detectMultiScale(rg, 1.1, 5, minSize=(80, 80))
                                    if len(rc) == 0:
                                        continue
                                    rx, ry, rw, rh = rc[0]
                                    ref_cara = ref[ry:ry + rh, rx:rx + rw]
                                    def hist(img):
                                        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                                        return cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
                                    corr = cv2.compareHist(hist(cara), hist(ref_cara), cv2.HISTCMP_CORREL)
                                    mejores.append((corr, nombre))
                                except Exception:
                                    continue
                    mejores.sort(key=lambda m: -m[0])
                    if mejores and mejores[0][0] > 0.82:
                        self._avisar(f"Delante de la cámara está {mejores[0][1]}, señor.")
                    else:
                        self._avisar("Hay alguien delante de la cámara, pero no le reconozco, señor.")
                except Exception as e:
                    self.log(f"Reconocer fallo: {e}")
                    self._avisar("Señor, no pude analizar la cámara.")
            threading.Thread(target=_do, daemon=True).start()
            return "Analizando la cámara, señor. Un momento."
        return None

    # ── QUIÉN ESTÁ EN MI RED WIFI ───────────────────────────────────────────
    def _quien_red(self, t: str):
        if not re.search(r"quien esta conectado|quién está conectado|dispositivos en mi red|"
                         r"quien esta en mi wifi|quién está en mi wifi|quien esta en mi red|"
                         r"quién está en mi red|que dispositivos hay en mi red", t):
            return None
        if self.safe:
            return "(modo seguro: no escanearía la red)"
        def _do():
            try:
                r = subprocess.run("arp -a", capture_output=True, text=True, timeout=20,
                                   shell=True, creationflags=0x08000000)
                salida = r.stdout or ""
                patron = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2})")
                propia = self._ip_lan()
                lineas = []
                for ip, mac in patron.findall(salida):
                    if ip == propia or ip.endswith(".255"):
                        continue
                    nombre = ""
                    try:
                        nombre = socket.gethostbyaddr(ip)[0].split(".")[0]
                    except Exception:
                        pass
                    lineas.append(f"{nombre or ip} ({mac})")
                if not lineas:
                    self._avisar("No veo otros dispositivos en su red, señor.")
                    return
                self._avisar(f"Dispositivos en su red, señor: " + ", ".join(lineas[:8]))
            except Exception as e:
                self.log(f"Quien red fallo: {e}")
                self._avisar("Señor, no pude escanear la red.")
        threading.Thread(target=_do, daemon=True).start()
        return "Escaneando su red, señor. Un momento."

    # ── CHISTES, QUIZ Y CURIOSIDADES ────────────────────────────────────────
    _CHISTES = [
        "¿Qué le dice un jaguar a otro? Jaguar you.",
        "¿Cómo se despiden los químicos? Ácido un placer.",
        "¿Qué hace un pez en la NASA? Nada, nada.",
        "¿Cuál es el colmo de un electricista? Que su mujer le diga que hoy se pone las pilas.",
        "¿Qué le dijo un semáforo a otro? No me mires, me estoy cambiando.",
        "¿Por qué los pájaros no usan WhatsApp? Porque ya tienen Twitter.",
        "¿Cómo se llama el primo vegano de Bruce Lee? Broco Lee.",
        "¿Qué le dice una pared a otra? Nos vemos en la esquina.",
        "¿Cuál es el colmo de un calvo? Tener ideas descabelladas.",
        "¿Qué hace una abeja en el gimnasio? Zumba.",
        "¿Cómo se dice adiós en China? Chow, chao.",
        "¿Qué le dice un espagueti a otro? Gracias por tu apoyo.",
    ]

    _QUIZ = {
        "historia": [
            ("¿Quién pintó la Mona Lisa?", ["Miguel Ángel", "Leonardo da Vinci", "Rafael", "Caravaggio"], 1),
            ("¿En qué año cayó el Muro de Berlín?", ["1985", "1989", "1991", "1987"], 1),
            ("¿Quién fue el primer presidente de Estados Unidos?", ["Jefferson", "Adams", "Washington", "Lincoln"], 2),
        ],
        "ciencia": [
            ("¿Cuál es el planeta más grande del sistema solar?", ["Júpiter", "Saturno", "Neptuno", "Tierra"], 0),
            ("¿Qué gas respiramos principalmente?", ["Oxígeno", "Nitrógeno", "Hidrógeno", "CO2"], 1),
            ("¿Cuántos huesos tiene un adulto?", ["206", "300", "150", "250"], 0),
        ],
        "geografia": [
            ("¿Cuál es el río más largo del mundo?", ["Amazonas", "Nilo", "Yangtsé", "Misisipi"], 0),
            ("¿Qué país tiene forma de bota?", ["España", "Grecia", "Italia", "Portugal"], 2),
            ("¿Cuál es la capital de Australia?", ["Sídney", "Melbourne", "Canberra", "Perth"], 2),
        ],
        "deportes": [
            ("¿Cuántos jugadores tiene un equipo de fútbol?", ["10", "11", "12", "9"], 1),
            ("¿En qué deporte se usa un birdie?", ["Tenis", "Golf", "Cricket", "Bádminton"], 1),
            ("¿Cuántos anillos tiene el logo de los Juegos Olímpicos?", ["4", "6", "5", "7"], 2),
        ],
    }

    _CURIOSIDADES = [
        "La miel nunca caduca: los arqueólogos han encontrado miel comestible de hace 3000 años.",
        "Los pulpos tienen tres corazones y sangre azul.",
        "Un día en Venus dura más que un año en Venus.",
        "El corazón de una ballena azul pesa como un coche pequeño.",
        "Las avellanas se llaman así porque las recogían en el día de San Andrés.",
        "El bambú puede crecer casi un metro en un solo día.",
        "Los flamencos no nacen rosados: su color viene del alimento.",
        "El wifi y el Bluetooth comparten la misma banda de frecuencia.",
        "La Estatua de la Libertad fue un regalo de Francia en 1886.",
        "Los camellos pueden beber hasta 100 litros de agua de una vez.",
    ]

    def _chiste(self, t: str):
        if not re.search(r"cuentame un chiste|cuéntame un chiste|dime un chiste|otro chiste|"
                         r"un chiste por favor|hazme reir|hazme reír", t):
            return None
        import random as _r
        return _r.choice(self._CHISTES)

    def _quiz(self, t: str):
        m = re.search(r"(?:hazme un quiz de|hazme un test de|hazme una pregunta de|"
                      r"quiz de|trivia de|preguntame de)\s*(?P<cat>[a-záéíóúñ ]+?)\s*$", t)
        if not m:
            return None
        cat = self._norm(m.group("cat").strip())
        preguntas = self._QUIZ.get(cat)
        if not preguntas:
            return (f"Señor, mis categorías de quiz son: {', '.join(self._QUIZ)}. "
                    f"Por ejemplo: «hazme un quiz de historia».")
        import random as _r
        q, opciones, correcta = _r.choice(preguntas)
        letras = ["A", "B", "C", "D"]
        texto = (f"{q} " + " ".join(f"{letras[i]}) {opciones[i]}" for i in range(4))
                  + f" La respuesta correcta es {letras[correcta]}).")
        return f"Quiz, señor: {texto}"

    def _curiosidad(self, t: str):
        if not re.search(r"dime una curiosidad|dato curioso|algo interesante|"
                         r"cuentame algo interesante|una curiosidad", t):
            return None
        import random as _r
        return "Curiosidad, señor: " + _r.choice(self._CURIOSIDADES)

    # ── COMANDOS PERSONALIZADOS (macros) ────────────────────────────────────
    def _comandos_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "comandos.json")

    def _comandos_leer(self) -> dict:
        try:
            return json.load(open(self._comandos_path(), encoding="utf-8"))
        except Exception:
            return {}

    def _comandos_guardar(self, d: dict):
        with open(self._comandos_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _macro(self, t: str):
        m = re.search(r"crea el comando\s+(?P<nom>[a-zñ ]+?)\s+que haga\s+(?P<acc>.+?)\s*$", t)
        if m:
            nombre = self._norm(m.group("nom").strip())
            accion = m.group("acc").strip().strip(".")
            if len(nombre) < 3 or len(accion) < 3:
                return None
            cmds = self._comandos_leer()
            cmds[nombre] = accion
            self._comandos_guardar(cmds)
            return f"Comando «{nombre}» creado, señor. Dígalo en cualquier momento y ejecutaré «{accion}»."
        m = re.search(r"(?:borra|elimina|quita)\s+el\s+comando\s+(?P<nom>[a-zñ ]+?)\s*$", t)
        if m:
            nombre = self._norm(m.group("nom").strip())
            cmds = self._comandos_leer()
            if nombre not in cmds:
                return f"Señor, no tengo el comando «{nombre}»."
            del cmds[nombre]
            self._comandos_guardar(cmds)
            return f"Comando «{nombre}» eliminado, señor."
        if re.search(r"que comandos tengo|qué comandos tengo|lista mis comandos|"
                     r"lista de mis comandos|mis comandos personalizados", t):
            cmds = self._comandos_leer()
            if not cmds:
                return ("No tiene comandos personalizados, señor. Cree uno así: "
                        "«crea el comando ñapas que haga abre chrome y dime las noticias».")
            return "Sus comandos, señor: " + ", ".join(f"«{n}»" for n in cmds)
        return None

    # ── DISPARADORES («cuando diga X, haz Y») ───────────────────────────────
    def _triggers_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "triggers.json")

    def _triggers_leer(self) -> dict:
        try:
            return json.load(open(self._triggers_path(), encoding="utf-8"))
        except Exception:
            return {}

    def _triggers_guardar(self, d: dict):
        with open(self._triggers_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _trigger(self, t: str):
        m = re.search(r"cuando diga\s+(?P<trig>.+?)\s+haz\s+(?P<acc>.+?)\s*$", t)
        if m:
            trig = self._norm(m.group("trig").strip().strip(".,"))
            accion = m.group("acc").strip().strip(".")
            if len(trig) < 2 or len(accion) < 3:
                return None
            trigs = self._triggers_leer()
            trigs[trig] = accion
            self._triggers_guardar(trigs)
            return (f"Disparador creado, señor: cuando diga «{trig}», ejecutaré «{accion}».")
        m = re.search(r"(?:borra|elimina|quita)\s+el\s+trigger\s+(?P<trig>.+?)\s*$", t)
        if m:
            trig = self._norm(m.group("trig").strip().strip(".,"))
            trigs = self._triggers_leer()
            if trig not in trigs:
                return f"Señor, no tengo el disparador «{trig}»."
            del trigs[trig]
            self._triggers_guardar(trigs)
            return f"Disparador «{trig}» eliminado, señor."
        if re.search(r"que triggers tengo|qué triggers tengo|lista mis triggers|"
                     r"mis disparadores|que disparadores tengo", t):
            trigs = self._triggers_leer()
            if not trigs:
                return ("No tiene disparadores, señor. Cree uno así: "
                        "«cuando diga buenas noches, haz apaga la pantalla».")
            return "Sus disparadores, señor: " + ", ".join(f"«{k}» → {v}" for k, v in trigs.items())
        return None

    def _ejecutar_macro(self, t: str):
        """Comandos personalizados y disparadores. Guard de recursión."""
        if self._en_macro or self.safe:
            return None
        for nombre, accion in self._comandos_leer().items():
            if t == nombre or re.search(r"ejecuta mi comando " + re.escape(nombre) + r"$", t):
                return self._correr_macro(nombre, accion)
        for trig, accion in self._triggers_leer().items():
            if trig in t:
                return self._correr_macro(trig, accion)
        return None

    def _correr_macro(self, nombre: str, accion: str):
        self._en_macro = True
        try:
            inner = self.handle(accion)
        finally:
            self._en_macro = False
        return f"«{nombre}» ejecutado, señor." + (f" {inner}" if inner else "")

    # ── BÚSQUEDA EN LA MEMORIA ──────────────────────────────────────────────
    def _buscar_memoria(self, t: str):
        m = re.search(r"(?:cuando hablamos de|cuándo hablamos de|cuando me dijiste|cuándo me dijiste|"
                      r"busca en tu memoria|que te dije sobre|qué te dije sobre|"
                      r"que me dijiste de|qué me dijiste de|que hablamos sobre|qué hablamos sobre)\s+"
                      r"(?P<kw>.+?)\s*$", t)
        if not m:
            return None
        kw = m.group("kw").strip().strip("?.")
        if len(kw) < 3:
            return None
        def _do():
            try:
                import sqlite3
                for base in (jarvis_config.JARVIS_DB,
                             os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "jarvis_memory.db")):
                    if not os.path.exists(base):
                        continue
                    conn = sqlite3.connect(base, timeout=5)
                    cur = conn.cursor()
                    cur.execute("SELECT timestamp, role, content FROM interactions "
                                "WHERE content LIKE ? ORDER BY id DESC LIMIT 3", ("%" + kw + "%",))
                    filas = cur.fetchall()
                    conn.close()
                    if filas:
                        partes = []
                        for ts, role, content in filas:
                            quien = "usted" if role == "user" else "yo"
                            partes.append(f"el {ts[8:10]}/{ts[5:7]} a las {ts[11:16]} {quien} dijo: {content[:100]}")
                        self._avisar(f"En mi memoria sobre «{kw}», señor: " + " | ".join(partes))
                        return
                self._avisar(f"Señor, no recuerdo nada sobre «{kw}».")
            except Exception as e:
                self.log(f"Buscar memoria fallo: {e}")
                self._avisar("Señor, no pude consultar mi memoria.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Buscando en mi memoria «{kw}», señor. Un momento."

    # ── EXPORTAR / IMPORTAR AGENDA (ICS) ────────────────────────────────────
    def _agenda_ics(self, t: str):
        if re.search(r"exporta mi agenda|exporta mi calendario|exportar la agenda|"
                     r"exporta la agenda", t):
            if self.safe:
                return "(modo seguro: no exportaría la agenda)"
            eventos = self._agenda_leer()
            if not eventos:
                return "Su agenda está vacía, señor."
            lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JARVIS//ES"]
            for e in eventos:
                try:
                    dt = datetime.strptime(e["cuando"], "%Y-%m-%d %H:%M")
                except Exception:
                    continue
                inicio = dt.strftime("%Y%m%dT%H%M%S")
                lineas.append("BEGIN:VEVENT")
                lineas.append(f"DTSTART:{inicio}")
                lineas.append(f"SUMMARY:{e['titulo']}")
                lineas.append("END:VEVENT")
            lineas.append("END:VCALENDAR")
            d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Agenda")
            os.makedirs(d, exist_ok=True)
            ruta = os.path.join(d, "agenda.ics")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("\r\n".join(lineas))
            return (f"Agenda exportada, señor: {ruta}. Puede importarla en Google Calendar "
                    f"(Ajustes → Importar) o en su teléfono.")
        if re.search(r"importa mi agenda|importa mi calendario|importar la agenda", t):
            m = re.search(r"importa (?:mi agenda|mi calendario|la agenda)(?: de | desde )?(?P<f>\S+)?", t)
            ruta = m.group("f") if m and m.group("f") else os.path.join(
                os.path.expanduser("~"), "Descargas", "JARVIS", "Agenda", "agenda.ics")
            ruta = ruta.strip().strip(".")
            if not os.path.isfile(ruta):
                ruta2 = os.path.join(os.path.expanduser("~"), "Descargas", ruta)
                if os.path.isfile(ruta2):
                    ruta = ruta2
                else:
                    return f"Señor, no encuentro el archivo «{ruta}»."
            try:
                with open(ruta, encoding="utf-8") as f:
                    contenido = f.read()
                eventos = self._agenda_leer()
                for m2 in re.finditer(r"BEGIN:VEVENT(.*?)END:VEVENT", contenido, re.S):
                    bloque = m2.group(1)
                    dt = re.search(r"DTSTART(?:;.*?)?:(20\d{6}T\d{6})", bloque)
                    summ = re.search(r"SUMMARY:(.*)", bloque)
                    if not dt:
                        continue
                    fecha = f"{dt.group(1)[:4]}-{dt.group(1)[4:6]}-{dt.group(1)[6:8]} {dt.group(1)[9:11]}:{dt.group(1)[11:13]}"
                    titulo = (summ.group(1).strip() if summ else "Evento importado")
                    eventos.append({"cuando": fecha, "titulo": titulo})
                self._agenda_guardar(eventos)
                return f"Agenda importada, señor: {len(eventos)} eventos en total."
            except Exception as e:
                self.log(f"Importar agenda fallo: {e}")
                return "Señor, no pude importar el archivo de calendario."
        return None

    # ── SEGURIDAD WEB ───────────────────────────────────────────────────────
    def _seguridad(self, t: str):
        m = re.search(r"cambia mi pin a\s*(\d{4,8})|cambia el pin a\s*(\d{4,8})", t)
        if m:
            pin = m.group(1) or m.group(2)
            if not pin.isdigit() or len(pin) != 6:
                return "Señor, el PIN debe tener exactamente 6 dígitos."
            if self.safe:
                return "(modo seguro: no cambiaría el PIN)"
            ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", ".jarvis_auth")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(pin)
            return "PIN cambiado, señor. La próxima vez que abra la web móvil use el nuevo."
        if re.search(r"bloquea las demas ips|bloquea las demás ips|solo permitir mi ip|"
                     r"solo mi ip|permite solo mi ip|restringe el acceso", t):
            d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
            os.makedirs(d, exist_ok=True)
            json.dump([], open(os.path.join(d, "allowed_ips.json"), "w", encoding="utf-8"))
            return ("Modo de restricción activado, señor: ahora abra la web del móvil y pulse "
                    "«Permitir mi IP» para que solo su teléfono pueda entrar.")
        if re.search(r"desbloquea todas las ips|quita la restriccion|quita la restricción|"
                     r"permite cualquier ip|desactiva la restriccion de ips", t):
            try:
                os.remove(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                       "Prefs", "allowed_ips.json"))
            except Exception:
                pass
            return "Restricción de IPs eliminada, señor. Cualquiera en la red puede entrar."
        return None

    # ── DASHBOARD EN EL MÓVIL ───────────────────────────────────────────────
    def _dashboard(self, t: str):
        if not re.search(r"abre el dashboard|dame el dashboard|panel de estadisticas|"
                         r"panel de estadísticas|muestrame las graficas|muéstrame las gráficas|"
                         r"dashboard del pc|graficas del sistema", t):
            return None
        url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/dashboard"
        self._avisar(f"Dashboard listo, señor: {url}")
        return "Abriendo el dashboard del sistema, señor."

    # ── PORTAPAPELES COMPARTIDO ─────────────────────────────────────────────
    def _portapapeles(self, t: str):
        if not re.search(r"portapapeles|clipboard|copiame|copia el texto|copia esta|copia ese|copia esa|"
                         r"copia esto|copia eso|al portapapeles", t):
            return None
        if re.search(r"copia|portapapeles", t) and re.search(r"al movil|al telefono|al celular|al móvil|al teléfono", t):
            m = re.search(r"(?:copia|copiame)\s+(?:el\s+|la\s+|este\s+|esta\s+)?(?P<t>.+?)\s+"
                          r"(?:al|en el|para el)\s+(?:movil|teléfono|telefono|celular|móvil)\s*$", t)
            texto = (m.group("t") if m else "").strip().strip(".")
            if texto:
                self._avisar(f"Portapapeles del móvil: {texto}")
                return f"Copiado a su móvil, señor: «{texto[:80]}»"
            return None
        m = re.search(r"(?:copia|copiame|pon)\s+(?:en\s+el\s+|al\s+|en\s+)?portapapeles\s+(?:el\s+|la\s+|este\s+|esta\s+)?"
                      r"(?P<t>.+?)\s*$", t)
        texto = (m.group("t") if m else "").strip().strip(".")
        if not texto:
            return None
        def _do():
            try:
                script = f"Set-Clipboard -Value @'`n{texto}`n'@"
                subprocess.run(["powershell", "-NoProfile", "-Command", script],
                               capture_output=True, timeout=15, creationflags=0x08000000)
                self._avisar(f"Copiado al portapapeles del PC: {texto[:80]}")
            except Exception as e:
                self.log(f"Portapapeles fallo: {e}")
        threading.Thread(target=_do, daemon=True).start()
        return f"Copiando «{texto[:80]}» al portapapeles del PC, señor."

    # ── SELFIE BAJO DEMANDA ────────────────────────────────────────────────
    def _selfie(self, t: str):
        if not re.search(r"selfie|sacate una foto|sácate una foto|tomate una foto|tómate una foto|"
                         r"foto con la camara|foto de la webcam|foto con la webcam", t):
            return None
        if self.safe:
            return "(modo seguro: no me haría una foto)"
        def _do():
            try:
                import cv2
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    self._avisar("Señor, no tengo acceso a la cámara.")
                    return
                ok, frame = cap.read()
                cap.release()
                if not ok:
                    self._avisar("Señor, no pude capturar la imagen de la cámara.")
                    return
                nombre = f"selfie_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                pub = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "capturas", nombre)
                os.makedirs(os.path.dirname(pub), exist_ok=True)
                cv2.imwrite(pub, frame)
                url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/capturas/{nombre}"
                self._avisar(f"Aquí tiene mi selfie, señor: {url}")
            except Exception as e:
                self.log(f"Selfie fallo: {e}")
                self._avisar("Señor, no pude tomar la selfie.")
        threading.Thread(target=_do, daemon=True).start()
        return "Tomando la selfie, señor. Un momento."

    # ── APAGADO PROGRAMADO ─────────────────────────────────────────────────
    def _apagado_programado(self, t: str):
        if re.search(r"cancela el apagado|cancela el reinicio|no apagues el pc|no reinicies", t):
            subprocess.Popen("shutdown /a", shell=True, creationflags=0x08000000)
            return "Apagado cancelado, señor."
        m = re.search(r"(?:apagate|apágate|apaga el pc|apaga el equipo|hiberna|hibernate|hibernáte)"
                      r"\s+(?:en\s+)?(?P<n>\d+)\s+minutos?", t)
        if m:
            n = int(m.group("n"))
            if n < 1 or n > 1440:
                return None
            if self.safe:
                return f"(modo seguro: no programaría el apagado en {n} min)"
            subprocess.Popen(f"shutdown /s /t {n * 60} /c \"Jarvis apagará el equipo por orden del señor\"",
                             shell=True, creationflags=0x08000000)
            return f"Programado, señor: el equipo se apagará en {n} minutos."
        m = re.search(r"(?:apagate|apágate|apaga el pc|apaga el equipo|hiberna|hibernate|hibernate)"
                      r"\s+(?:a las|a la|para las)\s*(\d{1,2})[:.](\d{2})", t)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            if hh > 23 or mm > 59:
                return None
            now = datetime.now()
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            secs = int((target - now).total_seconds())
            if self.safe:
                return f"(modo seguro: no programaría el apagado a las {hh:02d}:{mm:02d})"
            subprocess.Popen(f"shutdown /s /t {secs} /c \"Jarvis apagará el equipo por orden del señor\"",
                             shell=True, creationflags=0x08000000)
            return f"Programado, señor: apagaré el equipo a las {hh:02d}:{mm:02d}."
        m = re.search(r"(?:hiberna|hibernate|hibernate)\s+(?:en\s+)?(?P<n>\d+)\s+minutos?", t)
        if m:
            n = int(m.group("n"))
            if n < 1 or n > 1440:
                return None
            if self.safe:
                return f"(modo seguro: no programaría la hibernación en {n} min)"
            threading.Timer(n * 60, lambda: subprocess.Popen(
                "shutdown /h", shell=True, creationflags=0x08000000)).start()
            return f"Programado, señor: el equipo hibernará en {n} minutos."
        return None

    # ── ACTUALIZAR PROGRAMAS / WINDOWS ─────────────────────────────────────
    def _actualizar(self, t: str):
        if re.search(r"actualiza mis programas|actualiza los programas|actualiza todo|"
                     r"actualiza las aplicaciones|actualiza tus programas", t):
            if self.safe:
                return "(modo seguro: no actualizaría los programas)"
            def _do():
                try:
                    r = subprocess.run(
                        "winget upgrade --all --silent --accept-source-agreements --disable-interactivity",
                        capture_output=True, text=True, timeout=1800, shell=True, creationflags=0x08000000)
                    ok = r.returncode == 0 or "ninguna actualizaci" in (r.stdout or "").lower()
                    self._avisar("Programas actualizados, señor." if ok else
                                 f"Señor, la actualización terminó con avisos: {(r.stderr or '')[:100]}")
                except Exception as e:
                    self.log(f"Actualizar fallo: {e}")
                    self._avisar("Señor, no pude actualizar los programas.")
            threading.Thread(target=_do, daemon=True).start()
            return "Actualizando sus programas, señor. Esto puede tardar varios minutos."
        if re.search(r"actualiza windows|actualizar windows|actualiza el sistema operativo|"
                     r"actualiza el sistema", t):
            if self.safe:
                return "(modo seguro: no lanzaría la actualización de Windows)"
            subprocess.Popen("UsoClient StartScan", shell=True, creationflags=0x08000000)
            threading.Timer(60.0, lambda: subprocess.Popen(
                "UsoClient StartInstall", shell=True, creationflags=0x08000000)).start()
            return ("Lanzando la búsqueda de actualizaciones de Windows, señor. "
                    "Si hay pendientes, se instalarán y quizá pida reiniciar.")
        return None

    # ── TEST DE VELOCIDAD ──────────────────────────────────────────────────
    def _velocidad(self, t: str):
        if not re.search(r"test de velocidad|velocidad de internet|velocidad de la red|"
                         r"prueba de velocidad|que tan rapida", t):
            return None
        if self.safe:
            return "(modo seguro: no haría el test de velocidad)"
        def _do():
            try:
                import time as _t
                t0 = _t.time()
                with urllib.request.urlopen("https://speed.cloudflare.com/__down?bytes=25000000", timeout=40) as r:
                    total = 0
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                seg = _t.time() - t0
                mbps = (total * 8) / seg / 1e6
                t0 = _t.time()
                cuerpo = b"x" * 1048576
                req = urllib.request.Request("https://speed.cloudflare.com/__up",
                                             data=cuerpo, method="POST")
                req.add_header("Content-Type", "application/octet-stream")
                with urllib.request.urlopen(req, timeout=40) as r:
                    r.read()
                subida = (1048576 * 8) / (_t.time() - t0) / 1e6
                self._avisar(f"Velocidad de su conexión, señor: descarga {mbps:.0f} Mbps, "
                             f"subida {subida:.1f} Mbps.")
            except Exception as e:
                self.log(f"Velocidad fallo: {e}")
                self._avisar("Señor, no pude medir la velocidad de la conexión.")
        threading.Thread(target=_do, daemon=True).start()
        return "Midiendo su velocidad de internet, señor. Unos segundos por favor."

    # ── NOTICIAS DEL DÍA (RSS) ─────────────────────────────────────────────
    _RSS_FUENTES = [
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
        ("El Mundo", "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml"),
        ("Marca", "https://e00-marca.uecdn.es/rss/portada.xml"),
        ("Xataka", "https://www.xataka.com/feed"),
    ]

    def _noticias(self, t: str):
        if not re.search(r"dame las noticias|noticias del dia|noticias de hoy|que noticias hay|"
                         r"resumen de noticias|cuales son las noticias", t):
            return None
        if self.safe:
            return "(modo seguro: no consultaría las noticias)"
        def _do():
            try:
                import xml.etree.ElementTree as ET
                lineas = []
                for fuente, url in self._RSS_FUENTES:
                    try:
                        with urllib.request.urlopen(url, timeout=12) as r:
                            xml = r.read().decode("utf-8", "ignore")
                        raiz = ET.fromstring(xml)
                        items = raiz.findall(".//item")[:3]
                        for it in items:
                            titulo = (it.findtext("title") or "").strip()
                            if titulo:
                                lineas.append(f"{titulo}")
                        if lineas:
                            break
                    except Exception:
                        continue
                if not lineas:
                    self._avisar("Señor, no pude obtener las noticias ahora mismo.")
                    return
                self._avisar("Noticias de hoy, señor: " + " | ".join(lineas[:6]))
            except Exception as e:
                self.log(f"Noticias fallo: {e}")
                self._avisar("Señor, no pude obtener las noticias.")
        threading.Thread(target=_do, daemon=True).start()
        return "Consultando las noticias del día, señor. Un momento."

    # ── PRONÓSTICO 5 DÍAS ──────────────────────────────────────────────────
    def _pronostico(self, t: str):
        m = re.search(r"(?:que tiempo hará|qué tiempo hará|que tiempo hara|como estara el tiempo|"
                      r"como estará el tiempo|pronostico|prediccion)\s*(?P<cuando>hoy|mañana|manana|"
                      r"pasado mañana|pasado manana|lunes|martes|miercoles|miércoles|jueves|viernes|"
                      r"sabado|sábado|domingo|el finde|el fin de semana)?", t)
        if not m:
            return None
        cuando = m.group("cuando") or "hoy"
        if self.safe:
            return "(modo seguro: no consultaría el pronóstico)"
        def _do():
            try:
                city = self._pref_leer().get("ciudad", "")
                url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1" if city else "https://wttr.in/?format=j1"
                with urllib.request.urlopen(url, timeout=12) as r:
                    d = json.loads(r.read().decode())
                hoy_dia = datetime.now().weekday()
                dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
                objetivo = {
                    "hoy": 0, "mañana": 1, "manana": 1, "pasado mañana": 2, "pasado manana": 2,
                    "el finde": (5 - hoy_dia) % 7, "el fin de semana": (5 - hoy_dia) % 7,
                }.get(cuando)
                if objetivo is None:
                    for i, dd in enumerate(dias):
                        if dd == cuando:
                            objetivo = (i - hoy_dia) % 7
                            break
                if objetivo is None:
                    objetivo = 0
                if objetivo > 4:
                    objetivo = 0
                dia = d["weather"][objetivo]
                fecha = (datetime.now() + timedelta(days=objetivo)).strftime("%d/%m")
                t_max = dia["maxtempC"]
                t_min = dia["mintempC"]
                desc = dia["hourly"][6]["weatherDesc"][0]["value"] if dia.get("hourly") else "variable"
                prob_lluvia = max(int(h.get("chanceofrain", 0)) for h in dia.get("hourly", []))
                self._avisar(f"Pronóstico para {cuando} ({fecha}): {desc.lower()}, "
                             f"máxima {t_max}°C, mínima {t_min}°C, probabilidad de lluvia {prob_lluvia}%.")
            except Exception as e:
                self.log(f"Pronóstico fallo: {e}")
                self._avisar("Señor, no pude consultar el pronóstico del tiempo.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Consultando el pronóstico para {cuando}, señor."

    # ── DEPORTES ───────────────────────────────────────────────────────────
    def _deportes(self, t: str):
        m = re.search(r"(?:como va|como va el|que tal va|resultado de|resultado del|marcador de|marcador del|"
                      r"próximo partido de|proximo partido de|cuando juega|a que hora juega|como quedó|como quedo)\s+"
                      r"(?P<eq>.+?)\s*$", t)
        if not m:
            if re.search(r"resultados de hoy|resultados del dia|resultados del día|que partidos hay hoy", t):
                m = None
                eq = None
                hoy = True
            else:
                return None
        else:
            eq = m.group("eq").strip().strip("?.")
            hoy = False
        if self.safe:
            return "(modo seguro: no consultaría los deportes)"
        def _do():
            try:
                import urllib.parse as _up
                if hoy:
                    fecha = datetime.now().strftime("%Y-%m-%d")
                    with urllib.request.urlopen(
                            f"https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={fecha}&l=Spanish_La_Liga",
                            timeout=15) as r:
                        d = json.loads(r.read().decode())
                    evs = d.get("events") or []
                    if not evs:
                        self._avisar("Señor, hoy no hay partidos de La Liga.")
                        return
                    partes = [f"{e.get('strHomeTeam')} {e.get('intHomeScore', '-')}-{e.get('intAwayScore', '-')} {e.get('strAwayTeam')}"
                              for e in evs[:4]]
                    self._avisar("Partidos de La Liga hoy, señor: " + " | ".join(partes))
                    return
                with urllib.request.urlopen(
                        "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t=" + _up.quote(eq),
                        timeout=15) as r:
                    d = json.loads(r.read().decode())
                teams = d.get("teams") or []
                if not teams:
                    self._avisar(f"Señor, no encontré el equipo «{eq}».")
                    return
                tid = teams[0]["idTeam"]
                nombre = teams[0]["strTeam"]
                with urllib.request.urlopen(
                        f"https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id={tid}", timeout=15) as r:
                    nd = json.loads(r.read().decode())
                with urllib.request.urlopen(
                        f"https://www.thesportsdb.com/api/v1/json/3/eventslast.php?id={tid}", timeout=15) as r:
                    ld = json.loads(r.read().decode())
                ultimo = (ld.get("results") or [None])[0]
                proximo = (nd.get("events") or [None])[0]
                partes = []
                if ultimo:
                    partes.append(f"Último: {ultimo.get('strHomeTeam')} {ultimo.get('intHomeScore')}-"
                                  f"{ultimo.get('intAwayScore')} {ultimo.get('strAwayTeam')}")
                if proximo:
                    partes.append(f"Próximo: {proximo.get('strEvent')} el {proximo.get('dateEvent')} "
                                  f"a las {proximo.get('strTime') or 'por definir'}")
                self._avisar(f"{nombre}, señor: " + (" | ".join(partes) if partes else "sin partidos próximos."))
            except Exception as e:
                self.log(f"Deportes fallo: {e}")
                self._avisar("Señor, no pude consultar los deportes.")
        threading.Thread(target=_do, daemon=True).start()
        return "Consultando los deportes, señor. Un momento."

    # ── BUSCAR ARCHIVOS EN EL PC ───────────────────────────────────────────
    def _buscar_archivos(self, t: str):
        m = re.search(r"(?:busca|buscar|encuentra|localiza|donde esta|dónde está)\s+(?:el\s+|la\s+|los\s+|las\s+)?"
                      r"(?P<nom>.+?)\s*(?:en el pc|en el equipo|en mi pc|en el disco)?\s*$", t)
        if not m:
            return None
        nombre = m.group("nom").strip().strip("?.")
        if not re.search(r"archivo|archivos|fichero|documento|pdf|factura|informe|video|vídeo|imagen|foto|"
                         r"carpeta|apk|exe|zip|en el pc|en el equipo|en mi pc|donde esta|dónde está", t) or \
           len(nombre) < 3:
            return None
        if self.safe:
            return f"(modo seguro: no buscaría «{nombre}»)"
        def _do():
            try:
                raices = [os.path.expanduser("~")]
                excluir = {"AppData", "NTUSER.DAT*", "ntuser.dat*", ".cache", "node_modules", "venv", ".git"}
                hallados = []
                total = 0
                for raiz in raices:
                    for dirpath, dirs, files in os.walk(raiz):
                        dirs[:] = [d for d in dirs if d not in excluir]
                        for f in files:
                            total += 1
                            if nombre.lower() in f.lower():
                                hallados.append(os.path.join(dirpath, f))
                                if len(hallados) >= 10:
                                    break
                        if len(hallados) >= 10:
                            break
                    if len(hallados) >= 10:
                        break
                if not hallados:
                    self._avisar(f"Señor, no encontré «{nombre}» en sus carpetas.")
                    return
                msg = f"Encontré {len(hallados)} archivo(s) «{nombre}»: " + " | ".join(hallados[:6])
                self._avisar(msg)
            except Exception as e:
                self.log(f"Buscar fallo: {e}")
                self._avisar("Señor, no pude completar la búsqueda.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Buscando «{nombre}» en el PC, señor. Un momento."

    # ── OCR DE IMÁGENES (Windows OCR) ──────────────────────────────────────
    _OCR_SCRIPT = r"""
$path = $args[0]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics,ContentType=WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) { Write-Output "OCR_NO_ENGINE"; exit 1 }
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    Write-Output $result.Text
} catch {
    Write-Output ("OCR_ERROR " + $_.Exception.Message)
    exit 1
}
"""

    def _ocr(self, t: str):
        es_pantalla = bool(re.search(r"lee lo que hay en pantalla|lee lo que esta en pantalla|"
                                     r"lee lo que veo en pantalla|lee la pantalla|"
                                     r"lee el texto de la pantalla", t))
        m = re.search(r"(?:lee el texto|saca el texto|extrae el texto|reconoce el texto|lee lo que dice)"
                      r"\s+(?:de\s+|de\s+la\s+|de\s+esta\s+|de\s+esta\s+foto\s+|de\s+esta\s+imagen\s+|en\s+)?"
                      r"(?P<f>.+?)\s*$", t)
        if not m and not es_pantalla:
            return None
        if es_pantalla:
            if self.safe:
                return "(modo seguro: no haría el OCR)"
            def _do_pantalla():
                try:
                    from PIL import ImageGrab
                    ruta_img = os.path.join(tempfile.gettempdir(), "jarvis_ocr_pantalla.png")
                    ImageGrab.grab().save(ruta_img, "PNG")
                    self._ocr_ejecutar(ruta_img)
                except Exception as e:
                    self.log(f"OCR pantalla fallo: {e}")
                    self._avisar("Señor, no pude leer la pantalla.")
            threading.Thread(target=_do_pantalla, daemon=True).start()
            return "Leyendo lo que hay en pantalla, señor. Un momento."
        nombre = m.group("f").strip().strip("?.")
        candidatos = [nombre,
                      os.path.join(os.path.expanduser("~"), "Downloads", nombre),
                      os.path.join(os.path.expanduser("~"), "Desktop", nombre),
                      os.path.join(os.path.expanduser("~"), "Documents", nombre),
                      os.path.join(os.path.expanduser("~"), "Descargas", nombre)]
        ruta = next((c for c in candidatos if os.path.isfile(c)), None)
        if not ruta:
            return f"Señor, no encontré la imagen «{nombre}»."
        if self.safe:
            return "(modo seguro: no haría el OCR)"
        threading.Thread(target=self._ocr_ejecutar, args=(ruta,), daemon=True).start()
        return "Leyendo el texto de la imagen, señor. Un momento."

    def _ocr_ejecutar(self, ruta: str):
        try:
            script = os.path.join(tempfile.gettempdir(), "jarvis_ocr.ps1")
            with open(script, "w", encoding="utf-8") as f:
                f.write(self._OCR_SCRIPT)
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                "-File", script, ruta],
                               capture_output=True, text=True, timeout=60,
                               creationflags=0x08000000)
            salida = (r.stdout or "").strip()
            if not salida or salida.startswith("OCR_"):
                self._avisar("Señor, no pude leer el texto de esa imagen.")
                return
            self._avisar(f"Texto de la imagen, señor: {salida[:400]}")
        except Exception as e:
            self.log(f"OCR fallo: {e}")
            self._avisar("Señor, no pude leer el texto de la imagen.")

    # ── TRANSCRIBIR AUDIO (System.Speech) ──────────────────────────────────
    def _transcribir(self, t: str):
        m = re.search(r"(?:transcribe|transcribir|pasa a texto|convierte a texto|que dice el audio|"
                      r"que dice la nota de voz)\s+(?:este\s+|el\s+|la\s+|esta\s+)?(?P<f>.+?)\s*$", t)
        if not m:
            return None
        nombre = m.group("f").strip().strip("?.")
        candidatos = [nombre,
                      os.path.join(os.path.expanduser("~"), "Downloads", nombre),
                      os.path.join(os.path.expanduser("~"), "Desktop", nombre),
                      os.path.join(os.path.expanduser("~"), "Documents", nombre),
                      os.path.join(os.path.expanduser("~"), "Descargas", nombre),
                      os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Notas", nombre)]
        ruta = next((c for c in candidatos if os.path.isfile(c)), None)
        if not ruta:
            return f"Señor, no encontré el audio «{nombre}»."
        if self.safe:
            return "(modo seguro: no transcribiría el audio)"
        def _do():
            try:
                # Whisper local (faster-whisper) si está instalado; si no, motor de Windows
                if self._whisper is not None or self._whisper_probar():
                    try:
                        if self._whisper is None:
                            from faster_whisper import WhisperModel
                            self._whisper = WhisperModel("base", device="cpu", compute_type="int8")
                        segmentos, _info = self._whisper.transcribe(ruta, language="es")
                        texto_w = " ".join(s.text.strip() for s in segmentos).strip()
                        if texto_w:
                            self._avisar(f"Transcripción, señor: {texto_w[:400]}")
                            return
                    except Exception as e:
                        self.log(f"Whisper fallo: {e}")
                wav = os.path.join(tempfile.gettempdir(), "jarvis_transcribe.wav")
                ffdir = self._ffmpeg_location()
                ffmpeg = os.path.join(ffdir, "ffmpeg.exe") if ffdir else None
                if ffmpeg and os.path.exists(ffmpeg):
                    subprocess.run([ffmpeg, "-y", "-i", ruta, "-ar", "16000", "-ac", "1", wav],
                                   capture_output=True, timeout=120, creationflags=0x08000000)
                else:
                    wav = ruta
                script = (r"""
Add-Type -AssemblyName System.Speech
$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine("es-ES")
try { $r.SetInputToWaveFile($args[0]) } catch { Write-Output "NO_RECONOCEDOR"; exit 1 }
$res = $r.Recognize()
if ($null -eq $res) { Write-Output "NO_RECONOCIDO" } else { Write-Output $res.Text }
""")
                ps = os.path.join(tempfile.gettempdir(), "jarvis_transcribe.ps1")
                with open(ps, "w", encoding="utf-8") as f:
                    f.write(script)
                r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                    "-File", ps, wav],
                                   capture_output=True, text=True, timeout=300,
                                   creationflags=0x08000000)
                salida = (r.stdout or "").strip()
                if not salida or salida.startswith("NO_"):
                    self._avisar("Señor, no pude reconocer el audio (¿está el motor de voz español instalado?).")
                    return
                self._avisar(f"Transcripción, señor: {salida[:400]}")
            except Exception as e:
                self.log(f"Transcribir fallo: {e}")
                self._avisar("Señor, no pude transcribir el audio.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Transcribiendo «{nombre}», señor. Un momento."

    def _whisper_probar(self):
        try:
            import importlib.util
            return importlib.util.find_spec("faster_whisper") is not None
        except Exception:
            return False

    # ── MODO NO MOLESTAR ───────────────────────────────────────────────────
    def _silencio(self, t: str):
        if re.search(r"activa modo silencio|modo no molestar on|activa el modo no molestar|"
                     r"activa modo no molestar|modo silencio on|no me molestes ahora", t):
            self._modo_silencio = True
            return "Modo no molestar activado, señor. Silencio total hasta nueva orden."
        if re.search(r"desactiva modo silencio|desactiva el modo no molestar|modo no molestar off|"
                     r"apaga modo silencio|quita el modo no molestar|ya puedes molestar", t):
            self._modo_silencio = False
            return "Modo no molestar desactivado, señor. Todo vuelve a la normalidad."
        return None

    # ── MODO AUSENTE ───────────────────────────────────────────────────────
    def _ausente_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "ausente.json")

    def _ausente(self, t: str):
        m = re.search(r"activa modo ausente con mensaje\s+[\"']?(?P<msg>.+?)[\"']?\s*$", t)
        if m:
            if self.safe:
                return "(modo seguro: no activaría el modo ausente)"
            msg = m.group("msg").strip()
            json.dump({"activo": True, "mensaje": msg},
                      open(self._ausente_path(), "w", encoding="utf-8"))
            return (f"Modo ausente activado, señor. Cuando le escriban, responderé: «{msg}» "
                    f"y le avisaré a usted por Telegram.")
        if re.search(r"activa modo ausente|activa el modo ausente|modo ausente on", t):
            if self.safe:
                return "(modo seguro: no activaría el modo ausente)"
            json.dump({"activo": True, "mensaje": "Señor no está disponible en este momento. Le devolveré el mensaje cuando vuelva."},
                      open(self._ausente_path(), "w", encoding="utf-8"))
            return "Modo ausente activado, señor. Contestaré con el mensaje por defecto."
        if re.search(r"desactiva modo ausente|desactiva el modo ausente|modo ausente off|"
                     r"quita el modo ausente|apaga modo ausente", t):
            json.dump({"activo": False, "mensaje": ""},
                      open(self._ausente_path(), "w", encoding="utf-8"))
            return "Modo ausente desactivado, señor."
        if re.search(r"que mensaje hay en modo ausente|modo ausente actual|mensaje del modo ausente", t):
            try:
                a = json.load(open(self._ausente_path(), encoding="utf-8"))
                if a.get("activo"):
                    return f"Modo ausente activo con mensaje: «{a.get('mensaje', '')}»"
                return "El modo ausente está desactivado, señor."
            except Exception:
                return "El modo ausente está desactivado, señor."
        return None

    # ── BLUETOOTH ──────────────────────────────────────────────────────────
    def _bluetooth(self, t: str):
        if re.search(r"desconecta el bluetooth|apaga el bluetooth|desactiva el bluetooth|"
                     r"quita el bluetooth", t):
            if self.safe:
                return "(modo seguro: no tocaría el Bluetooth)"
            def _do():
                try:
                    subprocess.run(["powershell", "-NoProfile", "-Command",
                                    "Get-PnpDevice -Class Bluetooth -Status OK | ForEach-Object { Disable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false }"],
                                   capture_output=True, timeout=60, creationflags=0x08000000)
                    self._avisar("Bluetooth desactivado, señor.")
                except Exception as e:
                    self.log(f"Bluetooth fallo: {e}")
                    self._avisar("Señor, no pude desactivar el Bluetooth (quizá necesite permisos de administrador).")
            threading.Thread(target=_do, daemon=True).start()
            return "Desactivando el Bluetooth, señor."
        if re.search(r"conecta mis auriculares|conecta mis audifonos|conecta los auriculares|"
                     r"activa el bluetooth|enciende el bluetooth|conecta el bluetooth", t):
            if self.safe:
                return "(modo seguro: no tocaría el Bluetooth)"
            def _do():
                try:
                    subprocess.run(["powershell", "-NoProfile", "-Command",
                                    "Get-PnpDevice -Class Bluetooth -Status Error | ForEach-Object { Enable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false }"],
                                   capture_output=True, timeout=60, creationflags=0x08000000)
                    self._avisar("Bluetooth activado, señor. Conecte sus auriculares desde el icono del sistema.")
                except Exception as e:
                    self.log(f"Bluetooth fallo: {e}")
                    self._avisar("Señor, no pude activar el Bluetooth (quizá necesite permisos de administrador).")
            threading.Thread(target=_do, daemon=True).start()
            return "Activando el Bluetooth, señor."
        return None

    # ── STATS DE USO (sesiones de la semana) ───────────────────────────────
    def _stats_uso(self, t: str):
        if not re.search(r"cuantas horas he usado|cuántas horas he usado|horas he usado el pc|"
                         r"tiempo de uso|cuanto tiempo he usado|cuánto tiempo he usado", t):
            return None
        if self.safe:
            return "(modo seguro: no consultaría las estadísticas)"
        def _do():
            try:
                ps = os.path.join(tempfile.gettempdir(), "jarvis_uptime.ps1")
                script = r"""
$start = (Get-Date).AddDays(-7)
$arranques = Get-WinEvent -FilterHashtable @{LogName='System'; Id=12; StartTime=$start} -ErrorAction SilentlyContinue | Sort-Object TimeCreated
$apagados  = Get-WinEvent -FilterHashtable @{LogName='System'; Id=13; StartTime=$start} -ErrorAction SilentlyContinue | Sort-Object TimeCreated
$total = 0.0
foreach ($a in $arranques) {
    $fin = ($apagados | Where-Object { $_.TimeCreated -gt $a.TimeCreated } | Select-Object -First 1).TimeCreated
    if ($null -eq $fin) { $fin = Get-Date }
    $total += ($fin - $a.TimeCreated).TotalHours
}
Write-Output ("{0:N1}" -f $total)
"""
                with open(ps, "w", encoding="utf-8") as f:
                    f.write(script)
                r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps],
                                   capture_output=True, text=True, timeout=60, creationflags=0x08000000)
                horas = (r.stdout or "").strip()
                if not horas:
                    self._avisar("Señor, no pude calcular el tiempo de uso.")
                    return
                self._avisar(f"Esta semana ha usado el equipo {horas} horas, señor.")
            except Exception as e:
                self.log(f"Stats uso fallo: {e}")
                self._avisar("Señor, no pude calcular el tiempo de uso.")
        threading.Thread(target=_do, daemon=True).start()
        return "Calculando el tiempo de uso de esta semana, señor."

    # ── APAGAR PANTALLA ────────────────────────────────────────────────────
    def _pantalla(self, t: str):
        if not re.search(r"apaga la pantalla|apaga el monitor|apaga la pantalla del pc|"
                         r"apaga el monitor del pc", t):
            return None
        if self.safe:
            return "(modo seguro: no apagaría la pantalla)"
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
            return "Pantalla apagada, señor. Mueva el ratón o pulse una tecla para recuperarla."
        except Exception:
            return "Señor, no pude apagar la pantalla."

    # ── ENVIAR ARCHIVO AL MÓVIL ──────────────────────────────────────────────
    def _enviar_archivo(self, t: str):
        if not re.search(r"envia|enviame|mandame|manda|pasame|pasa", t) or \
           not re.search(r"archivo|documento|pdf|informe|foto|imagen|video|zip", t) or \
           not re.search(r"telefono|movil|celular", t):
            return None
        m = re.search(r"(?:envia|enviame|mandame|manda|pasame|pasa)\s+(?:el\s+|la\s+|mi\s+|este\s+|esta\s+|ese\s+|esa\s+)?"
                      r"(?:archivo|documento|fichero)\s+(?P<nom>[^\s]+)\s+(?:a\s+)?(?:mi\s+|el\s+|al\s+)?(?:telefono|movil|celular)", t)
        if not m:
            m = re.search(r"(?:envia|enviame|mandame|manda)\s+(?:el\s+|la\s+|mi\s+)?(?P<nom>[^\s]+\.(?:pdf|docx?|xlsx?|pptx?|txt|zip|png|jpg|jpeg|mp3|mp4))\s+(?:a\s+)?(?:mi\s+|el\s+|al\s+)?(?:telefono|movil|celular)", t)
        if not m:
            return None
        nombre = m.group("nom").strip().strip(".,")
        candidatos = [nombre,
                      os.path.join(os.path.expanduser("~"), "Downloads", nombre),
                      os.path.join(os.path.expanduser("~"), "Desktop", nombre),
                      os.path.join(os.path.expanduser("~"), "Documents", nombre),
                      os.path.join(os.path.expanduser("~"), "Descargas", nombre),
                      os.path.join(os.path.expanduser("~"), "Escritorio", nombre)]
        ruta = next((c for c in candidatos if os.path.isfile(c)), None)
        if not ruta:
            return f"Señor, no encontré «{nombre}». Dígame la ruta completa o asegúrese de que esté en Descargas o el Escritorio."
        if self.safe:
            return f"(modo seguro: no enviaría «{nombre}»)"
        def _do():
            try:
                base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "envios")
                os.makedirs(base, exist_ok=True)
                destino = os.path.join(base, os.path.basename(ruta))
                if os.path.exists(destino):
                    destino = os.path.join(base, f"{datetime.now().strftime('%H%M%S')}_{os.path.basename(ruta)}")
                import shutil
                shutil.copy2(ruta, destino)
                url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/envios/{os.path.basename(destino)}"
                self._avisar(f"Archivo «{os.path.basename(ruta)}» listo en su teléfono: {url}")
            except Exception as e:
                self.log(f"Envio archivo fallo: {e}")
                self._avisar(f"Señor, no pude enviar «{nombre}» a su teléfono.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Enviando «{nombre}» a su teléfono, señor."

    # ── LISTAR ARCHIVOS (navegador móvil) ───────────────────────────────────
    def _archivos_movil(self, t: str):
        m = re.search(r"(?:muestrame|muéstrame|lista|listame|dime|ver|que archivos hay|que hay)\s+"
                      r"(?:los\s+|las\s+|que\s+)?archivos?\s+(?:de\s+|en\s+)?(?P<ubi>.+?)\s*$", t)
        if not m:
            return None
        ubi = m.group("ubi").strip().strip("?.")
        if not ubi or len(ubi) < 3:
            return None
        ruta = self._ubicacion_real(ubi)
        if not ruta or not os.path.isdir(ruta):
            return f"Señor, no encuentro la carpeta «{ubi}»."
        try:
            archivos = sorted(
                (f for f in os.listdir(ruta) if os.path.isfile(os.path.join(ruta, f))),
                key=lambda f: -os.path.getsize(os.path.join(ruta, f)))[:20]
        except Exception:
            return None
        if not archivos:
            return f"La carpeta {ubi} está vacía, señor."
        partes = []
        for a in archivos:
            tam = os.path.getsize(os.path.join(ruta, a))
            partes.append(f"{a} ({tam / 1048576:.1f} MB)" if tam > 1048576 else f"{a} ({tam // 1024} KB)")
        return (f"En {ubi} hay {len(archivos)} archivos. Los más recientes: " + ", ".join(partes)
                + ". Para enviarme uno: «envía el archivo <nombre> a mi teléfono».")

    # ── MODO ANTI ROBO (aviso al desbloquear) ───────────────────────────────
    def _antirobo(self, t: str):
        if re.search(r"activa el modo anti robo|activa el anti robo|protege el pc|protege el equipo|"
                     r"modo anti robo on|vigila si alguien desbloquea", t):
            if self._antirobo_activo:
                return "El modo anti robo ya está activo, señor."
            if self.safe:
                return "(modo seguro: no activaría el modo anti robo)"
            self._antirobo_activo = True
            def _loop():
                import ctypes
                wts = ctypes.windll.wtsapi32
                estado = None
                while self._antirobo_activo:
                    try:
                        sid = wts.WTSGetActiveConsoleSessionId()
                        if sid == 0xFFFFFFFF:
                            time.sleep(3)
                            continue
                        p = ctypes.c_void_p()
                        n = ctypes.c_ulong()
                        ok = wts.WTSQuerySessionInformationW(0, sid, 10, ctypes.byref(p), ctypes.byref(n))
                        if ok and p.value:
                            nuevo = ctypes.cast(p, ctypes.POINTER(ctypes.c_int)).contents.value
                            wts.WTSFreeMemory(p)
                            if estado == 4 and nuevo == 0:  # Desconectado -> Activo = desbloqueo
                                self._foto_antirobo()
                            estado = nuevo
                    except Exception as e:
                        self.log(f"Antirobo fallo: {e}")
                    time.sleep(3)
            threading.Thread(target=_loop, daemon=True).start()
            return ("Modo anti robo activado, señor. Si alguien desbloquea el equipo, "
                    "tomaré una foto y se la enviaré a su teléfono.")
        if re.search(r"desactiva el modo anti robo|para el anti robo|apaga el anti robo|"
                     r"desactiva el anti robo", t):
            self._antirobo_activo = False
            return "Modo anti robo desactivado, señor."
        return None

    def _foto_antirobo(self):
        try:
            import cv2
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if cap.isOpened():
                ok, frame = cap.read()
                cap.release()
                if ok:
                    d = os.path.join(self._caps_dir, "Antirobo")
                    os.makedirs(d, exist_ok=True)
                    nombre = f"alguien_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    cv2.imwrite(os.path.join(d, nombre), frame)
                    pub = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "capturas", nombre)
                    try:
                        os.makedirs(os.path.dirname(pub), exist_ok=True)
                        cv2.imwrite(pub, frame)
                        url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/capturas/{nombre}"
                    except Exception:
                        url = ""
                    urls = [u for u in [url] if u]
                    try:
                        from PIL import ImageGrab
                        nombre_ss = f"escritorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        ImageGrab.grab().save(os.path.join(d, nombre_ss), "JPEG")
                        pub_ss = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "web_interface", "capturas", nombre_ss)
                        ImageGrab.grab().save(pub_ss, "JPEG")
                        urls.append(f"http://{self._ip_lan()}:{jarvis_config.PORT}/capturas/{nombre_ss}")
                    except Exception:
                        pass
                    extra = (" Imágenes: " + " y ".join(urls)) if urls else ""
                    self._avisar("Alguien ha desbloqueado el equipo, señor." + extra)
                    return
        except Exception as e:
            self.log(f"Foto antirobo fallo: {e}")
        self._avisar("Alguien ha desbloqueado el equipo, señor. No pude tomar foto de la cámara.")

    # ── BLOQUEO POR PRESENCIA (móvil conectado) ─────────────────────────────
    def _presencia_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "presencia.json")

    def _presencia(self, t: str):
        if re.search(r"bloqueo por presencia|bloquea el pc si pierdo la conexion|bloquea el pc si mi telefono se va|"
                     r"bloqueo cuando me vaya|activa el bloqueo por presencia", t):
            json.dump({"activo": True}, open(self._presencia_path(), "w", encoding="utf-8"))
            return ("Bloqueo por presencia activado, señor: cuando su teléfono pierda la conexión "
                    "con JARVIS, el equipo se bloqueará automáticamente.")
        if re.search(r"desactiva el bloqueo por presencia|quita el bloqueo por presencia|"
                     r"para el bloqueo por presencia", t):
            json.dump({"activo": False}, open(self._presencia_path(), "w", encoding="utf-8"))
            return "Bloqueo por presencia desactivado, señor."
        return None

    # ── WEBHOOKS ────────────────────────────────────────────────────────────
    def _webhooks_path(self) -> str:
        d = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "webhooks.json")

    def _webhooks_leer(self) -> dict:
        try:
            return json.load(open(self._webhooks_path(), encoding="utf-8"))
        except Exception:
            return {}

    def _webhooks_guardar(self, d: dict):
        with open(self._webhooks_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _webhook(self, t: str):
        if re.search(r"crea un webhook|configura un webhook|dame un webhook|hazme un webhook", t):
            import secrets
            clave = secrets.token_hex(6)
            wh = self._webhooks_leer()
            wh[clave] = {"ts": datetime.now().isoformat()}
            self._webhooks_guardar(wh)
            url = f"http://{self._ip_lan()}:{jarvis_config.PORT}/webhook/{clave}"
            return (f"Webhook creado, señor: {url}. Llámelo con un POST desde IFTTT, "
                    f"Google Home o cualquier servicio y le avisaré en su teléfono al instante.")
        if re.search(r"borra mi webhook|elimina mi webhook|desactiva mi webhook|quita mi webhook", t):
            self._webhooks_guardar({})
            return "Webhook eliminado, señor."
        if re.search(r"que webhook tengo|mi webhook|webhook actual", t):
            wh = self._webhooks_leer()
            if not wh:
                return "No tiene webhooks activos, señor. Dígame «crea un webhook»."
            clave = next(iter(wh))
            return f"Su webhook activo: http://{self._ip_lan()}:{jarvis_config.PORT}/webhook/{clave}"
        return None

    # ── BOT DE TELEGRAM ─────────────────────────────────────────────────────
    def _telegram_path(self) -> str:
        # Misma ruta que usa telegram_bot.py: jarvis_config resuelve
        # Descargas/Downloads. Fijarla a "Descargas" hacia que el token se
        # guardara donde el bot no lo buscaba.
        try:
            import jarvis_config
            ruta = jarvis_config.TELEGRAM_JSON
        except Exception:
            ruta = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                "Prefs", "telegram.json")
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        return ruta

    def _telegram_lanzar(self) -> bool:
        """Levanta telegram_bot.py ya mismo, sin esperar a reiniciar JARVIS."""
        try:
            raiz = os.path.dirname(os.path.abspath(__file__))
            bot = os.path.join(raiz, "telegram_bot.py")
            if not os.path.exists(bot):
                return False
            exe = sys.executable or "python"
            kwargs = {"cwd": raiz, "env": {**os.environ, "JARVIS_TELEGRAM_CHILD": "1"}}
            if os.name == "nt":
                pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
                if os.path.exists(pythonw):
                    exe = pythonw
                kwargs["creationflags"] = 0x08000000
            subprocess.Popen([exe, bot], **kwargs)
            return True
        except Exception as e:
            self.log(f"No pude lanzar el bot de Telegram: {e}")
            return False

    def _telegram(self, t: str):
        m = re.search(r"configura mi bot de telegram en (\d+:[A-Za-z0-9_-]{20,})", t)
        if m:
            if self.safe:
                return "(modo seguro: no guardaría el token)"
            ruta = self._telegram_path()
            try:  # conservar offset/chat_id de una configuracion anterior
                datos = json.load(open(ruta, encoding="utf-8-sig"))
                if not isinstance(datos, dict):
                    datos = {}
            except Exception:
                datos = {}
            datos["token"] = m.group(1)
            json.dump(datos, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            if self._telegram_lanzar():
                return ("Token de Telegram guardado, señor. El bot ya está en marcha: "
                        "mándele un mensaje y le responderé desde el PC.")
            return ("Token de Telegram guardado, señor. El bot se activará en el próximo arranque de JARVIS. "
                    "Mándele un mensaje al bot y le responderé desde el PC.")
        if re.search(r"estado de mi bot de telegram|mi bot de telegram", t):
            try:
                tg = json.load(open(self._telegram_path(), encoding="utf-8"))
            except Exception:
                tg = {}
            if tg.get("token"):
                return "Su bot de Telegram está configurado y activo, señor."
            return ("No tiene bot de Telegram configurado, señor. Cree uno con @BotFather y dígame: "
                    "«configura mi bot de telegram en SU_TOKEN».")
        if re.search(r"desactiva mi bot de telegram|borra mi bot de telegram|quita mi bot de telegram", t):
            try:
                os.remove(self._telegram_path())
                return "Bot de Telegram desactivado, señor. Se detendrá en el próximo arranque."
            except Exception:
                return "No había bot de Telegram configurado, señor."
        return None

    # ── ENCENDIDO PROGRAMADO (Wake timer) ───────────────────────────────────
    def _encendido(self, t: str):
        m = re.search(r"(?:enciendete|enciéndete|despiertame el pc|arrancate|arrancate el pc)\s+(?P<cuando>.+?)\s*$", t)
        if not m:
            return None
        if self.safe:
            return "(modo seguro: no programaría el encendido)"
        fecha, _ = self._fecha_agenda(m.group("cuando"))
        if not fecha:
            return None
        if fecha <= datetime.now():
            return "Señor, esa hora ya pasó. Dígame «enciéndete mañana a las 8»."
        import tempfile as _tf
        xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><TimeTrigger><StartBoundary>{fecha.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary><Enabled>true</Enabled></TimeTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><Enabled>true</Enabled><WakeToRun>true</WakeToRun><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries></Settings>
  <Actions><Exec><Command>cmd.exe</Command><Arguments>/c exit</Arguments></Exec></Actions>
</Task>'''
        ruta_xml = os.path.join(_tf.gettempdir(), "jarvis_wake.xml")
        with open(ruta_xml, "w", encoding="utf-16") as f:
            f.write(xml)
        try:
            r = subprocess.run(f'schtasks /Create /F /TN "JARVIS_WAKEUP" /XML "{ruta_xml}"',
                               capture_output=True, text=True, timeout=20, shell=True,
                               creationflags=0x08000000)
            if "success" in (r.stdout or "").lower() or "correctamente" in (r.stdout or "").lower() or r.returncode == 0:
                return (f"Programado, señor: el equipo despertará el {fecha.strftime('%d/%m')} a las "
                        f"{fecha.strftime('%H:%M')}. Funciona desde suspensión o hibernación; "
                        f"si está apagado del todo, active el arranque RTC en la BIOS.")
            return f"Señor, no pude programar el encendido: {(r.stdout or r.stderr)[:80]}"
        except Exception as e:
            return f"Señor, no pude programar el encendido: {str(e)[:80]}"

    # ── HISTORIAL DE CONVERSACIONES ─────────────────────────────────────────
    def _historial(self, t: str):
        m = re.search(r"(?:de que hablamos|de qué hablamos|que hicimos|que hiciste|resumen de la conversacion|"
                      r"resumen de (?:ayer|hoy)|historial de (?:ayer|hoy)|que paso (?:ayer|hoy))\s*(?P<dia>ayer|hoy)?", t)
        if not m:
            return None
        dia = m.group("dia") or ("ayer" if re.search(r"ayer", t) else "hoy")
        try:
            import sqlite3
            fecha = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d") if dia == "ayer" \
                else datetime.now().strftime("%Y-%m-%d")
            for base in (jarvis_config.JARVIS_DB,
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_interface", "jarvis_memory.db")):
                if os.path.exists(base):
                    conn = sqlite3.connect(base, timeout=5)
                    cur = conn.cursor()
                    cur.execute("SELECT role, content FROM interactions WHERE timestamp LIKE ? "
                                "ORDER BY id DESC LIMIT 12", (fecha + "%",))
                    filas = cur.fetchall()
                    conn.close()
                    if not filas:
                        return f"Señor, no guardé conversaciones {dia}."
                    partes = []
                    for role, content in reversed(filas):
                        quien = "usted" if role == "user" else "yo"
                        partes.append(f"{quien}: {content[:120]}")
                    resumen = " | ".join(partes[-6:])
                    return f"Resumen de {dia}, señor: {resumen}"
            return "Señor, no encontré la memoria de conversaciones."
        except Exception as e:
            self.log(f"Historial fallo: {e}")
            return "Señor, no pude leer el historial de conversaciones."

    # ── MENÚ SEMANAL ────────────────────────────────────────────────────────
    def _menu_semanal(self, t: str):
        if not re.search(r"menu semanal|menú semanal|planifica el menu|planifica el menú|"
                         r"menu de la semana|menú de la semana", t):
            return None
        if self.safe:
            return "(modo seguro: no generaría el menú)"
        import random as _r
        desayunos = ["Tostada con tomate y aceite", "Yogur con granola y fruta", "Huevos revueltos con jamón",
                     "Avena con plátano", "Café con leche y croissant", "Batido de frutas", "Tortitas de avena"]
        comidas = ["Lentejas con arroz", "Pollo al horno con patatas", "Pasta con tomate y albahaca",
                   "Sopa de verduras y pescado", "Ensalada de garbanzos", "Arroz con pollo",
                   "Merluza a la plancha con ensalada"]
        cenas = ["Tortilla francesa", "Crema de calabaza", "Ensalada con atún", "Pescado al vapor con brócoli",
                 "Revuelto de champiñones", "Sopa de pescado", "Yogur con frutos secos"]
        _r.shuffle(desayunos); _r.shuffle(comidas); _r.shuffle(cenas)
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        lineas = ["# Menú semanal", ""]
        for i, d in enumerate(dias):
            lineas.append(f"**{d}**")
            lineas.append(f"- Desayuno: {desayunos[i]}")
            lineas.append(f"- Comida: {comidas[i]}")
            lineas.append(f"- Cena: {cenas[i]}")
            lineas.append("")
        ruta = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "menu_semanal.md")
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))
        self._avisar(f"Menú semanal listo, señor. Hoy: {comidas[datetime.now().weekday()]}. "
                     f"Guardado en {ruta}")
        return "Generando el menú semanal, señor. Un momento."

    # ── DESINSTALAR PROGRAMAS (winget) ──────────────────────────────────────
    def _desinstalar(self, t: str):
        m = re.search(r"desinstala|desinstalar|quita el programa|borra el programa\s+(?P<app>.+?)\s*$", t)
        if not m:
            return None
        app = m.group("app").strip().strip(".")
        if not app or len(app) > 40:
            return None
        if self.safe:
            return f"(modo seguro: no desinstalaría «{app}»)"
        def _do():
            try:
                r = subprocess.run(
                    f'winget uninstall --name "{app}" --silent --accept-source-agreements --disable-interactivity',
                    capture_output=True, text=True, timeout=180, shell=True, creationflags=0x08000000)
                if r.returncode == 0 or "se ha desinstalado" in (r.stdout or "").lower():
                    self._avisar(f"«{app}» desinstalado correctamente, señor.")
                else:
                    self._avisar(f"Señor, no pude desinstalar «{app}»: {(r.stderr or r.stdout or 'sin detalle')[:100]}")
            except Exception as e:
                self.log(f"Desinstalar fallo: {e}")
                self._avisar(f"Señor, la desinstalación de «{app}» falló: {str(e)[:80]}")
        threading.Thread(target=_do, daemon=True).start()
        return f"Desinstalando «{app}», señor. Un momento."

    # ── BRILLO DE PANTALLA ──────────────────────────────────────────────────
    def _brillo(self, t: str):
        m = re.search(r"(?:sube|baja|pon|ajusta|cambia|al|a)\s+el\s+brillo\s+(?:al\s+|a\s+|del\s+|en\s+)?(\d{1,3})", t)
        if not m:
            return None
        nivel = min(int(m.group(1)), 100)
        if self.safe:
            return f"(modo seguro: no cambiaría el brillo al {nivel}%)"
        def _do():
            try:
                script = (f"$m = Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods; "
                          f"$m.WmiSetBrightness(1, {nivel})")
                r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                   capture_output=True, text=True, timeout=20,
                                   creationflags=0x08000000)
                if r.returncode == 0:
                    self._avisar(f"Brillo al {nivel}%, señor.")
                else:
                    self._avisar("Señor, no pude cambiar el brillo (el monitor puede no soportarlo).")
            except Exception as e:
                self.log(f"Brillo fallo: {e}")
                self._avisar("Señor, no pude cambiar el brillo.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Ajustando el brillo al {nivel}%, señor."

    # ── HORA MUNDIAL ────────────────────────────────────────────────────────
    _ZONAS = {
        "nueva york": "America/New_York", "new york": "America/New_York", "miami": "America/New_York",
        "londres": "Europe/London", "paris": "Europe/Paris", "madrid": "Europe/Madrid",
        "barcelona": "Europe/Madrid", "sevilla": "Europe/Madrid", "valencia": "Europe/Madrid",
        "berlin": "Europe/Berlin", "roma": "Europe/Rome", "lisboa": "Europe/Lisbon",
        "tokio": "Asia/Tokyo", "tokyo": "Asia/Tokyo", "pekin": "Asia/Shanghai", "beijing": "Asia/Shanghai",
        "singapur": "Asia/Singapore", "dubai": "Asia/Dubai", "moscu": "Europe/Moscow",
        "estambul": "Europe/Istanbul", "mexico": "America/Mexico_City",
        "buenos aires": "America/Argentina/Buenos_Aires", "santiago": "America/Santiago",
        "lima": "America/Lima", "bogota": "America/Bogota", "la habana": "America/Havana",
        "caracas": "America/Caracas", "los angeles": "America/Los_Angeles", "chicago": "America/Chicago",
        "sydney": "Australia/Sydney", "dublin": "Europe/Dublin", "amsterdam": "Europe/Amsterdam",
        "viena": "Europe/Vienna", "praga": "Europe/Prague", "estocolmo": "Europe/Stockholm",
        "helsinki": "Europe/Helsinki", "athens": "Europe/Athens", "montevideo": "America/Montevideo",
        "asuncion": "America/Asuncion", "quito": "America/Guayaquil", "san juan": "America/Puerto_Rico",
    }

    def _hora_mundial(self, t: str):
        m = re.search(r"(?:que hora es en|hora en|hora de|que hora hay en)\s+(?P<ciudad>.+?)\s*$", t)
        if not m:
            return None
        ciudad = m.group("ciudad").strip().strip("?.")
        zona = self._ZONAS.get(self._norm(ciudad)) or self._ZONAS.get(ciudad.lower())
        if not zona:
            return f"Señor, no tengo la zona horaria de «{ciudad}»."
        try:
            from zoneinfo import ZoneInfo
            ahora = datetime.now(ZoneInfo(zona))
            return f"En {ciudad} son las {ahora.strftime('%H:%M')} horas, señor."
        except Exception:
            try:
                import urllib.parse
                with urllib.request.urlopen(f"https://worldtimeapi.org/api/timezone/{zona}", timeout=10) as r:
                    d = json.loads(r.read().decode())
                hh = d.get("datetime", "")[11:16]
                return f"En {ciudad} son las {hh} horas, señor."
            except Exception:
                return f"Señor, no pude consultar la hora en {ciudad}."
        return None

    # ── LEER EN VOZ ALTA (audiolibro) ───────────────────────────────────────
    def _leer(self, t: str):
        if re.search(r"para de leer|deja de leer|calla|silencio de lectura|para el audiolibro|"
                     r"deten la lectura|detén la lectura", t):
            if self._lector and self._lector.poll() is None:
                try:
                    self._lector.terminate()
                except Exception:
                    pass
                self._lector = None
                return "Lectura detenida, señor."
            return "No estaba leyendo nada, señor."
        m = re.search(r"(?:leeme|leer en voz alta|lee en voz alta|leeme en voz alta|audiolibro|"
                      r"lee el libro)\s+(?:el\s+|este\s+|la\s+|esta\s+)?(?P<f>.+?)\s*$", t)
        if not m:
            return None
        nombre = m.group("f").strip().strip("?.")
        candidatos = [nombre,
                      os.path.join(os.path.expanduser("~"), "Downloads", nombre),
                      os.path.join(os.path.expanduser("~"), "Desktop", nombre),
                      os.path.join(os.path.expanduser("~"), "Documents", nombre),
                      os.path.join(os.path.expanduser("~"), "Descargas", nombre)]
        ruta = next((c for c in candidatos if os.path.isfile(c)), None)
        if not ruta:
            return f"Señor, no encontré «{nombre}». ¿Tiene el archivo en Descargas o el Escritorio?"
        if self.safe:
            return f"(modo seguro: no leería «{nombre}»)"
        def _do():
            try:
                texto = self._resumir_fuente(ruta)
                if not texto or len(texto) < 20:
                    self._avisar(f"Señor, no pude extraer texto de «{nombre}».")
                    return
                texto = texto[:5000]
                _vz = self._voz_leer()
                _rate = max(-10, min(10, int(_vz.get("rate") or 0)))
                _vname = (_vz.get("voice") or "").strip()
                _sel = ("try { $s.SelectVoice('%s') } catch {}" % _vname) if _vname else ""
                script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToDefaultAudioDevice()
$s.Rate = %d
%s
$texto = [Console]::In.ReadToEnd()
foreach ($trozo in ($texto -split '(?<=[.;!?])')) {
    $t = $trozo.Trim()
    if ($t.Length -gt 2) { [void]$s.SpeakAsync($t).Wait() }
}
$s.Dispose()
""" % (_rate, _sel)
                p = subprocess.Popen(["powershell", "-NoProfile", "-Command", script],
                                     stdin=subprocess.PIPE,
                                     creationflags=0x08000000)
                p.stdin.write(texto.encode("utf-8", "ignore"))
                p.stdin.close()
                self._lector = p
                self._avisar(f"Leyendo «{os.path.basename(ruta)}», señor. Diga «para de leer» para detenerme.")
            except Exception as e:
                self.log(f"Leer fallo: {e}")
                self._avisar(f"Señor, no pude leer «{nombre}».")
        threading.Thread(target=_do, daemon=True).start()
        return f"Preparando la lectura de «{nombre}», señor."

    # ── PODCASTS (iTunes Search API + RSS) ──────────────────────────────────
    def _podcast(self, t: str):
        if re.search(r"para el podcast|apaga el podcast|deten el podcast|quita el podcast", t):
            self._matar_reproductor()
            return "Podcast detenido, señor."
        m = re.search(r"(?:pon|ponme|reproduce|sintoniza|activa)\s+(?:el\s+|la\s+)?podcast"
                      r"(?:\s+(?:de|sobre|del)\s+(?P<q>.+?))?\s*$", t)
        if not m:
            return None
        q = (m.group("q") or "").strip().strip(".")
        if not q:
            return "¿Qué podcast quiere escuchar, señor? Por ejemplo: «pon el podcast de ciencia»."
        if self.safe:
            return f"(modo seguro: no reproduciría el podcast «{q[:40]}»)"
        def _do():
            try:
                import urllib.parse
                url = ("https://itunes.apple.com/search?term=" + urllib.parse.quote(q)
                       + "&media=podcast&limit=1&country=ES")
                with urllib.request.urlopen(url, timeout=15) as r:
                    data = json.loads(r.read().decode("utf-8", "ignore"))
                res = data.get("results") or []
                if not res:
                    self._avisar(f"Señor, no encontré el podcast «{q}».")
                    return
                feed = res[0].get("feedUrl") or ""
                titulo = res[0].get("trackName") or q
                if not feed:
                    self._avisar("Señor, el podcast no tiene feed disponible.")
                    return
                with urllib.request.urlopen(feed, timeout=15) as r:
                    xml = r.read().decode("utf-8", "ignore")
                import xml.etree.ElementTree as ET
                raiz = ET.fromstring(xml)
                item = raiz.find(".//item") or raiz.find(".//*[local-name()='item']")
                audio = ""
                if item is not None:
                    enc = item.find("enclosure")
                    if enc is not None:
                        audio = enc.attrib.get("url", "")
                if not audio:
                    self._avisar("Señor, el último episodio no tiene audio disponible.")
                    return
                import shutil
                ffdir = self._ffmpeg_location()
                ffplay = os.path.join(ffdir, "ffplay.exe") if ffdir else shutil.which("ffplay")
                if ffplay:
                    self._matar_reproductor()
                    self._player = subprocess.Popen(
                        [ffplay, "-nodisp", "-loglevel", "quiet", "-autoexit", audio],
                        creationflags=0x08000000)
                    self._avisar(f"Reproduciendo el podcast «{titulo}», señor.")
                else:
                    subprocess.Popen(["start", "", audio], shell=True)
                    self._avisar(f"Abro el podcast «{titulo}» en el navegador, señor.")
            except Exception as e:
                self.log(f"Podcast fallo: {e}")
                self._avisar(f"Señor, no pude reproducir el podcast «{q[:40]}»: {str(e)[:80]}")
        threading.Thread(target=_do, daemon=True).start()
        return f"Buscando el podcast «{q}», señor. Un momento."

    # ── DESCARGA DE VIDEOS / MÚSICA (yt-dlp) ─────────────────────────────────
    @staticmethod
    def _ffmpeg_location() -> str:
        """Devuelve el directorio con ffmpeg.exe o '' si no lo encuentra."""
        import shutil
        exe = shutil.which("ffmpeg")
        if exe:
            return os.path.dirname(exe)
        for base in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"),):
            if os.path.isdir(base):
                for raiz, _, archivos in os.walk(base):
                    if "ffmpeg.exe" in archivos:
                        return raiz
        for ruta in (r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin"):
            if os.path.isfile(os.path.join(ruta, "ffmpeg.exe")):
                return ruta
        return ""

    def _descargar_video(self, t: str):
        m_url = re.search(r"(?:descarga|descargar|baja|bajate)\s+(?:este\s+|ese\s+)?(?:video\s+|musica\s+|audio\s+)?(https?://\S+)", self._orig)
        m = re.search(r"(?:descarga|descargar|baja|bajate|guardame)\s+(?:el\s+|la\s+|los\s+|las\s+|lo\s+|un\s+|una\s+|este\s+|esta\s+|ese\s+|esa\s+)?(?:video|musica|audio|cancion|pista)\s+(?:de\s+youtube\s+)?(?:de\s+|llamado\s+|sobre\s+|de\s+la\s+)?(.+?)\s*$", t)
        if not m and not m_url:
            return None
        if m and any(k in m.group(1) for k in ("mi pc", "tu pc", "el sistema", "windows", "la nube")):
            return None
        query = (m_url.group(1) if m_url else m.group(1)).strip().strip(".")
        if not query:
            return None
        es_musica = bool(re.search(r"musica|audio|cancion|pista", t))
        if self.safe:
            return f"(modo seguro: no descargaría «{query[:40]}»)"

        def _do():
            try:
                import yt_dlp
                base = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Videos")
                os.makedirs(base, exist_ok=True)
                ff = self._ffmpeg_location()
                opts = {
                    "outtmpl": os.path.join(base, "%(title).80s.%(ext)s"),
                    "format": "bestaudio/best" if es_musica else "best[height<=1080]/best",
                    "quiet": True,
                    "noplaylist": True,
                    "noprogress": True,
                    "extractor_args": {"youtube": {"player_client": ["tv_embedded", "android"]}},
                }
                if ff:
                    opts["ffmpeg_location"] = ff
                if es_musica:
                    opts["postprocessors"] = [
                        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                is_url = query.startswith("http://") or query.startswith("https://")
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(query if is_url else f"ytsearch1:{query}", download=True)
                # yt_dlp con postprocessor puede devolver 'requested_downloads' con la ruta final
                titulo = (info or {}).get("title") or query[:40]
                # Log de archivo real para depuración
                try:
                    if is_url:
                        fpath = ydl.prepare_filename(info)
                        # Si es audio, el mp3 renombrado puede diferir
                        if es_musica:
                            fpath = os.path.splitext(fpath)[0] + ".mp3"
                        self.log(f"Descarga OK: {fpath} ({os.path.getsize(fpath) if os.path.exists(fpath) else 'no size'} bytes)")
                except Exception:
                    pass
                self._avisar(f"Descarga completada, señor: {titulo}. "
                             f"Está en Descargas\\JARVIS\\Videos.")
            except Exception as e:
                self.log(f"Descarga falló: {e}")
                self._avisar(f"Señor, no pude descargar «{query[:40]}»: {str(e)[:100]}")

        threading.Thread(target=_do, daemon=True).start()
        return f"Enseguida, señor. Descargando «{query[:50]}»..."

    # ── OCR: leer texto de pantalla / captura / imagen (winocr) ──────────────
    def _ocr(self, t: str):
        if not re.search(r"\bocr\b|(?:lee|leeme|leer|extrae|extraer|reconoce|reconocer)\s+(?:el\s+)?texto", t):
            return None
        if self.safe:
            return "(modo seguro: no ejecutaría OCR)"
        m_cap = re.search(r"(?:de\s+la\s+)?(?:ultima\s+|ultimo\s+)?captura", t)
        m_img = re.search(r"(?:de\s+la\s+)?imagen\s+(.+?)\s*$", t)
        es_pantalla = bool(re.search(r"pantalla|pantallazo|escritorio", t))

        def _origen():
            try:
                from PIL import ImageGrab
                from PIL import Image as PILImage
                if m_img:
                    ruta = m_img.group(1).strip().strip(".")
                    if not os.path.exists(ruta):
                        candidata = os.path.join(os.path.expanduser("~"), "Descargas", ruta)
                        if os.path.exists(candidata):
                            ruta = candidata
                    if not os.path.exists(ruta):
                        raise FileNotFoundError(ruta)
                    return PILImage.open(ruta)
                if m_cap:
                    caps = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Capturas")
                    ultima = None
                    if os.path.exists(caps):
                        for raiz, _, archivos in os.walk(caps):
                            for a in sorted(archivos):
                                if a.lower().endswith(".png"):
                                    ultima = os.path.join(raiz, a)
                    if ultima:
                        return PILImage.open(ultima)
                return ImageGrab.grab()
            except Exception:
                return None

        def _do():
            try:
                import winocr
                img = _origen()
                if img is None:
                    self._avisar("Señor, no encontré la imagen ni la captura para leer el texto.")
                    return
                res = winocr.recognize_pil_sync(img, "es")
                lineas = [ln.get("text", "") for ln in res.get("lines", []) if ln.get("text", "").strip()]
                texto = "\n".join(lineas) or res.get("text", "")
                if not texto:
                    self._avisar("Señor, no encontré texto legible en esa imagen.")
                    return
                self._avisar(f"Texto detectado, señor: {texto[:400]}")
            except Exception as e:
                self.log(f"OCR falló: {e}")
                self._avisar(f"Señor, no pude leer el texto: {str(e)[:100]}")

        threading.Thread(target=_do, daemon=True).start()
        return "Analizando el texto de la imagen, señor. Un momento por favor."

    # ── CONVERSOR DE UNIDADES Y DIVISAS ──────────────────────────────────────
    _UNIDADES = {
        "longitud": {"m": 1, "metro": 1, "metros": 1, "km": 1000, "kilometro": 1000, "kilometros": 1000,
                     "cm": 0.01, "centimetro": 0.01, "centimetros": 0.01, "mm": 0.001, "milimetro": 0.001,
                     "millas": 1609.344, "milla": 1609.344, "yardas": 0.9144, "yarda": 0.9144,
                     "pies": 0.3048, "pie": 0.3048, "pulgadas": 0.0254, "pulgada": 0.0254},
        "masa": {"kg": 1, "kilo": 1, "kilos": 1, "kilogramo": 1, "kilogramos": 1, "g": 0.001, "gramo": 0.001,
                 "gramos": 0.001, "mg": 1e-6, "miligramo": 1e-6, "miligramos": 1e-6,
                 "libras": 0.45359237, "libra": 0.45359237, "onzas": 0.0283495, "onza": 0.0283495,
                 "toneladas": 1000, "tonelada": 1000},
        "volumen": {"l": 1, "litro": 1, "litros": 1, "ml": 0.001, "mililitro": 0.001, "mililitros": 0.001,
                    "m3": 1000, "galones": 3.78541, "galon": 3.78541, "tazas": 0.24, "taza": 0.24},
        "velocidad": {"km/h": 1, "kilometros por hora": 1, "kmh": 1, "m/s": 3.6, "metros por segundo": 3.6,
                      "mph": 1.609344, "millas por hora": 1.609344, "nudos": 1.852, "nudo": 1.852},
        "datos": {"mb": 1, "megabyte": 1, "megabytes": 1, "gb": 1024, "gigabyte": 1024, "gigabytes": 1024,
                  "kb": 1 / 1024, "kilobyte": 1 / 1024, "kilobytes": 1 / 1024, "tb": 1024 * 1024,
                  "terabyte": 1024 * 1024, "terabytes": 1024 * 1024},
        "tiempo": {"segundos": 1, "segundo": 1, "seg": 1, "minutos": 60, "minuto": 60, "min": 60,
                   "horas": 3600, "hora": 3600, "h": 3600, "dias": 86400, "dia": 86400},
    }
    _DIVISAS = {
        "dolar": "USD", "dolares": "USD", "usd": "USD", "euro": "EUR", "euros": "EUR", "eur": "EUR",
        "libra": "GBP", "libras esterlinas": "GBP", "gbp": "GBP", "yen": "JPY", "yenes": "JPY",
        "jpy": "JPY", "peso": "MXN", "pesos": "MXN", "mxn": "MXN", "peso argentino": "ARS",
        "pesos argentinos": "ARS", "ars": "ARS", "real": "BRL", "reales": "BRL", "brl": "BRL",
        "peso chileno": "CLP", "clp": "CLP", "sol": "PEN", "soles": "PEN", "pen": "PEN",
        "peso colombiano": "COP", "cop": "COP", "bolivar": "VES", "bolivares": "VES",
    }
    _TASAS = {"USD": 1.0, "_ts": 0}

    @staticmethod
    def _tasa_divisa(desde: str, hasta: str) -> float:
        """Tasa actual desde->hasta con caché de 1 hora (open.er-api.com)."""
        import time as _time
        ahora = _time.time()
        if ahora - SkillsManager._TASAS.get("_ts", 0) > 3600:
            try:
                import urllib.request, json
                with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=8) as r:
                    d = json.loads(r.read().decode())
                if d.get("result") == "success":
                    SkillsManager._TASAS = {**d["rates"], "_ts": ahora}
            except Exception:
                pass
        t1 = SkillsManager._TASAS.get(desde)
        t2 = SkillsManager._TASAS.get(hasta)
        if not t1 or not t2:
            return 0.0
        return t2 / t1

    def _conversor(self, t: str):
        m = re.search(r"(?:convierte|convertir|pasa|pasar|transforma)\s+(\d+(?:[.,]\d+)?)\s*(.+?)\s+a\s+(.+?)\s*$", t)
        m2 = re.search(r"cuantos?\s+(.+?)\s+son\s+(\d+(?:[.,]\d+)?)\s+(.+?)\s*$", t)
        m3 = re.search(r"cuanto es\s+(\d+(?:[.,]\d+)?)\s+(.+?)\s+en\s+(.+?)\s*$", t)
        if not m and not m2 and not m3:
            return None
        if m:
            cantidad = float(m.group(1).replace(",", "."))
            origen, destino = m.group(2).strip(), m.group(3).strip()
        elif m2:
            destino, cantidad, origen = m2.group(1).strip(), float(m2.group(2).replace(",", ".")), m2.group(3).strip()
        else:
            cantidad, origen, destino = float(m3.group(1).replace(",", ".")), m3.group(2).strip(), m3.group(3).strip()
        origen = origen.rstrip(".")
        # Divisas
        cod_o = SkillsManager._DIVISAS.get(origen)
        cod_d = SkillsManager._DIVISAS.get(destino)
        if cod_o and cod_d:
            tasa = SkillsManager._tasa_divisa(cod_o, cod_d)
            if tasa:
                res = cantidad * tasa
                return (f"Señor, {cantidad:g} {origen} equivalen a {res:,.2f} {destino} "
                        f"al cambio actual.")
            return f"Señor, no pude obtener el cambio actual de {origen} a {destino}."
        # Unidades
        for cat, mapa in SkillsManager._UNIDADES.items():
            if origen in mapa and destino in mapa:
                res = cantidad * mapa[origen] / mapa[destino]
                return (f"Señor, {cantidad:g} {origen} son {res:,.4g} {destino}.")
        return None

    # ── ORGANIZAR DESCARGAS ──────────────────────────────────────────────────
    _CATEGORIAS = {
        "Imagenes": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic", ".tiff"),
        "Videos": (".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv"),
        "Musica": (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"),
        "Documentos": (".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx",
                       ".md", ".csv", ".rtf", ".epub"),
        "Instaladores": (".exe", ".msi", ".bat", ".cmd"),
        "Comprimidos": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"),
        "Codigo": (".py", ".js", ".html", ".css", ".json", ".xml", ".ino", ".c", ".cpp", ".java"),
    }

    def _organizar_descargas(self, t: str):
        if not re.search(r"(?:organiza|ordena|limpia|arregla)\s+(?:la\s+carpeta\s+de\s+)?(?:mis\s+|las\s+)?descargas\b", t):
            return None
        origen = os.path.join(os.path.expanduser("~"), "Descargas")
        if self.safe:
            return "(modo seguro: no movería archivos de Descargas)"
        try:
            movidos = {}
            for f in sorted(os.listdir(origen)):
                ruta = os.path.join(origen, f)
                if os.path.isdir(ruta):
                    continue
                ext = os.path.splitext(f)[1].lower()
                cat = next((c for c, exts in SkillsManager._CATEGORIAS.items() if ext in exts), "Otros")
                destino = os.path.join(origen, "Organizadas", cat)
                os.makedirs(destino, exist_ok=True)
                nueva = self._nuevo_nombre(destino, os.path.splitext(f)[0], ext=ext)
                os.replace(ruta, os.path.join(destino, nueva))
                movidos[cat] = movidos.get(cat, 0) + 1
            if not movidos:
                return "Señor, sus descargas ya están impecables: no había nada que organizar."
            detalle = ", ".join(f"{k}: {v}" for k, v in sorted(movidos.items()))
            return (f"Hecho, señor. Organicé {sum(movidos.values())} archivos en "
                    f"Descargas\\Organizadas ({detalle}).")
        except Exception as e:
            return f"Señor, no pude organizar las descargas: {str(e)[:100]}"

    # ── NOTICIAS DEL DÍA (RSS Google News) ───────────────────────────────────
    def _noticias(self, t: str):
        if re.search(r"de (mi|tu) (vida|familia)|noticias personales", t):
            return None
        if not re.search(r"(?:dame|muestra(?:me)?|lee|leeme|cuentame|dime|quiero|pasame|hay)\s+(?:las\s+|algunas\s+|ultimas\s+)?noticias|noticias\s+(?:del\s+dia|de\s+hoy|del\s+dia\s+de\s+hoy)", t):
            return None

        def _do():
            try:
                import urllib.request
                import xml.etree.ElementTree as ET
                url = "https://news.google.com/rss?hl=es-419&gl=MX&ceid=MX:es-419"
                with urllib.request.urlopen(url, timeout=10) as r:
                    datos = r.read(200000).decode("utf-8", "ignore")
                root = ET.fromstring(datos)
                items = []
                for it in root.iter("item"):
                    titulo = it.findtext("title", "").strip()
                    fuente = it.findtext("source", "").strip()
                    if titulo and ":" in titulo:
                        titulo, fuente2 = titulo.split(":", 1)
                        fuente = (fuente or fuente2).strip()
                    if titulo and titulo not in items:
                        items.append((titulo.strip(), fuente))
                    if len(items) >= 6:
                        break
                if not items:
                    self._avisar("Señor, no pude obtener las noticias en este momento.")
                    return
                msg = "Noticias del día, señor:\n" + "\n".join(
                    f"{i + 1}. {ti} ({fu or 'prensa'})" for i, (ti, fu) in enumerate(items))
                self._avisar(msg)
            except Exception as e:
                self.log(f"Noticias falló: {e}")
                self._avisar("Señor, no pude obtener las noticias en este momento.")

        threading.Thread(target=_do, daemon=True).start()
        return "Consultando las noticias del día, señor. Un momento por favor."

    # ── NAVEGADOR (control real de la página, PyAutoGUI) ────────────────────
    @staticmethod
    def _has_gui():
        try:
            import pyautogui  # noqa
            return True
        except Exception:
            return False

    def _navegador(self, t: str):
        # Navegar a una URL o buscar en una web concreta
        if re.search(r"abre.*pagina|navega (a|hasta)|ve a (la )?pagina|entra en (la )?pagina|abre.*web (de|del)", t):
            m = re.search(r"(?:pagina|web|sitio)\s+(?:de|del|del sitio)\s+(.+?)(?:\s*$)", t)
            url = m.group(1).strip() if m else None
            if not url:
                return None
            SITIOS = {
                "wikipedia": "https://es.wikipedia.org",
                "youtube": "https://www.youtube.com",
                "google": "https://www.google.com",
                "google maps": "https://www.google.com/maps",
                "maps": "https://www.google.com/maps",
                "gmail": "https://mail.google.com",
                "whatsapp": "https://web.whatsapp.com",
                "telegram": "https://web.telegram.org",
                "twitter": "https://twitter.com",
                "x": "https://x.com",
                "instagram": "https://www.instagram.com",
                "facebook": "https://www.facebook.com",
                "netflix": "https://www.netflix.com",
                "amazon": "https://www.amazon.es",
                "github": "https://github.com",
                "spotify": "https://open.spotify.com",
                "twitch": "https://www.twitch.tv",
                "reddit": "https://www.reddit.com",
            }
            url_low = url.lower()
            if url_low in SITIOS:
                url = SITIOS[url_low]
            elif " " not in url and "." not in url:
                url += ".com"
            if not url.startswith("http"):
                url = "https://" + url.replace(" ", "")
            subprocess.Popen(["start", "", url], shell=True)
            return f"Abriendo {url}, señor."
        # Búsqueda específica en web: "busca X en youtube" / "busca en youtube X"
        SITIOS = r"youtube|google maps|maps|wikipedia|amazon|github|google imágenes|google imagenes|twitter|x\b"
        m = re.search(r"busca\s+en\s+(" + SITIOS + r")\s+(.+)", t)
        if m:
            sitio, q = m.group(1), m.group(2).strip()
        else:
            m = re.search(r"busca\s+(.+?)\s+en\s+(" + SITIOS + r")", t)
            if m:
                q, sitio = m.group(1).strip(), m.group(2)
        if m:
            base = {"youtube": "https://www.youtube.com/results?search_query=",
                    "google maps": "https://www.google.com/maps/search/", "maps": "https://www.google.com/maps/search/",
                    "wikipedia": "https://es.wikipedia.org/w/index.php?search=",
                    "amazon": "https://www.amazon.es/s?k=",
                    "github": "https://github.com/search?q=",
                    "google imágenes": "https://www.google.com/search?tbm=isch&q=", "google imagenes": "https://www.google.com/search?tbm=isch&q=",
                    "twitter": "https://twitter.com/search?q=", "x": "https://twitter.com/search?q="}[sitio]
            # canal específico en YouTube: "busca X en youtube del canal Y"
            mc = re.search(r"(.+?)\s+(?:del canal|en el canal|del video del canal|de la canal)\s+(.+)$", q)
            if mc and sitio == "youtube":
                q = f"{mc.group(1).strip()} canal {mc.group(2).strip()}"
            import urllib.parse
            subprocess.Popen(["start", "", base + urllib.parse.quote(q)], shell=True)
            return f"Buscando «{q}» en {sitio}, señor."
        # Control directo del navegador con teclado/ratón
        if not self._has_gui():
            return None
        import pyautogui
        pyautogui.PAUSE = 0.15
        if re.search(r"recarga|refresca|actualiza la pagina", t):
            pyautogui.hotkey("ctrl", "r")
            return "Página recargada, señor."
        if re.search(r"vuelve atras|pagina anterior|ir atras", t):
            pyautogui.hotkey("alt", "left")
            return "Volviendo a la página anterior, señor."
        if re.search(r"pagina siguiente|ir adelante|avanza", t):
            pyautogui.hotkey("alt", "right")
            return "Avanzando a la página siguiente, señor."
        if re.search(r"baja la pagina|scroll abajo|mas abajo", t):
            pyautogui.scroll(-5)
            return "Bajando, señor."
        if re.search(r"sube la pagina|scroll arriba|mas arriba", t):
            pyautogui.scroll(5)
            return "Subiendo, señor."
        if re.search(r"nueva pestana|nueva pestaña|abre una pestana nueva", t):
            pyautogui.hotkey("ctrl", "t")
            return "Nueva pestaña abierta, señor."
        if re.search(r"cierra la pestana|cierra esta pestana|cierra la pestaña", t):
            pyautogui.hotkey("ctrl", "w")
            return "Pestaña cerrada, señor."
        if re.search(r"escribe (en la pagina|en el buscador|en la barra)\s+(.+)", t):
            m = re.search(r"escribe (?:en la pagina|en el buscador|en la barra)\s+(.+)", t)
            pyautogui.typewrite(m.group(1), interval=0.02)
            return "Escrito, señor."
        if re.search(r"pulsa enter|dale enter|presiona enter", t):
            pyautogui.press("enter")
            return "Enter pulsado, señor."
        return None

    # ── MÓVIL ANDROID (puente ADB, Sprint 2) ─────────────────────────────────
    @staticmethod
    def _adb_available() -> bool:
        try:
            subprocess.run(["adb", "version"], capture_output=True, timeout=5,
                           creationflags=0x08000000)
            return True
        except Exception:
            return False

    @staticmethod
    def _adb_devices() -> list:
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=8,
                               creationflags=0x08000000)
            lines = r.stdout.strip().splitlines()[1:]
            return [ln.split("\t")[0] for ln in lines if "device" in ln and "\t" in ln]
        except Exception:
            return []

    def _movil(self, t: str):
        if not re.search(r"telefono|teléfono|movil|móvil|celular|android|pantalla del telefono", t):
            return None
        # Frases que no son comandos móviles directos
        if re.search(r"abre|apaga el pc|clima|nota|musica", t):
            return None
        if not self._adb_available():
            return "Señor, el puente ADB no está disponible en este equipo."
        devices = self._adb_devices()
        if not devices:
            return ("Señor, no detecto ningún dispositivo Android conectado. "
                    "Conecte su teléfono por USB con depuración USB activada.")
        if re.search(r"bateria|batería|carga", t):
            r = subprocess.run(["adb", "shell", "dumpsys", "battery"], capture_output=True,
                               text=True, timeout=10, creationflags=0x08000000)
            for ln in r.stdout.splitlines():
                ln = ln.strip()
                if ln.startswith("level:"):
                    pct = ln.split(":")[1].strip()
                if ln.startswith("status:"):
                    status = ln.split(":")[1].strip()
            estado = {1: "descargando", 2: "cargando", 3: "cargada", 4: "desconectada"}.get(
                int(status) if str(status).isdigit() else 0, "desconocido")
            return f"Señor, su teléfono tiene {pct}% de batería y está {estado}."
        if re.search(r"bloquea|apaga la pantalla|pantalla apagada", t):
            subprocess.Popen(["adb", "shell", "input", "keyevent", "26"], creationflags=0x08000000)
            return "Pantalla del teléfono bloqueada, señor."
        if re.search(r"captura.*telefono|foto.*pantalla.*telefono|screenshot.*telefono", t):
            def _shot():
                try:
                    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = os.path.join(self._caps_dir, f"movil_{fecha}.png")
                    subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=open(path, "wb"),
                                   timeout=15, creationflags=0x08000000)
                    if self.notify:
                        self.notify(f"Captura del teléfono guardada, señor.")
                except Exception as e:
                    self.log(f"Captura móvil falló: {e}")
            threading.Thread(target=_shot, daemon=True).start()
            return "Tomando captura de su teléfono, señor."
        if re.search(r"despierta|desbloquea|prende la pantalla", t):
            subprocess.Popen(["adb", "shell", "input", "keyevent", "224"], creationflags=0x08000000)
            return "Despertando el teléfono, señor."
        if re.search(r"toca|abre.*(whatsapp|youtube|chrome|spotify) en el telefono", t):
            m = re.search(r"(whatsapp|youtube|chrome|spotify)", t)
            pkg = {"whatsapp": "com.whatsapp", "youtube": "com.google.android.youtube",
                   "chrome": "com.android.chrome", "spotify": "com.spotify.music"}[m.group(1)]
            subprocess.Popen(["adb", "shell", "monkey", "-p", pkg, "1"], creationflags=0x08000000)
            return f"Abriendo {m.group(1)} en su teléfono, señor."
        return None

    # ── RECORDATORIO ─────────────────────────────────────────────────────────
    def _recordatorio(self, t: str):
        if not re.search(r"recuerdame|recuérdame|recordame|recuérdame|avísame|avisame|no se me olvide", t):
            return None
        m = re.search(r"(?:recuerdame|recordame|avisame|no se me olvide)\s+(?:que\s+)?(.+?)\s*(?:a las|para las)\s*(\d{1,2})[:.](\d{2})", t)
        if not m:
            return None
        mo = re.search(r"(?:recuerdame|recordame|avisame|no se me olvide)\s+(?:que\s+)?(.+?)\s*(?:a las|para las)\s*(\d{1,2})[:.](\d{2})", self._orig_lower)
        texto = (mo.group(1) if mo else m.group(1)).strip()
        hh, mm = int(m.group(2)), int(m.group(3))
        if hh > 23 or mm > 59 or not texto:
            return None
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        secs = (target - now).total_seconds()
        if self.remember:
            self.remember(texto, f"{hh:02d}:{mm:02d}")
        def _done():
            self._avisar(f"Señor, recordatorio: {texto}.")
            if not self.notify:
                try:
                    import winsound
                    winsound.Beep(1000, 1200)
                except Exception:
                    pass
        tmr = threading.Timer(secs, _done)
        tmr.daemon = True
        tmr.start()
        return f"Recordado, señor. Le avisaré a las {hh:02d}:{mm:02d} sobre «{texto[:80]}»."

    # ── ALARMA ───────────────────────────────────────────────────────────────
    def _alarma(self, t: str):
        m = re.search(r"alarma(?: a| para| de)?\s*(?:las\s*)?(\d{1,2})[:.](\d{2})", t)
        if not m:
            return None
        hh, mm = int(m.group(1)), int(m.group(2))
        if hh > 23 or mm > 59:
            return None
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        secs = (target - now).total_seconds()
        def _done():
            self._avisar(f"Señor, son las {hh:02d}:{mm:02d}. Su alarma está sonando.")
            if not self.notify:
                try:
                    import winsound
                    winsound.Beep(1200, 1800)
                except Exception:
                    pass
        t = threading.Timer(secs, _done)
        t.daemon = True
        t.start()
        return f"Alarma a las {hh:02d}:{mm:02d}, señor. Le avisaré puntualmente."

    # ── BLOQUEAR / APAGAR / REINICIAR ────────────────────────────────────────
    def _bloquear(self, t: str):
        if re.search(r"bloquea|bloquear (la pantalla|el pc|el equipo|la sesion)", t):
            if self.safe:
                return "Bloqueando el equipo, señor. (modo seguro: no ejecutado)"
            subprocess.Popen("rundll32.exe user32.dll,LockWorkStation")
            return "Bloqueando el equipo, señor. Le espero a su regreso."
        return None

    def _cancela_apagado(self, t: str):
        if re.search(r"cancela|cancelar|deten.*apagado|no apagues|quita el apagado", t):
            subprocess.Popen("shutdown /a", shell=True, creationflags=0x08000000)
            return "Apagado cancelado, señor. El equipo se queda encendido."
        return None

    def _apagar(self, t: str):
        if re.search(r"apaga (el pc|el equipo|la computadora|el ordenador|el sistema)|apaga el", t):
            if self.safe:
                return "Apagando el equipo en 30 segundos, señor. (modo seguro: no ejecutado)"
            subprocess.Popen("shutdown /s /t 30 /c \"Jarvis apagando por orden del señor\"", shell=True, creationflags=0x08000000)
            return ("Apagando el equipo en 30 segundos, señor. "
                    "Si cambia de idea, dígame «cancela el apagado».")
        return None

    def _reiniciar(self, t: str):
        if re.search(r"reinicia|reiniciar (el pc|el equipo|la computadora|el ordenador)", t):
            if self.safe:
                return "Reiniciando el equipo en 30 segundos, señor. (modo seguro: no ejecutado)"
            subprocess.Popen("shutdown /r /t 30 /c \"Jarvis reiniciando por orden del señor\"", shell=True, creationflags=0x08000000)
            return ("Reiniciando el equipo en 30 segundos, señor. "
                    "Dígame «cancela el apagado» si desea detenerlo.")
        return None

    # ── BATERÍA ──────────────────────────────────────────────────────────────
    def _bateria(self, t: str):
        if not re.search(r"bateria|batería|nivel de carga", t):
            return None
        try:
            import psutil
            b = psutil.sensors_battery()
            if b is None:
                return "Señor, este equipo no tiene batería: funciona con corriente."
            estado = "cargando" if b.power_plugged else "con batería"
            return (f"Señor, la batería está al {b.percent}% y el equipo {estado}.")
        except Exception:
            return "Señor, no pude leer el estado de la batería."

    # ── HORA / FECHA ─────────────────────────────────────────────────────────
    def _hora_fecha(self, t: str):
        if re.search(r"que hora es|hora es|dime la hora|la hora actual|hora exacta", t):
            return f"Son las {datetime.now().strftime('%H:%M')} exactamente, señor."
        if re.search(r"que dia es|que dia|fecha de hoy|hoy es|dime la fecha|a que dia", t):
            now = datetime.now()
            return f"Hoy es {DIA_ES[now.weekday()]} {now.day} de {MES_ES[now.month - 1]} de {now.year}, señor."

    # ═══════════════════════════════════════════════════════════════════════════
    # SKILLS AVANZADAS (IA-PARA-TODOS)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── WEB SCRAPING (BeautifulSoup + Ollama) ────────────────────────────────
    def _scrape_web(self, t: str):
        if not re.search(r"extrae|scrape|raspa|lee (?:el )?(?:contenido|texto|info) de|"
                         r"que (?:dice|hay|pone|contiene) (?:esta|esa|la) (?:pag|web|url|pagina|página)",
                         t):
            return None
        m = re.search(r"(https?://[^\s<>\"']+)", self._orig)
        if not m:
            return None
        url = m.group(1)
        if self.safe:
            return f"(modo seguro: no haría scraping de {url[:60]})"
        def _do():
            try:
                from bs4 import BeautifulSoup
                import requests as _req
                resp = _req.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)[:3000]
                if not text:
                    self._avisar(f"Señor, no encontré contenido legible en {url[:60]}.")
                    return
                sys_prompt = "Eres un asistente experto. Resume y analiza el siguiente contenido web de forma clara y concisa."
                user_prompt = f"Analiza este contenido web:\n\n{text[:2500]}"
                import requests as _req2
                resp_llm = _req2.post(jarvis_config.OLLAMA_URL, json={
                    "model": "llama3.2:1b", "system": sys_prompt,
                    "prompt": user_prompt, "stream": False,
                    "options": {"num_predict": 512}
                }, timeout=45)
                resultado = resp_llm.json().get("response", "No pude analizar el contenido.")
                self._avisar(f"Análisis web completado, señor. {resultado[:300]}")
            except Exception as e:
                self.log(f"Scraping error: {e}")
                self._avisar(f"Señor, tuve un error al analizar la web: {str(e)[:100]}")
        threading.Thread(target=_do, daemon=True).start()
        return f"Analizando el contenido de la web, señor. Un momento."

    # ── DATOS BURSÁTILS (YFinance) ──────────────────────────────────────────
    def _stock_data(self, t: str):
        if not re.search(r"(?:accion|acción|acciones|stock|bolsa|cotiza|cotizacion|cotización)\s+"
                         r"(?:de\s+)?([A-Za-z]{1,5})", t):
            return None
        m = re.search(r"(?:accion|acción|acciones|stock|bolsa|cotiza|cotizacion|cotización)\s+"
                      r"(?:de\s+)?(?P<ticker>[A-Za-z]{1,5})", t)
        if not m:
            return None
        ticker = m.group("ticker").upper()
        if self.safe:
            return f"(modo seguro: no consultaría datos de {ticker})"
        def _do():
            try:
                import yfinance as yf
                stock = yf.Ticker(ticker)
                info = stock.info
                precio = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose", "?")
                cambio = info.get("regularMarketChangePercent", 0)
                nombre = info.get("shortName", ticker)
                volumen = info.get("volume", 0)
                max_dia = info.get("dayHigh", "?")
                min_dia = info.get("dayLow", "?")
                icono = "▲" if cambio >= 0 else "▼"
                resumen = (
                    f"{icono} {nombre} ({ticker}): ${precio} | "
                    f"Cambio: {cambio:+.2f}% | "
                    f"Max: ${max_dia} | Min: ${min_dia} | "
                    f"Vol: {volumen:,}"
                )
                self._avisar(resumen)
            except Exception as e:
                self.log(f"Stock error: {e}")
                self._avisar(f"Señor, no pude obtener datos de {ticker}. Verifique el símbolo.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Consultando datos de {ticker}, señor. Un momento."

    # ── NOTICIAS INTELIGENTES (DuckDuckGo + Llama 3) ─────────────────────────
    def _noticias_buscar(self, t: str):
        m = re.search(r"(?:noticias?|news|actualidad)\s+(?:de|sobre|del?)\s+(.+)$", t)
        if not m:
            return None
        tema = m.group(1).strip().strip(".")
        if len(tema) < 3:
            return None
        if self.safe:
            return f"(modo seguro: no buscaria noticias sobre {tema})"
        def _do():
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddg:
                    results = ddg.text(f"{tema} noticias recientes 2026", max_results=5)
                if not results:
                    self._avisar(f"Señor, no encontre noticias recientes sobre {tema}.")
                    return
                noticias = []
                for r in results[:5]:
                    noticias.append(f"- {r.get('title', '?')}: {r.get('body', '')[:120]}")
                raw = "\n".join(noticias)
                sys_prompt = "Eres un analista de noticias experto. Resume las noticias en un parrafo conciso y claro."
                user_prompt = f"Resume estas noticias sobre {tema}:\n\n{raw}"
                import requests as _req
                resp = _req.post(jarvis_config.OLLAMA_URL, json={
                    "model": "llama3.2:1b", "system": sys_prompt,
                    "prompt": user_prompt, "stream": False,
                    "options": {"num_predict": 300}
                }, timeout=45)
                resumen = resp.json().get("response", "No pude resumir las noticias.")
                self._avisar(f"Noticias de {tema}: {resumen[:400]}")
            except Exception as e:
                self.log(f"Noticias buscar error: {e}")
                self._avisar(f"Señor, no pude buscar noticias sobre {tema}.")
        threading.Thread(target=_do, daemon=True).start()
        return f"Buscando noticias sobre {tema}, señor. Un momento."

    # ── CHAT CON PDF (embedchain + Ollama) ───────────────────────────────────
    def _pdf_chat(self, t: str):
        if not re.search(r"(?:pregunta|habla|chatea|analiza|resume|resume) (?:al|a|con|el|este)? "
                         r"pdf|qué (?:dice|contiene|opina)|cuales son las|resumen del pdf", t):
            return None
        if self.safe:
            return "(modo seguro: no procesaría PDFs)"
        def _do():
            try:
                pdfs_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS")
                pdfs = []
                for root, _, files in os.walk(pdfs_dir):
                    for f in files:
                        if f.lower().endswith(".pdf"):
                            pdfs.append(os.path.join(root, f))
                if not pdfs:
                    self._avisar("Señor, no encontré archivos PDF en su carpeta de JARVIS.")
                    return
                pdf_path = max(pdfs, key=os.path.getmtime)
                self._avisar(f"Analizando el PDF más reciente: {os.path.basename(pdf_path)}. Un momento.")
                try:
                    import fitz
                    doc = fitz.open(pdf_path)
                    texto = ""
                    for i, page in enumerate(doc):
                        texto += page.get_text()
                        if len(texto) > 4000:
                            break
                    doc.close()
                except ImportError:
                    self._avisar("Señor, necesito PyMuPDF para leer PDFs. Instálelo con: pip install PyMuPDF")
                    return
                sys_prompt = ("Eres un asistente experto en análisis de documentos. "
                              "Analiza el siguiente contenido PDF y responde de forma clara y detallada.")
                user_prompt = f"Analiza este contenido PDF:\n\n{texto[:3500]}"
                import requests as _req
                resp = _req.post(jarvis_config.OLLAMA_URL, json={
                    "model": "llama3.2:1b", "system": sys_prompt,
                    "prompt": user_prompt, "stream": False,
                    "options": {"num_predict": 600}
                }, timeout=60)
                resultado = resp.json().get("response", "No pude analizar el PDF.")
                self._avisar(f"Análisis del PDF: {resultado[:400]}")
            except Exception as e:
                self.log(f"PDF chat error: {e}")
                self._avisar(f"Señor, tuve un error al analizar el PDF: {str(e)[:100]}")
        threading.Thread(target=_do, daemon=True).start()
        return "Analizando el PDF más reciente, señor. Un momento."

    # ── RESUMEN INTELIGENTE DE WEB (URL + Ollama) ───────────────────────────
    def _resumen_url(self, t: str):
        if not re.search(r"(?:resume|resumir|resumen de|que (?:dice|hay)|analiza)\s+(https?://[^\s<>\"']+)", t):
            return None
        m = re.search(r"(https?://[^\s<>\"']+)", self._orig)
        if not m:
            return None
        url = m.group(1)
        if self.safe:
            return f"(modo seguro: no resumiría {url[:60]})"
        def _do():
            try:
                from bs4 import BeautifulSoup
                import requests as _req
                resp = _req.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)[:3000]
                if not text:
                    self._avisar(f"Señor, no encontré contenido en {url[:60]}.")
                    return
                sys_prompt = "Resume el siguiente contenido web en un párrafo claro y conciso. Enfócate en los puntos principales."
                user_prompt = f"Resume este contenido:\n\n{text[:2500]}"
                import requests as _req2
                resp_llm = _req2.post(jarvis_config.OLLAMA_URL, json={
                    "model": "llama3.2:1b", "system": sys_prompt,
                    "prompt": user_prompt, "stream": False,
                    "options": {"num_predict": 400}
                }, timeout=45)
                resultado = resp_llm.json().get("response", "No pude resumir el contenido.")
                self._avisar(f"Resumen: {resultado[:400]}")
            except Exception as e:
                self.log(f"Resumen URL error: {e}")
                self._avisar(f"Señor, no pude resumir la URL: {str(e)[:100]}")
        threading.Thread(target=_do, daemon=True).start()
        return f"Resumiendo el contenido de la web, señor. Un momento."

    # ── REFRIGERACIÓN ────────────────────────────────────────────────────────
    def _refrigeracion(self, t: str):
        if not re.search(r"(refrigeraci[oó]n|enfriar|ventilador|cooling|bajar temperatura|bajar temp|caliente|overheat|fresca|fan max|máx.*ventilador)", t):
            return None
        if self.safe:
            return "(modo seguro: no activaría la refrigeración)"

        # Detectar si es parar/detener
        if re.search(r"(parar|detener|stop|cancelar|restaurar|volver|normal)", t):
            try:
                import jarvis_cooling
                jarvis_cooling.stop_cooling()
                return "Ventiladores restaurados a su velocidad normal, señor."
            except Exception as e:
                return f"No pude detener la refrigeración: {str(e)[:80]}"

        # Detectar si quiere ver estado
        if re.search(r"(estado|status|temperatura|temp|cu[aá]nto)", t):
            try:
                import jarvis_cooling
                status = jarvis_cooling.get_status()
                if not status["temps"]:
                    return "No puedo leer las temperaturas ahora mismo, señor. LibreHardwareMonitor puede no estar activo."
                lines = ["Estado de refrigeración:"]
                for name, info in status["temps"].items():
                    lines.append(f"  {name}: {info['value']:.0f}°C")
                if status["controls"]:
                    for name, info in status["controls"].items():
                        lines.append(f"  Ventilador {name}: {info['value']:.0f}%")
                lines.append(f"  Ciclo activo: {'Sí' if status['active'] else 'No'}")
                return "\n".join(lines)
            except Exception as e:
                return f"No pude obtener el estado: {str(e)[:80]}"

        # Activar refrigeración máxima por 5 minutos
        def _do():
            try:
                import jarvis_cooling
                def _on_progress(cpu_temp, elapsed, remaining):
                    mins, secs = divmod(remaining, 60)
                    if cpu_temp is not None:
                        self._avisar(f"Refrigeración activa. CPU: {cpu_temp:.0f}°C. Quedan {mins}:{secs:02d}.")
                    else:
                        self._avisar(f"Refrigeración activa. Quedan {mins}:{secs:02d}.")

                ok, info = jarvis_cooling.start_cooling(callback=_on_progress)
                if ok:
                    if isinstance(info, dict):
                        temps = info.get("temps", {})
                        controls = info.get("controls", {})
                        cpu_temp = "desconocida"
                        for name, data in temps.items():
                            if "cpu" in name.lower() or "package" in name.lower():
                                cpu_temp = f"{data['value']:.0f}°C"
                                break
                        fan_count = len(controls)
                        self._avisar(
                            f"Ventiladores al máximo por 5 minutos. "
                            f"CPU: {cpu_temp}. {fan_count} ventilador(es) controlados. "
                            f"Se restaurarán automáticamente."
                        )
                    else:
                        self._avisar(f"Refrigeración activada: {info}")
                else:
                    self._avisar(f"No pude activar la refrigeración: {info}")
            except Exception as e:
                self.log(f"Refrigeración error: {e}")
                self._avisar(f"Error en refrigeración: {str(e)[:120]}")

        threading.Thread(target=_do, daemon=True).start()
        return "Activando refrigeración máxima, señor. Los ventiladores irán al 100% por 5 minutos."