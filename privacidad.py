#!/usr/bin/env python3
"""
privacidad.py - Modo privado verificable
========================================
El proyecto ya tenia todas las piezas para funcionar sin nube (Piper para la
voz, faster-whisper para el dictado, Ollama para el cerebro), pero la
privacidad dependia de que cada preferencia estuviera bien puesta en su sitio,
y no habia forma de comprobarlo de un vistazo. «¿Sale mi voz del equipo?» no
tenia respuesta: tenia siete respuestas repartidas por el codigo.

Aqui hay dos cosas:

  auditar(core)  -> lista honesta de POR DONDE puede salir informacion ahora
                    mismo (voz, dictado, cerebro, memoria, mensajeria, web).
  activar(core)  -> cierra todas esas salidas de golpe y lo deja anotado, para
                    poder volver atras exactamente al estado anterior.

El modo privado no borra nada ni rompe nada: fuerza los caminos locales que ya
existian. Si algo no tiene alternativa local (ElevenLabs, por ejemplo), se
desactiva y se dice cual es el coste, en lugar de fingir que sigue igual.
"""
import json
import os

CLAVE_ESTADO = "modo_privado_estado"     # preferencia donde guardamos el «antes»
CLAVE_ACTIVO = "modo_privado"


# ── auditoria ───────────────────────────────────────────────────────────────
def auditar(core) -> list:
    """Salidas por las que información puede abandonar el equipo AHORA."""
    salidas = []

    # 1. Voz sintetizada
    try:
        piper = core._voz_piper_activa()
    except Exception:
        piper = False
    clave_el = (getattr(core, "elevenlabs_key", "") or "").strip()
    if clave_el and "tu_api" not in clave_el and not piper:
        salidas.append(("voz", "ElevenLabs recibe el texto de cada respuesta hablada",
                        "voz local (Piper o Windows)"))

    # 2. Dictado
    try:
        local = (core.get_pref("stt_local") or "1") != "0"
    except Exception:
        local = True
    if not local:
        salidas.append(("dictado", "su voz se envía a Google para transcribirla",
                        "faster-whisper en el propio equipo"))
    else:
        # Aun con dictado local, Google sigue siendo el ultimo recurso.
        salidas.append(("dictado (respaldo)",
                        "si el motor local falla, la frase se manda a Google",
                        "desactivar el respaldo en la nube"))

    # 3. Cerebro. Se mira la lista efectiva de proveedores; si el nucleo no
    # expone _proveedores() (o falla), se lee la configuracion directamente:
    # una salida a la nube no puede pasar desapercibida por un detalle de API.
    proveedores = []
    try:
        proveedores = [(n, u) for n, u, _m, _c in core._proveedores()]
    except Exception:
        try:
            proveedores = [((p.get("nombre") or "?"), (p.get("url") or ""))
                           for p in (getattr(core, "_cerebro", {}) or {}).get("proveedores", [])]
        except Exception:
            proveedores = []
    for nombre, url in proveedores:
        if url and "localhost" not in url and "127.0.0.1" not in url:
            salidas.append((f"cerebro ({nombre})",
                            f"las conversaciones viajan a {url}",
                            "usar solo Ollama local"))

    # 4. Memoria semantica
    if os.getenv("MEM0_API_KEY", "").strip():
        salidas.append(("memoria", "Mem0 en la nube guarda fragmentos de memoria",
                        "memoria-grafo local (jarvis_grafo)"))

    # 5. Mensajeria
    try:
        import jarvis_config
        if os.path.exists(jarvis_config.TELEGRAM_JSON):
            salidas.append(("telegram", "los avisos y las respuestas pasan por Telegram",
                            "silenciar el bot"))
    except Exception:
        pass

    # 6. Interfaz web accesible desde fuera
    if os.getenv("TAILSCALE_ACTIVO", "").strip() == "1":
        salidas.append(("web remota", "la interfaz es alcanzable fuera de la red local",
                        "limitarla a la Wi-Fi de casa"))
    return salidas


def informe(core) -> str:
    """Frase para decir en voz alta con las salidas abiertas."""
    activo = _activo(core)
    salidas = auditar(core)
    if not salidas:
        return ("Nada sale de este equipo, señor: voz, dictado, cerebro y memoria "
                "funcionan en local.")
    detalle = "; ".join(f"{nombre}: {que}" for nombre, que, _alt in salidas)
    cabecera = ("Modo privado activo, pero quedan salidas abiertas"
                if activo else "Salidas abiertas ahora mismo")
    return f"{cabecera}, señor: {detalle}."


def _activo(core) -> bool:
    try:
        return (core.get_pref(CLAVE_ACTIVO) or "0") == "1"
    except Exception:
        return False


# ── activar / desactivar ────────────────────────────────────────────────────
def activar(core) -> str:
    """Cierra todas las salidas a la nube y guarda el estado anterior."""
    if _activo(core):
        return "El modo privado ya estaba activo, señor."

    anterior = {
        "elevenlabs_key": getattr(core, "elevenlabs_key", ""),
        "stt_local": core.get_pref("stt_local") or "",
        "voz_windows": core.get_pref("voz_windows") or "",
        "voz_piper": core.get_pref("voz_piper") or "",
        "cerebro": getattr(core, "_cerebro", {}),
    }
    try:
        core.set_pref(CLAVE_ESTADO, json.dumps(anterior, ensure_ascii=False)[:4000])
    except Exception as e:
        core.log(f"[PRIVADO] No pude guardar el estado anterior: {e}")

    cambios = []

    # Voz: fuera ElevenLabs, dentro Piper (o la voz de Windows).
    if getattr(core, "elevenlabs_key", ""):
        core.elevenlabs_key = ""
        cambios.append("la voz deja de pasar por ElevenLabs")
    try:
        core.set_pref("voz_piper", "1")
    except Exception:
        pass

    # Dictado local obligatorio.
    core.set_pref("stt_local", "1")
    cambios.append("el dictado se queda en el equipo")

    # Cerebro: solo proveedores locales.
    try:
        proveedores = (core._cerebro.get("proveedores") or [])
        locales = [p for p in proveedores
                   if "localhost" in (p.get("url") or "") or "127.0.0.1" in (p.get("url") or "")]
        if not locales:
            locales = [{"nombre": "ollama", "url": core.base_url,
                        "modelo": core.model, "clave": core.api_key}]
        if len(locales) != len(proveedores):
            cambios.append("el cerebro usa solo el modelo local")
        core._cerebro = dict(core._cerebro or {})
        core._cerebro["proveedores"] = locales
    except Exception as e:
        core.log(f"[PRIVADO] Cerebro: {e}")

    core.set_pref(CLAVE_ACTIVO, "1")
    try:
        from storage import get_storage
        get_storage(log=core.log).registrar_evento(
            "privacidad", "Modo privado activado", "; ".join(cambios),
            gravedad="info", agente=getattr(core, "nombre_agente", "JARVIS"))
    except Exception:
        pass

    pendientes = auditar(core)
    aviso = ""
    if pendientes:
        aviso = (" Quedan abiertas: "
                 + ", ".join(n for n, _q, _a in pendientes) + ".")
    return ("Modo privado activado, señor: " + (", ".join(cambios) or "todo ya era local")
            + "." + aviso)


def desactivar(core) -> str:
    """Vuelve exactamente al estado anterior al modo privado."""
    if not _activo(core):
        return "El modo privado no estaba activo, señor."
    try:
        anterior = json.loads(core.get_pref(CLAVE_ESTADO) or "{}")
    except Exception:
        anterior = {}

    if anterior.get("elevenlabs_key"):
        core.elevenlabs_key = anterior["elevenlabs_key"]
    for clave in ("stt_local", "voz_windows", "voz_piper"):
        if anterior.get(clave) != "":
            try:
                core.set_pref(clave, anterior.get(clave, ""))
            except Exception:
                pass
    if anterior.get("cerebro"):
        core._cerebro = anterior["cerebro"]

    core.set_pref(CLAVE_ACTIVO, "0")
    try:
        from storage import get_storage
        get_storage(log=core.log).registrar_evento(
            "privacidad", "Modo privado desactivado", "",
            gravedad="info", agente=getattr(core, "nombre_agente", "JARVIS"))
    except Exception:
        pass
    return "Modo privado desactivado, señor. Vuelvo a usar los servicios externos."
