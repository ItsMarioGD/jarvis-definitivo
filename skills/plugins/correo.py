#!/usr/bin/env python3
"""
skills/plugins/correo.py - Preguntar por el correo de viva voz
=============================================================
«¿tengo correos?», «léeme los correos sin leer», «resúmeme el correo».
Solo lectura. Enviar correo NO pasa por aquí: eso exige confirmación y va por
una herramienta explícita.
"""
from skills.plugins import SkillPlugin


class CorreoSkill:
    patterns = [
        r"\b(tengo|hay)\s+correos?\b",
        r"\bcorreos?\s+(sin\s+leer|nuevos|pendientes|importantes)\b",
        r"\b(l[eé]eme|revisa|resume|res[uú]meme|mira)\s+(mi\s+|el\s+|los\s+)?correos?\b",
        r"\bbandeja\s+de\s+entrada\b",
        r"\bgmail\b",
    ]
    priority = 20
    description = "Correo (Gmail): resumen de la bandeja sin leer"

    def handle(self, text: str, core) -> str | None:
        try:
            import correo_gmail
        except Exception:
            return None
        log = getattr(core, "log", print)
        return correo_gmail.resumen(log=log)


def register():
    return CorreoSkill()
