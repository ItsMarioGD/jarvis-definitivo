#!/usr/bin/env python3
"""
consejo.py - JARVIS contra ULTRON: deliberacion adversaria
==========================================================
El proyecto tiene algo que casi ningun asistente tiene: dos personalidades
opuestas corriendo sobre el mismo nucleo y con la misma memoria. Hasta ahora
eran dos productos separados que apenas se hablaban.

Aqui se les pone a discutir. Ante una decision con consecuencias:

    ULTRON  argumenta la via agresiva: velocidad, resultado, coste de no actuar.
    JARVIS  argumenta la prudente: riesgo, reversibilidad, coste de equivocarse.
    Sintesis: una recomendacion que ha tenido que sobrevivir a las dos.

Por que no basta con preguntarle una vez al modelo: un solo modelo tiende a
darte la razon. Dos con instrucciones contrarias sacan a la luz lo que uno solo
se salta, y ademas dejan ver el desacuerdo, que muchas veces es la informacion
util.

Funciona con el mismo Ollama local; son tres llamadas cortas, no tres modelos.
"""
import os

TEMPERATURA = float(os.getenv("JARVIS_CONSEJO_TEMPERATURA", "0.6"))
MAX_TOKENS = int(os.getenv("JARVIS_CONSEJO_TOKENS", "260"))

VOZ_ULTRON = (
    "Eres ULTRON. Defiendes la opción más decidida y rápida. Te importa el "
    "resultado y el coste de NO actuar. Eres frío, directo y no adornas. "
    "Responde en español, en 3 frases como máximo, sin listas."
)
VOZ_JARVIS = (
    "Eres JARVIS, mayordomo prudente. Defiendes la opción segura y reversible. "
    "Te importa qué pasa si sale mal y si se puede deshacer. Eres cortés y "
    "concreto. Responde en español, en 3 frases como máximo, sin listas."
)
VOZ_SINTESIS = (
    "Eres un árbitro imparcial. Te dan dos posturas opuestas sobre una misma "
    "decisión. Di en qué están de acuerdo, dónde está el desacuerdo real y "
    "cuál recomiendas, con una condición práctica que la haga segura. "
    "Responde en español, en 4 frases como máximo, sin listas."
)


def _preguntar(core, sistema: str, usuario: str, log=print) -> str:
    """Una llamada corta al modelo local con una personalidad concreta."""
    try:
        from openai import OpenAI
        nombre, url, modelo, clave = core._proveedores()[0]
        cliente = OpenAI(base_url=url, api_key=clave)
        resp = cliente.chat.completions.create(
            model=modelo,
            messages=[{"role": "system", "content": sistema},
                      {"role": "user", "content": usuario}],
            temperature=TEMPERATURA, max_tokens=MAX_TOKENS)
        texto = (resp.choices[0].message.content or "").strip()
        # Qwen mete su razonamiento entre <think>; aquí solo queremos la postura.
        if "</think>" in texto:
            texto = texto.split("</think>", 1)[1].strip()
        return texto
    except Exception as e:
        log(f"[CONSEJO] {sistema[:20]}… falló: {e}")
        return ""


def deliberar_estructurado(core, asunto: str, log=print) -> dict:
    """Las dos posturas y la sintesis por separado.

    La interfaz unificada las necesita sueltas para poder animarlas cada una en
    su lado; `deliberar()` las junta en texto para la voz y el chat de siempre.
    """
    if not asunto or len(asunto.strip()) < 5:
        return {"ok": False, "error": "¿Sobre qué quiere que delibere, señor?"}

    contexto = f"Decisión a tomar: {asunto.strip()}"
    ultron = _preguntar(core, VOZ_ULTRON, contexto, log=log)
    jarvis = _preguntar(core, VOZ_JARVIS, contexto, log=log)
    if not ultron and not jarvis:
        return {"ok": False, "error": "El cerebro no responde ahora mismo."}

    sintesis = ""
    if ultron and jarvis:
        sintesis = _preguntar(
            core, VOZ_SINTESIS,
            f"{contexto}\n\nPostura A (decidida): {ultron}\n"
            f"Postura B (prudente): {jarvis}", log=log)

    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "consejo", f"Deliberación: {asunto[:80]}",
            f"ULTRON: {ultron[:200]} | JARVIS: {jarvis[:200]}",
            gravedad="info", datos=sintesis[:400])
    except Exception:
        pass

    return {"ok": True, "asunto": asunto.strip(), "ultron": ultron,
            "jarvis": jarvis, "sintesis": sintesis,
            "desacuerdo": hay_desacuerdo(ultron, jarvis)}


def deliberar(core, asunto: str, log=print) -> str:
    """Somete una decisión a las dos personalidades y devuelve la síntesis."""
    if not asunto or len(asunto.strip()) < 5:
        return "¿Sobre qué quiere que delibere, señor?"

    contexto = f"Decisión a tomar: {asunto.strip()}"

    postura_ultron = _preguntar(core, VOZ_ULTRON, contexto, log=log)
    postura_jarvis = _preguntar(core, VOZ_JARVIS, contexto, log=log)

    if not postura_ultron and not postura_jarvis:
        return ("No pude convocar el consejo, señor: el cerebro no responde "
                "ahora mismo.")
    if not postura_ultron or not postura_jarvis:
        unica = postura_ultron or postura_jarvis
        return (f"Solo una de las dos voces respondió, señor. "
                f"Su postura: {unica}")

    sintesis = _preguntar(
        core, VOZ_SINTESIS,
        f"{contexto}\n\nPostura A (decidida): {postura_ultron}\n"
        f"Postura B (prudente): {postura_jarvis}", log=log)

    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "consejo", f"Deliberación: {asunto[:80]}",
            f"ULTRON: {postura_ultron[:200]} | JARVIS: {postura_jarvis[:200]}",
            gravedad="info", datos=sintesis[:400])
    except Exception:
        pass

    partes = [f"ULTRON dice: {postura_ultron}",
              f"JARVIS dice: {postura_jarvis}"]
    if sintesis:
        partes.append(f"Conclusión: {sintesis}")
    else:
        partes.append("No hubo síntesis; le dejo las dos posturas para que juzgue.")
    return "\n\n".join(partes)


# Formas de decir que no en la PRIMERA frase, que es donde cada voz se moja.
_RECHAZO = ("no lo hagas", "no borres", "no conviene", "no recomiendo",
            "no deberia", "no debería", "mejor no", "evita", "espera",
            "no procede", "no actues", "no actúes", "nunca")
_APROBACION = ("si.", "sí.", "hazlo", "adelante", "procede", "borra", "ejecuta",
               "actua ya", "actúa ya", "sin dudar")


def _postura_es_no(texto: str) -> bool:
    """¿Esta voz dice que NO? Solo mira la primera frase.

    Mirar el texto entero daba falsos negativos absurdos: «Sí. Borra la
    carpeta. No hay tiempo para dudas.» contiene «no» y se contaba como
    rechazo, con lo que un desacuerdo evidente se reportaba como acuerdo.
    """
    limpio = (texto or "").strip().lower()
    if not limpio:
        return False
    primera = limpio.split(".")[0] + "."
    if any(p in primera for p in _RECHAZO):
        return True
    if any(p in primera for p in _APROBACION):
        return False
    # Sin señal clara en la primera frase, se mira el arranque del párrafo.
    return any(p in limpio[:120] for p in _RECHAZO)


def hay_desacuerdo(postura_a: str, postura_b: str) -> bool:
    """¿Las dos posturas apuntan a lados contrarios?

    Sirve para decidir si merece la pena enseñar el debate o basta con la
    recomendación: cuando ambas coinciden, el debate solo es ruido.
    """
    return _postura_es_no(postura_a) != _postura_es_no(postura_b)
