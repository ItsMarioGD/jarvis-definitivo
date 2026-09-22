#!/usr/bin/env python3
"""
skills/plugins/portal.py - El campus, de viva voz
=================================================
«configura mi portal en campus.uni.es», «mira el campus», «qué tengo que
entregar», «baja el material de cálculo», «pon las entregas en el calendario»,
«hazme un borrador de la práctica 2».

La entrega NO se envía nunca desde aquí: se prepara el borrador y el botón lo
pulsa el señor.
"""
import re

from skills.plugins import SkillPlugin


class PortalSkill(SkillPlugin):
    patterns = [
        r"\bconfigura\s+(mi\s+)?(portal|campus)\b",
        r"\b(mira|revisa|entra\s+en|abre)\s+(el\s+|mi\s+)?(campus|portal|aula\s+virtual)\b",
        r"\bqu[eé]\s+tengo\s+que\s+entregar\b",
        r"\b(entregas|tareas|deberes)\s+(pendientes|de\s+la\s+(uni|universidad))\b",
        r"\bmis\s+(asignaturas|cursos|materias)\b",
        r"\bbaja(me)?\s+(el\s+)?material\b",
        r"\bpon\s+(las\s+)?entregas\s+en\s+(el\s+)?calendario\b",
        r"\b(hazme|prepara|escribe)(me)?\s+(un\s+)?borrador\b",
    ]
    priority = 35
    description = "Campus virtual: cursos, entregas, material y borradores"

    def handle(self, text: str, core) -> str | None:
        try:
            import portal_academico as P
        except Exception:
            return None
        t = (text or "").strip()
        bajo = t.lower()
        log = getattr(core, "log", print)

        m = re.search(r"\bconfigura\s+(?:mi\s+)?(?:portal|campus)\s+"
                      r"(?:en\s+|con\s+)?((?:https?://)?[\w.-]+\.[a-z]{2,}(?:/\S*)?)",
                      t, re.I)
        if m:
            return P.configurar(m.group(1))
        if re.search(r"\bconfigura\s+(mi\s+)?(portal|campus)\b", bajo):
            return P.configurar()

        if re.search(r"\b(hazme|prepara|escribe)(me)?\s+(un\s+)?borrador\b", bajo):
            m = re.search(r"borrador\s+(?:de\s+|para\s+|sobre\s+)?(.+)", t, re.I)
            if not m:
                return ("¿Borrador de qué entrega, señor? Dígame «hazme un "
                        "borrador de la práctica 2».")
            return P.borrador(core, m.group(1).strip(" .?!"), log=log)

        if re.search(r"\bpon\s+(las\s+)?entregas\s+en\s+(el\s+)?calendario\b", bajo):
            return P.al_calendario(core, log=log)

        if re.search(r"\bbaja(me)?\s+(el\s+)?material\b", bajo):
            m = re.search(r"material\s+(?:de\s+|del\s+|de\s+la\s+)?(.+)", t, re.I)
            r = P.material(m.group(1).strip(" .?!") if m else "", log=log)
            return r.get("mensaje")

        if re.search(r"\bmis\s+(asignaturas|cursos|materias)\b", bajo):
            r = P.cursos(log=log)
            if not r.get("ok"):
                return r.get("mensaje")
            lista = r.get("cursos") or []
            if not lista:
                return r.get("mensaje")
            return (r["mensaje"] + "\n"
                    + "\n".join(f"  · {c['nombre']}" for c in lista[:15]))

        if re.search(r"\bqu[eé]\s+tengo\s+que\s+entregar\b", bajo) or \
                re.search(r"\b(entregas|tareas|deberes)\s+(pendientes|de\s+la\s+(uni|universidad))\b", bajo):
            return P.tareas(log=log).get("mensaje")

        if re.search(r"\b(mira|revisa|entra\s+en|abre)\s+(el\s+|mi\s+)?"
                     r"(campus|portal|aula\s+virtual)\b", bajo):
            r = P.entrar(log=log)
            if not r.get("ok"):
                return r.get("mensaje")
            return P.tareas(log=log).get("mensaje")

        return None


def register():
    return PortalSkill()
