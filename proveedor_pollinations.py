#!/usr/bin/env python3
"""
proveedor_pollinations.py - El cerebro de la nube que no pide tarjeta
=====================================================================
Anthropic se quedó sin saldo y JARVIS volvió a Qwen en casa. Qwen no cuesta
nada y funciona sin internet, pero el techo es el techo: 8B en una tarjeta de
6 GB, treinta segundos por paso y huecos en lo específico de carrera.

**Pollinations** es la tercera vía: pasarela abierta con endpoint compatible
con OpenAI, así que el cliente que el proyecto YA usa le habla sin traductor.

Dos endpoints, y confundirlos cuesta una tarde
----------------------------------------------
    https://gen.pollinations.ai/v1        el BUENO, con clave `sk_...`
    https://text.pollinations.ai/openai   el antiguo, anónimo

No es un detalle: con la clave del señor puesta, el antiguo seguía contestando
«tier: anonymous» y enseñando **un** modelo, como si no hubiera clave. El
nuevo, con la misma clave, da **241 modelos** —139 con herramientas, 95 con
ojos— y contextos de hasta 1,3 millones de tokens. La clave `sk_` es del portal
nuevo (enter.pollinations.ai) y el endpoint viejo sencillamente la ignora.

Así que aquí se elige solo:

    con clave   -> gen.pollinations.ai/v1, el catálogo entero
    sin clave   -> text.pollinations.ai/openai, un modelo y 15 s de espera

Autenticación
-------------
Cabecera `Authorization: Bearer <clave>`, que es justo lo que pone el cliente
de OpenAI con el `api_key`. O sea: **no hay que escribir código de auth**. La
clave se pone en el `.env`:

    POLLINATIONS_API_KEY=sk_...

y se consigue en https://enter.pollinations.ai

Qué NO hace
-----------
No guarda la clave en ningún sitio que no sea el `.env` del señor, y no la
manda a nadie más que a Pollinations. En `Prefs/cerebro.json` va por
referencia (`${POLLINATIONS_API_KEY}`), nunca escrita: ese fichero acaba en
capturas y copias de seguridad.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

def _env(nombre: str, por_defecto: str = "") -> str:
    """Variable de entorno, tratando «puesta pero vacía» como no puesta.

    `os.getenv("X", "algo")` con `X=` en el .env devuelve la cadena vacía, no
    «algo». Aquí eso dejó la URL en blanco y las llamadas se iban a ninguna
    parte con un 404 que no decía por qué. Una línea vacía en el .env significa
    «usa el valor por defecto», que es lo que cualquiera espera.
    """
    return (os.getenv(nombre) or "").strip() or por_defecto


# El de la clave y el anónimo. `url()` elige según haya clave o no.
URL_CON_CLAVE = _env("POLLINATIONS_URL", "https://gen.pollinations.ai/v1").rstrip("/")
URL_ANONIMA = "https://text.pollinations.ai/openai"
MODELO_ANONIMO = "openai-fast"

# Si el señor no elige, se escoge solo entre los que saben usar herramientas.
MODELO_POR_DEFECTO = _env("POLLINATIONS_MODELO")

_BASE = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS")
_CACHE = os.path.join(_BASE, "Prefs", "pollinations_modelos.json")

# Ritmo del nivel anónimo: una petición cada 15 s. Con clave no se limita desde
# aquí; manda el saldo de «pollen» de la cuenta.
_ESPERA_ANONIMA = 15.0

_candado = threading.Lock()
_ultima_llamada = 0.0
_nivel_visto = ""


# ── la clave ────────────────────────────────────────────────────────────────
def clave() -> str:
    """La clave del señor, si la puso. Se aceptan los tres nombres que ha ido
    usando la documentación, para no obligarle a adivinar cuál es."""
    for nombre in ("POLLINATIONS_API_KEY", "POLLINATIONS_TOKEN",
                   "POLLINATIONS_KEY"):
        v = (os.getenv(nombre) or "").strip()
        if v and not v.startswith("${"):
            return v
    return ""


def hay_clave() -> bool:
    return bool(clave())


def url() -> str:
    """El endpoint que toca. Con clave, el nuevo; sin ella, el anónimo."""
    return URL_CON_CLAVE if hay_clave() else URL_ANONIMA


def es_pollinations(u: str) -> bool:
    return "pollinations.ai" in (u or "").lower()


def _cabeceras() -> dict:
    cab = {"Content-Type": "application/json",
           "User-Agent": "JARVIS/1.0 (asistente personal)"}
    c = clave()
    if c:
        cab["Authorization"] = f"Bearer {c}"
    return cab


# ── catálogo de modelos ─────────────────────────────────────────────────────
def _url_modelos() -> str:
    return (f"{URL_CON_CLAVE}/models" if hay_clave()
            else "https://text.pollinations.ai/models")


def modelos(refrescar: bool = False, log=print) -> list:
    """Los modelos que TU clave alcanza.

    La caché se guarda junto con si había clave al pedirla: si no, el listado
    de un arranque sin clave (un modelo) se quedaba pegado y el señor no veía
    los 241 después de ponerla.
    """
    marca = "con_clave" if hay_clave() else "anonimo"
    if not refrescar:
        try:
            with open(_CACHE, encoding="utf-8") as f:
                guardado = json.load(f)
            if (guardado.get("modelos") and guardado.get("marca") == marca
                    and time.time() - guardado.get("t", 0) < 86400):
                return guardado["modelos"]
        except Exception:
            pass

    try:
        pet = urllib.request.Request(_url_modelos(), headers=_cabeceras())
        with urllib.request.urlopen(pet, timeout=25) as r:
            crudo = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        log(f"[POLLINATIONS] No pude listar modelos: {e}")
        try:
            with open(_CACHE, encoding="utf-8") as f:
                return json.load(f).get("modelos") or []
        except Exception:
            return []

    lista = crudo.get("data") if isinstance(crudo, dict) else crudo
    salida = []
    for m in (lista or []):
        if isinstance(m, str):
            salida.append({"nombre": m, "titulo": m, "descripcion": "",
                           "herramientas": False, "vision": False,
                           "contexto": 0, "precio": 0.0, "comunidad": False})
            continue
        if not isinstance(m, dict):
            continue
        nombre = m.get("id") or m.get("name") or ""
        if not nombre:
            continue
        try:
            precio = float((m.get("pricing") or {}).get("promptTextTokens") or 0)
        except Exception:
            precio = 0.0
        salida.append({
            "nombre": nombre,
            "titulo": m.get("title") or nombre,
            "descripcion": (m.get("description") or "")[:110],
            "herramientas": bool(m.get("tools")),
            "vision": "image" in (m.get("input_modalities") or []),
            "razona": bool(m.get("reasoning")),
            "contexto": int(m.get("context_length") or 0),
            "precio": precio,
            # Los `community/*` los sube cualquiera: sirven, pero no se eligen
            # solos como cerebro principal del señor.
            "comunidad": bool(m.get("community")) or nombre.startswith("community/"),
        })

    try:
        os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
        with open(_CACHE, "w", encoding="utf-8") as f:
            json.dump({"t": time.time(), "marca": marca, "modelos": salida}, f,
                      ensure_ascii=False, indent=1)
    except Exception:
        pass
    return salida


def _puntuar(m: dict) -> tuple:
    """Orden de preferencia para el cerebro de diario.

    El primer intento ordenaba por precio y elegía `nova-micro`: el más barato
    del catálogo y un modelo flojo. Para una carrera eso es el criterio
    equivocado. Ahora manda la CAPACIDAD y el precio solo desempata:

      1. herramientas   sin ellas JARVIS habla pero no actúa
      2. no comunidad   los `community/*` los sube cualquiera
      3. que razone     es lo que separa explicar de repetir
      4. que vea        pantalla, fotos y el escáner, con el mismo modelo
      5. contexto util  256k basta y sobra; más no se paga
      6. precio         ya solo entre los que cumplen lo de arriba
    """
    contexto = m.get("contexto") or 0
    return (
        0 if m.get("herramientas") else 1,
        1 if m.get("comunidad") else 0,
        0 if m.get("razona") else 1,
        0 if m.get("vision") else 1,
        0 if contexto >= 200000 else 1,
        m.get("precio") or 0.0,
        -contexto,
    )


def mejor_modelo(log=print) -> str:
    """El mejor que la clave alcance, y que sepa usar HERRAMIENTAS."""
    pedido = _env("POLLINATIONS_MODELO")
    if pedido:
        return pedido
    if not hay_clave():
        return MODELO_ANONIMO
    lista = [m for m in modelos(log=log) if m.get("herramientas")]
    if not lista:
        return MODELO_ANONIMO
    return sorted(lista, key=_puntuar)[0]["nombre"]


def modelo_vision(log=print) -> str:
    """El que además VE imágenes: pantalla, fotos y el escáner."""
    pedido = _env("POLLINATIONS_MODELO_VISION")
    if pedido:
        return pedido
    lista = [m for m in modelos(log=log) if m.get("vision") and m.get("herramientas")]
    if not lista:
        lista = [m for m in modelos(log=log) if m.get("vision")]
    return sorted(lista, key=_puntuar)[0]["nombre"] if lista else ""


def catalogo(filtro: str = "", tope: int = 20, log=print) -> str:
    """El catálogo en texto, para decirlo en voz alta o leerlo."""
    lista = modelos(log=log)
    if filtro:
        f = filtro.lower()
        lista = [m for m in lista
                 if f in m["nombre"].lower() or f in m["titulo"].lower()]
    if not lista:
        return "No tengo modelos que enseñarle, señor."
    lista = sorted(lista, key=_puntuar)[:tope]
    filas = []
    for m in lista:
        marcas = []
        if m.get("herramientas"):
            marcas.append("herramientas")
        if m.get("vision"):
            marcas.append("ojos")
        if m.get("razona"):
            marcas.append("razona")
        ctx = f"{m['contexto'] // 1000}k" if m.get("contexto") else "—"
        filas.append(f"  {m['nombre']:40} ctx {ctx:>6}  {', '.join(marcas)}")
    return "\n".join(filas)


# ── ritmo ───────────────────────────────────────────────────────────────────
def nivel() -> str:
    if _nivel_visto:
        return _nivel_visto
    return "con clave" if hay_clave() else "anonymous"


def espera_entre_llamadas() -> float:
    """Con clave, el ritmo lo marca el saldo, no un reloj. Sin ella, 15 s."""
    return 0.0 if hay_clave() else _ESPERA_ANONIMA


def esperar_turno():
    global _ultima_llamada
    hueco = espera_entre_llamadas()
    if hueco <= 0:
        return
    with _candado:
        falta = hueco - (time.time() - _ultima_llamada)
        if falta > 0:
            time.sleep(min(falta, hueco))
        _ultima_llamada = time.time()


def anotar_respuesta(respuesta) -> None:
    """El endpoint antiguo dice el nivel en cada respuesta (`user_tier`)."""
    global _nivel_visto
    try:
        visto = getattr(respuesta, "user_tier", None)
        if visto is None and isinstance(respuesta, dict):
            visto = respuesta.get("user_tier")
        if visto:
            _nivel_visto = str(visto)
    except Exception:
        pass


# ── comprobación directa ────────────────────────────────────────────────────
def probar(mensaje: str = "Contesta solo con la palabra: funciona",
           modelo: str = "", log=print) -> dict:
    """Una llamada de verdad, para saber si esto está vivo y a qué velocidad."""
    modelo = modelo or mejor_modelo(log=log)
    destino = (f"{URL_CON_CLAVE}/chat/completions" if hay_clave() else URL_ANONIMA)
    cuerpo = {"model": modelo, "max_tokens": 60,
              "messages": [{"role": "user", "content": mensaje}]}
    pet = urllib.request.Request(destino, data=json.dumps(cuerpo).encode(),
                                 headers=_cabeceras())
    esperar_turno()
    t0 = time.time()
    try:
        with urllib.request.urlopen(pet, timeout=120) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        if e.code == 429:
            return {"ok": False, "codigo": 429, "modelo": modelo,
                    "error": ("Va demasiado rápido para el nivel anónimo. "
                              "Con clave desaparece ese límite.")}
        if e.code in (401, 403):
            return {"ok": False, "codigo": e.code, "modelo": modelo,
                    "error": ("La clave no vale o no llega a ese modelo. "
                              "Compruébela en https://enter.pollinations.ai")}
        if e.code == 402:
            return {"ok": False, "codigo": 402, "modelo": modelo,
                    "error": "Sin saldo de «pollen» en la cuenta."}
        return {"ok": False, "codigo": e.code, "modelo": modelo,
                "error": f"HTTP {e.code}: {detalle}"}
    except Exception as e:
        return {"ok": False, "codigo": 0, "modelo": modelo,
                "error": f"{type(e).__name__}: {e}"}

    anotar_respuesta(d)
    texto = ""
    try:
        texto = (d["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        pass
    return {"ok": True, "modelo": d.get("model") or modelo, "texto": texto[:200],
            "segundos": round(time.time() - t0, 2),
            "nivel": d.get("user_tier") or nivel(),
            "tokens": (d.get("usage") or {}).get("total_tokens", 0)}


# ── lo que el núcleo necesita ───────────────────────────────────────────────
def proveedores(log=print) -> list:
    """Las entradas para Prefs/cerebro.json, de más listo a reserva.

    La clave va como `${POLLINATIONS_API_KEY}` y no con su valor dentro: ese
    fichero se comparte en capturas y copias, y una clave escrita ahí es una
    clave filtrada.
    """
    modelo = mejor_modelo(log=log)
    return [{"nombre": f"pollinations:{modelo}", "url": url(), "modelo": modelo,
             "clave": "${POLLINATIONS_API_KEY}"}]


def estado(log=print) -> dict:
    lista = modelos(log=log)
    return {"url": url(), "clave": hay_clave(), "nivel": nivel(),
            "modelo": mejor_modelo(log=log), "modelo_vision": modelo_vision(log=log),
            "modelos": len(lista),
            "con_herramientas": sum(1 for m in lista if m.get("herramientas")),
            "con_vision": sum(1 for m in lista if m.get("vision")),
            "espera_s": espera_entre_llamadas()}


def resumen(log=print) -> str:
    e = estado(log=log)
    if not e["modelos"]:
        return "Pollinations — no he podido hablar con el servicio. ¿Hay internet?"
    if not e["clave"]:
        return ("Pollinations SIN clave: un solo modelo y una petición cada 15 "
                "segundos, que para el bucle de herramientas se queda corto. "
                "Ponga la clave y pasa a tener el catálogo entero.")
    return (f"Pollinations con su clave. {e['modelos']} modelos "
            f"({e['con_herramientas']} con herramientas, {e['con_vision']} con "
            f"ojos). Pienso con «{e['modelo']}»"
            + (f" y veo con «{e['modelo_vision']}»." if e["modelo_vision"] else "."))


def instrucciones_clave() -> str:
    return (
        "Para poner su clave de Pollinations, señor:\n"
        "  1. Consíguela en https://enter.pollinations.ai (empieza por «sk_»)\n"
        "  2. Abra el archivo .env de la carpeta de JARVIS y péguela en:\n"
        "       POLLINATIONS_API_KEY=\n"
        "  3. Reinicie JARVIS. Yo solo la leo de ahí; no la guardo en ningún\n"
        "     otro sitio ni se la mando a nadie más que a Pollinations.\n"
        "Sin clave también funciona, pero con un solo modelo y a una petición\n"
        "cada 15 segundos.")


if __name__ == "__main__":
    try:
        import consola_utf8  # noqa: F401
    except Exception:
        pass
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except Exception:
        pass
    print(resumen())
    print()
    print(catalogo(tope=12))
    print()
    r = probar()
    print("prueba:", r)
    if not hay_clave():
        print()
        print(instrucciones_clave())
