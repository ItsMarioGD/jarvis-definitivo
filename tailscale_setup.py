"""
tailscale_setup.py — Deja el telefono hablando con JARVIS desde cualquier sitio
==============================================================================
Antes del formateo el señor tenia Tailscale: el movil llegaba al PC por su IP
aunque no estuvieran en el mismo Wi-Fi. Esto lo vuelve a dejar igual:

    python tailscale_setup.py             → instala, conecta y diagnostica
    python tailscale_setup.py --estado    → solo mira como esta la cosa
    python tailscale_setup.py --firewall  → solo abre los puertos de JARVIS
    python tailscale_setup.py --https     → solo publica la interfaz en HTTPS
    python tailscale_setup.py --sin-https → retira esa publicacion

Lo que hace, en orden:
  1. Busca tailscale.exe; si no esta, lo instala (winget y, si falla, el MSI).
  2. Levanta la VPN (`tailscale up`) y enseña el enlace de login si hace falta.
  3. Abre en el Firewall de Windows los puertos 5000 (web), 8765 (JARVIS) y
     8766 (ULTRON) para la red privada y para la 100.64.0.0/10 de Tailscale.
  4. Publica la interfaz en https://<equipo>.ts.net con `tailscale serve`.
     Sin HTTPS el movil entra por http://, que no es «origen seguro», y el
     navegador BLOQUEA el microfono: los comandos de voz no funcionarian.
  5. Imprime la direccion exacta que hay que abrir en el telefono.

El paso 3 es la causa mas habitual de «no responde en el telefono»: el servidor
escucha en 0.0.0.0 pero el Firewall tira los paquetes que vienen de fuera.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time

try:
    import jarvis_config
    PUERTO_WEB = jarvis_config.PORT
except Exception:                                            # pragma: no cover
    jarvis_config = None
    PUERTO_WEB = int(os.getenv("JARVIS_PORT", "5000"))

PUERTOS = {
    PUERTO_WEB: "JARVIS Web (movil y HUD)",
    8765: "JARVIS backend",
    8766: "ULTRON backend",
}

_IS_WIN = os.name == "nt"
_SIN_VENTANA = 0x08000000 if _IS_WIN else 0
MSI_URL = "https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi"

# Tailscale reparte direcciones dentro de 100.64.0.0/10 (CGNAT).
RED_TAILSCALE = "100.64.0.0/10"


def _run(cmd, timeout=180):
    """Ejecuta y devuelve (codigo, salida). Nunca lanza."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=_SIN_VENTANA if _IS_WIN else 0)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except FileNotFoundError:
        return 127, f"no encuentro {cmd[0] if isinstance(cmd, list) else cmd}"
    except subprocess.TimeoutExpired:
        return 124, "se agoto el tiempo de espera"
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Localizar el ejecutable
# ─────────────────────────────────────────────────────────────────────────────
def buscar_tailscale() -> str:
    """Ruta de tailscale(.exe) o "" si no esta instalado."""
    if jarvis_config is not None:
        # jarvis_config lo cachea al importar: si acabamos de instalarlo, ese
        # valor esta obsoleto, asi que se vuelve a buscar de cero.
        try:
            ruta = jarvis_config.find_tailscale()
            if ruta:
                return ruta
        except Exception:
            pass
    candidatas = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     "Tailscale", "tailscale.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     "Tailscale", "tailscale.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tailscale", "tailscale.exe"),
    ]
    for c in candidatas:
        if c and os.path.isfile(c):
            return c
    encontrado = shutil.which("tailscale")
    return encontrado or ""


# ─────────────────────────────────────────────────────────────────────────────
# Instalacion
# ─────────────────────────────────────────────────────────────────────────────
def instalar(log=print) -> str:
    """Instala Tailscale si falta. Devuelve la ruta del ejecutable o ""."""
    ruta = buscar_tailscale()
    if ruta:
        log(f"[tailscale] Ya esta instalado: {ruta}")
        return ruta
    if not _IS_WIN:
        log("[tailscale] Este instalador automatico es para Windows. En Linux: "
            "curl -fsSL https://tailscale.com/install.sh | sh")
        return ""

    log("[tailscale] No esta instalado. Probando con winget...")
    codigo, salida = _run(["winget", "install", "--id", "Tailscale.Tailscale",
                           "-e", "--source", "winget",
                           "--accept-package-agreements", "--accept-source-agreements",
                           "--silent"], timeout=900)
    if codigo == 0:
        log("[tailscale] Instalado con winget.")
    else:
        log(f"[tailscale] winget no pudo ({salida[:160]}). Descargando el MSI...")
        if not _instalar_msi(log):
            return ""

    # El instalador tarda un poco en dejar el .exe donde toca.
    for _ in range(20):
        ruta = buscar_tailscale()
        if ruta:
            log(f"[tailscale] Listo: {ruta}")
            return ruta
        time.sleep(1.5)
    log("[tailscale] Se instalo pero no encuentro tailscale.exe. Reinicie la "
        "consola (o el PC) y vuelva a ejecutar este script.")
    return ""


def _instalar_msi(log=print) -> bool:
    """Descarga el MSI oficial y lo instala en silencio."""
    import tempfile
    destino = os.path.join(tempfile.gettempdir(), "tailscale-setup.msi")
    try:
        import urllib.request
        log(f"[tailscale] Bajando {MSI_URL}")
        urllib.request.urlretrieve(MSI_URL, destino)
    except Exception as e:
        log(f"[tailscale] No pude descargar el instalador: {e}")
        log(f"[tailscale] Bajelo a mano de {MSI_URL} y ejecutelo.")
        return False
    log("[tailscale] Instalando (puede pedir permisos de administrador)...")
    codigo, salida = _run(["msiexec", "/i", destino, "/quiet", "/norestart"], timeout=900)
    if codigo != 0:
        log(f"[tailscale] msiexec devolvio {codigo}: {salida[:200]}")
        log(f"[tailscale] Ejecute a mano: {destino}")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Conexion
# ─────────────────────────────────────────────────────────────────────────────
def levantar(log=print, exe: str = "") -> dict:
    """`tailscale up`. Si hace falta login, enseña el enlace y espera."""
    exe = exe or buscar_tailscale()
    if not exe:
        return {"ok": False, "error": "Tailscale no esta instalado."}

    st = estado(exe)
    if st.get("conectado"):
        log(f"[tailscale] Ya conectado como {st.get('dns') or st.get('ip')}.")
        return {"ok": True, **st}

    log("[tailscale] Conectando...")
    codigo, salida = _run([exe, "up", "--accept-routes", "--operator=" +
                           os.environ.get("USERNAME", "")], timeout=90) \
        if _IS_WIN and os.environ.get("USERNAME") else _run([exe, "up", "--accept-routes"], timeout=90)

    enlace = re.search(r"https://login\.tailscale\.com/\S+", salida or "")
    if enlace:
        url = enlace.group(0)
        log("")
        log("  ┌──────────────────────────────────────────────────────────┐")
        log("  │  ABRA ESTE ENLACE Y ENTRE CON SU CUENTA DE TAILSCALE:    │")
        log("  └──────────────────────────────────────────────────────────┘")
        log(f"  {url}")
        log("")
        log("  Use LA MISMA cuenta en el movil (app Tailscale).")
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
        for _ in range(60):                                  # 5 minutos
            time.sleep(5)
            st = estado(exe)
            if st.get("conectado"):
                log(f"[tailscale] Conectado como {st.get('dns') or st.get('ip')}.")
                return {"ok": True, **st}
        return {"ok": False, "error": "Se agoto la espera del login.", "login": url}

    if codigo != 0:
        return {"ok": False, "error": salida[:300] or f"codigo {codigo}"}
    st = estado(exe)
    return {"ok": bool(st.get("conectado")), **st}


def estado(exe: str = "") -> dict:
    """Radiografia de Tailscale: instalado, conectado, IP, MagicDNS y equipos."""
    exe = exe or buscar_tailscale()
    base = {"instalado": bool(exe), "exe": exe, "conectado": False,
            "ip": "", "dns": "", "equipos": [], "error": ""}
    if not exe:
        base["error"] = "Tailscale no esta instalado."
        return base
    codigo, salida = _run([exe, "status", "--json"], timeout=20)
    if codigo != 0:
        base["error"] = salida[:200]
        return base
    try:
        datos = json.loads(salida)
    except Exception as e:
        base["error"] = f"no entendi la respuesta de tailscale ({e})"
        return base
    yo = datos.get("Self") or {}
    ips = yo.get("TailscaleIPs") or []
    base["ip"] = next((i for i in ips if ":" not in i), ips[0] if ips else "")
    base["dns"] = (yo.get("DNSName") or "").rstrip(".")
    base["conectado"] = (datos.get("BackendState") == "Running") and bool(base["ip"])
    base["estado_backend"] = datos.get("BackendState", "")
    for par in (datos.get("Peer") or {}).values():
        base["equipos"].append({
            "nombre": (par.get("DNSName") or par.get("HostName") or "").rstrip("."),
            "ip": next((i for i in (par.get("TailscaleIPs") or []) if ":" not in i), ""),
            "en_linea": bool(par.get("Online")),
            "so": par.get("OS", ""),
        })
    return base


# ─────────────────────────────────────────────────────────────────────────────
# HTTPS dentro del tailnet: sin esto el movil no puede usar el microfono
# ─────────────────────────────────────────────────────────────────────────────
def estado_serve(exe: str = "", puerto: int = None) -> dict:
    """¿Esta el servidor publicado por HTTPS en el tailnet?"""
    exe = exe or buscar_tailscale()
    puerto = puerto or PUERTO_WEB
    base = {"activo": False, "url": "", "error": ""}
    if not exe:
        base["error"] = "Tailscale no esta instalado."
        return base
    codigo, salida = _run([exe, "serve", "status"], timeout=20)
    if codigo != 0:
        base["error"] = salida[:200]
        return base
    # La salida lista lineas del tipo «https://equipo.ts.net (tailnet only)»
    # seguidas del destino local. Nos vale con encontrar nuestro puerto.
    if f"127.0.0.1:{puerto}" in salida or f"localhost:{puerto}" in salida:
        base["activo"] = True
        m = re.search(r"https://[\w.-]+\.ts\.net\S*", salida or "")
        if m:
            base["url"] = m.group(0).rstrip("/")
    return base


def servir_https(log=print, exe: str = "", puerto: int = None) -> dict:
    """Publica el servidor local en https://<equipo>.ts.net (tailscale serve).

    Por que hace falta: por HTTP plano el telefono entra en
    http://100.x.x.x:5000, que NO es un «origen seguro». Chrome y Safari
    bloquean ahi el microfono, asi que ni el dictado ni los comandos de voz
    funcionan desde el movil por mucho que la pagina cargue. Con serve, la
    MISMA interfaz queda en HTTPS con un certificado valido de Let's Encrypt
    y el microfono vuelve a estar permitido.

    Requiere tener activados MagicDNS y «HTTPS Certificates» en la consola de
    Tailscale; si no lo estan, el propio comando lo dice y lo repetimos aqui.
    """
    exe = exe or buscar_tailscale()
    puerto = puerto or PUERTO_WEB
    if not exe:
        return {"ok": False, "error": "Tailscale no esta instalado."}

    ya = estado_serve(exe, puerto)
    if ya.get("activo"):
        log(f"[tailscale] HTTPS ya publicado: {ya.get('url') or '(sin MagicDNS)'}")
        return {"ok": True, **ya}

    log("[tailscale] Publicando la interfaz por HTTPS dentro del tailnet...")
    codigo, salida = _run([exe, "serve", "--bg", "--https=443",
                           f"http://127.0.0.1:{puerto}"], timeout=90)
    if codigo != 0:
        # El fallo tipico es no tener los certificados HTTPS activados.
        pista = ""
        if "https" in (salida or "").lower() or "cert" in (salida or "").lower():
            pista = ("Active «HTTPS Certificates» y MagicDNS en "
                     "https://login.tailscale.com/admin/dns y repita.")
        log(f"[tailscale] No pude publicar HTTPS: {salida[:200]}")
        if pista:
            log(f"[tailscale] {pista}")
        return {"ok": False, "error": salida[:200], "ayuda": pista}

    st = estado_serve(exe, puerto)
    if st.get("url"):
        log(f"[tailscale] HTTPS listo: {st['url']}")
    return {"ok": True, **st}


def dejar_de_servir(log=print, exe: str = "") -> bool:
    """Retira la publicacion HTTPS (vuelve a quedar solo el HTTP del puerto)."""
    exe = exe or buscar_tailscale()
    if not exe:
        return False
    codigo, salida = _run([exe, "serve", "--https=443", "off"], timeout=45)
    if codigo != 0:
        codigo, salida = _run([exe, "serve", "reset"], timeout=45)
    log("[tailscale] Publicacion HTTPS retirada." if codigo == 0
        else f"[tailscale] No pude retirarla: {salida[:150]}")
    return codigo == 0


# ─────────────────────────────────────────────────────────────────────────────
# Firewall (la causa nº1 de «no responde en el telefono»)
# ─────────────────────────────────────────────────────────────────────────────
def abrir_firewall(log=print) -> dict:
    """Reglas de entrada para los puertos de JARVIS. Necesita administrador."""
    if not _IS_WIN:
        return {"ok": True, "detalle": "No es Windows: no hay nada que abrir."}
    resultado, todo_ok = {}, True
    for puerto, desc in PUERTOS.items():
        nombre = f"JARVIS {puerto}"
        _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nombre}"], timeout=30)
        codigo, salida = _run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={nombre}", "dir=in", "action=allow", "protocol=TCP",
            f"localport={puerto}", "profile=private,domain",
            f"remoteip=LocalSubnet,{RED_TAILSCALE}",
            f"description={desc}",
        ], timeout=30)
        ok = codigo == 0
        todo_ok &= ok
        resultado[puerto] = "abierto" if ok else salida[:120]
        log(f"[firewall] {puerto} ({desc}): {'OK' if ok else 'FALLO — ' + salida[:120]}")
    if not todo_ok:
        log("[firewall] Si dice «acceso denegado», abra la consola como "
            "ADMINISTRADOR y repita.")
    return {"ok": todo_ok, "puertos": resultado}


def firewall_configurado() -> bool:
    """¿Existe ya la regla del puerto web?"""
    if not _IS_WIN:
        return True
    codigo, salida = _run(["netsh", "advfirewall", "firewall", "show", "rule",
                           f"name=JARVIS {PUERTO_WEB}"], timeout=20)
    return codigo == 0 and "JARVIS" in (salida or "")


# ─────────────────────────────────────────────────────────────────────────────
# Resumen para el señor (y para el comando de voz «estado de la red»)
# ─────────────────────────────────────────────────────────────────────────────
def ip_local() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith(("127.", "169.254")):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def resumen(puerto: int = None) -> dict:
    """Todo lo que hace falta para conectar el telefono."""
    puerto = puerto or PUERTO_WEB
    st = estado()
    serve = estado_serve(puerto=puerto)
    lan = ip_local()
    urls = []
    # La direccion HTTPS va la PRIMERA a proposito: es la unica desde la que
    # el navegador del movil deja usar el microfono (las http:// no son
    # «origen seguro» y Chrome y Safari bloquean ahi los comandos de voz).
    if serve.get("activo") and serve.get("url"):
        urls.append({"tipo": "https", "url": serve["url"] + "/mobile",
                     "nota": "La mejor: cifrada y la unica que permite usar el "
                             "microfono desde el movil."})
    if st.get("dns"):
        urls.append({"tipo": "tailscale-dns", "url": f"http://{st['dns']}:{puerto}/mobile",
                     "nota": "Desde cualquier red, con la app Tailscale abierta en el movil."})
    if st.get("ip"):
        urls.append({"tipo": "tailscale-ip", "url": f"http://{st['ip']}:{puerto}/mobile",
                     "nota": "La misma via, por IP, si MagicDNS no resuelve."})
    urls.append({"tipo": "lan", "url": f"http://{lan}:{puerto}/mobile",
                 "nota": "Solo con el movil en el mismo Wi-Fi que el PC."})
    return {
        "puerto": puerto,
        "ip_local": lan,
        "tailscale": st,
        "serve": serve,
        "firewall_ok": firewall_configurado(),
        "urls": urls,
        "recomendada": urls[0]["url"],
    }


def resumen_texto(puerto: int = None) -> str:
    """Una o dos frases para que las diga JARVIS en voz alta."""
    r = resumen(puerto)
    ts = r["tailscale"]
    partes = []
    if ts.get("conectado"):
        partes.append(f"Tailscale conectado como {ts.get('dns') or ts.get('ip')}.")
    elif ts.get("instalado"):
        partes.append("Tailscale esta instalado pero desconectado; ejecute "
                      "«instalar_tailscale.bat» para volver a entrar.")
    else:
        partes.append("Tailscale no esta instalado: sin el, el movil solo llega "
                      "desde el mismo Wi-Fi.")
    if not r["firewall_ok"]:
        partes.append("Ademas el Firewall no tiene abiertos mis puertos, que es "
                      "el motivo mas habitual de que el movil no reciba respuesta.")
    if not r.get("serve", {}).get("activo"):
        partes.append("La interfaz no esta publicada por HTTPS, asi que desde el "
                      "movil no se puede usar el microfono.")
    partes.append(f"Direccion para el telefono: {r['recomendada']}")
    return " ".join(partes)


# ─────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    log = print

    if "--estado" in argv:
        print(json.dumps(resumen(), indent=2, ensure_ascii=False))
        return 0
    if "--firewall" in argv:
        return 0 if abrir_firewall(log)["ok"] else 1
    if "--https" in argv:
        return 0 if servir_https(log)["ok"] else 1
    if "--sin-https" in argv:
        return 0 if dejar_de_servir(log) else 1

    print("=" * 62)
    print("  TAILSCALE PARA JARVIS — conexion del telefono")
    print("=" * 62)

    exe = instalar(log)
    if not exe:
        print("\nNo pude dejar Tailscale instalado. Instalelo a mano desde "
              "https://tailscale.com/download/windows y vuelva a ejecutar esto.")
        return 1

    res = levantar(log, exe)
    if not res.get("ok"):
        print(f"\n[tailscale] No quedo conectado: {res.get('error', '')}")
        print("Abra la app de Tailscale en la bandeja del sistema y pulse «Connect».")

    print("\n— Abriendo puertos en el Firewall de Windows —")
    abrir_firewall(log)

    print("\n— Publicando la interfaz por HTTPS (para el microfono del movil) —")
    servir_https(log, exe)

    r = resumen()
    print("\n" + "=" * 62)
    print("  COMO ENTRAR DESDE EL TELEFONO")
    print("=" * 62)
    for u in r["urls"]:
        print(f"  {u['url']}")
        print(f"      {u['nota']}")
    print("\n  PIN de emparejamiento: abra http://localhost:%d/pair en el PC." % r["puerto"])
    print("\n  En el movil: instale la app «Tailscale», entre con LA MISMA cuenta,")
    print("  dejela conectada, y abra la primera direccion de la lista.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
