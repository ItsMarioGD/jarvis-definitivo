#!/usr/bin/env python3
"""
matematica.py - El motor matemático de JARVIS y ULTRON
======================================================
Resuelve y, sobre todo, DIBUJA. Todo en local: sympy para el álgebra exacta,
numpy para el muestreo, matplotlib para la lámina de alta resolución y un visor
web propio (three.js) para la versión 3D que se puede girar con el ratón.

Lo que entra
------------
Una frase dicha en voz alta («derívame equis al cuadrado por seno de equis y
grafícamelo en tres dimensiones») o escrita con notación normal
(`d/dx (x^2 sin x)`). `normalizar_expresion()` traduce la voz a notación y
`sympificar()` la convierte en objeto de sympy.

Lo que sale
-----------
    - Respuesta hablada: corta, para el TTS.
    - Desarrollo paso a paso: para leerlo en el panel.
    - lamina.png       render 2D/3D de matplotlib a 200 ppp
    - visor.html       visor interactivo (se abre solo en el navegador)
    - malla.obj/.stl   la gráfica como MODELO 3D de verdad, imprimible y
                       abrible en Blender; enlaza con modelado3d.holograma()

Tipos de gráfica
----------------
    2D   funciones, varias curvas, paramétrica, polar, campo de direcciones,
         nube de puntos con ajuste
    3D   superficie z=f(x,y), paramétrica (u,v), curva en el espacio,
         campo vectorial, e IMPLÍCITA F(x,y,z)=0 por «surface nets»

El módulo es autónomo: no necesita el LLM para funcionar. Si hay cerebro
disponible lo usa para entender enunciados retorcidos; si no, tira de reglas.
"""
import json
import math
import os
import re
import struct
import time

_SALIDA = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Ciencia")

# Paleta: la misma que la interfaz AEON, para que las láminas parezcan suyas.
_FONDO = "#04060a"
_PANEL = "#080d14"
_REJILLA = "#123043"
_TINTA = "#cfe9f5"
_ACENTO = ("#2ec6ff", "#ff9f43", "#7bed9f", "#ff6b81", "#c56cf0",
           "#ffd166", "#4ecdc4", "#f78fb3")


# ── disponibilidad ─────────────────────────────────────────────────────────
def _tiene(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def disponible() -> bool:
    """Con sympy y numpy ya resuelve; matplotlib solo hace falta para la lámina."""
    return _tiene("sympy") and _tiene("numpy")


def estado() -> dict:
    return {
        "sympy": _tiene("sympy"),
        "numpy": _tiene("numpy"),
        "matplotlib": _tiene("matplotlib"),
        "scipy": _tiene("scipy"),
        "pint": _tiene("pint"),
        "salida": _SALIDA,
    }


def faltantes() -> list:
    return [m for m in ("sympy", "numpy", "matplotlib", "scipy", "pint") if not _tiene(m)]


def instalar_faltantes(log=print) -> str:
    """Instala lo que falte con el pip del intérprete en marcha."""
    falta = faltantes()
    if not falta:
        return "Ya está todo instalado, señor."
    import subprocess
    import sys
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", *falta],
                       check=True, capture_output=True, timeout=900)
        return "Instalado: " + ", ".join(falta)
    except Exception as e:
        log(f"[MAT] pip falló: {e}")
        return f"No pude instalar {', '.join(falta)}: {str(e)[:160]}"


def carpeta_salida(nombre: str) -> str:
    slug = re.sub(r"\W+", "-", (nombre or "grafica").lower()).strip("-")[:40] or "grafica"
    d = os.path.join(_SALIDA, f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(d, exist_ok=True)
    return d


# ── de la voz a la notación ────────────────────────────────────────────────
# Orden importante: lo más largo primero, para que «raíz cúbica» no se coma
# «raíz».
_VOZ = [
    (r"\ba\s+la\s+(\d+)\s*(?:[ªº]|-?esima|ava)?\s*potencia\b", r"**\1"),
    (r"\belevad[oa]\s+a\s+la\s+(\d+)\b", r"**\1"),
    (r"\belevad[oa]\s+a\s+(?:la\s+)?(?:potencia\s+)?", "**"),
    (r"\ba\s+la\s+(\d+)\b", r"**\1"),          # «equis a la cuatro»
    (r"\bal\s+cuadrado\b", "**2"),
    (r"\bal\s+cubo\b", "**3"),
    (r"\bra[ií]z\s+c[uú]bica\s+de\b", "cbrt "),
    (r"\bra[ií]z\s+cuadrada\s+de\b", "sqrt "),
    (r"\bra[ií]z\s+de\b", "sqrt "),
    (r"\blogaritmo\s+natural\s+de\b", "ln "),
    (r"\blogaritmo\s+neperiano\s+de\b", "ln "),
    (r"\blogaritmo\s+de\b", "log10 "),
    (r"\bvalor\s+absoluto\s+de\b", "abs "),
    (r"\bseno\s+hiperb[oó]lico\s+de\b", "sinh "),
    (r"\bcoseno\s+hiperb[oó]lico\s+de\b", "cosh "),
    (r"\btangente\s+hiperb[oó]lica\s+de\b", "tanh "),
    (r"\barco\s*seno\s+de\b", "asin "),
    (r"\barco\s*coseno\s+de\b", "acos "),
    (r"\barco\s*tangente\s+de\b", "atan "),
    (r"\bseno\s+de\b", "sin "),
    (r"\bcoseno\s+de\b", "cos "),
    (r"\btangente\s+de\b", "tan "),
    (r"\bcosecante\s+de\b", "csc "),
    (r"\bsecante\s+de\b", "sec "),
    (r"\bcotangente\s+de\b", "cot "),
    (r"\bfactorial\s+de\b", "factorial "),
    (r"\bexponencial\s+de\b", "exp "),
    (r"\bpor\s+ciento\b", "/100"),
    (r"\bm[aá]s\b", "+"),
    (r"\bmenos\b", "-"),
    (r"\bmultiplicado\s+por\b", "*"),
    (r"\bpor\b", "*"),
    (r"\bdividido\s+(?:por|entre)\b", "/"),
    (r"\bdividido\b", "/"),
    (r"\bentre\b", "/"),
    (r"\bsobre\b", "/"),
    (r"\bes\s+igual\s+a\b", "="),
    (r"\bigual\s+a\b", "="),
    (r"\bmenor\s+o\s+igual\s+que\b", "<="),
    (r"\bmayor\s+o\s+igual\s+que\b", ">="),
    (r"\bmenor\s+que\b", "<"),
    (r"\bmayor\s+que\b", ">"),
    (r"\babre\s+par[eé]ntesis\b", "("),
    (r"\bcierra\s+par[eé]ntesis\b", ")"),
    (r"\binfinito\b", "oo"),
    # Nombres de letra dictados. «equis» es el caso real; el resto por si acaso.
    (r"\bequis\b", "x"),
    (r"\bye\b", "y"),
    (r"\bzeta\b", "z"),
    (r"\bu\s+ve\b", "v"),
    (r"\bteta\b", "theta"),
    (r"\balfa\b", "alpha"),
    (r"\blambda\b", "lamda"),          # sympy la llama lamda
]

# Superíndices que escupen los teclados y los OCR.
_SUPER = {"⁰": "**0", "¹": "**1", "²": "**2", "³": "**3",
          "⁴": "**4", "⁵": "**5", "⁶": "**6", "⁷": "**7",
          "⁸": "**8", "⁹": "**9"}

_FUNCS = ("sqrt", "cbrt", "log10", "log", "ln", "abs", "exp", "factorial",
          "sinh", "cosh", "tanh", "asin", "acos", "atan",
          "sin", "cos", "tan", "csc", "sec", "cot")


def _cerrar_funciones(t: str) -> str:
    """«sin x + 1» -> «sin(x) + 1». Toma el trozo mínimo que es argumento."""
    for f in _FUNCS:
        for _ in range(24):
            m = re.search(rf"\b{f}\s+(?!\()", t)
            if not m:
                break
            i = m.end()
            # Argumento: un número o un identificador, con potencia opcional.
            m2 = re.match(r"[-+]?\s*(?:\d+(?:\.\d+)?|[A-Za-z_]\w*)"
                          r"(?:\s*\*\*\s*[-+]?\d+(?:\.\d+)?)?", t[i:])
            if not m2:
                t = t[:m.start()] + f + "(" + t[i:] + ")"
                break
            arg = m2.group(0).strip()
            t = t[:m.start()] + f"{f}({arg})" + t[i + m2.end():]
    return t


# Números dictados. Sin esto, «dos por equis al cuadrado» llega al parser como
# la variable «dos» y todo el enunciado se cae.
_UNI = {"cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
        "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
        "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18,
        "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintiun": 21,
        "veintidos": 22, "veintidós": 22, "veintitres": 23, "veintitrés": 23,
        "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintiséis": 26,
        "veintisiete": 27, "veintiocho": 28, "veintinueve": 29}
_DEC = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
        "setenta": 70, "ochenta": 80, "noventa": 90}
_CEN = {"cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
        "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
        "setecientos": 700, "ochocientos": 800, "novecientos": 900}
_PALNUM = {**_UNI, **_DEC, **_CEN}


# «un» y «una» casi siempre son artículos («una pelota de 2 kg»), no el número
# uno. Solo cuentan como número si detrás viene una unidad o una potencia.
_TRAS_UN = ("medio", "medios", "tercio", "tercios", "cuarto", "cuartos",
            "quinto", "quintos", "metro", "metros", "kilo", "kilos",
            "kilogramo", "kilogramos", "gramo", "gramos", "segundo", "segundos",
            "minuto", "minutos", "hora", "horas", "newton", "newtons",
            "julio", "julios", "mol", "moles", "litro", "litros", "grado",
            "grados", "radian", "radianes", "voltio", "voltios", "amperio",
            "amperios", "%")


def _palabras_a_numeros(t: str) -> str:
    """«dos mil trescientos cuarenta y cinco» -> «2345». Decimales con «coma»."""
    fichas = t.split()
    salida, i = [], 0
    while i < len(fichas):
        limpia = fichas[i].strip(".,;:()")
        if limpia in ("un", "una"):
            siguiente = (fichas[i + 1].strip(".,;:()") if i + 1 < len(fichas) else "")
            if siguiente not in _TRAS_UN:
                salida.append(fichas[i])
                i += 1
                continue
        if limpia not in _PALNUM and limpia != "mil":
            salida.append(fichas[i])
            i += 1
            continue
        total, parcial, consumidas = 0, 0, 0
        while i < len(fichas):
            w = fichas[i].strip(".,;:()")
            if w in _CEN:
                parcial += _CEN[w]
            elif w in _DEC:
                parcial += _DEC[w]
            elif w in _UNI:
                parcial += _UNI[w]
            elif w == "mil":
                total += (parcial or 1) * 1000
                parcial = 0
            elif w in ("millon", "millón", "millones"):
                total = (total + parcial or 1) * 1000000
                parcial = 0
            elif w == "y" and i + 1 < len(fichas) and \
                    fichas[i + 1].strip(".,;:()") in _UNI:
                pass                                 # «cuarenta y cinco»
            else:
                break
            i += 1
            consumidas += 1
        num = total + parcial
        # Parte decimal: «tres coma uno cuatro» -> 3.14
        if i < len(fichas) and fichas[i].strip(".,;:()") in ("coma", "punto"):
            j, digitos = i + 1, ""
            while j < len(fichas) and fichas[j].strip(".,;:()") in _UNI:
                digitos += str(_UNI[fichas[j].strip(".,;:()")])
                j += 1
            if digitos:
                salida.append(f"{num}.{digitos}")
                i = j
                continue
        salida.append(str(num) if consumidas else fichas[i])
    return " ".join(salida)


def normalizar_expresion(texto: str) -> str:
    """«equis al cuadrado más dos por equis» -> «x**2 + 2*x».

    Después de sustituir, las funciones quedan como «sin x»: `_cerrar_funciones`
    les pone los paréntesis que faltan.
    """
    t = " " + (texto or "").strip() + " "
    for k, v in _SUPER.items():
        t = t.replace(k, v)
    t = (t.replace("×", "*").replace("·", "*").replace("÷", "/")
          .replace("−", "-").replace("–", "-").replace("^", "**"))
    t = re.sub(r"\*\*\s*\*\*", "**", t)
    bajo = _palabras_a_numeros(t.lower())
    for pat, rep in _VOZ:
        bajo = re.sub(pat, rep, bajo)
    t = bajo.replace("cbrt ", "cbrt").replace("sqrt ", "sqrt")
    t = _cerrar_funciones(t)
    t = re.sub(r"\blog10\s*\(([^()]*)\)", r"log(\1, 10)", t)
    t = re.sub(r"\bln\b", "log", t)
    t = re.sub(r"\bcbrt\(([^()]+)\)", r"(\1)**Rational(1,3)", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def sympificar(texto: str, variables: dict | None = None):
    """Texto -> expresión de sympy, tolerando `2x`, `x^2` y el dictado."""
    import sympy as sp
    from sympy.parsing.sympy_parser import (parse_expr, standard_transformations,
                                            implicit_multiplication_application,
                                            convert_xor)
    t = normalizar_expresion(texto)
    if "=" in t:                      # «a = b» se pasa a «a - (b)»
        izq, der = t.split("=", 1)
        t = f"({izq}) - ({der})"
    trans = standard_transformations + (implicit_multiplication_application, convert_xor)
    local = {"e": sp.E, "pi": sp.pi, "oo": sp.oo, "I": sp.I, "Rational": sp.Rational}
    if variables:
        local.update(variables)
    return parse_expr(t, local_dict=local, transformations=trans, evaluate=True)


def partir_ecuacion(texto: str):
    """«2x + 1 = 7» -> (lhs, rhs) ya sympificados. Sin «=», rhs es 0."""
    import sympy as sp
    t = normalizar_expresion(texto)
    if "=" in t:
        izq, der = t.split("=", 1)
        return sympificar(izq), sympificar(der)
    return sympificar(texto), sp.Integer(0)


def simbolos_de(expr) -> list:
    """Símbolos libres con x,y,z,t delante: es el orden que espera la vista."""
    pref = ["x", "y", "z", "t", "u", "v", "r", "n", "k"]
    libres = sorted(expr.free_symbols, key=lambda s: s.name)
    return (sorted([s for s in libres if s.name in pref], key=lambda s: pref.index(s.name))
            + [s for s in libres if s.name not in pref])


def bonito(expr) -> str:
    """Expresión legible para leerla en voz alta o imprimirla en el panel."""
    import sympy as sp
    try:
        s = sp.sstr(expr)
    except Exception:
        s = str(expr)
    return (s.replace("**", "^").replace("*", "·").replace("sqrt", "√")
             .replace("Abs", "|·|").replace("pi", "π"))


def latex(expr) -> str:
    import sympy as sp
    try:
        return sp.latex(expr)
    except Exception:
        return str(expr)


# ── resolutores ────────────────────────────────────────────────────────────
def resolver_ecuacion(texto: str, variable: str = "") -> dict:
    """Ecuación o inecuación de una incógnita, con desarrollo."""
    import sympy as sp
    izq, der = partir_ecuacion(texto)
    expr = sp.simplify(izq - der)
    libres = simbolos_de(expr)
    if not libres:
        return {"tipo": "identidad", "resultado": expr == 0,
                "pasos": [f"No hay incógnita: la igualdad es {'cierta' if expr == 0 else 'falsa'}."]}
    var = sp.Symbol(variable) if variable else libres[0]
    pasos = [f"Ecuación: {bonito(izq)} = {bonito(der)}",
             f"Todo a un lado: {bonito(expr)} = 0"]
    tex = [rf"{latex(izq)} = {latex(der)}", rf"{latex(expr)} = 0"]
    fact = sp.factor(expr)
    if fact != expr:
        pasos.append(f"Factorizada: {bonito(fact)} = 0")
    grado = None
    try:
        grado = sp.degree(sp.Poly(expr, var))
    except Exception:
        pass
    datos = {}
    if grado == 2:
        a, b, c = (sp.Poly(expr, var).all_coeffs() + [0, 0, 0])[:3]
        disc = sp.simplify(b**2 - 4*a*c)
        rdisc = sp.sqrt(disc)
        datos = {"a": a, "b": b, "c": c, "discriminante": disc}
        pasos.append(f"Coeficientes: a = {bonito(a)}, b = {bonito(b)}, c = {bonito(c)}")
        pasos.append("Fórmula general: x = (−b ± √(b² − 4ac)) / (2a)")
        pasos.append(f"Discriminante: Δ = b² − 4ac = ({bonito(b)})² − 4·({bonito(a)})·"
                     f"({bonito(c)}) = {bonito(disc)}")
        pasos.append("   Δ > 0 → dos raíces reales distintas; Δ = 0 → una raíz doble; "
                     "Δ < 0 → dos raíces complejas conjugadas.")
        pasos.append("   Aquí Δ = " + bonito(disc) + " → "
                     + ("dos soluciones reales y distintas: la parábola corta al eje X "
                        "en dos puntos."
                        if disc.is_positive else
                        "raíz doble: la parábola es tangente al eje X."
                        if disc == 0 else
                        "sin solución real: la parábola no llega a cortar el eje X."))
        if disc.is_positive and not sp.sqrt(disc).is_rational:
            pasos.append(f"   √Δ = {bonito(rdisc)} ≈ {float(sp.N(rdisc)):.6g} "
                         "(irracional: las raíces salen con radical)")
        elif disc.is_positive:
            pasos.append(f"   √Δ = {bonito(rdisc)} (exacto: las raíces son racionales)")
        pasos.append(f"Sustituyendo: x = ({bonito(-b)} ± √{bonito(disc)}) / "
                     f"({bonito(2*a)})")
        tex += [rf"a = {latex(a)},\quad b = {latex(b)},\quad c = {latex(c)}",
                r"x = \frac{-b \pm \sqrt{b^{2}-4ac}}{2a}",
                rf"\Delta = b^{{2}}-4ac = ({latex(b)})^{{2}}-4({latex(a)})({latex(c)})"
                rf" = {latex(disc)}",
                rf"x = \frac{{{latex(-b)} \pm \sqrt{{{latex(disc)}}}}}{{{latex(2*a)}}}"]
        pasos.append(f"Suma de las raíces (−b/a) = {bonito(sp.simplify(-b/a))}   ·   "
                     f"Producto (c/a) = {bonito(sp.simplify(c/a))}   [Cardano-Vieta]")
        vx = sp.simplify(-b / (2*a))
        pasos.append(f"Vértice de la parábola: x = −b/2a = {bonito(vx)}, "
                     f"y = {bonito(sp.simplify(expr.subs(var, vx)))}")
    sols = sp.solve(sp.Eq(izq, der), var, dict=False)
    if not isinstance(sols, (list, tuple)):
        sols = [sols]
    if sols:
        pasos.append("Soluciones exactas: "
                     + ", ".join(f"{var} = {bonito(sp.nsimplify(s))}" for s in sols))
        tex.append(r",\quad ".join(rf"{var} = {latex(s)}" for s in sols))
    else:
        pasos.append("No tiene solución en los reales.")
    aprox = []
    for s in sols:
        try:
            aprox.append(complex(sp.N(s)))
        except Exception:
            aprox.append(None)
    decimales = [f"{var} ≈ {v.real:.6g}" for v in aprox
                 if v is not None and abs(v.imag) < 1e-12]
    if decimales and any(not sp.nsimplify(s).is_Integer for s in sols):
        pasos.append("En decimal: " + ", ".join(decimales))
    if fact != expr and grado == 2:
        pasos.append(f"Comprobación por factorización: {bonito(fact)} = 0 "
                     "da las mismas raíces.")
    return {"tipo": "ecuacion", "variable": str(var), "expr": expr,
            "soluciones": sols, "aprox": aprox, "grado": grado, "pasos": pasos,
            "latex": tex, "coeficientes": datos}


def resolver_sistema(lineas: list, incognitas: list | None = None) -> dict:
    """Sistema de ecuaciones (lineal o no) con desarrollo matricial si procede."""
    import sympy as sp
    ecs = []
    for ln in lineas:
        izq, der = partir_ecuacion(ln)
        ecs.append(sp.Eq(izq, der))
    libres = sorted({s for e in ecs for s in e.free_symbols}, key=lambda s: s.name)
    inc = [sp.Symbol(v) for v in incognitas] if incognitas else libres
    pasos = ["Sistema:"] + [f"   {bonito(e.lhs)} = {bonito(e.rhs)}" for e in ecs]
    try:
        A, b = sp.linear_eq_to_matrix(ecs, inc)
        pasos.append(f"Matriz de coeficientes A =\n{sp.pretty(A)}")
        pasos.append(f"Términos independientes b = {sp.pretty(b.T)}")
        if A.rows == A.cols:
            det = sp.det(A)
            pasos.append(f"det(A) = {bonito(det)}"
                         + (" → compatible determinado" if det != 0
                            else " → el determinante es 0: no hay solución única"))
    except Exception:
        pass
    sol = sp.solve(ecs, inc, dict=True)
    if sol:
        pasos.append("Solución: " + ", ".join(
            f"{k} = {bonito(v)}" for k, v in sol[0].items()))
    else:
        pasos.append("El sistema no tiene solución.")
    tex = [r"\begin{cases}" + r"\\".join(
        rf"{latex(e.lhs)} = {latex(e.rhs)}" for e in ecs) + r"\end{cases}"]
    if sol:
        tex.append(r",\quad ".join(rf"{k} = {latex(v)}" for k, v in sol[0].items()))
    return {"tipo": "sistema", "incognitas": [str(i) for i in inc],
            "soluciones": sol, "pasos": pasos, "latex": tex}


def derivar(texto: str, variable: str = "", orden: int = 1) -> dict:
    import sympy as sp
    expr = sympificar(texto)
    libres = simbolos_de(expr)
    var = sp.Symbol(variable) if variable else (libres[0] if libres else sp.Symbol("x"))
    d = sp.diff(expr, var, orden)
    ds = sp.simplify(d)
    pasos = [f"f({var}) = {bonito(expr)}",
             f"Derivada de orden {orden} respecto a {var}:",
             f"f{'′' * min(orden, 3)}({var}) = {bonito(d)}"]
    if ds != d:
        pasos.append(f"Simplificada: {bonito(ds)}")
    try:
        criticos = sp.solve(sp.Eq(sp.diff(expr, var), 0), var)
        if criticos:
            pasos.append("Puntos críticos (f′=0): "
                         + ", ".join(f"{var}={bonito(c)}" for c in criticos))
            seg = sp.diff(expr, var, 2)
            for c in criticos[:6]:
                try:
                    v = sp.N(seg.subs(var, c))
                    pasos.append(f"   f″({bonito(c)}) = {bonito(v)} → "
                                 + ("mínimo" if v > 0 else "máximo" if v < 0
                                    else "punto de inflexión o silla"))
                except Exception:
                    pass
    except Exception:
        pass
    return {"tipo": "derivada", "variable": str(var), "expr": expr,
            "resultado": ds, "pasos": pasos,
            "latex": [rf"f({var}) = {latex(expr)}",
                      rf"\frac{{d^{{{orden}}}f}}{{d{var}^{{{orden}}}}} = {latex(ds)}"]}


def integrar(texto: str, variable: str = "", a=None, b=None) -> dict:
    import sympy as sp
    expr = sympificar(texto)
    libres = simbolos_de(expr)
    var = sp.Symbol(variable) if variable else (libres[0] if libres else sp.Symbol("x"))
    F = sp.integrate(expr, var)
    pasos = [f"f({var}) = {bonito(expr)}",
             f"Primitiva: ∫ f d{var} = {bonito(F)} + C"]
    res = F
    if a is not None and b is not None:
        la = sympificar(str(a)) if isinstance(a, str) else sp.nsimplify(a)
        lb = sympificar(str(b)) if isinstance(b, str) else sp.nsimplify(b)
        res = sp.integrate(expr, (var, la, lb))
        pasos.append(f"Regla de Barrow: F({bonito(lb)}) − F({bonito(la)})")
        pasos.append(f"   F({bonito(lb)}) = {bonito(sp.simplify(F.subs(var, lb)))}")
        pasos.append(f"   F({bonito(la)}) = {bonito(sp.simplify(F.subs(var, la)))}")
        pasos.append(f"Valor de la integral definida = {bonito(sp.simplify(res))}")
        try:
            pasos.append(f"En decimal ≈ {float(sp.N(res)):.6g}")
        except Exception:
            pass
    tex = [rf"\int {latex(expr)}\,d{var} = {latex(F)} + C"]
    if a is not None and b is not None:
        tex.append(rf"\int_{{{latex(sympificar(str(a)))}}}^{{{latex(sympificar(str(b)))}}}"
                   rf" {latex(expr)}\,d{var} = {latex(sp.simplify(res))}")
    return {"tipo": "integral", "variable": str(var), "expr": expr,
            "resultado": res, "primitiva": F, "limites": (a, b), "pasos": pasos,
            "latex": tex}


def limite(texto: str, variable: str = "", punto="0", lado: str = "") -> dict:
    import sympy as sp
    expr = sympificar(texto)
    libres = simbolos_de(expr)
    var = sp.Symbol(variable) if variable else (libres[0] if libres else sp.Symbol("x"))
    p = sympificar(str(punto))
    dirn = {"+": "+", "-": "-", "derecha": "+", "izquierda": "-"}.get(lado, "+")
    L = sp.limit(expr, var, p, dirn) if lado else sp.limit(expr, var, p)
    pasos = [f"f({var}) = {bonito(expr)}",
             f"Sustitución directa en {var}→{bonito(p)}:"]
    try:
        sub = expr.subs(var, p)
        pasos.append(f"   f({bonito(p)}) = {bonito(sub)}"
                     + ("  → indeterminación, hay que trabajarlo"
                        if sub.has(sp.nan, sp.zoo) or sub is sp.nan else ""))
    except Exception:
        pass
    pasos.append(f"lím = {bonito(L)}")
    return {"tipo": "limite", "variable": str(var), "expr": expr,
            "resultado": L, "punto": p, "pasos": pasos,
            "latex": [rf"\lim_{{{var} \to {latex(p)}}} {latex(expr)} = {latex(L)}"]}


def serie_taylor(texto: str, variable: str = "", centro="0", orden: int = 6) -> dict:
    import sympy as sp
    expr = sympificar(texto)
    libres = simbolos_de(expr)
    var = sp.Symbol(variable) if variable else (libres[0] if libres else sp.Symbol("x"))
    c = sympificar(str(centro))
    s = sp.series(expr, var, c, orden).removeO()
    pasos = [f"f({var}) = {bonito(expr)}",
             f"Taylor alrededor de {var}={bonito(c)} hasta orden {orden}:",
             f"   {bonito(sp.expand(s))}"]
    return {"tipo": "serie", "variable": str(var), "expr": expr,
            "resultado": sp.expand(s), "pasos": pasos,
            "latex": [rf"{latex(expr)} \approx {latex(sp.expand(s))}"]}


def matriz(datos, operacion: str = "todo") -> dict:
    """Determinante, inversa, rango, autovalores, LU... de una matriz."""
    import sympy as sp
    M = sp.Matrix(datos)
    pasos = [f"M =\n{sp.pretty(M)}", f"Dimensión: {M.rows}×{M.cols}"]
    out = {"tipo": "matriz", "matriz": M, "pasos": pasos}
    try:
        pasos.append(f"Rango = {M.rank()}")
    except Exception:
        pass
    if M.rows == M.cols:
        det = M.det()
        pasos.append(f"det(M) = {bonito(det)}")
        out["det"] = det
        pasos.append(f"traza = {bonito(M.trace())}")
        if det != 0:
            inv = M.inv()
            out["inversa"] = inv
            pasos.append(f"M⁻¹ =\n{sp.pretty(inv)}")
        else:
            pasos.append("Singular: no tiene inversa.")
        try:
            ev = M.eigenvals()
            out["autovalores"] = ev
            pasos.append("Autovalores: " + ", ".join(
                f"{bonito(k)} (multiplicidad {v})" for k, v in ev.items()))
        except Exception:
            pass
    return out


def ecuacion_diferencial(texto: str, funcion: str = "y", variable: str = "x") -> dict:
    """EDO escrita como «y'' + y = 0» o «Derivative(y(x),x) - y(x)»."""
    import sympy as sp
    x = sp.Symbol(variable)
    f = sp.Function(funcion)
    t = normalizar_expresion(texto)
    # y'' -> Derivative(y(x),x,2); y' -> Derivative(y(x),x); y -> y(x)
    t = re.sub(rf"\b{funcion}'''", f"Derivative({funcion}({variable}),{variable},3)", t)
    t = re.sub(rf"\b{funcion}''", f"Derivative({funcion}({variable}),{variable},2)", t)
    t = re.sub(rf"\b{funcion}'", f"Derivative({funcion}({variable}),{variable})", t)
    t = re.sub(rf"\b{funcion}\b(?!\()", f"{funcion}({variable})", t)
    izq, der = (t.split("=", 1) + ["0"])[:2] if "=" in t else (t, "0")
    loc = {funcion: f, variable: x, "Derivative": sp.Derivative}
    ec = sp.Eq(sp.sympify(izq, locals=loc), sp.sympify(der, locals=loc))
    sol = sp.dsolve(ec, f(x))
    pasos = [f"EDO: {bonito(ec.lhs)} = {bonito(ec.rhs)}",
             f"Orden: {sp.ode_order(ec, f(x))}",
             f"Solución general: {bonito(sol.lhs)} = {bonito(sol.rhs)}"]
    try:
        pasos.insert(2, "Clasificación: " + ", ".join(sp.classify_ode(ec, f(x))[:3]))
    except Exception:
        pass
    return {"tipo": "edo", "resultado": sol, "pasos": pasos}


def estadistica(datos: list) -> dict:
    """Descriptiva completa de una muestra."""
    import statistics as st
    d = [float(v) for v in datos]
    n = len(d)
    if n == 0:
        return {"tipo": "estadistica", "pasos": ["No hay datos."], "resultado": None}
    orden = sorted(d)
    med = st.fmean(d)
    var_m = st.variance(d) if n > 1 else 0.0
    var_p = st.pvariance(d)
    q1 = orden[int(0.25 * (n - 1))] if n > 1 else orden[0]
    q3 = orden[int(0.75 * (n - 1))] if n > 1 else orden[0]
    try:
        moda = st.multimode(d)
    except Exception:
        moda = []
    res = {"n": n, "media": med, "mediana": st.median(d), "moda": moda,
           "min": orden[0], "max": orden[-1], "rango": orden[-1] - orden[0],
           "varianza_muestral": var_m, "desviacion_muestral": math.sqrt(var_m),
           "varianza_poblacional": var_p, "desviacion_poblacional": math.sqrt(var_p),
           "q1": q1, "q3": q3, "iqr": q3 - q1, "suma": sum(d)}
    pasos = [f"n = {n} datos",
             f"Media = Σx/n = {sum(d):.6g}/{n} = {med:.6g}",
             f"Mediana = {res['mediana']:.6g}",
             f"Moda = {', '.join(f'{m:.6g}' for m in moda) if moda else '—'}",
             f"Varianza muestral s² = {var_m:.6g}  →  s = {res['desviacion_muestral']:.6g}",
             f"Varianza poblacional σ² = {var_p:.6g}  →  σ = {res['desviacion_poblacional']:.6g}",
             f"Rango = {res['rango']:.6g}   Q1 = {q1:.6g}   Q3 = {q3:.6g}   IQR = {res['iqr']:.6g}"]
    return {"tipo": "estadistica", "resultado": res, "datos": d, "pasos": pasos}


def simplificar(texto: str) -> dict:
    import sympy as sp
    expr = sympificar(texto)
    s = sp.simplify(expr)
    pasos = [f"Original: {bonito(expr)}", f"Simplificada: {bonito(s)}"]
    for nombre, fn in (("Expandida", sp.expand), ("Factorizada", sp.factor),
                       ("Fracción común", sp.together)):
        try:
            v = fn(expr)
            if v != expr and v != s:
                pasos.append(f"{nombre}: {bonito(v)}")
        except Exception:
            pass
    return {"tipo": "simplificar", "expr": expr, "resultado": s, "pasos": pasos,
            "latex": [rf"{latex(expr)} = {latex(s)}"]}


# ── muestreo robusto ───────────────────────────────────────────────────────
def _f_numerica(expr, vars_):
    """lambdify con numpy; devuelve una función que nunca revienta."""
    import numpy as np
    import sympy as sp
    f = sp.lambdify(vars_, expr, modules=["numpy", {"cbrt": np.cbrt}])

    def segura(*a):
        base = np.zeros_like(np.asarray(a[0], dtype=float))
        with np.errstate(all="ignore"):
            try:
                # Si a la expresión le sobran símbolos, lambdify devuelve una
                # expresión de sympy y esto revienta: se responde con NaN.
                y = np.asarray(f(*a), dtype=float) + base
            except Exception:
                y = np.full_like(base, np.nan)
            y[~np.isfinite(y)] = np.nan
            return y
    return segura


def _cortar_polos(x, y, umbral: float = 40.0):
    """Mete NaN donde la curva pega un salto: así no se dibuja la asíntota."""
    import numpy as np
    y = np.asarray(y, dtype=float).copy()
    dy = np.abs(np.diff(y))
    escala = np.nanpercentile(np.abs(y[np.isfinite(y)]), 90) if np.any(np.isfinite(y)) else 1.0
    salto = dy > max(umbral * (escala if escala > 0 else 1.0) / max(len(y), 1), 1e-9) * 50
    y[1:][salto] = np.nan
    return y


def _limites_y(ys, margen: float = 0.08):
    """Recorte robusto del eje Y: los polos no deben aplastar la curva."""
    import numpy as np
    v = np.concatenate([np.asarray(y, dtype=float).ravel() for y in ys])
    v = v[np.isfinite(v)]
    if v.size == 0:
        return (-1.0, 1.0)
    lo, hi = np.percentile(v, 1.0), np.percentile(v, 99.0)
    if hi - lo < 1e-12:
        lo, hi = lo - 1, hi + 1
    d = (hi - lo) * margen
    return (float(lo - d), float(hi + d))


def _estilo(ax, titulo: str = "", xl: str = "x", yl: str = "y"):
    ax.set_facecolor(_PANEL)
    ax.grid(True, color=_REJILLA, linewidth=0.6, alpha=0.85)
    ax.grid(True, which="minor", color=_REJILLA, linewidth=0.3, alpha=0.4)
    ax.minorticks_on()
    for s in ax.spines.values():
        s.set_color(_REJILLA)
    ax.tick_params(colors=_TINTA, labelsize=8)
    ax.set_xlabel(xl, color=_TINTA, fontsize=10)
    ax.set_ylabel(yl, color=_TINTA, fontsize=10)
    if titulo:
        ax.set_title(titulo, color=_ACENTO[0], fontsize=12, pad=12)


# ── gráfica 2D ─────────────────────────────────────────────────────────────
def grafica_2d(expresiones, rango=(-10, 10), titulo: str = "", carpeta: str = "",
               variable: str = "x", puntos: int = 2000, area=None,
               marcar: bool = True, log=print) -> dict:
    """Una o varias funciones de una variable, anotadas hasta el detalle.

    Marca raíces, máximos, mínimos, inflexiones, corte con el eje Y y las
    asíntotas verticales y horizontales. `area=(a,b)` sombrea la integral.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp

    # Admite texto, una expresión de sympy suelta, o una lista de cualquiera.
    if isinstance(expresiones, str) or hasattr(expresiones, "free_symbols"):
        expresiones = [expresiones]
    var = sp.Symbol(variable)
    exprs = [e if hasattr(e, "free_symbols") else sympificar(str(e)) for e in expresiones]
    a, b = float(rango[0]), float(rango[1])
    x = np.linspace(a, b, puntos)

    fig, ax = plt.subplots(figsize=(11, 6.6), dpi=200, facecolor=_FONDO)
    notas = []
    for i, expr in enumerate(exprs):
        color = _ACENTO[i % len(_ACENTO)]
        f = _f_numerica(expr, (var,))
        y = _cortar_polos(x, f(x))
        ax.plot(x, y, color=color, linewidth=2.0, label=f"${latex(expr)}$",
                solid_capstyle="round", zorder=3)
        if not marcar:
            continue
        # Raíces
        try:
            for r in sp.solve(sp.Eq(expr, 0), var):
                rv = complex(sp.N(r))
                if abs(rv.imag) < 1e-9 and a <= rv.real <= b:
                    ax.plot([rv.real], [0], "o", color=color, markersize=7,
                            markeredgecolor="white", markeredgewidth=0.8, zorder=5)
                    ax.annotate(f"raíz {rv.real:.4g}", (rv.real, 0),
                                textcoords="offset points", xytext=(6, -14),
                                color=color, fontsize=7.5)
                    notas.append(f"raíz en {variable}={rv.real:.6g}")
        except Exception:
            pass
        # Extremos e inflexiones
        try:
            d1, d2 = sp.diff(expr, var), sp.diff(expr, var, 2)
            for c in sp.solve(sp.Eq(d1, 0), var)[:8]:
                cv = complex(sp.N(c))
                if abs(cv.imag) > 1e-9 or not (a <= cv.real <= b):
                    continue
                yv = float(sp.N(expr.subs(var, cv.real)))
                s2 = float(sp.N(d2.subs(var, cv.real)))
                etiqueta = "máx" if s2 < 0 else "mín" if s2 > 0 else "silla"
                ax.plot([cv.real], [yv], "^" if s2 < 0 else "v", color=color,
                        markersize=8, markeredgecolor="white", markeredgewidth=0.7, zorder=5)
                ax.annotate(f"{etiqueta} ({cv.real:.3g}, {yv:.3g})", (cv.real, yv),
                            textcoords="offset points", xytext=(6, 8),
                            color=color, fontsize=7.5)
                notas.append(f"{etiqueta} en ({cv.real:.4g}, {yv:.4g})")
            for c in sp.solve(sp.Eq(d2, 0), var)[:6]:
                cv = complex(sp.N(c))
                if abs(cv.imag) < 1e-9 and a <= cv.real <= b:
                    yv = float(sp.N(expr.subs(var, cv.real)))
                    ax.plot([cv.real], [yv], "s", color=color, markersize=5,
                            alpha=0.8, zorder=4)
                    notas.append(f"inflexión en ({cv.real:.4g}, {yv:.4g})")
        except Exception:
            pass
        # Asíntotas
        try:
            den = sp.denom(sp.together(expr))
            for p in sp.solve(sp.Eq(den, 0), var):
                pv = complex(sp.N(p))
                if abs(pv.imag) < 1e-9 and a <= pv.real <= b:
                    ax.axvline(pv.real, color=color, linestyle=":", alpha=0.55, linewidth=1.2)
                    ax.annotate(f"asíntota {variable}={pv.real:.3g}", (pv.real, 0),
                                rotation=90, textcoords="offset points", xytext=(4, 20),
                                color=color, fontsize=7, alpha=0.9)
                    notas.append(f"asíntota vertical en {variable}={pv.real:.4g}")
            for direccion in (sp.oo, -sp.oo):
                L = sp.limit(expr, var, direccion)
                if L.is_finite and L.is_real:
                    ax.axhline(float(L), color=color, linestyle="--", alpha=0.35, linewidth=1.0)
                    notas.append(f"asíntota horizontal y={float(L):.4g}")
                    break
        except Exception:
            pass

    if area and len(exprs) == 1:
        try:
            ia, ib = float(sympificar(str(area[0]))), float(sympificar(str(area[1])))
            xs = np.linspace(ia, ib, 600)
            ys = _f_numerica(exprs[0], (var,))(xs)
            ax.fill_between(xs, 0, ys, color=_ACENTO[0], alpha=0.22, zorder=2,
                            label=f"área [{ia:g}, {ib:g}]")
            val = float(sp.N(sp.integrate(exprs[0], (var, ia, ib))))
            ax.annotate(f"∫ = {val:.6g}", ((ia + ib) / 2, float(np.nanmean(ys)) / 2),
                        color="white", fontsize=10, ha="center")
            notas.append(f"área bajo la curva = {val:.6g}")
        except Exception as e:
            log(f"[MAT] área falló: {e}")

    ys_all = [_f_numerica(e, (var,))(x) for e in exprs]
    ax.set_ylim(*_limites_y(ys_all))
    ax.set_xlim(a, b)
    ax.axhline(0, color=_TINTA, linewidth=1.0, alpha=0.5)
    ax.axvline(0, color=_TINTA, linewidth=1.0, alpha=0.5)
    _estilo(ax, titulo or "Gráfica", variable, "f(" + variable + ")")
    leg = ax.legend(facecolor=_PANEL, edgecolor=_REJILLA, labelcolor=_TINTA,
                    fontsize=10, loc="best")
    leg.get_frame().set_alpha(0.9)
    fig.tight_layout()

    out = carpeta or carpeta_salida(titulo or "grafica")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)

    datos = {"tipo": "2d", "x": x.tolist(),
             "series": [{"nombre": bonito(e),
                         "y": [None if not np.isfinite(v) else float(v)
                               for v in _cortar_polos(x, _f_numerica(e, (var,))(x))]}
                        for e in exprs]}
    html = visor_web(datos, os.path.join(out, "visor.html"), titulo or "Gráfica")
    return {"png": png, "html": html, "carpeta": out, "notas": notas, "datos": datos}


def grafica_parametrica_2d(fx: str, fy: str, rango=(0, 6.283185307), titulo: str = "",
                           carpeta: str = "", parametro: str = "t", puntos: int = 3000) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp
    t = sp.Symbol(parametro)
    ex, ey = sympificar(fx), sympificar(fy)
    ts = np.linspace(float(rango[0]), float(rango[1]), puntos)
    xs, ys = _f_numerica(ex, (t,))(ts), _f_numerica(ey, (t,))(ts)
    fig, ax = plt.subplots(figsize=(9, 9), dpi=200, facecolor=_FONDO)
    # Color por avance del parámetro: se ve el sentido del recorrido.
    for i in range(len(ts) - 1):
        ax.plot(xs[i:i+2], ys[i:i+2],
                color=plt.cm.cool(i / max(len(ts) - 1, 1)), linewidth=1.8)
    ax.plot([xs[0]], [ys[0]], "o", color="#7bed9f", markersize=8, label="inicio")
    ax.plot([xs[-1]], [ys[-1]], "s", color="#ff6b81", markersize=8, label="fin")
    ax.set_aspect("equal", adjustable="datalim")
    _estilo(ax, titulo or f"Paramétrica ({parametro})", "x(t)", "y(t)")
    ax.legend(facecolor=_PANEL, edgecolor=_REJILLA, labelcolor=_TINTA, fontsize=9)
    fig.tight_layout()
    out = carpeta or carpeta_salida(titulo or "parametrica")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)
    datos = {"tipo": "2d", "x": xs.tolist(),
             "series": [{"nombre": f"({fx}, {fy})", "y": ys.tolist()}]}
    return {"png": png, "html": visor_web(datos, os.path.join(out, "visor.html"),
                                          titulo or "Paramétrica"),
            "carpeta": out, "notas": [], "datos": datos}


def grafica_polar(expr: str, rango=(0, 6.283185307), titulo: str = "",
                  carpeta: str = "", puntos: int = 2000) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp
    th = sp.Symbol("theta")
    e = sympificar(expr, {"theta": th})
    ts = np.linspace(float(rango[0]), float(rango[1]), puntos)
    r = _f_numerica(e, (th,))(ts)
    fig = plt.figure(figsize=(8.5, 8.5), dpi=200, facecolor=_FONDO)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(_PANEL)
    ax.plot(ts, r, color=_ACENTO[0], linewidth=2.0)
    ax.fill(ts, r, color=_ACENTO[0], alpha=0.15)
    ax.tick_params(colors=_TINTA, labelsize=8)
    ax.grid(color=_REJILLA, alpha=0.8)
    ax.set_title(titulo or f"r(θ) = {bonito(e)}", color=_ACENTO[0], pad=18)
    out = carpeta or carpeta_salida(titulo or "polar")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)
    return {"png": png, "html": "", "carpeta": out, "notas": [], "datos": {}}


def grafica_datos(valores, etiquetas=None, clase: str = "auto", titulo: str = "",
                  carpeta: str = "", ajuste: str = "") -> dict:
    """Barras, histograma, dispersión con recta o parábola de ajuste, o caja."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    v = np.asarray(valores, dtype=float)
    fig, ax = plt.subplots(figsize=(10.5, 6.2), dpi=200, facecolor=_FONDO)
    notas = []
    if clase == "auto":
        clase = ("dispersion" if v.ndim == 2 and v.shape[0] == 2
                 else "barras" if etiquetas else "histograma")
    if clase == "barras":
        ax.bar(etiquetas or range(len(v)), v, color=_ACENTO[0], edgecolor=_ACENTO[3],
               linewidth=0.8)
        for i, val in enumerate(v):
            ax.annotate(f"{val:g}", (i, val), ha="center", va="bottom",
                        color=_TINTA, fontsize=8)
    elif clase == "histograma":
        n = max(6, int(math.sqrt(len(v))) + 1)
        ax.hist(v, bins=n, color=_ACENTO[0], edgecolor=_FONDO, alpha=0.9)
        ax.axvline(float(v.mean()), color=_ACENTO[3], linestyle="--",
                   label=f"media {v.mean():.4g}")
        ax.axvline(float(np.median(v)), color=_ACENTO[2], linestyle=":",
                   label=f"mediana {np.median(v):.4g}")
        ax.legend(facecolor=_PANEL, edgecolor=_REJILLA, labelcolor=_TINTA, fontsize=9)
    elif clase == "caja":
        bp = ax.boxplot(v if v.ndim > 1 else [v], patch_artist=True, vert=True)
        for caja in bp["boxes"]:
            caja.set(facecolor=_ACENTO[0], alpha=0.55)
    else:                                        # dispersión
        xs, ys = (v[0], v[1]) if v.ndim == 2 else (np.arange(len(v)), v)
        ax.scatter(xs, ys, s=34, color=_ACENTO[0], edgecolor="white", linewidth=0.5, zorder=3)
        if ajuste in ("lineal", "recta", "auto", ""):
            m, b0 = np.polyfit(xs, ys, 1)
            xx = np.linspace(xs.min(), xs.max(), 200)
            r = float(np.corrcoef(xs, ys)[0, 1])
            ax.plot(xx, m * xx + b0, color=_ACENTO[1], linewidth=2,
                    label=f"y = {m:.4g}x + {b0:.4g}   (r = {r:.4f}, R² = {r*r:.4f})")
            notas.append(f"recta de regresión y = {m:.6g}x + {b0:.6g}, R² = {r*r:.4f}")
        elif ajuste in ("cuadratico", "parabola"):
            c = np.polyfit(xs, ys, 2)
            xx = np.linspace(xs.min(), xs.max(), 300)
            ax.plot(xx, np.polyval(c, xx), color=_ACENTO[1], linewidth=2,
                    label=f"y = {c[0]:.4g}x² + {c[1]:.4g}x + {c[2]:.4g}")
            notas.append("ajuste cuadrático")
        ax.legend(facecolor=_PANEL, edgecolor=_REJILLA, labelcolor=_TINTA, fontsize=9)
    _estilo(ax, titulo or "Datos", "", "")
    fig.tight_layout()
    out = carpeta or carpeta_salida(titulo or "datos")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)
    return {"png": png, "html": "", "carpeta": out, "notas": notas, "datos": {}}


def campo_direcciones(expr: str, rango=(-4, 4), rango_y=(-4, 4), titulo: str = "",
                      carpeta: str = "", n: int = 26) -> dict:
    """Campo de pendientes de y' = f(x,y), con algunas soluciones dibujadas."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp
    x, y = sp.symbols("x y")
    e = sympificar(expr, {"x": x, "y": y})
    X, Y = np.meshgrid(np.linspace(*rango, n), np.linspace(*rango_y, n))
    P = _f_numerica(e, (x, y))(X, Y)
    U = 1.0 / np.sqrt(1 + P**2)
    V = P * U
    fig, ax = plt.subplots(figsize=(9.5, 8), dpi=200, facecolor=_FONDO)
    ax.quiver(X, Y, U, V, np.hypot(U, V), cmap="cool", pivot="mid",
              scale=n * 1.6, width=0.0028)
    # Curvas integrales por Euler mejorado desde varias condiciones iniciales.
    for y0 in np.linspace(rango_y[0] * 0.8, rango_y[1] * 0.8, 7):
        for sentido in (1, -1):
            xs, ys = [0.0], [float(y0)]
            h = sentido * (rango[1] - rango[0]) / 900
            for _ in range(900):
                xa, ya = xs[-1], ys[-1]
                try:
                    k1 = float(e.subs({x: xa, y: ya}))
                    k2 = float(e.subs({x: xa + h, y: ya + h * k1}))
                except Exception:
                    break
                xn, yn = xa + h, ya + h * (k1 + k2) / 2
                if not (rango[0] <= xn <= rango[1]) or abs(yn) > abs(rango_y[1]) * 3:
                    break
                xs.append(xn)
                ys.append(yn)
            ax.plot(xs, ys, color=_ACENTO[1], linewidth=1.1, alpha=0.75)
    ax.set_xlim(*rango)
    ax.set_ylim(*rango_y)
    _estilo(ax, titulo or f"y′ = {bonito(e)}", "x", "y")
    fig.tight_layout()
    out = carpeta or carpeta_salida(titulo or "campo")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)
    return {"png": png, "html": "", "carpeta": out, "notas": [], "datos": {}}


# ── mallas: la gráfica como objeto 3D de verdad ────────────────────────────
def exportar_obj(vertices, caras, ruta: str, nombre: str = "grafica") -> str:
    """Wavefront .obj. Acepta triángulos y cuadriláteros."""
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(f"# {nombre} - JARVIS\no {nombre}\n")
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for c in caras:
            f.write("f " + " ".join(str(i + 1) for i in c) + "\n")
    return ruta


def _triangular(caras) -> list:
    tri = []
    for c in caras:
        if len(c) == 3:
            tri.append(tuple(c))
        elif len(c) == 4:
            tri.append((c[0], c[1], c[2]))
            tri.append((c[0], c[2], c[3]))
        elif len(c) > 4:
            for i in range(1, len(c) - 1):
                tri.append((c[0], c[i], c[i + 1]))
    return tri


def exportar_stl(vertices, caras, ruta: str, nombre: str = "grafica") -> str:
    """STL binario: lo que traga cualquier laminador de impresión 3D."""
    tri = _triangular(caras)
    with open(ruta, "wb") as f:
        f.write(nombre.encode("ascii", "replace")[:80].ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tri)))
        for a, b, c in tri:
            p, q, r = vertices[a], vertices[b], vertices[c]
            ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
            vx, vy, vz = r[0] - p[0], r[1] - p[1], r[2] - p[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            f.write(struct.pack("<3f", nx / L, ny / L, nz / L))
            for w in (p, q, r):
                f.write(struct.pack("<3f", float(w[0]), float(w[1]), float(w[2])))
            f.write(struct.pack("<H", 0))
    return ruta


def _malla_de_rejilla(X, Y, Z):
    """Rejilla (n×m) de numpy -> (vertices, caras) saltándose los NaN."""
    import numpy as np
    n, m = Z.shape
    idx = -np.ones((n, m), dtype=int)
    verts, k = [], 0
    for i in range(n):
        for j in range(m):
            if np.isfinite(Z[i, j]):
                verts.append((float(X[i, j]), float(Y[i, j]), float(Z[i, j])))
                idx[i, j] = k
                k += 1
    caras = []
    for i in range(n - 1):
        for j in range(m - 1):
            a, b, c, d = idx[i, j], idx[i, j + 1], idx[i + 1, j + 1], idx[i + 1, j]
            if min(a, b, c, d) >= 0:
                caras.append((int(a), int(b), int(c), int(d)))
    return verts, caras


def _surface_nets(F, limites, n: int = 48, nivel: float = 0.0):
    """Isosuperficie F(x,y,z)=nivel por «surface nets» ingenuo.

    Da una malla suave sin depender de scikit-image: en cada celda con cambio
    de signo se coloca UN vértice en el centroide de los cortes de sus aristas,
    y luego se cosen los cuadriláteros alrededor de cada arista que cruza.
    """
    import numpy as np
    (x0, x1), (y0, y1), (z0, z1) = limites
    n = max(16, min(int(n), 96))
    xs = np.linspace(float(x0), float(x1), n + 1)
    ys = np.linspace(float(y0), float(y1), n + 1)
    zs = np.linspace(float(z0), float(z1), n + 1)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    with np.errstate(all="ignore"):
        V = np.asarray(F(X, Y, Z), dtype=float) - nivel
    V[~np.isfinite(V)] = np.nan
    S = V > 0
    # Aristas de la rejilla que cruzan el nivel, por dirección.
    cruza = [np.zeros((n + 1, n + 1, n + 1), dtype=bool) for _ in range(3)]
    cruza[0][:-1, :, :] = S[:-1, :, :] != S[1:, :, :]
    cruza[1][:, :-1, :] = S[:, :-1, :] != S[:, 1:, :]
    cruza[2][:, :, :-1] = S[:, :, :-1] != S[:, :, 1:]
    finito = np.isfinite(V)
    cruza[0][:-1, :, :] &= finito[:-1, :, :] & finito[1:, :, :]
    cruza[1][:, :-1, :] &= finito[:, :-1, :] & finito[:, 1:, :]
    cruza[2][:, :, :-1] &= finito[:, :, :-1] & finito[:, :, 1:]

    ARISTAS = [((0, 0, 0), 0), ((0, 1, 0), 0), ((0, 0, 1), 0), ((0, 1, 1), 0),
               ((0, 0, 0), 1), ((1, 0, 0), 1), ((0, 0, 1), 1), ((1, 0, 1), 1),
               ((0, 0, 0), 2), ((1, 0, 0), 2), ((0, 1, 0), 2), ((1, 1, 0), 2)]
    paso = (xs[1] - xs[0], ys[1] - ys[0], zs[1] - zs[0])
    eje_g = (xs, ys, zs)
    idx = {}
    verts = []
    for i in range(n):
        for j in range(n):
            for k in range(n):
                acum, cuenta = [0.0, 0.0, 0.0], 0
                for (dx, dy, dz), eje in ARISTAS:
                    ii, jj, kk = i + dx, j + dy, k + dz
                    if not cruza[eje][ii, jj, kk]:
                        continue
                    p = [float(xs[ii]), float(ys[jj]), float(zs[kk])]
                    va = float(V[ii, jj, kk])
                    nb = [ii, jj, kk]
                    nb[eje] += 1
                    vb = float(V[nb[0], nb[1], nb[2]])
                    t = 0.5 if (va - vb) == 0 else va / (va - vb)
                    t = min(max(t, 0.0), 1.0)
                    p[eje] += t * paso[eje]
                    acum[0] += p[0]
                    acum[1] += p[1]
                    acum[2] += p[2]
                    cuenta += 1
                if cuenta:
                    idx[(i, j, k)] = len(verts)
                    verts.append((acum[0] / cuenta, acum[1] / cuenta, acum[2] / cuenta))
    caras = []
    # Cada arista interior que cruza cose las 4 celdas que la rodean.
    vecinos = {0: [(0, -1, -1), (0, 0, -1), (0, 0, 0), (0, -1, 0)],
               1: [(-1, 0, -1), (-1, 0, 0), (0, 0, 0), (0, 0, -1)],
               2: [(-1, -1, 0), (0, -1, 0), (0, 0, 0), (-1, 0, 0)]}
    for eje in range(3):
        ii, jj, kk = np.nonzero(cruza[eje])
        for a, b, c in zip(ii.tolist(), jj.tolist(), kk.tolist()):
            quad = []
            for dx, dy, dz in vecinos[eje]:
                celda = (a + dx, b + dy, c + dz)
                v = idx.get(celda)
                if v is None:
                    quad = []
                    break
                quad.append(v)
            if not quad:
                continue
            # Orientación: la normal debe apuntar hacia donde F crece.
            if bool(S[a, b, c]):
                quad.reverse()
            caras.append(tuple(quad))
    return verts, caras


def _f_numerica3(expr, vars_):
    import numpy as np
    import sympy as sp
    f = sp.lambdify(vars_, expr, modules="numpy")

    def segura(X, Y, Z):
        with np.errstate(all="ignore"):
            try:
                r = f(X, Y, Z)
            except Exception:
                r = np.full_like(X, np.nan, dtype=float)
            return np.asarray(r, dtype=float) + np.zeros_like(X, dtype=float)
    return segura


def _estilo3d(ax, titulo: str = ""):
    """Paneles oscuros y ejes en cian: el 3D de matplotlib viene en gris claro."""
    ax.set_facecolor(_FONDO)
    for eje in ("xaxis", "yaxis", "zaxis"):
        a = getattr(ax, eje)
        try:
            a.set_pane_color((0.02, 0.035, 0.055, 1.0))
            a.pane.set_edgecolor(_REJILLA)
            a._axinfo["grid"].update(color=_REJILLA, linewidth=0.5)
        except Exception:
            pass
        a.set_tick_params(colors=_TINTA, labelsize=7)
        a.label.set_color(_TINTA)
    if titulo:
        ax.set_title(titulo, color=_ACENTO[0], fontsize=12)


# ── gráficas 3D ────────────────────────────────────────────────────────────
def superficie_3d(expr, rango_x=(-5, 5), rango_y=(-5, 5), titulo: str = "",
                  carpeta: str = "", n: int = 140, curvas_nivel: bool = True,
                  log=print) -> dict:
    """z = f(x,y): lámina con mapa de color, curvas de nivel, malla y visor."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp

    x, y = sp.symbols("x y")
    e = expr if hasattr(expr, "free_symbols") else sympificar(str(expr), {"x": x, "y": y})
    n = max(40, min(int(n), 240))
    xs = np.linspace(float(rango_x[0]), float(rango_x[1]), n)
    ys = np.linspace(float(rango_y[0]), float(rango_y[1]), n)
    X, Y = np.meshgrid(xs, ys)
    Z = _f_numerica(e, (x, y))(X, Y)
    # Recorte robusto: un polo no debe aplastar toda la superficie.
    finitos = Z[np.isfinite(Z)]
    if finitos.size:
        lo, hi = np.percentile(finitos, 0.5), np.percentile(finitos, 99.5)
        if hi > lo:
            Z = np.clip(Z, lo, hi)

    fig = plt.figure(figsize=(13, 7.4), dpi=190, facecolor=_FONDO)
    ax = fig.add_subplot(121, projection="3d")
    ax.set_facecolor(_FONDO)
    sup = ax.plot_surface(X, Y, Z, cmap="turbo", linewidth=0, antialiased=True,
                          rstride=1, cstride=1, alpha=0.96)
    paso = max(1, n // 26)
    ax.plot_wireframe(X, Y, Z, rstride=paso, cstride=paso,
                      color="#0a1620", linewidth=0.35, alpha=0.55)
    if curvas_nivel and finitos.size:
        try:
            ax.contour(X, Y, Z, zdir="z", offset=float(np.nanmin(Z)), cmap="cool",
                       levels=14, linewidths=0.8)
        except Exception:
            pass
    for eje in ("x", "y", "z"):
        getattr(ax, f"set_{eje}label")(eje, color=_TINTA)
    _estilo3d(ax, titulo or f"z = {bonito(e)}")
    cb = fig.colorbar(sup, ax=ax, shrink=0.62, pad=0.09)
    cb.ax.tick_params(colors=_TINTA, labelsize=7)
    cb.outline.set_edgecolor(_REJILLA)

    ax2 = fig.add_subplot(122)
    cf = ax2.contourf(X, Y, Z, levels=40, cmap="turbo")
    cl = ax2.contour(X, Y, Z, levels=14, colors="#04060a", linewidths=0.5)
    ax2.clabel(cl, inline=True, fontsize=6, colors=_TINTA)
    _estilo(ax2, "Mapa de nivel (vista cenital)", "x", "y")
    cb2 = fig.colorbar(cf, ax=ax2, shrink=0.85)
    cb2.ax.tick_params(colors=_TINTA, labelsize=7)
    fig.tight_layout()

    out = carpeta or carpeta_salida(titulo or "superficie")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)

    verts, caras = _malla_de_rejilla(X, Y, Z)
    obj = exportar_obj(verts, caras, os.path.join(out, "malla.obj"), "superficie")
    stl = exportar_stl(verts, caras, os.path.join(out, "malla.stl"), "superficie")
    datos = {"tipo": "3d", "vertices": verts, "caras": _triangular(caras),
             "titulo": titulo or f"z = {bonito(e)}"}
    html = visor_web(datos, os.path.join(out, "visor.html"), titulo or "Superficie")
    notas = []
    if finitos.size:
        notas = [f"máximo muestreado z = {float(np.nanmax(Z)):.6g}",
                 f"mínimo muestreado z = {float(np.nanmin(Z)):.6g}",
                 f"malla de {len(verts)} vértices y {len(caras)} caras"]
    return {"png": png, "html": html, "obj": obj, "stl": stl, "carpeta": out,
            "notas": notas, "datos": datos}


def superficie_parametrica(fx: str, fy: str, fz: str, rango_u=(0, 6.283185307),
                           rango_v=(0, 3.141592653), titulo: str = "",
                           carpeta: str = "", n: int = 120) -> dict:
    """Superficie (u,v): esferas, toros, cintas de Möbius, superficies regladas."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp
    u, v = sp.symbols("u v")
    ex = [sympificar(s, {"u": u, "v": v}) for s in (fx, fy, fz)]
    n = max(30, min(int(n), 200))
    U, V = np.meshgrid(np.linspace(float(rango_u[0]), float(rango_u[1]), n),
                       np.linspace(float(rango_v[0]), float(rango_v[1]), n))
    X, Y, Z = [_f_numerica(e, (u, v))(U, V) for e in ex]
    fig = plt.figure(figsize=(9.5, 8.5), dpi=190, facecolor=_FONDO)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(_FONDO)
    ax.plot_surface(X, Y, Z, cmap="turbo", linewidth=0, antialiased=True,
                    rstride=1, cstride=1, alpha=0.97)
    paso = max(1, n // 24)
    ax.plot_wireframe(X, Y, Z, rstride=paso, cstride=paso, color="#05121c",
                      linewidth=0.35, alpha=0.6)
    _estilo3d(ax, titulo or "Superficie paramétrica")
    try:
        ax.set_box_aspect((float(np.ptp(X)), float(np.ptp(Y)), float(np.ptp(Z))))
    except Exception:
        pass
    out = carpeta or carpeta_salida(titulo or "parametrica3d")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)
    verts, caras = _malla_de_rejilla(X, Y, Z)
    obj = exportar_obj(verts, caras, os.path.join(out, "malla.obj"), "parametrica")
    stl = exportar_stl(verts, caras, os.path.join(out, "malla.stl"), "parametrica")
    datos = {"tipo": "3d", "vertices": verts, "caras": _triangular(caras),
             "titulo": titulo or "Superficie paramétrica"}
    return {"png": png, "html": visor_web(datos, os.path.join(out, "visor.html"),
                                          titulo or "Paramétrica"),
            "obj": obj, "stl": stl, "carpeta": out,
            "notas": [f"malla de {len(verts)} vértices"], "datos": datos}


def _tubo(P, radio: float = 0.05, lados: int = 10):
    """Convierte una polilínea en un tubo cerrado: ya es un sólido imprimible."""
    import numpy as np
    P = np.asarray(P, dtype=float)
    P = P[np.all(np.isfinite(P), axis=1)]
    if len(P) < 2:
        return [], []
    esc = float(np.max(np.ptp(P, axis=0))) or 1.0
    r = radio * esc
    T = np.gradient(P, axis=0)
    T /= (np.linalg.norm(T, axis=1, keepdims=True) + 1e-12)
    N = np.cross(T, np.array([0.0, 0.0, 1.0]))
    malas = np.linalg.norm(N, axis=1) < 1e-6
    if malas.any():
        N[malas] = np.cross(T[malas], np.array([0.0, 1.0, 0.0]))
    N /= (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)
    B = np.cross(T, N)
    verts, caras = [], []
    ang = np.linspace(0, 2 * math.pi, lados, endpoint=False)
    for i in range(len(P)):
        for a in ang:
            verts.append(tuple(P[i] + r * (math.cos(a) * N[i] + math.sin(a) * B[i])))
    for i in range(len(P) - 1):
        for j in range(lados):
            a = i * lados + j
            b = i * lados + (j + 1) % lados
            caras.append((a, b, b + lados, a + lados))
    return verts, caras


def curva_3d(fx: str, fy: str, fz: str, rango=(0, 12.566370614), titulo: str = "",
             carpeta: str = "", puntos: int = 1600, grosor: float = 0.02) -> dict:
    """Curva en el espacio. Se exporta como TUBO, para que sea imprimible."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp
    t = sp.Symbol("t")
    ex = [sympificar(s, {"t": t}) for s in (fx, fy, fz)]
    ts = np.linspace(float(rango[0]), float(rango[1]), int(puntos))
    P = np.stack([_f_numerica(e, (t,))(ts) for e in ex], axis=1)
    fig = plt.figure(figsize=(9.5, 8.5), dpi=190, facecolor=_FONDO)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(_FONDO)
    col = plt.cm.turbo(np.linspace(0, 1, max(len(ts) - 1, 1)))
    for i in range(0, len(ts) - 1):
        ax.plot(P[i:i+2, 0], P[i:i+2, 1], P[i:i+2, 2], color=col[i], linewidth=1.8)
    ax.scatter(*P[0], color="#7bed9f", s=45)
    ax.scatter(*P[-1], color="#ff6b81", s=45)
    _estilo3d(ax, titulo or "Curva en el espacio")
    out = carpeta or carpeta_salida(titulo or "curva3d")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)
    verts, caras = _tubo(P, grosor)
    obj = exportar_obj(verts, caras, os.path.join(out, "malla.obj"), "curva") if verts else ""
    stl = exportar_stl(verts, caras, os.path.join(out, "malla.stl"), "curva") if verts else ""
    datos = {"tipo": "3d", "vertices": verts, "caras": _triangular(caras),
             "lineas": [[[float(c) for c in p] for p in P if np.all(np.isfinite(p))]],
             "titulo": titulo or "Curva en el espacio"}
    return {"png": png, "html": visor_web(datos, os.path.join(out, "visor.html"),
                                          titulo or "Curva 3D"),
            "obj": obj, "stl": stl, "carpeta": out,
            "notas": [f"{len(ts)} puntos de curva"], "datos": datos}


def implicita_3d(expr, limites=((-3, 3), (-3, 3), (-3, 3)), titulo: str = "",
                 carpeta: str = "", n: int = 52, nivel: float = 0.0) -> dict:
    """F(x,y,z)=0: cuádricas, toros, superficies de nivel, orbitales."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    x, y, z = sp.symbols("x y z")
    e = expr if hasattr(expr, "free_symbols") else sympificar(str(expr),
                                                              {"x": x, "y": y, "z": z})
    F = _f_numerica3(e, (x, y, z))
    verts, caras = _surface_nets(F, limites, n=n, nivel=nivel)
    out = carpeta or carpeta_salida(titulo or "implicita")
    if not verts:
        return {"png": "", "html": "", "obj": "", "stl": "", "carpeta": out,
                "notas": ["La superficie no corta la caja: pruebe con otro rango."],
                "datos": {}}
    V = np.asarray(verts)
    tri = _triangular(caras)
    fig = plt.figure(figsize=(9.5, 8.5), dpi=190, facecolor=_FONDO)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(_FONDO)
    alt = V[:, 2]
    norm = (alt - alt.min()) / (float(np.ptp(alt)) or 1.0)
    T = np.asarray(tri)
    pc = Poly3DCollection(V[T], facecolors=plt.cm.turbo(norm[T[:, 0]]),
                          edgecolors="#06131d", linewidths=0.08, alpha=0.97)
    ax.add_collection3d(pc)
    for eje, lim in zip("xyz", limites):
        getattr(ax, f"set_{eje}lim")(float(lim[0]), float(lim[1]))
        getattr(ax, f"set_{eje}label")(eje, color=_TINTA)
    _estilo3d(ax, titulo or f"{bonito(e)} = {nivel:g}")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)
    obj = exportar_obj(verts, caras, os.path.join(out, "malla.obj"), "implicita")
    stl = exportar_stl(verts, caras, os.path.join(out, "malla.stl"), "implicita")
    datos = {"tipo": "3d", "vertices": verts, "caras": tri,
             "titulo": titulo or f"{bonito(e)} = 0"}
    return {"png": png, "html": visor_web(datos, os.path.join(out, "visor.html"),
                                          titulo or "Superficie implícita"),
            "obj": obj, "stl": stl, "carpeta": out,
            "notas": [f"malla de {len(verts)} vértices y {len(tri)} triángulos"],
            "datos": datos}


def campo_vectorial_3d(fx: str, fy: str, fz: str, limites=((-3, 3), (-3, 3), (-3, 3)),
                       titulo: str = "", carpeta: str = "", n: int = 9) -> dict:
    """Campo F(x,y,z) con flechas coloreadas por módulo. Física pura."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import sympy as sp
    x, y, z = sp.symbols("x y z")
    ex = [sympificar(s, {"x": x, "y": y, "z": z}) for s in (fx, fy, fz)]
    g = [np.linspace(float(lim[0]), float(lim[1]), n) for lim in limites]
    X, Y, Z = np.meshgrid(*g, indexing="ij")
    U, V, W = [_f_numerica3(e, (x, y, z))(X, Y, Z) for e in ex]
    M = np.sqrt(U**2 + V**2 + W**2)
    M[~np.isfinite(M)] = 0
    U, V, W = [np.nan_to_num(a) for a in (U, V, W)]
    fig = plt.figure(figsize=(9.5, 8.5), dpi=190, facecolor=_FONDO)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(_FONDO)
    ax.quiver(X, Y, Z, U, V, W, length=0.6, normalize=True,
              color=plt.cm.turbo((M / (M.max() or 1)).ravel()), linewidth=0.9)
    _estilo3d(ax, titulo or f"F = ({bonito(ex[0])}, {bonito(ex[1])}, {bonito(ex[2])})")
    out = carpeta or carpeta_salida(titulo or "campo3d")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=_FONDO)
    plt.close(fig)
    div = sp.simplify(sp.diff(ex[0], x) + sp.diff(ex[1], y) + sp.diff(ex[2], z))
    rot = [sp.simplify(sp.diff(ex[2], y) - sp.diff(ex[1], z)),
           sp.simplify(sp.diff(ex[0], z) - sp.diff(ex[2], x)),
           sp.simplify(sp.diff(ex[1], x) - sp.diff(ex[0], y))]
    notas = [f"divergencia ∇·F = {bonito(div)}",
             f"rotacional ∇×F = ({bonito(rot[0])}, {bonito(rot[1])}, {bonito(rot[2])})"]
    return {"png": png, "html": "", "obj": "", "stl": "", "carpeta": out,
            "notas": notas, "datos": {}}


# ── visor web: la gráfica que se puede girar ───────────────────────────────
_VISOR_2D = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITULO__</title>
<style>html,body{margin:0;height:100%;background:#04060a;color:#cfe9f5;
font-family:system-ui,Segoe UI,sans-serif;overflow:hidden}
#cab{position:fixed;top:0;left:0;right:0;padding:10px 16px;font-size:13px;
letter-spacing:.14em;text-transform:uppercase;color:#2ec6ff;z-index:5}
#lec{position:fixed;right:16px;bottom:16px;font-size:12px;color:#9fdcff;
background:#080d14cc;border:1px solid #123043;padding:6px 10px;border-radius:6px}
canvas{display:block}</style></head><body>
<div id="cab">JARVIS · __TITULO__</div><canvas id="c"></canvas>
<div id="lec">mueve el ratón para leer la curva · rueda para acercar</div>
<script>
const D=__DATOS__;
const c=document.getElementById('c'),g=c.getContext('2d');
let zoom=1,offx=0,offy=0,arrastra=null;
const COL=['#2ec6ff','#ff9f43','#7bed9f','#ff6b81','#c56cf0','#ffd166','#4ecdc4'];
function ext(){let x0=Math.min(...D.x),x1=Math.max(...D.x),y0=1e30,y1=-1e30;
 for(const s of D.series)for(const v of s.y){if(v==null||!isFinite(v))continue;
  if(v<y0)y0=v;if(v>y1)y1=v;}
 if(y0>y1){y0=-1;y1=1;}
 const vals=[];for(const s of D.series)for(const v of s.y)if(v!=null&&isFinite(v))vals.push(v);
 vals.sort((a,b)=>a-b);
 if(vals.length>20){y0=vals[Math.floor(vals.length*0.01)];y1=vals[Math.floor(vals.length*0.99)];}
 const m=(y1-y0)*0.08||1;return[x0,x1,y0-m,y1+m];}
let E=ext();
function px(x){return (x-(E[0]+E[1])/2)*zoom*c.width/((E[1]-E[0])||1)+c.width/2+offx;}
function py(y){return c.height/2-(y-(E[2]+E[3])/2)*zoom*c.height/((E[3]-E[2])||1)+offy;}
function ix(p){return (p-c.width/2-offx)*((E[1]-E[0])||1)/(zoom*c.width)+(E[0]+E[1])/2;}
function rejilla(){g.strokeStyle='#123043';g.lineWidth=1;g.font='11px system-ui';
 g.fillStyle='#5f8ea3';
 const pasoX=paso((E[1]-E[0])/zoom/10),pasoY=paso((E[3]-E[2])/zoom/8);
 for(let x=Math.ceil(E[0]/pasoX)*pasoX;x<=E[1];x+=pasoX){const X=px(x);
  if(X<0||X>c.width)continue;g.beginPath();g.moveTo(X,0);g.lineTo(X,c.height);g.stroke();
  g.fillText(x.toPrecision(3),X+3,py(0)+13);}
 for(let y=Math.ceil(E[2]/pasoY)*pasoY;y<=E[3];y+=pasoY){const Y=py(y);
  if(Y<0||Y>c.height)continue;g.beginPath();g.moveTo(0,Y);g.lineTo(c.width,Y);g.stroke();
  g.fillText(y.toPrecision(3),px(0)+4,Y-3);}
 g.strokeStyle='#cfe9f5';g.lineWidth=1.4;
 g.beginPath();g.moveTo(0,py(0));g.lineTo(c.width,py(0));g.stroke();
 g.beginPath();g.moveTo(px(0),0);g.lineTo(px(0),c.height);g.stroke();}
function paso(v){const e=Math.pow(10,Math.floor(Math.log10(Math.abs(v)||1)));
 const n=v/e;return (n<2?1:n<5?2:5)*e;}
let raton=null;
function pinta(){c.width=innerWidth;c.height=innerHeight;
 g.fillStyle='#04060a';g.fillRect(0,0,c.width,c.height);rejilla();
 D.series.forEach((s,i)=>{g.strokeStyle=COL[i%COL.length];g.lineWidth=2;g.beginPath();
  let corta=true;
  for(let k=0;k<D.x.length;k++){const v=s.y[k];
   if(v==null||!isFinite(v)){corta=true;continue;}
   const X=px(D.x[k]),Y=py(v);
   if(Y<-4000||Y>c.height+4000){corta=true;continue;}
   if(corta){g.moveTo(X,Y);corta=false;}else g.lineTo(X,Y);}
  g.stroke();
  g.fillStyle=COL[i%COL.length];g.font='13px system-ui';
  g.fillText(s.nombre,16,60+i*20);});
 if(raton!==null){const xv=ix(raton);
  g.strokeStyle='#ffffff44';g.beginPath();g.moveTo(raton,0);g.lineTo(raton,c.height);g.stroke();
  let k=0,mej=1e30;
  for(let j=0;j<D.x.length;j++){const d=Math.abs(D.x[j]-xv);if(d<mej){mej=d;k=j;}}
  let txt='x = '+D.x[k].toPrecision(5);
  D.series.forEach((s,i)=>{const v=s.y[k];
   txt+='   ·   '+s.nombre+' = '+(v==null||!isFinite(v)?'—':Number(v).toPrecision(5));
   if(v!=null&&isFinite(v)){g.fillStyle=COL[i%COL.length];
    g.beginPath();g.arc(px(D.x[k]),py(v),4,0,7);g.fill();}});
  document.getElementById('lec').textContent=txt;}}
addEventListener('resize',pinta);
c.addEventListener('mousemove',e=>{if(arrastra){offx+=e.clientX-arrastra[0];
 offy+=e.clientY-arrastra[1];arrastra=[e.clientX,e.clientY];}raton=e.clientX;pinta();});
c.addEventListener('mousedown',e=>arrastra=[e.clientX,e.clientY]);
addEventListener('mouseup',()=>arrastra=null);
c.addEventListener('wheel',e=>{e.preventDefault();
 zoom*=e.deltaY<0?1.15:1/1.15;pinta();},{passive:false});
pinta();
</script></body></html>"""

_VISOR_3D = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITULO__</title>
<style>html,body{margin:0;height:100%;background:#04060a;overflow:hidden;
font-family:system-ui,Segoe UI,sans-serif}
#cab{position:fixed;top:0;left:0;padding:10px 16px;color:#2ec6ff;font-size:13px;
letter-spacing:.14em;text-transform:uppercase;z-index:5}
#ctl{position:fixed;left:16px;bottom:16px;display:flex;gap:8px;z-index:5}
button{background:#080d14;color:#9fdcff;border:1px solid #123043;padding:7px 12px;
border-radius:6px;font-size:12px;cursor:pointer;letter-spacing:.06em}
button:hover{border-color:#2ec6ff;color:#fff}
#pie{position:fixed;right:16px;bottom:16px;color:#5f8ea3;font-size:11px}</style>
<script type="importmap">
{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}
</script></head><body>
<div id="cab">JARVIS · __TITULO__</div>
<div id="ctl"><button id="b1">malla</button><button id="b2">girar</button>
<button id="b3">ejes</button><button id="b4">encuadrar</button></div>
<div id="pie">arrastra para orbitar · rueda para acercar · botón derecho para desplazar</div>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const D=__DATOS__;
const S=new THREE.Scene();S.background=new THREE.Color(0x04060a);
S.fog=new THREE.FogExp2(0x04060a,0.012);
const C=new THREE.PerspectiveCamera(50,innerWidth/innerHeight,0.01,5000);
const R=new THREE.WebGLRenderer({antialias:true});R.setPixelRatio(devicePixelRatio);
R.setSize(innerWidth,innerHeight);document.body.appendChild(R.domElement);
const ctr=new OrbitControls(C,R.domElement);ctr.enableDamping=true;
// Luz contenida: con más, los colores propios de la malla (altura, o el
// código CPK de los átomos) se lavan y todo sale blanco.
S.add(new THREE.HemisphereLight(0x9fe4ff,0x061018,0.55));
const dl=new THREE.DirectionalLight(0xffffff,0.95);dl.position.set(4,8,6);S.add(dl);
const dl2=new THREE.DirectionalLight(0x66d9ff,0.35);dl2.position.set(-5,2,-4);S.add(dl2);
const grupo=new THREE.Group();S.add(grupo);
const V=D.vertices||[],F=D.caras||[];
let malla=null,alambre=null;
if(V.length&&F.length){
 const pos=new Float32Array(V.length*3),col=new Float32Array(V.length*3);
 let zmin=1e30,zmax=-1e30;
 for(const v of V){if(v[2]<zmin)zmin=v[2];if(v[2]>zmax)zmax=v[2];}
 const rango=(zmax-zmin)||1;
 const c=new THREE.Color();
 const CC=D.colores||null;
 for(let i=0;i<V.length;i++){pos[i*3]=V[i][0];pos[i*3+1]=V[i][2];pos[i*3+2]=V[i][1];
  if(CC){col[i*3]=CC[i][0];col[i*3+1]=CC[i][1];col[i*3+2]=CC[i][2];}
  else{c.setHSL(0.72-0.72*((V[i][2]-zmin)/rango),0.85,0.55);
   col[i*3]=c.r;col[i*3+1]=c.g;col[i*3+2]=c.b;}}
 const idx=new Uint32Array(F.length*3);
 for(let i=0;i<F.length;i++){idx[i*3]=F[i][0];idx[i*3+1]=F[i][1];idx[i*3+2]=F[i][2];}
 const G=new THREE.BufferGeometry();
 G.setAttribute('position',new THREE.BufferAttribute(pos,3));
 G.setAttribute('color',new THREE.BufferAttribute(col,3));
 G.setIndex(new THREE.BufferAttribute(idx,1));G.computeVertexNormals();
 malla=new THREE.Mesh(G,new THREE.MeshStandardMaterial({vertexColors:true,
  side:THREE.DoubleSide,metalness:0.25,roughness:0.42,flatShading:false}));
 grupo.add(malla);
 alambre=new THREE.LineSegments(new THREE.WireframeGeometry(G),
  new THREE.LineBasicMaterial({color:0x0b2a3a,transparent:true,opacity:0.45}));
 alambre.visible=false;grupo.add(alambre);}
for(const L of (D.lineas||[])){
 const pts=L.map(p=>new THREE.Vector3(p[0],p[2],p[1]));
 grupo.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
  new THREE.LineBasicMaterial({color:0x2ec6ff})));}
let ejes=new THREE.Group();
const caja=new THREE.Box3().setFromObject(grupo);
const tam=caja.getSize(new THREE.Vector3()),cen=caja.getCenter(new THREE.Vector3());
const R0=Math.max(tam.x,tam.y,tam.z)||1;
ejes.add(new THREE.AxesHelper(R0*0.75));
const rej=new THREE.GridHelper(R0*2.4,24,0x123043,0x0a1c28);
rej.position.y=caja.min.y;ejes.add(rej);
ejes.position.copy(new THREE.Vector3(cen.x,0,cen.z));S.add(ejes);
function encuadrar(){C.position.set(cen.x+R0*1.15,cen.y+R0*0.85,cen.z+R0*1.3);
 ctr.target.copy(cen);ctr.update();}
encuadrar();
let gira=true;
document.getElementById('b1').onclick=()=>{if(alambre)alambre.visible=!alambre.visible;};
document.getElementById('b2').onclick=()=>gira=!gira;
document.getElementById('b3').onclick=()=>ejes.visible=!ejes.visible;
document.getElementById('b4').onclick=encuadrar;
addEventListener('resize',()=>{C.aspect=innerWidth/innerHeight;C.updateProjectionMatrix();
 R.setSize(innerWidth,innerHeight);});
(function bucle(){requestAnimationFrame(bucle);
 if(gira)grupo.rotation.y+=0.0022;ctr.update();R.render(S,C);})();
</script></body></html>"""


def visor_web(datos: dict, ruta_html: str, titulo: str = "Gráfica") -> str:
    """Escribe el visor interactivo con los datos EMBEBIDOS.

    Van dentro del HTML a propósito: abierto con file:// el navegador bloquea
    cualquier fetch a un archivo de al lado, así que un visor que cargue los
    datos aparte no funcionaría al hacer doble clic.
    """
    if not datos:
        return ""
    plantilla = _VISOR_3D if datos.get("tipo") == "3d" else _VISOR_2D
    crudo = json.dumps(datos, allow_nan=False, default=lambda o: None,
                       separators=(",", ":"))
    html = (plantilla.replace("__TITULO__", (titulo or "Gráfica").replace("<", ""))
                     .replace("__DATOS__", crudo))
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(html)
    return ruta_html


def abrir(ruta: str, log=print) -> bool:
    """Abre el resultado. Los .html van SIEMPRE al navegador."""
    import subprocess
    import sys
    try:
        if not ruta or not os.path.exists(ruta):
            return False
        if ruta.lower().endswith((".html", ".htm")):
            import webbrowser
            if webbrowser.open("file:///" + os.path.abspath(ruta).replace("\\", "/")):
                return True
        if hasattr(os, "startfile"):
            os.startfile(ruta)  # noqa: S606
            return True
        subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", ruta])
        return True
    except Exception as e:
        log(f"[MAT] no pude abrir {ruta}: {e}")
        return False


def a_holograma(core, ruta_malla: str, log=print) -> str:
    """Pasa la malla de la gráfica al pipeline de holograma de modelado3d."""
    try:
        import modelado3d
        if not modelado3d.disponible():
            return ""
        return modelado3d.holograma(core, ruta_malla, modo="completo", log=log)
    except Exception as e:
        log(f"[MAT] holograma de la gráfica falló: {e}")
        return ""
