#!/usr/bin/env python3
"""
reunion.py - Modo reunión: de un audio a acuerdos y tareas
=========================================================
`jarvis_whisper.py` ya transcribe. Esto añade lo que faltaba: de la
transcripción saca un resumen, la lista de acuerdos y las tareas con
responsable, y mete cada tarea como recordatorio (`core.add_reminder`).

    "resume la reunión: C:\\...\\grabacion.wav"

La diarización real (quién habla) necesita pyannote y no está; se trabaja sobre
el texto corrido, que para extraer acuerdos y tareas basta.

Guarda transcripción + análisis en ~/Descargas/JARVIS/Reuniones/.
"""
import json
import os
import re
import time

_DIR = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Reuniones")


def transcribir(ruta: str, log=print) -> str:
    ruta = os.path.expanduser((ruta or "").strip().strip('"'))
    if not os.path.isfile(ruta):
        return ""
    # 1) faster-whisper acepta cualquier formato
    try:
        from faster_whisper import WhisperModel
        modelo = WhisperModel(os.getenv("JARVIS_FW_MODELO", "small"),
                              device="cpu", compute_type="int8")
        segmentos, _info = modelo.transcribe(ruta, language="es")
        return " ".join(s.text.strip() for s in segmentos).strip()
    except Exception as e:
        log(f"[REUNION] faster-whisper no disponible ({str(e)[:80]}); pruebo whisper.cpp")
    # 2) whisper.cpp (solo .wav)
    try:
        import jarvis_whisper
        if ruta.lower().endswith(".wav"):
            return jarvis_whisper.get_whisper_stt(log=log).transcribe_file(ruta, timeout=600)
    except Exception as e:
        log(f"[REUNION] whisper.cpp falló: {e}")
    return ""


_PROMPT = (
    "Eres el secretario de una reunión. A partir de esta transcripción en "
    "español, devuelve SOLO un JSON con esta forma exacta:\n"
    '{"resumen": "2-3 frases", "acuerdos": ["..."], '
    '"tareas": [{"quien": "nombre o \'sin asignar\'", "que": "...", "cuando": "fecha/plazo o \'\'"}]}\n'
    "Sin texto fuera del JSON. Transcripción:\n\n"
)


def analizar(core, transcripcion: str, log=print) -> dict:
    if not transcripcion.strip():
        return {}
    try:
        from openai import OpenAI
        nombre, url, modelo, clave = core._proveedores()[0]
        cli = OpenAI(base_url=url, api_key=clave)
        r = cli.chat.completions.create(
            model=modelo, temperature=0.1, max_tokens=900,
            messages=[{"role": "user", "content": _PROMPT + transcripcion[:12000]}])
        crudo = (r.choices[0].message.content or "").strip()
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        return json.loads(m.group(0)) if m else {}
    except Exception as e:
        log(f"[REUNION] análisis falló: {e}")
        return {}


def procesar(core, ruta: str, log=print) -> str:
    t0 = time.time()
    texto = transcribir(ruta, log=log)
    if not texto:
        return ("Señor, no pude transcribir ese audio. Necesito faster-whisper "
                "instalado, o un archivo .wav para whisper.cpp.")
    datos = analizar(core, texto, log=log)
    if not datos:
        return "Transcribí la reunión, señor, pero no pude extraer acuerdos ni tareas."

    tareas = datos.get("tareas", []) or []
    metidas = 0
    for tarea in tareas:
        que = (tarea.get("que") or "").strip()
        if not que:
            continue
        quien = (tarea.get("quien") or "").strip()
        cuando = (tarea.get("cuando") or "").strip()
        etiqueta = f"[Reunión] {que}" + (f" — {quien}" if quien and quien != "sin asignar" else "")
        try:
            core.add_reminder(etiqueta, due=cuando)
            metidas += 1
        except Exception as e:
            log(f"[REUNION] no pude guardar tarea: {e}")

    # Guardar acta
    try:
        os.makedirs(_DIR, exist_ok=True)
        acta = os.path.join(_DIR, time.strftime("%Y%m%d-%H%M%S") + ".md")
        with open(acta, "w", encoding="utf-8") as f:
            f.write(f"# Acta {time.strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(f"## Resumen\n{datos.get('resumen', '')}\n\n")
            f.write("## Acuerdos\n" + "\n".join(f"- {a}" for a in datos.get("acuerdos", [])) + "\n\n")
            f.write("## Tareas\n" + "\n".join(
                f"- {t.get('que','')} ({t.get('quien','')}, {t.get('cuando','') or 'sin plazo'})"
                for t in tareas) + "\n\n")
            f.write("## Transcripción\n" + texto + "\n")
    except Exception as e:
        log(f"[REUNION] no pude guardar el acta: {e}")
        acta = ""

    dur = int(time.time() - t0)
    partes = [f"Reunión procesada en {dur} segundos, señor.",
              datos.get("resumen", "")]
    if datos.get("acuerdos"):
        partes.append(f"{len(datos['acuerdos'])} acuerdos.")
    partes.append(f"He anotado {metidas} tarea{'s' if metidas != 1 else ''} como recordatorios.")
    if acta:
        partes.append(f"El acta completa está en {acta}.")
    return " ".join(p for p in partes if p)
