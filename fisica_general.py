#!/usr/bin/env python3
"""
fisica_general.py - Cualquier ecuación, cualquier incógnita, con unidades
=========================================================================
`fisica.py` tiene un banco de 74 leyes y despeja de maravilla... **las 74**. En
una carrera de ingeniería eso se acaba en semanas: llega la ley que el profesor
escribió en la pizarra y que no está en ninguna lista, y el asistente se queda
mirando.

Esto quita ese techo. Se le da **la ecuación que sea** —dictada, copiada del
libro o inventada por el profesor— y despeja lo que falte:

    despejar("v = v0 + a*t", {"v0": "0 m/s", "a": "9.8 m/s^2", "t": "3 s"})
    -> v = 29.4 m/s

Tres cosas que un despeje a pelo no da y aquí sí:

**1. Unidades de verdad, no números sueltos.** Con `pint`: los datos entran con
su unidad, se convierten solas al sistema que haga falta y el resultado sale
con la suya. «2 km» y «2000 m» son el mismo dato, y se nota.

**2. Análisis dimensional.** Antes de resolver se comprueba que los dos lados
de la ecuación midan lo mismo. Media docena de errores de examen son sumar una
velocidad a una aceleración, y eso se caza aquí sin resolver nada:

    comprobar("E = m*v")  ->  no cuadra: [masa·longitud/tiempo] ≠ [energía]

**3. Despeje simbólico primero.** Se enseña la fórmula despejada ANTES de meter
números, que es lo que piden en los exámenes y lo que de verdad se aprende.

Todo con sympy y pint, en local, sin llamar a ningún modelo. Lo que sale de
aquí está calculado, no recordado.
"""
import re

import matematica as M

# Unidades escritas como se dictan, a como las entiende pint.
_ARREGLOS = (
    (r"\bmetros?\s+por\s+segundo\s+al\s+cuadrado\b", "m/s**2"),
    (r"\bmetros?\s+por\s+segundo\b", "m/s"),
    (r"\bkil[oó]metros?\s+por\s+hora\b", "km/hour"),
    (r"\bmetros?\s+cuadrados?\b", "m**2"),
    (r"\bmetros?\s+c[uú]bicos?\b", "m**3"),
    (r"\bkil[oó]gramos?\b", "kg"), (r"\bgramos?\b", "g"),
    (r"\bmetros?\b", "m"), (r"\bsegundos?\b", "s"), (r"\bminutos?\b", "min"),
    (r"\bhoras?\b", "hour"), (r"\bnewtons?\b", "N"), (r"\bjulios?\b", "J"),
    (r"\bvatios?\b", "W"), (r"\bvoltios?\b", "V"), (r"\bamperios?\b", "A"),
    (r"\bohmios?\b", "ohm"), (r"\bpascales?\b", "Pa"), (r"\bkelvin\b", "K"),
    (r"\bgrados?\s+cent[ií]grados?\b", "degC"), (r"\bcelsius\b", "degC"),
    (r"\bhercios?\b", "Hz"), (r"\bculombios?\b", "C"), (r"\bmoles?\b", "mol"),
    (r"\blitros?\b", "L"), (r"\bradianes?\b", "rad"),
    (r"\^", "**"),
)

_REGISTRO = None


def _ureg():
    """El registro de unidades, uno solo: crear uno por llamada cuesta medio
    segundo y, peor, hace que dos magnitudes no se puedan comparar entre sí."""
    global _REGISTRO
    if _REGISTRO is None:
        import pint
        _REGISTRO = pint.UnitRegistry()
    return _REGISTRO


def hay_unidades() -> bool:
    try:
        _ureg()
        return True
    except Exception:
        return False


# ── leer un dato con su unidad ──────────────────────────────────────────────
def magnitud(valor):
    """«9.8 m/s^2», «2 km», «30 grados centígrados» o un número pelado.

    Devuelve una cantidad de pint, o un float si no hay unidad. Un número sin
    unidad NO se rechaza: en clase se trabaja así la mitad del tiempo y obligar
    a ponerlas sería estorbar.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return None
    for patron, reemplazo in _ARREGLOS:
        texto = re.sub(patron, reemplazo, texto, flags=re.I)
    texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        pass
    if not hay_unidades():
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", texto)
        return float(m.group(1)) if m else None
    try:
        q = _ureg().Quantity(texto)
        return q if q.dimensionality else float(q.magnitude)
    except Exception:
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", texto)
        return float(m.group(1)) if m else None


def _numero(q) -> float:
    """El valor crudo, en unidades base del SI, para meterlo en sympy."""
    if q is None:
        return None
    if isinstance(q, (int, float)):
        return float(q)
    try:
        return float(q.to_base_units().magnitude)
    except Exception:
        try:
            return float(q.magnitude)
        except Exception:
            return None


def _unidad_base(q) -> str:
    if isinstance(q, (int, float)) or q is None:
        return ""
    try:
        return f"{q.to_base_units().units:~P}"
    except Exception:
        return ""


# ── la ecuación ─────────────────────────────────────────────────────────────
# Funciones que SÍ queremos que sympy interprete como tales. Todo lo demás que
# parezca un nombre se fuerza a ser un símbolo a secas.
_FUNCIONES = {"sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh",
              "tanh", "exp", "log", "ln", "sqrt", "abs", "pi"}


def _simbolos_forzados(texto: str) -> dict:
    """Cada nombre de la ecuación, atado a un símbolo propio.

    Sin esto, sympy interpreta a su manera unas cuantas letras que en física
    significan otra cosa: `E` es el número de Euler, `I` la unidad imaginaria,
    `N`, `O`, `S` y `Q` son clases suyas. Escribir «E = m*c**2» daba
    «e = c²·m», con la energía convertida en 2,718…, y el despeje salía mal
    sin que nadie viera por qué.
    """
    import sympy as sp
    nombres = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", texto or ""))
    return {n: sp.Symbol(n) for n in nombres if n.lower() not in _FUNCIONES}


def leer_ecuacion(texto: str):
    """De «v = v0 + a*t» a una expresión de sympy igualada a cero.

    Ojo con las mayúsculas: NO se normaliza el texto como en matemáticas. En
    física `P` es potencia y `p` cantidad de movimiento, `F` fuerza y `f`
    frecuencia. Pasarlo todo a minúsculas fundiría símbolos distintos.
    """
    import sympy as sp
    crudo = (texto or "").strip().replace("^", "**")
    if not crudo:
        return None, "No me ha dado ninguna ecuación."
    if "=" not in crudo:
        return None, f"«{texto}» no es una ecuación: le falta el igual."
    izq, der = crudo.split("=", 1)
    locales = _simbolos_forzados(crudo)
    try:
        return sp.sympify(izq, locals=locales) - sp.sympify(der, locals=locales), ""
    except Exception as e:
        return None, f"No entiendo la ecuación «{texto}»: {e}"


def simbolos(ecuacion) -> list:
    return sorted(s.name for s in ecuacion.free_symbols)


# ── análisis dimensional ────────────────────────────────────────────────────
def comprobar(ecuacion_texto: str, unidades: dict = None) -> dict:
    """¿Los dos lados miden lo mismo? Se responde SIN resolver nada.

    Es la comprobación más rentable de la física: si no cuadra, el resultado va
    a estar mal por muchos decimales que traiga, y se ve en un segundo.
    """
    import sympy as sp
    crudo = (ecuacion_texto or "").replace("^", "**")
    if "=" not in crudo:
        return {"ok": False, "pasos": ["Eso no es una ecuación: falta el igual."]}
    if not hay_unidades():
        return {"ok": False, "pasos": [
            "Necesito «pint» para analizar dimensiones.",
            "Instálelo con:  pip install pint"]}

    unidades = {k: str(v) for k, v in (unidades or {}).items()}
    faltan = []
    izq_txt, der_txt = crudo.split("=", 1)

    locales = _simbolos_forzados(crudo)

    def _dimension(lado: str):
        try:
            expr = sp.sympify(lado, locals=locales)
        except Exception as e:
            return None, f"no entiendo «{lado}»: {e}"
        sustituciones = {}
        for s in expr.free_symbols:
            u = unidades.get(s.name)
            if not u:
                faltan.append(s.name)
                return None, ""
            try:
                sustituciones[s.name] = _ureg().Quantity(1, u)
            except Exception:
                return None, f"no conozco la unidad «{u}» de {s.name}"
        try:
            f = sp.lambdify(sorted(sustituciones), expr, "math")
            valor = f(*[sustituciones[k] for k in sorted(sustituciones)])
            return getattr(valor, "dimensionality", None), ""
        except Exception as e:
            return None, f"no pude componer las unidades: {e}"

    d_izq, err1 = _dimension(izq_txt)
    d_der, err2 = _dimension(der_txt)
    if faltan:
        return {"ok": False, "pasos": [
            "Para comprobar dimensiones me faltan las unidades de: "
            + ", ".join(sorted(set(faltan))) + "."]}
    if err1 or err2:
        return {"ok": False, "pasos": [err1 or err2]}

    cuadra = d_izq == d_der
    pasos = [f"Lado izquierdo: [{d_izq}]", f"Lado derecho:   [{d_der}]"]
    if cuadra:
        pasos.append("Cuadra: la ecuación es dimensionalmente homogénea.")
    else:
        pasos.append("NO cuadra. Los dos lados no miden lo mismo, así que la "
                     "ecuación está mal escrita — y no hace falta resolverla "
                     "para saberlo.")
    return {"ok": True, "homogenea": cuadra, "izquierda": str(d_izq),
            "derecha": str(d_der), "pasos": pasos}


# ── el despeje ──────────────────────────────────────────────────────────────
def despejar(ecuacion_texto: str, conocidos: dict = None, incognita: str = "",
             log=print) -> dict:
    """Despeja lo que falte de CUALQUIER ecuación, con o sin unidades.

    Devuelve el despeje simbólico (la fórmula), y el número solo si hay datos
    para todo lo demás. El orden es a propósito: en un examen lo que puntúa es
    la fórmula despejada, y el número viene después.
    """
    import sympy as sp
    ec, error = leer_ecuacion(ecuacion_texto)
    if ec is None:
        return {"ok": False, "pasos": [error]}

    crudos = {k: v for k, v in (conocidos or {}).items() if v not in (None, "")}
    cantidades, valores, unidades = {}, {}, {}
    for k, v in crudos.items():
        q = magnitud(v)
        if q is None:
            continue
        cantidades[k] = q
        valores[k] = _numero(q)
        u = _unidad_base(q)
        if u:
            unidades[k] = u

    nombres = simbolos(ec)
    libres = [n for n in nombres if n not in valores]
    if incognita:
        objetivo = incognita.strip()
        if objetivo not in nombres:
            return {"ok": False, "pasos": [
                f"«{objetivo}» no aparece en la ecuación. Hay: "
                + ", ".join(nombres) + "."]}
    elif len(libres) == 1:
        objetivo = libres[0]
    elif not libres:
        return {"ok": False, "pasos": [
            "Me ha dado valor para todo: no queda nada que despejar. "
            "Dígame cuál quiere comprobar y la compruebo."]}
    else:
        return {"ok": False, "pasos": [
            f"Ecuación: {M.bonito(ec)} = 0",
            "Faltan datos. Sin conocer quedan: " + ", ".join(libres) + ".",
            "Déme todos menos uno, o dígame cuál quiere despejar."]}

    inc = sp.Symbol(objetivo)
    pasos = [f"Ecuación: {M.bonito(ec)} = 0", f"Incógnita: {objetivo}"]
    for k in sorted(cantidades):
        pasos.append(f"   {k} = {cantidades[k]}")

    try:
        soluciones = sp.solve(sp.Eq(ec, 0), inc)
    except Exception as e:
        return {"ok": False, "pasos": pasos + [f"No pude despejar: {e}"]}
    if not soluciones:
        return {"ok": False, "pasos": pasos + [
            f"No se puede despejar {objetivo} de esa ecuación."]}

    formulas = [M.bonito(s) for s in soluciones]
    pasos.append("Despejado: " + "  ó  ".join(f"{objetivo} = {f}" for f in formulas))

    # Número, solo si hay datos para todo lo demás.
    restantes = [n for n in nombres if n != objetivo and n not in valores]
    if restantes:
        pasos.append("Para el número me faltarían: " + ", ".join(restantes) + ".")
        return {"ok": True, "incognita": objetivo, "formulas": formulas,
                "valor": None, "pasos": pasos, "faltan": restantes}

    numericas = []
    for s in soluciones:
        try:
            v = complex(s.subs({sp.Symbol(k): val for k, val in valores.items()}))
            if abs(v.imag) < 1e-9:
                numericas.append(v.real)
        except Exception:
            continue
    if not numericas:
        pasos.append("La solución no da un número real con esos datos.")
        return {"ok": True, "incognita": objetivo, "formulas": formulas,
                "valor": None, "pasos": pasos}

    # La unidad del resultado sale de componer las de los datos: si entraron
    # con unidad, el resultado sale con la suya y no como un número desnudo.
    unidad = ""
    if unidades and hay_unidades():
        try:
            sustituidas = {}
            for k in nombres:
                if k == objetivo:
                    continue
                q = cantidades.get(k)
                sustituidas[k] = (q.to_base_units() if hasattr(q, "to_base_units")
                                  else q)
            f = sp.lambdify(sorted(sustituidas), soluciones[0], "math")
            resultado = f(*[sustituidas[k] for k in sorted(sustituidas)])
            unidad = f"{resultado.units:~P}" if hasattr(resultado, "units") else ""
        except Exception:
            unidad = ""

    valor = numericas[0]
    texto_valor = f"{valor:.6g}" + (f" {unidad}" if unidad else "")
    pasos.append(f"Resultado: {objetivo} = {texto_valor}")
    if len(numericas) > 1:
        pasos.append("Otras soluciones: "
                     + ", ".join(f"{v:.6g}" for v in numericas[1:]))

    # Comprobación dimensional de regalo — pero SOLO si se conocen las unidades
    # de TODOS los símbolos, incluida la incógnita. Con la de la incógnita sin
    # declarar la comparación no significa nada, y antes daba falsos avisos de
    # «no es homogénea» en ecuaciones perfectamente correctas.
    if unidad:
        completas = dict(unidades, **{objetivo: unidad})
        if all(n in completas for n in nombres):
            chequeo = comprobar(ecuacion_texto, completas)
            if chequeo.get("ok") and not chequeo.get("homogenea"):
                pasos.append("OJO: la ecuación no es dimensionalmente homogénea. "
                             "El número sale, pero algo está mal planteado.")

    return {"ok": True, "incognita": objetivo, "formulas": formulas,
            "valor": valor, "unidad": unidad, "valores": numericas,
            "pasos": pasos}


# ── conversión de unidades, que se pide a diario ────────────────────────────
def convertir(cantidad: str, a: str) -> dict:
    """«120 km/h a m/s», «3 atm a pascales»."""
    if not hay_unidades():
        return {"ok": False, "pasos": ["Necesito «pint»:  pip install pint"]}
    q = magnitud(cantidad)
    if q is None or isinstance(q, float):
        return {"ok": False, "pasos": [
            f"«{cantidad}» no trae unidad, así que no hay nada que convertir."]}
    destino = a
    for patron, reemplazo in _ARREGLOS:
        destino = re.sub(patron, reemplazo, destino, flags=re.I)
    try:
        r = q.to(destino.strip())
    except Exception as e:
        return {"ok": False, "pasos": [f"No puedo pasar {q} a «{a}»: {e}"]}
    return {"ok": True, "valor": float(r.magnitude), "unidad": f"{r.units:~P}",
            "pasos": [f"{q}  =  {r:~P}"]}


def resumen_estado() -> dict:
    return {"unidades": hay_unidades(),
            "banco_cerrado": False,
            "que_hace": "despeja cualquier ecuación, con unidades y "
                        "comprobación dimensional"}


if __name__ == "__main__":
    # sympy imprime con «·» y la consola de Windows va en cp1252: sin esto,
    # la demostración muere por el separador de un producto.
    try:
        import consola_utf8  # noqa: F401
    except Exception:
        pass
    for prueba in (("v = v0 + a*t", {"v0": "0 m/s", "a": "9.8 m/s^2", "t": "3 s"}, ""),
                   ("E = m*c**2", {"m": "2 kg", "c": "299792458 m/s"}, ""),
                   ("P = F/A", {"F": "500 N", "A": "0.25 m^2"}, "")):
        r = despejar(*prueba)
        print("\n".join(r["pasos"]))
        print("-" * 60)
    print("\n".join(comprobar("E = m*v", {"E": "J", "m": "kg", "v": "m/s"})["pasos"]))
