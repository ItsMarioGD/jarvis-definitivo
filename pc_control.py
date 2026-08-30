#!/usr/bin/env python3
"""
pc_control.py - Control total del PC para Jarvis (Sprint "Más poder")
=====================================================================
Módulo de poder del sistema. Se consulta DESPUÉS de jarvis_skills (las
habilidades simples conservan prioridad) y ANTES del LLM.

Ámbitos:
  A. Sistema  : apagado/reinicio programado ("en X minutos", "a las HH:MM"),
                suspender, hibernar, cerrar sesión
  B. UI       : ventanas (listar/cerrar/minimizar/maximizar/mover), ratón y
                teclado (clic, arrastrar, scroll, escribir, atajos), macros
  C. Archivos : mover/renombrar en lote, ZIP, búsqueda profunda, copias de
                seguridad, limpieza de temporales
  D. Profundo : instalar/desinstalar (winget), servicios de Windows,
                variables de entorno, registro (lectura + escritura acotada)
  E. Tareas   : planificador interno (diarias/semanales/una vez/arranque)
                con ejecución en hilo de fondo

Poder total:
  * JARVIS ejecuta toda orden al instante, sin modo administrador, sin
    confirmaciones y sin listas de acciones prohibidas.
  * El parámetro interno `safe` solo existe como interruptor de pruebas
    (nunca se activa en producción) para no apagar el equipo durante tests.
"""
import os
import re
import shutil
import subprocess
import threading
import time
import sqlite3
import ctypes
import unicodedata
from datetime import datetime, timedelta

# ── aplicaciones conocidas → IDs winget ──────────────────────────────────────
WINGET_MAP = {
    "chrome": "Google.Chrome", "google chrome": "Google.Chrome",
    "firefox": "Mozilla.Firefox", "spotify": "Spotify.Spotify",
    "vscode": "Microsoft.VisualStudioCode", "visual studio code": "Microsoft.VisualStudioCode",
    "discord": "Discord.Discord", "steam": "Valve.Steam",
    "telegram": "Telegram.TelegramDesktop", "whatsapp": "WhatsApp.WhatsApp",
    "7zip": "7zip.7zip", "vlc": "VideoLAN.VLC", "vlc media player": "VideoLAN.VLC",
    "obsidian": "Obsidian.Obsidian", "blender": "BlenderFoundation.Blender",
    "python": "Python.Python.3.14", "git": "Git.Git",
    "notepad++": "Notepad++.Notepad++", "obs": "OBSProject.OBSStudio",
    "audacity": "Audacity.Audacity", "paint.net": "dotPDN.PaintDotNet",
    "teamviewer": "TeamViewer.TeamViewer", "zoom": "Zoom.Zoom",
    "libreoffice": "TheDocumentFoundation.LibreOffice",
    "powershell": "Microsoft.PowerShell", "terminal de windows": "Microsoft.WindowsTerminal",
    "winrar": "RARLab.WinRAR", "postman": "Postman.Postman",
    "figma": "Figma.Figma", "notion": "Notion.Notion", "gimp": "GIMP.GIMP",
    "audacity": "Audacity.Audacity",
}


def _norm(s: str) -> str:
    """Minúsculas y sin acentos para matcheo robusto."""
    n = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in n if unicodedata.category(c) != "Mn")


class PCControl:
    """Despachador de control total del PC. handle(text) -> str | None"""

    def __init__(self, log=print, notify=None, get_pref=None, set_pref=None, safe=False):
        self.log = log
        self.notify = notify
        self._get_pref = get_pref
        self._set_pref = set_pref
        self.safe = safe  # solo interruptor interno de pruebas; producción = False
        self._macros_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Macros")
        self._backup_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Backups")
        os.makedirs(self._macros_dir, exist_ok=True)
        os.makedirs(self._backup_dir, exist_ok=True)
        self._db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_memory.db")
        self._db_lock = threading.RLock()
        self._init_tasks_db()
        # planificador de tareas en segundo plano
        self._scheduler_stop = threading.Event()
        self._scheduler = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler.start()
        self._winget = None  # caché de disponibilidad

    # ── utilidades ───────────────────────────────────────────────────────────
    def _dbconn(self):
        c = sqlite3.connect(self._db, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init_tasks_db(self):
        with self._db_lock, self._dbconn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS pc_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                accion TEXT NOT NULL,
                hora TEXT,             -- HH:MM para tareas diarias/semanales
                dia INTEGER,           -- 0=lunes..6=domingo (o NULL = diaria)
                fecha TEXT,            -- YYYY-MM-DD para tareas de una vez
                activo INTEGER DEFAULT 1,
                ultima_ejec TEXT,
                creada TEXT)""")

    def _modo_admin(self) -> bool:
        # Poder total permanente: siempre True (sin barreras)
        return True

    # ── DESPACHADOR PRINCIPAL ────────────────────────────────────────────────
    def handle(self, text: str):
        t = _norm(text)
        if not t:
            return None

        # 1) estado de poder (preguntas sobre modo admin / permisos)
        r = self._admin_mode(t)
        if r:
            return r

        # 2) ámbitos (A→E), primero el planificador de tareas
        for fn in (self._tareas, self._youtube, self._rutinas, self._arranque,
                   self._sistema, self._ui, self._archivos, self._profundo):
            r = fn(t)
            if r:
                return r
        return None

    # ── MODO ADMINISTRADOR ───────────────────────────────────────────────────
    def _admin_mode(self, t: str):
        # Sin barreras: cualquier referencia al modo admin responde poder total
        if re.search(r"modo admin|modo administrador|permisos de administrador|"
                     r"que modo (tengo|estoy)|tengo permisos|estas en modo admin", t):
            return "Señor, mi poder es total en todo momento: sin modo seguro, sin confirmaciones y sin restricciones."
        return None

    # ── BÚSQUEDA EN YOUTUBE CON CANAL ────────────────────────────────────────
    def _youtube(self, t: str):
        # "busca en youtube X del canal Y" / "video X de Y" / "en el canal Y"
        if "youtube" not in t and "yt" != t:
            return None
        m = re.search(r"busca(?: en youtube)?\s+(.+?)\s+(?:del canal|en el canal|de la canal|del video del canal)\s+(.+)$", t)
        if m:
            video, canal = m.group(1).strip(), m.group(2).strip()
            import urllib.parse
            query = urllib.parse.quote(f"{video} canal {canal}")
            subprocess.Popen(f"start https://www.youtube.com/results?search_query={query}",
                             shell=True, creationflags=0x08000000)
            return f"Buscando «{video}» en el canal «{canal}», señor. Abriendo YouTube."
        # "abre el canal Y en youtube" / "busca el canal Y"
        m = re.search(r"(?:abre|busca)\s+(?:el\s+)?canal\s+(.+?)(?:\s+en\s+youtube)?$", t)
        if m:
            canal = m.group(1).strip().rstrip(".")
            import urllib.parse
            query = urllib.parse.quote(f"canal {canal}")
            subprocess.Popen(f"start https://www.youtube.com/results?search_query={query}",
                             shell=True, creationflags=0x08000000)
            return f"Abriendo el canal «{canal}» en YouTube, señor."
        return None

    # ── RUTINAS DEL USUARIO (patrones de trabajo) ────────────────────────────
    def _rutinas(self, t: str):
        if not re.search(r"rutinas|patrones|patrones de trabajo|que hago (cada|habitualmente)|detecta mis", t):
            return None
        db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_memory.db")
        try:
            import sqlite3
            with sqlite3.connect(db, timeout=10) as c:
                rows = c.execute(
                    "SELECT ts, usuario FROM cog_interactions ORDER BY ts DESC LIMIT 500").fetchall()
            if len(rows) < 10:
                return ("Señor, aún no tengo suficientes datos para detectar sus rutinas. "
                        "Siga conversando conmigo y pronto las reconoceré.")
            # agrupar por franja horaria del día
            franjas = {"madrugada (0-6)": {}, "mañana (6-12)": {},
                       "tarde (12-18)": {}, "noche (18-24)": {}}
            for ts, texto in rows:
                from datetime import datetime
                h = datetime.fromtimestamp(ts).hour
                franja = ("madrugada (0-6)" if h < 6 else "mañana (6-12)"
                          if h < 12 else "tarde (12-18)" if h < 18 else "noche (18-24)")
                # extraer acción típica del texto
                accion = None
                mm = re.search(r"(?:abre|abrir|lanza)\s+(?:(?:la|el|un|una|mi|su|tu|este|esta)\s+)?(\w+)", _norm(texto))
                if mm:
                    accion = f"abrir {mm.group(1)}"
                mm = re.search(r"(?:busca|buscar)\s+", _norm(texto))
                if mm:
                    accion = "búsquedas web"
                mm = re.search(r"(?:escribele|manda un whatsapp|correo)", _norm(texto))
                if mm:
                    accion = "mensajes"
                if accion:
                    franjas[franja][accion] = franjas[franja].get(accion, 0) + 1
            # top por franja con datos
            detectadas = []
            for franja, acciones in franjas.items():
                if acciones:
                    top = max(acciones, key=acciones.get)
                    detectadas.append((franja, top, acciones[top]))
            if not detectadas:
                return ("Señor, no he detectado patrones claros todavía. "
                        "Dígame cosas como «abre chrome» en sus horarios habituales y los aprenderé.")
            resumen = "; ".join(f"{f}: {a} ({n} veces)" for f, a, n in detectadas[:3])
            return (f"Señor, detecté sus rutinas: {resumen}. "
                    f"Si quiere, dígame «crea una tarea que {detectadas[0][1]} a las 9» y la programo.")
        except Exception as e:
            return f"Señor, no pude analizar mis registros: {e}"

    # ── ARRANQUE AUTOMÁTICO DEL ASISTENTE ────────────────────────────────────
    def _arranque(self, t: str):
        if re.search(r"(?<![a-z])activa (el )?arranque automatico|que jarvis (se )?arranque|inicia con el pc|inicie con el pc|ejecuta al encender|que jarvis se ejecute al encender", t):
            startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                   "Start Menu", "Programs", "Startup")
            proyecto = os.path.dirname(os.path.abspath(__file__))
            vbs = os.path.join(startup, "jarvis_arranque.vbs")
            pythonw = r"C:\Python314\pythonw.exe"
            chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            if not os.path.exists(chrome):
                chrome = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            if not os.path.exists(chrome):
                chrome = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            contenido = (
                'Set sh = CreateObject("WScript.Shell")\r\n'
                f'sh.Run "{pythonw} ""{proyecto}\\jarvis_mcp_server.py"" --http", 0, False\r\n'
                f'sh.Run "{pythonw} ""{proyecto}\\web_interface\\app.py""", 0, False\r\n'
                'WScript.Sleep 7000\r\n'
                f'sh.Run ""{chrome}"" http://127.0.0.1:5000/pair", 1, False\r\n'
            )
            if not self.safe:
                with open(vbs, "w", encoding="utf-8") as f:
                    f.write(contenido)
            if self._set_pref:
                self._set_pref("saludar_al_arranque", "1")
            return ("Arranque automático activado, señor. Al encender el PC me "
                    "levantaré, abriré el código QR de emparejamiento y le saludaré "
                    "listo para trabajar.")
        if re.search(r"desactiva (el )?arranque automatico|que jarvis no (se )?arranque|no se inicie con el pc|quita el arranque", t):
            startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                   "Start Menu", "Programs", "Startup")
            vbs = os.path.join(startup, "jarvis_arranque.vbs")
            if not self.safe and os.path.exists(vbs):
                os.remove(vbs)
            if self._set_pref:
                self._set_pref("saludar_al_arranque", "0")
            return "Arranque automático desactivado, señor. Solo me despertaré cuando usted me llame."
        return None

    # ── A. SISTEMA (energía programada, suspensión, sesión) ──────────────────
    def _sistema(self, t: str):
        # apagado/reinicio retardado: "apaga el pc en 5 minutos" / "a las 23:00"
        m = re.search(r"apaga[^\n]*?(?:en|dentro de)\s*(\d+)\s*(minuto|min|segundo|seg|hora|h)", t)
        m2 = re.search(r"(?:apaga|reinicia)[^\n]*?a las\s*(\d{1,2})[:.]?(\d{2})", t)
        if m or m2:
            if m:
                n = int(m.group(1))
                unidad = m.group(2)
                seg = n * (60 if unidad.startswith("min") else (1 if unidad.startswith("seg") else 3600))
                cmds = {"apaga": "shutdown /s /t", "reinicia": "shutdown /r /t"}
                modo = "apaga" if "apaga" in t else "reinicia"
                if self.safe:
                    return f"{'Apagaré' if modo == 'apaga' else 'Reiniciaré'} el equipo en {n} {unidad}(s), señor. (modo seguro: no ejecutado)"
                subprocess.Popen(f"{cmds[modo]} {seg} /c \"Jarvis por orden del señor\"",
                                 shell=True, creationflags=0x08000000)
                return f"{'Apagaré' if modo == 'apaga' else 'Reiniciaré'} el equipo en {n} {unidad}(s), señor. Dígame «cancela el apagado» si cambia de idea."
            if m2:
                hh, mm = int(m2.group(1)), int(m2.group(2))
                ahora = datetime.now()
                objetivo = ahora.replace(hour=hh, minute=mm, second=0)
                if objetivo <= ahora:
                    objetivo += timedelta(days=1)
                seg = int((objetivo - ahora).total_seconds())
                if self.safe:
                    return f"Equipo programado para las {hh:02d}:{mm:02d}, señor. (modo seguro: no ejecutado)"
                subprocess.Popen(f"shutdown /s /t {seg} /c \"Jarvis apagado programado\"",
                                 shell=True, creationflags=0x08000000)
                return f"Apagaré el equipo a las {hh:02d}:{mm:02d}, señor. Dígame «cancela el apagado» si cambia de idea."
        # suspender / hibernar / cerrar sesión (poder total: ejecución inmediata)
        if re.search(r"suspende (el pc|el equipo|la computadora)|ponlo a dormir|suspender el", t):
            if self.safe:
                return "Equipo suspendido, señor. (modo seguro: no ejecutado)"
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                             shell=True, creationflags=0x08000000)
            return "Suspendiendo el equipo, señor. Hasta pronto."
        if re.search(r"hiberna (el pc|el equipo)|hibernacion", t):
            if self.safe:
                return "Equipo hibernado, señor. (modo seguro: no ejecutado)"
            subprocess.Popen("shutdown /h", shell=True, creationflags=0x08000000)
            return "Hibernando el equipo, señor. Lo reanudaré a su regreso."
        if re.search(r"cierra (la )?sesion|cerrar sesion|cerrar la sesion", t):
            if self.safe:
                return "Sesión cerrada, señor. (modo seguro: no ejecutado)"
            subprocess.Popen("shutdown /l", shell=True, creationflags=0x08000000)
            return "Cerrando la sesión, señor. Sus programas quedarán en espera."
        return None

    # ── B. UI: VENTANAS + RATÓN/TECLADO + MACROS ─────────────────────────────
    @staticmethod
    def _hwnds():
        """Ventanas visibles de primer nivel: [(titulo, hwnd)]"""
        import ctypes
        user32 = ctypes.windll.user32
        ventanas = []
        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, 512)
                if buf.value.strip():
                    ventanas.append((buf.value, int(hwnd)))
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return ventanas

    def _buscar_ventana(self, nombre):
        nombre = _norm(nombre)
        for titulo, hwnd in self._hwnds():
            if nombre in _norm(titulo):
                return titulo, hwnd
        return None, None

    def _ui(self, t: str):
        # ── ventanas ──
        if re.search(r"que ventanas (hay|estan abiertas|tienes abiertas)|lista las ventanas|ventanas abiertas", t):
            v = self._hwnds()
            if not v:
                return "No hay ventanas visibles, señor."
            nombres = ", ".join(x for x, _ in v[:12])
            return f"Ventanas abiertas, señor: {nombres}."
        m = re.search(r"(?:cierra|minimiza|maximiza|restaura|mueve)\s+(?:la\s+|esta\s+)?ventana(?: de| del| llamada| titulada| del programa| de la aplicacion)?\s+(.+)", t)
        if m:
            titulo, hwnd = self._buscar_ventana(m.group(1))
            if not hwnd:
                return f"Señor, no encontré una ventana llamada «{m.group(1).strip()}»."
            if self.safe:
                return f"(modo seguro: no manipularía la ventana «{titulo}»)"
            user32 = ctypes.windll.user32
            if "cierra" in t:
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                return f"Cerrando la ventana «{titulo}», señor."
            if "minimiza" in t:
                user32.ShowWindow(hwnd, 6)
                return f"Ventana «{titulo}» minimizada, señor."
            if "maximiza" in t:
                user32.ShowWindow(hwnd, 3)
                return f"Ventana «{titulo}» maximizada, señor."
            if "restaura" in t:
                user32.ShowWindow(hwnd, 9)
                return f"Ventana «{titulo}» restaurada, señor."
            mm = re.search(r"mueve[^\n]*?(?:a|hacia)\s*\(?\s*(\d+)\s*[, ]\s*(\d+)", t)
            if mm:
                x, y = int(mm.group(1)), int(mm.group(2))
                user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001 | 0x0004)  # NOSIZE|NOZORDER
                return f"Ventana «{titulo}» movida a ({x}, {y}), señor."
            return f"Señor, entendí la ventana «{titulo}» pero no la acción."
        if re.search(r"(?:trae|enfoca|activa|abre la ventana)\s+(?:al frente|la ventana|la aplicacion)?\s*(.+)", t) and "ventana" in t:
            titulo, hwnd = self._buscar_ventana(t.split("ventana")[-1] if "ventana" in t else "")
            if not hwnd:
                return "Señor, no encontré esa ventana."
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return f"Ventana «{titulo}» al frente, señor."

        # ── ratón y teclado ──
        if re.search(r"haz (un )?clic|click|clica|cliquea|pincha", t):
            import pyautogui
            mm = re.search(r"(?:clic|click|clica|cliquea|pincha)[^\n]*?(?:en|a)\s*\(?\s*(\d+)\s*[, ]\s*(\d+)", t)
            if mm:
                x, y = int(mm.group(1)), int(mm.group(2))
                pyautogui.click(x, y)
                return f"Clic en ({x}, {y}), señor."
            # clic sobre ventana: "haz clic en la ventana chrome"
            mw = re.search(r"clic\s+(?:en|sobre)\s+la\s+ventana\s+(.+)", t)
            if mw:
                titulo, hwnd = self._buscar_ventana(mw.group(1))
                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    cx = ctypes.windll.user32.GetSystemMetrics(0) // 2
                    cy = ctypes.windll.user32.GetSystemMetrics(1) // 2
                    pyautogui.click(cx, cy)
                    return f"Clic en el centro de «{titulo}», señor."
                return f"Señor, no veo la ventana «{mw.group(1).strip()}»."
        if re.search(r"doble clic|doble click", t):
            import pyautogui
            mm = re.search(r"doble clic[^\n]*?(?:en|a)\s*\(?\s*(\d+)\s*[, ]\s*(\d+)", t)
            if mm:
                pyautogui.doubleClick(int(mm.group(1)), int(mm.group(2)))
                return f"Doble clic en ({mm.group(1)}, {mm.group(2)}), señor."
        if re.search(r"arrastra[^\n]*?(\d+)\s*[, ]\s*(\d+)[^\n]*?(\d+)\s*[, ]\s*(\d+)", t):
            import pyautogui
            mm = re.search(r"(\d+)\s*[, ]\s*(\d+)[^\n]*?(\d+)\s*[, ]\s*(\d+)", t)
            pyautogui.dragTo(int(mm.group(3)), int(mm.group(4)),
                             duration=0.4, button="left")
            return "Arrastrado, señor."
        if re.search(r"scroll|desplaza la rueda|baja la pagina|sube la pagina", t):
            import pyautogui
            n = 3
            mm = re.search(r"scroll[^\n]*?(\d+)", t)
            if mm:
                n = int(mm.group(1))
            hacia_abajo = "baja" in t or "abajo" in t or "scroll" in t
            pyautogui.scroll(-n * 120 if hacia_abajo else n * 120)
            return f"Desplazando la página {'hacia abajo' if hacia_abajo else 'hacia arriba'}, señor."
        if re.search(r"escribe\s+«?([^»]+)»?|teclea\s+", t):
            import pyautogui
            mm = re.search(r"(?:escribe|teclea)\s+«?([^»\n]+)»?", t)
            if mm:
                pyautogui.typewrite(mm.group(1).strip(), interval=0.02)
                return f"Escribí «{mm.group(1).strip()}», señor."
        atajos = {
            "copia": ("ctrl", "c"), "pega": ("ctrl", "v"), "corta": ("ctrl", "x"),
            "deshace": ("ctrl", "z"), "selecciona todo": ("ctrl", "a"),
            "guarda el archivo": ("ctrl", "s"), "imprime": ("ctrl", "p"),
            "cierra la pestana": ("ctrl", "w"), "nueva pestana": ("ctrl", "t"),
        }
        for frase, keys in atajos.items():
            if frase in t and re.search(r"pulsa|presiona|aprieta|atajo|haz", t):
                import pyautogui
                pyautogui.hotkey(*keys)
                return f"Atajo «{frase}» ejecutado, señor."

        # ── macros ──
        return self._macros(t)

    def _macros(self, t: str):
        if re.search(r"graba una macro|empieza a grabar|grabar macro", t):
            mm = re.search(r"(?:macro|grabar)\s*(?:llamada\s+|con\s+nombre\s+)?(.+)$", t)
            nombre = (mm.group(1).strip().rstrip(".") if mm else f"macro_{int(time.time())}")[:60]
            import pyautogui
            try:
                from pynput import mouse, keyboard
            except ImportError:
                return "Señor, falta el paquete pynput para grabar macros (pip install pynput)."
            eventos = []
            inicio = time.time()
            def on_move(x, y):
                eventos.append(("move", round(time.time() - inicio, 3), x, y))
            def on_click(x, y, btn, pressed):
                if pressed:
                    eventos.append(("click", round(time.time() - inicio, 3), x, y))
            def on_press(k):
                try:
                    eventos.append(("key", round(time.time() - inicio, 3), k.char))
                except AttributeError:
                    eventos.append(("key", round(time.time() - inicio, 3), f"<{k.name}>"))
            self._grabando = {"nombre": nombre, "mouse": None, "teclado": None, "inicio": inicio}
            try:
                self._grabando["mouse"] = mouse.Listener(on_move=on_move, on_click=on_click)
                self._grabando["teclado"] = keyboard.Listener(on_press=on_press)
                self._grabando["mouse"].start()
                self._grabando["teclado"].start()
            except Exception as e:
                return f"Señor, no pude iniciar la grabación: {e}"
            def _guardar():
                time.sleep(1.5)
                if not self._grabando:
                    return
                g = self._grabando
                g["mouse"].stop(); g["teclado"].stop()
                eventos.sort(key=lambda e: e[1])
                ruta = os.path.join(self._macros_dir, g["nombre"] + ".json")
                with open(ruta, "w", encoding="utf-8") as f:
                    import json
                    json.dump(eventos, f)
                self._grabando = None
                if self.notify:
                    self.notify(f"Macro «{g['nombre']}» grabada, señor. Dígame «ejecuta la macro {g['nombre']}».")
            threading.Thread(target=_guardar, daemon=True).start()
            return (f"Grabando la macro «{nombre}», señor. Ejecute sus acciones; "
                    f"dígame «para la macro» cuando termine.")
        if re.search(r"para (la )?macro|detente|deja de grabar|termina la grabacion", t):
            if getattr(self, "_grabando", None):
                return "Macro guardada, señor. Se lo confirmaré cuando esté lista."
            return "Señor, no estaba grabando ninguna macro."
        if re.search(r"ejecuta (la )?macro|reproduce (la )?macro|lanza (la )?macro", t):
            mm = re.search(r"(?:macro)\s+(.+)$", t)
            nombre = (mm.group(1).strip().rstrip(".") if mm else "")
            ruta = os.path.join(self._macros_dir, nombre + ".json")
            if not os.path.exists(ruta):
                return f"Señor, no existe la macro «{nombre}». Dígame «que macros hay» para ver la lista."
            try:
                import json
                import pyautogui
                with open(ruta, encoding="utf-8") as f:
                    eventos = json.load(f)
                pyautogui.PAUSE = 0.01
                anterior = 0.0
                for ev in eventos:
                    delay = max(ev[1] - anterior, 0)
                    anterior = ev[1]
                    if ev[0] == "move":
                        pyautogui.moveTo(ev[2], ev[3])
                    elif ev[0] == "click":
                        pyautogui.click(ev[2], ev[3])
                    elif ev[0] == "key" and not ev[2].startswith("<"):
                        pyautogui.typewrite(ev[2], interval=0.005)
                return f"Macro «{nombre}» ejecutada, señor."
            except Exception as e:
                return f"Señor, falló la macro: {e}"
        if re.search(r"que macros hay|lista las macros|mis macros", t):
            archivos = [f[:-5] for f in os.listdir(self._macros_dir) if f.endswith(".json")]
            if not archivos:
                return "Señor, aún no tiene macros. Dígame «graba una macro llamada X» para crear una."
            return "Macros disponibles, señor: " + ", ".join(sorted(archivos)) + "."
        if re.search(r"borra (la )?macro|elimina (la )?macro", t):
            mm = re.search(r"macro\s+(.+)$", t)
            nombre = (mm.group(1).strip().rstrip(".") if mm else "")
            ruta = os.path.join(self._macros_dir, nombre + ".json")
            if os.path.exists(ruta):
                os.remove(ruta)
                return f"Macro «{nombre}» borrada, señor."
            return f"Señor, no existe la macro «{nombre}»."
        return None

    # ── C. ARCHIVOS: lotes, ZIP, búsqueda, backups, limpieza ────────────────
    @staticmethod
    def _ubi(alias):
        u = os.path.expanduser("~")
        ruta = {
            "escritorio": os.path.join(u, "Desktop"),
            "descargas": os.path.join(u, "Downloads"),
            "descarga": os.path.join(u, "Downloads"),
            "documentos": os.path.join(u, "Documents"),
            "imagenes": os.path.join(u, "Pictures"),
            "musica": os.path.join(u, "Music"),
            "videos": os.path.join(u, "Videos"),
            "temp": os.environ.get("TEMP", os.path.join(u, "AppData", "Local", "Temp")),
        }.get(alias.strip().lower() if alias else "")
        if ruta:
            return ruta
        # ruta directa (absoluta o relativa): se acepta aunque el destino no
        # exista aún (se creará); los alias desconocidos devuelven None
        a = (alias or "").strip()
        if (os.sep in a or "/" in a or re.match(r"^[a-zA-Z]:[\\/]", a)):
            return a
        return None

    def _archivos(self, t: str):
        # mover en lote: "mueve todos los pdf de descargas a documentos"
        # (origen/destino admiten alias o ruta directa con espacios)
        m = re.search(r"mueve todos los (?:archivos )?\.?(\w+)\s+(?:de|en|que estan en)\s+(.+)\s+(?:a|hacia|para)\s+(.+)$", t)
        if m:
            ext, origen, destino = m.group(1), m.group(2).strip(), m.group(3).strip()
            src = self._ubi(origen)
            dst = self._ubi(destino)
            if not src or not dst:
                return f"Señor, no conozco las ubicaciones «{origen}» o «{destino}»."
            if not os.path.isdir(src):
                return f"Señor, la carpeta {src} no existe."
            if not os.path.isdir(dst):
                os.makedirs(dst, exist_ok=True)
            mover = 0
            for f in os.listdir(src):
                if f.lower().endswith("." + ext.lower()):
                    shutil.move(os.path.join(src, f), os.path.join(dst, f))
                    mover += 1
            return (f"Moví {mover} archivos .{ext} de {os.path.basename(src.rstrip('\\/'))} a "
                    f"{os.path.basename(dst.rstrip('\\/'))}, señor." if mover
                    else f"Señor, no había archivos .{ext} en {os.path.basename(src.rstrip('\\/'))}.")
        # renombrar en lote: "renombra los archivos de descargas añadiendo la fecha"
        m = re.search(r"renombra los (?:archivos|ficheros)\s+(?:de|en|que estan en)\s+(.+?)\s+(?:anadiendo|agregando|reemplazando|con el prefijo|con prefijo|poniendo)(?: la | el | de | )?(.+)$", t)
        if m:
            carpeta = self._ubi(m.group(1).strip())
            if not carpeta or not os.path.isdir(carpeta):
                return f"Señor, no conozco o no existe la carpeta «{m.group(1).strip()}»."
            modo = m.group(2)
            prefijo = datetime.now().strftime("%Y-%m-%d_") if "fecha" in modo else None
            m2 = re.search(r"reemplazando\s+«?([^»]+)»?\s+por\s+«?([^»]+)»?", t)
            cambiados = 0
            for f in os.listdir(carpeta):
                ruta = os.path.join(carpeta, f)
                if not os.path.isfile(ruta) or f.startswith("~"):
                    continue
                if m2:
                    nuevo = f.replace(m2.group(1), m2.group(2))
                elif prefijo:
                    nuevo = prefijo + f
                else:
                    continue
                if nuevo != f:
                    try:
                        os.rename(ruta, os.path.join(carpeta, nuevo))
                        cambiados += 1
                    except OSError:
                        pass
            return (f"Renombré {cambiados} archivos en {os.path.basename(carpeta.rstrip('\\/'))}, señor." if cambiados
                    else "Señor, no había nada que renombrar allí.")
        # comprimir: "comprime la carpeta descargas" / "comprime C:\ruta"
        m = re.search(r"comprime (?:la carpeta |la |el )?(.+?)(?:\s+en\s+(\S+))?$", t)
        if m and "comprime" in t:
            carpeta = self._ubi(m.group(1).strip())
            if not carpeta or not os.path.isdir(carpeta):
                return f"Señor, no existe la carpeta {m.group(1).strip()}."
            nombre = m.group(2) or os.path.basename(carpeta.rstrip("\\/"))
            destino = os.path.join(self._backup_dir if self.safe else os.path.dirname(carpeta),
                                   re.sub(r"\.zip$", "", nombre))
            try:
                ruta = shutil.make_archive(destino, "zip", carpeta)
                return f"Comprimí {carpeta} en {ruta}, señor."
            except Exception as e:
                return f"Señor, no pude comprimir: {e}"
        # buscar profundo: "busca todos los pdf en descargas" / "mayores de 100 mb"
        m = re.search(r"busca todos los (?:archivos )?\.?(\w+)\s+(?:en|de|que esten en)\s+(.+)$", t)
        if m:
            ext, carpeta = m.group(1), m.group(2).strip()
            raiz = self._ubi(carpeta)
            if not raiz or not os.path.isdir(raiz):
                return f"Señor, no conozco la carpeta «{carpeta}»."
            tam_min = None
            mt = re.search(r"mayores de (\d+)\s*(mb|gb)", t)
            if mt:
                tam_min = int(mt.group(1)) * (1024 ** 2 if mt.group(2) == "mb" else 1024 ** 3)
            hallados, limite = [], time.time() + 12
            for dirpath, _dirs, files in os.walk(raiz):
                for f in files:
                    if f.lower().endswith("." + ext.lower()):
                        ruta = os.path.join(dirpath, f)
                        if tam_min and os.path.getsize(ruta) < tam_min:
                            continue
                        hallados.append(os.path.basename(ruta))
                        if len(hallados) >= 20 or time.time() > limite:
                            break
                if len(hallados) >= 20 or time.time() > limite:
                    break
            if not hallados:
                return f"Señor, no encontré archivos .{ext} en {carpeta}."
            return f"Encontré {len(hallados)} archivos .{ext} en {carpeta}: " + ", ".join(hallados[:10]) + "."
        # limpiar temporales (poder total: ejecución inmediata)
        if re.search(r"limpia (los )?temporales|limpiar temporales|limpia la carpeta temporal", t):
            temp = os.environ.get("TEMP", "")
            if not temp or not os.path.isdir(temp):
                return "Señor, no encontré la carpeta temporal."
            if self.safe:
                return "Señor, hay temporales listos para limpiar. (modo seguro: no ejecutado)"
            borrados = 0
            for nombre in os.listdir(temp):
                ruta = os.path.join(temp, nombre)
                try:
                    if os.path.isfile(ruta):
                        os.remove(ruta)
                        borrados += 1
                    elif os.path.isdir(ruta):
                        shutil.rmtree(ruta, ignore_errors=True)
                        borrados += 1
                except OSError:
                    pass
            return f"Limpié {borrados} elementos temporales, señor. El sistema respira mejor."
        # copia de seguridad: "haz una copia de seguridad de la carpeta descargas"
        m = re.search(r"(?:copia de seguridad|backup|respaldo)[^\n]*?(?:de|de la carpeta|de la)\s+(.+)$", t)
        if m:
            carpeta = self._ubi(m.group(1).strip())
            if not carpeta or not os.path.isdir(carpeta):
                return f"Señor, no existe la carpeta {m.group(1).strip()}."
            destino = os.path.join(self._backup_dir,
                                   f"{os.path.basename(carpeta.rstrip('\\/'))}_{datetime.now().strftime('%Y%m%d_%H%M')}")
            try:
                shutil.copytree(carpeta, destino)
                return f"Copia de seguridad completada en {destino}, señor."
            except Exception as e:
                return f"Señor, no pude hacer la copia: {e}"
        return None

    # ── D. PROFUNDO: winget, servicios, entorno, registro ────────────────────
    def _winget_disponible(self) -> bool:
        if self._winget is None:
            try:
                r = subprocess.run(["winget", "--version"], capture_output=True,
                                   timeout=10, text=True)
                self._winget = r.returncode == 0
            except Exception:
                self._winget = False
        return self._winget

    def _profundo(self, t: str):
        # ── winget: instalar / desinstalar / buscar (poder total: inmediato) ──
        m = re.search(r"instala(?:me)? (la aplicacion |el programa |la app |de | )?(.+)", t)
        if m and "desinstala" not in t:
            app = m.group(2).strip().strip(".").lower()
            if not self._winget_disponible():
                return "Señor, winget no está disponible en este equipo."
            wid = WINGET_MAP.get(app)
            if not wid:
                return (f"Señor, no tengo el identificador winget de «{app}». "
                        f"Pruebe con uno conocido: chrome, firefox, vscode, spotify, 7zip, vlc, obsidian…")
            if self.safe:
                return f"[modo seguro] Instalaría {app} (winget id {wid})"
            r = subprocess.run(["winget", "install", "--id", wid, "--silent",
                                "--accept-source-agreements", "--accept-package-agreements"],
                               capture_output=True, timeout=600, text=True)
            return (f"Instalación de {app} completada, señor." if r.returncode == 0
                    else f"Señor, la instalación de {app} falló: {(r.stdout or r.stderr)[-200:]}")
        if re.search(r"desinstala (la aplicacion |el programa |la app |de | )?(.+)", t):
            app = t.split("desinstala")[-1].strip().strip(".")
            if not self._winget_disponible():
                return "Señor, winget no está disponible en este equipo."
            wid = WINGET_MAP.get(app.lower())
            if not wid:
                return f"Señor, no conozco el paquete winget de «{app}»."
            if self.safe:
                return f"[modo seguro] Desinstalaría {app}"
            r = subprocess.run(["winget", "uninstall", "--id", wid, "--silent"],
                               capture_output=True, timeout=600, text=True)
            return (f"«{app}» desinstalado, señor." if r.returncode == 0
                    else f"Señor, no pude desinstalar {app}: {(r.stdout or r.stderr)[-200:]}")
        if re.search(r"busca (un )?programa|que programas puedo instalar|busca (un )?paquete", t):
            if not self._winget_disponible():
                return "Señor, winget no está disponible en este equipo."
            mm = re.search(r"(?:programa|paquete|app)\s+(\w+)", t)
            if not mm:
                return ("Señor, puedo instalar con winget: " + ", ".join(
                    sorted(set(WINGET_MAP.values()))) + ". Dígame «instala chrome» por ejemplo.")
            r = subprocess.run(["winget", "search", mm.group(1), "--limit", "8"],
                               capture_output=True, timeout=60, text=True)
            salida = (r.stdout or "").strip()
            if not salida or r.returncode != 0:
                return f"Señor, no encontré nada para «{mm.group(1)}»."
            lineas = [l for l in salida.splitlines() if re.search(r"\S\s+\S", l)][1:9]
            return "Resultados de winget, señor: " + " | ".join(l.split()[0] for l in lineas if l.split()) + "."

        # ── servicios de Windows ──
        if re.search(r"que servicios hay|lista los servicios|servicios de windows", t):
            try:
                r = subprocess.run(["sc", "query", "state=", "all"],
                                   capture_output=True, timeout=20, text=True)
                servicios = re.findall(r"SERVICE_NAME:\s+(\S+)", r.stdout or "")
                return f"Señor, hay {len(servicios)} servicios en el sistema. El más relevante: " + servicios[0] + "."
            except Exception as e:
                return f"Señor, no pude listar servicios: {e}"
        m = re.search(r"(?:inicia|arranca|para|detiene|reinicia) el servicio (?:de |llamado |)??(\S+)", t)
        if m and ("servicio" in t):
            svc = m.group(1)
            accion = "start" if re.search(r"inicia|arranca", t) else ("stop" if re.search(r"para|detiene", t) else "restart")
            if self.safe:
                return f"[modo seguro] {accion} servicio {svc}"
            r = subprocess.run(["sc", accion, svc], capture_output=True, timeout=30, text=True)
            ok = "1062" not in r.stdout and r.returncode == 0
            return (f"Servicio «{svc}» {accion} correctamente, señor." if ok
                    else f"Señor, el servicio «{svc}» no cambió de estado: {(r.stdout or r.stderr)[-150:]}")

        # ── variables de entorno ──
        m = re.search(r"que (?:valor tiene |es )?la variable(?: de entorno)?\s+(?:de |llamada )?(\S+)", t)
        if m and "variable" in t:
            try:
                r = subprocess.run(["cmd", "/c", f"echo %{m.group(1)}%"],
                                   capture_output=True, timeout=10, text=True)
                valor = (r.stdout or "").strip()
                return f"La variable «{m.group(1)}» vale «{valor}», señor." if valor else f"Señor, la variable «{m.group(1)}» no está definida."
            except Exception as e:
                return f"Señor, no pude leer la variable: {e}"
        m = re.search(r"crea la variable(?: de entorno)?\s+(?:de |llamada )?(\S+)\s+(?:con valor|igual a|que valga)\s+(.+)", t)
        if m:
            nombre, valor = m.group(1), m.group(2).strip().strip(".")
            if self.safe:
                return f"[modo seguro] Crearía variable {nombre}={valor}"
            subprocess.run(["setx", nombre, valor], capture_output=True, timeout=15)
            return f"Variable «{nombre}» creada con valor «{valor}», señor. Aplicará en las nuevas ventanas."

        # ── registro de Windows ──
        if re.search(r"lee|consulta|dime (el valor de )?la clave|que hay en la clave", t) and "registro" in t:
            m = re.search(r"clave\s+(?:de registro\s+)?(\S+)", t)
            if m:
                try:
                    r = subprocess.run(["reg", "query", m.group(1)],
                                       capture_output=True, timeout=15, text=True)
                    salida = (r.stdout or "").strip()
                    if not salida:
                        return f"Señor, la clave «{m.group(1)}» no existe."
                    return f"Clave «{m.group(1)}», señor: " + "; ".join(salida.splitlines()[:6])
                except Exception as e:
                    return f"Señor, no pude consultar el registro: {e}"
        m = re.search(r"(?:escribe|crea)[^\n]*(?:en el )?registro[^\n]*?(?:clave|ruta)\s+([^\s]+)", t)
        if m and "registro" in t:
            ruta_clave = m.group(1).strip().strip(".")
            nombre_valor = "Jarvis"
            mv = re.search(r"(?:valor|nombre|entry)\s+(\S+)", t)
            if mv:
                nombre_valor = mv.group(1)
            md = re.search(r"(?:con valor|dato)\s+(.+)", t)
            dato = md.group(1).strip().strip(".") if md else "1"
            if self.safe:
                return f"[modo seguro] Escribiría en registro {ruta_clave} /v {nombre_valor} /d {dato}"
            r = subprocess.run(["reg", "add", ruta_clave, "/v", nombre_valor, "/d", dato, "/f"],
                               capture_output=True, timeout=15, text=True)
            if r.returncode == 0:
                return f"Clave «{ruta_clave}» creada con «{nombre_valor}={dato}», señor."
            return f"Señor, no pude escribir en el registro: {(r.stdout or r.stderr)[-150:]}"
        return None

    # ── E. TAREAS PROGRAMADAS ────────────────────────────────────────────────
    def _ejecutar_accion(self, accion: str) -> str:
        """Ejecuta una acción de tarea. Devuelve texto (se notifica por voz)."""
        if self.safe:
            return f"Tarea «{accion}» (modo seguro: simulada)"
        a = _norm(accion)
        try:
            if "temporal" in a or "temporales" in a:
                temp = os.environ.get("TEMP", "")
                n = 0
                if temp and os.path.isdir(temp):
                    for nombre in os.listdir(temp):
                        ruta = os.path.join(temp, nombre)
                        try:
                            if os.path.isfile(ruta):
                                os.remove(ruta)
                            elif os.path.isdir(ruta):
                                shutil.rmtree(ruta, ignore_errors=True)
                            n += 1
                        except OSError:
                            pass
                return f"Tarea «{accion}»: limpié {n} temporales."
            if "papelera" in a:
                subprocess.run("powershell -NoProfile -Command Clear-RecycleBin -Force",
                               capture_output=True, timeout=30)
                return f"Tarea «{accion}»: papelera vaciada."
            if "copia de seguridad" in a or "backup" in a:
                u = os.path.expanduser("~")
                dst = os.path.join(self._backup_dir, f"automatico_{datetime.now().strftime('%Y%m%d_%H%M')}")
                shutil.copytree(os.path.join(u, "Documents"), dst)
                return f"Tarea «{accion}»: copia de seguridad de Documentos completada."
            if "abre " in a or "abrir " in a:
                app = re.sub(r"^(abre|abrir|la aplicacion)\s+", "", accion.strip())
                if re.search(r'[&|;<>^$`]', app):
                    return f"Tarea «{accion}»: nombre de aplicación no válido."
                subprocess.Popen(["cmd", "/c", "start", "", app], creationflags=0x08000000)
                return f"Tarea «{accion}»: abrí {app}."
            if "apaga" in a:
                subprocess.Popen("shutdown /s /t 60", shell=True, creationflags=0x08000000)
                return f"Tarea «{accion}»: el equipo se apagará en un minuto."
            return f"Tarea «{accion}» ejecutada."
        except Exception as e:
            return f"Tarea «{accion}» falló: {e}"

    def _tareas(self, t: str):
        if re.search(r"que tareas (tengo|hay|programadas)|lista las tareas|mis tareas programadas", t):
            with self._db_lock, self._dbconn() as c:
                rows = c.execute("SELECT * FROM pc_tasks ORDER BY id").fetchall()
            if not rows:
                return ("Señor, no hay tareas programadas. Dígame por ejemplo: "
                        "«crea una tarea que limpie los temporales todos los lunes a las 9».")
            desc = []
            for r in rows:
                prog = "diaria" if r["hora"] and r["dia"] is None else (
                    f"cada {['lunes','martes','miercoles','jueves','viernes','sabado','domingo'][r['dia']]}" if r["dia"] is not None
                    else f"el {r['fecha']}")
                desc.append(f"{r['nombre']} ({r['accion']}, {prog} {r['hora'] or ''})")
            return "Tareas programadas, señor: " + ", ".join(desc) + "."
        # crear tarea: "crea una tarea que <accion> <frecuencia>"
        m = re.search(
            r"crea una tarea(?: llamada (.+?))? que (.+?)(?:"
            r" todos los (\w+)(?:s)? a las (\d{1,2})(?::?(\d{2}))?"
            r"| todas las noches a las (\d{1,2})(?::?(\d{2}))?"
            r"| diaria a las (\d{1,2})(?::?(\d{2}))?"
            r"| a las (\d{1,2})(?::?(\d{2}))?"
            r"| el (?:dia )?(\d{1,2}) de (\w+) a las (\d{1,2})(?::?(\d{2}))?"
            r"| cada (\d+) (minuto|hora)"
            r"| al arrancar el pc| al iniciar el pc)$", t)
        if m and "tarea" in t:
            def _hmm(gh, gm):
                return f"{int(gh):02d}:{gm or '00'}"

            nombre = (m.group(1) or "tarea").strip()
            accion = m.group(2).strip()
            hora = dia = fecha = None
            if m.group(3):
                dia = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
                       "viernes": 4, "sabado": 5, "domingo": 6}.get(m.group(3))
                hora = _hmm(m.group(4), m.group(5))
            elif m.group(6):
                hora = _hmm(m.group(6), m.group(7))
            elif m.group(8):
                hora = _hmm(m.group(8), m.group(9))
            elif m.group(10):
                hora = _hmm(m.group(10), m.group(11))
            elif m.group(12) and m.group(13):
                dia = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
                       "viernes": 4, "sabado": 5, "domingo": 6}.get(m.group(13), None)
                hora = _hmm(m.group(14), m.group(15))
            elif m.group(16):
                # cada N minutos/horas → se guarda como diaria con hora ahora
                hora = datetime.now().strftime("%H:%M")
            if "al arrancar el pc" in t or "al iniciar el pc" in t:
                # tarea de arranque: acceso directo en la carpeta Inicio
                startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                       "Start Menu", "Programs", "Startup")
                bat = os.path.join(startup, f"jarvis_{nombre}.bat")
                comando = self._accion_a_comando(accion)
                with open(bat, "w", encoding="utf-8") as f:
                    f.write(f"@echo off\n{comando}\n")
                return f"Tarea «{nombre}» creada: se ejecutará al arrancar el PC, señor."
            if not hora and not dia and not fecha:
                return ("Señor, no entendí la programación. Ejemplos: «crea una tarea que limpie "
                        "los temporales todos los lunes a las 9», «… que haga backup a las 22:00», "
                        "«… que abra spotify al arrancar el pc».")
            with self._db_lock, self._dbconn() as c:
                c.execute("INSERT INTO pc_tasks (nombre, accion, hora, dia, fecha, creada) "
                          "VALUES (?,?,?,?,?,?)",
                          (nombre, accion, hora, dia, fecha,
                           datetime.now().strftime("%Y-%m-%d %H:%M")))
            prog = "cada " + ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"][dia] if dia is not None else (f"a las {hora}" if hora else f"el {fecha}")
            return f"Tarea «{nombre}» programada ({accion}, {prog}), señor."
        # borrar tarea
        m = re.search(r"borra (la )?tarea|elimina (la )?tarea|quita (la )?tarea", t)
        if m:
            mm = re.search(r"tarea\s+(?:llamada\s+|de\s+nombre\s+)?(.+)$", t)
            nombre = re.sub(r"^(?:de\s+la\s+|de\s+|que\s+|llamada\s+|la\s+)", "",
                            (mm.group(1).strip().rstrip(".") if mm else ""))
            if "al arrancar" in t:
                startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                       "Start Menu", "Programs", "Startup")
                bat = os.path.join(startup, f"jarvis_{nombre}.bat")
                if os.path.exists(bat):
                    os.remove(bat)
                    return f"Tarea de arranque «{nombre}» eliminada, señor."
            with self._db_lock, self._dbconn() as c:
                cur = c.execute("DELETE FROM pc_tasks WHERE nombre LIKE ? OR accion LIKE ?",
                                (f"%{nombre}%", f"%{nombre}%"))
                n = cur.rowcount
            return (f"Tarea «{nombre}» eliminada, señor." if n
                    else f"Señor, no encontré la tarea «{nombre}».")
        # ejecutar ahora
        m = re.search(r"ejecuta (la )?tarea|lanza (la )?tarea|corre (la )?tarea", t)
        if m:
            mm = re.search(r"tarea\s+(?:llamada\s+|de\s+nombre\s+)?(.+)$", t)
            nombre = re.sub(r"^(?:de\s+la\s+|de\s+|que\s+|llamada\s+|la\s+)", "",
                            (mm.group(1).strip().rstrip(".") if mm else ""))
            with self._db_lock, self._dbconn() as c:
                row = c.execute("SELECT * FROM pc_tasks WHERE nombre LIKE ? OR accion LIKE ?",
                                (f"%{nombre}%", f"%{nombre}%")).fetchone()
            if not row:
                return f"Señor, no existe la tarea «{nombre}»."
            r = self._ejecutar_accion(row["accion"])
            with self._db_lock, self._dbconn() as c:
                c.execute("UPDATE pc_tasks SET ultima_ejec=? WHERE id=?",
                          (datetime.now().strftime("%Y-%m-%d %H:%M"), row["id"]))
            return r + " (tarea «" + row["nombre"] + "»)"
        return None

    @staticmethod
    def _accion_a_comando(accion: str) -> str:
        a = _norm(accion)
        if "temporal" in a:
            return 'powershell -NoProfile -Command "Remove-Item \\"$env:TEMP\\*\\" -Recurse -Force -ErrorAction SilentlyContinue"'
        if "papelera" in a:
            return 'powershell -NoProfile -Command "Clear-RecycleBin -Force"'
        if "backup" in a or "copia" in a:
            return 'powershell -NoProfile -Command "Copy-Item $env:USERPROFILE\\Documents -Destination $env:USERPROFILE\\Descargas\\JARVIS\\Backups\\automatico_$(Get-Date -Format yyyyMMdd_HHmm) -Recurse"'
        if "apaga" in a:
            return "shutdown /s /t 60"
        mm = re.search(r"abre\s+(.+)", accion)
        if mm:
            return f"start {mm.group(1).strip()}"
        return "echo tarea jarvis"

    def _scheduler_loop(self):
        """Hilo de fondo: cada 30 s comprueba tareas pendientes."""
        while not self._scheduler_stop.is_set():
            try:
                ahora = datetime.now()
                clave = ahora.strftime("%H:%M")
                with self._db_lock, self._dbconn() as c:
                    rows = c.execute(
                        "SELECT * FROM pc_tasks WHERE activo=1 AND hora=? AND ultima_ejec IS NULL",
                        (clave,)).fetchall()
                    for r in rows:
                        if r["dia"] is None or r["dia"] == ahora.weekday():
                            c.execute("UPDATE pc_tasks SET ultima_ejec=? WHERE id=?",
                                      (ahora.strftime("%Y-%m-%d %H:%M"), r["id"]))
                for r in rows:
                    if r["dia"] is None or r["dia"] == ahora.weekday():
                        texto = self._ejecutar_accion(r["accion"])
                        if self.notify:
                            self.notify(texto)
                        self.log(f"tarea: {texto}")
            except Exception as e:
                self.log(f"scheduler: {e}")
            self._scheduler_stop.wait(30)

    def shutdown(self):
        self._scheduler_stop.set()

    # ── estado para telemetría ───────────────────────────────────────────────
    def estado(self):
        return {
            "poder": "total",
            "winget": self._winget_disponible(),
            "macros": len([f for f in os.listdir(self._macros_dir) if f.endswith(".json")]),
            "tareas": self._count_tasks(),
        }

    def _count_tasks(self):
        try:
            with self._db_lock, self._dbconn() as c:
                return c.execute("SELECT COUNT(*) n FROM pc_tasks WHERE activo=1").fetchone()["n"]
        except Exception:
            return 0