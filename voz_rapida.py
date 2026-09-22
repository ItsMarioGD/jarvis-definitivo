#!/usr/bin/env python3
"""
voz_rapida.py - Hablar sin arrancar PowerShell en cada frase
============================================================
La voz local de Windows se sintetizaba lanzando un PowerShell nuevo por cada
frase: medido, **2,3 segundos** de los cuales casi todo es arrancar el proceso
y cargar System.Speech. Eso es lo que hacía que JARVIS pareciera lento aunque
el modelo hubiera contestado en un segundo.

Aquí se habla desde el propio proceso, con el motor SAPI cargado una sola vez:

  1. pywin32 (win32com) -> SAPI.SpVoice en proceso. Instantáneo.
  2. pyttsx3            -> mismo motor, otra librería, por si falta pywin32.
  3. PowerShell         -> el camino de siempre, como último recurso.

Además el motor se elige UNA vez y se recuerda, y la voz se selecciona una vez
(masculina en español si existe), no en cada frase.
"""
import os
import threading

_lock = threading.RLock()
_motor = None          # objeto del motor ya inicializado
_tipo = ""             # "sapi" | "pyttsx3" | "powershell" | "no"
_error = ""


def _init_sapi(log=print):
    """SAPI por COM. Es el camino rápido: el motor vive en este proceso."""
    import win32com.client
    voz = win32com.client.Dispatch("SAPI.SpVoice")
    # Voz masculina en español si la hay; si no, la que venga.
    try:
        for v in voz.GetVoices():
            descripcion = v.GetDescription().lower()
            if "spanish" in descripcion or "español" in descripcion or "helena" in descripcion:
                voz.Voice = v
                if "male" in descripcion or "pablo" in descripcion or "raul" in descripcion:
                    break
    except Exception as e:
        log(f"[VOZ] No pude elegir voz: {e}")
    return voz


def _init_pyttsx3(log=print):
    import pyttsx3
    motor = pyttsx3.init()
    try:
        for v in motor.getProperty("voices"):
            if "spanish" in (v.name or "").lower() or "es-" in (v.id or "").lower():
                motor.setProperty("voice", v.id)
                break
    except Exception:
        pass
    return motor


def preparar(log=print) -> str:
    """Elige y carga el motor una sola vez. Devuelve el tipo elegido."""
    global _motor, _tipo, _error
    with _lock:
        if _tipo:
            return _tipo
        if os.name != "nt":
            _tipo = "no"
            _error = "solo hay voz local en Windows"
            return _tipo
        for nombre, constructor in (("sapi", _init_sapi), ("pyttsx3", _init_pyttsx3)):
            try:
                _motor = constructor(log=log)
                _tipo = nombre
                log(f"[VOZ] Motor local «{nombre}» listo (sin arrancar procesos).")
                return _tipo
            except Exception as e:
                _error = str(e)[:120]
                log(f"[VOZ] {nombre} no disponible: {_error}")
        _tipo = "powershell"
        log("[VOZ] Sin motor en proceso: usaré PowerShell (más lento).")
        return _tipo


def hablar(texto: str, velocidad: int = 0, log=print) -> bool:
    """Dice el texto. `velocidad` va de -10 a 10 como en SAPI."""
    if not texto or not texto.strip():
        return False
    tipo = preparar(log=log)

    if tipo == "sapi":
        try:
            with _lock:
                _motor.Rate = max(-10, min(10, int(velocidad)))
                _motor.Speak(texto)          # síncrono: el worker de TTS ya va aparte
            return True
        except Exception as e:
            log(f"[VOZ] SAPI falló ({e}); paso a PowerShell.")
            return _powershell(texto, velocidad, log=log)

    if tipo == "pyttsx3":
        try:
            with _lock:
                _motor.setProperty("rate", 175 + velocidad*12)
                _motor.say(texto)
                _motor.runAndWait()
            return True
        except Exception as e:
            log(f"[VOZ] pyttsx3 falló ({e}); paso a PowerShell.")
            return _powershell(texto, velocidad, log=log)

    if tipo == "powershell":
        return _powershell(texto, velocidad, log=log)
    return False


def _powershell(texto: str, velocidad: int = 0, log=print) -> bool:
    """El camino antiguo. Se conserva para equipos sin pywin32 ni pyttsx3."""
    import base64
    import json
    import subprocess
    script = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Culture.Name -like 'es-*' }} | Select-Object -First 1
if ($v) {{ $s.SelectVoice($v.VoiceInfo.Name) }}
$s.Rate = {max(-10, min(10, int(velocidad)))}
$s.Speak({json.dumps(texto, ensure_ascii=False)})
"""
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                        base64.b64encode(script.encode("utf-16le")).decode("ascii")],
                       capture_output=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception as e:
        log(f"[VOZ] PowerShell también falló: {e}")
        return False


def callar():
    """Corta la frase en curso (barge-in)."""
    with _lock:
        if _tipo == "sapi" and _motor is not None:
            try:
                # 2 = SVSFPurgeBeforeSpeak: descarta lo pendiente y calla.
                _motor.Speak("", 2)
                return True
            except Exception:
                return False
        if _tipo == "pyttsx3" and _motor is not None:
            try:
                _motor.stop()
                return True
            except Exception:
                return False
    return False


def estado() -> dict:
    return {"motor": _tipo or "sin preparar", "error": _error,
            "en_proceso": _tipo in ("sapi", "pyttsx3")}
