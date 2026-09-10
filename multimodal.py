#!/usr/bin/env python3
"""
multimodal.py - Meter una imagen o un PDF en la conversación
==========================================================
`vision.preguntar_a_imagen` ya pregunta a un modelo de visión LOCAL (Ollama).
Esto añade dos cosas:

* Ruta de nube: manda la imagen como `image_url` (data URI) al proveedor
  configurado, por si el modelo de nube ve mejor que el local. Si falla, cae a
  `vision` (local) y de ahí a OCR.
* PDF: extrae el texto (pdfplumber / PyPDF2) y se lo pasa al modelo de texto.

Se usa como herramienta (`analizar_imagen`, `analizar_documento`) o por voz
(«mira esta imagen: ...», «qué dice este pdf: ...»).
"""
import base64
import os

_MAX_PDF_CHARS = 12000


def _data_uri(ruta: str) -> str:
    ext = os.path.splitext(ruta)[1].lower().lstrip(".") or "png"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp",
            "gif": "gif"}.get(ext, "png")
    with open(ruta, "rb") as f:
        return f"data:image/{mime};base64," + base64.b64encode(f.read()).decode("ascii")


def _imagen_nube(core, ruta: str, pregunta: str, log=print) -> str:
    try:
        from openai import OpenAI
    except Exception:
        return ""
    try:
        for nombre, url, modelo, clave in core._proveedores():
            if ("localhost" in url) or ("127.0.0.1" in url):
                continue  # el local ya lo cubre vision.py
            try:
                import presupuesto
                if not presupuesto.permite_nube():
                    return ""
            except Exception:
                pass
            cli = OpenAI(base_url=url, api_key=clave)
            r = cli.chat.completions.create(
                model=modelo, temperature=0.2, max_tokens=500,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": pregunta or
                     "Describe esta imagen en español, breve. Si hay un error, dilo primero."},
                    {"type": "image_url", "image_url": {"url": _data_uri(ruta)}},
                ]}])
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                log(f"[MULTIMODAL] visión por nube ({nombre})")
                return txt
    except Exception as e:
        log(f"[MULTIMODAL] visión por nube falló: {str(e)[:100]}")
    return ""


def analizar_imagen(core, ruta: str, pregunta: str = "", log=print) -> str:
    ruta = os.path.expanduser((ruta or "").strip().strip('"'))
    if not os.path.isfile(ruta):
        return f"No encuentro la imagen {ruta}, señor."
    txt = _imagen_nube(core, ruta, pregunta, log=log)
    if txt:
        return txt
    try:
        import vision
        return vision.preguntar_a_imagen(ruta, pregunta, log=log)
    except Exception as e:
        return f"No pude analizar la imagen, señor: {str(e)[:100]}"


def _texto_pdf(ruta: str, log=print) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(ruta) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:20])
    except Exception:
        pass
    try:
        from pypdf import PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader
        except Exception:
            return ""
    try:
        lector = PdfReader(ruta)
        return "\n".join((pg.extract_text() or "") for pg in lector.pages[:20])
    except Exception as e:
        log(f"[MULTIMODAL] no pude leer el PDF: {e}")
        return ""


def analizar_documento(core, ruta: str, pregunta: str = "", log=print) -> str:
    ruta = os.path.expanduser((ruta or "").strip().strip('"'))
    if not os.path.isfile(ruta):
        return f"No encuentro el documento {ruta}, señor."
    if ruta.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return analizar_imagen(core, ruta, pregunta, log=log)
    texto = _texto_pdf(ruta, log=log) if ruta.lower().endswith(".pdf") else ""
    if not texto:
        try:
            with open(ruta, encoding="utf-8", errors="replace") as f:
                texto = f.read()
        except Exception:
            texto = ""
    if not texto.strip():
        return "No pude extraer texto de ese documento, señor."
    try:
        from openai import OpenAI
        nombre, url, modelo, clave = core._proveedores()[0]
        cli = OpenAI(base_url=url, api_key=clave)
        q = pregunta or "Resume este documento en español, en 3-5 frases."
        r = cli.chat.completions.create(
            model=modelo, temperature=0.2, max_tokens=600,
            messages=[{"role": "user",
                       "content": f"{q}\n\n---\n{texto[:_MAX_PDF_CHARS]}"}])
        return (r.choices[0].message.content or "").strip() or "No supe resumirlo, señor."
    except Exception as e:
        return f"Leí el documento pero no pude analizarlo, señor: {str(e)[:100]}"
