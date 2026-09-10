#!/usr/bin/env python3
"""
red_movil.py - Que el telefono encuentre al PC sin que nadie lo configure
========================================================================
El emparejamiento fallaba por una razon tonta y muy repetible: el PC coge una
IP nueva del router (DHCP) y el QR que estaba en pantalla seguia apuntando a la
IP vieja. El telefono escanea, intenta abrir una direccion que ya no existe y
se queda cargando para siempre.

Aqui esta todo lo que hace falta para que eso no vuelva a pasar:

  * ips_lan()      TODAS las direcciones por las que se puede llegar al PC,
                   ordenadas de mejor a peor, sin las que no sirven (169.254
                   de un cable sin red, la 100.x de Tailscale, VPNs sueltas).
  * mejor_ip()     la que hay que poner en el QR ahora mismo.
  * firewall()     si el cortafuegos de Windows deja pasar el puerto.
  * abrir_firewall()  crea la regla (pide permiso de administrador una vez).
  * preparar()     lo anterior junto, para llamarlo al arrancar el servidor.
  * diagnostico()  cuando aun asi no carga: que mirar, por orden de sospecha.

Nada de esto necesita que el señor toque una consola.
"""
import ipaddress
import os
import socket
import subprocess

PUERTOS = (5000, 8766)          # JARVIS y ULTRON
REGLA = "JARVIS Movil"


# ── direcciones ─────────────────────────────────────────────────────────────
def _powershell(orden: str, timeout: int = 12) -> str:
    if os.name != "nt":
        return ""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", orden],
                           capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _ip_de_salida() -> str:
    """La IP con la que este equipo sale a la red. La mejor pista de cual vale."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def _util(ip: str) -> bool:
    """¿Sirve esta IP para que un telefono del mismo WiFi llegue al PC?"""
    try:
        d = ipaddress.ip_address(ip)
    except Exception:
        return False
    if d.is_loopback or d.is_link_local:      # 127.x y 169.254.x
        return False
    if ip.startswith("100."):                  # Tailscale: solo con su app
        return False
    return d.is_private


_cache = {"ts": 0.0, "ips": []}
SEGUNDOS_CACHE = 15


def ips_lan(refrescar: bool = False) -> list:
    """Direcciones por las que se puede entrar, de mejor a peor.

    Cada una viene con la interfaz y el perfil de red, que hacen falta para
    explicarle al señor por que una funciona y otra no.

    Se guarda quince segundos: la pagina de emparejamiento pregunta cada cuatro
    y arrancar PowerShell cada vez es tirar medio segundo a la basura.
    """
    import time as _t
    if not refrescar and _cache["ips"] and _t.time() - _cache["ts"] < SEGUNDOS_CACHE:
        return _cache["ips"]
    salida = _ip_de_salida()
    encontradas, vistas = [], set()

    # Las dos consultas van en UNA sola llamada: arrancar PowerShell cuesta
    # dos segundos y medio, y hacerlo dos veces se nota al abrir la pagina.
    todo = _powershell(
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.IPAddress -ne '127.0.0.1' } | "
        "ForEach-Object { 'IP|' + $_.IPAddress + '|' + $_.InterfaceAlias }; "
        "Get-NetConnectionProfile | ForEach-Object "
        "{ 'PERFIL|' + $_.InterfaceAlias + '|' + $_.NetworkCategory }",
        timeout=20)
    lineas_ip, perfiles = [], {}
    for linea in todo.splitlines():
        partes = linea.split("|")
        if len(partes) != 3:
            continue
        if partes[0] == "IP":
            lineas_ip.append(f"{partes[1]}|{partes[2]}")
        elif partes[0] == "PERFIL":
            perfiles[partes[1].strip()] = partes[2].strip()
    bruto = "\n".join(lineas_ip)

    for linea in bruto.splitlines():
        if "|" not in linea:
            continue
        ip, alias = (p.strip() for p in linea.split("|", 1))
        if not _util(ip) or ip in vistas:
            continue
        vistas.add(ip)
        encontradas.append({"ip": ip, "interfaz": alias,
                            "perfil": perfiles.get(alias, ""),
                            "salida": ip == salida})

    # Sin PowerShell (o sin Windows) al menos queda la de salida.
    if not encontradas and _util(salida):
        encontradas.append({"ip": salida, "interfaz": "", "perfil": "", "salida": True})

    def peso(e):
        # La de salida primero; luego WiFi y Ethernet; las virtuales al final.
        alias = (e["interfaz"] or "").lower()
        virtual = any(p in alias for p in ("vmware", "virtualbox", "hyper-v",
                                           "vethernet", "openvpn", "tap", "tun"))
        real = any(p in alias for p in ("wi-fi", "wifi", "ethernet", "lan"))
        return (not e["salida"], virtual, not real, e["ip"])

    _cache["ips"] = sorted(encontradas, key=peso)
    _cache["ts"] = _t.time()
    return _cache["ips"]


def mejor_ip() -> str:
    lista = ips_lan()
    return lista[0]["ip"] if lista else "127.0.0.1"


def tailscale_ip() -> str:
    for linea in _powershell(
            "Get-NetIPAddress -AddressFamily IPv4 | "
            "ForEach-Object { $_.IPAddress }").splitlines():
        if linea.strip().startswith("100."):
            return linea.strip()
    return ""


# ── cortafuegos ─────────────────────────────────────────────────────────────
def firewall() -> dict:
    """Si el cortafuegos esta activo y si deja pasar el puerto."""
    if os.name != "nt":
        return {"activo": False, "regla": True, "perfiles": []}
    activos = [l.strip() for l in _powershell(
        "Get-NetFirewallProfile | Where-Object { $_.Enabled } | "
        "ForEach-Object { $_.Name }").splitlines() if l.strip()]
    regla = bool(_powershell(
        f"Get-NetFirewallRule -DisplayName '{REGLA}' -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.DisplayName }").strip())
    return {"activo": bool(activos), "perfiles": activos, "regla": regla,
            "hace_falta": bool(activos) and not regla}


def abrir_firewall(log=print) -> str:
    """Crea la regla de entrada. Pide permiso de administrador una vez."""
    if os.name != "nt":
        return "Aquí no hace falta tocar el cortafuegos, señor."
    puertos = ",".join(str(p) for p in PUERTOS)
    orden = (f"New-NetFirewallRule -DisplayName '{REGLA}' -Direction Inbound "
             f"-Action Allow -Protocol TCP -LocalPort {puertos} "
             "-Profile Private,Public,Domain")
    # -Verb RunAs saca el aviso de Windows; el señor solo tiene que aceptar.
    lanzar = ("Start-Process powershell -Verb RunAs -WindowStyle Hidden "
              f"-ArgumentList '-NoProfile','-Command',\"{orden}\" -Wait")
    log("[RED] Pidiendo permiso para abrir el puerto del teléfono…")
    _powershell(lanzar, timeout=90)
    if firewall()["regla"]:
        return "Puerto abierto, señor: el teléfono ya puede entrar."
    return ("No pude abrir el puerto, señor. Si el aviso de Windows no salió o "
            "lo canceló, ejecute como administrador: herramientas\\abrir_firewall.ps1")


def preparar(log=print) -> dict:
    """Todo lo que hay que dejar listo al arrancar el servidor."""
    estado = {"ip": mejor_ip(), "ips": ips_lan(), "firewall": firewall()}
    if estado["firewall"].get("hace_falta"):
        estado["firewall_mensaje"] = abrir_firewall(log=log)
        estado["firewall"] = firewall()
    return estado


# ── cuando aun asi no carga ─────────────────────────────────────────────────
def diagnostico(puerto: int = 5000) -> list:
    """Qué mirar cuando el teléfono escanea y no pasa nada, por orden."""
    problemas = []
    lista = ips_lan()
    if not lista:
        problemas.append({
            "que": "Este equipo no tiene ninguna dirección de red local.",
            "hacer": "Conéctelo al WiFi de casa; con el cable desenchufado no hay por dónde entrar."})
        return problemas

    fw = firewall()
    if fw.get("hace_falta"):
        problemas.append({
            "que": "El cortafuegos de Windows no deja entrar al puerto "
                   f"{puerto}.",
            "hacer": "Pulse «abrir el puerto» aquí abajo y acepte el aviso de Windows."})

    publica = [e for e in lista if (e.get("perfil") or "").lower() == "public"]
    if publica and len(lista) == len(publica):
        problemas.append({
            "que": f"La red «{publica[0]['interfaz']}» está marcada como pública.",
            "hacer": "En Windows, Configuración › Red › WiFi › cambie el perfil a "
                     "«Red privada». Muchos repetidores además aíslan los equipos "
                     "entre sí: si el teléfono sigue sin entrar, conéctelo al router "
                     "principal en vez de al extensor."})

    if len(lista) > 1:
        problemas.append({
            "que": "Este equipo tiene varias direcciones: "
                   + ", ".join(f"{e['ip']} ({e['interfaz']})" for e in lista[:4]),
            "hacer": "Si el QR principal no va, pruebe los de las otras direcciones: "
                     "el teléfono tiene que estar en esa misma red."})

    # Si ya esta publicado en remoto, esa es la respuesta buena: funciona
    # dentro y fuera de casa, y ademas por HTTPS.
    try:
        import remoto
        estado_remoto = remoto.estado()
        seguras = [u for u in estado_remoto.get("urls", []) if u.get("segura")]
        if seguras:
            problemas.insert(0, {
                "que": "Puede entrar desde cualquier red, no hace falta el WiFi de casa.",
                "hacer": f"Con Tailscale en el teléfono, abra {seguras[0]['url']}/mobile. "
                         "Va cifrado y con HTTPS, así que también funciona el micrófono."})
            return problemas
        if estado_remoto.get("red", {}).get("activo"):
            problemas.append({
                "que": "Tailscale está en marcha en este equipo pero sin publicar.",
                "hacer": "Dígame «actívate en remoto» y podrá entrar desde cualquier "
                         "sitio, no solo desde este WiFi."})
            return problemas
    except Exception:
        pass

    ts = tailscale_ip()
    if ts:
        problemas.append({
            "que": "Tailscale está en marcha en este equipo.",
            "hacer": f"Instale Tailscale en el teléfono y use http://{ts}:{puerto}/mobile. "
                     "Funciona hasta con datos móviles, sin depender del WiFi."})
    return problemas


def resumen(puerto: int = 5000) -> str:
    lista = ips_lan()
    if not lista:
        return "No tengo dirección de red, señor: este equipo no está conectado."
    principal = lista[0]
    otras = [e["ip"] for e in lista[1:3]]
    texto = (f"El teléfono me encuentra en http://{principal['ip']}:{puerto}/mobile, "
             f"señor (por {principal['interfaz'] or 'la red local'})")
    if otras:
        texto += f". También valen {', '.join(otras)}"
    fw = firewall()
    if fw.get("hace_falta"):
        texto += ". El cortafuegos está cerrando el paso: dígame «abre el puerto del teléfono»"
    return texto + "."


if __name__ == "__main__":
    import json
    print(json.dumps({"ips": ips_lan(), "mejor": mejor_ip(),
                      "firewall": firewall(), "tailscale": tailscale_ip(),
                      "diagnostico": diagnostico()}, ensure_ascii=False, indent=2))
