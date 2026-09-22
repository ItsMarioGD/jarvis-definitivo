#!/usr/bin/env python3
"""
skills/plugins/llegada.py - «Jarvis, papá llegó»
================================================
La frase de llegada del señor. No es un saludo de cortesía: es el interruptor
general. Al oírla, el asistente saluda y **enciende todo lo que estaba
apagado**, cada cosa por su cuenta y sin que un fallo tumbe a los demás:

    escucha continua   el micrófono queda atento sin pulsar nada
    motor proactivo    vuelve a vigilar batería, disco, agenda y seguridad
    observador         ojos en la pantalla, para ofrecerse si hay un atasco
    vigilante          el perro guardián del propio asistente
    luces              la habitación, si hay domótica configurada

Lo que ya estaba en marcha no se reinicia: se informa y punto. Y si algo no se
puede encender (sin micrófono, sin domótica), se dice cuál y por qué, en vez de
fingir que todo fue bien.

La palabra de activación la pone `jarvis_escucha.py`, así que basta con decirlo
en alto: «Jarvis, papá llegó».
"""
import re
import time

from skills.plugins import SkillPlugin

# «papá llegó», «ya llegué», «llegó papá», «he llegado», con y sin tildes.
#
# El `$` del final no es adorno: sin él, «mi papá llegó tarde ayer» —contar algo,
# no anunciarse— encendía la casa entera. La frase de llegada es la frase
# COMPLETA, no una que aparezca dentro de otra.
_LLEGADA = re.compile(
    r"\b(pap[aá]\s+lleg[oó]|lleg[oó]\s+pap[aá]|ya\s+lleg[uú]e|ya\s+estoy\s+(aqu[ií]|en\s+casa)|"
    r"he\s+llegado|estoy\s+de\s+vuelta|(ya\s+)?vuelvo\s+a\s+casa)"
    r"\s*[!¡.,]*\s*$", re.I)


def _saludo(core) -> str:
    """Saludo según la hora y según quién conteste."""
    hora = time.localtime().tm_hour
    if hora < 6:
        momento = "Buenas noches"
    elif hora < 13:
        momento = "Buenos días"
    elif hora < 21:
        momento = "Buenas tardes"
    else:
        momento = "Buenas noches"
    if getattr(core, "nombre_agente", "JARVIS") == "ULTRON":
        return f"{momento}. Ha vuelto. Levanto todos los sistemas."
    return f"{momento}, señor. Bienvenido a casa. Lo enciendo todo."


class LlegadaSkill(SkillPlugin):
    patterns = [
        r"\bpap[aá]\s+lleg[oó]\b",
        r"\blleg[oó]\s+pap[aá]\b",
        r"\bya\s+lleg[uú]e\b",
        r"\bya\s+estoy\s+(aqu[ií]|en\s+casa)\b",
        r"\bhe\s+llegado\b",
        r"\bestoy\s+de\s+vuelta\b",
    ]
    priority = 90          # antes que casi todo: es una frase inconfundible
    description = "Llegada del señor: saluda y enciende todos los sistemas"

    def handle(self, text: str, core) -> str | None:
        if not _LLEGADA.search(text or ""):
            return None

        encendidos, ya_estaban, fallaron = [], [], []

        def _intentar(nombre, funcion):
            """Cada sistema por su cuenta: uno caído no tumba a los demás."""
            try:
                estado = funcion()
            except Exception as e:
                fallaron.append(f"{nombre} ({type(e).__name__})")
                return
            if estado is True:
                encendidos.append(nombre)
            elif estado is None:
                ya_estaban.append(nombre)
            else:
                fallaron.append(f"{nombre} ({estado})")

        _intentar("la escucha continua", lambda: _escucha(core))
        _intentar("el motor proactivo", lambda: _proactivo(core))
        _intentar("los ojos en la pantalla", lambda: _observador(core))
        _intentar("el vigilante", lambda: _vigilante(core))
        _intentar("las luces", lambda: _luces(core))

        partes = [_saludo(core)]
        if encendidos:
            partes.append("He encendido " + _lista(encendidos) + ".")
        if ya_estaban:
            partes.append(("Ya estaba" if len(ya_estaban) == 1 else "Ya estaban")
                          + " en marcha " + _lista(ya_estaban) + ".")
        if fallaron:
            partes.append("No he podido con " + _lista(fallaron) + ".")
        if not (encendidos or ya_estaban or fallaron):
            partes.append("No tengo ningún sistema que encender.")
        return " ".join(partes)


def _lista(cosas: list) -> str:
    """«a, b y c», que es como se dice en voz alta."""
    if len(cosas) == 1:
        return cosas[0]
    return ", ".join(cosas[:-1]) + " y " + cosas[-1]


# ── cada sistema: True encendido, None ya estaba, texto = motivo del fallo ──
def _escucha(core):
    esc = getattr(core, "escucha", None)
    if esc is None:
        return "no hay micrófono configurado"
    try:
        if esc.estado().get("activa"):
            return None
    except Exception:
        pass
    ok, motivo = esc.start()
    if ok:
        try:
            core.set_pref("escucha_continua", "1")
        except Exception:
            pass
        return True
    return motivo or "no arrancó"


def _proactivo(core):
    if getattr(core, "proactivo", None) is not None:
        return None
    from jarvis_proactive import ProactiveEngine
    core.proactivo = ProactiveEngine(core, log=getattr(core, "log", print))
    core.proactivo.start()
    return True


def _observador(core):
    import observador
    if getattr(core, "observador", None) is None:
        core.observador = observador.Observador(core, log=getattr(core, "log", print))
    try:
        if core.observador.estado().get("activo"):
            return None
    except Exception:
        pass
    ok, motivo = core.observador.disponible()
    if not ok:
        return motivo
    # start() devuelve la frase para la voz; el estado es quien dice la verdad.
    core.observador.start()
    return True if core.observador.estado().get("activo") else "no llegó a arrancar"


def _vigilante(core):
    vig = getattr(core, "vigilante", None)
    if vig is None:
        return "no está montado"
    if vig.estado().get("vigilando"):
        return None
    vig.start()
    return True if vig.estado().get("vigilando") else "no llegó a arrancar"


def _luces(core):
    """Solo si hay domótica de verdad. En modo seguro, ni se intenta."""
    skills = getattr(core, "skills", None)
    if skills is None or not hasattr(skills, "_prender_apagar_habitacion"):
        return "no hay domótica"
    if getattr(skills, "safe", False):
        return "el modo seguro está puesto"
    if not (skills._domo_leer() or {}).get("broker"):
        return "no hay domótica configurada"
    skills._prender_apagar_habitacion(True)
    return True


def register():
    return LlegadaSkill()
