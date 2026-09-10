#!/usr/bin/env python3
"""
router_modelo.py - DRÁSTICO #7: el modelo enruta, no 360 regex
============================================================
`jarvis_skills.py` decide qué hacer con una cascada de ~360 regex en un orden
frágil. Esto pone al modelo delante como router, con dos trucos para que no
cueste latencia:

  * **Caché**: cada frase normalizada guarda su decisión en disco. La segunda
    vez que se dice algo parecido, cero llamadas al modelo.
  * **Las regex siguen de red**: si el router no está seguro, se cae al flujo
    de siempre. No se borra nada todavía; se invierte quién manda.

El router devuelve una de estas decisiones:

    {"tipo": "skill", "frase": "baja el volumen"}   -> se despacha esa frase
    {"tipo": "conversacion"}                         -> saltar skills, ir al LLM
    {"tipo": "herramienta"}                          -> ir al bucle de tools
    {"tipo": "?"}                                    -> no sé, sigue como siempre

Se activa con JARVIS_ROUTER_MODELO=1.
"""
import json
import os
import re
import time
import unicodedata

_CACHE = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs",
                      "router_cache.json")
_mem = None

_SISTEMA = (
    "Eres el router de un asistente. Clasificas UNA frase del usuario. Responde "
    "SOLO con JSON, sin nada más:\n"
    '{"tipo":"skill","frase":"<orden reformulada en imperativo simple>"}  si es una '
    "orden concreta al PC/casa/agenda (abrir/cerrar apps, volumen, brillo, "
    "notas, alarmas, temporizadores, clima, captura, bloquear, apagar, "
    "recordatorios, música, agenda);\n"
    '{"tipo":"herramienta"}  si pide una acción que requiere varios pasos, '
    "ficheros, git, correo, web o razonar y actuar;\n"
    '{"tipo":"conversacion"}  si es charla, preguntas de conocimiento, '
    "opiniones, saludos o dictado libre;\n"
    '{"tipo":"?"}  si dudas.\n'
    "La frase reformulada de 'skill' debe ser corta y directa, como la diría "
    "alguien mandando: «sube el volumen», «pon una alarma a las 7», «abre chrome»."
)


def activo() -> bool:
    return os.getenv("JARVIS_ROUTER_MODELO", "0") == "1"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", "", s)).strip()


def _cache_load() -> dict:
    global _mem
    if _mem is not None:
        return _mem
    try:
        with open(_CACHE, encoding="utf-8") as f:
            _mem = json.load(f)
    except Exception:
        _mem = {}
    return _mem


def _cache_save():
    try:
        os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
        # Cota: nos quedamos con las 2000 entradas más recientes.
        if len(_mem) > 2000:
            recientes = sorted(_mem.items(), key=lambda kv: kv[1].get("t", 0))[-2000:]
            _mem.clear()
            _mem.update(dict(recientes))
        with open(_CACHE, "w", encoding="utf-8") as f:
            json.dump(_mem, f, ensure_ascii=False)
    except Exception:
        pass


def enrutar(core, texto: str, log=print) -> dict:
    if not activo() or not (texto or "").strip():
        return {"tipo": "?"}
    clave = _norm(texto)
    if len(clave) < 3:
        return {"tipo": "?"}
    cache = _cache_load()
    hit = cache.get(clave)
    if hit:
        return {k: v for k, v in hit.items() if k != "t"}

    try:
        from openai import OpenAI
        nombre, url, modelo, cl = core._proveedores()[0]
        # Router: pesetero. No gasta presupuesto si la nube está cortada.
        if not (("localhost" in url) or ("127.0.0.1" in url)):
            try:
                import presupuesto
                if not presupuesto.permite_nube():
                    return {"tipo": "?"}
            except Exception:
                pass
        cli = OpenAI(base_url=url, api_key=cl)
        r = cli.chat.completions.create(
            model=modelo, temperature=0, max_tokens=120,
            messages=[{"role": "system", "content": _SISTEMA},
                      {"role": "user", "content": texto[:400]}])
        crudo = (r.choices[0].message.content or "").strip()
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        dec = json.loads(m.group(0)) if m else {"tipo": "?"}
        if dec.get("tipo") not in ("skill", "herramienta", "conversacion", "?"):
            dec = {"tipo": "?"}
        if dec.get("tipo") != "?":
            cache[clave] = {**dec, "t": time.time()}
            _cache_save()
        log(f"[ROUTER] «{texto[:40]}» -> {dec}")
        return dec
    except Exception as e:
        log(f"[ROUTER] falló ({str(e)[:80]}); sigo como siempre")
        return {"tipo": "?"}


def estado() -> dict:
    c = _cache_load()
    tipos = {}
    for v in c.values():
        tipos[v.get("tipo", "?")] = tipos.get(v.get("tipo", "?"), 0) + 1
    return {"activo": activo(), "en_cache": len(c), "por_tipo": tipos}


def limpiar_cache() -> str:
    global _mem
    _mem = {}
    try:
        os.remove(_CACHE)
    except OSError:
        pass
    return "Caché del router vaciada, señor."
