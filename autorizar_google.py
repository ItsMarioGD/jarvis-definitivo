#!/usr/bin/env python3
"""
autorizar_google.py - Conecta JARVIS con tu Google Calendar. Un solo paso.

Ejecuta:   python autorizar_google.py

Que hace:
  1. Busca el JSON de credenciales (en Google/, con el nombre que le pusiera
     Google al descargarlo) y comprueba que es del tipo correcto.
  2. Abre el navegador para que autorices la cuenta.
  3. Guarda el token junto a las credenciales.
  4. Verifica de verdad: crea un evento de prueba y lo borra.

Opciones:
  --puerto N   Usa el puerto N para el redirect (por si ya tienes otro
               registrado en Google, p. ej. --puerto 8080).
  --json RUTA  Fuerza que credenciales usar, si tienes varias.
  --buscar     Solo dice donde busca y que encuentra (no autoriza nada).
  --revocar    Olvida la autorizacion (borra el token).
  --sin-probar No crea el evento de prueba.
"""
import os
import sys
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _explicar_mismatch(jarvis_config, info):
    """El fallo mas comun. Se explica entero, con el valor a copiar."""
    uri = jarvis_config.REDIRECT_OAUTH
    print("\n" + "=" * 62)
    print(" Google rechazo el redirect  (Error 400: redirect_uri_mismatch)")
    print("=" * 62)
    print("\n  El redirect que enviamos es EXACTAMENTE:")
    print(f"\n      {uri}\n")
    print("  Copialo tal cual (mejor copiar que teclear) en la pantalla de tu")
    print("  ID de cliente. Enlace directo:")
    proy = info.get("proyecto", "")
    cid_completo = ""
    try:
        import json as _j
        datos = _j.load(open(info["ruta"], encoding="utf-8-sig"))
        cid_completo = (datos.get("web") or datos.get("installed") or {}).get("client_id", "")
    except Exception:
        pass
    if cid_completo and proy:
        print(f"\n    https://console.cloud.google.com/apis/credentials/oauthclient/"
              f"{cid_completo}?project={proy}")
    print("\n  Si ya tienes OTRO redirect de localhost registrado ahi, no hace")
    print("  falta anadir nada: relanza esto con ese puerto. Ejemplo:")
    print("      python autorizar_google.py --puerto 8080")
    print("\n  Fallos tipicos al pegarlo:")
    print(f"    - sin la barra final       (tiene que ser  ...:{jarvis_config.OAUTH_PORT}/  )")
    print("    - 127.0.0.1 en vez de localhost  (usamos localhost)")
    print("    - https:// en vez de http://     (es http, sin la s)")
    print("    - pegarlo en «Origenes autorizados de JavaScript»")
    print("      (ese campo va VACIO; es el de REDIRECCIONAMIENTO)")
    print("    - guardarlo en otro ID de cliente distinto del que usa el JSON")
    print("\n  Tras darle a GUARDAR, Google tarda un rato en aplicarlo:")
    print("  si acabas de hacerlo, espera un par de minutos y reintenta.")
    print("=" * 62)
    sys.exit(1)


LIBRERIAS = ["google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2"]


def _importa_google() -> bool:
    try:
        import google.auth.transport.requests  # noqa: F401
        import google.oauth2.credentials       # noqa: F401
        import google_auth_oauthlib.flow       # noqa: F401
        import googleapiclient.discovery       # noqa: F401
        return True
    except Exception:
        return False


def _cargar_librerias_google() -> bool:
    """Importa las librerias de Google; si faltan, las instala y reintenta.

    Usa sys.executable en vez de "pip" a secas: con varios Python instalados
    (el del sistema, el de C:\\Python314...) un "pip install" suelto puede
    acabar instalando en un interprete distinto del que ejecuta JARVIS, y el
    import seguiria fallando igual.
    """
    if _importa_google():
        return True
    print("\n  Faltan las librerias de Google. Las instalo ahora en:")
    print(f"    {sys.executable}")
    import subprocess
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                            *LIBRERIAS], timeout=600)
    except Exception as e:
        print(f"  No pude lanzar pip: {e}")
        return False
    if r.returncode != 0:
        print(f"  pip termino con error (codigo {r.returncode}).")
        return False
    # Los modulos recien instalados pueden no verse sin refrescar la cache.
    import importlib
    importlib.invalidate_caches()
    if _importa_google():
        print("  [OK] Librerias instaladas.")
        return True
    print("  Instaladas, pero siguen sin importarse. Cierra esta ventana y "
          "vuelve a ejecutar el script.")
    return False


def fatal(msg, ayuda=""):
    print(f"\n  [MAL] {msg}")
    if ayuda:
        print(f"        {ayuda}")
    sys.exit(1)


def main():
    import jarvis_config

    # --puerto N: usar un redirect que ya este registrado en Google, en vez
    # de tener que anadir uno nuevo.
    if "--json" in sys.argv:
        try:
            ruta = sys.argv[sys.argv.index("--json") + 1]
        except IndexError:
            fatal("--json necesita la ruta de un fichero .json")
        if not os.path.isfile(ruta):
            fatal(f"No existe: {ruta}")
        os.environ["GOOGLE_CREDENTIALS_JSON"] = os.path.abspath(ruta)
        import importlib
        importlib.reload(jarvis_config)

    if "--puerto" in sys.argv:
        try:
            n = int(sys.argv[sys.argv.index("--puerto") + 1])
            jarvis_config.OAUTH_PORT = n
            jarvis_config.REDIRECT_OAUTH = f"http://localhost:{n}/"
            print(f"  (usando el puerto {n}: redirect {jarvis_config.REDIRECT_OAUTH})")
        except (ValueError, IndexError):
            fatal("--puerto necesita un numero, por ejemplo: --puerto 8080")

    print("=" * 62)
    print(" Autorizar JARVIS en Google Calendar")
    print("=" * 62)

    if "--buscar" in sys.argv:
        print(f"\n  Carpeta preferida: {jarvis_config.GOOGLE_DIR}")
        print("  Tambien miro en la raiz del proyecto, en cualquier subcarpeta")
        print("  suya (hasta 3 niveles), en Prefs y en la carpeta de descargas.")
        print("  Nombres que reconozco: client_secret*.json, credentials*.json,")
        print("  *oauth*.json\n")
        hallados = jarvis_config.listar_credenciales_google()
        if not hallados:
            print("  No he encontrado ningun JSON de credenciales.")
            print("\n  Si crees que lo dejaste en el proyecto, comprueba que:")
            print("   - esta dentro de esta carpeta:")
            print(f"       {jarvis_config.PROJECT_ROOT}")
            print("   - termina en .json (Windows puede ocultar la extension)")
            print("   - no esta dentro de un .zip sin descomprimir")
            return 1
        for h in hallados:
            marca = "  ->" if h == jarvis_config.buscar_credenciales_google() else "    "
            print(f"{marca} {h}")
        info = jarvis_config.revisar_credenciales_google()
        print(f"\n  Usare el marcado con «->». Tipo: "
              f"{info['tipo'] or '?'} — {'valido' if info['ok'] else info['error']}")
        return 0 if info["ok"] else 1

    if "--revocar" in sys.argv:
        tok = jarvis_config.ruta_token_google()
        if os.path.exists(tok):
            os.remove(tok)
            print(f"\n  Token borrado: {tok}")
            print("  JARVIS ya no tiene acceso. Vuelve a ejecutar esto para reconectar.")
        else:
            print("\n  No habia ninguna autorizacion guardada.")
        return 0

    # ── 1. Credenciales ──────────────────────────────────────────────────────
    print(f"\n[1/4] Buscando credenciales en {jarvis_config.GOOGLE_DIR} ...")
    info = jarvis_config.revisar_credenciales_google()
    if not info["ok"]:
        fatal(info["error"],
              "Si ya tienes el ID de cliente creado, entra en el (Credenciales "
              "→ clic en su nombre) y pulsa «DESCARGAR JSON» arriba. Guarda ese "
              "fichero en la carpeta Google/ del proyecto y vuelve a ejecutar "
              "esto. Acuerdate tambien de activar la API de Google Calendar.")
    print(f"  [OK] {os.path.basename(info['ruta'])}")
    if info.get("cliente"):
        print(f"       cliente:  {info['cliente']}")
    if info.get("proyecto"):
        print(f"       proyecto: {info['proyecto']}")
    print(f"       tipo:     {info['tipo']}")
    otros = [c for c in jarvis_config.listar_credenciales_google()
             if os.path.abspath(c) != os.path.abspath(info["ruta"])]
    if otros:
        print(f"\n  [!] Hay {len(otros) + 1} ficheros de credenciales. Uso el mas")
        print("      reciente. Los otros:")
        for o in otros[:4]:
            print(f"        - {os.path.basename(o)}")
        print("      Si no es el que quieres, borra los que sobren o usa:")
        print("        python autorizar_google.py --json RUTA")
    if info.get("aviso"):
        print("\n  " + "-" * 58)
        print("  ATENCION, un paso previo en Google Cloud Console:")
        print(f"    1. Credenciales → tu ID de cliente OAuth")
        print(f"    2. «URI de redireccionamiento autorizados» → AÑADIR URI")
        print(f"    3. Pega exactamente:  {info['redirect']}")
        print(f"    4. Guardar (tarda unos segundos en aplicarse)")
        print("  Sin eso Google respondera «redirect_uri_mismatch».")
        print("  " + "-" * 58)

    if not _cargar_librerias_google():
        fatal("No pude preparar las librerias de Google.",
              f'Instalalas a mano con:  "{sys.executable}" -m pip install '
              "google-api-python-client google-auth-oauthlib google-auth-httplib2")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    # ── 2. Autorizacion ──────────────────────────────────────────────────────
    token_path = jarvis_config.ruta_token_google()
    creds = None
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        print(f"\n[2/4] Ya estabas autorizado ({os.path.basename(token_path)}).")
    else:
        if creds and creds.expired and creds.refresh_token:
            print("\n[2/4] Renovando la autorizacion caducada ...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"  No se pudo renovar ({e}); pedire autorizacion de nuevo.")
                creds = None
        if not creds or not creds.valid:
            print(f"\n[2/4] Abriendo el navegador (servidor local en el puerto "
                  f"{jarvis_config.OAUTH_PORT}) ...")
            print("      El redirect que se le envia a Google es EXACTAMENTE este:")
            print(f"          {jarvis_config.REDIRECT_OAUTH}")
            print("      Tiene que estar, tal cual (con http://, con el puerto y")
            print("      con la barra final), en «URI de redireccionamiento")
            print("      autorizados» de tu ID de cliente.")
            print("      Si te avisa de que la app «no esta verificada», es la tuya:")
            print("      pulsa «Configuracion avanzada» y continua.")
            # Puerto FIJO: con credenciales de tipo «web» Google valida el
            # redirect contra los registrados, y uno aleatorio nunca casaria.
            puerto = jarvis_config.OAUTH_PORT
            try:
                flow = InstalledAppFlow.from_client_secrets_file(info["ruta"], SCOPES)
                creds = flow.run_local_server(port=puerto, open_browser=True)
            except Exception as e:
                detalle = str(e)
                if "redirect_uri_mismatch" in detalle or "redirect" in detalle.lower():
                    _explicar_mismatch(jarvis_config, info)
                if "mismatching_state" in detalle or "CSRF" in detalle:
                    fatal("El navegador respondio a una autorizacion ANTERIOR "
                          "(mismatching_state).",
                          "Cierra TODAS las pestanas de «Acceder con Google» y "
                          "las de localhost:8088, y vuelve a lanzar el script. "
                          "Pasa cuando queda abierto un intento previo: el "
                          "navegador devuelve el codigo viejo y no cuadra con "
                          "la peticion nueva.")
                if "access_denied" in detalle or "403" in detalle:
                    fatal(f"Google denego el acceso: {detalle[:150]}",
                          "En «Pantalla de consentimiento de OAuth» anade tu "
                          "correo como usuario de prueba, y comprueba que el "
                          "permiso de Calendar esta en la lista de scopes.")
                if "address already in use" in detalle.lower() or "10048" in detalle:
                    fatal(f"El puerto {puerto} esta ocupado.",
                          "Cierra lo que lo use, o define GOOGLE_OAUTH_PORT con "
                          "otro puerto (y registra el nuevo redirect en Google).")
                fatal(f"La autorizacion fallo: {detalle[:200]}",
                      "Comprueba que la API de Google Calendar esta activada en "
                      f"el proyecto «{info.get('proyecto', '?')}» y que tu correo "
                      "esta como usuario de prueba.")

    # ── 3. Guardar ───────────────────────────────────────────────────────────
    try:
        os.makedirs(os.path.dirname(token_path) or ".", exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    except Exception as e:
        fatal(f"No pude guardar el token en {token_path}: {e}")
    print(f"\n[3/4] Autorizacion guardada en {token_path}")
    print("      (esta en .gitignore: no se subira al repositorio)")

    # ── 4. Probar de verdad ──────────────────────────────────────────────────
    if "--sin-probar" in sys.argv:
        print("\n[4/4] Prueba omitida (--sin-probar).")
        return 0
    print("\n[4/4] Probando: creo un evento y lo borro ...")
    try:
        service = build("calendar", "v3", credentials=creds)
        cals = service.calendarList().list().execute().get("items", [])
        principal = next((c for c in cals if c.get("primary")), {})
        print(f"  [OK] Cuenta: {principal.get('id', '(desconocida)')}")

        inicio = datetime.now() + timedelta(days=370)
        ev = service.events().insert(calendarId="primary", body={
            "summary": "Prueba de JARVIS (se borra sola)",
            "description": "Creado por autorizar_google.py para verificar el acceso.",
            "start": {"dateTime": inicio.strftime("%Y-%m-%dT%H:%M:%S"),
                      "timeZone": os.getenv("JARVIS_TIMEZONE", "Europe/Madrid")},
            "end": {"dateTime": (inicio + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": os.getenv("JARVIS_TIMEZONE", "Europe/Madrid")},
        }).execute()
        print(f"  [OK] Evento creado (id {ev['id'][:12]}…)")
        service.events().delete(calendarId="primary", eventId=ev["id"]).execute()
        print("  [OK] Evento borrado. Permisos de escritura confirmados.")
    except Exception as e:
        fatal(f"No pude escribir en el calendario: {e}",
              "Revisa que la API de Google Calendar este activada en el proyecto "
              "de Google Cloud y que autorizaste el permiso de calendario.")

    print("\n" + "=" * 62)
    print(" LISTO. Arranca JARVIS con start_jarvis.bat y prueba a decirle:")
    print('   «Jarvis, agenda una reunión con Marta mañana a las 5»')
    print('   «¿qué citas tengo esta semana?»')
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
