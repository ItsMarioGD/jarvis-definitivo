#!/usr/bin/env python3
"""
voz_propia.py - Una voz de verdad, local y sin factura
======================================================
ElevenLabs lleva devolviendo 402 (sin credito) desde hace tiempo, asi que el
asistente habla con la voz de Windows, que suena a Windows. Y la voz es la
mitad de la personalidad: JARVIS y ULTRON no pueden sonar igual.

Aqui se gestiona la voz neuronal LOCAL, que no cuesta nada y no sale del equipo:

  * PIPER      voz neuronal ligera (onnx, ~60 MB por voz). Es la recomendada:
               suena bastante mejor que SAPI y va en CPU sin despeinarse.
               El proyecto ya trae jarvis_piper.py para reproducirla; lo que
               faltaba era ELEGIR voz distinta por personalidad y saber cual
               esta instalada.
  * XTTS       clonacion de voz (coqui-TTS). Si el señor la instala, con treinta
               segundos de grabacion se puede tener su propia voz. Es opcional y
               pesada (torch): aqui solo se detecta y se explica.
  * SAPI       la de Windows, que sigue como ultimo recurso (voz_rapida.py).

Voces recomendadas en español (se descargan solas la primera vez):
    es_ES-sharvard-medium   femenina, neutra
    es_ES-davefx-medium     masculina, calida     <- JARVIS
    es_MX-ald-medium        masculina, seca       <- ULTRON
"""
import os

# Voz por personalidad. Se pueden cambiar con las preferencias
# «voz_jarvis» y «voz_ultron».
VOCES = {
    "jarvis": os.getenv("JARVIS_VOZ_PIPER", "es_ES-davefx-medium"),
    "ultron": os.getenv("ULTRON_VOZ_PIPER", "es_MX-ald-medium"),
    "consejo": os.getenv("JARVIS_VOZ_PIPER", "es_ES-davefx-medium"),
}

CATALOGO = {
    "es_ES-davefx-medium": "masculina española, cálida (recomendada para JARVIS)",
    "es_MX-ald-medium": "masculina mexicana, seca (recomendada para ULTRON)",
    "es_ES-sharvard-medium": "femenina española, neutra",
    "es_ES-carlfm-x_low": "masculina española, muy ligera (equipos lentos)",
    "es_MX-claude-high": "masculina mexicana, alta calidad (110 MB)",
}


# ── qué hay disponible ──────────────────────────────────────────────────────
def motores() -> dict:
    """Qué motores de voz hay en este equipo, del mejor al peor."""
    estado = {"piper": False, "xtts": False, "sapi": False, "detalle": {}}
    try:
        import jarvis_piper
        import importlib.util
        tiene_lib = importlib.util.find_spec("piper") is not None
        instaladas = voces_instaladas()
        estado["piper"] = bool(tiene_lib or instaladas)
        estado["detalle"]["piper"] = {
            "libreria": tiene_lib, "voces": instaladas,
            "carpeta": getattr(jarvis_piper, "DIR", "")}
    except Exception as e:
        estado["detalle"]["piper"] = {"error": str(e)[:90]}
    try:
        import importlib.util
        estado["xtts"] = importlib.util.find_spec("TTS") is not None
    except Exception:
        pass
    try:
        import voz_rapida
        estado["sapi"] = voz_rapida.preparar(log=lambda *a: None) in ("sapi", "pyttsx3")
    except Exception:
        pass
    return estado


def voces_instaladas() -> list:
    """Voces de Piper ya descargadas."""
    try:
        import jarvis_piper
        carpeta = getattr(jarvis_piper, "DIR", "")
        if not carpeta or not os.path.isdir(carpeta):
            return []
        return sorted(f[:-5] for f in os.listdir(carpeta) if f.endswith(".onnx"))
    except Exception:
        return []


def voz_de(agente: str = "jarvis", core=None) -> str:
    """Qué voz le toca a esta personalidad."""
    agente = (agente or "jarvis").lower()
    if core is not None:
        try:
            guardada = (core.get_pref(f"voz_{agente}") or "").strip()
            if guardada:
                return guardada
        except Exception:
            pass
    return VOCES.get(agente, VOCES["jarvis"])


# ── instalar y elegir ───────────────────────────────────────────────────────
def instalar(voz: str = "", log=print) -> str:
    """Descarga una voz de Piper (unos 60 MB). La primera vez tarda."""
    voz = voz or VOCES["jarvis"]
    if voz not in CATALOGO and not voz.startswith(("es_", "en_")):
        return (f"No conozco la voz «{voz}», señor. Tengo: "
                + "; ".join(f"{k} ({v})" for k, v in CATALOGO.items()))
    try:
        import jarvis_piper
    except Exception as e:
        return f"No puedo usar Piper, señor: {e}"
    if voz in voces_instaladas():
        return f"La voz «{voz}» ya estaba instalada, señor."
    log(f"[VOZ] Descargando la voz {voz}…")
    try:
        ok = jarvis_piper._descargar(voz)
    except Exception as e:
        return f"La descarga falló, señor: {str(e)[:120]}"
    if not ok:
        return (f"No pude descargar «{voz}», señor. Compruebe la conexión o "
                "pruebe con otra del catálogo.")
    return (f"Voz «{voz}» instalada, señor: {CATALOGO.get(voz, 'voz neuronal local')}. "
            "Ya no necesito ElevenLabs para sonar decente.")


def elegir(core, agente: str, voz: str, log=print) -> str:
    """Fija la voz de una personalidad y la deja lista."""
    agente = (agente or "jarvis").lower()
    if voz not in voces_instaladas():
        mensaje = instalar(voz, log=log)
        if "instalada" not in mensaje:
            return mensaje
    try:
        core.set_pref(f"voz_{agente}", voz)
        core.set_pref("voz_piper", "1")      # que la cadena de TTS use Piper
    except Exception as e:
        return f"No pude guardar la elección, señor: {e}"
    return f"{agente.upper()} hablará con «{voz}», señor: {CATALOGO.get(voz, '')}."


def hablar(texto: str, agente: str = "jarvis", core=None, log=print) -> bool:
    """Dice el texto con la voz de esa personalidad. False si no se pudo."""
    voz = voz_de(agente, core)
    try:
        import jarvis_piper
        if voz in voces_instaladas():
            return bool(jarvis_piper.hablar(texto, voice_id=voz))
    except Exception as e:
        log(f"[VOZ] Piper falló ({e}); paso a la voz del sistema.")
    try:
        import voz_rapida
        return voz_rapida.hablar(texto, log=log)
    except Exception:
        return False


# ── clonación (opcional) ────────────────────────────────────────────────────
def puede_clonar() -> bool:
    try:
        import importlib.util
        return (importlib.util.find_spec("TTS") is not None
                and importlib.util.find_spec("torch") is not None)
    except Exception:
        return False


def clonar(muestra_wav: str, nombre: str = "propia", log=print) -> str:
    """Voz clonada a partir de una grabación. Requiere coqui-TTS instalado."""
    if not os.path.exists(muestra_wav):
        return f"No encuentro la grabación {muestra_wav}, señor."
    if not puede_clonar():
        return ("Para clonar una voz hace falta coqui-TTS, señor: "
                "«pip install TTS» (trae PyTorch, unos 2 GB). Con eso, treinta "
                "segundos de grabación bastan. Mientras tanto, Piper suena "
                "bastante bien y no pesa nada.")
    try:
        from TTS.api import TTS
        modelo = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        carpeta = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Voces")
        os.makedirs(carpeta, exist_ok=True)
        destino = os.path.join(carpeta, f"{nombre}.wav")
        modelo.tts_to_file(text="Voz registrada, señor.", speaker_wav=muestra_wav,
                           language="es", file_path=destino)
        return (f"Voz «{nombre}» clonada, señor. Muestra en {destino}. "
                "Dígame «usa la voz propia» para que la utilice.")
    except Exception as e:
        return f"La clonación falló, señor: {str(e)[:150]}"


# ── informe ─────────────────────────────────────────────────────────────────
def estado(core=None) -> dict:
    m = motores()
    return {
        "motores": {k: v for k, v in m.items() if k != "detalle"},
        "voces_instaladas": voces_instaladas(),
        "voz_jarvis": voz_de("jarvis", core),
        "voz_ultron": voz_de("ultron", core),
        "puede_clonar": puede_clonar(),
        "catalogo": CATALOGO,
    }


def resumen(core=None) -> str:
    e = estado(core)
    instaladas = e["voces_instaladas"]
    if instaladas:
        return (f"Voces neuronales instaladas, señor: {', '.join(instaladas)}. "
                f"JARVIS usa «{e['voz_jarvis']}» y ULTRON «{e['voz_ultron']}». "
                "Todo local y sin coste.")
    return ("Ahora mismo hablo con la voz de Windows, señor. Con «instala tu voz» "
            "descargo una voz neuronal local (unos 60 MB) que suena bastante "
            "mejor y no depende de ninguna cuenta.")
