#!/usr/bin/env python3
"""
mensajeria.py - Comunicación por voz para Jarvis
==================================================
Envía mensajes de WhatsApp y correos electrónicos desde comandos hablados:

  "Jarvis, abre whatsapp y escribele a Mangel que si puede jugar a las 3"
  "manda un whatsapp a Marta diciendo llego tarde"
  "escribele un correo a Luis que vemos mañana"           (con asunto opcional)
  "guarda el correo de Luis como luis@gmail.com"

Cómo funciona:
  * WhatsApp: abre web.whatsapp.com, localiza el panel de búsqueda por
    coordenadas relativas de la ventana, escribe el contacto, el mensaje
    y envía con Enter. Si no hay sesión iniciada, avisa del código QR.
  * Gmail: abre mail.google.com, tecla 'c' (redactar), escribe destinatario
    (resuelto desde la agenda de contactos guardada en user_prefs),
    asunto (opcional), cuerpo y envía con Ctrl+Enter.
  * Contactos: se guardan como user_prefs `contacto_<nombre>`.
"""
import os
import re
import subprocess
import time
import ctypes
import unicodedata


def _norm(s: str) -> str:
    n = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in n if unicodedata.category(c) != "Mn")


class Mensajeria:
    """Despachador de mensajería. handle(text) -> str | None"""

    def __init__(self, log=print, notify=None, get_pref=None, set_pref=None, safe=False):
        self.log = log
        self.notify = notify
        self._get_pref = get_pref
        self._set_pref = set_pref
        self.safe = safe

    # ── utilidades ───────────────────────────────────────────────────────────
    @staticmethod
    def _hwnd_rect(titulo_contiene):
        """Rect (left, top, w, h) de la primera ventana visible que contenga el texto."""
        user32 = ctypes.windll.user32
        resultado = [None]

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, 512)
                if titulo_contiene.lower() in buf.value.lower():
                    rect = ctypes.wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    resultado[0] = (rect.left, rect.top,
                                    rect.right - rect.left, rect.bottom - rect.top)
                    return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return resultado[0]

    def _abrir_y_esperar(self, url, segundos=12, titulo_busca=""):
        """Abre URL en el navegador por defecto y espera a que cargue."""
        subprocess.Popen(f"start {url}", shell=True, creationflags=0x08000000)
        time.sleep(segundos)
        if titulo_busca:
            for _ in range(6):
                rect = self._hwnd_rect(titulo_busca)
                if rect:
                    return rect
                time.sleep(2)
        return None

    # ── agenda de contactos ──────────────────────────────────────────────────
    def _correo_de(self, nombre):
        v = self._get_pref(f"contacto_{_norm(nombre)}") if self._get_pref else None
        return v

    def _guardar_correo(self, nombre, correo):
        if self._set_pref:
            self._set_pref(f"contacto_{_norm(nombre)}", correo.strip())
            return True
        return False

    # ── DESPACHADOR ──────────────────────────────────────────────────────────
    def handle(self, text: str):
        t = _norm(text)
        if not t:
            return None
        for fn in (self._contactos, self._whatsapp, self._correo):
            r = fn(t, text)
            if r:
                return r
        return None

    # ── contactos ────────────────────────────────────────────────────────────
    def _contactos(self, t: str, orig: str):
        m = re.search(r"guarda (?:el correo|la direccion|el email)\s+(?:de|del)\s+(.+?)\s+(?:como|en|con valor)\s+([\w.+-]+@[\w.-]+\.[a-z]{2,})", t)
        if m:
            nombre = re.sub(r"^(?:de\s+la\s+|de\s+|el\s+|a\s+)", "", m.group(1)).strip()
            correo = m.group(2)
            if self.safe:
                return f"[modo seguro] Guardaría el correo de {nombre} como {correo}"
            self._guardar_correo(nombre, correo)
            return f"Contacto guardado, señor: {nombre} → {correo}."
        m = re.search(r"(?:que correo|que email|cual es el correo)\s+(?:tienes|hay)\s+(?:de|para|del)\s+(.+)$", t)
        if m:
            nombre = m.group(1).strip().rstrip(".")
            c = self._correo_de(nombre)
            return (f"El correo de {nombre} es {c}, señor." if c
                    else f"Señor, no tengo el correo de {nombre}. Dígame «guarda el correo de {nombre} como ...».")
        return None

    # ── WhatsApp ─────────────────────────────────────────────────────────────
    def _whatsapp(self, t: str, orig: str):
        m = re.search(
            r"(?:escribele|escribe(?:le)?|mandale un|mandale|manda un whatsapp|"
            r"manda un mensaje|manda un wsp|manda un|manda|enviale|enviarle)\s*"
            r"(?:un mensaje|un whatsapp|por whatsapp|un wsp)?\s*"
            r"(?:a|al|para)\s+"
            r"(.+?)\s+"
            r"(?:que\s+|diciendo\s*:?\s*|:)\s*"
            r"(.+)$", t)
        if not m:
            return None
        nombre = re.sub(r"^(?:de\s+la\s+|de\s+|el\s+|a\s+)", "", m.group(1)).strip().rstrip(".")
        mensaje = m.group(2).strip().strip(".").strip("«»\"")
        if not nombre or not mensaje:
            return None

        # nombre con mayúsculas reales desde el texto original
        mo = re.search(r"(?:a|al|para)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ .-]{1,25})", orig)
        nombre_original = (mo.group(1).strip() if mo else nombre).strip()

        if self.safe:
            return f"[modo seguro] Enviaría por WhatsApp a {nombre_original}: «{mensaje}»"

        try:
            import pyautogui
            pyautogui.FAILSAFE = True
        except ImportError:
            return "Señor, falta pyautogui para escribir el mensaje."

        rect = self._abrir_y_esperar("https://web.whatsapp.com", segundos=14, titulo_busca="WhatsApp")
        if not rect:
            return ("Señor, abrí WhatsApp Web pero tardó en cargar. "
                    "Si ve un código QR, escanéelo con el teléfono y repita el mensaje.")
        left, top, w, h = rect
        # panel izquierdo: buscador de chats arriba
        x_buscar = left + int(w * 0.13)
        y_buscar = top + int(h * 0.045)
        x_mensaje = left + int(w * 0.5)
        y_mensaje = top + int(h * 0.965)

        pyautogui.click(x_buscar, y_buscar)
        time.sleep(1.0)
        pyautogui.typewrite(nombre_original, interval=0.04)
        time.sleep(1.5)
        pyautogui.press("enter")
        time.sleep(2.0)
        pyautogui.click(x_mensaje, y_mensaje)
        time.sleep(0.8)
        pyautogui.typewrite(mensaje, interval=0.03)
        time.sleep(0.5)
        pyautogui.press("enter")
        self.log(f"WhatsApp: enviado a {nombre_original}: {mensaje}")
        return f"Mensaje enviado a {nombre_original} por WhatsApp, señor."
        # -- nota: si no existe el chat, el mensaje se pierde en el buscador;

    # ── correo (Gmail) ───────────────────────────────────────────────────────
    def _correo(self, t: str, orig: str):
        m = re.search(
            r"(?:escribele|escribe(?:le)?|manda|mandale|enviale)\s*(?:un correo|un email|un mail|un mensaje de correo)?\s*"
            r"(?:a|al|para)\s+"
            r"(.+?)\s+"
            r"(?:que\s+|diciendo\s*:?\s*|:)\s*"
            r"(.+)$", t)
        if not m:
            return None
        nombre = re.sub(r"^(?:de\s+la\s+|de\s+|el\s+|a\s+)", "", m.group(1)).strip().rstrip(".")
        mensaje = m.group(2).strip().strip(".")
        if not nombre or not mensaje:
            return None
        if "correo" not in t and "email" not in t and "mail" not in t:
            return None  # "escribele a X que Y" sin palabra correo → WhatsApp

        correo = self._correo_de(nombre)
        if not correo:
            return (f"Señor, no tengo el correo de {nombre}. Dígame "
                    f"«guarda el correo de {nombre} como correo@ejemplo.com» y lo escribiré enseguida.")

        asunto = "Mensaje"
        ma = re.search(r"con (?:el )?asunto\s+(.+?)(?:\s+que\s+|\s+diciendo\s+|$)", t)
        if ma:
            asunto = ma.group(1).strip()

        if self.safe:
            return f"[modo seguro] Enviaría correo a {nombre} ({correo}): «{mensaje}»"

        try:
            import pyautogui
            pyautogui.FAILSAFE = True
        except ImportError:
            return "Señor, falta pyautogui."

        if not self._abrir_y_esperar("https://mail.google.com", segundos=12, titulo_busca="Gmail"):
            return "Señor, Gmail tardó en cargar. Asegúrese de tener sesión iniciada y repita el correo."
        time.sleep(2.0)
        pyautogui.press("c")          # redactar nuevo mensaje
        time.sleep(2.0)
        pyautogui.typewrite(correo, interval=0.03)
        pyautogui.press("tab")        # → Asunto
        time.sleep(0.5)
        pyautogui.typewrite(asunto, interval=0.03)
        pyautogui.press("tab")        # → Cuerpo
        time.sleep(0.5)
        pyautogui.typewrite(mensaje, interval=0.03)
        time.sleep(0.8)
        pyautogui.hotkey("ctrl", "enter")  # enviar
        self.log(f"Correo enviado a {correo}: {asunto}")
        return f"Correo enviado a {nombre} ({correo}), señor. Con asunto «{asunto}»."
        # -- nota: Ctrl+Enter envía en Gmail con atajos activados