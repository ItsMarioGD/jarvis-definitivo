#!/usr/bin/env python3
"""
vision.py - Los ojos: que JARVIS vea tu pantalla
================================================
El proyecto ya sabia hacer capturas y pasarles OCR, pero nadie **interpretaba**
la imagen: el OCR devuelve letras sueltas, no entiende que hay un error de
compilacion en la esquina ni que un formulario tiene un campo sin rellenar.

Quien mira es, por orden: el modelo con ojos de casa (qwen2.5vl servido por
Ollama) y, si no esta descargado, Claude. Lo que se abre con ello es lo que de
verdad distingue a un asistente de escritorio de un chatbot:

    «¿que error me esta dando esto?»
    «¿que dice esta factura?»
    «¿que ventana tengo abierta?»

Con el modelo local la captura NO sale del equipo, asi que el modo privado ya
no obliga a conformarse con el OCR: se ve de verdad sin mandar nada a ningun
sitio. Si el que mira es Claude, la imagen si viaja, y entonces el modo privado
la para: se lee el texto con OCR y se explica por que.
"""
import base64
import io as _io
import os
import time

try:
    ANCHO_MAX = int((os.getenv("JARVIS_VISION_ANCHO") or "").strip() or 1280)
except ValueError:
    ANCHO_MAX = 1280
MODELO = os.getenv("JARVIS_VISION_MODELO", "").strip()


# ── disponibilidad ──────────────────────────────────────────────────────────
def proveedor_vision(log=print) -> tuple:
    """(url, modelo, clave) del que VE, o () si nadie puede mirar.

    Primero el de casa (qwen2.5vl por Ollama): no cuesta nada y la captura NO
    sale del equipo, que para una foto de la pantalla del señor importa. Si no
    está descargado, Claude; y si tampoco, nadie.
    """
    # `JARVIS_VISION` manda sobre todo lo demás: «nube» para una imagen difícil
    # (una foto torcida, un enunciado a mano), «local» para no sacar nada del
    # equipo. Vacío o «auto» = el de casa primero.
    quien = ((os.getenv("JARVIS_VISION") or "").strip().lower()
             or (os.getenv("JARVIS_CEREBRO") or "").strip().lower())
    if quien in ("nube", "pollinations") and not privado():
        try:
            import proveedor_pollinations as poll
            if poll.hay_clave():
                modelo = MODELO or poll.modelo_vision(log=log)
                if modelo:
                    return (poll.url(), modelo, poll.clave())
        except Exception as e:
            log(f"[VISION] Pollinations no disponible: {e}")

    try:
        import cerebro_local
        if quien not in ("claude", "anthropic"):
            modelo = MODELO or cerebro_local.MODELO_VISION
            if cerebro_local.tiene(modelo) and (cerebro_local.vivo() or
                                                cerebro_local.arrancar(log=log)):
                return (cerebro_local.URL, modelo, cerebro_local.CLAVE)
    except Exception as e:
        log(f"[VISION] cerebro local no disponible: {e}")

    # Con el modo privado puesto, la captura NO sale del equipo: si el de casa
    # no puede mirar, no mira nadie. Es el sentido entero de ese modo.
    if privado():
        return ()

    # Pollinations antes que Anthropic: hay 95 modelos con ojos y la cuenta de
    # Anthropic lleva sin saldo desde septiembre.
    #
    # Va DETRÁS del de casa a propósito, y no por cortesía: medido sobre un
    # enunciado en pantalla, qwen2.5vl:3b acierta lo mismo que gpt-5-nano y
    # solo tarda 1,7 s más. Mandar una foto de su pantalla a un tercero para
    # empatar no sale a cuenta. Para una imagen difícil está `JARVIS_VISION`.
    try:
        import proveedor_pollinations as poll
        if poll.hay_clave():
            modelo = MODELO or poll.modelo_vision(log=log)
            if modelo:
                return (poll.url(), modelo, poll.clave())
    except Exception as e:
        log(f"[VISION] Pollinations no disponible: {e}")

    clave = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if clave:
        try:
            import proveedor_claude
            modelo = MODELO if (MODELO or "").lower().startswith("claude") else ""
            return (proveedor_claude.URL_ANTHROPIC,
                    modelo or proveedor_claude.MODELO_CLAUDE_DEFECTO, clave)
        except Exception:
            pass
    return ()


def modelo_vision(log=print) -> str:
    """Nombre del modelo con el que se mira, o cadena vacia si no hay ninguno."""
    p = proveedor_vision(log=log)
    return p[1] if p else ""


def modelos_instalados(timeout: float = 5.0) -> list:
    """Los modelos con ojos que hay a mano, locales y de la nube."""
    salida = []
    try:
        import cerebro_local
        salida += [m for m in cerebro_local.modelos_instalados()
                   if "vl" in m.lower() or "vision" in m.lower()]
    except Exception:
        pass
    if (os.getenv("ANTHROPIC_API_KEY") or "").strip():
        try:
            import proveedor_claude
            salida += list(proveedor_claude.MODELOS)
        except Exception:
            pass
    return salida


def privado() -> bool:
    """¿Modo privado? Entonces la captura no sale del equipo."""
    if os.getenv("JARVIS_PRIVADO", "0") == "1":
        return True
    # La preferencia la deja privacidad.activar() en la tabla user_prefs. Se
    # lee de la base directamente para no necesitar el core aqui.
    try:
        import sqlite3
        import jarvis_config
        con = sqlite3.connect(jarvis_config.JARVIS_DB, timeout=3)
        try:
            fila = con.execute(
                "SELECT value FROM user_prefs WHERE key = 'modo_privado'").fetchone()
        finally:
            con.close()
        return bool(fila) and str(fila[0]).strip() == "1"
    except Exception:
        return False


def instrucciones_instalacion() -> str:
    if privado() and not modelo_vision():
        return ("Con el modo privado activado no mando su pantalla a ningún "
                "sitio, señor, y no tengo aquí ningún modelo con ojos: solo "
                "puedo leerle el texto con OCR.")
    try:
        import cerebro_local
        modelo = MODELO or cerebro_local.MODELO_VISION
        if not cerebro_local.tiene(modelo):
            return (f"No tengo ojos todavía, señor: me falta el modelo {modelo}. "
                    f"Descárguelo con «ollama pull {modelo}» (unos 3 GB) y veré "
                    "la pantalla sin que salga nada de este equipo.")
        if not cerebro_local.vivo():
            return ("No tengo ojos ahora mismo, señor: Ollama está apagado. "
                    "Arránquelo y vuelvo a ver.")
    except Exception:
        pass
    return ("No tengo ojos todavía, señor: ni el modelo local ni la clave de "
            "Anthropic están disponibles.")


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
    """Imagen reducida y en base64 (una captura 4K gasta tokens de sobra)."""
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
    """Le pregunta al modelo con ojos sobre una imagen concreta."""
    proveedor = proveedor_vision(log=log)
    if not proveedor:
        return _respaldo_ocr(ruta, pregunta, log=log)
    url, modelo, clave = proveedor

    # El modo privado existe para que la pantalla del señor no salga de casa.
    # Con el modelo local mirando no sale: la imagen no pasa de este equipo,
    # así que se puede ver de verdad en vez de deletrear el OCR.
    if privado():
        try:
            import proveedor_claude as _pc
            if not _pc.es_local(url):
                return _respaldo_ocr(ruta, pregunta, log=log)
            log(f"[VISION] modo privado: miro con {modelo}, aquí mismo")
        except Exception:
            return _respaldo_ocr(ruta, pregunta, log=log)

    imagen = _imagen_base64(ruta, log=log)
    if not imagen:
        return "No pude leer la imagen, señor."

    try:
        import presupuesto
        import proveedor_claude as _pc
        # El cerebro de casa no gasta: el tope solo aplica a la nube.
        if not _pc.es_local(url) and not presupuesto.permite_nube():
            log("[VISION] Tope de gasto alcanzado: miro con OCR.")
            return _respaldo_ocr(ruta, pregunta, log=log)
    except Exception:
        pass

    try:
        from proveedor_claude import cliente as OpenAI
        inicio = time.time()
        cli = OpenAI(url, api_key=clave, timeout=timeout, log=log)
        r = cli.chat.completions.create(
            model=modelo, max_tokens=1200,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": pregunta or
                 "Describe lo que hay en la pantalla, en español y en pocas "
                 "frases. Si hay un error, dilo primero."},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{imagen}"}},
            ]}])
        texto = (r.choices[0].message.content or "").strip()
        log(f"[VISION] {modelo} respondió en {time.time() - inicio:.1f}s")
        try:
            import presupuesto
            uso = getattr(r, "usage", None)
            if uso:
                presupuesto.registrar_uso("claude", modelo,
                                          getattr(uso, "prompt_tokens", 0) or 0,
                                          getattr(uso, "completion_tokens", 0) or 0)
        except Exception:
            pass
        return texto or "No supe interpretar la imagen, señor."
    except Exception as e:
        log(f"[VISION] {modelo} falló: {e}")
        return _respaldo_ocr(ruta, pregunta, log=log)


def _respaldo_ocr(ruta: str, pregunta: str, log=print) -> str:
    """Sin Claude (o en modo privado), al menos leemos el texto de la imagen."""
    try:
        import pytesseract
        from PIL import Image
        texto = pytesseract.image_to_string(Image.open(ruta), lang="spa")[:1200].strip()
        if texto:
            return ("Solo puedo leerle el texto, señor: "
                    f"«{texto[:400]}». " + instrucciones_instalacion())
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
    proveedor = proveedor_vision(log=log)
    modelo = proveedor[1] if proveedor else ""
    # Con el modelo de casa mirando, el modo privado no apaga los ojos: la
    # captura no sale de este equipo. El HUD decía «ojos: sin modelo»
    # teniendo qwen2.5vl descargado y funcionando.
    local = False
    if proveedor:
        try:
            import proveedor_claude as _pc
            local = _pc.es_local(proveedor[0])
        except Exception:
            local = False
    return {
        "modelo": modelo,
        "listo": bool(modelo) and (local or not privado()),
        "local": local,
        "instalados": modelos_instalados(),
        "privado": privado(),
        "ancho_max": ANCHO_MAX,
    }
