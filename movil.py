#!/usr/bin/env python3
"""
movil.py - El movil como una extension mas del asistente
========================================================
JARVIS vive dentro del PC. En cuanto el señor sale de la silla, deja de existir.
Esto lo saca de ahi: el telefono Android conectado por USB (o por WiFi) pasa a
ser otro periferico mas, igual que el raton o la pantalla.

Lo que permite
--------------
    «que bateria tiene mi movil»           lee el estado del telefono
    «que notificaciones tengo»             las del movil, no las del PC
    «donde esta mi movil»                  lo hace sonar aunque este en silencio
    «abre spotify en el movil»             lanza una app
    «mandale un whatsapp a Ana: llego tarde»   redacta y PIDE CONFIRMACION
    «avisame cuando me escriba el banco»   dispara una regla al llegar el aviso

Como se conecta
---------------
Por ADB (Android Debug Bridge), que es la via oficial de Google y no requiere
root ni cuentas ni servidores intermedios: todo se queda entre el PC y el
telefono por cable, o por WiFi si el señor lo empareja.

    1. Ajustes > Informacion > pulsar 7 veces «Numero de compilacion»
    2. Ajustes > Opciones de desarrollador > Depuracion USB
    3. Conectar el cable y aceptar la huella del PC en el telefono

Sin ADB instalado el modulo no falla: dice que falta y como ponerlo.

Sobre mandar mensajes
---------------------
Enviar un WhatsApp en nombre del señor no es reversible: se prepara el mensaje,
se enseña TAL CUAL va a salir y solo se envia si el señor lo confirma. Nunca se
manda un mensaje redactado por el modelo sin que lo haya leido antes.
"""
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse

ADB = os.getenv("JARVIS_ADB", "") or shutil.which("adb") or ""
TIMEOUT = int(os.getenv("JARVIS_ADB_TIMEOUT", "12"))

# Apps por nombre corriente, que nadie dice «com.spotify.music».
APPS = {
    "whatsapp": "com.whatsapp",
    "spotify": "com.spotify.music",
    "youtube": "com.google.android.youtube",
    "telegram": "org.telegram.messenger",
    "instagram": "com.instagram.android",
    "gmail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps",
    "camara": "com.android.camera",
    "chrome": "com.android.chrome",
    "ajustes": "com.android.settings",
}


# ── hablar con el telefono ──────────────────────────────────────────────────
def _adb(*args, timeout: int = TIMEOUT) -> tuple:
    """Ejecuta adb y devuelve (ok, salida). Nunca lanza excepcion."""
    if not ADB:
        return False, "no hay adb"
    try:
        r = subprocess.run([ADB, *args], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        salida = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, salida.strip()
    except subprocess.TimeoutExpired:
        return False, "el telefono no respondio a tiempo"
    except Exception as e:
        return False, str(e)[:150]


def _shell(orden: str, timeout: int = TIMEOUT) -> str:
    ok, salida = _adb("shell", orden, timeout=timeout)
    return salida if ok else ""


def disponible() -> tuple:
    """(hay_movil, explicacion)."""
    if not ADB:
        return False, ("no tengo adb instalado. Se pone con «winget install "
                       "Google.PlatformTools» o descargando las Platform Tools "
                       "de Android")
    ok, salida = _adb("devices")
    if not ok:
        return False, f"adb no responde ({salida[:60]})"
    lineas = [l for l in salida.splitlines()[1:] if l.strip()]
    conectados = [l.split("\t")[0] for l in lineas if l.endswith("device")]
    sin_permiso = [l for l in lineas if l.endswith("unauthorized")]
    if sin_permiso:
        return False, ("el teléfono está conectado pero no ha aceptado la huella "
                       "del PC: desbloquéelo y acepte el aviso de depuración USB")
    if not conectados:
        return False, ("no veo ningún teléfono. Conecte el cable con la "
                       "depuración USB activada")
    return True, conectados[0]


def emparejar_wifi(ip: str = "", puerto: str = "5555", log=print) -> str:
    """Deja el telefono conectado sin cable. Hay que hacerlo una vez con cable."""
    hay, quien = disponible()
    if not hay and not ip:
        return f"Conecte primero el cable, señor: {quien}."
    if not ip:
        _adb("tcpip", puerto)
        time.sleep(2)
        salida = _shell("ip route")
        m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", salida)
        if not m:
            return "No consigo la IP del teléfono, señor. Mírela en Ajustes > WiFi."
        ip = m.group(1)
    ok, salida = _adb("connect", f"{ip}:{puerto}")
    if ok and "connected" in salida.lower():
        return (f"Teléfono emparejado por WiFi en {ip}, señor. Ya puede quitar el "
                "cable; mientras estén en la misma red le sigo llegando.")
    return f"No pude emparejarlo, señor: {salida[:100]}"


# ── estado del telefono ─────────────────────────────────────────────────────
def bateria() -> dict:
    salida = _shell("dumpsys battery")
    if not salida:
        return {}
    def campo(nombre, por_defecto=""):
        m = re.search(rf"{nombre}: *(\S+)", salida)
        return m.group(1) if m else por_defecto
    nivel = campo("level", "0")
    return {
        "nivel": int(nivel) if nivel.isdigit() else 0,
        "cargando": campo("AC powered") == "true" or campo("USB powered") == "true",
        "temperatura": round(int(campo("temperature", "0")) / 10, 1),
        "salud": campo("health", ""),
    }


def notificaciones(limite: int = 8) -> list:
    """Lo que hay en la barra de notificaciones, en claro."""
    salida = _shell("dumpsys notification --noredact")
    if not salida:
        return []
    avisos, actual = [], {}
    for linea in salida.splitlines():
        m_paq = re.search(r"pkg=(\S+)", linea)
        if m_paq:
            if actual.get("texto"):
                avisos.append(actual)
            actual = {"app": m_paq.group(1).split(".")[-1], "titulo": "", "texto": ""}
        m_tit = re.search(r"android\.title=(?:String \()?([^)\n]+)", linea)
        if m_tit and actual:
            actual["titulo"] = m_tit.group(1).strip()[:80]
        m_txt = re.search(r"android\.text=(?:String \()?([^)\n]+)", linea)
        if m_txt and actual:
            actual["texto"] = m_txt.group(1).strip()[:140]
    if actual.get("texto"):
        avisos.append(actual)

    # Las del sistema no le interesan a nadie.
    ruido = ("android", "systemui", "settings", "providers")
    limpias = [a for a in avisos if a["app"] not in ruido]
    vistas, salida_final = set(), []
    for a in limpias:
        huella = (a["titulo"], a["texto"])
        if huella in vistas:
            continue
        vistas.add(huella)
        salida_final.append(a)
    return salida_final[:limite]


def ubicacion() -> dict:
    """Ultima posicion conocida. Solo la que el telefono ya tenia."""
    salida = _shell("dumpsys location")
    m = re.search(r"(-?\d+\.\d{4,}),\s*(-?\d+\.\d{4,})", salida or "")
    if not m:
        return {}
    return {"lat": float(m.group(1)), "lon": float(m.group(2))}


def estado() -> dict:
    hay, quien = disponible()
    if not hay:
        return {"conectado": False, "motivo": quien}
    return {"conectado": True, "dispositivo": quien, "bateria": bateria(),
            "notificaciones": len(notificaciones()), "adb": ADB}


def resumen() -> str:
    e = estado()
    if not e["conectado"]:
        return f"No tengo el teléfono a mano, señor: {e['motivo']}."
    b = e.get("bateria") or {}
    trozos = [f"Teléfono conectado ({e['dispositivo']}), señor"]
    if b:
        trozos.append(f"batería al {b['nivel']}%"
                      + (" cargando" if b["cargando"] else "")
                      + (f", a {b['temperatura']} grados" if b["temperatura"] else ""))
    if e["notificaciones"]:
        trozos.append(f"{e['notificaciones']} notificaciones sin ver")
    return ". ".join(trozos) + "."


# ── acciones ────────────────────────────────────────────────────────────────
def abrir_app(nombre: str) -> str:
    hay, quien = disponible()
    if not hay:
        return f"No tengo el teléfono, señor: {quien}."
    clave = (nombre or "").strip().lower()
    paquete = APPS.get(clave)
    if not paquete:
        # Buscar entre lo instalado: «abre el banco» no esta en la lista corta.
        instaladas = _shell("pm list packages")
        for linea in instaladas.splitlines():
            p = linea.replace("package:", "").strip()
            if clave and clave in p.lower():
                paquete = p
                break
    if not paquete:
        return f"No encuentro «{nombre}» en el teléfono, señor."
    ok, salida = _adb("shell", "monkey", "-p", paquete, "-c",
                      "android.intent.category.LAUNCHER", "1")
    if ok and "injected" in salida.lower():
        return f"{nombre.capitalize()} abierto en el teléfono, señor."
    return f"No pude abrirlo, señor: {salida[:90]}"


def encontrar(segundos: int = 12) -> str:
    """Hace sonar el telefono aunque este en silencio."""
    hay, quien = disponible()
    if not hay:
        return f"No puedo hacerlo sonar, señor: {quien}."
    _shell("media volume --show --stream 3 --set 15")
    ok = _shell("am start -a android.intent.action.VIEW -d "
                "content://settings/system/ringtone -t audio/*")
    if not ok:
        # Segundo intento: la alarma es mas fiable que el tono.
        _shell("am start -a android.intent.action.SET_ALARM "
               "--ei android.intent.extra.alarm.HOUR 0 "
               "--ei android.intent.extra.alarm.MINUTES 0 "
               "--ez android.intent.extra.alarm.SKIP_UI true")
    return ("Subo el volumen y lo hago sonar, señor. Si no lo oye, mire la "
            "última posición con «dónde está mi móvil».")


def preparar_whatsapp(contacto: str, mensaje: str) -> dict:
    """Deja el mensaje escrito en pantalla. NO lo envia."""
    hay, quien = disponible()
    if not hay:
        return {"ok": False, "frase": f"No tengo el teléfono, señor: {quien}."}
    if not mensaje.strip():
        return {"ok": False, "frase": "¿Qué le digo, señor?"}
    destino = (contacto or "").strip()
    texto = urllib.parse.quote(mensaje.strip())
    if re.fullmatch(r"\+?\d[\d ]{6,}", destino):
        numero = re.sub(r"\D", "", destino)
        url = f"https://wa.me/{numero}?text={texto}"
    else:
        # Sin numero solo se puede abrir el chat y dejarlo escrito a mano.
        url = f"https://wa.me/?text={texto}"
    _shell(f'am start -a android.intent.action.VIEW -d "{url}" '
           "com.whatsapp", timeout=15)
    return {"ok": True, "mensaje": mensaje.strip(), "contacto": destino,
            "frase": (f"Mensaje preparado en WhatsApp para {destino or 'quien elija'}, "
                      f"señor: «{mensaje.strip()}». Está escrito y sin enviar: "
                      "dígame «envíalo» y le doy al botón, o cámbielo usted.")}


def enviar_preparado() -> str:
    """Pulsa el boton de enviar. Solo despues de que el señor lo confirme."""
    hay, quien = disponible()
    if not hay:
        return f"No tengo el teléfono, señor: {quien}."
    # El intro del teclado envia el mensaje en el chat de WhatsApp.
    _shell("input keyevent 66")
    return "Enviado, señor."


# ── reglas: que el movil despierte al PC ────────────────────────────────────
class Puente:
    """Vigila las notificaciones del telefono y dispara reglas del señor.

    Una regla es «cuando llegue algo de X, avisame» o «...y haz Y». Se comprueba
    cada pocos segundos y solo con el telefono conectado; sin telefono, el hilo
    duerme y no gasta nada.
    """

    def __init__(self, core, log=print, intervalo: int = 20):
        self.core = core
        self.log = log
        self.intervalo = max(10, intervalo)
        self.reglas = []          # [{"filtro": str, "accion": str}]
        self._stop = threading.Event()
        self._hilo = None
        self._vistas = set()
        self.disparos = 0

    def añadir(self, filtro: str, accion: str = "") -> str:
        filtro = (filtro or "").strip().lower()
        if not filtro:
            return "¿De qué quiere que le avise, señor?"
        self.reglas.append({"filtro": filtro, "accion": accion.strip()})
        self._guardar()
        cola = f" y {accion}" if accion else ""
        return (f"Anotado, señor: cuando el teléfono reciba algo de «{filtro}» "
                f"se lo digo{cola}.")

    def quitar(self, filtro: str) -> str:
        antes = len(self.reglas)
        f = (filtro or "").strip().lower()
        self.reglas = [r for r in self.reglas if f not in r["filtro"]]
        self._guardar()
        if len(self.reglas) == antes:
            return f"No tenía ningún aviso para «{filtro}», señor."
        return f"Quitado el aviso de «{filtro}», señor."

    def _guardar(self):
        try:
            import json
            self.core.set_pref("movil_reglas", json.dumps(self.reglas))
        except Exception:
            pass

    def cargar(self):
        try:
            import json
            guardadas = self.core.get_pref("movil_reglas") or ""
            if guardadas:
                self.reglas = json.loads(guardadas)
        except Exception:
            self.reglas = []
        return self.reglas

    def start(self) -> str:
        hay, quien = disponible()
        if not hay:
            return f"No puedo vigilar el teléfono, señor: {quien}."
        if self._hilo and self._hilo.is_alive():
            return "Ya estoy pendiente del teléfono, señor."
        self.cargar()
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        try:
            self.core.set_pref("movil_puente", "1")
        except Exception:
            pass
        return ("Pendiente del teléfono, señor. Le aviso de lo que me haya pedido "
                "y de nada más.")

    def stop(self) -> str:
        self._stop.set()
        try:
            self.core.set_pref("movil_puente", "0")
        except Exception:
            pass
        return "Dejo de mirar el teléfono, señor."

    def _bucle(self):
        while not self._stop.is_set():
            try:
                self.ronda()
            except Exception as e:
                self.log(f"[MOVIL] {e}")
            self._stop.wait(self.intervalo)

    def ronda(self) -> list:
        if not self.reglas:
            return []
        disparadas = []
        for aviso in notificaciones(limite=15):
            texto = f"{aviso['app']} {aviso['titulo']} {aviso['texto']}".lower()
            huella = (aviso["titulo"], aviso["texto"])
            if huella in self._vistas:
                continue
            for regla in self.reglas:
                if regla["filtro"] in texto:
                    self._vistas.add(huella)
                    disparadas.append((regla, aviso))
                    break
        if len(self._vistas) > 400:
            self._vistas = set(list(self._vistas)[-200:])

        for regla, aviso in disparadas:
            self.disparos += 1
            frase = (f"Señor, el teléfono: {aviso['titulo'] or aviso['app']}. "
                     f"{aviso['texto']}")
            self._decir(frase, regla, aviso)
        return disparadas

    def _decir(self, frase: str, regla: dict, aviso: dict):
        try:
            if getattr(self.core, "tts_queue", None) is not None:
                self.core.tts_queue.put(frase)
        except Exception:
            pass
        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                "movil", aviso["titulo"][:80] or aviso["app"],
                aviso["texto"][:150], gravedad="aviso",
                agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass
        self.log(f"[MOVIL] {frase[:110]}")
        # La regla puede pedir ademas una accion en el PC.
        if regla.get("accion"):
            try:
                self.core.procesar_texto(regla["accion"])
            except Exception as e:
                self.log(f"[MOVIL] La accion «{regla['accion']}» fallo: {e}")

    def estado(self) -> dict:
        return {"activo": bool(self._hilo and self._hilo.is_alive()),
                "reglas": list(self.reglas), "disparos": self.disparos}


def instrucciones() -> str:
    return ("Para que el teléfono me obedezca, señor: Ajustes > Información del "
            "teléfono, siete toques en «Número de compilación»; luego Opciones "
            "de desarrollador > Depuración USB; conecte el cable y acepte la "
            "huella del PC. Con eso puedo leer la batería, las notificaciones, "
            "abrirle apps y hacerlo sonar cuando no lo encuentre.")


if __name__ == "__main__":
    print(resumen())
    hay, _ = disponible()
    if hay:
        print("Notificaciones:", notificaciones())
        print("Ubicacion:", ubicacion() or "sin dato")
    else:
        print(instrucciones())
