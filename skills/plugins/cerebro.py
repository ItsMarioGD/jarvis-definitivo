#!/usr/bin/env python3
"""
skills/plugins/cerebro.py - Mandar sobre el cerebro de viva voz
===============================================================
«¿qué cerebro estás usando?», «cámbiate a pollinations», «usa el de casa»,
«prueba pollinations», «¿dónde pongo la clave?».

Cambiar de cerebro era editar `Prefs/cerebro.json` a mano y reiniciar. Aquí se
dice y ya está: se escribe la preferencia, se reordena la lista y la siguiente
frase ya sale por el cerebro nuevo.
"""
import os
import re

from skills.plugins import SkillPlugin


class CerebroSkill(SkillPlugin):
    patterns = [
        r"\b(qu[eé]|cu[aá]l)\s+cerebro\b",
        r"\bqu[eé]\s+modelo\s+(est[aá]s\s+)?(usando|us[aá]s)\b",
        r"\b(c[aá]mbiate|cambia|usa|p[aá]sate)\s+(?:a|al|el|la|con)?\s*(pollinations|"
        r"cerebro\s+de\s+casa|local|qwen|claude)\b",
        r"\bprueba\s+(a\s+)?pollinations\b",
        r"\b(d[oó]nde|c[oó]mo)\s+pongo\s+la\s+(clave|api\s*key)\b",
        r"\bclave\s+de\s+pollinations\b",
    ]
    priority = 40
    description = "Cerebro: qué modelo manda, cambiarlo y poner la clave"

    def handle(self, text: str, core) -> str | None:
        t = (text or "").strip()
        bajo = t.lower()
        log = getattr(core, "log", print)
        try:
            import proveedor_pollinations as poll
        except Exception:
            return None

        # ── dónde va la clave ───────────────────────────────────────────────
        if re.search(r"\b(d[oó]nde|c[oó]mo)\s+pongo\s+la\s+(clave|api\s*key)\b", bajo) \
                or re.search(r"\bclave\s+de\s+pollinations\b", bajo):
            if poll.hay_clave():
                return (f"Ya tiene la clave puesta, señor: nivel «{poll.nivel()}», "
                        f"una petición cada {poll.espera_entre_llamadas():.0f} "
                        "segundos. Si quiere cambiarla, está en el .env como "
                        "POLLINATIONS_API_KEY.")
            return poll.instrucciones_clave()

        # ── probar ──────────────────────────────────────────────────────────
        if re.search(r"\bprueba\s+(a\s+)?pollinations\b", bajo):
            r = poll.probar(log=log)
            if r.get("ok"):
                return (f"Pollinations responde en {r['segundos']} segundos con "
                        f"«{r['modelo']}», nivel {r['nivel']}, señor. "
                        f"Dijo: «{r['texto']}».")
            return f"Pollinations no responde, señor: {r.get('error', '')}"

        # ── cambiar ─────────────────────────────────────────────────────────
        m = re.search(r"\b(?:c[aá]mbiate|cambia|usa|p[aá]sate)\s+(?:a|al|el|la|con)?\s*"
                      r"(pollinations|cerebro\s+de\s+casa|local|qwen|claude)\b", bajo)
        if m:
            elegido = m.group(1)
            destino = ("pollinations" if "pollination" in elegido else
                       "claude" if "claude" in elegido else "local")
            if destino == "pollinations" and not poll.hay_clave():
                aviso = ("Aviso, señor: sin clave va el nivel anónimo, una "
                         "petición cada 15 segundos, y el bucle de herramientas "
                         "encadena hasta cuatro. Se le va a hacer eterno. ")
            else:
                aviso = ""
            os.environ["JARVIS_CEREBRO"] = destino
            try:
                core.set_pref("cerebro_preferido", destino)
            except Exception:
                pass
            # Releer la lista: el cambio vale para la siguiente frase.
            nuevo = ""
            try:
                core._cerebro = core._cerebro_leer()
                nuevo = (core._proveedores() or [("?",)])[0][0]
            except Exception as e:
                log(f"[CEREBRO] No pude recargar la lista: {e}")
            return (aviso + f"Hecho, señor: mando ahora por «{nuevo or destino}». "
                    "El cerebro de casa se queda de reserva por si no hay internet.")

        # ── qué cerebro manda ───────────────────────────────────────────────
        try:
            lista = core._proveedores() or []
        except Exception:
            lista = []
        if not lista:
            return "No tengo ningún cerebro configurado, señor."
        nombre, url, modelo, _clave = lista[0]
        cola = ", ".join(p[0] for p in lista[1:3])
        if poll.es_pollinations(url):
            detalle = (f" Nivel «{poll.nivel()}»"
                       + ("" if poll.hay_clave() else ", SIN clave: una petición "
                          "cada 15 segundos") + ".")
        elif "anthropic" in (url or ""):
            detalle = " Es la nube de Anthropic."
        else:
            detalle = " Es el de casa: gratis y sin internet."
        return (f"Estoy pensando con «{nombre}», señor.{detalle}"
                + (f" De reserva tengo {cola}." if cola else ""))


def register():
    return CerebroSkill()
