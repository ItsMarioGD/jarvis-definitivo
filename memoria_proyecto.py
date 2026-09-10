#!/usr/bin/env python3
"""
memoria_proyecto.py - JARVIS.md: la memoria permanente que se carga cada sesión
=============================================================================
mem0 es memoria semántica (se busca por parecido) y `user_prefs` es clave-valor.
Faltaba lo que en Claude Code es CLAUDE.md: un texto corto, escrito a mano o por
el propio JARVIS, con hechos y convenciones que SIEMPRE deben estar presentes:

    - "El proyecto vive en C:\\Users\\...\\jarvis definitivo"
    - "Nunca reinicies el PC entre las 9 y las 18: hay trabajo abierto"
    - "Al señor le gusta que las respuestas por voz no pasen de dos frases"

Se inyecta entero en el prompt cada turno (con tope), así que conviene que sea
breve. Lo edita el señor con un editor, o JARVIS con `anadir()`.
"""
import os
import time

_RUTA = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "JARVIS.md")
_TOPE = int(os.getenv("JARVIS_MD_TOPE", "4000"))

_PLANTILLA = """# JARVIS.md — Memoria permanente

Este archivo se carga entero en cada conversación. Manténlo breve.
Lo edita el señor a mano, o JARVIS cuando se le pide «apunta en tu memoria permanente que…».

## Preferencias fijas
- (aún nada)

## Convenciones
- (aún nada)

## Proyectos en curso
- (aún nada)

## Notas
"""


def _asegurar():
    if not os.path.exists(_RUTA):
        try:
            os.makedirs(os.path.dirname(_RUTA), exist_ok=True)
            with open(_RUTA, "w", encoding="utf-8") as f:
                f.write(_PLANTILLA)
        except Exception:
            pass


def cargar(log=print) -> str:
    _asegurar()
    try:
        with open(_RUTA, encoding="utf-8") as f:
            txt = f.read().strip()
        return txt[:_TOPE]
    except Exception as e:
        log(f"[JARVIS.md] no pude leer: {e}")
        return ""


def contexto(log=print) -> str:
    txt = cargar(log=log)
    if not txt:
        return ""
    # Si no hay ni un punto real (todo son placeholders), no gastamos tokens.
    reales = [l for l in txt.splitlines()
              if l.lstrip().startswith("- ") and l.strip() != "- (aún nada)"]
    if not reales:
        return ""
    return "[Memoria permanente del señor (JARVIS.md):\n" + txt + "\n]"


def anadir(nota: str, seccion: str = "Notas", log=print) -> str:
    """Añade un punto. Si la sección existe, debajo de ella; si no, al final."""
    nota = (nota or "").strip().rstrip(".")
    if not nota:
        return "¿Qué apunto, señor?"
    _asegurar()
    try:
        with open(_RUTA, encoding="utf-8") as f:
            lineas = f.read().splitlines()
    except Exception as e:
        return f"No pude abrir la memoria permanente: {e}"

    marca = f"## {seccion}"
    sello = time.strftime("%Y-%m-%d")
    punto = f"- {nota}  ({sello})"

    idx = next((i for i, l in enumerate(lineas) if l.strip().lower() == marca.lower()), -1)
    if idx == -1:
        lineas += ["", marca, punto]
    else:
        j = idx + 1
        while j < len(lineas) and not lineas[j].startswith("## "):
            j += 1
        # quita el placeholder si estaba
        bloque = lineas[idx + 1:j]
        bloque = [b for b in bloque if b.strip() != "- (aún nada)"]
        lineas = lineas[:idx + 1] + bloque + [punto] + lineas[j:]

    try:
        with open(_RUTA, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lineas).rstrip() + "\n")
        return f"Apuntado en mi memoria permanente, señor: «{nota}»."
    except Exception as e:
        return f"No pude guardarlo: {e}"


def ruta() -> str:
    return _RUTA
