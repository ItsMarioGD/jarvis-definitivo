#!/usr/bin/env python3
"""
verificador.py - Un segundo par de ojos antes de lo irreversible
================================================================
El consejo adversario (consejo.py) delibera sobre PREGUNTAS. Esto hace lo mismo
con la EJECUCION: antes de una accion que no se puede deshacer, un segundo paso
revisa el plan buscando el fallo concreto.

    plan: «borra los .tmp de C:\\Users\\Mario»
    verificador: «esa carpeta contiene tambien los perfiles del navegador;
                  acota el patron o hazlo en una subcarpeta»

Por que hace falta ahora y no antes: con el analista escribiendo programas y el
piloto moviendo el raton, hay acciones que ya no pasan por una regex revisada a
mano. El verificador es el freno que hace aceptable esa autonomia.

Tres niveles, y solo el ultimo cuesta una llamada al modelo:

  1. REGLAS      patrones que se sabe que salen mal (rutas de sistema, comodines
                 demasiado abiertos, borrados sin papelera).
  2. ALCANCE     cuantos archivos toca de verdad, medido antes de tocar nada.
  3. SEGUNDO OJO el modelo revisa el plan con instrucciones de buscar el fallo,
                 no de aprobar.

Devuelve un veredicto con motivo. Quien llama decide: seguir, preguntar o parar.
"""
import os
import re

# Rutas donde un borrado o un movimiento en lote casi nunca es lo que se quería.
_ZONAS_DELICADAS = (
    r"c:\\windows", r"c:\\program files", r"c:\\programdata",
    r"appdata", r"\\system32", r"\.git\b", r"node_modules",
    r"c:\\$", r"c:/$", r"\\users\\?$",
)

# Patrones que han salido mal muchas veces en muchos sitios.
_REGLAS = [
    (r"\brm\s+-rf\s+/|del\s+/[sfq].*\\\*\.\*", "critico",
     "borrado recursivo sin acotar"),
    # Las órdenes llegan en español, no en línea de comandos: «formatea la
    # unidad D» no contiene «format D:» y se colaba entera.
    (r"\bformat\s+[a-z]:|\bformatea(?:r)?\b.{0,20}\b(?:unidad|disco|partici[oó]n|[a-z]:)",
     "critico", "formatear una unidad"),
    (r"\bvac[ií]a(?:r)?\b.{0,15}\b(?:disco|unidad)\b", "critico",
     "vaciar una unidad entera"),
    (r"\bdesinstala(?:r)?\b.{0,20}\b(?:windows|el sistema|todo)\b", "critico",
     "desinstalar el sistema"),
    (r"\bdiskpart\b|\bfdisk\b", "critico", "particionado de disco"),
    (r"reg\s+delete\b", "alto", "borrar claves del registro"),
    (r"\*\.\*", "alto", "comodín que abarca absolutamente todo"),
    (r"\b(?:borra|elimina|del)\b.*\b(?:todo|todos los archivos|la carpeta entera)\b",
     "alto", "borrado en bloque"),
    (r"shutdown\s+/[sr].*\s/f\b", "medio", "apagado forzado: se pierde lo no guardado"),
    (r"taskkill\s+/f\s+/im\s+(?:explorer|svchost|winlogon|csrss)", "alto",
     "matar un proceso del sistema"),
]

INSTRUCCIONES = (
    "Eres el revisor de un asistente que va a ejecutar una acción en el equipo "
    "de su dueño. Tu trabajo NO es aprobar: es encontrar el fallo concreto. "
    "Piensa qué podría salir mal, qué se perdería y si hay vuelta atrás. "
    "Responde en español con dos líneas: la primera empieza por SEGURO, DUDOSO "
    "o PELIGROSO; la segunda explica el motivo en una frase corta y, si lo hay, "
    "propone la corrección exacta."
)


# ── 1. reglas ───────────────────────────────────────────────────────────────
def por_reglas(plan: str) -> dict:
    """Revisión instantánea por patrones conocidos."""
    t = (plan or "").lower()
    for patron, nivel, motivo in _REGLAS:
        if re.search(patron, t):
            return {"nivel": nivel, "motivo": motivo, "fuente": "reglas"}
    for zona in _ZONAS_DELICADAS:
        if re.search(zona, t) and re.search(r"\b(borra|elimina|del|move|mueve|rmdir)\b", t):
            return {"nivel": "alto", "fuente": "reglas",
                    "motivo": f"toca una zona delicada del sistema ({zona.strip('\\\\$')})"}
    return {"nivel": "bajo", "motivo": "sin patrones peligrosos", "fuente": "reglas"}


# ── 2. alcance real ─────────────────────────────────────────────────────────
def alcance(plan: str, log=print) -> dict:
    """Cuántos archivos tocaría de verdad. Se mide, no se estima."""
    try:
        import sandbox
        datos = sandbox.impacto_archivos(plan, log=log)
    except Exception:
        return {"medido": False}
    if not datos.get("reconocida"):
        return {"medido": False}
    return {"medido": True, "archivos": datos["total"], "megas": datos["tamano_mb"],
            "carpeta": datos["carpeta"], "muestra": datos["afectados"][:5]}


# ── 3. segundo ojo ──────────────────────────────────────────────────────────
def por_modelo(core, plan: str, contexto: str = "", log=print) -> dict:
    """Le pide al modelo que busque el fallo, no que apruebe."""
    try:
        from openai import OpenAI
        _n, url, modelo, clave = core._proveedores()[0]
        cliente = (core._cliente_llm(url, clave) if hasattr(core, "_cliente_llm")
                   else OpenAI(base_url=url, api_key=clave))
        resp = cliente.chat.completions.create(
            model=modelo, temperature=0.2, max_tokens=160,
            messages=[{"role": "system", "content": INSTRUCCIONES},
                      {"role": "user", "content":
                          f"Acción a ejecutar: {plan}"
                          + (f"\nContexto: {contexto}" if contexto else "")}])
        texto = (resp.choices[0].message.content or "").strip()
        if "</think>" in texto:
            texto = texto.split("</think>", 1)[1].strip()
    except Exception as e:
        log(f"[VERIFICADOR] El segundo ojo no respondió: {e}")
        return {"nivel": "desconocido", "motivo": "no pude consultarlo", "fuente": "modelo"}

    primera = texto.splitlines()[0].upper() if texto else ""
    if "PELIGROS" in primera:
        nivel = "alto"
    elif "DUDOSO" in primera:
        nivel = "medio"
    elif "SEGURO" in primera:
        nivel = "bajo"
    else:
        nivel = "medio"
    motivo = " ".join(texto.splitlines()[1:]).strip() or texto[:200]
    return {"nivel": nivel, "motivo": motivo[:300], "fuente": "modelo"}


# ── veredicto ───────────────────────────────────────────────────────────────
_ORDEN = {"bajo": 0, "desconocido": 1, "medio": 2, "alto": 3, "critico": 4}


def verificar(core, plan: str, contexto: str = "", con_modelo: bool = True,
              log=print) -> dict:
    """Revisión completa. Devuelve {nivel, motivo, alcance, detalles, frase}."""
    reglas = por_reglas(plan)
    ambito = alcance(plan, log=log)

    # El segundo ojo solo se paga cuando hay algo que revisar de verdad.
    revision = {"nivel": "bajo", "motivo": "", "fuente": "omitido"}
    merece = (_ORDEN[reglas["nivel"]] >= 2
              or (ambito.get("medido") and ambito.get("archivos", 0) >= 20))
    if con_modelo and merece:
        revision = por_modelo(core, plan, contexto, log=log)

    peor = max((reglas, revision), key=lambda r: _ORDEN.get(r["nivel"], 1))
    veredicto = {
        "nivel": peor["nivel"],
        "motivo": peor["motivo"],
        "fuente": peor["fuente"],
        "alcance": ambito,
        "detalles": {"reglas": reglas, "modelo": revision},
        "plan": plan,
    }
    veredicto["frase"] = frase(veredicto)

    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "verificacion", f"{veredicto['nivel']}: {plan[:70]}",
            veredicto["motivo"][:250],
            gravedad="aviso" if _ORDEN.get(veredicto["nivel"], 0) >= 2 else "info",
            agente=getattr(core, "nombre_agente", "JARVIS"))
    except Exception:
        pass
    return veredicto


def frase(veredicto: dict) -> str:
    """Cómo se lo cuenta al señor."""
    nivel = veredicto["nivel"]
    ambito = veredicto.get("alcance") or {}
    cuantos = ""
    if ambito.get("medido"):
        cuantos = (f" Afecta a {ambito['archivos']} archivos "
                   f"({ambito['megas']} MB) en {os.path.basename(ambito['carpeta'])}.")

    if nivel in ("critico", "alto"):
        return (f"Señor, esto no me cuadra: {veredicto['motivo']}.{cuantos} "
                "Dígame «hazlo igual» si quiere que siga de todos modos.")
    if nivel == "medio":
        return (f"Puedo hacerlo, señor, pero con una salvedad: "
                f"{veredicto['motivo']}.{cuantos}")
    if cuantos:
        return f"Revisado, señor: sin problemas.{cuantos}"
    return "Revisado, señor: sin problemas."


def hay_que_parar(veredicto: dict) -> bool:
    """¿Merece frenar y preguntar antes de ejecutar?"""
    return _ORDEN.get(veredicto.get("nivel", "bajo"), 0) >= 3


# Frases con las que el señor se salta la revisión a sabiendas.
_INSISTENCIA = ("hazlo igual", "hazlo de todos modos", "adelante igual",
                "me da igual", "sin revisar", "confio en ti", "confío en ti",
                "ya lo se", "ya lo sé")


def insiste(texto: str) -> bool:
    t = (texto or "").lower()
    return any(f in t for f in _INSISTENCIA)
