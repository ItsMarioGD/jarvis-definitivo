#!/usr/bin/env python3
"""
skills/plugins/estudiar.py - Estudiar de viva voz
=================================================
«hazme tarjetas de derivadas», «pregúntame», «cómo voy», «hazme el informe de
la práctica 3», «descompón 100 newtons a 30 grados», «dibuja estas fuerzas».

El repaso funciona por turnos: JARVIS pregunta, el señor contesta en la frase
siguiente y JARVIS corrige. Por eso hace falta recordar cuál era la pregunta
entre un turno y el otro, y eso vive aquí.
"""
import re

from skills.plugins import SkillPlugin


class EstudiarSkill(SkillPlugin):
    patterns = [
        r"\b(hazme|prepara|saca|crea)(me)?\s+(unas?\s+)?(tarjetas|fichas)\b",
        r"\bpreg[uú]ntame\b",
        r"\b(rep[aá]same|repasar|repaso)\b",
        r"\b(c[oó]mo\s+voy|qu[eé]\s+tal\s+voy|mis\s+tarjetas)\b",
        r"\bolvida\s+(las\s+)?tarjetas\b",
        r"\b(hazme|prepara|escribe)(me)?\s+(el\s+|un\s+)?informe\b",
        r"\bmis\s+informes\b",
        r"\bdescomp[oó]n\w*\b",
        r"\b(dibuja|pinta)\w*\s+(las\s+|estas\s+)?fuerzas\b",
        r"\b(resultante|equilibrio)\s+de\s+(las\s+)?fuerzas\b",
        r"\bmomento\s+de\s+(una\s+)?fuerza\b",
        r"\bviga\s+(apoyada|de)\b",
        # La respuesta al repaso necesita un disparador explícito: el registro
        # de plugins solo entrega la frase si encaja con un patrón, así que una
        # respuesta libre («es la pendiente de la tangente») no llegaría nunca
        # hasta aquí. Por eso se contesta con «respondo …».
        r"^\s*(respondo|mi\s+respuesta|la\s+respuesta\s+es|contesto)\b",
        r"^\s*(no\s+lo\s+s[eé]|ni\s+idea|paso)\s*$",
    ]
    priority = 34
    description = "Estudio: tarjetas, repaso, informes, vectores y estática"

    # Qué pregunta está en el aire, para poder corregir la respuesta siguiente.
    _en_el_aire = {}

    def handle(self, text: str, core) -> str | None:
        t = (text or "").strip()
        bajo = t.lower()
        log = getattr(core, "log", print)

        # ── tarjetas y repaso ───────────────────────────────────────────────
        m = re.search(r"\b(?:hazme|prepara|saca|crea)(?:me)?\s+(?:unas?\s+)?"
                      r"(?:tarjetas|fichas)\s+(?:de\s+|sobre\s+)?(.+)", t, re.I)
        if m:
            import estudio
            return estudio.crear(core, m.group(1).strip(" .?!"), log=log)

        if re.search(r"\bolvida\s+(las\s+)?tarjetas\b", bajo):
            import estudio
            m = re.search(r"tarjetas\s+(?:de\s+|sobre\s+)?(.+)", t, re.I)
            return estudio.olvidar(m.group(1).strip(" .?!") if m else "")

        if re.search(r"\b(c[oó]mo\s+voy|qu[eé]\s+tal\s+voy|mis\s+tarjetas)\b", bajo):
            import estudio
            return estudio.resumen()

        if re.search(r"\bpreg[uú]ntame\b", bajo) or \
                re.search(r"\b(rep[aá]same|repasar|repaso)\b", bajo):
            import estudio
            m = re.search(r"(?:de|sobre)\s+(.+)", t, re.I)
            s = estudio.siguiente(m.group(1).strip(" .?!") if m else "")
            if s.get("hay"):
                self._en_el_aire[id(core)] = s["id"]
                return (s["mensaje"] + "\n\n(Conteste con «respondo …», o "
                        "«no lo sé» si no le sale.)")
            return s.get("mensaje")

        # ── informes ────────────────────────────────────────────────────────
        if re.search(r"\bmis\s+informes\b", bajo):
            import informe
            return informe.listar()

        m = re.search(r"\b(?:hazme|prepara|escribe)(?:me)?\s+(?:el\s+|un\s+)?informe"
                      r"\s+(?:de\s+|sobre\s+|para\s+)?(.+)", t, re.I)
        if m:
            import informe
            return informe.redactar(core, m.group(1).strip(" .?!"),
                                    log=log).get("mensaje")

        # ── vectores y estática ─────────────────────────────────────────────
        m = re.search(r"\bdescomp[oó]n\w*\s+(?:una\s+fuerza\s+de\s+)?"
                      r"(-?\d+(?:[.,]\d+)?)\s*(?:N|newtons?)?\s*"
                      r"(?:a|en|con)\s+(-?\d+(?:[.,]\d+)?)", t, re.I)
        if m:
            import vectores
            mag = float(m.group(1).replace(",", "."))
            ang = float(m.group(2).replace(",", "."))
            return "\n".join(vectores.descomponer(mag, ang)["pasos"])

        if re.search(r"\bviga\s+(apoyada|de)\b", bajo):
            import vectores
            nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", t)]
            if len(nums) < 3:
                return ("Dígame la longitud y las cargas, señor: «viga de 6 "
                        "metros con 1000 newtons a 2 metros».")
            largo, resto = nums[0], nums[1:]
            # Los números van en pares (carga, posición) o (posición, carga);
            # se toma el orden en que se dicta: «1000 newtons a 2 metros».
            cargas = [(resto[i + 1], resto[i]) for i in range(0, len(resto) - 1, 2)]
            return "\n".join(vectores.viga(largo, cargas)["pasos"])

        if re.search(r"\b(dibuja|pinta)\w*\s+(las\s+|estas\s+)?fuerzas\b", bajo) or \
                re.search(r"\b(resultante|equilibrio)\s+de\s+(las\s+)?fuerzas\b", bajo):
            import vectores
            grupos = re.findall(r"\(?\s*(-?\d+(?:\.\d+)?)[,\s]+(-?\d+(?:\.\d+)?)"
                                r"(?:[,\s]+(-?\d+(?:\.\d+)?))?\s*\)?", t)
            if not grupos:
                return ("Dígame las fuerzas, señor: «dibuja las fuerzas "
                        "(100, 0, 0) y (0, 80, 0)».")
            fuerzas = [[float(a), float(b), float(c) if c else 0.0]
                       for a, b, c in grupos]
            if re.search(r"\bdibuja|pinta\b", bajo):
                r = vectores.dibujar(fuerzas, log=log)
                return "\n".join(r.get("pasos") or []) + "\n(Abierto en el navegador.)"
            return "\n".join(vectores.equilibrio(fuerzas)["pasos"])

        # ── la respuesta a la pregunta que estaba en el aire ────────────────
        m = re.match(r"^\s*(?:respondo|mi\s+respuesta(?:\s+es)?|"
                     r"la\s+respuesta\s+es|contesto)\s*:?\s*(.+)", t, re.I)
        rendido = re.match(r"^\s*(?:no\s+lo\s+s[eé]|ni\s+idea|paso)\s*$", t, re.I)
        if m or rendido:
            import estudio
            pendiente = self._en_el_aire.pop(id(core), None)
            if not pendiente:
                return ("No le había preguntado nada todavía, señor. Dígame "
                        "«pregúntame» y empezamos.")
            if rendido:
                r = {"nota": "fallo", "comentario": ""}
                estudio.calificar(pendiente, "fallo")
                correcta = next((c["respuesta"] for c in estudio.pendientes(limite=50)
                                 if c["id"] == pendiente), "")
                r["comentario"] = f"La respuesta era: {correcta}" if correcta else ""
            else:
                r = estudio.corregir(core, pendiente, m.group(1).strip(), log=log)
            cabecera = {"fallo": "No es eso, señor.", "regular": "Casi, señor.",
                        "bien": "Correcto, señor.", "facil": "Perfecto, señor."}
            siguiente = estudio.siguiente()
            cola = ""
            if siguiente.get("hay"):
                self._en_el_aire[id(core)] = siguiente["id"]
                cola = f"\n\nSiguiente: {siguiente['mensaje']}"
            else:
                cola = "\n\n" + siguiente.get("mensaje", "")
            return f"{cabecera.get(r['nota'], '')} {r['comentario']}".strip() + cola

        return None


def register():
    return EstudiarSkill()
