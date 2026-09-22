#!/usr/bin/env python3
"""
relacion.py - Niveles de relación (idea 5 del IDEAS.MD)
======================================================
JARVIS no debería hablarle igual el primer día que el mes doce. Esto mantiene
un "estado de relación" que sube solo con el uso y ajusta el tono del cerebro
sin tocar el contenido de las respuestas.

Niveles (por número de interacciones y días desde la primera):

    1 conocimiento   formal y preciso, sin bromas
    2 comodidad      relajado, recuerda preferencias, humor suave
    3 confidente     cercano, referencias a lo ya vivido, más proactivo
    4 asesor         confianza plena, puede desafiar y reflexionar

Persistencia en user_prefs (core.get_pref/set_pref):
    rel_interacciones   contador
    rel_desde           fecha ISO de la primera vez
    rel_intimo          "1" si el señor ha compartido algo sensible

Nada de esto se inventa números: son umbrales fijos y explicables.
"""
import time

_UMBRALES = [
    # (nivel, nombre, min_interacciones, min_dias)
    (4, "asesor",       600, 120),
    (3, "confidente",   200, 30),
    (2, "comodidad",     25, 3),
    (1, "conocimiento",   0, 0),
]

_INSTRUCCION = {
    1: "Relación: reciente. Sé formal y preciso, trátalo de usted, sin bromas ni familiaridad.",
    2: "Relación: con rodaje. Puedes relajar el tono, recordar sus preferencias y usar humor suave.",
    3: "Relación: de confianza. Habla con cercanía, apóyate en lo ya vivido juntos y sé más proactivo.",
    4: "Relación: asesor de confianza. Confianza plena: puedes retarle intelectualmente, discrepar con "
       "argumentos y ofrecer reflexión, sin dejar de ser su mayordomo.",
}


def _num(v, defecto=0):
    try:
        return int(str(v).strip())
    except Exception:
        return defecto


def registrar_interaccion(core, texto_usuario: str = "", log=print):
    """Suma una interacción y marca intimidad si el señor comparte algo sensible."""
    try:
        n = _num(core.get_pref("rel_interacciones")) + 1
        core.set_pref("rel_interacciones", str(n))
        if not core.get_pref("rel_desde"):
            core.set_pref("rel_desde", time.strftime("%Y-%m-%d"))
        t = (texto_usuario or "").lower()
        if not core.get_pref("rel_intimo") and any(
            k in t for k in ("te confieso", "en secreto", "no se lo digas",
                             "me siento", "estoy pasando por", "mi contraseña",
                             "entre tú y yo", "nadie sabe")):
            core.set_pref("rel_intimo", "1")
    except Exception as e:
        log(f"[RELACION] no pude registrar: {e}")


def nivel(core) -> tuple[int, str]:
    try:
        n = _num(core.get_pref("rel_interacciones"))
        desde = core.get_pref("rel_desde") or time.strftime("%Y-%m-%d")
        dias = max(0, (time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
                       - time.mktime(time.strptime(desde, "%Y-%m-%d"))) / 86400)
        intimo = core.get_pref("rel_intimo") == "1"
    except Exception:
        return 1, "conocimiento"
    for niv, nombre, min_int, min_dias in _UMBRALES:
        if n >= min_int and dias >= min_dias:
            # La intimidad compartida sube un peldaño, pero nunca salta a asesor
            # sin el tiempo puesto.
            if intimo and niv < 3 and n >= 10:
                return 3, "confidente"
            return niv, nombre
    return 1, "conocimiento"


def instruccion_prompt(core) -> str:
    niv, _nombre = nivel(core)
    return _INSTRUCCION.get(niv, "")


def resumen(core) -> str:
    niv, nombre = nivel(core)
    n = _num(core.get_pref("rel_interacciones"))
    desde = core.get_pref("rel_desde") or "hoy"
    return (f"Señor, nuestra relación está en nivel {niv} ({nombre}): "
            f"{n} conversaciones desde {desde}.")
