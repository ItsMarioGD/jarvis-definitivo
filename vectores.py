#!/usr/bin/env python3
"""
vectores.py - Vectores, fuerzas y estática, dibujados
=====================================================
Es lo que más se usa en primero de ingeniería y lo único que no tenía módulo:
descomponer una fuerza, sumar vectores, sacar un momento, y comprobar si un
cuerpo está en equilibrio. Se hacía a mano en cada problema.

Lo que hay aquí:

    vector          módulo, dirección, ángulos, unitario
    operaciones     suma, resta, escalar, producto escalar y vectorial
    descomponer     una fuerza en sus componentes, y al revés
    equilibrio      ¿la suma de fuerzas es cero? Si no, cuál falta
    momento         M = r x F, con su brazo
    viga            reacciones de una viga apoyada en dos puntos

Y todo se puede **ver**: las fuerzas salen dibujadas en 3D sobre el mismo visor
que usa `simulacion.py`, con su resultante. Un diagrama de sólido libre mal
dibujado es la causa de la mitad de los errores de estática, y verlo girar
enseña más que tres páginas de componentes.

Sin dependencias nuevas: numpy y sympy, que ya están.
"""
import math
import os
import re

import matematica as M

G = 9.80665


def _np():
    import numpy as np
    return np


# ── leer vectores como se dictan ────────────────────────────────────────────
def leer(valor) -> list:
    """Admite «(3, 4, 0)», «3i + 4j», «5 N a 30 grados» o una lista ya hecha."""
    if valor is None:
        return [0.0, 0.0, 0.0]
    if isinstance(valor, (list, tuple)):
        v = [float(x) for x in valor]
        return (v + [0.0, 0.0, 0.0])[:3]
    texto = str(valor).strip().replace(",", " ").replace("^", "**")

    # «5 N a 30 grados» (y con elevación: «5 a 30 y 20 grados»)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:N|newtons?)?\s*(?:a|en|con)\s+"
                  r"(-?\d+(?:\.\d+)?)\s*(?:º|grados?|deg)?"
                  r"(?:\s*(?:y|,)\s*(-?\d+(?:\.\d+)?)\s*(?:º|grados?|deg)?)?",
                  texto, re.I)
    if m:
        mod = float(m.group(1))
        az = math.radians(float(m.group(2)))
        elev = math.radians(float(m.group(3))) if m.group(3) else 0.0
        return [mod * math.cos(elev) * math.cos(az),
                mod * math.cos(elev) * math.sin(az),
                mod * math.sin(elev)]

    # «3i + 4j - 2k»
    if re.search(r"[ijk]\b", texto, re.I):
        comp = {"i": 0.0, "j": 0.0, "k": 0.0}
        for signo, num, letra in re.findall(
                r"([+-]?)\s*(\d+(?:\.\d+)?)?\s*([ijk])", texto, re.I):
            valor_num = float(num) if num else 1.0
            comp[letra.lower()] = -valor_num if signo == "-" else valor_num
        return [comp["i"], comp["j"], comp["k"]]

    numeros = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", texto)]
    return (numeros + [0.0, 0.0, 0.0])[:3]


# ── lo básico ───────────────────────────────────────────────────────────────
def modulo(v) -> float:
    v = leer(v)
    return math.sqrt(sum(x * x for x in v))


def unitario(v) -> list:
    v, m = leer(v), modulo(v)
    return [x / m for x in v] if m else [0.0, 0.0, 0.0]


def escalar(a, b) -> float:
    a, b = leer(a), leer(b)
    return sum(x * y for x, y in zip(a, b))


def vectorial(a, b) -> list:
    a, b = leer(a), leer(b)
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def angulo(a, b) -> float:
    """En grados. Entre 0 y 180."""
    ma, mb = modulo(a), modulo(b)
    if not ma or not mb:
        return 0.0
    coseno = max(-1.0, min(1.0, escalar(a, b) / (ma * mb)))
    return math.degrees(math.acos(coseno))


def proyeccion(a, sobre) -> dict:
    """La sombra de `a` sobre `sobre`: escalar y vector."""
    u = unitario(sobre)
    largo = escalar(a, u)
    return {"escalar": largo, "vector": [largo * x for x in u]}


def analizar(v, nombre: str = "v") -> dict:
    """Todo lo que se pide de un vector en un examen, de una vez."""
    v = leer(v)
    m = modulo(v)
    pasos = [f"{nombre} = ({v[0]:g}, {v[1]:g}, {v[2]:g})",
             f"|{nombre}| = √({v[0]:g}² + {v[1]:g}² + {v[2]:g}²) = {m:.4f}"]
    if m:
        u = unitario(v)
        pasos.append(f"Unitario: ({u[0]:.4f}, {u[1]:.4f}, {u[2]:.4f})")
        # Ángulos directores: los que se piden y casi nadie recuerda.
        alfa, beta, gamma = (math.degrees(math.acos(max(-1, min(1, x / m))))
                             for x in v)
        pasos.append(f"Ángulos directores: α = {alfa:.2f}°, β = {beta:.2f}°, "
                     f"γ = {gamma:.2f}°")
        if abs(v[2]) < 1e-12:
            pasos.append(f"En el plano: dirección {math.degrees(math.atan2(v[1], v[0])):.2f}° "
                         "medida desde el eje X")
    return {"ok": True, "vector": v, "modulo": m, "pasos": pasos}


# ── fuerzas ─────────────────────────────────────────────────────────────────
def descomponer(magnitud: float, angulo_grados: float,
                elevacion: float = 0.0) -> dict:
    """De módulo y ángulo a componentes. El primer ejercicio de todo curso."""
    a, e = math.radians(angulo_grados), math.radians(elevacion)
    fx = magnitud * math.cos(e) * math.cos(a)
    fy = magnitud * math.cos(e) * math.sin(a)
    fz = magnitud * math.sin(e)
    pasos = [f"F = {magnitud:g} N a {angulo_grados:g}°"
             + (f" con {elevacion:g}° de elevación" if elevacion else ""),
             f"Fx = F·cos(θ) = {magnitud:g}·cos({angulo_grados:g}°) = {fx:.4f} N",
             f"Fy = F·sen(θ) = {magnitud:g}·sen({angulo_grados:g}°) = {fy:.4f} N"]
    if elevacion:
        pasos.append(f"Fz = F·sen(φ) = {fz:.4f} N")
    pasos.append(f"Comprobación: √(Fx²+Fy²+Fz²) = "
                 f"{math.sqrt(fx*fx+fy*fy+fz*fz):.4f} N")
    return {"ok": True, "vector": [fx, fy, fz], "pasos": pasos}


def resultante(fuerzas, nombres=None) -> dict:
    """Suma de fuerzas, con su módulo y dirección."""
    lista = [leer(f) for f in (fuerzas or [])]
    if not lista:
        return {"ok": False, "pasos": ["No me ha dado ninguna fuerza."]}
    nombres = list(nombres or []) + [f"F{i+1}" for i in range(len(lista))]
    total = [sum(v[i] for v in lista) for i in range(3)]
    m = modulo(total)
    pasos = [f"{nombres[i]} = ({v[0]:g}, {v[1]:g}, {v[2]:g})"
             for i, v in enumerate(lista)]
    pasos.append(f"R = Σ F = ({total[0]:.4f}, {total[1]:.4f}, {total[2]:.4f})")
    pasos.append(f"|R| = {m:.4f} N")
    if m > 1e-9:
        pasos.append(f"Dirección en el plano XY: "
                     f"{math.degrees(math.atan2(total[1], total[0])):.2f}°")
    return {"ok": True, "vector": total, "modulo": m, "fuerzas": lista,
            "nombres": nombres[:len(lista)], "pasos": pasos}


def equilibrio(fuerzas, nombres=None, tolerancia: float = 1e-6) -> dict:
    """¿Está en equilibrio? Y si no, qué fuerza falta para que lo esté."""
    r = resultante(fuerzas, nombres)
    if not r.get("ok"):
        return r
    total, m = r["vector"], r["modulo"]
    pasos = list(r["pasos"])
    if m <= tolerancia:
        pasos.append("ΣF = 0: el cuerpo ESTÁ en equilibrio de traslación.")
        return {"ok": True, "equilibrio": True, "falta": [0.0, 0.0, 0.0],
                "pasos": pasos}
    falta = [-x for x in total]
    pasos.append(f"ΣF ≠ 0, así que NO está en equilibrio: le sobra "
                 f"{m:.4f} N.")
    pasos.append(f"Para equilibrarlo hace falta "
                 f"({falta[0]:.4f}, {falta[1]:.4f}, {falta[2]:.4f}) N, "
                 f"o sea {m:.4f} N a "
                 f"{math.degrees(math.atan2(falta[1], falta[0])):.2f}°.")
    return {"ok": True, "equilibrio": False, "falta": falta, "pasos": pasos}


def momento(fuerza, punto_aplicacion, respecto_a=(0, 0, 0)) -> dict:
    """M = r x F. Con su brazo, que es lo que casi nadie calcula bien."""
    F = leer(fuerza)
    r = [a - b for a, b in zip(leer(punto_aplicacion), leer(respecto_a))]
    M_vec = vectorial(r, F)
    m = modulo(M_vec)
    mf = modulo(F)
    pasos = [f"r = ({r[0]:g}, {r[1]:g}, {r[2]:g}) m",
             f"F = ({F[0]:g}, {F[1]:g}, {F[2]:g}) N",
             f"M = r × F = ({M_vec[0]:.4f}, {M_vec[1]:.4f}, {M_vec[2]:.4f}) N·m",
             f"|M| = {m:.4f} N·m"]
    if mf > 1e-9:
        brazo = m / mf
        pasos.append(f"Brazo: d = |M| / |F| = {brazo:.4f} m "
                     "(la distancia perpendicular de la línea de acción al punto)")
    if m > 1e-9:
        sentido = "antihorario" if M_vec[2] > 0 else "horario"
        pasos.append(f"En el plano XY gira en sentido {sentido}.")
    return {"ok": True, "vector": M_vec, "modulo": m, "pasos": pasos}


def viga(longitud: float, cargas, log=print) -> dict:
    """Reacciones de una viga apoyada en los dos extremos.

    `cargas` = [(posicion_m, fuerza_N), ...] con la fuerza hacia abajo positiva.
    Se resuelve con las dos ecuaciones de siempre: ΣM = 0 y ΣF = 0.
    """
    cargas = [(float(p), float(f)) for p, f in (cargas or [])]
    if not cargas or longitud <= 0:
        return {"ok": False, "pasos": ["Necesito la longitud y alguna carga."]}
    for p, _f in cargas:
        if p < 0 or p > longitud:
            return {"ok": False, "pasos": [
                f"La carga en {p:g} m se sale de la viga (0 a {longitud:g} m)."]}

    total = sum(f for _p, f in cargas)
    momentos_a = sum(f * p for p, f in cargas)          # respecto del apoyo A
    Rb = momentos_a / longitud
    Ra = total - Rb

    pasos = [f"Viga de {longitud:g} m apoyada en A (0 m) y B ({longitud:g} m).",
             "Cargas:"]
    pasos += [f"   {f:g} N a {p:g} m de A" for p, f in cargas]
    pasos.append(f"ΣM(A) = 0 → R_B · {longitud:g} = "
                 + " + ".join(f"{f:g}·{p:g}" for p, f in cargas)
                 + f" = {momentos_a:g}")
    pasos.append(f"R_B = {momentos_a:g} / {longitud:g} = {Rb:.4f} N")
    pasos.append(f"ΣF = 0 → R_A = {total:g} − {Rb:.4f} = {Ra:.4f} N")
    pasos.append(f"Comprobación: R_A + R_B = {Ra + Rb:.4f} N = carga total.")
    if Ra < 0 or Rb < 0:
        pasos.append("OJO: una reacción sale negativa; ese apoyo tiraría hacia "
                     "abajo. Revise las posiciones.")
    return {"ok": True, "Ra": Ra, "Rb": Rb, "longitud": longitud,
            "cargas": cargas, "pasos": pasos}


# ── verlo ───────────────────────────────────────────────────────────────────
def dibujar(fuerzas, nombres=None, titulo: str = "Diagrama de fuerzas",
            con_resultante: bool = True, carpeta: str = "",
            abrir_visor: bool = True, log=print) -> dict:
    """Las fuerzas en 3D, girables, con su resultante.

    Se reutiliza el visor animado de `simulacion.py`: un vector es un cuerpo
    que va del origen a su punta, así que con dos marcos —origen y punta— el
    visor lo dibuja y deja su estela, que es exactamente la flecha.
    """
    import simulacion as SIM
    lista = [leer(f) for f in (fuerzas or [])]
    if not lista:
        return {"ok": False, "pasos": ["No me ha dado ninguna fuerza que dibujar."]}
    nombres = list(nombres or []) + [f"F{i+1}" for i in range(len(lista))]
    nombres = nombres[:len(lista)]

    vectores = list(lista)
    etiquetas = list(nombres)
    if con_resultante and len(lista) > 1:
        vectores.append([sum(v[i] for v in lista) for i in range(3)])
        etiquetas.append("Resultante")

    # 40 marcos: cada flecha crece desde el origen hasta su punta.
    marcos = []
    for paso in range(40):
        t = (paso + 1) / 40
        marcos.append([[round(c * t, 4) for c in v] for v in vectores])

    cuerpos = []
    for i, nombre in enumerate(etiquetas):
        es_resultante = (con_resultante and len(lista) > 1 and i == len(etiquetas) - 1)
        cuerpos.append(SIM._cuerpo(
            f"{nombre} ({modulo(vectores[i]):.2f} N)", i,
            radio=0.18 if es_resultante else 0.12,
            estela=True,
            color=(1.0, 0.95, 0.35) if es_resultante else None))

    # Ejes de referencia, para que se vea respecto a qué.
    escala = max((modulo(v) for v in vectores), default=1.0) or 1.0
    lineas = [[[-escala, 0, 0], [escala, 0, 0]],
              [[0, -escala, 0], [0, escala, 0]],
              [[0, 0, -escala], [0, 0, escala]]]

    notas = []
    r = resultante(lista, nombres)
    notas += r["pasos"]
    eq = equilibrio(lista, nombres)
    notas.append("EN EQUILIBRIO" if eq.get("equilibrio")
                 else "NO está en equilibrio")

    datos = SIM._escena(titulo, cuerpos, marcos, 0.05, lineas=lineas, notas=notas)
    out = carpeta or M.carpeta_salida("fuerzas")
    html = SIM.visor(datos, os.path.join(out, "fuerzas.html"), titulo)
    if abrir_visor and html:
        M.abrir(html, log=log)
    return {"ok": True, "html": html, "carpeta": out, "pasos": notas,
            "resultante": r["vector"]}


def resumen_estado() -> dict:
    return {"operaciones": ["modulo", "unitario", "escalar", "vectorial",
                            "angulo", "proyeccion", "descomponer", "resultante",
                            "equilibrio", "momento", "viga"],
            "dibuja": True}


if __name__ == "__main__":
    try:
        import consola_utf8  # noqa: F401
    except Exception:
        pass
    print("\n".join(analizar([3, 4, 12])["pasos"]))
    print("-" * 60)
    print("\n".join(descomponer(100, 30)["pasos"]))
    print("-" * 60)
    print("\n".join(equilibrio([[10, 0, 0], [0, 10, 0], [-10, -10, 0]])["pasos"]))
    print("-" * 60)
    print("\n".join(viga(6.0, [(2.0, 1000.0), (4.5, 500.0)])["pasos"]))
