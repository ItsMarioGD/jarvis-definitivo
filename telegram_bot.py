#!/usr/bin/env python3
"""
telegram_bot.py - Puente JARVIS <-> Telegram.

Proceso independiente: hace long-polling del bot configurado y responde
usando el nucleo de JARVIS.

Robustez (por que el bot dejaba de responder):
- El token se busca en jarvis_config.TELEGRAM_JSON, en las rutas heredadas y
  en la variable de entorno TELEGRAM_BOT_TOKEN / .env. Antes solo miraba
  ~/Descargas/JARVIS/Prefs y salia en silencio si no estaba.
- TODO se registra en jarvis_log/telegram_bot.log. Antes cada fallo se tragaba
  sin dejar rastro y era imposible saber por que no contestaba.
- Se valida el token con getMe y se llama a deleteWebhook al arrancar: si el
  bot tenia un webhook puesto, getUpdates devuelve 409 para siempre y el bot
  queda mudo. Tambien se reintenta al detectar un 409 en caliente.
- La cola de mensajes pendientes ya no se pierde mientras el nucleo arranca.
- El nucleo se invoca con speak_server=False: un mensaje remoto no debe
  secuestrar el audio del PC (y el TTS bloqueaba la respuesta).
- Instancia unica (lock por PID) para no duplicar respuestas.
- Offset persistido y confirmado ANTES de procesar: Telegram nunca reenvia el
  mismo mensaje aunque el proceso muera.
"""
import os
import sys
import json
import time
import shutil
import inspect
import threading
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections import deque

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

BASE = "https://api.telegram.org/bot"
MAX_TG = 4000  # limite real de sendMessage: 4096 caracteres

# Marca para que JarvisCore no vuelva a lanzar este mismo bot desde dentro
# del proceso del bot (antes se relanzaba en cascada).
os.environ["JARVIS_TELEGRAM_CHILD"] = "1"


# ── rutas y configuracion ────────────────────────────────────────────────────
def _prefs_dir() -> str:
    try:
        import jarvis_config
        return os.path.dirname(jarvis_config.TELEGRAM_JSON)
    except Exception:
        home = os.path.expanduser("~")
        for nombre in ("Descargas", "Downloads", "downloads"):
            p = os.path.join(home, nombre, "JARVIS", "Prefs")
            if os.path.isdir(p):
                return p
        p = os.path.join(home, "Descargas", "JARVIS", "Prefs")
        os.makedirs(p, exist_ok=True)
        return p


PREFS = _prefs_dir()
PREF = os.path.join(PREFS, "telegram.json")
LOCK = os.path.join(PREFS, "telegram_bot.lock")
AUSENTE = os.path.join(PREFS, "ausente.json")

# Rutas heredadas: si el token se guardo con una version anterior en la otra
# carpeta de descargas, lo seguimos encontrando.
_LEGACY = [os.path.join(os.path.expanduser("~"), n, "JARVIS", "Prefs", "telegram.json")
           for n in ("Descargas", "Downloads", "downloads")]


def _log_path() -> str:
    d = os.path.join(RAIZ, "jarvis_log")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return os.path.join(tempfile.gettempdir(), "telegram_bot.log")
    return os.path.join(d, "telegram_bot.log")


LOG = _log_path()


def log(msg: str):
    """Deja rastro en disco y en stderr. Sin esto el bot fallaba en silencio."""
    linea = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass
    try:
        print(linea, file=sys.stderr, flush=True)
    except Exception:
        pass


def _cargar_env():
    """Carga .env para que TELEGRAM_BOT_TOKEN funcione sin exportarlo a mano."""
    ruta = os.path.join(RAIZ, ".env")
    if not os.path.exists(ruta):
        return
    try:
        for linea in open(ruta, encoding="utf-8"):
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def config() -> dict:
    for ruta in [PREF] + _LEGACY:
        try:
            d = json.load(open(ruta, encoding="utf-8-sig"))
            if isinstance(d, dict) and d.get("token"):
                return d
        except Exception:
            continue
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    return {"token": tok} if tok else {}


def guardar(d: dict):
    try:
        os.makedirs(os.path.dirname(PREF), exist_ok=True)
        with open(PREF, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"No pude guardar {PREF}: {e}")


# ── API de Telegram ──────────────────────────────────────────────────────────
def api(token: str, method: str, data=None, timeout: int = 50):
    """Llama a la API. Devuelve el cuerpo aunque Telegram responda con error
    HTTP: es la unica forma de ver el 409/401 que dejaba mudo al bot."""
    url = BASE + token + "/" + method
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        try:
            cuerpo = json.loads(e.read().decode("utf-8", "ignore"))
        except Exception:
            cuerpo = {"ok": False, "error_code": e.code, "description": str(e)}
        log(f"{method}: HTTP {e.code} {cuerpo.get('description', '')}")
        return cuerpo
    except Exception as e:
        log(f"{method}: fallo de red ({type(e).__name__}: {e})")
        return None


def enviar(token: str, chat_id, texto: str):
    """Envia el texto troceado al limite de Telegram y avisa si falla."""
    texto = (texto or "").strip() or "Señor, no he entendido."
    for i in range(0, len(texto), MAX_TG):
        r = api(token, "sendMessage", {"chat_id": chat_id, "text": texto[i:i + MAX_TG]})
        if not r or not r.get("ok"):
            log(f"sendMessage a {chat_id} fallo: {r}")
            return False
    return True


def _limpiar_webhook(token: str):
    """Un webhook activo hace que getUpdates devuelva 409 indefinidamente.
    Es la causa mas comun de «el bot no responde»."""
    r = api(token, "getWebhookInfo", timeout=15)
    url = ((r or {}).get("result") or {}).get("url") or ""
    if url:
        log(f"El bot tenia un webhook activo ({url}); lo quito para poder hacer polling.")
    # drop_pending_updates=False: no queremos perder mensajes ya recibidos.
    api(token, "deleteWebhook", {"drop_pending_updates": False}, timeout=15)


def _single_instance() -> bool:
    """True si esta copia puede quedarse; False si ya hay otra viva."""
    try:
        import psutil
    except Exception:
        log("psutil no disponible: no puedo comprobar instancias duplicadas.")
        return True
    try:
        if os.path.exists(LOCK):
            try:
                pid = int(open(LOCK).read().strip() or "0")
            except Exception:
                pid = 0
            if pid and pid != os.getpid() and psutil.pid_exists(pid):
                try:
                    cmd = " ".join(psutil.Process(pid).cmdline()).lower()
                    if "telegram_bot" in cmd:
                        log(f"Ya hay otro telegram_bot vivo (pid {pid}); esta copia se detiene.")
                        return False
                except Exception:
                    pass
        with open(LOCK, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        log(f"No pude tomar el lock ({e}); continuo igualmente.")
        return True


def _stats() -> str:
    try:
        import psutil
    except Exception:
        return "Señor, no tengo psutil instalado para leer el estado del equipo."
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    # Antes estaba fijado a C:\ y reventaba fuera de Windows.
    raiz = os.path.abspath(os.sep) if os.name != "nt" else os.environ.get("SystemDrive", "C:") + "\\"
    try:
        disc = psutil.disk_usage(raiz).percent
    except Exception:
        disc = 0.0
    up = int(time.time() - psutil.boot_time())
    return (f"Stats, señor: CPU {cpu:.0f}% | RAM {ram.percent:.0f}% | "
            f"disco {disc:.0f}% | encendido {up // 3600}h {(up % 3600) // 60}m.")


def _preguntar_core(core, texto: str) -> str:
    """Llama al nucleo sin hablar por los altavoces del PC."""
    fn = core.process_text_stream
    try:
        acepta = "speak_server" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        acepta = False
    return (fn(texto, speak_server=False) if acepta else fn(texto)) or "Señor, no he entendido."


def main():
    _cargar_env()
    cfg = config()
    token = (cfg.get("token") or "").strip()
    if not token:
        log(f"Sin token de Telegram. Configuralo en {PREF} "
            f"(clave \"token\") o exporta TELEGRAM_BOT_TOKEN. El bot no arranca.")
        return
    if not _single_instance():
        return

    yo = api(token, "getMe", timeout=20)
    if not yo or not yo.get("ok"):
        log(f"El token de Telegram no es valido o no hay red: {yo}. El bot no arranca.")
        return
    log(f"Bot conectado como @{(yo.get('result') or {}).get('username', '?')}. Log en {LOG}")
    _limpiar_webhook(token)

    offset = int(cfg.get("offset", 0) or 0)
    ultimo_id = int(cfg.get("ultimo_id", 0) or 0)
    # Solo respondemos a estos chats si la clave existe; vacio = abierto.
    permitidos = {str(c) for c in (cfg.get("chats_permitidos") or [])}
    core = None
    core_err = None
    core_listo = threading.Event()
    pendientes = deque()          # (chat_id, texto, texto_bajo)
    pend_lock = threading.Lock()

    def encolar(item, al_principio=False):
        with pend_lock:
            if al_principio:
                pendientes.appendleft(item)
            else:
                pendientes.append(item)
            while len(pendientes) > 50:
                pendientes.popleft()

    def _procesar_voz(cid_v, fid_v):
        """Nota de voz -> ffmpeg -> Whisper -> orden para Jarvis."""
        try:
            g = api(token, "getFile", {"file_id": fid_v})
            ruta = ((g or {}).get("result") or {}).get("file_path") or ""
            if not ruta:
                enviar(token, cid_v, "Señor, no pude descargar el audio.")
                return
            url = f"https://api.telegram.org/file/bot{token}/{ruta}"
            datos = urllib.request.urlopen(url, timeout=60).read()
            tmp = os.path.join(tempfile.gettempdir(), f"tg_voz_{int(time.time() * 1000)}.ogg")
            with open(tmp, "wb") as f:
                f.write(datos)
            wav = tmp[:-4] + ".wav"
            if not shutil.which("ffmpeg"):
                enviar(token, cid_v, "Señor, no tengo ffmpeg instalado para convertir el audio.")
                return
            subprocess.run(["ffmpeg", "-y", "-i", tmp, "-ar", "16000", "-ac", "1", wav],
                           capture_output=True, timeout=120)
            if not os.path.exists(wav):
                enviar(token, cid_v, "Señor, no pude convertir el audio.")
                return
            from faster_whisper import WhisperModel
            m = WhisperModel("base", device="cpu", compute_type="int8")
            segs, _ = m.transcribe(wav, language="es")
            texto = "".join(s.text for s in segs).strip()
            for p in (tmp, wav):
                try:
                    os.remove(p)
                except OSError:
                    pass
            if not texto:
                enviar(token, cid_v, "Señor, no escuché nada claro en el audio.")
                return
            encolar((cid_v, texto, texto.lower()))
        except Exception as e:
            log(f"Fallo procesando voz de {cid_v}: {e}")
            enviar(token, cid_v, "Señor, tuve un problema con el audio: " + str(e)[:100])

    def preparar_core():
        nonlocal core, core_err
        try:
            from jarvis_core import JarvisCore
            core = JarvisCore(log_callback=lambda m: log(f"[core] {m}"))
            log("Nucleo de JARVIS listo para Telegram.")
        except Exception as e:
            core_err = e
            log(f"No pude inicializar JarvisCore: {type(e).__name__}: {e}")
        finally:
            core_listo.set()

    threading.Thread(target=preparar_core, daemon=True).start()

    espera_red = 2
    try:
        while True:
            try:
                actual = config()
                if not actual.get("token") or actual["token"] != token:
                    log("El token se borro o cambio; el bot se detiene.")
                    return

                r = api(token, "getUpdates", {"offset": offset, "timeout": 30})
                if r is None:
                    time.sleep(espera_red)
                    espera_red = min(espera_red * 2, 60)  # backoff: no martillear sin red
                    continue
                espera_red = 2
                if not r.get("ok"):
                    codigo = r.get("error_code")
                    if codigo == 409:
                        # Otro getUpdates o un webhook nos esta pisando.
                        log("409 en getUpdates: reintento quitando el webhook.")
                        _limpiar_webhook(token)
                        time.sleep(5)
                    elif codigo in (401, 404):
                        log("Token rechazado por Telegram (401/404). El bot se detiene.")
                        return
                    else:
                        time.sleep(3)
                    continue

                updates = r.get("result", [])
                if updates:
                    nuevo = max(u.get("update_id", 0) for u in updates) + 1
                    if nuevo > offset:
                        # CONFIRMAR YA, antes de procesar, para que Telegram
                        # jamas reenvie estos mensajes aunque tardemos.
                        api(token, "getUpdates", {"offset": nuevo, "timeout": 0}, timeout=20)
                        offset = nuevo
                        c = config()
                        c["offset"] = offset
                        c["ultimo_id"] = ultimo_id
                        guardar(c)
                    for upd in updates:
                        uid = upd.get("update_id", 0)
                        if uid <= ultimo_id:
                            continue
                        ultimo_id = uid
                        msg = upd.get("message") or upd.get("edited_message") or {}
                        cid = (msg.get("chat") or {}).get("id")
                        texto = (msg.get("text") or msg.get("caption") or "").strip()
                        if not cid:
                            continue
                        if permitidos and str(cid) not in permitidos:
                            log(f"Mensaje ignorado de un chat no autorizado: {cid}")
                            continue
                        if not texto:
                            fid = (msg.get("voice") or {}).get("file_id") or ""
                            if fid:
                                threading.Thread(target=_procesar_voz,
                                                 args=(cid, fid), daemon=True).start()
                                enviar(token, cid, "Escuchando su audio, señor...")
                            continue
                        c = config()
                        c["chat_id"] = cid
                        c["offset"] = offset
                        c["ultimo_id"] = ultimo_id
                        guardar(c)
                        encolar((cid, texto, texto.lower()))

                # Procesar pendientes (ya confirmados, sin riesgo de duplicado)
                with pend_lock:
                    cola = list(pendientes)
                    pendientes.clear()
                sin_core = []
                for cid, texto, bajo in cola:
                    try:
                        if bajo in ("/start", "/ayuda", "/help"):
                            enviar(token, cid, "JARVIS en línea, señor. Escríbame lo que necesite "
                                               "y le responderé desde el PC.")
                            continue
                        if bajo in ("/stats", "/estado", "/status"):
                            enviar(token, cid, _stats())
                            continue

                        # Modo ausente: responder con el mensaje guardado y avisar al dueño
                        try:
                            aus = json.load(open(AUSENTE, encoding="utf-8"))
                        except Exception:
                            aus = {}
                        if aus.get("activo"):
                            enviar(token, cid, aus.get("mensaje") or "Señor no está disponible.")
                            dueno = config().get("chat_id")
                            if dueno and str(dueno) != str(cid):
                                enviar(token, dueno,
                                       f"Señor, le han escrito por Telegram: «{texto[:200]}»")
                            continue

                        if core is None:
                            if core_err is not None:
                                enviar(token, cid, "Señor, no pude inicializar mi núcleo: "
                                                   + str(core_err)[:200])
                            else:
                                # Se reencola entero: antes el resto de la cola
                                # se perdia al cortar el bucle con un break.
                                sin_core.append((cid, texto, bajo))
                            continue

                        if bajo in ("/clear", "/limpia", "/borra memoria"):
                            try:
                                enviar(token, cid, core.limpiar_memoria())
                            except Exception as e:
                                log(f"limpiar_memoria fallo: {e}")
                                enviar(token, cid, "Señor, no pude limpiar la memoria: " + str(e)[:100])
                            continue

                        try:
                            resp = _preguntar_core(core, texto)
                        except Exception as e:
                            log(f"process_text_stream fallo con «{texto[:60]}»: {e}")
                            resp = "Señor, tuve un problema procesando eso: " + str(e)[:200]
                        enviar(token, cid, resp)
                    except Exception as e:
                        log(f"Error tratando el mensaje de {cid}: {e}")

                if sin_core:
                    avisados = set()
                    for item in reversed(sin_core):
                        encolar(item, al_principio=True)
                        if item[0] not in avisados:
                            avisados.add(item[0])
                            enviar(token, item[0], "Un momento, señor, estoy arrancando...")
                    # Esperamos al nucleo en vez de dormir a ciegas.
                    core_listo.wait(timeout=20)
                time.sleep(1)
            except Exception as e:
                log(f"Error en el bucle principal: {type(e).__name__}: {e}")
                time.sleep(3)
    finally:
        try:
            if os.path.exists(LOCK) and open(LOCK).read().strip() == str(os.getpid()):
                os.remove(LOCK)
        except Exception:
            pass
        log("telegram_bot detenido.")


if __name__ == "__main__":
    main()
