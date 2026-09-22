#!/usr/bin/env python3
"""
analista.py - Escribir codigo, ejecutarlo y corregirlo hasta que salga
======================================================================
Hasta ahora, cada cosa que JARVIS sabia hacer habia que escribirla como
habilidad. Eso pone un techo: lo que nadie previo, no se puede pedir.

Esto lo rompe. En vez de una habilidad por tarea, una habilidad que las cubre
casi todas: el modelo escribe un programa, se ejecuta de verdad, y si falla se
le devuelve el error para que lo arregle. Hasta tres intentos.

    «cruza el excel de gastos con el de ingresos y dime el balance por mes»
    «renombra las fotos de la carpeta por su fecha de captura»
    «saca una grafica de cuanto he dormido segun el csv del reloj»
    «extrae las tablas del pdf del contrato a un excel»

Como se mantiene bajo control
-----------------------------
* El programa corre en un PROCESO APARTE, con su propia carpeta de trabajo y un
  limite de tiempo. Si se cuelga, se mata; no arrastra al asistente.
* Se revisa antes de ejecutar: nada de borrar sin papelera, nada de apagar el
  equipo, nada de lanzar procesos por su cuenta.
* Todo queda guardado: el codigo, la salida y los archivos generados. Si algo
  sale raro, se puede mirar exactamente que se ejecuto.
* Los archivos que crea van a una carpeta suya, no encima de los del señor.
"""
import json
import os
import re
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Analisis")
MAX_INTENTOS = int(os.getenv("JARVIS_ANALISTA_INTENTOS", "3"))
TIMEOUT = int(os.getenv("JARVIS_ANALISTA_TIMEOUT", "120"))

# Lo que no se acepta en el codigo generado. No es una lista de "cosas
# peligrosas" (el proyecto apaga el equipo a diario): es la lista de cosas que
# NO se pueden auditar o que estropean algo sin vuelta atras.
PROHIBIDO = [
    (r"\bshutil\.rmtree\b", "borrar árboles enteros; usa deshacer.a_papelera()"),
    (r"\bos\.(remove|unlink)\b", "borrado directo; usa deshacer.a_papelera()"),
    (r"\bsubprocess\b", "lanzar procesos; pide lo que necesites por otra vía"),
    (r"\bos\.system\b", "lanzar procesos"),
    (r"\b(eval|exec)\s*\(", "código dinámico: no se puede revisar"),
    (r"shutdown\s*/|SetSuspendState|LockWorkStation", "acciones sobre el equipo"),
    (r"\bformat\s*\(?\s*['\"]?[A-Z]:", "formatear unidades"),
    (r"\bwinreg\b", "tocar el registro de Windows"),
]

INSTRUCCIONES = """Eres un analista que resuelve tareas escribiendo un programa de Python.

Reglas:
- Escribe UN programa completo que resuelva la petición y que IMPRIMA el
  resultado por pantalla con print(). Lo que no se imprime, no existe.
- Estás en una carpeta de trabajo propia y es tu directorio actual. Guarda ahí
  lo que generes (gráficas, .xlsx, .csv) usando SIEMPRE rutas relativas
  (por ejemplo "gastos.csv"), nunca una ruta absoluta con unidad de disco.
  Después imprime el nombre del archivo que has creado.
- Para LEER los archivos del señor sí puedes usar rutas absolutas.
- Puedes usar la librería estándar y, si están instaladas: pandas, numpy,
  openpyxl, matplotlib (usa el backend "Agg"), PIL, docx, pypdf, requests.
  Si una falta, apáñate con la estándar en vez de fallar.
- Rutas del señor: {rutas}
- NO uses subprocess, os.system, eval, exec, os.remove ni shutil.rmtree.
- Nada de pedir datos por teclado: el programa se ejecuta solo.
- Si algo no se puede hacer, imprime por qué en una línea y termina.

Responde SOLO con el código, sin explicaciones y sin ```."""


def _carpeta_trabajo() -> str:
    ruta = os.path.join(CARPETA, time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(ruta, exist_ok=True)
    return ruta


def _rutas_utiles() -> str:
    hogar = os.path.expanduser("~")
    partes = []
    for nombre in ("Descargas", "Downloads", "Documentos", "Documents",
                   "Escritorio", "Desktop", "Imágenes", "Pictures"):
        ruta = os.path.join(hogar, nombre)
        if os.path.isdir(ruta):
            partes.append(f"{nombre} = {ruta}")
    return "; ".join(partes)


def validar(codigo: str):
    """(ok, motivo). Sintaxis y construcciones que no se aceptan."""
    if not codigo.strip():
        return False, "el programa vino vacío"
    try:
        compile(codigo, "<analista>", "exec")
    except SyntaxError as e:
        return False, f"no compila: línea {e.lineno}, {e.msg}"
    for patron, motivo in PROHIBIDO:
        if re.search(patron, codigo):
            return False, f"usa algo que no acepto: {motivo}"

    # Escribir fuera de su carpeta ensucia las del señor: la primera versión de
    # esto dejó un gastos.csv suelto en Descargas sin que nadie lo pidiera.
    absoluta = re.compile(r"""['"][A-Za-z]:[\\/]""")
    for m in re.finditer(r"""open\s*\(\s*([^,)]+)[^)]*['"][wax]""", codigo):
        if absoluta.search(m.group(1)):
            return False, ("escribe en una ruta absoluta; debe guardar en su "
                           "carpeta de trabajo con rutas relativas")
    # Una variable con la ruta esquiva la comprobación de arriba, así que se
    # mira también cualquier asignación con unidad de disco seguida de escritura.
    for m in re.finditer(r"""(\w+)\s*=\s*['"]([A-Za-z]:[\\/][^'"]+)['"]""", codigo):
        variable, ruta = m.group(1), m.group(2)
        if re.search(rf"open\s*\(\s*{variable}\b[^)]*['\"][wax]", codigo):
            return False, (f"guarda en {ruta[:40]}…, fuera de su carpeta de trabajo")
    if re.search(r"(?:to_csv|to_excel|savefig|save)\s*\(\s*['\"][A-Za-z]:[\/]", codigo):
        return False, "guarda fuera de su carpeta de trabajo"
    return True, "válido"


def _pedir_codigo(core, peticion: str, error_previo: str = "", codigo_previo: str = "",
                  log=print) -> str:
    """Le pide el programa al modelo. Si hay error previo, se lo da para corregir."""
    try:
        from proveedor_claude import cliente as OpenAI
        _n, url, modelo, clave = core._proveedores()[0]
        cliente = (core._cliente_llm(url, clave) if hasattr(core, "_cliente_llm")
                   else OpenAI(base_url=url, api_key=clave))
        sistema = INSTRUCCIONES.replace("{rutas}", _rutas_utiles())
        if error_previo:
            usuario = (f"Tarea: {peticion}\n\nTu programa anterior falló. "
                       f"Código:\n{codigo_previo[:2500]}\n\n"
                       f"Error:\n{error_previo[:1200]}\n\n"
                       "Devuélveme el programa corregido entero.")
        else:
            usuario = f"Tarea: {peticion}"
        resp = cliente.chat.completions.create(
            model=modelo, temperature=0.15, max_tokens=3000,
            messages=[{"role": "system", "content": sistema},
                      {"role": "user", "content": usuario}])
        texto = resp.choices[0].message.content or ""
    except Exception as e:
        log(f"[ANALISTA] El cerebro no pudo escribir el programa: {e}")
        return ""
    if "</think>" in texto:
        texto = texto.split("</think>", 1)[1]
    m = re.search(r"```(?:python)?\s*(.+?)```", texto, re.DOTALL)
    if m:
        texto = m.group(1)
    return texto.strip()


def _ejecutar(codigo: str, carpeta: str, log=print) -> dict:
    """Corre el programa en un proceso aparte, con tiempo limitado."""
    guion = os.path.join(carpeta, "programa.py")
    with open(guion, "w", encoding="utf-8") as f:
        f.write(codigo)

    entorno = os.environ.copy()
    entorno["MPLBACKEND"] = "Agg"          # matplotlib sin ventana
    entorno["PYTHONIOENCODING"] = "utf-8"
    inicio = time.time()
    try:
        p = subprocess.run([sys.executable, guion], cwd=carpeta, env=entorno,
                           capture_output=True, timeout=TIMEOUT,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        salida = (p.stdout or b"").decode("utf-8", errors="ignore")
        error = (p.stderr or b"").decode("utf-8", errors="ignore")
        return {"ok": p.returncode == 0, "salida": salida.strip(),
                "error": error.strip(), "segundos": round(time.time() - inicio, 1)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "salida": "", "segundos": TIMEOUT,
                "error": f"el programa no terminó en {TIMEOUT} segundos; lo he parado"}
    except Exception as e:
        return {"ok": False, "salida": "", "error": str(e)[:400], "segundos": 0}


def resolver(core, peticion: str, log=print, max_intentos: int = MAX_INTENTOS) -> dict:
    """Escribe, ejecuta y corrige hasta que el programa funcione."""
    resultado = {"ok": False, "peticion": peticion, "intentos": 0,
                 "salida": "", "error": "", "codigo": "", "carpeta": "", "archivos": []}
    if not peticion or len(peticion.strip()) < 5:
        resultado["error"] = "no me ha dicho qué analizar"
        return resultado

    carpeta = _carpeta_trabajo()
    resultado["carpeta"] = carpeta
    antes = set(os.listdir(carpeta))
    codigo = error_previo = ""

    for intento in range(1, max_intentos + 1):
        resultado["intentos"] = intento
        codigo = _pedir_codigo(core, peticion, error_previo, codigo, log=log)
        if not codigo:
            resultado["error"] = "el cerebro no devolvió código"
            break
        ok, motivo = validar(codigo)
        if not ok:
            error_previo = f"El código no pasó la revisión: {motivo}"
            log(f"[ANALISTA] Intento {intento} rechazado: {motivo}")
            continue

        log(f"[ANALISTA] Intento {intento}: ejecutando ({len(codigo.splitlines())} líneas)")
        ejecucion = _ejecutar(codigo, carpeta, log=log)
        resultado.update({"codigo": codigo, "salida": ejecucion["salida"],
                          "error": ejecucion["error"]})
        if ejecucion["ok"]:
            resultado["ok"] = True
            break
        # La traza del error es lo que se le devuelve para que corrija.
        error_previo = ejecucion["error"] or "terminó con error y sin mensaje"
        log(f"[ANALISTA] Intento {intento} falló: {error_previo.splitlines()[-1][:120]}")

    try:
        resultado["archivos"] = [f for f in os.listdir(carpeta)
                                 if f not in antes and f != "programa.py"]
    except Exception:
        pass

    try:
        from storage import get_storage
        get_storage(log=log).registrar_accion(
            origen="analista", orden=peticion[:200],
            comando=f"{resultado['intentos']} intento(s), {len(codigo.splitlines())} líneas",
            ok=resultado["ok"], detalle=(resultado["salida"] or resultado["error"])[:300],
            agente=getattr(core, "nombre_agente", "JARVIS"))
    except Exception:
        pass

    return resultado


def frase(resultado: dict) -> str:
    """La respuesta hablada: el resultado, no el proceso."""
    if not resultado.get("ok"):
        motivo = (resultado.get("error") or "").strip().splitlines()
        ultimo = motivo[-1][:160] if motivo else "sin detalle"
        return (f"No he conseguido resolverlo, señor, tras "
                f"{resultado.get('intentos', 0)} intentos: {ultimo}")

    partes = []
    salida = (resultado.get("salida") or "").strip()
    if salida:
        partes.append(salida[:1200])
    archivos = resultado.get("archivos") or []
    if archivos:
        partes.append("He dejado " + ", ".join(archivos[:4])
                      + f" en {os.path.basename(resultado['carpeta'])}.")
    if resultado.get("intentos", 1) > 1:
        partes.append(f"(me costó {resultado['intentos']} intentos)")
    return " ".join(partes) or "Hecho, señor, aunque el programa no imprimió nada."


# ── ¿esto es tarea de analista? ─────────────────────────────────────────────
_SEÑALES = (
    "calcula", "cruza", "analiza", "grafica", "gráfica", "grafico", "gráfico",
    "estadistica", "estadística", "media de", "suma de", "cuantos hay",
    "extrae", "convierte", "renombra", "ordena por", "agrupa", "compara",
    "csv", "excel", "xlsx", "json", "pdf", "hoja de calculo", "hoja de cálculo",
    "balance", "informe de datos", "tabla",
)


def parece_analisis(texto: str) -> bool:
    """¿Merece escribir un programa, o lo resuelve una habilidad normal?"""
    t = (texto or "").lower()
    if len(t.split()) < 3:
        return False
    return any(s in t for s in _SEÑALES)


def historial(limite: int = 5) -> str:
    """Los últimos análisis, para poder volver a ellos."""
    if not os.path.isdir(CARPETA):
        return "Todavía no he hecho ningún análisis, señor."
    carpetas = sorted(os.listdir(CARPETA), reverse=True)[:limite]
    if not carpetas:
        return "Todavía no he hecho ningún análisis, señor."
    filas = []
    for c in carpetas:
        ruta = os.path.join(CARPETA, c)
        try:
            archivos = [f for f in os.listdir(ruta) if f != "programa.py"]
        except Exception:
            archivos = []
        filas.append(f"{c}: {len(archivos)} archivo(s)")
    return "Últimos análisis, señor: " + "; ".join(filas) + f". Están en {CARPETA}."
