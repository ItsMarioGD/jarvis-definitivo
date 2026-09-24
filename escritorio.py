#!/usr/bin/env python3
"""
escritorio.py - JARVIS como aplicacion de escritorio
====================================================
ORIGEN se abre en su propia ventana, sin pestañas ni barra de direcciones,
con el motor de Edge que ya trae Windows (o Chrome si no hay Edge). No es una
pestaña mas del navegador del señor: es un perfil aparte, sin extensiones, sin
sincronizar y sin trabajo en segundo plano, que se cierra del todo al cerrar
la ventana. La interfaz es exactamente la misma.

Por que no una ventana «nativa» hecha a mano: ORIGEN es WebGL (el cerebro de
particulas) y necesita un motor web. Electron trae uno entero (~150 MB por
aplicacion) y pywebview usa por debajo este mismo motor de Edge, con mas
dependencias. Asi es lo mismo sin instalar nada.

Uso:
    doble clic en el icono «JARVIS»  (lo crea el propio JARVIS la primera vez que arranca)
    pythonw escritorio.py            lo mismo: abre JARVIS y arranca el nucleo si hace falta
    python escritorio.py --acceso    vuelve a crear el icono (escritorio y menu Inicio)
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

URL = "http://localhost:5000/"
SALUD = "http://127.0.0.1:5000/health"

# Lo que no hace falta para una sola pagina en localhost: extensiones,
# sincronizar, traducir, enviar a la tele, actualizar componentes, informes...
# Y el audio sin esperar a un clic: JARVIS saluda en cuanto se abre.
BANDERAS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-background-mode",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-features=Translate,MediaRouter,OptimizationHints",
    "--autoplay-policy=no-user-gesture-required",
    # Tras un reinicio no pregunta si «restaurar páginas».
    "--hide-crash-restore-bubble",
]


def carpeta_datos() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "JARVIS")


def perfil() -> str:
    return os.path.join(carpeta_datos(), "ventana")


def _sin_consola() -> int:
    return 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW


# ── dónde está el motor ─────────────────────────────────────────────────────
def _registro(exe: str) -> str:
    """Ruta registrada en «App Paths» de Windows (así se instalan Edge y Chrome)."""
    try:
        import winreg
    except ImportError:
        return ""
    clave = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + exe
    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(raiz, clave) as k:
                ruta = winreg.QueryValue(k, None)
                if ruta and os.path.exists(ruta.strip('"')):
                    return ruta.strip('"')
        except OSError:
            continue
    return ""


def navegador() -> str:
    """Edge primero (viene con Windows); si no, Chrome o Brave."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    candidatos = []
    for exe, rel in (("msedge.exe", r"Microsoft\Edge\Application\msedge.exe"),
                     ("chrome.exe", r"Google\Chrome\Application\chrome.exe"),
                     ("brave.exe", r"BraveSoftware\Brave-Browser\Application\brave.exe")):
        candidatos += [os.path.join(pf86, rel), os.path.join(pf, rel)]
        if local:
            candidatos.append(os.path.join(local, rel))
        candidatos.append(_registro(exe))
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    for nombre in ("msedge", "microsoft-edge", "google-chrome", "chrome",
                   "chromium", "chromium-browser", "brave"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return ""


def orden(exe: str, url: str = URL, primera_vez: bool = False) -> list:
    """La línea de órdenes de la ventana (se prueba sin abrir nada)."""
    cmd = [exe, f"--app={url}", f"--user-data-dir={perfil()}", *BANDERAS]
    if primera_vez:
        # Solo la primera vez: después el motor recuerda dónde la dejó el señor.
        cmd.append("--window-size=1360,860")
    return cmd


def _preparar_perfil() -> bool:
    """Crea el perfil de la ventana. True si es la primera vez."""
    carpeta = perfil()
    nuevo = not os.path.isdir(carpeta)
    os.makedirs(carpeta, exist_ok=True)
    estado = os.path.join(carpeta, "Local State")
    if not os.path.exists(estado):
        # Que no siga vivo en segundo plano al cerrar la ventana.
        try:
            with open(estado, "w", encoding="utf-8") as f:
                json.dump({"background_mode": {"enabled": False}}, f)
        except OSError:
            pass
    return nuevo


# ── la ventana ya abierta ───────────────────────────────────────────────────
def procesos_ventana() -> list:
    """Procesos del motor que usan el perfil de JARVIS."""
    try:
        import psutil
    except ImportError:
        return []
    marca = perfil().lower()
    encontrados = []
    for p in psutil.process_iter(["cmdline"]):
        try:
            linea = " ".join(p.info.get("cmdline") or []).lower()
        except Exception:
            continue
        if "--user-data-dir=" in linea and marca in linea:
            encontrados.append(p)
    return encontrados


_USER32 = None


def _user32():
    """user32 con los tipos declarados (en 64 bits un HWND no cabe en un int)."""
    global _USER32
    if _USER32 is None:
        import ctypes
        from ctypes import wintypes
        u = ctypes.WinDLL("user32")
        u.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        _USER32 = u
    return _USER32


def _ventanas(procesos) -> list:
    """Ventanas visibles de esos procesos (Windows). Así no se confunde con una
    pestaña de ORIGEN abierta en el navegador de siempre."""
    if os.name != "nt" or not procesos:
        return []
    try:
        import ctypes
        from ctypes import wintypes
        user32 = _user32()
        pids = {p.pid for p in procesos}
        halladas = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def mirar(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
                halladas.append(hwnd)
            return True
        user32.EnumWindows(mirar, 0)
        return halladas
    except Exception:
        return []


def _traer_al_frente(procesos) -> bool:
    """Si la ventana de JARVIS está abierta, la trae delante. Solo Windows."""
    ventanas = _ventanas(procesos)
    if not ventanas:
        return False
    try:
        _user32().ShowWindow(ventanas[0], 9)            # SW_RESTORE
        _user32().SetForegroundWindow(ventanas[0])
        return True
    except Exception:
        return False


def cerrar_ventana() -> int:
    """Cierra la ventana de JARVIS (tras actualizar, para cargar lo nuevo).

    Primero como si el señor pulsara la X (WM_CLOSE): cerrarla a la fuerza haría
    que el motor preguntase «¿restaurar páginas?» la próxima vez. Solo lo que
    no se cierre en unos segundos se termina a la fuerza.
    """
    procesos = procesos_ventana()
    if not procesos:
        return 0
    try:
        import psutil
    except ImportError:
        return 0
    ventanas = _ventanas(procesos)
    if ventanas:
        for hwnd in ventanas:
            _user32().PostMessageW(hwnd, 0x0010, 0, 0)                # WM_CLOSE
        _, vivos = psutil.wait_procs(procesos, timeout=6)
    else:
        vivos = procesos
    for p in vivos:
        try:
            p.terminate()
        except Exception:
            pass
    psutil.wait_procs(vivos, timeout=5)
    return len(procesos)


def abrir_ventana(url: str = URL, reemplazar: bool = False) -> bool:
    """Abre ORIGEN como aplicación. Sin motor compatible, en el navegador."""
    if reemplazar:
        cerrar_ventana()
    else:
        abiertos = procesos_ventana()
        if abiertos and _traer_al_frente(abiertos):
            return True
    exe = navegador()
    if not exe:
        import webbrowser
        return webbrowser.open(url)
    primera = _preparar_perfil()
    try:
        subprocess.Popen(orden(exe, url, primera), cwd=carpeta_datos(),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=_sin_consola())
        return True
    except OSError:
        import webbrowser
        return webbrowser.open(url)


# ── el núcleo ───────────────────────────────────────────────────────────────
def nucleo_vivo(timeout: float = 1.5) -> bool:
    try:
        urllib.request.urlopen(SALUD, timeout=timeout)
        return True
    except Exception:
        return False


def asegurar_nucleo(espera: float = 60.0) -> bool:
    """Si JARVIS no está en marcha, lo arranca (oculto) y espera a que conteste."""
    if nucleo_vivo():
        return True
    import reiniciar_todo
    reiniciar_todo.arrancar_servicios(solo_los_caidos=True)
    fin = time.time() + espera
    while time.time() < fin:
        if nucleo_vivo():
            return True
        time.sleep(0.5)
    return False


# ── acceso directo ──────────────────────────────────────────────────────────
def _icono() -> str:
    """jarvis.ico a partir del icono de ORIGEN (hace falta Pillow)."""
    destino = os.path.join(carpeta_datos(), "jarvis.ico")
    origen = os.path.join(RAIZ, "web_interface", "icon-512.png")
    try:
        from PIL import Image
        os.makedirs(carpeta_datos(), exist_ok=True)
        Image.open(origen).save(destino, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                                (64, 64), (128, 128), (256, 256)])
        return destino
    except Exception:
        return ""


def _pythonw() -> str:
    try:
        from interprete import python_del_proyecto
        base = python_del_proyecto() or sys.executable
    except Exception:
        base = sys.executable
    w = os.path.join(os.path.dirname(base), "pythonw.exe")
    return w if os.path.exists(w) else base


def _comillas(texto: str) -> str:
    return "'" + str(texto).replace("'", "''") + "'"


def crear_acceso_directo() -> bool:
    """«JARVIS» en el escritorio y en el menú Inicio: doble clic y listo."""
    if os.name != "nt":
        print("El acceso directo solo se crea en Windows.")
        return False
    guion = (
        "$sh = New-Object -ComObject WScript.Shell\n"
        "foreach ($sitio in 'Desktop', 'Programs') {\n"
        "  $lnk = Join-Path ([Environment]::GetFolderPath($sitio)) 'JARVIS.lnk'\n"
        "  $s = $sh.CreateShortcut($lnk)\n"
        f"  $s.TargetPath = {_comillas(_pythonw())}\n"
        f"  $s.Arguments = {_comillas(chr(34) + os.path.join(RAIZ, 'escritorio.py') + chr(34))}\n"
        f"  $s.WorkingDirectory = {_comillas(RAIZ)}\n"
        f"  $icono = {_comillas(_icono())}\n"
        "  if ($icono) { $s.IconLocation = $icono }\n"
        "  $s.Description = 'J.A.R.V.I.S.'\n"
        "  $s.Save()\n"
        "}\n"
    )
    codificado = base64.b64encode(guion.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
                       capture_output=True, timeout=60, creationflags=_sin_consola())
    ok = r.returncode == 0
    if ok:
        try:
            with open(_marca_acceso(), "w", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M"))
        except OSError:
            pass
    print("Acceso directo «JARVIS» creado en el escritorio y en el menú Inicio."
          if ok else "No pude crear el acceso directo.")
    return ok


def _marca_acceso() -> str:
    return os.path.join(carpeta_datos(), "acceso_creado")


def asegurar_acceso() -> bool:
    """El icono, la primera vez que arranca JARVIS, sin abrir ninguna terminal.

    Solo una vez: si el señor lo borra, no vuelve a aparecer solo (con
    «escritorio.py --acceso» se rehace cuando quiera).
    """
    if os.name != "nt" or os.path.exists(_marca_acceso()):
        return False
    os.makedirs(carpeta_datos(), exist_ok=True)
    return crear_acceso_directo()


# ── al hacer doble clic ─────────────────────────────────────────────────────
PUERTO_CANDADO = 47931


def _candado():
    """Un solo lanzador a la vez: un segundo doble clic mientras arranca no
    levanta los servidores dos veces. El puerto se libera solo al salir."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", PUERTO_CANDADO))
        return s
    except OSError:
        s.close()
        return None


def _mensaje(texto: str):
    """Un aviso de Windows (sin tkinter también se ve)."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, texto, "J.A.R.V.I.S.", 0x30)
            return
        except Exception:
            pass
    print(texto)


def _registro_nucleo() -> str:
    try:
        import reiniciar_todo
        return reiniciar_todo.registro("JARVIS")
    except Exception:
        return os.path.join(RAIZ, "jarvis_log", "jarvis.log")


class _Aviso:
    """«JARVIS despertando…» mientras arranca el núcleo.

    Sin esto el doble clic no daba señales durante los segundos que tarda en
    arrancar, y lo natural era volver a pulsar. Sin tkinter se arranca igual.
    """
    FONDO, ORO, TENUE = "#030407", "#E8B26A", "#8A8578"

    def __init__(self):
        import tkinter as tk
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        self.tk = tk
        self.raiz = r = tk.Tk()
        r.withdraw()
        r.overrideredirect(True)
        r.configure(bg=self.FONDO)
        r.attributes("-topmost", True)
        esc = max(1.0, r.winfo_fpixels("1i") / 96.0)
        w, h = int(440 * esc), int(180 * esc)
        r.geometry(f"{w}x{h}+{(r.winfo_screenwidth() - w) // 2}+{(r.winfo_screenheight() - h) // 2}")
        tk.Label(r, text="J . A . R . V . I . S .", fg=self.ORO, bg=self.FONDO,
                 font=("Consolas", 15)).pack(pady=(int(38 * esc), 6))
        self.texto = tk.StringVar(value="despertando…")
        tk.Label(r, textvariable=self.texto, fg=self.TENUE, bg=self.FONDO, justify="center",
                 font=("Georgia", 11, "italic"), wraplength=w - int(60 * esc)).pack()
        self.ancho = int(260 * esc)
        self.lienzo = tk.Canvas(r, width=self.ancho, height=2, bg=self.FONDO, highlightthickness=0)
        self.lienzo.pack(pady=int(20 * esc))
        self.barra = self.lienzo.create_rectangle(0, 0, 0, 2, fill=self.ORO, width=0)
        self.x = 0
        self._anim = None
        r.deiconify()
        self._animar()

    def _animar(self):
        self.x = (self.x + 5) % (self.ancho + 70)
        self.lienzo.coords(self.barra, self.x - 70, 0, self.x, 2)
        self._anim = self.raiz.after(30, self._animar)

    def error(self, texto: str, registro: str):
        if self._anim:
            self.raiz.after_cancel(self._anim)
        self.lienzo.pack_forget()
        self.texto.set(texto)
        tk = self.tk
        fila = tk.Frame(self.raiz, bg=self.FONDO)
        fila.pack(pady=14)
        estilo = dict(fg=self.ORO, bg=self.FONDO, activebackground=self.FONDO,
                      activeforeground=self.ORO, relief="flat", bd=0, highlightthickness=0,
                      font=("Consolas", 10), cursor="hand2")
        if os.path.exists(registro):
            tk.Button(fila, text="ver qué pasó", command=lambda: os.startfile(registro),
                      **estilo).pack(side="left", padx=12)
        tk.Button(fila, text="cerrar", command=self.raiz.destroy, **estilo).pack(side="left", padx=12)


def arrancar_y_abrir(reemplazar: bool = False) -> bool:
    """Arranca el núcleo con el aviso en pantalla y, cuando contesta, abre la ventana."""
    fallo = ("No he podido arrancar, señor.\n"
             "Lo que pasó está en jarvis_log\\jarvis.log.")
    try:
        aviso = _Aviso()
    except Exception:
        aviso = None
    if aviso is None:
        if asegurar_nucleo():
            return abrir_ventana(reemplazar=reemplazar)
        _mensaje(fallo)
        return False

    import threading
    resultado = {}
    hilo = threading.Thread(target=lambda: resultado.update(ok=asegurar_nucleo()), daemon=True)
    hilo.start()

    def mirar():
        if hilo.is_alive():
            aviso.raiz.after(200, mirar)
        elif resultado.get("ok"):
            aviso.texto.set("aquí estoy")
            abrir_ventana(reemplazar=reemplazar)
            aviso.raiz.after(1800, aviso.raiz.destroy)     # hasta que aparece la ventana
        else:
            aviso.error(fallo, _registro_nucleo())
    aviso.raiz.after(200, mirar)
    aviso.raiz.mainloop()
    return bool(resultado.get("ok"))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        import sin_ventanas
        sin_ventanas.activar()          # nada de consolas negras al arrancar cosas
    except Exception:
        pass
    if "--acceso" in argv:
        return 0 if crear_acceso_directo() else 1
    candado = _candado()
    if candado is None:
        return 0                        # ya hay otro lanzador en marcha: él abre la ventana
    reemplazar = "--reemplazar" in argv
    if nucleo_vivo():
        abrir_ventana(reemplazar=reemplazar)
        return 0
    return 0 if arrancar_y_abrir(reemplazar) else 1


if __name__ == "__main__":
    sys.exit(main())
