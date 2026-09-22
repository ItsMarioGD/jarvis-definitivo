#!/usr/bin/env python3
"""
skills/plugins/navegador.py - Mandar en el navegador de viva voz
================================================================
«abre el navegador», «entra en ...», «qué hay en la pestaña», «en la web,
busca ... y dime ...», «ensaya en la web ...».

La tarea completa (`navegador_tarea`) es lenta y pulsa de verdad, así que por
voz sólo se atiende cuando el señor la pide con todas las letras («en la web»,
«en el navegador»). Lo demás —abrir y mirar— es inmediato y no toca nada.
"""
import re

from skills.plugins import SkillPlugin


class NavegadorSkill(SkillPlugin):
    patterns = [
        r"\babre\s+(el\s+)?navegador\b",
        r"\bcierra\s+(el\s+)?navegador\b",
        r"\bestado\s+del\s+navegador\b",
        r"\b(qu[eé]\s+hay|qu[eé]\s+pone|l[eé]eme)\s+(en\s+)?(la\s+)?(pesta[ñn]a|p[aá]gina)\b",
        # «entra en example.com», «ve a https://...», «vete a la web de ...».
        # Exige un punto y un dominio real, para no secuestrar «entra en la
        # carpeta de descargas».
        r"\b(entra|ve|vete|nav[eé]game)\s+(en|a)\s+(la\s+)?(web\b|p[aá]gina\b|"
        r"https?://|www\.|[\w-]+\.[a-z]{2,}\b)",
        r"\ben\s+(la\s+web|el\s+navegador)\b.{0,120}",
        r"\bensay[ao]\s+en\s+(la\s+web|el\s+navegador)\b",
        r"\b(qu[eé]\s+(est[aá]\s+)?(roto|fallando|mal)|diagnostica|revisa)\s+"
        r"(en\s+)?(la\s+|el\s+|mi\s+)?(web|p[aá]gina|sitio)\b",
        r"\b(datos|json|api)\s+de\s+(la\s+|esta\s+)?(p[aá]gina|web)\b",
    ]
    priority = 30
    description = "Navegador: abrir, mirar la pestaña y hacer tareas en la web"

    def handle(self, text: str, core) -> str | None:
        try:
            import navegador
        except Exception:
            return None
        log = getattr(core, "log", print)
        t = (text or "").strip()
        bajo = t.lower()

        if re.search(r"\bcierra\s+(el\s+)?navegador\b", bajo):
            navegador.obtener(log=log).cerrar()
            return "Navegador cerrado, señor."

        if re.search(r"\bestado\s+del\s+navegador\b", bajo):
            return navegador.estado(log=log)

        if re.search(r"\babre\s+(el\s+)?navegador\b", bajo):
            nav = navegador.obtener(log=log)
            ok, motivo = nav.arrancar()
            if not ok:
                return f"No pude abrirlo, señor: {motivo}."
            return f"Navegador listo, señor ({motivo}). Perfil propio, sus sesiones intactas."

        if re.search(r"\b(qu[eé]\s+hay|qu[eé]\s+pone|l[eé]eme)\s+(en\s+)?(la\s+)?(pesta[ñn]a|p[aá]gina)\b", bajo):
            return navegador.mirar(log=log)

        # «qué está roto en esta web», «diagnostica la página», «revisa el sitio»
        if re.search(r"\b(qu[eé]\s+(est[aá]\s+)?(roto|fallando|mal)|diagnostica|revisa)\s+"
                     r"(en\s+)?(la\s+|el\s+|mi\s+)?(web|p[aá]gina|sitio)\b", bajo):
            m = re.search(r"((?:https?://)?[\w-]+\.[a-z]{2,}(?:/\S*)?)", t, re.I)
            return navegador.diagnosticar(m.group(1) if m else "", log=log)

        # «los datos de la página», «el json de la web»
        if re.search(r"\b(datos|json|api)\s+de\s+(la\s+)?(p[aá]gina|web)\b", bajo):
            m = re.search(r"\bde\s+(?:la\s+)?(?:api|ruta)\s+(\S+)", t, re.I)
            return navegador.datos(m.group(1) if m else "", log=log)

        # «entra en example.com» / «ve a https://...»
        m = re.search(r"\b(?:entra|ve|vete|nav[eé]game)\s+(?:en|a)\s+(?:la\s+)?(?:web\s+|p[aá]gina\s+)?"
                      r"((?:https?://)?[\w.-]+\.[a-z]{2,}(?:/\S*)?)", t, re.I)
        if m:
            return navegador.abrir(m.group(1), log=log)

        # Ensayo: dice qué haría sin tocar nada.
        m = re.search(r"\bensay[ao]\s+en\s+(?:la\s+web|el\s+navegador)[,:]?\s*(.+)", t, re.I)
        if m:
            return navegador.navegar(m.group(1).strip(), core=core, seco=True, log=log)

        # Tarea completa: sólo si lo pide explícitamente.
        m = re.search(r"\ben\s+(?:la\s+web|el\s+navegador)[,:]?\s*(.+)", t, re.I)
        if m and len(m.group(1).strip()) > 8:
            return navegador.navegar(m.group(1).strip(), core=core, log=log)

        return None


def register():
    return NavegadorSkill()
