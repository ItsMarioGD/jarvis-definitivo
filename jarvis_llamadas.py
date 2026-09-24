#!/usr/bin/env python3
"""
jarvis_llamadas.py - JARVIS llama al señor cuando necesita respuesta
====================================================================
Cuando JARVIS tiene una duda, necesita confirmar algo urgente o quiere
notificar al señor, puede hacer una llamada real al celular.

Requiere Twilio:
  pip install twilio
  Vars: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, JARVIS_CELULAR

Fallback: si no hay Twilio, envía un SMS vía servicio gratuito o
muestra la notificación en el HUD.
"""
import os
import time
import threading
from typing import Optional

TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM  = os.getenv("TWILIO_FROM", "")
CELULAR      = os.getenv("JARVIS_CELULAR", "")

_COOLDOWN    = 60.0  # segundos mínimo entre llamadas
_ultimo_llamada = 0.0
_ultimo_sms = 0.0


def _disponible() -> tuple[bool, str]:
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, CELULAR]):
        faltantes = [k for k, v in {
            "TWILIO_ACCOUNT_SID": TWILIO_SID,
            "TWILIO_AUTH_TOKEN": TWILIO_TOKEN,
            "TWILIO_FROM": TWILIO_FROM,
            "JARVIS_CELULAR": CELULAR,
        }.items() if not v]
        return False, f"Faltan variables: {', '.join(faltantes)}"
    try:
        from twilio.rest import Client  # noqa: F401
        return True, ""
    except ImportError:
        return False, "falta twilio (pip install twilio)"


def llamar(mensaje: str, log=print) -> dict:
    """
    Llama al celular del señor y reproduce el mensaje como TTS.
    Devuelve {'ok', 'sid', 'error'}.
    """
    global _ultimo_llamada

    if not mensaje or len(mensaje.strip()) < 3:
        return {"ok": False, "error": "Sin mensaje para la llamada."}

    ahora = time.time()
    if ahora - _ultimo_llamada < _COOLDOWN:
        espera = int(_COOLDOWN - (ahora - _ultimo_llamada))
        return {"ok": False,
                "error": f"Cooldown activo: espere {espera}s antes de otra llamada."}

    ok, motivo = _disponible()
    if not ok:
        log(f"[LLAMADA] No disponible: {motivo}")
        return {"ok": False, "error": motivo}

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="es-ES" voice="Polly.Conchita">
    {mensaje[:500]}
  </Say>
  <Pause length="2"/>
  <Say language="es-ES" voice="Polly.Conchita">
    Repito: {mensaje[:200]}
  </Say>
</Response>"""

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        call = client.calls.create(
            twiml=twiml,
            to=CELULAR,
            from_=TWILIO_FROM,
        )
        _ultimo_llamada = time.time()
        log(f"[LLAMADA] Llamada iniciada: {call.sid}")

        try:
            from storage import get_storage
            get_storage(log=log).registrar_evento(
                "llamada", "Llamada al señor",
                mensaje[:200], gravedad="warn", datos=call.sid)
        except Exception:
            pass

        return {"ok": True, "sid": call.sid, "to": CELULAR}
    except Exception as e:
        log(f"[LLAMADA] Error Twilio: {e}")
        return {"ok": False, "error": str(e)[:120]}


def enviar_sms(mensaje: str, log=print) -> dict:
    """Envía SMS al celular del señor."""
    global _ultimo_sms

    ahora = time.time()
    if ahora - _ultimo_sms < _COOLDOWN:
        espera = int(_COOLDOWN - (ahora - _ultimo_sms))
        return {"ok": False,
                "error": f"Cooldown SMS: espere {espera}s."}

    ok, motivo = _disponible()
    if not ok:
        return {"ok": False, "error": motivo}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(
            body=f"JARVIS: {mensaje[:1500]}",
            to=CELULAR,
            from_=TWILIO_FROM,
        )
        _ultimo_sms = time.time()
        log(f"[SMS] Enviado: {msg.sid}")
        return {"ok": True, "sid": msg.sid}
    except Exception as e:
        log(f"[SMS] Error: {e}")
        return {"ok": False, "error": str(e)[:120]}


def enviar_whatsapp(mensaje: str, log=print) -> dict:
    """Envía WhatsApp vía Twilio Sandbox."""
    ok, motivo = _disponible()
    if not ok:
        return {"ok": False, "error": motivo}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        to_wa = f"whatsapp:{CELULAR}"
        from_wa = f"whatsapp:{TWILIO_FROM}"
        msg = client.messages.create(
            body=f"🤖 JARVIS: {mensaje[:1500]}",
            to=to_wa,
            from_=from_wa,
        )
        log(f"[WA] Enviado: {msg.sid}")
        return {"ok": True, "sid": msg.sid}
    except Exception as e:
        log(f"[WA] Error: {e}")
        return {"ok": False, "error": str(e)[:120]}


def notificar(mensaje: str, canal: str = "auto", log=print) -> dict:
    """
    Notifica al señor por el mejor canal disponible.
    canal: 'llamada' | 'sms' | 'whatsapp' | 'auto'
    En modo 'auto': intenta llamada → sms → whatsapp.
    """
    if canal == "llamada":
        return llamar(mensaje, log=log)
    if canal == "sms":
        return enviar_sms(mensaje, log=log)
    if canal == "whatsapp":
        return enviar_whatsapp(mensaje, log=log)

    # auto: probar en orden
    r = llamar(mensaje, log=log)
    if r["ok"]:
        return r
    r = enviar_sms(mensaje, log=log)
    if r["ok"]:
        return r
    return enviar_whatsapp(mensaje, log=log)


def preguntar_al_señor(pregunta: str, log=print, timeout_seg: int = 0) -> dict:
    """
    JARVIS llama al señor con una pregunta cuando necesita autorización.
    El mensaje explica que puede responder por el chat.
    """
    msg = (f"{pregunta}. "
           "Puede responderme en el chat de JARVIS cuando le sea posible. "
           "Gracias, señor.")
    return notificar(msg, log=log)


def estado() -> dict:
    """Estado del módulo de llamadas."""
    ok, motivo = _disponible()
    ahora = time.time()
    return {
        "disponible": ok,
        "motivo": motivo if not ok else "",
        "numero": CELULAR,
        "cooldown_llamada": max(0, int(_COOLDOWN - (ahora - _ultimo_llamada))),
        "cooldown_sms": max(0, int(_COOLDOWN - (ahora - _ultimo_sms))),
    }
