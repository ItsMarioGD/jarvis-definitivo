#!/usr/bin/env python3
"""
demostracion.py - Aprender viendote hacerlo una vez
===================================================
Hasta ahora, enseñarle algo nuevo a JARVIS era escribir codigo (o pedirselo a
autoskills). Esto lo cambia: se le dice «mira lo que hago», se hace una vez, y
el lo convierte en una habilidad repetible.

    señor: «aprende esto» -> hace su rutina -> «ya esta»
    JARVIS: «he aprendido "informe del lunes": 7 pasos. ¿Lo llamo asi?»
    señor: «haz el informe del lunes»  -> lo repite solo

Que se graba
------------
Teclas, clics con su posicion, ventana activa en cada momento y las pausas.
No se graban las contraseñas: cuando la ventana activa parece un gestor de
claves o un campo de contraseña, se anota «(omitido)» y se sigue.

Como se reproduce
-----------------
Con el mismo raton y teclado que usa el piloto (pyautogui), respetando las
esperas y comprobando ANTES de cada paso que la ventana activa es la que
tocaba. Si no lo es, para y lo dice en vez de hacer clics a ciegas.

Requiere `pynput` para escuchar teclado y raton (ya viene con el proyecto).
"""
import ctypes
import json
import os
import re
import threading
import time

CARPETA = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Rutinas")
PAUSA_MAXIMA = float(os.getenv("JARVIS_DEMO_PAUSA_MAX", "4"))   # s entre pasos
MAX_PASOS = int(os.getenv("JARVIS_DEMO_PASOS", "120"))

# Ventanas donde NO se graba lo que se teclea.
_VENTANAS_SENSIBLES = ("keepass", "bitwarden", "1password", "lastpass", "banco",
                       "bank", "contraseñ", "password", "iniciar sesion",
                       "iniciar sesión", "login", "cartera", "wallet")


def _ventana_activa() -> str:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        largo = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(hwnd, buffer, largo + 1)
        return buffer.value or ""
    except Exception:
        return ""


def _sensible(titulo: str) -> bool:
    t = (titulo or "").lower()
    return any(p in t for p in _VENTANAS_SENSIBLES)


class Grabadora:
    """Escucha teclado y ratón hasta que el señor diga que ya está."""

    def __init__(self, log=print):
        self.log = log
        self.pasos = []
        self.grabando = False
        self._ultimo = 0.0
        self._teclado = None
        self._raton = None
        self._buffer_texto = ""

    # ── ciclo ───────────────────────────────────────────────────────────────
    def disponible(self):
        try:
            import pynput  # noqa: F401
        except Exception:
            return False, "falta pynput (pip install pynput)"
        try:
            import pyautogui  # noqa: F401
        except Exception:
            return False, "falta pyautogui, que hace falta para repetirlo"
        return True, ""

    def empezar(self) -> str:
        ok, motivo = self.disponible()
        if not ok:
            return f"No puedo aprender mirando, señor: {motivo}."
        if self.grabando:
            return "Ya estoy mirando, señor. Dígame «ya está» cuando termine."

        from pynput import keyboard, mouse
        self.pasos = []
        self._buffer_texto = ""
        self._ultimo = time.time()
        self.grabando = True

        self._teclado = keyboard.Listener(on_press=self._tecla)
        self._raton = mouse.Listener(on_click=self._clic, on_scroll=self._scroll)
        self._teclado.start()
        self._raton.start()
        self.log("[DEMO] Grabando la demostración.")
        return ("Le miro, señor. Haga la tarea a su ritmo y dígame «ya está» "
                "cuando termine. No apuntaré nada de ventanas de contraseñas.")

    def terminar(self) -> list:
        self.grabando = False
        self._volcar_texto()
        for oyente in (self._teclado, self._raton):
            try:
                if oyente:
                    oyente.stop()
            except Exception:
                pass
        self._teclado = self._raton = None
        self.log(f"[DEMO] Demostración terminada: {len(self.pasos)} pasos.")
        return self.pasos

    # ── captura ─────────────────────────────────────────────────────────────
    def _espera(self) -> float:
        ahora = time.time()
        espera = min(PAUSA_MAXIMA, max(0.0, ahora - self._ultimo))
        self._ultimo = ahora
        return round(espera, 2)

    def _anotar(self, paso: dict):
        if len(self.pasos) >= MAX_PASOS:
            return
        paso["ventana"] = _ventana_activa()[:120]
        paso["espera"] = self._espera()
        self.pasos.append(paso)

    def _volcar_texto(self):
        """El texto tecleado se guarda junto, no letra a letra."""
        if self._buffer_texto:
            texto = self._buffer_texto
            self._buffer_texto = ""
            self._anotar({"tipo": "escribir", "texto": texto})

    def _tecla(self, tecla):
        if not self.grabando:
            return
        from pynput import keyboard
        ventana = _ventana_activa()
        if _sensible(ventana):
            self._buffer_texto = ""
            self._anotar({"tipo": "omitido", "motivo": "ventana con credenciales"})
            return
        try:
            if hasattr(tecla, "char") and tecla.char:
                self._buffer_texto += tecla.char
                return
        except Exception:
            pass
        # Tecla especial: primero se vuelca lo escrito, luego la tecla.
        self._volcar_texto()
        nombre = str(tecla).replace("Key.", "")
        self._anotar({"tipo": "tecla", "tecla": nombre})

    def _clic(self, x, y, boton, presionado):
        if not self.grabando or not presionado:
            return
        self._volcar_texto()
        self._anotar({"tipo": "clic", "x": int(x), "y": int(y),
                      "boton": "derecho" if "right" in str(boton) else "izquierdo"})

    def _scroll(self, x, y, dx, dy):
        if not self.grabando:
            return
        self._volcar_texto()
        self._anotar({"tipo": "scroll", "x": int(x), "y": int(y), "cantidad": int(dy)})


# ── guardar y repetir ───────────────────────────────────────────────────────
def _ruta(nombre: str) -> str:
    limpio = re.sub(r"[^a-z0-9_]+", "_", (nombre or "rutina").lower()).strip("_")
    return os.path.join(CARPETA, f"{limpio or 'rutina'}.json")


def guardar(nombre: str, pasos: list, log=print) -> str:
    os.makedirs(CARPETA, exist_ok=True)
    ruta = _ruta(nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"nombre": nombre, "creada": time.strftime("%Y-%m-%d %H:%M"),
                   "pasos": pasos}, f, ensure_ascii=False, indent=2)
    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "rutina", f"Aprendida: {nombre}", f"{len(pasos)} pasos", gravedad="info")
    except Exception:
        pass
    return ruta


def listar() -> list:
    if not os.path.isdir(CARPETA):
        return []
    salida = []
    for archivo in sorted(os.listdir(CARPETA)):
        if not archivo.endswith(".json"):
            continue
        try:
            with open(os.path.join(CARPETA, archivo), encoding="utf-8") as f:
                d = json.load(f)
            salida.append({"nombre": d.get("nombre", archivo[:-5]),
                           "pasos": len(d.get("pasos", [])),
                           "creada": d.get("creada", "")})
        except Exception:
            continue
    return salida


def cargar(nombre: str) -> dict:
    ruta = _ruta(nombre)
    if not os.path.exists(ruta):
        # Búsqueda tolerante por palabras: nadie recuerda el nombre exacto, así
        # que «informe lunes» debe encontrar «informe del lunes».
        vacias = {"el", "la", "los", "las", "de", "del", "un", "una", "mi", "para"}
        pedidas = {p for p in re.split(r"\W+", (nombre or "").lower()) if p and p not in vacias}
        mejor, puntos = None, 0
        for r in listar():
            suyas = {p for p in re.split(r"\W+", r["nombre"].lower()) if p and p not in vacias}
            comunes = len(pedidas & suyas)
            if comunes > puntos:
                mejor, puntos = r["nombre"], comunes
        if mejor and puntos:
            ruta = _ruta(mejor)
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def repetir(nombre: str, log=print, velocidad: float = 1.0, seco: bool = False) -> str:
    """Reproduce una rutina aprendida. `seco=True` solo cuenta qué haría."""
    rutina = cargar(nombre)
    pasos = rutina.get("pasos") or []
    if not pasos:
        disponibles = ", ".join(r["nombre"] for r in listar()) or "ninguna"
        return (f"No conozco la rutina «{nombre}», señor. Tengo: {disponibles}.")

    if seco:
        resumen = []
        for p in pasos[:8]:
            if p["tipo"] == "clic":
                resumen.append(f"clic en ({p['x']},{p['y']})")
            elif p["tipo"] == "escribir":
                resumen.append(f"escribir «{p['texto'][:20]}»")
            elif p["tipo"] == "tecla":
                resumen.append(f"tecla {p['tecla']}")
        return (f"«{rutina['nombre']}» son {len(pasos)} pasos: "
                + "; ".join(resumen) + ("…" if len(pasos) > 8 else ""))

    try:
        import pyautogui
    except Exception as e:
        return f"No puedo repetirla, señor: falta pyautogui ({e})."
    pyautogui.FAILSAFE = True

    hechos = 0
    for i, paso in enumerate(pasos, 1):
        time.sleep(min(PAUSA_MAXIMA, paso.get("espera", 0.2)) / max(velocidad, 0.1))

        # Comprobación antes de actuar: si la ventana no es la de entonces, se
        # para. Hacer clics a ciegas en otra ventana es como se rompen cosas.
        esperada = (paso.get("ventana") or "").strip()
        actual = _ventana_activa()
        if esperada and actual and esperada[:25].lower() not in actual.lower():
            return (f"Me detengo en el paso {i} de «{rutina['nombre']}», señor: "
                    f"esperaba estar en «{esperada[:40]}» y estoy en «{actual[:40]}».")

        try:
            tipo = paso["tipo"]
            if tipo == "clic":
                if paso.get("boton") == "derecho":
                    pyautogui.rightClick(paso["x"], paso["y"])
                else:
                    pyautogui.click(paso["x"], paso["y"])
            elif tipo == "escribir":
                pyautogui.typewrite(paso["texto"], interval=0.015)
            elif tipo == "tecla":
                pyautogui.press(paso["tecla"])
            elif tipo == "scroll":
                pyautogui.scroll(paso.get("cantidad", 0) * 100, x=paso.get("x"),
                                 y=paso.get("y"))
            elif tipo == "omitido":
                return (f"El paso {i} era una ventana de credenciales, señor: "
                        "no lo grabé y no puedo repetirlo. Hágalo usted y dígame "
                        "«sigue» cuando esté.")
            hechos += 1
        except pyautogui.FailSafeException:
            return "Abortado por la esquina de pánico, señor."
        except Exception as e:
            return f"Fallé en el paso {i} de «{rutina['nombre']}», señor: {str(e)[:90]}"

    try:
        from storage import get_storage
        get_storage(log=log).registrar_accion(
            origen="rutina", orden=f"repetir {rutina['nombre']}",
            comando=f"{hechos} pasos", ok=True, detalle="", agente="JARVIS")
    except Exception:
        pass
    return f"«{rutina['nombre']}» repetida, señor: {hechos} pasos."


def resumen() -> str:
    rutinas = listar()
    if not rutinas:
        return ("No he aprendido ninguna rutina todavía, señor. Dígame «aprende "
                "esto», haga la tarea y dígame «ya está».")
    return "Rutinas que sé repetir, señor: " + "; ".join(
        f"«{r['nombre']}» ({r['pasos']} pasos)" for r in rutinas) + "."
