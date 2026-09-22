#!/usr/bin/env python3
"""
pensar.py - Pedirle al cerebro sin que se quede a medias
========================================================
Todos los módulos que hablan con el modelo repetían el mismo trozo: montar el
cliente, llamar, quitar el `<think>` y rezar. Y todos se tropezaban con la
misma piedra, que no es evidente hasta que pasa:

    **Los modelos que razonan gastan del MISMO presupuesto de tokens.**

Con `max_tokens=2500` y un encargo largo —sacar doce tarjetas de unos apuntes—
el modelo se gasta los 2500 pensando y devuelve `finish_reason: length` con el
contenido **vacío**. No es un error: la llamada tiene éxito y no trae nada. El
módulo de arriba entonces dice «el cerebro no devolvió nada» y el señor no
tiene forma de saber por qué.

Aquí se resuelve una vez y para todos:

    1. Se pide con `reasoning_effort` bajo, que en lo estructurado no hace
       falta pensar en voz alta y además tarda menos (medido: 7,2 s -> 4,3 s).
    2. Si vuelve vacío por falta de sitio, se reintenta con el doble de
       presupuesto y sin razonamiento.
    3. Si se esperaba JSON y no lo hay, se reintenta pidiéndolo a bocajarro.

Y si el proveedor no entiende `reasoning_effort` —los de casa no—, se reintenta
sin él en vez de fallar.
"""
import json
import os
import re

MAX_TOKENS = int(os.getenv("JARVIS_PENSAR_MAX_TOKENS", "3000"))


def _cliente(core):
    from proveedor_claude import cliente as OpenAI
    _n, url, modelo, clave = core._proveedores()[0]
    return OpenAI(base_url=url, api_key=clave), modelo


def _llamar(cliente, modelo, mensajes, tope, esfuerzo, temperatura):
    """Una llamada. Devuelve (texto, motivo_de_fin)."""
    comun = dict(model=modelo, messages=mensajes, max_tokens=tope,
                 temperature=temperatura)
    try:
        r = cliente.chat.completions.create(**comun,
                                            extra_body={"reasoning_effort": esfuerzo})
    except TypeError:
        r = cliente.chat.completions.create(**comun)      # SDK sin extra_body
    except Exception as e:
        # Un proveedor que no conoce el parámetro no debe tumbar la petición.
        if "reasoning" not in str(e).lower():
            raise
        r = cliente.chat.completions.create(**comun)

    from proveedor_claude import sin_pensamiento
    eleccion = r.choices[0]
    return (sin_pensamiento(eleccion.message.content or "").strip(),
            getattr(eleccion, "finish_reason", "") or "")


def texto(core, sistema: str, usuario: str, tope: int = None,
          temperatura: float = 0.3, esfuerzo: str = "low", log=print) -> str:
    """Respuesta de texto. Cadena vacía si de verdad no hubo forma."""
    tope = tope or MAX_TOKENS
    try:
        cliente, modelo = _cliente(core)
    except Exception as e:
        log(f"[PENSAR] No hay cerebro al que preguntar: {e}")
        return ""

    mensajes = [{"role": "system", "content": sistema},
                {"role": "user", "content": usuario}]
    try:
        salida, motivo = _llamar(cliente, modelo, mensajes, tope, esfuerzo, temperatura)
    except Exception as e:
        log(f"[PENSAR] El cerebro no contestó: {e}")
        return ""

    # Vacío por falta de sitio: el razonamiento se comió el turno entero.
    if not salida and motivo == "length":
        log(f"[PENSAR] Se quedó sin tokens razonando; reintento con {tope * 2}.")
        try:
            salida, _m = _llamar(cliente, modelo, mensajes, tope * 2, "none",
                                 temperatura)
        except Exception as e:
            log(f"[PENSAR] El reintento falló: {e}")
    return salida


def _rescatar_json(texto_crudo: str):
    """El JSON aunque venga envuelto en explicaciones o en ```json."""
    if not texto_crudo:
        return None
    limpio = re.sub(r"^\s*```(?:json)?|```\s*$", "", texto_crudo.strip(),
                    flags=re.MULTILINE)
    for candidato in (limpio, texto_crudo):
        m = re.search(r"[{\[].*[}\]]", candidato, re.DOTALL)
        if not m:
            continue
        for intento in (m.group(0), m.group(0).replace("'", '"')):
            try:
                return json.loads(intento)
            except Exception:
                continue
    return None


def estructura(core, sistema: str, usuario: str, tope: int = None,
               temperatura: float = 0.2, log=print):
    """Respuesta en JSON, ya parseada. `None` si no hubo manera.

    Dos intentos: el normal y otro diciéndole que conteste a bocajarro. Es más
    barato que perder el encargo entero, y con los modelos pequeños hace falta
    más a menudo de lo que parece.
    """
    tope = tope or MAX_TOKENS
    crudo = texto(core, sistema, usuario, tope=tope, temperatura=temperatura,
                  esfuerzo="low", log=log)
    datos = _rescatar_json(crudo)
    if datos is not None:
        return datos

    log("[PENSAR] Sin JSON legible; reintento pidiéndolo a bocajarro.")
    crudo = texto(core, sistema + "\n\nResponde SOLO con el JSON, sin razonar "
                                 "antes ni explicar nada después.",
                  usuario, tope=tope, temperatura=0.0, esfuerzo="none", log=log)
    return _rescatar_json(crudo)


def disponible(core) -> bool:
    try:
        _c, _m = _cliente(core)
        return True
    except Exception:
        return False
