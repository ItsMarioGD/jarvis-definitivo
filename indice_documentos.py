#!/usr/bin/env python3
"""
indice_documentos.py - Buscar DENTRO de tus archivos, no solo por nombre
========================================================================
La habilidad `_buscar_archivos` encuentra ficheros por nombre. Eso no sirve
cuando lo que recuerdas es el contenido: «¿que decia el contrato del alquiler
sobre la fianza?», «busca en mis apuntes lo de los indices invertidos».

Este modulo indexa el contenido de tus documentos y responde con la cita.

Dos motores de busqueda, y se usa el mejor disponible:

  * FTS5 (viene dentro de SQLite): busqueda por texto completo. Funciona HOY,
    sin instalar nada y sin descargar modelos. Es el motor por defecto.
  * Embeddings locales (Ollama con nomic-embed-text): busqueda por significado,
    encuentra «fianza» aunque el documento diga «deposito de garantia». Se
    activa solo si el modelo esta instalado.

Todo es local: ni el contenido ni las consultas salen del equipo, asi que
funciona igual con el modo privado activado.
"""
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request

RAIZ = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(RAIZ, "jarvis_indice.db")
BASE_OLLAMA = os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1").replace("/v1", "")
MODELO_EMBED = os.getenv("JARVIS_EMBED_MODELO", "nomic-embed-text")
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


# ── embeddings (opcional) ───────────────────────────────────────────────────
def hay_embeddings() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_OLLAMA}/api/tags", timeout=4) as r:
            nombres = [m.get("name", "") for m in json.load(r).get("models", [])]
        return any(n.startswith(MODELO_EMBED.split(":")[0]) for n in nombres)
    except Exception:
        return False


def _vector(texto: str, log=print):
    cuerpo = json.dumps({"model": MODELO_EMBED, "prompt": texto[:4000]}).encode("utf-8")
    peticion = urllib.request.Request(f"{BASE_OLLAMA}/api/embeddings", data=cuerpo,
                                      headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=60) as r:
            return json.load(r).get("embedding") or None
    except Exception as e:
        log(f"[INDICE] Embedding falló: {e}")
        return None


def _similitud(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    punto = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return punto / (na * nb) if na and nb else 0.0


# ── indexado ────────────────────────────────────────────────────────────────
def carpetas_por_defecto():
    hogar = os.path.expanduser("~")
    return [os.path.join(hogar, c) for c in
            ("Documentos", "Documents", "Escritorio", "Desktop", "Descargas", "Downloads")
            if os.path.isdir(os.path.join(hogar, c))]


def indexar(carpetas=None, log=print, max_archivos: int = 800,
            con_vectores: bool = None) -> str:
    """Indexa (solo lo nuevo o modificado). Devuelve el parte para decirlo."""
    carpetas = carpetas or carpetas_por_defecto()
    if con_vectores is None:
        con_vectores = hay_embeddings()
    inicio = time.time()
    nuevos = actualizados = saltados = 0

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
                        for i, parte in enumerate(partes[:40]):
                            vector = ""
                            if con_vectores:
                                v = _vector(parte, log=log)
                                vector = json.dumps(v) if v else ""
                            cur = con.execute(
                                "INSERT OR REPLACE INTO documentos "
                                "(ruta, trozo, mtime, texto, vector) VALUES (?,?,?,?,?)",
                                (ruta, i, mtime, parte, vector))
                            if usa_fts:
                                con.execute(
                                    "INSERT INTO busqueda (rowid, texto, ruta, trozo) "
                                    "VALUES (?,?,?,?)",
                                    (cur.lastrowid, parte, ruta, i))
                        if fila:
                            actualizados += 1
                        else:
                            nuevos += 1
                    if nuevos + actualizados >= max_archivos:
                        break
            con.commit()
        finally:
            con.close()

    motor = "significado (embeddings)" if con_vectores else "texto completo"
    return (f"Índice actualizado, señor: {nuevos} documentos nuevos, "
            f"{actualizados} modificados"
            + (f", {saltados} demasiado grandes" if saltados else "")
            + f". Búsqueda por {motor}, en {time.time() - inicio:.0f} segundos.")


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
def buscar(consulta: str, k: int = 5, log=print) -> list:
    """Trozos más relevantes: [(ruta, texto, puntuación), ...]."""
    if not consulta.strip():
        return []
    with _lock:
        con = _con()
        try:
            if hay_embeddings():
                objetivo = _vector(consulta, log=log)
                if objetivo:
                    filas = con.execute(
                        "SELECT ruta, texto, vector FROM documentos "
                        "WHERE vector != '' LIMIT 4000").fetchall()
                    puntuadas = []
                    for ruta, texto, vector in filas:
                        try:
                            v = json.loads(vector)
                        except Exception:
                            continue
                        puntuadas.append((ruta, texto, _similitud(objetivo, v)))
                    puntuadas.sort(key=lambda x: -x[2])
                    if puntuadas and puntuadas[0][2] > 0.3:
                        return puntuadas[:k]

            if _hay_fts(con):
                limpia = re.sub(r'["\'\-*()]', " ", consulta).strip()
                try:
                    filas = con.execute(
                        "SELECT ruta, texto, rank FROM busqueda "
                        "WHERE busqueda MATCH ? ORDER BY rank LIMIT ?",
                        (limpia, k)).fetchall()
                    if filas:
                        return [(r, t, 1.0) for r, t, _rank in filas]
                except Exception as e:
                    log(f"[INDICE] FTS falló: {e}")

            patron = f"%{consulta.strip()[:60]}%"
            filas = con.execute(
                "SELECT ruta, texto FROM documentos WHERE texto LIKE ? LIMIT ?",
                (patron, k)).fetchall()
            return [(r, t, 0.5) for r, t in filas]
        finally:
            con.close()


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
        from openai import OpenAI
        _n, url, modelo, clave = core._proveedores()[0]
        cliente = OpenAI(base_url=url, api_key=clave)
        resp = cliente.chat.completions.create(
            model=modelo, temperature=0.2, max_tokens=350,
            messages=[
                {"role": "system", "content":
                    "Responde en español y SOLO con lo que digan los fragmentos. "
                    "Si no está ahí, dilo claramente. Cita el archivo del que sale."},
                {"role": "user", "content": f"Fragmentos:\n{contexto}\n\nPregunta: {pregunta}"}])
        texto = (resp.choices[0].message.content or "").strip()
        if "</think>" in texto:
            texto = texto.split("</think>", 1)[1].strip()
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
            "embeddings": hay_embeddings(), "db": DB}
