#!/usr/bin/env python3
"""
revisar.py - Dice de un vistazo que funciona y que no.

Comprueba, en este orden, todo lo que hace falta para que JARVIS este
operativo: dependencias, modelo de IA, servidores, emparejamiento del
telefono, control del PC y Google Calendar. De cada cosa rota dice el
comando exacto para arreglarla.

    python revisar.py
"""
import os
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consola_utf8  # noqa: F401  (salida a prueba de cp1252)

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

OK, MAL, AVISO = "[OK]  ", "[MAL] ", "[!]   "
_problemas = []


def linea(estado, texto, arreglo=""):
    print(f"  {estado}{texto}")
    if estado == MAL and arreglo:
        _problemas.append((texto, arreglo))


def titulo(t):
    print(f"\n{t}\n  " + "-" * (len(t) - 2))


def hay(modulo):
    import importlib.util
    try:
        return importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        return False


def responde(url, timeout=4):
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True          # contesta, aunque sea un error: el proceso vive
    except Exception:
        return False


def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def revisar_dependencias():
    titulo("1. Dependencias")
    criticas = {
        "flask": "flask", "flask_socketio": "flask-socketio", "openai": "openai",
        "requests": "requests", "psutil": "psutil", "dotenv": "python-dotenv",
    }
    faltan = [p for m, p in criticas.items() if not hay(m)]
    if faltan:
        linea(MAL, f"Faltan librerias imprescindibles: {', '.join(faltan)}",
              "python instalar_dependencias.py")
    else:
        linea(OK, "Lo imprescindible esta instalado.")

    funciones = {
        "qrcode": ("qrcode", "el QR sale en PNG (hay respaldo propio si falta)"),
        "PIL": ("Pillow", "capturas de pantalla y ver el escritorio desde el movil"),
        "pyautogui": ("pyautogui", "control del raton y el teclado"),
        "faster_whisper": ("faster-whisper", "hablarle a JARVIS desde el movil"),
        "cv2": ("opencv-python", "la camara"),
        "googleapiclient": ("google-api-python-client", "Google Calendar"),
        "aiohttp": ("aiohttp", "los servidores MCP (calendario, casa, movil)"),
    }
    for modulo, (paquete, para) in funciones.items():
        if hay(modulo):
            linea(OK, f"{paquete}: {para}")
        else:
            linea(MAL, f"Falta {paquete}, asi que no funciona: {para}",
                  f"python -m pip install {paquete}")


def revisar_ia():
    titulo("2. Motor de IA (Ollama)")
    import jarvis_config
    base = jarvis_config.OLLAMA_BASE.rstrip("/").replace("/v1", "")
    if not responde(f"{base}/api/tags"):
        linea(MAL, f"Ollama no responde en {base}.",
              "Abre una consola y ejecuta:  ollama serve")
        return
    linea(OK, f"Ollama responde en {base}")
    try:
        import json
        import urllib.request
        datos = json.load(urllib.request.urlopen(f"{base}/api/tags", timeout=6))
        modelos = [m["name"] for m in datos.get("models", [])]
    except Exception:
        modelos = []
    buscado = jarvis_config.OLLAMA_MODEL
    if any(m.startswith(buscado.split(":")[0]) for m in modelos):
        linea(OK, f"Modelo disponible: {buscado}")
    else:
        linea(MAL, f"El modelo «{buscado}» no esta descargado. Hay: {modelos or 'ninguno'}",
              f"ollama pull {buscado}")


def revisar_servidores():
    titulo("3. Servidores")
    import jarvis_config
    servicios = [
        (f"http://127.0.0.1:{jarvis_config.PORT}/health", f"JARVIS web (puerto {jarvis_config.PORT})", True),
        ("http://127.0.0.1:8766/health", "ULTRON web (puerto 8766)", False),
        ("http://127.0.0.1:8002/health", "Calendario MCP (puerto 8002)", False),
    ]
    for url, nombre, critico in servicios:
        if responde(url):
            linea(OK, f"{nombre} en marcha")
        elif critico:
            linea(MAL, f"{nombre} NO esta en marcha.", "python reiniciar_todo.py")
        else:
            linea(AVISO, f"{nombre} parado (arranca con: python reiniciar_todo.py)")


def revisar_movil():
    titulo("4. Emparejar el telefono")
    import jarvis_config
    ip, puerto = ip_local(), jarvis_config.PORT

    # El QR: lo importante es que se genere, con libreria o sin ella.
    try:
        from jarvis_qr import qr_response_data
        datos, tipo = qr_response_data(f"http://{ip}:{puerto}/mobile?token=000000")
        linea(OK, f"El QR se genera correctamente ({tipo}, {len(datos)} bytes)")
    except Exception as e:
        linea(MAL, f"El QR no se genera: {e}", "python -m pip install qrcode Pillow")

    if responde(f"http://127.0.0.1:{puerto}/health"):
        print(f"\n     Abre esto en el PC y escanea el codigo con el telefono:")
        print(f"       http://{ip}:{puerto}/pair\n")
        try:
            pin = open(os.path.join(RAIZ, "web_interface", ".jarvis_auth"),
                       encoding="utf-8").read().strip()
            print(f"     PIN de acceso: {pin}\n")
        except OSError:
            pass

    # Firewall: la causa mas comun de «el movil no conecta».
    if os.name == "nt":
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "if (Get-NetFirewallRule -DisplayName 'JARVIS (movil)' "
                 "-ErrorAction SilentlyContinue) { 'si' } else { 'no' }"],
                capture_output=True, text=True, timeout=25)
            if "si" in (r.stdout or "").lower():
                linea(OK, "El firewall tiene abierto el puerto del movil.")
            else:
                linea(AVISO, "No hay regla de firewall para JARVIS. Si el telefono "
                             "no conecta, ejecuta como administrador: "
                             "herramientas\\abrir_firewall.ps1")
        except Exception:
            pass


def revisar_pc():
    titulo("5. Control del PC")
    if hay("PIL"):
        linea(OK, "Capturas de pantalla y escritorio en vivo disponibles.")
    else:
        linea(MAL, "Sin Pillow no hay capturas ni escritorio en vivo.",
              "python -m pip install Pillow")
    if os.name == "nt":
        linea(OK, "Raton y teclado remotos disponibles (touchpad del movil).")


def revisar_google():
    titulo("6. Google Calendar")
    import jarvis_config
    info = jarvis_config.revisar_credenciales_google()
    if not info["ok"]:
        linea(MAL, "Falta el fichero de credenciales de Google.",
              "python autorizar_google.py   (te guia paso a paso)")
        print("\n     Resumen de lo que hay que hacer una sola vez:")
        print("       1. console.cloud.google.com -> crea un proyecto")
        print("       2. Activa la API de Google Calendar")
        print("       3. Credenciales -> Crear -> ID de cliente de OAuth")
        print("          -> tipo «Aplicacion de escritorio»")
        print("       4. Descarga el JSON y dejalo en la carpeta:")
        print(f"          {jarvis_config.GOOGLE_DIR}")
        print("       5. Publico objetivo -> anadete como usuario de prueba")
        print("       6. python autorizar_google.py\n")
        return
    linea(OK, f"Credenciales encontradas ({os.path.basename(info['ruta'])}, tipo {info['tipo']})")
    token = jarvis_config.ruta_token_google()
    if os.path.exists(token):
        linea(OK, "La cuenta de Google ya esta autorizada.")
    else:
        linea(MAL, "Las credenciales estan, pero la cuenta no esta autorizada.",
              "python autorizar_google.py")


def revisar_voz():
    titulo("7. Voz propia")
    try:
        import voz_propia
        e = voz_propia.estado()
    except Exception as ex:
        linea(MAL, f"No pude revisar la voz: {ex}")
        return
    puestas = e["voces_instaladas"]
    if not hay("piper"):
        linea(AVISO, "Sin la libreria de Piper hablo con la voz de Windows.",
              "python -m pip install piper-tts")
    if puestas:
        linea(OK, f"Voces neuronales instaladas: {', '.join(puestas)}")
        linea(OK, f"JARVIS usa {e['voz_jarvis']} y ULTRON {e['voz_ultron']}")
    else:
        linea(AVISO, "No hay ninguna voz neuronal descargada (unos 60 MB).",
              'di «instala tu voz» o: python -c "import voz_propia;'
              ' print(voz_propia.instalar())"')


def revisar_telefono():
    titulo("8. El telefono como extension")
    try:
        import movil
        conectado, motivo = movil.disponible()
    except Exception as ex:
        linea(MAL, f"No pude revisar el telefono: {ex}")
        return
    if conectado:
        b = movil.bateria()
        detalle = f" (bateria al {b['nivel']}%)" if b else ""
        linea(OK, f"Telefono conectado: {motivo}{detalle}")
        return
    if not movil.ADB:
        linea(AVISO, "Sin adb no puedo leer el telefono. Es opcional.",
              "winget install Google.PlatformTools")
    else:
        linea(AVISO, f"adb esta, pero {motivo}.",
              "conecta el cable con la depuracion USB activada")


def revisar_remoto():
    titulo("9. Entrar desde fuera de casa")
    try:
        import remoto
        e = remoto.estado()
    except Exception as ex:
        linea(MAL, f"No pude revisar el acceso remoto: {ex}")
        return
    if not e["instalado"]:
        linea(AVISO, "Sin Tailscale solo se llega a JARVIS desde esta misma red.",
              "instala Tailscale en el PC y en el movil: tailscale.com/download")
        return
    red = e["red"]
    if not red.get("activo"):
        linea(AVISO, f"Tailscale instalado pero parado ({red.get('estado','')}).",
              "abrelo e inicia sesion")
        return
    seguras = [u for u in e["urls"] if u.get("segura")]
    if seguras:
        linea(OK, f"Accesible desde cualquier red: {seguras[0]['url']}/mobile")
    else:
        linea(AVISO, "Tailscale esta en marcha pero JARVIS no esta publicado.",
              'di "activate en remoto" (o: python -c "import remoto; print(remoto.activar())")')
    conectados = e["aparatos_conectados"]
    otros = [a["nombre"] for a in red.get("aparatos", [])]
    if conectados:
        linea(OK, f"Aparatos conectados ahora: {', '.join(conectados)}")
    elif otros:
        linea(AVISO, f"Tus otros aparatos ({', '.join(otros[:3])}) estan apagados "
                     "o sin Tailscale encendido.")
    if e["publicado"].get("funnel"):
        linea(AVISO, "JARVIS esta abierto a Internet (Funnel).",
              'quitalo con "quita el acceso remoto" si ya no lo necesitas')


def main():
    print("=" * 66)
    print("  REVISION DE JARVIS")
    print(f"  {RAIZ}")
    print(f"  Python {sys.version.split()[0]}")
    print("=" * 66)

    for revision in (revisar_dependencias, revisar_ia, revisar_servidores,
                     revisar_movil, revisar_pc, revisar_google,
                     revisar_voz, revisar_telefono, revisar_remoto):
        try:
            revision()
        except Exception as e:
            print(f"  {MAL}No pude completar esta revision: {type(e).__name__}: {e}")

    print("\n" + "=" * 66)
    if not _problemas:
        print("  TODO EN ORDEN. JARVIS esta listo para recibir ordenes.")
    else:
        print(f"  HAY {len(_problemas)} COSA(S) QUE ARREGLAR:")
        for i, (que, como) in enumerate(_problemas, 1):
            print(f"\n   {i}. {que}")
            print(f"      -> {como}")
    print("=" * 66)
    return 1 if _problemas else 0


if __name__ == "__main__":
    sys.exit(main())
