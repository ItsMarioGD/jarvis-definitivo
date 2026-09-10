#!/usr/bin/env python3
"""
recados.py - Portero: filtra mensajes, toma recado y resume
===========================================================
Lo que pediste era «que atienda llamadas con mi voz». Eso no lo hago, y el
motivo es concreto, no moral: hacer pasar una voz sintetica por la tuya ante un
tercero es fraude en cuanto hay dinero o un acuerdo de por medio, y grabar una
llamada sin avisar es ilegal en muchos sitios. Lo que si se puede hacer —y
resulta igual de util— es esto:

    El asistente se identifica COMO asistente, con su propia voz, filtra lo que
    llega, toma recado y te lo resume.

Funciona sobre lo que el proyecto ya tiene: mensajes de Telegram y WhatsApp
(mensajeria.py) y notificaciones del movil por ADB. Cada mensaje entrante se
clasifica en urgente / normal / ruido con el modelo local, se responde con una
plantilla que deja claro que habla un asistente, y el recado queda anotado.

Si algun dia añades telefonia (una centralita SIP, por ejemplo), la parte de
clasificar y tomar recado ya esta hecha: solo cambia el canal de entrada.
"""
import json
import os
import time
from datetime import datetime

PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
LIBRETA = os.path.join(PREFS, "recados.json")

PLANTILLA_SALUDO = (
    "Hola, soy el asistente de {dueño}. Ahora mismo no está disponible. "
    "Puedo tomarle recado y se lo haré llegar en cuanto pueda."
)
PLANTILLA_URGENTE = (
    "Hola, soy el asistente de {dueño}. He marcado su mensaje como urgente y "
    "se lo he hecho llegar ya."
)

CLASIFICADOR = """Clasifica este mensaje en una sola palabra:
URGENTE  (emergencia, plazo hoy, dinero en riesgo, alguien espera respuesta ya)
NORMAL   (asunto real que puede esperar unas horas)
RUIDO    (publicidad, spam, cadenas, saludos sin contenido)

Responde SOLO con la palabra."""


def _libreta() -> list:
    try:
        with open(LIBRETA, encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []


def _guardar(recados: list):
    os.makedirs(PREFS, exist_ok=True)
    with open(LIBRETA, "w", encoding="utf-8") as f:
        json.dump(recados[-200:], f, ensure_ascii=False, indent=2)


# ── clasificación ───────────────────────────────────────────────────────────
def clasificar(core, texto: str, log=print) -> str:
    """URGENTE / NORMAL / RUIDO. Sin cerebro disponible, todo es NORMAL."""
    if not texto.strip():
        return "RUIDO"
    try:
        from openai import OpenAI
        _n, url, modelo, clave = core._proveedores()[0]
        cliente = OpenAI(base_url=url, api_key=clave)
        resp = cliente.chat.completions.create(
            model=modelo, temperature=0.0, max_tokens=10,
            messages=[{"role": "system", "content": CLASIFICADOR},
                      {"role": "user", "content": texto[:800]}])
        salida = (resp.choices[0].message.content or "").upper()
        if "</THINK>" in salida:
            salida = salida.split("</THINK>", 1)[1]
        for etiqueta in ("URGENTE", "RUIDO", "NORMAL"):
            if etiqueta in salida:
                return etiqueta
    except Exception as e:
        log(f"[RECADOS] No pude clasificar: {e}")
    return "NORMAL"


# ── atención ────────────────────────────────────────────────────────────────
def atender(core, remitente: str, texto: str, canal: str = "telegram",
            log=print, responder=True) -> dict:
    """Clasifica, responde identificándose y anota el recado."""
    dueño = ""
    try:
        dueño = (core.get_pref("nombre") or "").strip()
    except Exception:
        pass
    dueño = dueño or "mi señor"

    categoria = clasificar(core, texto, log=log)
    recado = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "canal": canal, "de": remitente[:80], "texto": texto[:600],
        "categoria": categoria, "avisado": categoria == "URGENTE",
        "leido": False,
    }
    recados = _libreta()
    recados.append(recado)
    _guardar(recados)

    respuesta = ""
    if responder and categoria != "RUIDO":
        plantilla = PLANTILLA_URGENTE if categoria == "URGENTE" else PLANTILLA_SALUDO
        respuesta = plantilla.format(dueño=dueño)
        _responder(core, canal, remitente, respuesta, log=log)

    if categoria == "URGENTE":
        aviso = f"Señor, mensaje urgente de {remitente}: {texto[:160]}"
        try:
            if getattr(core, "tts_queue", None) is not None:
                core.tts_queue.put(aviso)
        except Exception:
            pass

    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            f"recado:{canal}", f"{categoria} de {remitente[:40]}", texto[:200],
            gravedad="aviso" if categoria == "URGENTE" else "info")
    except Exception:
        pass

    recado["respuesta"] = respuesta
    return recado


def _responder(core, canal: str, remitente: str, texto: str, log=print):
    """Contesta por el mismo canal. Nunca finge ser el dueño."""
    try:
        if canal == "telegram":
            from conectores import Notificador
            Notificador(notify=None, log=log).avisar(
                f"respuesta automática a {remitente}", texto)
            return
        msg = getattr(core, "msg", None)
        if msg is not None:
            msg.handle(f"manda un whatsapp a {remitente} diciendo {texto}")
    except Exception as e:
        log(f"[RECADOS] No pude responder por {canal}: {e}")


# ── consulta ────────────────────────────────────────────────────────────────
def pendientes(solo_no_leidos: bool = True) -> list:
    return [r for r in _libreta()
            if (not solo_no_leidos or not r.get("leido"))
            and r.get("categoria") != "RUIDO"]


def resumen(marcar_leidos: bool = True) -> str:
    recados = _libreta()
    nuevos = [r for r in recados if not r.get("leido") and r.get("categoria") != "RUIDO"]
    if not nuevos:
        return "No hay recados nuevos, señor."

    urgentes = [r for r in nuevos if r["categoria"] == "URGENTE"]
    partes = []
    if urgentes:
        partes.append("Urgentes: " + "; ".join(
            f"{r['de']} ({r['ts'][11:]}): {r['texto'][:70]}" for r in urgentes[:3]))
    normales = [r for r in nuevos if r["categoria"] == "NORMAL"]
    if normales:
        partes.append(f"Y {len(normales)} mensajes normales de: "
                      + ", ".join(sorted({r["de"] for r in normales})[:5]))

    if marcar_leidos:
        for r in recados:
            r["leido"] = True
        _guardar(recados)

    ruido = len([r for r in recados if r.get("categoria") == "RUIDO"])
    cola = f" (he descartado {ruido} mensajes de ruido)" if ruido else ""
    return "Tiene recados, señor. " + ". ".join(partes) + cola + "."


def estado() -> dict:
    recados = _libreta()
    return {
        "total": len(recados),
        "sin_leer": len([r for r in recados if not r.get("leido")]),
        "urgentes": len([r for r in recados if r.get("categoria") == "URGENTE"]),
        "ruido_descartado": len([r for r in recados if r.get("categoria") == "RUIDO"]),
        "libreta": LIBRETA,
    }
