#!/usr/bin/env python3
"""
autoskills.py - Que JARVIS se escriba sus propias habilidades
=============================================================
El bucle ya estaba casi cerrado sin querer:

    storage.py          sabe que ordenes fallaron
    skills/plugins/     admite habilidades nuevas sin tocar el nucleo
    test_regresion.py   dice si algo se ha roto

Falta el paso del medio: que el cerebro escriba el codigo. Eso es lo que hay
aqui. Cuando una orden no la cubre nadie:

    1. el modelo escribe un plugin siguiendo una plantilla estricta,
    2. se valida sintaxis, contrato y construcciones prohibidas,
    3. se instala en CUARENTENA (skills/pendientes/), nunca directamente,
    4. se ejecuta la bateria de pruebas COMPLETA en un proceso aparte con el
       plugin cargado; si algo se rompe, se descarta solo,
    5. si todo pasa, se le enseña el codigo al señor y solo el decide.

El riesgo esta acotado por construccion: nada entra sin pasar las pruebas que
ya protegen al resto del proyecto, y nada se activa sin aprobacion humana.
"""
import os
import re
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
CUARENTENA = os.path.join(RAIZ, "skills", "pendientes")
DESTINO = os.path.join(RAIZ, "skills", "plugins")

# Construcciones que no se aceptan en codigo generado por el modelo. No es una
# lista de "cosas peligrosas" (el proyecto ejecuta apagados a diario): es una
# lista de cosas que impiden AUDITAR lo que hace el codigo.
PROHIBIDO = [
    (r"\beval\s*\(", "eval() hace imposible saber qué se ejecuta"),
    (r"\bexec\s*\(", "exec() hace imposible saber qué se ejecuta"),
    (r"__import__\s*\(", "importación dinámica: no se puede revisar"),
    (r"\bos\.system\s*\(", "usa ejecutor.ejecutar(), que registra y comprueba"),
    (r"subprocess\.(Popen|run|call)\s*\(", "usa ejecutor.ejecutar() en su lugar"),
    (r"\bopen\s*\([^)]*['\"][wa]", "escritura de archivos sin pasar por el proyecto"),
    (r"shutil\.rmtree|os\.remove|os\.unlink", "borrado directo: usa deshacer.a_papelera()"),
    (r"requests\.(post|put|delete)", "envío de datos fuera sin control"),
]

PLANTILLA = '''#!/usr/bin/env python3
"""
skills/plugins/{nombre}.py - {descripcion}
Generado por JARVIS el {fecha} a partir de: «{orden}»
"""


class {clase}:
    patterns = [{patrones}]
    priority = 40
    description = "{descripcion}"

    def handle(self, text: str, core):
        ...
'''

INSTRUCCIONES = """Escribe UN archivo de Python completo para una habilidad de JARVIS.

Contrato obligatorio:
- Una sola clase con estos atributos de clase: patterns (lista de expresiones
  regulares en español, sin acentos), priority (entero 40), description (string).
- Un método handle(self, text, core) que devuelve un string con la respuesta
  para el usuario (en español, tratándolo de «señor») o None si no aplica.
- Para ejecutar comandos del sistema: `import ejecutor` y usa
  ejecutor.ejecutar(comando, origen="plugin", orden=text). No uses subprocess.
- Para borrar archivos: `import deshacer` y usa deshacer.a_papelera(ruta).
- Prohibido: eval, exec, __import__, os.system, subprocess, requests.post,
  os.remove, shutil.rmtree, abrir archivos en modo escritura.
- Nada de dependencias nuevas: solo librería estándar y módulos del proyecto.

Responde SOLO con el código, sin explicaciones y sin ```."""


def _nombre_archivo(orden: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (orden or "habilidad").lower())[:40].strip("_")
    return f"auto_{base or 'habilidad'}"


# ── generación ──────────────────────────────────────────────────────────────
def proponer(core, orden: str, log=print) -> dict:
    """Escribe, valida y deja en cuarentena una habilidad para esa orden."""
    resultado = {"ok": False, "archivo": "", "codigo": "", "motivo": "", "pruebas": ""}
    if not orden or len(orden.strip()) < 4:
        resultado["motivo"] = "no me ha dicho qué habilidad quiere"
        return resultado

    codigo = _pedir_codigo(core, orden, log=log)
    if not codigo:
        resultado["motivo"] = "el cerebro no devolvió código utilizable"
        return resultado

    ok, motivo = validar(codigo)
    if not ok:
        resultado["motivo"] = motivo
        resultado["codigo"] = codigo
        return resultado

    os.makedirs(CUARENTENA, exist_ok=True)
    nombre = _nombre_archivo(orden)
    ruta = os.path.join(CUARENTENA, f"{nombre}.py")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(codigo)

    paso, salida = probar(ruta, orden, log=log)
    resultado.update({"archivo": ruta, "codigo": codigo, "pruebas": salida})
    if not paso:
        resultado["motivo"] = "no pasó las pruebas; la he descartado"
        try:
            os.unlink(ruta)
        except Exception:
            pass
        return resultado

    resultado["ok"] = True
    resultado["motivo"] = "lista para su aprobación"
    log(f"[AUTOSKILL] Habilidad candidata en cuarentena: {ruta}")
    return resultado


def _pedir_codigo(core, orden: str, log=print) -> str:
    try:
        from openai import OpenAI
        _n, url, modelo, clave = core._proveedores()[0]
        cliente = OpenAI(base_url=url, api_key=clave)
        resp = cliente.chat.completions.create(
            model=modelo, temperature=0.2, max_tokens=900,
            messages=[{"role": "system", "content": INSTRUCCIONES},
                      {"role": "user", "content":
                          f"Orden que ninguna habilidad reconoce: «{orden}». "
                          f"Escribe la habilidad que la atienda."}])
        texto = resp.choices[0].message.content or ""
    except Exception as e:
        log(f"[AUTOSKILL] El cerebro no pudo escribirla: {e}")
        return ""

    if "</think>" in texto:
        texto = texto.split("</think>", 1)[1]
    m = re.search(r"```(?:python)?\s*(.+?)```", texto, re.DOTALL)
    if m:
        texto = m.group(1)
    return texto.strip()


# ── validación ──────────────────────────────────────────────────────────────
def validar(codigo: str):
    """(ok, motivo). Sintaxis, contrato y construcciones prohibidas."""
    if not codigo.strip():
        return False, "el código está vacío"
    try:
        compile(codigo, "<autoskill>", "exec")
    except SyntaxError as e:
        return False, f"no compila: línea {e.lineno}, {e.msg}"

    for patron, motivo in PROHIBIDO:
        if re.search(patron, codigo):
            return False, f"usa algo que no acepto: {motivo}"

    if "patterns" not in codigo or "def handle" not in codigo:
        return False, "no cumple el contrato (faltan patterns o handle)"
    if "class " not in codigo:
        return False, "no define ninguna clase"

    # Las expresiones regulares deben compilar: una rota tumbaría el registro.
    for patron in re.findall(r'r?"([^"]{3,120})"', codigo):
        if any(c in patron for c in r"\b(|["):
            try:
                re.compile(patron)
            except re.error as e:
                return False, f"expresión regular inválida ({e})"
    return True, "válida"


# ── pruebas en proceso aparte ───────────────────────────────────────────────
def probar(ruta_cuarentena: str, orden: str, log=print, timeout: int = 240):
    """Instala temporalmente el plugin, pasa TODAS las pruebas y lo saca."""
    nombre = os.path.basename(ruta_cuarentena)
    destino = os.path.join(DESTINO, nombre)
    if os.path.exists(destino):
        return False, "ya existe una habilidad con ese nombre"

    try:
        with open(ruta_cuarentena, encoding="utf-8") as f:
            codigo = f.read()
        with open(destino, "w", encoding="utf-8") as f:
            f.write(codigo)

        # 1. La batería completa, en un proceso limpio.
        pruebas = subprocess.run([sys.executable, "test_regresion.py"], cwd=RAIZ,
                                 capture_output=True, timeout=timeout)
        salida = (pruebas.stdout or b"").decode("utf-8", errors="ignore")
        if pruebas.returncode != 0:
            return False, "las pruebas de regresión fallan con esa habilidad:\n" + salida[-600:]

        # 2. Y que además atienda la orden que la motivó.
        comprobacion = subprocess.run(
            [sys.executable, "-c",
             "from skills.plugins import get_plugin_registry;"
             "r = get_plugin_registry(log=lambda *a: None);"
             f"print('ATIENDE' if r.handle({orden!r}, None) else 'NO_ATIENDE')"],
            cwd=RAIZ, capture_output=True, timeout=60)
        texto = (comprobacion.stdout or b"").decode("utf-8", errors="ignore")
        if "ATIENDE" not in texto or "NO_ATIENDE" in texto:
            return False, "no llega a atender la orden para la que se escribió"
        return True, salida[-400:]
    except subprocess.TimeoutExpired:
        return False, "las pruebas no terminaron a tiempo"
    except Exception as e:
        return False, f"error probándola: {e}"
    finally:
        try:
            if os.path.exists(destino):
                os.unlink(destino)
        except Exception as e:
            log(f"[AUTOSKILL] No pude retirar la copia de prueba: {e}")


# ── aprobación ──────────────────────────────────────────────────────────────
def _firmar(codigo: str) -> str:
    """Cabecera con hash, fecha y modelo: trazabilidad del código autogenerado."""
    import hashlib
    huella = hashlib.sha256(codigo.encode("utf-8")).hexdigest()[:16]
    modelo = os.getenv("QWEN_MODEL", "modelo local")
    return (f"# [AUTOGENERADA por JARVIS]\n"
            f"# modelo: {modelo}\n"
            f"# fecha: {time.strftime('%Y-%m-%d %H:%M')}\n"
            f"# sha256(16): {huella}\n"
            f"# Aprobada a mano por el señor antes de instalarse.\n")


def firmadas() -> list:
    """Habilidades instaladas que escribió la propia IA."""
    salida = []
    if not os.path.isdir(DESTINO):
        return salida
    for nombre in sorted(os.listdir(DESTINO)):
        if not nombre.endswith(".py") or nombre.startswith("_"):
            continue
        try:
            with open(os.path.join(DESTINO, nombre), encoding="utf-8") as f:
                cabecera = f.read(400)
        except Exception:
            continue
        if "[AUTOGENERADA por JARVIS]" in cabecera:
            fecha = ""
            for linea in cabecera.splitlines():
                if linea.startswith("# fecha:"):
                    fecha = linea.split(":", 1)[1].strip()
            salida.append({"archivo": nombre, "fecha": fecha})
    return salida


def inventario() -> str:
    """Quién escribió cada habilidad modular instalada."""
    autos = firmadas()
    try:
        from skills.plugins import get_plugin_registry
        total = len(get_plugin_registry(log=lambda *a: None).catalogo())
    except Exception:
        total = 0
    if not autos:
        return (f"Tengo {total} habilidades modulares, señor, y ninguna la he "
                "escrito yo: todas son suyas.")
    detalle = "; ".join(f"{a['archivo']} ({a['fecha']})" for a in autos[:6])
    return (f"De mis {total} habilidades modulares, {len(autos)} las escribí yo "
            f"y usted las aprobó: {detalle}.")


def pendientes() -> list:
    if not os.path.isdir(CUARENTENA):
        return []
    return sorted(f for f in os.listdir(CUARENTENA) if f.endswith(".py"))


def ver(nombre: str) -> str:
    ruta = os.path.join(CUARENTENA, nombre if nombre.endswith(".py") else nombre + ".py")
    try:
        with open(ruta, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"No puedo leerla: {e}"


def aprobar(nombre: str, log=print) -> str:
    """Mueve una habilidad de cuarentena a producción y la carga en caliente."""
    archivo = nombre if nombre.endswith(".py") else nombre + ".py"
    origen = os.path.join(CUARENTENA, archivo)
    if not os.path.exists(origen):
        return f"No tengo ninguna habilidad pendiente llamada {archivo}, señor."
    destino = os.path.join(DESTINO, archivo)
    if os.path.exists(destino):
        return "Ya existe una habilidad instalada con ese nombre, señor."

    with open(origen, encoding="utf-8") as f:
        codigo = f.read()

    # Firma: dentro de seis meses habrá código en skills/plugins/ y hay que
    # poder distinguir de un vistazo lo que escribió el señor de lo que se
    # escribió solo, y con qué modelo.
    firma = _firmar(codigo)
    codigo = firma + codigo
    with open(destino, "w", encoding="utf-8") as f:
        f.write(codigo)
    os.unlink(origen)

    try:
        from skills.plugins import recargar_plugins
        total = recargar_plugins(log=log)
    except Exception as e:
        total = -1
        log(f"[AUTOSKILL] Instalada, pero no pude recargar: {e}")

    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "autoskill", f"Habilidad instalada: {archivo}",
            "escrita por el propio asistente y aprobada por el señor",
            gravedad="info")
    except Exception:
        pass
    try:
        import deshacer
        deshacer.anotar("comando", f"instalé la habilidad {archivo}",
                        {"inverso": f'del "{destino}"'}, log=log)
    except Exception:
        pass

    return (f"Habilidad {archivo} instalada, señor"
            + (f"; ahora tengo {total} habilidades modulares activas." if total >= 0
               else ", pero habrá que reiniciarme para que entre en juego."))


def descartar(nombre: str) -> str:
    archivo = nombre if nombre.endswith(".py") else nombre + ".py"
    ruta = os.path.join(CUARENTENA, archivo)
    try:
        os.unlink(ruta)
        return f"Descartada {archivo}, señor."
    except Exception as e:
        return f"No pude descartarla: {e}"


def resumen_propuesta(resultado: dict) -> str:
    """Frase para contarle al señor cómo fue el intento."""
    if resultado.get("ok"):
        nombre = os.path.basename(resultado["archivo"])
        lineas = len(resultado["codigo"].splitlines())
        return (f"He escrito una habilidad nueva ({nombre}, {lineas} líneas) y pasa "
                "todas las pruebas, señor. Está en cuarentena: dígame «muéstrame la "
                f"habilidad {nombre}» para verla, o «aprueba {nombre}» para instalarla.")
    return f"No he conseguido escribirla, señor: {resultado.get('motivo', 'sin motivo')}."
