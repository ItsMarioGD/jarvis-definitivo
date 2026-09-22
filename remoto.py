#!/usr/bin/env python3
"""
remoto.py - El PC como servidor y el señor conectandose desde donde sea
=======================================================================
Hasta ahora JARVIS solo existia dentro de casa: el telefono tenia que estar en
el mismo WiFi que el PC. Fuera de casa, nada. Esto lo convierte en lo que
deberia haber sido desde el principio: un servidor que el señor lleva encima.

Como, sin abrir el router
-------------------------
Con Tailscale, que ya esta instalado en este equipo. Monta una red privada
cifrada entre los aparatos del señor (este PC, el telefono, el otro portatil) y
los deja hablar como si estuvieran en la misma habitacion, aunque uno este con
datos moviles y el otro en la oficina. No se abre ningun puerto al mundo.

    tailscale serve   publica el servidor DENTRO de la red privada, por HTTPS
    tailscale funnel  lo publica en INTERNET (cualquiera con la URL) <- peligro

Por que HTTPS y no la IP pelada
-------------------------------
Con http://100.x.x.x:5000 el navegador del telefono considera la pagina
«insegura» y APAGA el microfono: el dictado por voz deja de funcionar y nadie
entiende por que. Con `tailscale serve` la direccion pasa a ser
https://<equipo>.<tailnet>.ts.net, con certificado de verdad, y funciona todo:
voz, camara, notificaciones y la pantalla en vivo.

Lo que NO se hace aqui
----------------------
Abrir puertos en el router. Un PIN de seis cifras colgado de Internet se
revienta en una tarde. Si el señor quiere eso de todas formas, esta `funnel`,
pero avisa antes y obliga a poner una clave larga.
"""
import json
import os
import subprocess

PUERTO_JARVIS = int(os.getenv("JARVIS_PORT", "5000"))
PUERTO_ULTRON = int(os.getenv("ULTRON_PORT", "8766"))


# ── hablar con Tailscale ────────────────────────────────────────────────────
def _exe() -> str:
    try:
        import jarvis_config
        ruta = jarvis_config.TAILSCALE_EXE
        if ruta and os.path.exists(ruta):
            return ruta
    except Exception:
        pass
    for c in (r"C:\Program Files\Tailscale\tailscale.exe",
              r"C:\Program Files (x86)\Tailscale\tailscale.exe",
              "/usr/bin/tailscale", "/usr/local/bin/tailscale"):
        if os.path.exists(c):
            return c
    import shutil
    return shutil.which("tailscale") or ""


def _ts(*args, timeout: int = 25) -> tuple:
    exe = _exe()
    if not exe:
        return False, "no está instalado Tailscale"
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return False, "Tailscale no respondió a tiempo"
    except Exception as e:
        return False, str(e)[:150]


def instalado() -> bool:
    return bool(_exe())


_cache = {}
SEGUNDOS_CACHE = 15


def _guardado(clave):
    """Lo que se pregunto hace nada. Preguntar a Tailscale cuesta medio segundo
    y la pagina de emparejamiento repite cada cuatro."""
    import time
    dato, ts = _cache.get(clave, (None, 0.0))
    return dato if dato is not None and time.time() - ts < SEGUNDOS_CACHE else None


def _guardar(clave, valor):
    import time
    _cache[clave] = (valor, time.time())
    return valor


def red() -> dict:
    """Quién hay en la red privada del señor y cómo se llama este equipo."""
    guardado = _guardado("red")
    if guardado is not None:
        return guardado
    ok, salida = _ts("status", "--json")
    if not ok:
        return {"activo": False, "motivo": salida}
    try:
        d = json.loads(salida)
    except Exception:
        return {"activo": False, "motivo": "no entiendo la respuesta de Tailscale"}

    yo = d.get("Self") or {}
    nombre = (yo.get("DNSName") or "").rstrip(".")
    aparatos = []
    for p in (d.get("Peer") or {}).values():
        aparatos.append({
            "nombre": (p.get("DNSName") or "").split(".")[0],
            "dns": (p.get("DNSName") or "").rstrip("."),
            "ips": p.get("TailscaleIPs") or [],
            "conectado": bool(p.get("Online")),
            "sistema": p.get("OS", ""),
        })
    return _guardar("red", {
        "activo": d.get("BackendState") == "Running",
        "estado": d.get("BackendState", ""),
        "nombre": nombre,
        "ips": yo.get("TailscaleIPs") or [],
        "aparatos": sorted(aparatos, key=lambda a: (not a["conectado"], a["nombre"])),
    })


# ── publicar el servidor ────────────────────────────────────────────────────
def publicado() -> dict:
    """Qué hay publicado ahora mismo: dentro de la red privada o en Internet."""
    guardado = _guardado("publicado")
    if guardado is not None:
        return guardado
    ok, salida = _ts("serve", "status", "--json")
    datos = {"serve": False, "funnel": False, "detalle": ""}
    if not ok:
        datos["detalle"] = salida[:120]
        return datos
    try:
        d = json.loads(salida) if salida.strip().startswith("{") else {}
    except Exception:
        d = {}
    datos["serve"] = bool(d.get("TCP") or d.get("Web"))
    datos["funnel"] = bool(d.get("AllowFunnel"))
    return _guardar("publicado", datos)


def activar(log=print) -> str:
    """Publica JARVIS en la red privada, por HTTPS y sin puerto en la URL."""
    if not instalado():
        return ("Para entrar desde fuera hace falta Tailscale, señor: "
                "instálelo en el PC y en el teléfono con la misma cuenta "
                "(tailscale.com/download). Es gratis para uso personal.")
    info = red()
    if not info.get("activo"):
        return (f"Tailscale está instalado pero no arrancado, señor "
                f"({info.get('motivo') or info.get('estado')}). Ábralo e inicie sesión.")

    log("[REMOTO] Publicando el servidor en la red privada…")
    ok, salida = _ts("serve", "--bg", str(PUERTO_JARVIS), timeout=60)
    _cache.clear()
    if not ok:
        return f"No pude publicarlo, señor: {salida[:160]}"
    return (f"Listo, señor. Desde cualquier sitio, con Tailscale en el teléfono: "
            f"https://{info['nombre']}. Va cifrado, sin abrir nada en el router, y "
            "al ser HTTPS el micrófono del teléfono también funciona.")


def desactivar(log=print) -> str:
    ok, salida = _ts("serve", "reset", timeout=40)
    _cache.clear()
    if not ok:
        return f"No pude quitarlo, señor: {salida[:140]}"
    return "Acceso remoto retirado, señor. Vuelvo a existir solo dentro de casa."


def publicar_en_internet(confirmado: bool = False, log=print) -> str:
    """Funnel: la URL queda abierta al mundo. Solo bajo petición expresa."""
    if not confirmado:
        return ("Eso publica JARVIS en Internet, señor: cualquiera que dé con la "
                "dirección llega a la pantalla del PIN, y seis cifras no aguantan "
                "a quien se lo tome en serio. Con Tailscale ya puede entrar desde "
                "cualquier red sin exponer nada. Si aun así lo quiere, dígame "
                "«publícalo en internet, confirmo» y lo hago.")
    info = red()
    if not info.get("activo"):
        return "Antes hay que tener Tailscale en marcha, señor."
    ok, salida = _ts("funnel", "--bg", str(PUERTO_JARVIS), timeout=60)
    _cache.clear()
    if not ok:
        return f"No pude publicarlo, señor: {salida[:200]}"
    return (f"Publicado en Internet, señor: https://{info['nombre']}. "
            "Le recomiendo cambiar el PIN por uno largo ahora mismo y quitarlo "
            "en cuanto no lo necesite con «quita el acceso remoto».")


# ── informe ─────────────────────────────────────────────────────────────────
def urls() -> list:
    """Direcciones por las que se puede entrar desde fuera de casa."""
    info = red()
    if not info.get("activo"):
        return []
    salida = []
    pub = publicado()
    if pub.get("serve") and info.get("nombre"):
        salida.append({"url": f"https://{info['nombre']}",
                       "via": "Tailscale con HTTPS (recomendada)", "segura": True})
    if info.get("nombre"):
        salida.append({"url": f"http://{info['nombre']}:{PUERTO_JARVIS}/mobile",
                       "via": "Tailscale por nombre", "segura": False})
    for ip in info.get("ips", []):
        if ":" in ip:
            continue
        salida.append({"url": f"http://{ip}:{PUERTO_JARVIS}/mobile",
                       "via": "Tailscale por IP", "segura": False})
    return salida


def estado() -> dict:
    info = red()
    return {"instalado": instalado(), "red": info, "publicado": publicado(),
            "urls": urls(),
            "aparatos_conectados": [a["nombre"] for a in info.get("aparatos", [])
                                    if a["conectado"]]}


def resumen() -> str:
    e = estado()
    if not e["instalado"]:
        return ("Ahora mismo solo existo dentro de casa, señor. Con Tailscale en "
                "el PC y en el teléfono podría hablarme desde cualquier sitio sin "
                "abrir nada en el router. Dígame «actívate en remoto» y le explico.")
    info = e["red"]
    if not info.get("activo"):
        return (f"Tailscale está instalado pero parado, señor ({info.get('estado') or ''}). "
                "Ábralo, inicie sesión y vuelva a decírmelo.")
    partes = [f"Soy alcanzable como «{info['nombre']}», señor"]
    if e["publicado"].get("serve"):
        partes[0] += f", desde cualquier red, en https://{info['nombre']}"
    else:
        partes[0] += (", aunque todavía sin HTTPS: dígame «actívate en remoto» "
                      "y lo publico")
    conectados = e["aparatos_conectados"]
    otros = [a["nombre"] for a in info.get("aparatos", [])]
    if conectados:
        partes.append(f"ahora hay conectados: {', '.join(conectados)}")
    elif otros:
        partes.append(f"sus otros aparatos ({', '.join(otros[:3])}) están apagados o sin Tailscale")
    if e["publicado"].get("funnel"):
        partes.append("OJO: además está abierto a Internet")
    # Cada frase empieza en mayuscula: se leen en voz alta, no son una lista.
    frase = partes[0]
    for p in partes[1:]:
        frase += ". " + p[0].upper() + p[1:]
    return frase + "."


if __name__ == "__main__":
    print(json.dumps(estado(), ensure_ascii=False, indent=2))
    print()
    print(resumen())
