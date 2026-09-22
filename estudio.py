#!/usr/bin/env python3
"""
estudio.py - Que te pregunte él a ti
====================================
Tener los apuntes indexados sirve para consultarlos. No sirve para
aprendértelos: releer da la sensación de saber y es de las peores formas de
estudiar que se han medido. Lo que funciona es lo contrario —que te pregunten y
tengas que sacarlo tú— y espaciado en el tiempo.

Eso es esto:

    tarjetas    JARVIS lee un tema de TUS apuntes y saca las preguntas
    repaso      te pregunta las que tocan hoy, no todas
    calendario  cada acierto aleja la siguiente vez; cada fallo la acerca

El intervalo va por un SM-2 recortado, que es el algoritmo de toda la vida de
Anki, sin la parte que nadie ajusta nunca:

    fallo      vuelve mañana y se reinicia la racha
    regular    el mismo intervalo otra vez
    bien       intervalo x factor de facilidad
    fácil      intervalo x factor x 1,3, y el factor sube

Las preguntas salen de los apuntes del señor, no de lo que el modelo recuerde.
Si no hay apuntes de ese tema, se dice — inventar preguntas de un temario que
no se ha visto es la forma más rápida de estudiar lo que no entra.

Todo en `~/Descargas/JARVIS/Estudio/tarjetas.db`.
"""
import json
import os
import re
import sqlite3
import threading
import time

_BASE = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Estudio")
DB = os.path.join(_BASE, "tarjetas.db")

# SM-2 recortado. El factor arranca en 2,5 y no baja de 1,3: por debajo de ahí
# una tarjeta se pregunta a diario para siempre y acabas odiándola.
FACTOR_INICIAL = 2.5
FACTOR_MINIMO = 1.3

_lock = threading.RLock()


def _con():
    os.makedirs(_BASE, exist_ok=True)
    con = sqlite3.connect(DB, check_same_thread=False, timeout=15)
    con.execute("""CREATE TABLE IF NOT EXISTS tarjetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tema TEXT, pregunta TEXT, respuesta TEXT, fuente TEXT,
        creada REAL, proxima REAL, intervalo REAL, factor REAL,
        aciertos INTEGER DEFAULT 0, fallos INTEGER DEFAULT 0,
        UNIQUE(tema, pregunta))""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_proxima ON tarjetas(proxima)")
    con.commit()
    return con


# ── crear tarjetas desde los apuntes ────────────────────────────────────────
_PROMPT = """Eres un profesor preparando tarjetas de estudio para un alumno de
ingeniería. Te doy fragmentos de SUS PROPIOS APUNTES sobre un tema.

Saca entre 5 y 12 tarjetas. Responde SOLO con un JSON, sin nada más:

{"tarjetas": [{"pregunta": "...", "respuesta": "..."}, ...]}

Reglas:
- Las preguntas y respuestas salen SOLO de los fragmentos. No añadas nada que
  no esté ahí, por muy seguro que estés.
- Pregunta por lo que hay que SABER HACER o ENTENDER, no por detalles sueltos.
- Una idea por tarjeta. Respuestas de una o dos frases.
- Nada de preguntas de sí o no.
- Si un fragmento trae una fórmula, haz una tarjeta que la pida.

Tema: {tema}
"""


def crear(core, tema: str, log=print) -> str:
    """Saca tarjetas de los apuntes del señor sobre un tema."""
    tema = (tema or "").strip()
    if not tema:
        return "¿De qué tema, señor?"

    try:
        import indice_documentos
        trozos = indice_documentos.buscar(tema, k=6, log=log)
    except Exception as e:
        return f"No pude leer sus apuntes, señor: {e}"
    if not trozos:
        return (f"No encuentro nada sobre «{tema}» en sus apuntes, señor. "
                "Indexe primero la carpeta donde estén («indexa mis "
                "documentos») o dígame otro tema.")

    contexto = "\n\n".join(f"[{os.path.basename(r)}]\n{t[:1200]}"
                           for r, t, _p in trozos)
    fuentes = sorted({os.path.basename(r) for r, _t, _p in trozos})

    import pensar
    datos = pensar.estructura(core, _PROMPT.replace("{tema}", tema), contexto,
                              tope=4000, log=log)
    nuevas = (datos or {}).get("tarjetas") or []
    if not nuevas:
        return ("El cerebro no devolvió tarjetas que pueda guardar, señor. "
                "Pruebe otra vez o con un tema más concreto.")

    ahora = time.time()
    puestas = repetidas = 0
    with _lock:
        con = _con()
        try:
            for t in nuevas:
                p = str(t.get("pregunta") or "").strip()
                resp = str(t.get("respuesta") or "").strip()
                if not p or not resp:
                    continue
                try:
                    con.execute(
                        "INSERT INTO tarjetas (tema, pregunta, respuesta, fuente, "
                        "creada, proxima, intervalo, factor) VALUES (?,?,?,?,?,?,?,?)",
                        (tema, p, resp, ", ".join(fuentes), ahora, ahora, 0.0,
                         FACTOR_INICIAL))
                    puestas += 1
                except sqlite3.IntegrityError:
                    repetidas += 1
            con.commit()
        finally:
            con.close()

    parte = f"{puestas} tarjetas nuevas de «{tema}», señor."
    if repetidas:
        parte += f" {repetidas} ya las tenía."
    return parte + f" Salen de {', '.join(fuentes)}. Dígame «pregúntame» cuando quiera."


def _leer_json(texto: str):
    if not texto:
        return None
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ── repasar ─────────────────────────────────────────────────────────────────
def pendientes(tema: str = "", limite: int = 20) -> list:
    """Las que tocan hoy. No todas: en eso consiste el repaso espaciado."""
    ahora = time.time()
    with _lock:
        con = _con()
        try:
            if tema:
                filas = con.execute(
                    "SELECT id, tema, pregunta, respuesta, fuente FROM tarjetas "
                    "WHERE proxima <= ? AND tema LIKE ? ORDER BY proxima LIMIT ?",
                    (ahora, f"%{tema}%", limite)).fetchall()
            else:
                filas = con.execute(
                    "SELECT id, tema, pregunta, respuesta, fuente FROM tarjetas "
                    "WHERE proxima <= ? ORDER BY proxima LIMIT ?",
                    (ahora, limite)).fetchall()
        finally:
            con.close()
    return [{"id": f[0], "tema": f[1], "pregunta": f[2], "respuesta": f[3],
             "fuente": f[4]} for f in filas]


def siguiente(tema: str = "") -> dict:
    """La próxima pregunta, sin la respuesta: la respuesta la pone el señor."""
    lista = pendientes(tema, limite=1)
    if not lista:
        cuando = _proxima_fecha(tema)
        if cuando:
            faltan = cuando - time.time()
            dias = max(int(faltan // 86400), 0)
            return {"hay": False,
                    "mensaje": ("Por hoy no le toca repasar nada, señor. "
                                + (f"La siguiente vuelve en {dias} días."
                                   if dias else "La siguiente vuelve hoy mismo."))}
        return {"hay": False,
                "mensaje": ("No tengo tarjetas todavía, señor. Dígame «hazme "
                            "tarjetas de derivadas» y las saco de sus apuntes.")}
    t = lista[0]
    return {"hay": True, "id": t["id"], "tema": t["tema"],
            "pregunta": t["pregunta"], "respuesta": t["respuesta"],
            "mensaje": f"[{t['tema']}] {t['pregunta']}"}


def _proxima_fecha(tema: str = ""):
    with _lock:
        con = _con()
        try:
            if tema:
                f = con.execute("SELECT MIN(proxima) FROM tarjetas WHERE tema LIKE ?",
                                (f"%{tema}%",)).fetchone()
            else:
                f = con.execute("SELECT MIN(proxima) FROM tarjetas").fetchone()
        finally:
            con.close()
    return f[0] if f and f[0] else None


def calificar(ident: int, nota: str) -> str:
    """Guarda qué tal fue y calcula cuándo vuelve.

    `nota`: fallo | regular | bien | facil.
    """
    nota = (nota or "bien").strip().lower()
    with _lock:
        con = _con()
        try:
            fila = con.execute(
                "SELECT intervalo, factor, aciertos, fallos, pregunta "
                "FROM tarjetas WHERE id = ?", (ident,)).fetchone()
            if not fila:
                return "Esa tarjeta ya no existe, señor."
            intervalo, factor, aciertos, fallos, pregunta = fila
            factor = factor or FACTOR_INICIAL

            if nota.startswith("fall") or nota in ("mal", "no"):
                intervalo, factor = 1.0, max(factor - 0.20, FACTOR_MINIMO)
                fallos += 1
            elif nota.startswith("reg") or nota.startswith("cost"):
                intervalo = max(intervalo, 1.0)
                factor = max(factor - 0.15, FACTOR_MINIMO)
                aciertos += 1
            elif nota.startswith("fac") or nota.startswith("fácil"):
                intervalo = max(intervalo * factor * 1.3, 4.0)
                factor = min(factor + 0.15, 3.0)
                aciertos += 1
            else:                                   # bien
                intervalo = max(intervalo * factor, 1.0) if intervalo else 1.0
                aciertos += 1

            intervalo = min(intervalo, 365.0)
            proxima = time.time() + intervalo * 86400
            con.execute(
                "UPDATE tarjetas SET intervalo=?, factor=?, proxima=?, "
                "aciertos=?, fallos=? WHERE id=?",
                (intervalo, factor, proxima, aciertos, fallos, ident))
            con.commit()
        finally:
            con.close()

    dias = int(intervalo)
    cuando = ("mañana" if dias <= 1 else f"en {dias} días")
    if nota.startswith("fall") or nota in ("mal", "no"):
        return f"Apuntado, señor. Esa se la vuelvo a preguntar {cuando}."
    return f"Bien. Esa vuelve {cuando}."


def corregir(core, ident: int, respuesta_del_senor: str, log=print) -> dict:
    """Compara lo que dijo el señor con la respuesta buena.

    No se compara por letras: dos respuestas correctas casi nunca se escriben
    igual. Lo juzga el cerebro, y si no está disponible se cae a comparar
    palabras clave, que es peor pero no deja al señor sin corrección.
    """
    with _lock:
        con = _con()
        try:
            fila = con.execute(
                "SELECT pregunta, respuesta FROM tarjetas WHERE id = ?",
                (ident,)).fetchone()
        finally:
            con.close()
    if not fila:
        return {"nota": "fallo", "comentario": "Esa tarjeta ya no existe, señor."}
    pregunta, buena = fila
    dicha = (respuesta_del_senor or "").strip()
    if not dicha:
        return {"nota": "fallo", "comentario": f"La respuesta era: {buena}"}

    try:
        from proveedor_claude import cliente as OpenAI, sin_pensamiento
        _n, url, modelo, clave = core._proveedores()[0]
        c = OpenAI(base_url=url, api_key=clave)
        r = c.chat.completions.create(
            model=modelo, temperature=0.1, max_tokens=500,
            messages=[
                {"role": "system", "content":
                    "Corriges una tarjeta de estudio. Responde SOLO con un JSON:\n"
                    '{"nota": "fallo|regular|bien|facil", "comentario": "..."}\n'
                    "«bien» si la idea es correcta aunque las palabras sean otras. "
                    "«regular» si va encaminado pero le falta algo importante. "
                    "«fallo» si está mal o no responde. El comentario, una o dos "
                    "frases, y si falla di qué le faltó."},
                {"role": "user", "content":
                    f"Pregunta: {pregunta}\nRespuesta correcta: {buena}\n"
                    f"Lo que ha dicho: {dicha}"}])
        d = _leer_json(sin_pensamiento(r.choices[0].message.content or "")) or {}
        nota = str(d.get("nota") or "regular").lower()
        comentario = str(d.get("comentario") or "").strip()
    except Exception as e:
        log(f"[ESTUDIO] Corrijo sin cerebro ({e})")
        claves = {p for p in re.findall(r"\w{5,}", buena.lower())}
        acertadas = {p for p in re.findall(r"\w{5,}", dicha.lower())} & claves
        proporcion = len(acertadas) / max(len(claves), 1)
        nota = "bien" if proporcion > 0.5 else "regular" if proporcion > 0.2 else "fallo"
        comentario = f"La respuesta era: {buena}"

    calificar(ident, nota)
    return {"nota": nota, "comentario": comentario or f"La respuesta era: {buena}",
            "correcta": buena}


# ── estado ──────────────────────────────────────────────────────────────────
def estado(tema: str = "") -> dict:
    ahora = time.time()
    with _lock:
        con = _con()
        try:
            total = con.execute("SELECT COUNT(*) FROM tarjetas").fetchone()[0]
            hoy = con.execute("SELECT COUNT(*) FROM tarjetas WHERE proxima <= ?",
                              (ahora,)).fetchone()[0]
            temas = [r[0] for r in con.execute(
                "SELECT tema, COUNT(*) c FROM tarjetas GROUP BY tema "
                "ORDER BY c DESC LIMIT 12").fetchall()]
            aciertos, fallos = con.execute(
                "SELECT COALESCE(SUM(aciertos),0), COALESCE(SUM(fallos),0) "
                "FROM tarjetas").fetchone()
        finally:
            con.close()
    return {"total": total, "hoy": hoy, "temas": temas,
            "aciertos": aciertos, "fallos": fallos}


def resumen(tema: str = "") -> str:
    e = estado(tema)
    if not e["total"]:
        return ("No tiene tarjetas todavía, señor. Dígame «hazme tarjetas de "
                "derivadas» y las saco de sus propios apuntes.")
    partes = [f"{e['total']} tarjetas en {len(e['temas'])} temas."]
    partes.append(f"Hoy le tocan {e['hoy']}." if e["hoy"]
                  else "Hoy no le toca ninguna.")
    if e["aciertos"] or e["fallos"]:
        total = e["aciertos"] + e["fallos"]
        partes.append(f"Lleva {e['aciertos']} de {total} "
                      f"({100 * e['aciertos'] // max(total, 1)} %).")
    if e["temas"]:
        partes.append("Temas: " + ", ".join(e["temas"][:8]) + ".")
    return " ".join(partes)


def olvidar(tema: str) -> str:
    """Borra las tarjetas de un tema. Se pide el tema a propósito: sin él,
    un «olvida las tarjetas» mal entendido se lleva el trabajo de un mes."""
    tema = (tema or "").strip()
    if not tema:
        return ("Dígame de qué tema, señor: no borro todas las tarjetas por "
                "una frase suelta.")
    with _lock:
        con = _con()
        try:
            n = con.execute("DELETE FROM tarjetas WHERE tema LIKE ?",
                            (f"%{tema}%",)).rowcount
            con.commit()
        finally:
            con.close()
    return (f"Borradas {n} tarjetas de «{tema}», señor." if n
            else f"No tenía tarjetas de «{tema}», señor.")


if __name__ == "__main__":
    try:
        import consola_utf8  # noqa: F401
    except Exception:
        pass
    print(resumen())
