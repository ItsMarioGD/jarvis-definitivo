#!/usr/bin/env python3
"""
telegram_bot.py - Puente JARVIS <-> Telegram.
Proceso independiente: hace long-polling del bot configurado en
Descargas\\JARVIS\\Prefs\\telegram.json y responde usando el núcleo de JARVIS.

Robustez:
- Instancia única (lock por PID): si otro bot con el mismo token ya corre,
  esta copia se detiene (evita respuestas duplicadas).
- Offset persistido y confirmado ANTES de procesar: aunque el proceso muera
  o tarde en responder, Telegram nunca reenvía el mismo mensaje.
- Deduplicación por update_id en memoria.
- JarvisCore se inicializa en segundo plano: la primera respuesta no espera.
"""
import os, sys, json, time, threading, urllib.request, subprocess, tempfile

BASE = "https://api.telegram.org/bot"
PREF = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "telegram.json")
LOCK = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "telegram_bot.lock")


def config() -> dict:
    try:
        return json.load(open(PREF, encoding="utf-8-sig"))
    except Exception:
        return {}


def guardar(d: dict):
    try:
        with open(PREF, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def api(token: str, method: str, data=None, timeout: int = 50):
    url = BASE + token + "/" + method
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return None


def _single_instance() -> bool:
    """Devuelve True si esta copia puede quedarse; False si ya hay otra viva."""
    try:
        import psutil
        if os.path.exists(LOCK):
            try:
                pid = int(open(LOCK).read().strip() or "0")
            except Exception:
                pid = 0
            if pid and psutil.pid_exists(pid):
                try:
                    cmd = " ".join(psutil.Process(pid).cmdline()).lower()
                    if "telegram_bot" in cmd:
                        return False
                except Exception:
                    pass
        with open(LOCK, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return True


def main():
    cfg = config()
    token = cfg.get("token", "")
    if not token:
        return
    if not _single_instance():
        return

    offset = int(cfg.get("offset", 0) or 0)
    ultimo_id = int(cfg.get("ultimo_id", 0) or 0)
    core = None
    core_err = None
    pendientes = []  # (chat_id, texto, texto_bajo) esperando al core
    pend_lock = threading.Lock()

    def _procesar_voz(token_v, cid_v, fid_v):
        """FCC voice flow: nota de voz -> ffmpeg -> Whisper -> orden para Jarvis."""
        try:
            g = api(token_v, "getFile", {"file_id": fid_v})
            ruta = (g or {}).get("result", {}).get("file_path") or ""
            if not ruta:
                api(token_v, "sendMessage", {"chat_id": cid_v,
                                             "text": "Señor, no pude descargar el audio."})
                return
            url = f"https://api.telegram.org/file/bot{token_v}/{ruta}"
            datos = urllib.request.urlopen(url, timeout=60).read()
            tmp = os.path.join(tempfile.gettempdir(), f"tg_voz_{int(time.time() * 1000)}.ogg")
            with open(tmp, "wb") as f:
                f.write(datos)
            wav = tmp[:-4] + ".wav"
            subprocess.run(["ffmpeg", "-y", "-i", tmp, "-ar", "16000", "-ac", "1", wav],
                           capture_output=True, timeout=120)
            if not os.path.exists(wav):
                api(token_v, "sendMessage", {"chat_id": cid_v,
                                             "text": "Señor, no pude convertir el audio."})
                return
            from faster_whisper import WhisperModel
            m = WhisperModel("base", device="cpu", compute_type="int8")
            segs, _ = m.transcribe(wav, language="es")
            texto = "".join(s.text for s in segs).strip()
            for p in (tmp, wav):
                try:
                    os.remove(p)
                except Exception:
                    pass
            if not texto:
                api(token_v, "sendMessage", {"chat_id": cid_v,
                                             "text": "Señor, no escuché nada claro en el audio."})
                return
            with pend_lock:
                pendientes.append((cid_v, texto, texto.lower()))
        except Exception as e:
            try:
                api(token_v, "sendMessage", {"chat_id": cid_v,
                                             "text": "Señor, tuve un problema con el audio: " + str(e)[:100]})
            except Exception:
                pass

    def preparar_core():
        nonlocal core, core_err
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from jarvis_core import JarvisCore
            core = JarvisCore()
            core_err = None
        except Exception as e:
            core_err = e

    threading.Thread(target=preparar_core, daemon=True).start()

    try:
        while True:
            try:
                actual = config()
                if not actual.get("token") or actual["token"] != token:
                    return  # token borrado o cambiado: salir
                r = api(token, "getUpdates", {"offset": offset, "timeout": 30})
                if not r or not r.get("ok"):
                    time.sleep(2)
                    continue
                updates = r.get("result", [])
                if updates:
                    nuevo = max(u.get("update_id", 0) for u in updates) + 1
                    if nuevo > offset:
                        # CONFIRMAR YA: antes de procesar nada, para que
                        # Telegram jamás reenvíe estos mensajes aunque tardemos.
                        api(token, "getUpdates", {"offset": nuevo, "timeout": 0})
                        offset = nuevo
                        try:
                            c = config()
                            c["offset"] = offset
                            guardar(c)
                        except Exception:
                            pass
                    for upd in updates:
                        uid = upd.get("update_id", 0)
                        if uid <= ultimo_id:
                            continue
                        ultimo_id = uid
                        msg = upd.get("message") or {}
                        cid = msg.get("chat", {}).get("id")
                        texto = (msg.get("text") or "").strip()
                        if not cid:
                            continue
                        if not texto:
                            voz = msg.get("voice") or {}
                            fid = voz.get("file_id") or ""
                            if fid:
                                threading.Thread(target=_procesar_voz,
                                                 args=(token, cid, fid), daemon=True).start()
                                api(token, "sendMessage", {"chat_id": cid,
                                                           "text": "Escuchando su audio, señor..."})
                            continue
                        try:
                            c = config()
                            c["chat_id"] = cid
                            guardar(c)
                        except Exception:
                            pass
                        pendientes.append((cid, texto, texto.lower()))
                        if len(pendientes) > 20:
                            pendientes.pop(0)
                # Procesar pendientes (ya confirmados, sin riesgo de duplicado)
                cola = pendientes
                pendientes = []
                for cid, texto, bajo in cola:
                    if bajo in ("/start", "/ayuda", "/help"):
                        api(token, "sendMessage", {"chat_id": cid,
                                                   "text": "JARVIS en línea, señor. Escríbame lo que necesite "
                                                           "y le responderé desde el PC."})
                        continue
                    if bajo in ("/stats", "/estado", "/status"):
                        try:
                            import psutil
                            cpu = psutil.cpu_percent(interval=0.5)
                            ram = psutil.virtual_memory()
                            disc = psutil.disk_usage("C:\\")
                            up = int(time.time() - psutil.boot_time())
                            api(token, "sendMessage", {"chat_id": cid,
                                                       "text": (f"Stats, señor: CPU {cpu:.0f}% | "
                                                                f"RAM {ram.percent:.0f}% | "
                                                                f"disco {disc.percent:.0f}% | "
                                                                f"encendido {up // 3600}h {(up % 3600) // 60}m.")})
                            continue
                        except Exception:
                            pass
                    if bajo in ("/clear", "/limpia", "/borra memoria"):
                        if core is None:
                            if core_err is not None:
                                api(token, "sendMessage", {"chat_id": cid,
                                                           "text": "Señor, no pude inicializar mi núcleo: "
                                                                   + str(core_err)[:100]})
                            else:
                                pendientes.insert(0, (cid, texto, bajo))
                                api(token, "sendMessage", {"chat_id": cid,
                                                           "text": "Un momento, señor, estoy arrancando..."})
                                time.sleep(3)
                                break
                            continue
                        try:
                            resp = core.limpiar_memoria()
                        except Exception as e:
                            resp = "Señor, no pude limpiar la memoria: " + str(e)[:100]
                        api(token, "sendMessage", {"chat_id": cid, "text": resp})
                        continue
                    # Modo ausente: responder con el mensaje guardado y avisar al dueño
                    try:
                        aus = json.load(open(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                                          "Prefs", "ausente.json"), encoding="utf-8"))
                    except Exception:
                        aus = {}
                    if aus.get("activo"):
                        api(token, "sendMessage", {"chat_id": cid, "text": (aus.get("mensaje") or
                                                                            "Señor no está disponible.")})
                        dueno = config().get("chat_id")
                        if dueno and str(dueno) != str(cid):
                            api(token, "sendMessage", {"chat_id": dueno,
                                                       "text": f"Señor, le han escrito por Telegram: «{texto[:200]}»"})
                        continue
                    if core is None:
                        if core_err is not None:
                            resp = "Señor, no pude inicializar mi núcleo: " + str(core_err)[:100]
                            api(token, "sendMessage", {"chat_id": cid, "text": resp})
                        else:
                            pendientes.insert(0, (cid, texto, bajo))
                            api(token, "sendMessage", {"chat_id": cid,
                                                       "text": "Un momento, señor, estoy arrancando..."})
                            time.sleep(3)
                            break
                        continue
                    try:
                        resp = core.process_text_stream(texto) or "Señor, no he entendido."
                    except Exception as e:
                        resp = "Señor, tuve un problema procesando eso: " + str(e)[:100]
                    api(token, "sendMessage", {"chat_id": cid, "text": resp[:3000]})
                time.sleep(1)
            except Exception:
                time.sleep(3)
    finally:
        try:
            if os.path.exists(LOCK):
                os.remove(LOCK)
        except Exception:
            pass


if __name__ == "__main__":
    main()