#!/usr/bin/env python3
"""
embeddings.py - Buscar por SIGNIFICADO, no por letras
=====================================================
`indice_documentos.py` tenía búsqueda semántica y se retiró cuando se fueron
los modelos que no eran de Anthropic. Desde entonces solo queda FTS5, que busca
**palabras**: si el apunte dice «tasa de variación instantánea» y el señor
pregunta «qué es una derivada», no encuentra nada. Con doscientos PDF de
carrera eso no es un buscador, es un archivador.

Aquí vuelve el motor, y con dos vías para no depender de una sola:

    Pollinations   `openai/text-embedding-3-small`, 1536 dimensiones.
                   Va por la misma clave que el cerebro. No hay que descargar
                   nada.
    Ollama         `nomic-embed-text` en casa, si el señor lo tiene bajado.
                   Funciona sin internet y sin gastar saldo.

Se elige solo: si hay clave de Pollinations, esa; si no, el de casa; si no hay
ninguno, se dice claramente y la búsqueda sigue funcionando por palabras, que
es peor pero no es nada.

Por qué no se guarda el modelo dentro de cada vector
-----------------------------------------------------
Sí se guarda, y es importante: dos motores distintos producen vectores que no
se pueden comparar entre sí (ni siquiera tienen el mismo número de
dimensiones). El índice apunta con qué motor se hizo cada uno, y si cambia, lo
dice en vez de devolver resultados sin sentido.
"""
import json
import math
import os
import urllib.error
import urllib.request

MODELO_NUBE = os.getenv("JARVIS_EMBED_MODELO", "").strip() or "openai/text-embedding-3-small"
MODELO_LOCAL = os.getenv("JARVIS_EMBED_LOCAL", "").strip() or "nomic-embed-text"

# Cuántos textos por petición. Ni uno (una llamada por trozo es eterno) ni
# quinientos (la petición se pasa de tamaño y el servidor la rechaza).
LOTE = int(os.getenv("JARVIS_EMBED_LOTE", "64"))


# ── qué motor hay ───────────────────────────────────────────────────────────
def _hay_nube() -> bool:
    try:
        import proveedor_pollinations as poll
        return poll.hay_clave()
    except Exception:
        return False


def _hay_local() -> bool:
    try:
        import cerebro_local as local
        return local.vivo() and MODELO_LOCAL in " ".join(local.modelos_instalados())
    except Exception:
        return False


def motor() -> str:
    """Identificador del motor en uso. Vacío si no hay ninguno."""
    forzado = (os.getenv("JARVIS_EMBED_MOTOR") or "").strip().lower()
    if forzado == "local" and _hay_local():
        return f"ollama:{MODELO_LOCAL}"
    if forzado == "nube" and _hay_nube():
        return f"pollinations:{MODELO_NUBE}"
    if _hay_nube():
        return f"pollinations:{MODELO_NUBE}"
    if _hay_local():
        return f"ollama:{MODELO_LOCAL}"
    return ""


def disponible() -> bool:
    return bool(motor())


def por_que_no() -> str:
    """Qué le falta al señor para tener búsqueda por significado."""
    if disponible():
        return ""
    return ("No hay motor de significado. Puede darle uno de dos formas:\n"
            "  · Ponga su clave de Pollinations en el .env "
            "(POLLINATIONS_API_KEY), que es lo más rápido.\n"
            f"  · O descárguese el de casa:  ollama pull {MODELO_LOCAL}")


# ── vectorizar ──────────────────────────────────────────────────────────────
def _nube(textos: list, log=print) -> list:
    import proveedor_pollinations as poll
    cuerpo = {"model": MODELO_NUBE, "input": textos}
    pet = urllib.request.Request(
        f"{poll.URL_CON_CLAVE}/embeddings", data=json.dumps(cuerpo).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {poll.clave()}"})
    with urllib.request.urlopen(pet, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    # El servidor puede devolverlos desordenados; `index` manda.
    datos = sorted(d.get("data") or [], key=lambda x: x.get("index", 0))
    return [x["embedding"] for x in datos]


def _local(textos: list, log=print) -> list:
    import cerebro_local as local
    raiz = local.URL.rstrip("/")
    if raiz.endswith("/v1"):
        raiz = raiz[:-3]
    salida = []
    for t in textos:
        pet = urllib.request.Request(
            f"{raiz}/api/embeddings",
            data=json.dumps({"model": MODELO_LOCAL, "prompt": t}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(pet, timeout=120) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        salida.append(d.get("embedding") or [])
    return salida


def vectorizar(textos, log=print) -> list:
    """Lista de vectores, uno por texto. Lista vacía si no hay motor.

    Nunca lanza: un fallo de red no puede tumbar un indexado de 800 archivos a
    la mitad. Devuelve lo que pudo y deja constancia en el registro.
    """
    if isinstance(textos, str):
        textos = [textos]
    textos = [t for t in textos if (t or "").strip()]
    if not textos or not disponible():
        return []

    usa_nube = motor().startswith("pollinations")
    salida = []
    for i in range(0, len(textos), LOTE):
        lote = textos[i:i + LOTE]
        try:
            salida += (_nube(lote, log=log) if usa_nube else _local(lote, log=log))
        except urllib.error.HTTPError as e:
            detalle = ""
            try:
                detalle = e.read().decode("utf-8", "replace")[:160]
            except Exception:
                pass
            log(f"[EMBED] HTTP {e.code} en el lote {i // LOTE + 1}: {detalle}")
            salida += [[] for _ in lote]
        except Exception as e:
            log(f"[EMBED] Falló el lote {i // LOTE + 1}: {type(e).__name__}: {e}")
            salida += [[] for _ in lote]
    return salida


def vectorizar_uno(texto: str, log=print) -> list:
    r = vectorizar([texto], log=log)
    return r[0] if r else []


# ── comparar ────────────────────────────────────────────────────────────────
def coseno(a, b) -> float:
    """Parecido entre dos vectores: 1 es lo mismo, 0 no tiene nada que ver."""
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)


def mas_parecidos(consulta_vec, candidatos, k: int = 5) -> list:
    """`candidatos` = [(identificador, vector), ...] -> los k más parecidos."""
    puntuados = [(ident, coseno(consulta_vec, vec))
                 for ident, vec in candidatos if vec]
    puntuados.sort(key=lambda x: -x[1])
    return puntuados[:k]


def estado() -> dict:
    return {"motor": motor(), "disponible": disponible(),
            "modelo_nube": MODELO_NUBE, "modelo_local": MODELO_LOCAL,
            "lote": LOTE}


def resumen() -> str:
    m = motor()
    if not m:
        return "Búsqueda por significado: APAGADA. " + por_que_no().split("\n")[0]
    donde = "en la nube" if m.startswith("pollinations") else "en casa"
    return f"Búsqueda por significado con «{m.split(':', 1)[1]}» ({donde})."


if __name__ == "__main__":
    try:
        import consola_utf8  # noqa: F401
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except Exception:
        pass
    print(resumen())
    if disponible():
        frases = ["la derivada mide la tasa de variación instantánea",
                  "el perro ladra en el jardín",
                  "pendiente de la recta tangente a una curva"]
        vs = vectorizar(frases)
        print(f"dimensiones: {len(vs[0])}")
        print(f"derivada vs tangente : {coseno(vs[0], vs[2]):.3f}  (deberían parecerse)")
        print(f"derivada vs perro    : {coseno(vs[0], vs[1]):.3f}  (no deberían)")
    else:
        print(por_que_no())
