#!/usr/bin/env python3
"""
metricas.py - Donde se van los segundos y el credito
====================================================
«Va lento» no se arregla sin saber en que etapa se pierde el tiempo, y el
credito de ElevenLabs se agota sin previo aviso (ya paso: un 402 y a la voz de
Windows). Aqui se mide lo que importa y se guarda con el resto del registro:

    escucha   cuanto tarda el dictado (local o en la nube)
    cerebro   cuanto tarda el modelo en responder, y cuantos tokens salen
    voz       cuanto tarda en hablar, y por que proveedor
    total     de que el señor termina de hablar a que JARVIS empieza

Se usa como cronometro de contexto:

    with metricas.medir("cerebro", modelo="claude-opus-5"):
        respuesta = llamar_al_modelo()

El informe responde a la pregunta util: «¿por que tarda?», con la mediana y el
peor caso de cada etapa, no con una media que esconde los picos.
"""
import os
import threading
import time
from collections import defaultdict, deque

MAX_MUESTRAS = int(os.getenv("JARVIS_METRICAS_MUESTRAS", "200"))

# Precio orientativo de ElevenLabs por caracter (plan Creator, 2025). Solo
# sirve para dar una idea del gasto; el numero exacto lo manda la factura.
COSTE_POR_CARACTER = float(os.getenv("JARVIS_ELEVENLABS_COSTE", "0.00003"))

_lock = threading.RLock()
_muestras = defaultdict(lambda: deque(maxlen=MAX_MUESTRAS))
_contadores = defaultdict(float)


class medir:
    """Cronómetro de contexto: with medir("cerebro"): ..."""

    def __init__(self, etapa: str, **extra):
        self.etapa = etapa
        self.extra = extra
        self.inicio = 0.0

    def __enter__(self):
        self.inicio = time.time()
        return self

    def __exit__(self, *_excepcion):
        anotar(self.etapa, (time.time() - self.inicio) * 1000, **self.extra)
        return False


def anotar(etapa: str, ms: float, **extra):
    """Guarda una medición. Nunca falla: medir no puede romper lo medido."""
    try:
        with _lock:
            _muestras[etapa].append({"ms": round(float(ms), 1),
                                     "ts": time.time(), **extra})
    except Exception:
        pass


def contar(clave: str, cantidad: float = 1.0):
    """Contadores acumulados: caracteres hablados, tokens, llamadas."""
    with _lock:
        _contadores[clave] += cantidad


def anotar_cerebro(proveedor: str, modelo: str, respuesta, log=print):
    """Cuántos tokens ha gastado cada cerebro, y si salieron del equipo.

    No se traduce a dinero a propósito. ElevenLabs cobra por carácter y ahí una
    estimación vale; Pollinations cobra en «pollen» y Anthropic en dólares con
    precios distintos por modelo, así que una cifra inventada en euros daría
    una falsa sensación de saber lo que se gasta. Lo que sí se puede decir con
    certeza es cuántos tokens han salido del equipo y por dónde.
    """
    try:
        uso = getattr(respuesta, "usage", None)
        if uso is None and isinstance(respuesta, dict):
            uso = respuesta.get("usage")
        if not uso:
            return
        entrada = int(getattr(uso, "prompt_tokens", 0)
                      or (uso.get("prompt_tokens", 0) if isinstance(uso, dict) else 0))
        salida = int(getattr(uso, "completion_tokens", 0)
                     or (uso.get("completion_tokens", 0) if isinstance(uso, dict) else 0))
    except Exception:
        return

    # `base_url` del cliente de OpenAI no es una cadena, es un objeto URL: sin
    # convertirlo, el `in` lanzaba TypeError y el contador se quedaba mudo
    # justo donde nadie lo mira.
    donde_str = str(proveedor or "")
    local = "localhost" in donde_str or "127.0.0.1" in donde_str
    donde = "casa" if local else "nube"
    contar(f"tokens_{donde}_entrada", entrada)
    contar(f"tokens_{donde}_salida", salida)
    contar(f"llamadas_{donde}", 1)
    contar(f"tokens_modelo::{modelo or '?'}", entrada + salida)


def caracteres_hablados(texto: str, proveedor: str = "elevenlabs"):
    """Registra el gasto de voz: es el único que cuesta dinero de verdad."""
    if proveedor == "elevenlabs":
        contar("caracteres_elevenlabs", len(texto or ""))
    contar(f"frases_{proveedor}", 1)


# ── lectura ─────────────────────────────────────────────────────────────────
def _percentil(valores, p: float):
    if not valores:
        return 0.0
    orden = sorted(valores)
    indice = min(int(len(orden) * p), len(orden) - 1)
    return orden[indice]


def resumen() -> dict:
    with _lock:
        etapas = {}
        for etapa, muestras in _muestras.items():
            valores = [m["ms"] for m in muestras]
            if not valores:
                continue
            etapas[etapa] = {
                "veces": len(valores),
                "mediana_ms": round(_percentil(valores, 0.5)),
                "p90_ms": round(_percentil(valores, 0.9)),
                "peor_ms": round(max(valores)),
            }
        contadores = dict(_contadores)

    caracteres = contadores.get("caracteres_elevenlabs", 0)
    return {
        "etapas": etapas,
        "contadores": contadores,
        "coste_voz_estimado_usd": round(caracteres * COSTE_POR_CARACTER, 3),
        "caracteres_elevenlabs": int(caracteres),
    }


def informe() -> str:
    """Respuesta hablada a «¿por qué tardas?»."""
    datos = resumen()
    if not datos["etapas"]:
        return "Todavía no tengo mediciones, señor. Hábleme un par de veces y le digo."

    partes = []
    for etapa, m in sorted(datos["etapas"].items(),
                           key=lambda x: -x[1]["mediana_ms"]):
        partes.append(f"{etapa}: {m['mediana_ms']} ms de mediana "
                      f"(peor {m['peor_ms']} ms, {m['veces']} veces)")

    coste = datos["coste_voz_estimado_usd"]
    cola = ""
    if datos["caracteres_elevenlabs"]:
        cola = (f" He gastado {datos['caracteres_elevenlabs']} caracteres de voz "
                f"en la nube, unos {coste:.2f} dólares estimados.")

    # Dónde ha pensado. Lo importante no es el dinero —que cada proveedor cobra
    # en su moneda— sino cuánto ha salido del equipo.
    c = datos["contadores"]
    nube = int(c.get("tokens_nube_entrada", 0) + c.get("tokens_nube_salida", 0))
    casa = int(c.get("tokens_casa_entrada", 0) + c.get("tokens_casa_salida", 0))
    if nube or casa:
        total = nube + casa
        cola += (f" De {total} tokens pensados, {casa} se quedaron en el equipo "
                 f"y {nube} salieron a la nube "
                 f"({100 * casa // max(total, 1)} % en casa).")
    return "Dónde se va el tiempo, señor — " + "; ".join(partes) + "." + cola


def cuello_de_botella() -> str:
    """La etapa que más pesa, para poder atacarla."""
    datos = resumen()["etapas"]
    if not datos:
        return ""
    etapa, m = max(datos.items(), key=lambda x: x[1]["mediana_ms"])
    consejos = {
        "escucha": "pruebe un modelo de dictado más pequeño (JARVIS_WHISPER_MODELO=tiny)",
        "cerebro": "un modelo más pequeño o menos contexto acortarían esto",
        "voz": "la voz local (Piper) responde antes que ElevenLabs",
        "herramientas": "cada herramienta encadenada suma una llamada al modelo",
    }
    return (f"Lo que más tarda es «{etapa}» ({m['mediana_ms']} ms de mediana). "
            + consejos.get(etapa, ""))


def reiniciar():
    with _lock:
        _muestras.clear()
        _contadores.clear()


def volcar_a_registro(log=print):
    """Deja una foto de las métricas en el almacén (para el parte diario)."""
    try:
        import json
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "metricas", "Rendimiento", informe()[:400], gravedad="info",
            datos=json.dumps(resumen(), ensure_ascii=False)[:900])
    except Exception as e:
        log(f"[METRICAS] No pude registrar: {e}")
