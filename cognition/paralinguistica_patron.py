#!/usr/bin/env python3
"""
cognition/paralinguistica_patron.py - Memoria temporal del estado del señor
=========================================================================
La idea 3 del IDEAS.MD pedia un modelo TinyML de estres/fatiga. El modelo
supervisado sigue pendiente (no hay datos etiquetados del señor), pero SI se
puede hacer lo que de verdad daba valor: el **feedback loop temporal**.

    "Suele estar tenso los martes a las 4 de la tarde"

Aqui se guarda cada lectura paralinguistica con su hora y dia de la semana, y
se ofrece un *prior* por franja horaria. `mezclar()` combina la lectura del
momento con ese prior, con peso proporcional a cuantas muestras hay: al
principio manda la lectura; con historial, el patron corrige el ruido de una
sola frase.

`corregir()` deja que el señor ajuste ("no estoy cansado"): baja el prior de
esa franja para que no vuelva a insistir.

Todo en un JSON rodante (ultimas 3000 muestras) en Prefs/. Nada sale del
equipo.
"""
import json
import os
import time

_ARCHIVO = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs",
                        "paralinguistica_patron.json")
_MAX = 3000
_MIN_MUESTRAS_FRANJA = 4

_cache = None


def _cargar() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    d = {"muestras": [], "correcciones": {}}
    try:
        with open(_ARCHIVO, encoding="utf-8") as f:
            d = json.load(f) or d
    except Exception:
        pass
    _cache = d
    return d


def _guardar():
    try:
        os.makedirs(os.path.dirname(_ARCHIVO), exist_ok=True)
        with open(_ARCHIVO, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
    except Exception:
        pass


def _franja(ts=None) -> str:
    t = time.localtime(ts or time.time())
    # dia_de_semana + bloque de 2 horas: 24 franjas/dia -> 168/semana.
    return f"{t.tm_wday}-{t.tm_hour // 2}"


def registrar(estres: float, fatiga: float, arousal: float, valencia: float,
              confianza: float, log=print):
    """Apunta una lectura. Nunca falla."""
    try:
        d = _cargar()
        d["muestras"].append({
            "ts": int(time.time()), "f": _franja(),
            "e": round(float(estres), 3), "fa": round(float(fatiga), 3),
            "a": round(float(arousal), 3), "v": round(float(valencia), 3),
            "c": round(float(confianza), 3),
        })
        if len(d["muestras"]) > _MAX:
            d["muestras"] = d["muestras"][-_MAX:]
        _guardar()
    except Exception as e:
        log(f"[PARALING-PATRON] no pude registrar: {e}")


def prior(ts=None) -> dict | None:
    """Media de estres/fatiga de esta franja horaria en el historial."""
    d = _cargar()
    f = _franja(ts)
    xs = [m for m in d["muestras"] if m.get("f") == f]
    if len(xs) < _MIN_MUESTRAS_FRANJA:
        return None
    n = len(xs)
    p = {
        "estres": sum(m["e"] for m in xs) / n,
        "fatiga": sum(m["fa"] for m in xs) / n,
        "arousal": sum(m["a"] for m in xs) / n,
        "valencia": sum(m["v"] for m in xs) / n,
        "n": n,
    }
    corr = d["correcciones"].get(f)
    if corr:
        p["estres"] = max(0.0, p["estres"] + corr.get("estres", 0.0))
        p["fatiga"] = max(0.0, p["fatiga"] + corr.get("fatiga", 0.0))
    return p


def mezclar(estres, fatiga, arousal, valencia, confianza, log=print) -> dict:
    """Devuelve la lectura ya combinada con el patron temporal + registra."""
    registrar(estres, fatiga, arousal, valencia, confianza, log=log)
    p = prior()
    if not p:
        return {"estres": estres, "fatiga": fatiga, "arousal": arousal,
                "valencia": valencia, "confianza": confianza, "patron": False}
    # Peso del prior: crece con las muestras, tope 0.5. Una frase nunca pesa
    # menos que el historial entero, pero el historial la suaviza.
    w = min(0.5, p["n"] / 40.0)
    mix = lambda ahora, hist: round((1 - w) * ahora + w * hist, 3)
    return {
        "estres": mix(estres, p["estres"]),
        "fatiga": mix(fatiga, p["fatiga"]),
        "arousal": mix(arousal, p["arousal"]),
        "valencia": mix(valencia, p["valencia"]),
        "confianza": round(min(1.0, confianza + 0.15), 3),  # el patron da respaldo
        "patron": True, "muestras_franja": p["n"],
    }


def corregir(campo: str, direccion: str = "menos", log=print) -> str:
    """El señor ajusta: «no estoy cansado» -> baja el prior de fatiga de esta franja."""
    campo = "fatiga" if campo.startswith("fatig") or campo.startswith("cansad") else "estres"
    delta = -0.15 if direccion == "menos" else 0.15
    try:
        d = _cargar()
        f = _franja()
        c = d["correcciones"].setdefault(f, {})
        c[campo] = round(max(-0.6, min(0.6, c.get(campo, 0.0) + delta)), 3)
        _guardar()
        return (f"Anotado, señor: ajusto mi lectura de {campo} para esta franja "
                f"({'a la baja' if delta < 0 else 'al alza'}).")
    except Exception as e:
        log(f"[PARALING-PATRON] corregir: {e}")
        return "No pude anotar la corrección, señor."


def resumen(log=print) -> str:
    d = _cargar()
    if not d["muestras"]:
        return "Aún no tengo lecturas de su voz, señor."
    p = prior()
    if not p:
        return (f"Tengo {len(d['muestras'])} lecturas de su voz, pero pocas en "
                "esta franja para ver un patrón.")
    return (f"En esta franja horaria, señor, su voz suele marcar "
            f"estrés {p['estres']:.0%} y fatiga {p['fatiga']:.0%} "
            f"({p['n']} lecturas).")
