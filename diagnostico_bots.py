#!/usr/bin/env python3
"""
diagnostico_bots.py - Por que no responden los bots.

Ejecuta:   python diagnostico_bots.py

Revisa, en orden, todo lo que deja mudo a JARVIS desde fuera del PC:
el token de Telegram, el webhook que rompe getUpdates, los procesos
duplicados, el nucleo, el servidor web del movil y el filtro de IPs.
No modifica nada salvo que se pase --arreglar (quita el webhook).
"""
import json
import os
import socket
import sys
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
ARREGLAR = "--arreglar" in sys.argv

OK, MAL, AVISO = "  [OK] ", "  [MAL] ", "  [!] "
problemas = []


def titulo(t):
    print(f"\n=== {t} ===")


def mal(msg, arreglo=""):
    print(MAL + msg)
    problemas.append((msg, arreglo))


def _tg(token, metodo, data=None, timeout=15):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{metodo}",
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "ignore"))
        except Exception:
            return {"ok": False, "error_code": e.code, "description": str(e)}
    except Exception as e:
        return {"ok": False, "description": f"sin red: {e}"}


def revisar_telegram():
    titulo("BOT DE TELEGRAM")
    try:
        import telegram_bot as tb
    except Exception as e:
        mal(f"No puedo importar telegram_bot.py: {e}")
        return
    tb._cargar_env()
    print(f"  Prefs:   {tb.PREF}")
    print(f"  Log:     {tb.LOG}")
    cfg = tb.config()
    token = (cfg.get("token") or "").strip()
    if not token:
        mal("No hay token de Telegram configurado.",
            'Di «configura mi bot de telegram en TU_TOKEN» o pon TELEGRAM_BOT_TOKEN en .env')
        return
    print(OK + f"Token encontrado (…{token[-6:]})")

    yo = _tg(token, "getMe")
    if not yo.get("ok"):
        mal(f"Telegram rechaza el token: {yo.get('description')}",
            "Genera un token nuevo con @BotFather y vuelve a configurarlo.")
        return
    print(OK + f"Bot valido: @{yo['result'].get('username')}")

    wh = _tg(token, "getWebhookInfo").get("result") or {}
    url = wh.get("url") or ""
    if url:
        mal(f"Hay un WEBHOOK activo ({url}): getUpdates devolvera 409 y el bot no lee nada.",
            "Ejecuta: python diagnostico_bots.py --arreglar")
        if ARREGLAR:
            r = _tg(token, "deleteWebhook", {"drop_pending_updates": False})
            print(OK + f"deleteWebhook -> {r.get('ok')}")
    else:
        print(OK + "Sin webhook: el long-polling puede funcionar.")
    if wh.get("pending_update_count"):
        print(AVISO + f"{wh['pending_update_count']} mensajes en cola sin leer.")
    if wh.get("last_error_message"):
        print(AVISO + f"Ultimo error de Telegram: {wh['last_error_message']}")

    up = _tg(token, "getUpdates", {"offset": int(cfg.get("offset", 0) or 0), "timeout": 0})
    if not up.get("ok"):
        if up.get("error_code") == 409:
            mal("409 en getUpdates: otro proceso esta leyendo el mismo bot.",
                "Cierra los telegram_bot.py duplicados (o reinicia el PC) y vuelve a probar.")
        else:
            mal(f"getUpdates falla: {up.get('description')}")
    else:
        print(OK + f"getUpdates responde ({len(up.get('result', []))} pendientes).")

    if os.path.exists(tb.LOCK):
        pid = open(tb.LOCK).read().strip()
        vivo = False
        try:
            import psutil
            vivo = psutil.pid_exists(int(pid or 0))
        except Exception:
            pass
        if vivo:
            print(OK + f"Bot en marcha (pid {pid}).")
        else:
            print(AVISO + f"Lock huerfano de un pid muerto ({pid}); la proxima copia lo reemplaza.")
    else:
        print(AVISO + "El bot no esta corriendo ahora mismo (no hay lock).")


def revisar_db():
    titulo("MEMORIA (SQLite)")
    try:
        import jarvis_config
        rutas = jarvis_config.rutas_db("jarvis_memory.db")
    except Exception as e:
        mal(f"jarvis_config no resuelve la ruta de la base: {e}")
        return
    import sqlite3
    elegida = None
    for r in rutas:
        try:
            c = sqlite3.connect(r, timeout=5)
            c.execute("SELECT 1")
            filas = 0
            try:
                filas = c.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
            except Exception:
                pass
            c.close()
            if elegida is None:
                elegida = r
                print(OK + f"Usara {r} ({filas} interacciones).")
            else:
                print(f"       alternativa: {r}")
        except Exception as e:
            print(AVISO + f"No se puede abrir {r}: {e}")
    if elegida is None:
        mal("Ninguna ruta de base de datos se puede abrir: el nucleo no arrancara.",
            "Define JARVIS_DB_DIR con una carpeta escribible.")
        return

    # Bases dispersas por arrancar desde distintos directorios de trabajo.
    otras = [p for p in (os.path.join(RAIZ, "web_interface", "jarvis_memory.db"),
                         os.path.join(RAIZ, "ultron_interface", "jarvis_memory.db"))
             if os.path.isfile(p) and os.path.abspath(p) != os.path.abspath(elegida)]
    for p_otra in otras:
        print(AVISO + f"Hay otra memoria suelta en {p_otra} "
                      "(de un arranque con otro directorio de trabajo).")
    for sufijo in ("-wal", "-shm"):
        huerf = elegida + sufijo
        if os.path.exists(huerf):
            print(AVISO + f"Existe {os.path.basename(huerf)}; si JARVIS arranco alguna vez "
                          "como administrador puede bloquear la base.")


def revisar_voz():
    titulo("VOZ (TTS)")
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    if key and "tu_api" not in key and voice:
        print(OK + f"ElevenLabs configurado (voz {voice}).")
    else:
        falta = []
        if not key or "tu_api" in key:
            falta.append("ELEVENLABS_API_KEY")
        if not voice:
            falta.append("ELEVENLABS_VOICE_ID")
        print(AVISO + f"Sin ElevenLabs (falta {', '.join(falta)} en .env).")

    try:
        import jarvis_piper
        if jarvis_piper.disponible():
            print(OK + "Voz local Piper lista: el navegador recibira audio del PC.")
        else:
            print(AVISO + "Modelo de Piper sin descargar. Para tener voz local sin nube:")
            print('       python -c "import jarvis_piper; jarvis_piper.descargar_modelo()"')
    except Exception as e:
        print(AVISO + f"Piper no instalado ({e}); pip install piper-tts")
    print("       Sin ninguno de los dos, /api/speak responde 204 y habla el "
          "navegador (speechSynthesis). No es un error.")


def revisar_conectores():
    titulo("CONECTORES (Google Calendar y demas)")
    try:
        import conectores
    except Exception as e:
        mal(f"No puedo importar conectores.py: {e}")
        return
    try:
        c = conectores.Conectores(log=lambda m: None)
    except Exception as e:
        mal(f"No pude crear el despachador de conectores: {e}")
        return
    if not c.conectores:
        mal("No hay ningun conector cargado.")
        return
    estado = c.estado()
    for servicio, vivo in estado.items():
        if vivo:
            print(OK + f"{servicio} responde.")
        else:
            print(AVISO + f"{servicio} no responde.")
    if not any(estado.values()):
        puerto = conectores.SERVIDORES["calendar"]
        mal("Ningun servidor de conectores esta escuchando.",
            f"Arranca el de calendario: python mcp_servers/calendar_server.py "
            f"(puerto {puerto}), o usa start_jarvis.bat que los levanta todos.")
        return
    cred = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
    tok = os.getenv("GOOGLE_TOKEN_JSON", "token.json")
    for ruta, que in ((cred, "credenciales de Google"), (tok, "token de autorizacion")):
        entero = ruta if os.path.isabs(ruta) else os.path.join(RAIZ, ruta)
        if os.path.exists(entero):
            print(OK + f"{que}: {entero}")
        elif que.startswith("token"):
            print(AVISO + f"Sin {que} ({entero}). La primera vez que agendes algo "
                          "se abrira el navegador para autorizar.")
        else:
            mal(f"Faltan las {que} ({entero}).",
                "Descargalas de Google Cloud Console (OAuth de escritorio) y "
                "guardalas ahi, o define GOOGLE_CREDENTIALS_JSON.")
    print('       Prueba: «Jarvis, agenda una reunión con Marta mañana a las 5».')


def revisar_nucleo():
    titulo("NUCLEO DE JARVIS")
    try:
        from jarvis_core import JarvisCore
    except Exception as e:
        mal(f"jarvis_core no importa: {type(e).__name__}: {e}",
            "Instala las dependencias: pip install -r requirements.txt")
        return
    if not hasattr(JarvisCore, "process_text_stream"):
        mal("JarvisCore no expone process_text_stream(): los bots no pueden preguntarle nada.")
        return
    print(OK + "JarvisCore importa y expone process_text_stream().")


def revisar_web():
    titulo("SERVIDOR WEB / MOVIL")
    try:
        import jarvis_config
        puerto = jarvis_config.PORT
        ip = jarvis_config.LOCAL_IP
    except Exception as e:
        mal(f"jarvis_config falla: {e}")
        return
    s = socket.socket()
    s.settimeout(2)
    escuchando = s.connect_ex(("127.0.0.1", puerto)) == 0
    s.close()
    if escuchando:
        print(OK + f"Servidor escuchando en el puerto {puerto}.")
        print(f"       Movil: http://{ip}:{puerto}/mobile   ·   PIN: http://{ip}:{puerto}/pair")
    else:
        mal(f"Nadie escucha en el puerto {puerto}: el movil no puede conectar.",
            "Arranca el servidor: python web_interface/app.py")

    pin = os.path.join(RAIZ, "web_interface", ".jarvis_auth")
    if os.path.exists(pin):
        print(OK + f"PIN de emparejamiento actual: {open(pin).read().strip()}")
    else:
        print(AVISO + "Aun no hay PIN generado (se crea al arrancar el servidor).")

    try:
        lista = json.load(open(os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS",
                                            "Prefs", "allowed_ips.json"), encoding="utf-8")) or []
    except Exception:
        lista = []
    if lista:
        print(AVISO + f"Filtro de IPs activo: {lista}")
        print("       Si la IP del movil cambio, ahora basta con el PIN correcto;"
              " si sigue fallando, borra ese allowed_ips.json.")
    else:
        print(OK + "Sin filtro de IPs.")


if __name__ == "__main__":
    print("Diagnostico de los bots de JARVIS")
    revisar_telegram()
    revisar_db()
    revisar_voz()
    revisar_conectores()
    revisar_nucleo()
    revisar_web()
    titulo("RESUMEN")
    if not problemas:
        print("  Todo correcto. Si el bot sigue mudo, mira jarvis_log/telegram_bot.log.")
    else:
        for msg, arreglo in problemas:
            print(f"  - {msg}")
            if arreglo:
                print(f"      -> {arreglo}")
    sys.exit(1 if problemas else 0)
