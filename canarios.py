#!/usr/bin/env python3
"""
canarios.py - Señuelos anti-ransomware
======================================
El ransomware domestico cifra por orden alfabetico y por carpetas de usuario.
Un archivo señuelo con un nombre que ordena primero es, por tanto, de los
primeros en caer, y eso da algo que ninguna copia de seguridad da: **tiempo**.
La diferencia entre reaccionar en tres segundos y en tres minutos son cientos
de archivos.

Como funciona:

  1. `desplegar()` deja un archivo canario en cada carpeta vigilada y guarda su
     huella (tamaño, fecha y sha256).
  2. `Canarios.vigilar()` comprueba cada pocos segundos si alguno cambio o
     desaparecio. Un canario tocado puede ser una casualidad; dos en menos de
     un minuto no lo es.
  3. Al dispararse: se corta la salida de red por firewall (reversible), se
     bloquea la sesion, se avisa por todos los canales y queda registrado.

Se corta con firewall y no desactivando adaptadores a proposito: es igual de
efectivo contra la exfiltracion, no deja el equipo sin red para siempre y se
revierte con una sola orden («restaura la red»).
"""
import hashlib
import json
import os
import threading
import time

NOMBRE_CANARIO = "__aaa_no_borrar_jarvis.docx"
PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
MANIFIESTO = os.path.join(PREFS, "canarios.json")
UMBRAL_TOCADOS = int(os.getenv("JARVIS_CANARIOS_UMBRAL", "2"))
VENTANA_S = int(os.getenv("JARVIS_CANARIOS_VENTANA", "60"))
INTERVALO_S = int(os.getenv("JARVIS_CANARIOS_INTERVALO", "5"))

CONTENIDO = (
    "Este archivo pertenece a JARVIS y no debe modificarse ni borrarse.\r\n"
    "Sirve de señuelo: si algo lo altera, JARVIS asume un cifrado masivo en "
    "curso, corta la red y bloquea el equipo.\r\n"
).encode("utf-8")


def _carpetas_por_defecto():
    hogar = os.path.expanduser("~")
    candidatas = ["Documentos", "Documents", "Escritorio", "Desktop",
                  "Imágenes", "Pictures", "Descargas", "Downloads"]
    vistas, salida = set(), []
    for nombre in candidatas:
        ruta = os.path.join(hogar, nombre)
        if os.path.isdir(ruta) and os.path.realpath(ruta) not in vistas:
            vistas.add(os.path.realpath(ruta))
            salida.append(ruta)
    return salida


def _huella(ruta: str) -> dict:
    with open(ruta, "rb") as f:
        datos = f.read()
    return {"sha256": hashlib.sha256(datos).hexdigest(),
            "tamano": len(datos),
            "mtime": round(os.path.getmtime(ruta), 2)}


# ── despliegue ──────────────────────────────────────────────────────────────
def desplegar(carpetas=None, log=print) -> str:
    carpetas = carpetas or _carpetas_por_defecto()
    os.makedirs(PREFS, exist_ok=True)
    manifiesto = {"creado": time.time(), "canarios": {}}
    puestos = 0
    for carpeta in carpetas:
        ruta = os.path.join(carpeta, NOMBRE_CANARIO)
        try:
            with open(ruta, "wb") as f:
                f.write(CONTENIDO)
            manifiesto["canarios"][ruta] = _huella(ruta)
            puestos += 1
        except Exception as e:
            log(f"[CANARIOS] No pude poner el señuelo en {carpeta}: {e}")
    try:
        with open(MANIFIESTO, "w", encoding="utf-8") as f:
            json.dump(manifiesto, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"[CANARIOS] No pude guardar el manifiesto: {e}")
    return (f"Señuelos desplegados en {puestos} carpetas, señor. "
            "Si algo empieza a cifrar sus archivos, lo sabré en segundos.")


def retirar(log=print) -> str:
    manifiesto = _leer_manifiesto()
    quitados = 0
    for ruta in manifiesto.get("canarios", {}):
        try:
            if os.path.exists(ruta):
                os.unlink(ruta)
                quitados += 1
        except Exception as e:
            log(f"[CANARIOS] No pude retirar {ruta}: {e}")
    try:
        if os.path.exists(MANIFIESTO):
            os.unlink(MANIFIESTO)
    except Exception:
        pass
    return f"Retirados {quitados} señuelos, señor."


def _leer_manifiesto() -> dict:
    try:
        with open(MANIFIESTO, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


# ── vigilancia ──────────────────────────────────────────────────────────────
class Canarios:
    """Vigila los señuelos y reacciona ante un cifrado masivo."""

    def __init__(self, core=None, log=print, intervalo: int = INTERVALO_S,
                 simulacro: bool = False):
        self.core = core
        self.log = log
        # simulacro=True: detecta y avisa, pero NO corta la red ni bloquea la
        # sesion. Sirve para comprobar que la alarma funciona sin quedarse
        # fuera del equipo, y es lo que usan las pruebas.
        self.simulacro = simulacro
        self.intervalo = max(2, intervalo)
        self._stop = threading.Event()
        self._hilo = None
        self._tocados = []          # [(ruta, momento)]
        self.disparado = False

    def start(self) -> str:
        manifiesto = _leer_manifiesto()
        if not manifiesto.get("canarios"):
            return ("No hay señuelos desplegados, señor. Dígame «despliega los "
                    "señuelos» y los coloco.")
        if self._hilo and self._hilo.is_alive():
            return "Ya estaba vigilando los señuelos, señor."
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        return (f"Vigilando {len(manifiesto['canarios'])} señuelos, señor. "
                f"Reviso cada {self.intervalo} segundos.")

    def stop(self):
        self._stop.set()

    def _bucle(self):
        while not self._stop.is_set():
            try:
                self.revisar()
            except Exception as e:
                self.log(f"[CANARIOS] Fallo revisando: {e}")
            self._stop.wait(self.intervalo)

    def revisar(self) -> list:
        """Devuelve la lista de señuelos alterados en esta pasada."""
        manifiesto = _leer_manifiesto()
        alterados = []
        ahora = time.time()
        for ruta, huella in (manifiesto.get("canarios") or {}).items():
            try:
                if not os.path.exists(ruta):
                    alterados.append((ruta, "borrado"))
                    continue
                actual = _huella(ruta)
                if actual["sha256"] != huella.get("sha256"):
                    alterados.append((ruta, "modificado"))
            except Exception:
                alterados.append((ruta, "ilegible"))

        for ruta, que in alterados:
            if not any(r == ruta for r, _t in self._tocados):
                self._tocados.append((ruta, ahora))
                self.log(f"[CANARIOS] Señuelo {que}: {ruta}")

        # Solo cuenta lo ocurrido dentro de la ventana: un archivo borrado por
        # el señor hace tres días no debe disparar nada.
        self._tocados = [(r, t) for r, t in self._tocados if ahora - t <= VENTANA_S]
        if len(self._tocados) >= UMBRAL_TOCADOS and not self.disparado:
            self.reaccionar([r for r, _t in self._tocados])
        return alterados

    # ── reacción ────────────────────────────────────────────────────────────
    def reaccionar(self, rutas) -> str:
        """Corta la red, bloquea el equipo y avisa. Es la parte que gana tiempo."""
        self.disparado = True
        detalle = f"{len(rutas)} señuelos alterados en menos de {VENTANA_S} s"
        self.log(f"[CANARIOS] ¡ALERTA! {detalle}")

        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                "ransomware", "Posible cifrado masivo en curso", detalle,
                gravedad="critica", datos="; ".join(rutas[:5]),
                agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass

        if self.simulacro:
            aviso = (f"SIMULACRO, señor: {detalle}. En una alerta real cortaría "
                     "la salida de red y bloquearía el equipo ahora mismo.")
            self._avisar(aviso)
            return aviso

        cortada = cortar_red(self.log)
        bloqueado = _bloquear_sesion(self.log)

        aviso = (f"Alerta máxima, señor: {detalle}. "
                 + ("He cortado la salida de red. " if cortada
                    else "No pude cortar la red (hace falta administrador). ")
                 + ("Bloqueo el equipo. " if bloqueado else "")
                 + "Revise sus archivos antes de restaurar la red.")
        self._avisar(aviso)
        return aviso

    def _avisar(self, texto: str):
        try:
            if self.core is not None and getattr(self.core, "tts_queue", None):
                self.core.tts_queue.put(texto)
        except Exception:
            pass
        try:
            from conectores import Notificador
            Notificador(notify=None, log=self.log).avisar("alerta de ransomware", texto)
        except Exception as e:
            self.log(f"[CANARIOS] No pude avisar fuera: {e}")

    def estado(self) -> dict:
        manifiesto = _leer_manifiesto()
        return {
            "desplegados": len(manifiesto.get("canarios", {})),
            "vigilando": bool(self._hilo and self._hilo.is_alive()),
            "intervalo_s": self.intervalo,
            "tocados_recientes": [r for r, _t in self._tocados],
            "disparado": self.disparado,
        }


# ── acciones de emergencia ──────────────────────────────────────────────────
def cortar_red(log=print) -> bool:
    """Bloquea todo el tráfico por firewall. Reversible con restaurar_red()."""
    import ejecutor
    res = ejecutor.ejecutar(
        "netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound",
        origen="canarios", orden="cortar la red por emergencia", log=log)
    if res["ok"]:
        try:
            import deshacer
            deshacer.anotar("comando", "corté la red por alerta de ransomware",
                            {"inverso": "netsh advfirewall set allprofiles "
                                        "firewallpolicy blockinbound,allowoutbound"},
                            log=log)
        except Exception:
            pass
    return res["ok"]


def restaurar_red(log=print) -> str:
    import ejecutor
    res = ejecutor.ejecutar(
        "netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound",
        origen="canarios", orden="restaurar la red", log=log)
    if res["ok"]:
        return "Red restaurada, señor. El tráfico vuelve a salir con normalidad."
    return f"No pude restaurar la red, señor: {res['error'][:120]} (hace falta administrador)."


def _bloquear_sesion(log=print) -> bool:
    import ejecutor
    ok, _error, _p = ejecutor.lanzar("rundll32.exe user32.dll,LockWorkStation",
                                     origen="canarios", orden="bloquear por emergencia",
                                     log=log)
    return ok
