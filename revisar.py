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

# El .env se lee AQUI, antes de mirar nada: `jarvis_config` guarda la clave en
# una constante al importarse, y sin cargar el fichero primero esta revision
# daba por perdida una ANTHROPIC_API_KEY que si estaba puesta.
def _cargar_env():
    ruta = os.path.join(RAIZ, ".env")
    try:
        from dotenv import load_dotenv
        load_dotenv(ruta)
        return
    except Exception:
        pass
    try:
        for linea in open(ruta, encoding="utf-8"):
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                os.environ.setdefault(clave.strip(),
                                      valor.strip().strip('"').strip("'"))
    except Exception:
        pass


_cargar_env()

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
    """El cerebro: Pollinations, el de casa (Qwen/Ollama) y Claude de reserva."""
    import os as _os
    preferido = (_os.getenv("JARVIS_CEREBRO") or "").strip().lower()
    revisar_pollinations()
    nube = preferido in ("claude", "anthropic", "nube")
    if not nube and revisar_cerebro_local():
        return
    if not nube:
        linea(AVISO, "Pruebo con Claude, que es la reserva.")
    revisar_ia_nube()


def revisar_pollinations() -> bool:
    """Pollinations: el cerebro de la nube que no pide tarjeta."""
    titulo("2a. Cerebro de la nube (Pollinations)")
    try:
        import proveedor_pollinations as poll
    except Exception as e:
        linea(MAL, f"No pude cargar proveedor_pollinations: {e}")
        return False

    lista = poll.modelos(log=lambda m: None)
    if not lista:
        linea(AVISO, "No contesta. Sin internet, JARVIS tira del cerebro de casa.")
        return False

    if poll.hay_clave():
        linea(OK, f"Clave puesta. Nivel «{poll.nivel()}», "
                  f"una peticion cada {poll.espera_entre_llamadas():.0f} s.")
    else:
        linea(AVISO,
              "SIN clave: nivel anonimo, una peticion cada 15 s. El bucle de "
              "herramientas encadena hasta cuatro, asi que se hace eterno.",
              "consiga la clave en https://auth.pollinations.ai y pongala en "
              "el .env como POLLINATIONS_API_KEY=...")

    con_manos = [m for m in lista if m["herramientas"]]
    if con_manos:
        linea(OK, f"{len(lista)} modelos, {len(con_manos)} con herramientas. "
                  f"Uso «{poll.mejor_modelo(log=lambda m: None)}».")
    else:
        linea(AVISO, "Ningun modelo admite herramientas: JARVIS hablaria pero "
                     "no podria actuar por esta via.")

    r = poll.probar(log=lambda m: None)
    if r.get("ok"):
        linea(OK, f"Responde en {r['segundos']} s con «{r['modelo']}».")
        return True
    linea(MAL, f"No responde: {r.get('error', '')}")
    return False


def revisar_cerebro_local() -> bool:
    titulo("2. Cerebro local (Qwen por Ollama)")
    try:
        import cerebro_local
    except Exception as e:
        linea(MAL, f"No pude cargar cerebro_local: {e}")
        return False
    if not cerebro_local.instalado():
        linea(MAL, "Ollama no esta instalado: sin el no hay cerebro local.",
              "descargalo de https://ollama.com/download")
        return False
    if not cerebro_local.vivo():
        linea(AVISO, "Ollama estaba apagado; lo levanto para comprobarlo.")
        if not cerebro_local.arrancar(log=lambda m: None):
            linea(MAL, "Ollama no arranca.", "pruebe a mano:  ollama serve")
            return False
    instalados = cerebro_local.modelos_instalados()
    modelo = cerebro_local.MODELO
    if modelo not in instalados:
        linea(MAL, f"Falta el modelo «{modelo}» (hay: {', '.join(instalados) or 'ninguno'}).",
              f"ollama pull {modelo}")
        return False
    linea(OK, f"Ollama en marcha con {modelo}")
    ojos = cerebro_local.MODELO_VISION
    if ojos in instalados:
        linea(OK, f"Ojos locales: {ojos} (pantalla, fotos y escaner 3D)")
    else:
        linea(AVISO, f"Sin el modelo con ojos ({ojos}) no puedo mirar imagenes.",
              f"ollama pull {ojos}")
    try:
        from proveedor_claude import cliente as _cli
        c = _cli(cerebro_local.URL, api_key=cerebro_local.CLAVE, timeout=300)
        r = c.chat.completions.create(
            model=modelo, max_tokens=160,
            extra_body={"reasoning_effort": "none"},
            messages=[{"role": "user", "content": "Responde solo: ok"}])
        if (r.choices[0].message.content or "").strip():
            linea(OK, "El cerebro de casa contesta (y no cuesta nada)")
            return True
        linea(MAL, "El modelo local no devolvio nada.",
              f"pruebe uno mas ligero: QWEN_MODEL=qwen3:4b-instruct en el .env")
    except Exception as e:
        linea(MAL, f"El cerebro local fallo: {str(e)[:110]}",
              "mire que Ollama siga en marcha")
    return False


def revisar_ia_nube():
    titulo("2b. Motor de IA en la nube (Claude / Anthropic)")
    import jarvis_config
    if not jarvis_config.hay_clave_llm():
        linea(AVISO, "Sin ANTHROPIC_API_KEY no hay reserva en la nube.",
              "no hace falta si el cerebro local responde; si la quiere, "
              "pon la clave de https://console.anthropic.com en el .env")
        return
    linea(OK, "ANTHROPIC_API_KEY puesta")
    if not hay("anthropic"):
        linea(MAL, "Falta el SDK de Anthropic.",
              "python -m pip install anthropic")
        return
    import os as _os
    modelo_nube = (_os.getenv("JARVIS_MODELO_CLAUDE") or "claude-sonnet-5").strip()
    linea(OK, f"Modelo de reserva: {modelo_nube}")
    # Una llamada minima: la clave puede estar puesta y no valer.
    fallo = ""
    respuesta = ""
    try:
        from proveedor_claude import cliente as _cli, URL_ANTHROPIC
        c = _cli(URL_ANTHROPIC, timeout=20, log=lambda *a: None)
        r = c.chat.completions.create(
            model=modelo_nube, max_tokens=1024,
            messages=[{"role": "user", "content": "Responde solo: ok"}])
        respuesta = (r.choices[0].message.content or "").strip()
    except Exception as e:
        fallo = str(e)

    if respuesta:
        linea(OK, f"La reserva en la nube contesta ({modelo_nube})")
    elif "anthropic-workspace-id" in fallo or "scoped to a workspace" in fallo:
        linea(MAL, "La clave es de organizacion, no de un workspace.",
              "Pon ANTHROPIC_WORKSPACE_ID en el .env (console.anthropic.com -> "
              "Settings -> Workspaces) o crea una clave de workspace")
    elif "credit" in fallo.lower() or "billing" in fallo.lower():
        linea(AVISO, "La clave vale pero la cuenta no tiene saldo.",
              "anade credito en console.anthropic.com -> Billing, o quedese "
              "con el cerebro local, que no cobra")
    elif "authentication" in fallo.lower() or "invalid x-api-key" in fallo.lower():
        linea(MAL, "La clave no es valida.",
              "Revisa ANTHROPIC_API_KEY en el .env")
    elif fallo:
        linea(MAL, f"El cerebro fallo: {fallo[:110]}",
              "Comprueba la clave, el saldo y la red")
    else:
        linea(MAL, "La clave esta puesta pero el cerebro no contesta.",
              "Comprueba saldo y red en console.anthropic.com")


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


def revisar_escaner3d():
    titulo("10. Escaner 3D y holograma")
    try:
        import escaner3d
        import modelado3d
    except Exception as ex:
        linea(MAL, f"No pude revisar el escaner: {ex}")
        return
    if modelado3d.disponible():
        linea(OK, f"Blender: {modelado3d._blender()}")
    else:
        linea(MAL, "Sin Blender no hay modelo ni holograma.",
              "instalalo y pon blender_exe en Descargas/JARVIS/Prefs/modelado3d.json")
    camaras = escaner3d.camaras()
    if camaras:
        linea(OK, f"Camaras del PC: {camaras}")
    else:
        linea(AVISO, "No veo ninguna camara en el equipo.",
              "escanea con el movil: di «escanealo con el movil»")
    if not hay("cv2") or not hay("numpy"):
        linea(AVISO, "Sin OpenCV/NumPy no puedo tallar el volumen con las siluetas.",
              "python -m pip install opencv-python numpy")
    if not hay("cryptography"):
        linea(AVISO, "Sin cryptography no hay HTTPS y el movil no abrira la camara.",
              "python -m pip install cryptography")
    locales = modelado3d.backends()
    if locales:
        linea(OK, f"Reconstructores locales: {', '.join(locales)}")
    else:
        linea(AVISO, "Sin TripoSR/Hunyuan3D/ComfyUI/Meshroom uso mi casco visual.",
              "va bien con fondo liso y una vuelta completa al objeto")
    escaneos = escaner3d.sesiones()
    if escaneos:
        linea(OK, f"Escaneos guardados: {len(escaneos)} (el ultimo, "
                  f"{escaneos[0]['nombre']})")


def main():
    print("=" * 66)
    print("  REVISION DE JARVIS")
    print(f"  {RAIZ}")
    print(f"  Python {sys.version.split()[0]}")
    print("=" * 66)

    for revision in (revisar_dependencias, revisar_ia, revisar_servidores,
                     revisar_movil, revisar_pc, revisar_google,
                     revisar_voz, revisar_telefono, revisar_remoto,
                     revisar_escaner3d):
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
