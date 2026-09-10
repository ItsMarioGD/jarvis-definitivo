#!/usr/bin/env python3
"""
vision.py - Los ojos: que JARVIS vea tu pantalla
================================================
El proyecto ya sabia hacer capturas y pasarles OCR, pero nadie **interpretaba**
la imagen: el OCR devuelve letras sueltas, no entiende que hay un error de
compilacion en la esquina ni que un formulario tiene un campo sin rellenar.

Con un modelo de vision local (Ollama sirve llava, qwen2.5-vl, moondream...)
se abre lo que de verdad distingue a un asistente de escritorio de un chatbot:

    «¿que error me esta dando esto?»
    «¿que dice esta factura?»
    «¿que ventana tengo abierta?»

Todo local: la captura no sale del equipo, asi que funciona igual con el modo
privado activado.

Si no hay ningun modelo de vision instalado se dice exactamente que hacer
(`ollama pull qwen2.5vl:3b`) y, mientras tanto, se cae al OCR que ya existia:
peor respuesta, pero respuesta.
"""
import base64
import io as _io
import json
import os
import time
import urllib.request

# Modelos de visión conocidos, del más ligero al más capaz. Se usa el primero
# que el usuario tenga instalado.
MODELOS_VISION = ("qwen2.5vl:3b", "qwen2.5vl:7b", "llava:7b", "llava:13b",
                  "llama3.2-vision:11b", "moondream", "bakllava")
BASE_OLLAMA = os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1").replace("/v1", "")
ANCHO_MAX = int(os.getenv("JARVIS_VISION_ANCHO", "1280"))


# ── disponibilidad ──────────────────────────────────────────────────────────
def modelos_instalados(timeout: float = 5.0) -> list:
    try:
        with urllib.request.urlopen(f"{BASE_OLLAMA}/api/tags", timeout=timeout) as r:
            datos = json.load(r)
        return [m.get("name", "") for m in datos.get("models", [])]
    except Exception:
        return []


def modelo_vision(log=print) -> str:
    """Nombre del modelo de visión disponible, o cadena vacía."""
    forzado = os.getenv("JARVIS_VISION_MODELO", "").strip()
    if forzado:
        return forzado
    instalados = modelos_instalados()
    for candidato in MODELOS_VISION:
        for instalado in instalados:
            if instalado.startswith(candidato.split(":")[0]):
                return instalado
    return ""


def instrucciones_instalacion() -> str:
    return ("No tengo ojos todavía, señor: hace falta un modelo de visión local. "
            "Con «ollama pull qwen2.5vl:3b» (unos 3 GB) queda listo y no sale "
            "ni un píxel del equipo.")


# ── captura ─────────────────────────────────────────────────────────────────
def capturar_pantalla(ruta: str = "", log=print) -> str:
    """Captura la pantalla completa y devuelve la ruta del PNG."""
    if not ruta:
        carpeta = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Vision")
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, f"pantalla_{time.strftime('%Y%m%d_%H%M%S')}.png")
    try:
        from PIL import ImageGrab
        imagen = ImageGrab.grab(all_screens=True)
        imagen.save(ruta, "PNG")
        return ruta
    except Exception as e:
        log(f"[VISION] No pude capturar la pantalla: {e}")
        return ""


def _imagen_base64(ruta: str, log=print) -> str:
    """Imagen reducida y en base64 (una captura 4K satura al modelo)."""
    try:
        from PIL import Image
        with Image.open(ruta) as img:
            img = img.convert("RGB")
            if img.width > ANCHO_MAX:
                alto = int(img.height * ANCHO_MAX / img.width)
                img = img.resize((ANCHO_MAX, alto))
            buffer = _io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception as e:
        log(f"[VISION] No pude preparar la imagen: {e}")
        try:
            with open(ruta, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except Exception:
            return ""


# ── interpretación ──────────────────────────────────────────────────────────
def preguntar_a_imagen(ruta: str, pregunta: str, log=print, timeout: float = 120.0) -> str:
    """Le pregunta al modelo de visión sobre una imagen concreta."""
    modelo = modelo_vision(log=log)
    if not modelo:
        return _respaldo_ocr(ruta, pregunta, log=log)

    imagen = _imagen_base64(ruta, log=log)
    if not imagen:
        return "No pude leer la imagen, señor."

    cuerpo = json.dumps({
        "model": modelo,
        "prompt": (pregunta or "Describe lo que hay en la pantalla, en español y "
                               "en pocas frases. Si hay un error, dilo primero."),
        "images": [imagen],
        "stream": False,
        "options": {"temperature": 0.2},
    }).encode("utf-8")

    peticion = urllib.request.Request(f"{BASE_OLLAMA}/api/generate", data=cuerpo,
                                      headers={"Content-Type": "application/json"})
    try:
        inicio = time.time()
        with urllib.request.urlopen(peticion, timeout=timeout) as r:
            datos = json.load(r)
        texto = (datos.get("response") or "").strip()
        log(f"[VISION] {modelo} respondió en {time.time() - inicio:.1f}s")
        return texto or "No supe interpretar la imagen, señor."
    except Exception as e:
        log(f"[VISION] {modelo} falló: {e}")
        return _respaldo_ocr(ruta, pregunta, log=log)


def _respaldo_ocr(ruta: str, pregunta: str, log=print) -> str:
    """Sin modelo de visión, al menos leemos el texto de la imagen."""
    try:
        import pytesseract
        from PIL import Image
        texto = pytesseract.image_to_string(Image.open(ruta), lang="spa")[:1200].strip()
        if texto:
            return ("No tengo modelo de visión, señor, así que solo puedo leer el "
                    f"texto: «{texto[:400]}». " + instrucciones_instalacion())
    except Exception as e:
        log(f"[VISION] OCR de respaldo no disponible: {e}")
    return instrucciones_instalacion()


def mirar_pantalla(pregunta: str = "", log=print) -> str:
    """Captura la pantalla y responde a la pregunta del señor sobre ella."""
    ruta = capturar_pantalla(log=log)
    if not ruta:
        return "No pude capturar la pantalla, señor."
    respuesta = preguntar_a_imagen(ruta, pregunta, log=log)
    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "vision", "Miré la pantalla", (pregunta or "descripción general")[:120],
            gravedad="info", datos=ruta)
    except Exception:
        pass
    return respuesta


def estado(log=print) -> dict:
    modelo = modelo_vision(log=log)
    return {
        "modelo": modelo,
        "listo": bool(modelo),
        "instalados": modelos_instalados(),
        "ancho_max": ANCHO_MAX,
    }
