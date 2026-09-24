#!/usr/bin/env python3
"""
correo_gmail.py - El sub-agente de correo de la idea 1 del IDEAS.MD
==================================================================
`autorizar_google.py` ya monta OAuth de Google para el calendario. Aqui se
reutiliza ese mismo token (ampliado con los permisos de Gmail) para lo que
pedia la topologia multi-agente: **escanear y resumir el correo entrante**.

Solo lectura por defecto. `enviar()` existe pero exige el permiso
`gmail.send` en el token y una confirmacion explicita del señor: nunca lo
dispara el enjambre.

Para activarlo: añade los scopes de Gmail y vuelve a autorizar:

    python autorizar_google.py

(SCOPES en autorizar_google.py ya incluye gmail.readonly y gmail.send.)
"""
import base64
import os
import re
from email.mime.text import MIMEText

_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

_REMITENTES_VIP = re.compile(
    r"(banco|factura|nomina|nómina|urgente|vencimiento|seguridad|security|"
    r"alerta|verifica|suspend|jefe|contrato|firma|deadline)", re.IGNORECASE)


def _servicio(log=print):
    """Cliente de Gmail sobre el token de Google ya guardado. None si no hay."""
    try:
        import jarvis_config
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except Exception as e:
        log(f"[CORREO] faltan librerias de Google: {e}")
        return None

    token_path = jarvis_config.ruta_token_google()
    if not os.path.exists(token_path):
        log("[CORREO] sin token de Google; ejecuta autorizar_google.py")
        return None
    try:
        creds = Credentials.from_authorized_user_file(token_path, _SCOPES)
    except Exception as e:
        log(f"[CORREO] token ilegible: {e}")
        return None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception as e:
                log(f"[CORREO] no pude refrescar el token: {e}")
                return None
        else:
            log("[CORREO] el token no cubre Gmail; vuelve a autorizar_google.py")
            return None
    try:
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        log(f"[CORREO] no pude crear el cliente Gmail: {e}")
        return None


def _cabecera(payload, nombre):
    for h in (payload or {}).get("headers", []):
        if h.get("name", "").lower() == nombre.lower():
            return h.get("value", "")
    return ""


def no_leidos(maximo: int = 10, solo_importantes: bool = False, log=print) -> list:
    """[{de, asunto, fecha, resumen, id, vip}] de la bandeja, sin leer."""
    svc = _servicio(log=log)
    if svc is None:
        return []
    q = "is:unread in:inbox"
    if solo_importantes:
        q += " is:important"
    try:
        lista = svc.users().messages().list(
            userId="me", q=q, maxResults=max(1, min(maximo, 25))).execute()
        ids = [m["id"] for m in lista.get("messages", [])]
    except Exception as e:
        log(f"[CORREO] no pude listar: {e}")
        return []
    salida = []
    for mid in ids:
        try:
            msg = svc.users().messages().get(
                userId="me", id=mid, format="metadata",
                metadataHeaders=["From", "Subject", "Date"]).execute()
        except Exception:
            continue
        de = _cabecera(msg.get("payload"), "From")
        asunto = _cabecera(msg.get("payload"), "Subject") or "(sin asunto)"
        salida.append({
            "id": mid,
            "de": re.sub(r"\s*<[^>]+>", "", de).strip() or de,
            "asunto": asunto,
            "fecha": _cabecera(msg.get("payload"), "Date"),
            "resumen": (msg.get("snippet", "") or "")[:200],
            "vip": bool(_REMITENTES_VIP.search(de + " " + asunto)),
        })
    return salida


def resumen(maximo: int = 8, log=print) -> str:
    """Texto hablado: cuantos hay sin leer y los mas relevantes."""
    svc = _servicio(log=log)
    if svc is None:
        return ("Señor, no tengo acceso al correo todavía. Ejecute "
                "autorizar_google.py para concederme los permisos de Gmail.")
    correos = no_leidos(maximo, log=log)
    if not correos:
        return "Señor, no tiene correos sin leer en la bandeja de entrada."
    vip = [c for c in correos if c["vip"]]
    partes = [f"Tiene {len(correos)} correo{'s' if len(correos) != 1 else ''} sin leer, señor."]
    destacar = (vip or correos)[:4]
    for c in destacar:
        marca = "Importante: " if c["vip"] else ""
        partes.append(f"{marca}{c['de']} — {c['asunto']}.")
    if len(correos) > len(destacar):
        partes.append(f"Y {len(correos) - len(destacar)} más.")
    return " ".join(partes)


def enviar(para: str, asunto: str, cuerpo: str, log=print):
    """Envia un correo. Requiere scope gmail.send y confirmacion del señor.
    Devuelve dict {'ok', 'mensaje'} o str (retrocompatibilidad)."""
    svc = _servicio(log=log)
    if svc is None:
        return {"ok": False, "mensaje": "Sin acceso a Gmail para enviar.", "error": "sin token"}
    try:
        mensaje = MIMEText(cuerpo or "", _charset="utf-8")
        mensaje["to"] = para
        mensaje["subject"] = asunto or "(sin asunto)"
        crudo = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()
        svc.users().messages().send(userId="me", body={"raw": crudo}).execute()
        return {"ok": True, "mensaje": f"Correo enviado a {para}, señor."}
    except Exception as e:
        log(f"[CORREO] no pude enviar: {e}")
        return {"ok": False, "mensaje": f"El envío falló: {str(e)[:120]}", "error": str(e)[:120]}


def hallazgos_para_enjambre(log=print) -> list:
    """Lo que el agente de correo del enjambre reporta. Lista de tuplas
    (titulo, detalle, importancia) para no acoplar con la clase Hallazgo."""
    correos = no_leidos(15, log=log)
    if not correos:
        return []
    vip = [c for c in correos if c["vip"]]
    salida = []
    if vip:
        nombres = "; ".join(f"{c['de']} ({c['asunto'][:40]})" for c in vip[:3])
        salida.append((f"{len(vip)} correo(s) que parecen importantes sin leer",
                       nombres, 0.72))
    elif len(correos) >= 10:
        salida.append((f"{len(correos)} correos sin leer acumulados",
                       "La bandeja de entrada se está llenando.", 0.4))
    return salida


def bandeja(limite: int = 10, log=print) -> list:
    """
    Alias moderno de `no_leidos` que devuelve una lista de dicts
    compatible con la API REST y el HUD.
    """
    correos = no_leidos(maximo=min(limite, 25), log=log)
    resultado = []
    for c in correos:
        resultado.append({
            "id":      c.get("id", ""),
            "from":    c.get("de", ""),
            "subject": c.get("asunto", ""),
            "body":    c.get("cuerpo", c.get("snippet", "")),
            "snippet": c.get("snippet", ""),
            "ts":      c.get("fecha_ts", 0),
            "read":    False,
            "vip":     c.get("vip", False),
        })
    return resultado


def leer(msg_id: str, log=print) -> dict:
    """Lee el contenido completo de un mensaje por su ID."""
    srv = _servicio(log=log)
    if not srv:
        return {"ok": False, "error": "Sin servicio de Gmail"}
    try:
        msg = srv.users().messages().get(
            userId="me", id=msg_id, format="full").execute()
        payload = msg.get("payload", {})
        asunto = _cabecera(payload, "subject")
        remitente = _cabecera(payload, "from")

        # Extraer cuerpo
        cuerpo = ""
        parts = payload.get("parts") or [payload]
        for p in parts:
            if p.get("mimeType") == "text/plain":
                data = p.get("body", {}).get("data", "")
                if data:
                    import base64
                    cuerpo = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                    break

        return {
            "ok": True,
            "id": msg_id,
            "from": remitente,
            "subject": asunto,
            "body": cuerpo[:3000],
            "vip": bool(_REMITENTES_VIP.search(asunto + remitente)),
        }
    except Exception as e:
        log(f"[CORREO] leer {msg_id}: {e}")
        return {"ok": False, "error": str(e)[:120]}
