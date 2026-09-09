"""
comandos_voz.py — Comandos de voz de JARVIS y ULTRON
====================================================
Dos cosas en un solo modulo:

1. Un catalogo de comandos utiles listos para usar (rutinas que combinan
   varias acciones: «modo enfoque», «modo estudio», «modo reunion»...).
2. Un taller para que el señor invente los suyos: dice una frase, elige que
   tiene que pasar, y a partir de ese momento JARVIS o ULTRON lo ejecutan.

Se guarda todo en <Prefs>/comandos_voz.json para que sobreviva a reinicios y
lo compartan los dos agentes (el web, el movil, Telegram y el HUD).

Este despachador va el PRIMERO de la cadena: un comando del señor manda sobre
cualquier habilidad de fabrica con la misma frase.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
import uuid

try:
    import jarvis_config
    _PREFS = os.path.join(jarvis_config.JARVIS_DATA, "Prefs")
except Exception:                                            # pragma: no cover
    _PREFS = os.path.join(os.path.expanduser("~"), ".jarvis")
os.makedirs(_PREFS, exist_ok=True)

RUTA_JSON = os.getenv("JARVIS_COMANDOS_JSON") or os.path.join(_PREFS, "comandos_voz.json")

# Tipos de accion admitidos. El nombre es el que ve el señor en la interfaz.
TIPOS = {
    "decir":     "Solo responder (una frase)",
    "abrir":     "Abrir una web, un archivo o una carpeta",
    "programa":  "Ejecutar un programa",
    "shell":     "Ejecutar un comando del sistema",
    "teclas":    "Pulsar una combinacion de teclas",
    "escribir":  "Escribir un texto donde este el cursor",
    "agente":    "Pedirselo al propio agente (lenguaje natural)",
    "esperar":   "Esperar N segundos antes de la siguiente accion",
}

_IS_WIN = os.name == "nt"
_SIN_VENTANA = 0x08000000 if _IS_WIN else 0


# ─────────────────────────────────────────────────────────────────────────────
# Normalizacion y coincidencia
# ─────────────────────────────────────────────────────────────────────────────
def normalizar(texto: str) -> str:
    """Minusculas, sin tildes, sin signos y con los espacios colapsados.

    «¿Activas el MODO Enfoque, Jarvis?» -> «activas el modo enfoque»
    """
    t = unicodedata.normalize("NFD", str(texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.lower()
    t = re.sub(r"\b(jarvis|ultron)\b", " ", t)
    t = re.sub(r"[^a-z0-9ñ\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Muletillas que el señor suele poner delante de una orden. Se recortan para
# que «oye jarvis, activa el modo enfoque» dispare «modo enfoque».
_PREFIJOS = (
    "oye", "eh", "por favor", "porfa", "venga", "anda", "quiero que",
    "necesito que", "puedes", "podrias", "activa", "activar", "actives",
    "pon", "poner", "ponme", "haz", "hazme", "ejecuta", "ejecutar",
    "lanza", "lanzar", "inicia", "iniciar", "arranca", "dale", "el", "la",
)


def _variantes(frase_norm: str) -> list:
    """La frase tal cual y sin las muletillas de delante."""
    salida = [frase_norm]
    palabras = frase_norm.split()
    i = 0
    while i < len(palabras) and palabras[i] in _PREFIJOS:
        i += 1
        resto = " ".join(palabras[i:])
        if resto and resto not in salida:
            salida.append(resto)
    return salida


def coincide(texto_norm: str, frase: str) -> int:
    """Puntua como de bien encaja `frase` en `texto_norm`. 0 = no encaja.

    Se puntua por longitud para que, entre «modo enfoque» y «modo enfoque
    total», gane siempre la frase mas especifica.
    """
    f = normalizar(frase)
    if len(f) < 3:
        return 0
    for variante in _variantes(texto_norm):
        if variante == f:
            return 1000 + len(f)
        if variante.startswith(f + " "):
            return 500 + len(f)
        if re.search(r"(?:^|\s)" + re.escape(f) + r"(?:\s|$)", variante):
            return 100 + len(f)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Catalogo de fabrica
# ─────────────────────────────────────────────────────────────────────────────
def catalogo_inicial() -> list:
    """Comandos utiles que vienen puestos. Todos se pueden editar o borrar."""
    return [
        {
            "id": "modo-enfoque",
            "nombre": "Modo enfoque",
            "frases": ["modo enfoque", "modo concentracion", "necesito concentrarme"],
            "acciones": [
                {"tipo": "shell", "valor": "taskkill /F /IM Discord.exe /IM Telegram.exe /IM WhatsApp.exe"},
                {"tipo": "abrir", "valor": "https://pomofocus.io/"},
            ],
            "respuesta": "Modo enfoque, señor. Distracciones cerradas y temporizador en pantalla.",
            "agente": "ambos", "activo": True, "origen": "fabrica",
        },
        {
            "id": "modo-estudio",
            "nombre": "Modo estudio",
            "frases": ["modo estudio", "vamos a estudiar", "hora de estudiar"],
            "acciones": [
                {"tipo": "abrir", "valor": "https://music.youtube.com/playlist?list=RDCLAK5uy_kmPRjHDECIcuVwnKsx2Ng7fyNgFKWNJFs"},
                {"tipo": "esperar", "valor": "2"},
                {"tipo": "abrir", "valor": "https://docs.google.com/"},
            ],
            "respuesta": "Modo estudio activo. Musica de fondo y sus documentos abiertos.",
            "agente": "ambos", "activo": True, "origen": "fabrica",
        },
        {
            "id": "modo-reunion",
            "nombre": "Modo reunion",
            "frases": ["modo reunion", "tengo una reunion", "modo videollamada"],
            "acciones": [
                {"tipo": "agente", "valor": "silencia tu voz"},
                {"tipo": "abrir", "valor": "https://meet.google.com/"},
            ],
            "respuesta": "Modo reunion. Me callo y le dejo la sala abierta, señor.",
            "agente": "ambos", "activo": True, "origen": "fabrica",
        },
        {
            "id": "modo-desarrollo",
            "nombre": "Modo desarrollo",
            "frases": ["modo desarrollo", "modo programador", "vamos a programar"],
            "acciones": [
                {"tipo": "programa", "valor": "code"},
                {"tipo": "abrir", "valor": "https://github.com/"},
            ],
            "respuesta": "Entorno de desarrollo listo, señor.",
            "agente": "ambos", "activo": True, "origen": "fabrica",
        },
        {
            "id": "bloquear-equipo",
            "nombre": "Bloquear el equipo",
            "frases": ["bloquea el equipo", "cierra la sesion", "me voy un momento"],
            "acciones": [
                {"tipo": "shell", "valor": "rundll32.exe user32.dll,LockWorkStation"},
            ],
            "respuesta": "Equipo bloqueado. Aqui le espero, señor.",
            "agente": "ambos", "activo": True, "origen": "fabrica",
        },
        {
            "id": "estado-de-red",
            "nombre": "Estado de la red",
            "frases": ["estado de la red", "como esta la conexion", "dame la direccion del movil"],
            "acciones": [{"tipo": "interno", "valor": "red"}],
            "respuesta": "",
            "agente": "ambos", "activo": True, "origen": "fabrica",
        },
        {
            "id": "captura-al-portapapeles",
            "nombre": "Recorte de pantalla",
            "frases": ["quiero recortar la pantalla", "abre el recorte"],
            "acciones": [{"tipo": "teclas", "valor": "win+shift+s"}],
            "respuesta": "Recorte listo, señor. Seleccione la zona.",
            "agente": "ambos", "activo": True, "origen": "fabrica",
        },
        {
            "id": "informe-ultron",
            "nombre": "Informe de guardia",
            "frases": ["informe de guardia", "que has vigilado"],
            "acciones": [{"tipo": "agente", "valor": "dame el estado del sistema y de la red"}],
            "respuesta": "",
            "agente": "ultron", "activo": True, "origen": "fabrica",
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Almacen
# ─────────────────────────────────────────────────────────────────────────────
class AlmacenComandos:
    """Lee y escribe comandos_voz.json. Seguro entre hilos y procesos."""

    def __init__(self, ruta: str = RUTA_JSON, log=print):
        self.ruta = ruta
        self.log = log
        self._lock = threading.RLock()
        self._cache = None
        self._mtime = 0.0

    # ── disco ──
    def _leer_disco(self) -> dict:
        try:
            with open(self.ruta, "r", encoding="utf-8-sig") as f:
                datos = json.load(f)
            if isinstance(datos, list):                     # formato antiguo
                datos = {"version": 1, "comandos": datos}
            datos.setdefault("comandos", [])
            return datos
        except FileNotFoundError:
            datos = {"version": 1, "comandos": catalogo_inicial()}
            self._escribir_disco(datos)
            return datos
        except Exception as e:
            self.log(f"[comandos] {os.path.basename(self.ruta)} ilegible ({e}); "
                     f"arranco con el catalogo de fabrica.")
            return {"version": 1, "comandos": catalogo_inicial()}

    def _escribir_disco(self, datos: dict):
        tmp = self.ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.ruta)
        try:
            self._mtime = os.path.getmtime(self.ruta)
        except OSError:
            self._mtime = 0.0
        self._cache = datos

    def _fresco(self) -> dict:
        """Recarga si otro proceso (el movil, el bot) toco el fichero."""
        with self._lock:
            try:
                mtime = os.path.getmtime(self.ruta)
            except OSError:
                mtime = 0.0
            if self._cache is None or mtime != self._mtime:
                self._cache = self._leer_disco()
                self._mtime = mtime
            return self._cache

    # ── API ──
    def listar(self, agente: str = "") -> list:
        cmds = list(self._fresco().get("comandos", []))
        if agente:
            cmds = [c for c in cmds if c.get("agente", "ambos") in ("ambos", agente)]
        return cmds

    def obtener(self, cid: str):
        return next((c for c in self.listar() if c.get("id") == cid), None)

    def guardar(self, comando: dict) -> dict:
        """Alta o modificacion. Devuelve el comando ya normalizado."""
        limpio = self._normalizar_comando(comando)
        with self._lock:
            datos = self._fresco()
            cmds = datos.setdefault("comandos", [])
            for i, c in enumerate(cmds):
                if c.get("id") == limpio["id"]:
                    limpio["usos"] = c.get("usos", 0)
                    limpio["creado"] = c.get("creado", limpio["creado"])
                    cmds[i] = limpio
                    break
            else:
                cmds.append(limpio)
            self._escribir_disco(datos)
        return limpio

    def borrar(self, cid: str) -> bool:
        with self._lock:
            datos = self._fresco()
            antes = len(datos.get("comandos", []))
            datos["comandos"] = [c for c in datos.get("comandos", []) if c.get("id") != cid]
            if len(datos["comandos"]) == antes:
                return False
            self._escribir_disco(datos)
            return True

    def restaurar_fabrica(self) -> list:
        """Devuelve los comandos de fabrica sin tocar los del señor."""
        with self._lock:
            datos = self._fresco()
            propios = [c for c in datos.get("comandos", []) if c.get("origen") != "fabrica"]
            datos["comandos"] = catalogo_inicial() + propios
            self._escribir_disco(datos)
            return datos["comandos"]

    def anotar_uso(self, cid: str):
        with self._lock:
            datos = self._fresco()
            for c in datos.get("comandos", []):
                if c.get("id") == cid:
                    c["usos"] = int(c.get("usos", 0)) + 1
                    c["ultimo_uso"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    self._escribir_disco(datos)
                    return

    # ── validacion ──
    @staticmethod
    def _normalizar_comando(c: dict) -> dict:
        frases = c.get("frases")
        if isinstance(frases, str):
            frases = [frases]
        frases = [str(f).strip() for f in (frases or []) if str(f).strip()]
        if not frases:
            raise ValueError("Un comando necesita al menos una frase que lo dispare.")
        if any(len(normalizar(f)) < 3 for f in frases):
            raise ValueError("Las frases muy cortas dispararian sin querer: use tres letras o mas.")

        acciones = c.get("acciones")
        if not acciones and c.get("tipo"):                   # forma corta
            acciones = [{"tipo": c["tipo"], "valor": c.get("valor", "")}]
        acciones = [a for a in (acciones or []) if isinstance(a, dict) and a.get("tipo")]
        for a in acciones:
            if a["tipo"] not in TIPOS and a["tipo"] != "interno":
                raise ValueError(f"No se que es una accion de tipo «{a['tipo']}».")
            a["valor"] = str(a.get("valor", "")).strip()
        respuesta = str(c.get("respuesta", "")).strip()
        if not acciones and not respuesta:
            raise ValueError("El comando no hace nada: dele una accion o una respuesta.")

        agente = c.get("agente", "ambos")
        if agente not in ("ambos", "jarvis", "ultron"):
            agente = "ambos"
        return {
            "id": str(c.get("id") or uuid.uuid4().hex[:10]),
            "nombre": str(c.get("nombre") or frases[0]).strip()[:60],
            "frases": frases[:8],
            "acciones": acciones[:12],
            "respuesta": respuesta[:400],
            "agente": agente,
            "activo": bool(c.get("activo", True)),
            "origen": c.get("origen", "usuario"),
            "creado": c.get("creado") or time.strftime("%Y-%m-%d %H:%M:%S"),
            "usos": int(c.get("usos", 0) or 0),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Ejecutor + despachador
# ─────────────────────────────────────────────────────────────────────────────
class ComandosVoz:
    """Despachador de comandos de voz. Se engancha a JarvisCore y a UltronCore.

    Uso:
        self.comandos = ComandosVoz(core=self, log=self.log)
        respuesta = self.comandos.handle("modo enfoque")   # None si no encaja
    """

    def __init__(self, core=None, log=print, almacen: AlmacenComandos = None,
                 agente: str = ""):
        self.core = core
        self.log = log
        self.almacen = almacen or AlmacenComandos(log=log)
        self.agente = (agente or getattr(core, "nombre_agente", "JARVIS") or "JARVIS").lower()
        if self.agente not in ("jarvis", "ultron"):
            self.agente = "ultron" if "ultron" in self.agente else "jarvis"

    # ── entrada del nucleo ──
    def handle(self, texto: str):
        """Devuelve la respuesta si alguna frase encaja; None para seguir la cadena."""
        if not texto or not str(texto).strip():
            return None
        gestion = self._gestion(texto)
        if gestion:
            return gestion

        cmd = self.buscar(texto)
        if not cmd:
            return None
        return self.ejecutar(cmd)

    def buscar(self, texto: str):
        """El comando con la frase mas especifica que encaje, o None."""
        t = normalizar(texto)
        if not t:
            return None
        mejor, punto_mejor = None, 0
        for c in self.almacen.listar(self.agente):
            if not c.get("activo", True):
                continue
            for frase in c.get("frases", []):
                p = coincide(t, frase)
                if p > punto_mejor:
                    mejor, punto_mejor = c, p
        return mejor

    # ── ejecucion ──
    def ejecutar(self, cmd: dict) -> str:
        partes, fallos = [], []
        for accion in cmd.get("acciones", []):
            try:
                r = self._una_accion(accion)
                if r:
                    partes.append(r)
            except Exception as e:
                fallos.append(f"{accion.get('tipo')}: {type(e).__name__}: {str(e)[:90]}")
                self.log(f"[comandos] «{cmd.get('nombre')}» fallo en "
                         f"{accion.get('tipo')} → {e}")
        try:
            self.almacen.anotar_uso(cmd["id"])
        except Exception:
            pass

        respuesta = cmd.get("respuesta", "").strip()
        if partes:
            respuesta = (respuesta + " " + " ".join(partes)).strip() if respuesta else " ".join(partes)
        if fallos:
            aviso = ("No pude completar todo: " if self.agente == "ultron"
                     else "Señor, algo no salio: ") + "; ".join(fallos)
            respuesta = (respuesta + " " + aviso).strip()
        if not respuesta:
            respuesta = (f"Hecho: {cmd.get('nombre')}." if self.agente == "ultron"
                         else f"Hecho, señor: {cmd.get('nombre')}.")
        return respuesta

    def _una_accion(self, accion: dict):
        tipo = accion.get("tipo")
        valor = str(accion.get("valor", "")).strip()

        if tipo == "decir":
            return valor
        if tipo == "esperar":
            try:
                time.sleep(max(0.0, min(30.0, float(valor or 1))))
            except ValueError:
                time.sleep(1)
            return None
        if tipo == "abrir":
            return self._abrir(valor)
        if tipo == "programa":
            return self._programa(valor)
        if tipo == "shell":
            return self._shell(valor)
        if tipo == "teclas":
            return self._teclas(valor)
        if tipo == "escribir":
            return self._escribir(valor)
        if tipo == "agente":
            return self._al_agente(valor)
        if tipo == "interno":
            return self._interno(valor)
        raise ValueError(f"accion desconocida «{tipo}»")

    # ── implementaciones ──
    @staticmethod
    def _abrir(destino: str):
        if not destino:
            raise ValueError("no dijo que abrir")
        if re.match(r"^[a-z][a-z0-9+.-]*://", destino, re.I) or destino.startswith("www."):
            url = destino if "://" in destino else "https://" + destino
            import webbrowser
            webbrowser.open(url)
            return None
        ruta = os.path.expandvars(os.path.expanduser(destino))
        if _IS_WIN:
            os.startfile(ruta)                              # noqa: S606  (Windows)
        else:
            subprocess.Popen(["xdg-open", ruta])
        return None

    @staticmethod
    def _programa(cmd: str):
        if not cmd:
            raise ValueError("no dijo que programa")
        import shlex
        partes = shlex.split(cmd, posix=not _IS_WIN)
        subprocess.Popen(partes, shell=False,
                         creationflags=_SIN_VENTANA if _IS_WIN else 0)
        return None

    def _shell(self, cmd: str):
        if not cmd:
            raise ValueError("no dijo que comando")
        if _IS_WIN:
            proc = subprocess.run(["cmd", "/c", cmd], capture_output=True, text=True,
                                  timeout=90, creationflags=_SIN_VENTANA)
        else:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=90)
        salida = (proc.stdout or "").strip()
        # taskkill devuelve 128 si el programa ni siquiera estaba abierto: eso
        # no es un fallo del comando del señor, es que ya no habia nada que cerrar.
        if proc.returncode not in (0, 128) and not salida:
            err = (proc.stderr or "").strip()[:140]
            raise RuntimeError(err or f"codigo {proc.returncode}")
        return salida[:300] or None

    def _teclas(self, combo: str):
        if not combo:
            raise ValueError("no dijo que teclas")
        teclas = [t.strip().lower() for t in re.split(r"[+\s]+", combo) if t.strip()]
        pc = getattr(self.core, "pc", None)
        for nombre in ("pulsar_teclas", "hotkey", "enviar_teclas"):
            fn = getattr(pc, nombre, None)
            if callable(fn):
                fn("+".join(teclas))
                return None
        try:
            import pyautogui
            pyautogui.hotkey(*teclas)
            return None
        except ImportError:
            pass
        try:
            import keyboard
            keyboard.press_and_release("+".join(teclas))
            return None
        except ImportError:
            raise RuntimeError("no hay pyautogui ni keyboard instalados para pulsar teclas")

    def _escribir(self, texto: str):
        if not texto:
            raise ValueError("no dijo que escribir")
        pc = getattr(self.core, "pc", None)
        for nombre in ("escribir", "teclear", "dictar"):
            fn = getattr(pc, nombre, None)
            if callable(fn):
                fn(texto)
                return None
        dictar = getattr(self.core, "dictar", None)
        if callable(dictar):
            dictar(texto)
            return None
        try:
            import pyautogui
            pyautogui.typewrite(texto, interval=0.01)
            return None
        except ImportError:
            raise RuntimeError("no hay forma de escribir: falta pyautogui")

    def _al_agente(self, orden: str):
        """Reinyecta la orden en el nucleo saltando este despachador.

        skip_comandos evita el bucle infinito de un comando que se llama a si
        mismo, y skip_skills=False deja que la orden llegue a las habilidades.
        """
        if not orden:
            raise ValueError("no dijo que pedirme")
        if self.core is None:
            raise RuntimeError("sin nucleo conectado")
        fn = getattr(self.core, "process_text_stream", None)
        if not callable(fn):
            raise RuntimeError("el nucleo no tiene process_text_stream")
        anterior = getattr(self.core, "_saltar_comandos_voz", False)
        self.core._saltar_comandos_voz = True
        try:
            return (fn(orden, speak_server=False) or "").strip()[:600] or None
        finally:
            self.core._saltar_comandos_voz = anterior

    def _interno(self, clave: str):
        if clave == "red":
            return self.resumen_de_red()
        raise ValueError(f"accion interna desconocida «{clave}»")

    # ── extras ──
    @staticmethod
    def resumen_de_red() -> str:
        """IP local, IP de Tailscale y la direccion que hay que abrir en el movil."""
        try:
            from tailscale_setup import resumen_texto
            return resumen_texto()
        except Exception:
            pass
        try:
            import jarvis_config as jc
            return (f"Direccion para el movil: http://{jc.LOCAL_IP}:{jc.PORT}/mobile "
                    f"(Tailscale no esta disponible).")
        except Exception as e:
            return f"No pude leer el estado de la red: {str(e)[:100]}"

    # ── el señor crea comandos hablando ──
    _RE_CREAR = re.compile(
        r"^(?:aprende|crea|añade|anade|agrega|guarda)\s+(?:un\s+|el\s+)?"
        r"(?:nuevo\s+)?comando\b(?:\s+(?:de\s+voz|nuevo))?\s*[:,]?\s*(.*)$", re.I)
    _RE_LISTAR = re.compile(
        r"^(?:que|cuales|dime|lista|listar|muestra|enumera)\b.*\bcomandos\b", re.I)
    _RE_OLVIDAR = re.compile(
        r"^(?:olvida|borra|elimina|quita)\s+(?:el\s+)?comando\s+(.+)$", re.I)

    def _gestion(self, texto: str):
        """«que comandos tienes», «olvida el comando X», «crea un comando...»."""
        t = str(texto).strip()

        if self._RE_LISTAR.match(t):
            cmds = [c for c in self.almacen.listar(self.agente) if c.get("activo", True)]
            if not cmds:
                return "Aun no hay comandos guardados, señor."
            lineas = [f"• {c['nombre']}: «{c['frases'][0]}»" for c in cmds[:25]]
            cab = (f"Tengo {len(cmds)} comandos listos:" if self.agente == "ultron"
                   else f"Señor, tengo {len(cmds)} comandos preparados:")
            return cab + "\n" + "\n".join(lineas)

        m = self._RE_OLVIDAR.match(t)
        if m:
            objetivo = normalizar(m.group(1))
            for c in self.almacen.listar():
                if normalizar(c["nombre"]) == objetivo or \
                        any(normalizar(f) == objetivo for f in c["frases"]):
                    self.almacen.borrar(c["id"])
                    return f"Comando «{c['nombre']}» olvidado, señor."
            return f"No encuentro ningun comando llamado «{m.group(1)}», señor."

        m = self._RE_CREAR.match(t)
        if m:
            return self._crear_hablando(m.group(1))
        return None

    _RE_RECETA = re.compile(
        r"^(?:cuando\s+(?:diga|te\s+diga)\s+)?[«\"']?(?P<frase>.+?)[»\"']?\s+"
        r"(?:entonces\s+)?(?:abre|abrir)\s+(?P<url>\S+)\s*$", re.I)

    def _crear_hablando(self, resto: str) -> str:
        """Alta rapida por voz: «crea un comando: cuando diga X abre Y»."""
        resto = (resto or "").strip()
        if not resto:
            return ("Digame la receta completa, señor. Por ejemplo: «crea un comando: "
                    "cuando diga radio, abre open.spotify.com». Para algo mas elaborado, "
                    "use el taller de comandos de la interfaz.")
        m = self._RE_RECETA.match(resto)
        if not m:
            return ("No he sabido leer esa receta, señor. El formato es «cuando diga "
                    "<frase>, abre <direccion>». Para comandos con varias acciones, "
                    "abra el taller de comandos en la interfaz.")
        frase = m.group("frase").strip(" ,.")
        destino = m.group("url").strip(" ,.")
        try:
            cmd = self.almacen.guardar({
                "nombre": frase.title(),
                "frases": [frase],
                "acciones": [{"tipo": "abrir", "valor": destino}],
                "respuesta": f"Abriendo {destino}, señor.",
                "agente": "ambos",
            })
        except ValueError as e:
            return f"No pude guardarlo, señor: {e}"
        return (f"Aprendido, señor. A partir de ahora, cuando diga «{frase}» "
                f"abrire {destino}. (Comando «{cmd['nombre']}».)")


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades para las interfaces web
# ─────────────────────────────────────────────────────────────────────────────
_ALMACEN_GLOBAL = None


def almacen() -> AlmacenComandos:
    """Un unico almacen compartido por el servidor web."""
    global _ALMACEN_GLOBAL
    if _ALMACEN_GLOBAL is None:
        _ALMACEN_GLOBAL = AlmacenComandos()
    return _ALMACEN_GLOBAL


if __name__ == "__main__":                                   # prueba manual
    cv = ComandosVoz(log=print)
    consulta = " ".join(sys.argv[1:]) or "que comandos tienes"
    print(cv.handle(consulta) or "(ningun comando encaja)")
