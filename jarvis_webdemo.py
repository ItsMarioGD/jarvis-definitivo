#!/usr/bin/env python3
"""
jarvis_webdemo.py - JARVIS crea demos web para empresas sin sitio
=================================================================
Genera un sitio web completo (HTML/CSS/JS) usando Claude, lo sube
a Vercel y devuelve la URL pública lista para enviar al cliente.

Flujo:
  1. jarvis: "crea demo para [empresa]"
  2. Este módulo: Claude genera el HTML completo (hero, servicios, CTA)
  3. Sube a Vercel via API y obtiene URL
  4. Jarvis entrega la URL y puede enviarla por correo
"""
import os
import json
import time
import re
import tempfile
import zipfile
import base64
from typing import Optional

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VERCEL_TOKEN = os.getenv("VERCEL_TOKEN", "")
LOVABLE_ENABLED = os.getenv("LOVABLE_ENABLED", "false").lower() == "true"


# ── Plantilla de prompt para generar el sitio ─────────────────────────────
_PROMPT_SITIO = """
Genera un sitio web de demostración profesional y moderno para la empresa: **{nombre}**
Industria: {industria}
Descripción: {descripcion}
Idioma: {idioma}

Crea UN archivo HTML completo y autocontenido con:
- CSS inline moderno (gradientes oscuros, colores de acento)
- Sección Hero con nombre de empresa y tagline
- Sección de Servicios (3-4 cards)
- Sección Nosotros
- Sección de contacto con formulario
- Footer con derechos
- Animaciones suaves (CSS transitions)
- Totalmente responsive (mobile-first)
- Paleta de colores: {color_primario} como acento principal
- Fuente: Inter o similar del sistema

IMPORTANTE:
- El código debe ser HTML válido completo (<!DOCTYPE html> hasta </html>)
- Sin dependencias externas (CDN) excepto Google Fonts
- Incluye meta tags SEO apropiados
- El sitio debe verse REAL y profesional, no como plantilla genérica
- Agrega una nota sutil al final: "Demo generada por JARVIS · Contacta para versión completa"

Devuelve SOLO el código HTML, sin explicaciones, sin markdown, sin ```html.
"""

_COLORES_INDUSTRIA = {
    "restaurante": "#e67e22", "comida": "#e67e22",
    "tecnologia": "#3498db", "tech": "#3498db", "software": "#3498db",
    "salud": "#2ecc71", "medicina": "#2ecc71", "clinica": "#2ecc71",
    "legal": "#2c3e50", "abogado": "#2c3e50",
    "construccion": "#e74c3c", "inmobiliaria": "#e74c3c",
    "educacion": "#9b59b6", "academia": "#9b59b6",
    "moda": "#e91e63", "ropa": "#e91e63",
    "viajes": "#00bcd4", "turismo": "#00bcd4",
}


def _color_para(industria: str) -> str:
    ind = (industria or "").lower()
    for k, v in _COLORES_INDUSTRIA.items():
        if k in ind:
            return v
    return "#00d4ff"


def _generar_html_con_claude(nombre: str, industria: str, descripcion: str,
                              idioma: str = "es", log=print) -> str:
    """Llama a Claude para generar el HTML completo del sitio."""
    if not ANTHROPIC_API_KEY:
        log("[DEMO] Sin ANTHROPIC_API_KEY; usando plantilla mínima.")
        return _html_fallback(nombre, industria, descripcion)

    prompt = _PROMPT_SITIO.format(
        nombre=nombre,
        industria=industria or "general",
        descripcion=descripcion or f"Empresa profesional de {industria}",
        idioma=idioma,
        color_primario=_color_para(industria),
    )

    try:
        from openai import OpenAI
        cliente = OpenAI(
            base_url="https://api.anthropic.com/v1",
            api_key=ANTHROPIC_API_KEY,
        )
        modelo = os.getenv("JARVIS_MODELO_DEMO", "claude-sonnet-4-6")
        resp = cliente.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content":
                 "Eres un diseñador web experto. Genera código HTML perfecto."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=8000,
            temperature=0.7,
        )
        html = (resp.choices[0].message.content or "").strip()
        # Limpiar posibles bloques markdown
        html = re.sub(r"^```html?\s*", "", html, flags=re.IGNORECASE)
        html = re.sub(r"\s*```$", "", html)
        return html
    except Exception as e:
        log(f"[DEMO] Claude falló ({e}), usando fallback.")
        return _html_fallback(nombre, industria, descripcion)


def _html_fallback(nombre: str, industria: str, descripcion: str) -> str:
    color = _color_para(industria)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{nombre} - Sitio Oficial</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Inter',sans-serif;background:#0a0a0f;color:#e0e0e0}}
  .hero{{background:linear-gradient(135deg,#0a0a0f 0%,#1a1a2e 100%);padding:100px 20px;text-align:center}}
  .hero h1{{font-size:clamp(2rem,5vw,4rem);font-weight:700;color:#fff;margin-bottom:20px}}
  .hero h1 span{{color:{color}}}
  .hero p{{font-size:1.2rem;max-width:600px;margin:0 auto 40px;color:#aaa}}
  .btn{{background:{color};color:#fff;padding:14px 36px;border-radius:8px;
    text-decoration:none;font-weight:600;display:inline-block;transition:transform .2s}}
  .btn:hover{{transform:scale(1.05)}}
  section{{padding:80px 20px;max-width:1100px;margin:0 auto}}
  h2{{font-size:2rem;font-weight:700;margin-bottom:40px;text-align:center}}
  h2 span{{color:{color}}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:24px}}
  .card{{background:#111;border:1px solid #222;border-radius:12px;padding:32px;
    transition:border-color .3s}}
  .card:hover{{border-color:{color}}}
  .card h3{{color:{color};margin-bottom:12px}}
  footer{{background:#111;padding:40px 20px;text-align:center;color:#666}}
  .tag{{display:inline-block;background:#1a1a2e;color:{color};
    padding:4px 12px;border-radius:20px;font-size:.75rem;margin-top:20px}}
</style>
</head>
<body>
<div class="hero">
  <h1><span>{nombre}</span></h1>
  <p>{descripcion}</p>
  <a href="#contacto" class="btn">Conoce más</a>
</div>
<section>
  <h2>Nuestros <span>Servicios</span></h2>
  <div class="cards">
    <div class="card"><h3>Servicio Premium</h3><p>Soluciones a medida para tu negocio con la más alta calidad.</p></div>
    <div class="card"><h3>Consultoría</h3><p>Acompañamiento experto en cada etapa de tu proyecto.</p></div>
    <div class="card"><h3>Soporte 24/7</h3><p>Atención continua para que tu operación nunca se detenga.</p></div>
  </div>
</section>
<section id="contacto">
  <h2>Contáctanos</h2>
  <div style="max-width:500px;margin:0 auto;background:#111;border-radius:12px;padding:40px">
    <input style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:12px;border-radius:8px;margin-bottom:16px;display:block" placeholder="Tu nombre">
    <input style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:12px;border-radius:8px;margin-bottom:16px;display:block" placeholder="Tu email">
    <textarea style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:12px;border-radius:8px;margin-bottom:16px;display:block;resize:vertical;min-height:100px" placeholder="Tu mensaje"></textarea>
    <button style="width:100%;background:{color};color:#fff;padding:14px;border:none;border-radius:8px;font-weight:600;cursor:pointer">Enviar</button>
  </div>
</section>
<footer>
  <p>&copy; 2025 {nombre}. Todos los derechos reservados.</p>
  <span class="tag">Demo generada por JARVIS · Contacta para versión completa</span>
</footer>
</body>
</html>"""


def subir_a_vercel(html: str, nombre_proyecto: str, log=print) -> dict:
    """
    Despliega el HTML a Vercel usando la API de deployments.
    Requiere VERCEL_TOKEN en el entorno.
    Devuelve dict con 'url', 'ok', y 'error'.
    """
    if not VERCEL_TOKEN:
        return {"ok": False, "error": "Sin VERCEL_TOKEN; configura la variable de entorno."}

    import urllib.request
    import urllib.error

    slug = re.sub(r"[^a-z0-9-]", "-",
                  (nombre_proyecto or "demo").lower().strip())[:40].strip("-")
    if not slug:
        slug = "jarvis-demo"

    timestamp = int(time.time())
    project_name = f"{slug}-{timestamp}"

    payload = {
        "name": project_name,
        "files": [
            {
                "file": "index.html",
                "data": base64.b64encode(html.encode("utf-8")).decode(),
                "encoding": "base64",
            }
        ],
        "projectSettings": {
            "framework": None,
            "outputDirectory": None,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.vercel.com/v13/deployments",
        data=data,
        headers={
            "Authorization": f"Bearer {VERCEL_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode())
        url = resp.get("url") or resp.get("alias", [None])[0]
        if url and not url.startswith("http"):
            url = "https://" + url
        return {"ok": True, "url": url, "id": resp.get("id", ""), "name": project_name}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log(f"[DEMO] Vercel error {e.code}: {body[:200]}")
        return {"ok": False, "error": f"Vercel devolvió {e.code}: {body[:100]}"}
    except Exception as e:
        log(f"[DEMO] Error al subir a Vercel: {e}")
        return {"ok": False, "error": str(e)[:120]}


# ── Punto de entrada principal ─────────────────────────────────────────────
def crear_demo(nombre: str, industria: str = "", descripcion: str = "",
               idioma: str = "es", log=print) -> dict:
    """
    Crea una demo web completa para la empresa dada y la sube a Vercel.
    Retorna {'ok', 'url', 'html', 'nombre', 'error'}.
    """
    if not nombre or len(nombre.strip()) < 2:
        return {"ok": False, "error": "Necesito el nombre de la empresa."}

    nombre = nombre.strip()
    industria = industria.strip()
    descripcion = descripcion.strip()

    log(f"[DEMO] Generando sitio para «{nombre}» ({industria})…")
    html = _generar_html_con_claude(nombre, industria, descripcion, idioma, log=log)

    if not html or len(html) < 200:
        return {"ok": False, "error": "La generación del HTML falló."}

    log(f"[DEMO] HTML generado ({len(html)} chars). Subiendo a Vercel…")
    resultado = subir_a_vercel(html, nombre, log=log)

    resultado["html"] = html
    resultado["nombre"] = nombre

    if resultado.get("ok"):
        log(f"[DEMO] ✓ Demo disponible en {resultado.get('url')}")
        try:
            from storage import get_storage
            get_storage(log=log).registrar_evento(
                "webdemo", f"Demo creada: {nombre}",
                f"URL: {resultado.get('url')}", gravedad="info")
        except Exception:
            pass
    else:
        log(f"[DEMO] No se pudo subir: {resultado.get('error')}")

    return resultado


def listar_demos(log=print) -> list:
    """Lista demos creadas (guardadas en storage)."""
    try:
        from storage import get_storage
        eventos = get_storage(log=log).obtener_eventos("webdemo", limite=20)
        return eventos or []
    except Exception:
        return []
