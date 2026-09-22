#!/usr/bin/env python3
"""
indice_documentos.py - Buscar DENTRO de tus archivos, no solo por nombre
========================================================================
La habilidad `_buscar_archivos` encuentra ficheros por nombre. Eso no sirve
cuando lo que recuerdas es el contenido: «¿que decia el contrato del alquiler
sobre la fianza?», «busca en mis apuntes lo de los indices invertidos».

Este modulo indexa el contenido de tus documentos y responde con la cita.

El motor es FTS5, que viene dentro de SQLite: busqueda por texto completo, sin
instalar nada y sin descargar modelos.

La busqueda es HIBRIDA: FTS5 para lo literal (un nombre, un numero de
expediente) y vectores para lo que se recuerda con otras palabras. Si el
apunte dice «tasa de variacion instantanea» y usted pregunta «que es una
derivada», solo la segunda via lo encuentra. El motor de significado lo pone
`embeddings.py`, con la clave de Pollinations o con Ollama en casa.

El indice es local: el contenido de los documentos solo sale del equipo cuando
se le pregunta a Claude, no al indexar.
"""
import json
import os
import re
import sqlite3
import threading
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(RAIZ, "jarvis_indice.db")
TAM_TROZO = int(os.getenv("JARVIS_INDICE_TROZO", "1200"))
MAX_MB = float(os.getenv("JARVIS_INDICE_MAX_MB", "20"))

EXTENSIONES = {".txt", ".md", ".markdown", ".py", ".js", ".ts", ".json", ".csv",
               ".html", ".css", ".log", ".ini", ".cfg", ".yaml", ".yml",
               ".pdf", ".docx"}
EXCLUIR = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist",
           "build", "AppData", "Windows", "Program Files"}

_lock = threading.RLock()


# ── base de datos ───────────────────────────────────────────────────────────
def _con():
    con = sqlite3.connect(DB, check_same_thread=False, timeout=15)
    con.execute("""CREATE TABLE IF NOT EXISTS documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruta TEXT, trozo INTEGER, mtime REAL, texto TEXT, vector TEXT,
        UNIQUE(ruta, trozo))""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_doc_ruta ON documentos(ruta)")
    try:
        con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS busqueda
                       USING fts5(texto, ruta UNINDEXED, trozo UNINDEXED,
                                  content='documentos', content_rowid='id')""")
    except sqlite3.OperationalError:
        pass        # SQLite sin FTS5: quedará la búsqueda por LIKE
    con.commit()
    return con


def _hay_fts(con) -> bool:
    try:
        con.execute("SELECT 1 FROM busqueda LIMIT 1")
        return True
    except Exception:
        return False


# ── extracción de texto ─────────────────────────────────────────────────────
def _texto_de(ruta: str, log=print) -> str:
    ext = os.path.splitext(ruta)[1].lower()
    try:
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
            except Exception:
                from PyPDF2 import PdfReader      # nombre antiguo
            lector = PdfReader(ruta)
            return "\n".join((p.extract_text() or "") for p in lector.pages[:60])
        if ext == ".docx":
            import docx
            return "\n".join(p.text for p in docx.Document(ruta).paragraphs)
        with open(ruta, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        log(f"[INDICE] No pude leer {os.path.basename(ruta)}: {e}")
        return ""


def _trozos(texto: str):
    """Corta por párrafos hasta el tamaño de trozo, sin partir frases."""
    texto = re.sub(r"\n{3,}", "\n\n", texto or "").strip()
    if not texto:
        return []
    partes, actual = [], ""
    for parrafo in texto.split("\n\n"):
        if len(actual) + len(parrafo) < TAM_TROZO:
            actual += ("\n\n" if actual else "") + parrafo
        else:
            if actual:
                partes.append(actual)
            actual = parrafo[:TAM_TROZO * 2]
    if actual:
        partes.append(actual)
    return partes


# ── embeddings: de vuelta ───────────────────────────────────────────────────
# Aqui vivia la busqueda por significado y se retiro con los modelos ajenos a
# Anthropic. Vuelve por `embeddings.py`, que la sirve con la clave de
# Pollinations o con Ollama en casa. La columna `vector` seguia en la tabla,
# asi que no hay que reindexar de cero: se rellena al vuelo.
def hay_embeddings() -> bool:
    try:
        import embeddings
        return embeddings.disponible()
    except Exception:
        return False


def motor_embeddings() -> str:
    try:
        import embeddings
        return embeddings.motor()
    except Exception:
        return ""


def _guardar_vectores(con, filas, log=print) -> int:
    """Calcula y guarda los vectores de [(id, texto), ...]. Devuelve cuantos.

    Se hace en lote y DESPUES de escribir el texto: si la red falla, el
    documento ya esta indexado y buscable por palabras, y los vectores se
    completan en la siguiente pasada en vez de perderse el indexado entero.
    """
    if not filas or not hay_embeddings():
        return 0
    import embeddings
    marca = embeddings.motor()
    vectores = embeddings.vectorizar([t for _i, t in filas], log=log)
    if not vectores:
        return 0
    hechos = 0
    for (ident, _texto), vec in zip(filas, vectores):
        if not vec:
            continue
        con.execute("UPDATE documentos SET vector = ? WHERE id = ?",
                    (json.dumps({"m": marca, "v": [round(x, 5) for x in vec]}), ident))
        hechos += 1
    return hechos


def vectorizar_pendientes(limite: int = 400, log=print) -> str:
    """Rellena los vectores que falten. Para lo indexado ANTES de este motor.

    Sin esto, todo lo que el señor ya tenia indexado se quedaria fuera de la
    busqueda por significado para siempre, y no se entenderia por que unos
    documentos aparecen y otros no.
    """
    if not hay_embeddings():
        import embeddings
        return embeddings.por_que_no()
    with _lock:
        con = _con()
        try:
            filas = con.execute(
                "SELECT id, texto FROM documentos "
                "WHERE vector IS NULL OR vector = '' LIMIT ?", (limite,)).fetchall()
            if not filas:
                return "Todos sus documentos tienen ya su vector, señor."
            hechos = _guardar_vectores(con, filas, log=log)
            con.commit()
            quedan = con.execute(
                "SELECT COUNT(*) FROM documentos "
                "WHERE vector IS NULL OR vector = ''").fetchone()[0]
        finally:
            con.close()
    parte = f"He vectorizado {hechos} trozos, señor."
    if quedan:
        parte += f" Quedan {quedan}; dígamelo otra vez y sigo."
    return parte


# ── indexado ────────────────────────────────────────────────────────────────
def carpetas_por_defecto():
    hogar = os.path.expanduser("~")
    return [os.path.join(hogar, c) for c in
            ("Documentos", "Documents", "Escritorio", "Desktop", "Descargas", "Downloads")
            if os.path.isdir(os.path.join(hogar, c))]


def indexar(carpetas=None, log=print, max_archivos: int = 800,
            con_vectores: bool = None) -> str:
    """Indexa (solo lo nuevo o modificado). Devuelve el parte para decirlo.

    Si hay motor de significado, cada trozo se vectoriza al indexarlo. Si no,
    se indexa igual y queda buscable por palabras: `con_vectores` se acepta
    para no romper a quien ya llamaba con ese argumento.
    """
    carpetas = carpetas or carpetas_por_defecto()
    inicio = time.time()
    nuevos = actualizados = saltados = vectorizados = 0

    with _lock:
        con = _con()
        usa_fts = _hay_fts(con)
        try:
            for carpeta in carpetas:
                for base, dirs, ficheros in os.walk(carpeta):
                    dirs[:] = [d for d in dirs if d not in EXCLUIR and not d.startswith(".")]
                    for nombre in ficheros:
                        if nuevos + actualizados >= max_archivos:
                            break
                        ruta = os.path.join(base, nombre)
                        if os.path.splitext(nombre)[1].lower() not in EXTENSIONES:
                            continue
                        try:
                            if os.path.getsize(ruta) > MAX_MB * 1024 * 1024:
                                saltados += 1
                                continue
                            mtime = os.path.getmtime(ruta)
                        except Exception:
                            continue

                        fila = con.execute(
                            "SELECT mtime FROM documentos WHERE ruta = ? LIMIT 1",
                            (ruta,)).fetchone()
                        if fila and abs(fila[0] - mtime) < 1:
                            continue        # sin cambios desde la última vez

                        texto = _texto_de(ruta, log=log)
                        partes = _trozos(texto)
                        if not partes:
                            continue
                        con.execute("DELETE FROM documentos WHERE ruta = ?", (ruta,))
                        recien = []
                        for i, parte in enumerate(partes[:40]):
                            cur = con.execute(
                                "INSERT OR REPLACE INTO documentos "
                                "(ruta, trozo, mtime, texto, vector) VALUES (?,?,?,?,?)",
                                (ruta, i, mtime, parte, ""))
                            recien.append((cur.lastrowid, parte))
                            if usa_fts:
                                con.execute(
                                    "INSERT INTO busqueda (rowid, texto, ruta, trozo) "
                                    "VALUES (?,?,?,?)",
                                    (cur.lastrowid, parte, ruta, i))
                        # Los vectores DESPUÉS del texto: si la red falla, el
                        # documento ya está indexado y buscable por palabras.
                        vectorizados += _guardar_vectores(con, recien, log=log)
                        if fila:
                            actualizados += 1
                        else:
                            nuevos += 1
                    if nuevos + actualizados >= max_archivos:
                        break
            con.commit()
        finally:
            con.close()

    return (f"Índice actualizado, señor: {nuevos} documentos nuevos, "
            f"{actualizados} modificados"
            + (f", {saltados} demasiado grandes" if saltados else "")
            + (f", {vectorizados} trozos vectorizados" if vectorizados else "")
            + f". En {time.time() - inicio:.0f} segundos."
            + ("" if hay_embeddings() else
               " Sin motor de significado: solo búsqueda por palabras."))


# ── conversaciones ──────────────────────────────────────────────────────────
def indexar_conversaciones(log=print, limite: int = 4000) -> str:
    """Mete el historial de conversaciones en el mismo indice que los documentos.

    La memoria influia en las respuestas pero no se podia consultar: no habia
    forma de preguntar «¿que me dijiste la semana pasada sobre X?». Como el
    indice ya sabe buscar por contenido, basta con darle de comer tambien las
    conversaciones, con la fecha por delante para poder situarlas.
    """
    import sqlite3 as _sq
    pares_totales = 0
    with _lock:
        con = _con()
        usa_fts = _hay_fts(con)
        try:
            for db, agente in ((os.path.join(RAIZ, "jarvis_memory.db"), "JARVIS"),
                               (os.path.join(RAIZ, "ultron_memory.db"), "ULTRON")):
                if not os.path.exists(db):
                    continue
                ruta_virtual = f"conversación:{agente}"
                con.execute("DELETE FROM documentos WHERE ruta = ?", (ruta_virtual,))
                try:
                    memoria = _sq.connect(db)
                    filas = memoria.execute(
                        "SELECT role, content, timestamp FROM interactions "
                        "ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
                    memoria.close()
                except Exception as e:
                    log(f"[INDICE] No pude leer {os.path.basename(db)}: {e}")
                    continue

                # Se agrupan turnos consecutivos para que un fragmento tenga
                # pregunta y respuesta juntas: medio diálogo no sirve de nada.
                bloques, actual = [], []
                for rol, contenido, marca in reversed(filas):
                    if not contenido:
                        continue
                    actual.append(f"[{(marca or '')[:16]}] {rol}: {contenido[:600]}")
                    if len(" ".join(actual)) > TAM_TROZO:
                        bloques.append("\n".join(actual))
                        actual = []
                if actual:
                    bloques.append("\n".join(actual))

                for i, texto in enumerate(bloques[:400]):
                    cur = con.execute(
                        "INSERT OR REPLACE INTO documentos "
                        "(ruta, trozo, mtime, texto, vector) VALUES (?,?,?,?,?)",
                        (ruta_virtual, i, time.time(), texto, ""))
                    if usa_fts:
                        con.execute(
                            "INSERT INTO busqueda (rowid, texto, ruta, trozo) "
                            "VALUES (?,?,?,?)", (cur.lastrowid, texto, ruta_virtual, i))
                pares_totales += len(bloques)
            con.commit()
        finally:
            con.close()
    return (f"He indexado {pares_totales} fragmentos de nuestras conversaciones, "
            "señor. Ya puede preguntarme qué hablamos y cuándo.")


def buscar_conversacion(consulta: str, k: int = 4, log=print) -> str:
    """Responde «¿qué me dijiste sobre X?» con la fecha delante."""
    trozos = [t for t in buscar(consulta, k=k * 2, log=log)
              if t[0].startswith("conversación:")][:k]
    if not trozos:
        return ("No encuentro nada de eso en nuestras conversaciones, señor. "
                "Si hace mucho, puede que aún no lo haya indexado: dígame "
                "«indexa nuestras conversaciones».")
    partes = []
    for _ruta, texto, _p in trozos:
        primera = texto.strip().splitlines()[0]
        partes.append(primera[:180])
    return "Esto es lo que encuentro, señor: " + " … ".join(partes)


# ── búsqueda ────────────────────────────────────────────────────────────────
def buscar_semantica(consulta: str, k: int = 5, log=print) -> list:
    """Por SIGNIFICADO: encuentra «tasa de variación» preguntando «derivada».

    Se comparan vectores, así que las palabras no tienen que coincidir. Solo se
    miran los trozos vectorizados con el MISMO motor que la consulta: mezclar
    dos motores es comparar cosas que no se pueden comparar.
    """
    if not consulta.strip() or not hay_embeddings():
        return []
    import embeddings
    vec = embeddings.vectorizar_uno(consulta, log=log)
    if not vec:
        return []
    marca = embeddings.motor()

    with _lock:
        con = _con()
        try:
            filas = con.execute(
                "SELECT ruta, texto, vector FROM documentos "
                "WHERE vector IS NOT NULL AND vector != ''").fetchall()
        finally:
            con.close()

    puntuados = []
    for ruta, texto, crudo in filas:
        try:
            guardado = json.loads(crudo)
        except Exception:
            continue
        if guardado.get("m") != marca:
            continue
        s = embeddings.coseno(vec, guardado.get("v") or [])
        if s > 0.15:                     # por debajo de ahí es ruido
            puntuados.append((ruta, texto, s))
    puntuados.sort(key=lambda x: -x[2])
    return puntuados[:k]


def buscar(consulta: str, k: int = 5, log=print) -> list:
    """Trozos más relevantes: [(ruta, texto, puntuación), ...].

    Híbrida a propósito. FTS5 clava lo literal —un nombre propio, un número de
    expediente— y el significado clava lo que se recuerda con otras palabras.
    Ninguna de las dos sola sirve para unos apuntes de carrera, así que se
    juntan y se quita lo repetido.
    """
    if not consulta.strip():
        return []

    semanticos = buscar_semantica(consulta, k=k, log=log)

    literales = []
    with _lock:
        con = _con()
        try:
            if _hay_fts(con):
                # FTS5 tiene sintaxis propia y una consulta dictada la pisa
                # sin querer: los dos puntos de «caída libre: medida» son el
                # operador de columna, y la búsqueda moría con «no such
                # column: libre». Fuera todo lo que FTS5 interpreta, y las
                # palabras reservadas en minúscula para que no manden.
                limpia = re.sub(r'[:"\'\-*()^{}\[\]~]', " ", consulta)
                limpia = re.sub(r"\b(AND|OR|NOT|NEAR)\b", lambda m: m.group(0).lower(),
                                limpia).strip()
                try:
                    filas = con.execute(
                        "SELECT ruta, texto, rank FROM busqueda "
                        "WHERE busqueda MATCH ? ORDER BY rank LIMIT ?",
                        (limpia, k)).fetchall()
                    literales = [(r, t, 1.0) for r, t, _rank in filas]
                except Exception as e:
                    log(f"[INDICE] FTS falló: {e}")
            if not literales:
                patron = f"%{consulta.strip()[:60]}%"
                filas = con.execute(
                    "SELECT ruta, texto FROM documentos WHERE texto LIKE ? LIMIT ?",
                    (patron, k)).fetchall()
                literales = [(r, t, 0.5) for r, t in filas]
        finally:
            con.close()

    # Se mezclan alternando: primero el mejor de cada vía, luego el segundo de
    # cada una... Así ninguna de las dos se come la lista entera, que es lo que
    # pasaba al concatenarlas sin más.
    mezcla, vistos = [], set()
    for par in zip(literales + [None] * len(semanticos),
                   semanticos + [None] * len(literales)):
        for item in par:
            if item is None:
                continue
            firma = (item[0], (item[1] or "")[:80])
            if firma in vistos:
                continue
            vistos.add(firma)
            mezcla.append(item)
    return mezcla[:k]


def responder(core, pregunta: str, log=print) -> str:
    """Busca en los documentos y deja que el cerebro conteste citando la fuente."""
    trozos = buscar(pregunta, k=4, log=log)
    if not trozos:
        return ("No encuentro nada sobre eso en sus documentos, señor. "
                "¿Quiere que indexe alguna carpeta más?")

    contexto = "\n\n".join(
        f"[{os.path.basename(ruta)}]\n{texto[:900]}" for ruta, texto, _p in trozos)
    fuentes = ", ".join(sorted({os.path.basename(r) for r, _t, _p in trozos}))

    try:
        # 350 tokens daban de sobra con un modelo que contesta y punto; con uno
        # que razona, el razonamiento se los comía y la respuesta salía vacía.
        import pensar
        texto = pensar.texto(
            core,
            "Responde en español y SOLO con lo que digan los fragmentos. "
            "Si no está ahí, dilo claramente. Cita el archivo del que sale.",
            f"Fragmentos:\n{contexto}\n\nPregunta: {pregunta}",
            tope=1500, temperatura=0.2, log=log)
        if not texto:
            raise ValueError("el cerebro no devolvió nada")
        return texto + f"\n\n(Fuentes: {fuentes})"
    except Exception as e:
        log(f"[INDICE] El cerebro no pudo responder: {e}")
        ruta, texto, _p = trozos[0]
        return (f"Esto es lo más parecido que encuentro, señor, en "
                f"{os.path.basename(ruta)}: «{texto[:400]}»")


def estado(log=print) -> dict:
    with _lock:
        con = _con()
        try:
            total = con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0]
            archivos = con.execute("SELECT COUNT(DISTINCT ruta) FROM documentos").fetchone()[0]
            fts = _hay_fts(con)
        finally:
            con.close()
    return {"trozos": total, "archivos": archivos, "fts5": fts,
            "embeddings": False, "db": DB}
