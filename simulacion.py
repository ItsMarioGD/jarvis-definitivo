#!/usr/bin/env python3
"""
simulacion.py - Que la ciencia se MUEVA
=======================================
`matematica.py` levanta superficies, `fisica.py` dibuja la trayectoria y
`quimica.py` arma la molécula. Todo eso es un retrato: quieto. Falta lo que
enseña de verdad, que es ver el sistema EVOLUCIONAR — la órbita cerrándose, el
péndulo doble volviéndose loco, la carga enroscándose en el campo, la molécula
vibrando.

Aquí está ese motor. Tres piezas y ninguna más:

    1. Un integrador Runge-Kutta de orden 4 escrito a mano (numpy y nada más;
       scipy es opcional en este proyecto y esto tiene que funcionar sin él).
    2. Un catálogo de sistemas ya montados, para que se pidan hablando.
    3. Una puerta abierta: `desde_ecuaciones()` integra LAS ECUACIONES QUE
       DICTE EL SEÑOR. Eso es lo que hace que no haga falta una función por
       cada tema que a nadie se le ocurrió prever.

Lo que sale es un `.html` que se abre solo: tres.js, cuerpos con su estela,
play/pausa, barra de tiempo, velocidad, ejes y un panel con las magnitudes vivas
(energía, velocidad, lo que toque en cada sistema). Y, cuando tiene sentido, la
malla `.obj` de la trayectoria para imprimirla.

Sistemas del catálogo:

    tiro            proyectil en 3D con rozamiento y viento
    orbita          N cuerpos con gravitación de Newton (Sol-Tierra-Luna, …)
    pendulo         simple y DOBLE (el caos, que se ve a simple vista)
    muelle          oscilador amortiguado y forzado, con resonancia
    carga           partícula cargada en campo eléctrico y magnético (hélice)
    lorenz          el atractor: por qué el tiempo no se puede predecir
    cuerda          onda en una cuerda con sus extremos fijos
    membrana        tambor vibrando: la ecuación de ondas en 2D
    molecula        la molécula vibrando en sus modos (estiramiento y flexión)
    ecuaciones      LAS QUE DICTE EL SEÑOR

Todo local. Ni una llamada a internet más que el three.js del visor, igual que
los visores que ya había.
"""
import json
import math
import os
import re

import matematica as M

PASOS_MAX = int(os.getenv("JARVIS_SIM_MARCOS", "600"))
PASOS_MALLA = int(os.getenv("JARVIS_SIM_MARCOS_MALLA", "240"))

# Paleta de los cuerpos, en el orden en que se piden.
_PALETA = [(0.18, 0.78, 1.00), (1.00, 0.58, 0.20), (0.45, 1.00, 0.55),
           (1.00, 0.35, 0.45), (0.80, 0.60, 1.00), (1.00, 0.88, 0.35),
           (0.40, 0.90, 0.85), (0.95, 0.50, 0.80)]

G_GRAV = 6.67430e-11
G_TIERRA = 9.80665


def _np():
    import numpy as np
    return np


def _color(i: int):
    return _PALETA[i % len(_PALETA)]


def _r(x, n=4):
    """Redondea para que el .html no pese tres veces lo que debe."""
    return round(float(x), n)


# ── el integrador ───────────────────────────────────────────────────────────
def rk4(derivada, estado0, dt: float, pasos: int, parar=None):
    """Runge-Kutta 4. `derivada(t, y) -> dy/dt`, con `y` un array de numpy.

    RK4 y no Euler porque Euler miente en cuanto el sistema conserva algo: una
    órbita dibujada con Euler se abre en espiral y parece física cuando sólo es
    error de truncamiento. Con RK4 la elipse cierra.
    """
    np = _np()
    y = np.array(estado0, dtype=float)
    t = 0.0
    salida = [y.copy()]
    tiempos = [0.0]
    for _ in range(pasos):
        k1 = np.asarray(derivada(t, y), dtype=float)
        k2 = np.asarray(derivada(t + dt / 2, y + dt / 2 * k1), dtype=float)
        k3 = np.asarray(derivada(t + dt / 2, y + dt / 2 * k2), dtype=float)
        k4 = np.asarray(derivada(t + dt, y + dt * k3), dtype=float)
        y = y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        t += dt
        if not np.all(np.isfinite(y)):
            break
        salida.append(y.copy())
        tiempos.append(t)
        if parar and parar(t, y):
            break
    return tiempos, salida


def _diezmar(tiempos: list, estados: list, tope: int = PASOS_MAX):
    """Se integra fino y se GUARDA grueso: precisión sin un HTML de 40 MB."""
    n = len(estados)
    if n <= tope:
        return tiempos, estados
    # Techo, no división entera: con `n // tope` un caso de 3240 marcos salía
    # con 1080, casi el doble del tope, y el .html engordaba lo mismo.
    paso = max(1, math.ceil(n / tope))
    return tiempos[::paso], estados[::paso]


# ── estructura de lo que consume el visor ───────────────────────────────────
def _escena(titulo: str, cuerpos: list, marcos: list, dt: float,
            escalares: dict = None, enlaces: list = None,
            lineas: list = None, malla=None, notas: list = None) -> dict:
    return {"tipo": "sim", "titulo": titulo, "dt": _r(dt, 6),
            "cuerpos": cuerpos, "marcos": marcos,
            "escalares": escalares or {}, "enlaces": enlaces or [],
            "lineas": lineas or [], "malla": malla or {},
            "notas": notas or []}


def _cuerpo(nombre: str, i: int, radio: float = 0.25, estela: bool = True,
            color=None) -> dict:
    return {"nombre": nombre, "color": list(color or _color(i)),
            "radio": _r(radio, 4), "estela": bool(estela)}


# ── 1. proyectil en 3D, con rozamiento y viento ─────────────────────────────
def tiro(v0: float = 25.0, angulo: float = 45.0, azimut: float = 0.0,
         y0: float = 0.0, k_roce: float = 0.0, viento=(0.0, 0.0, 0.0),
         masa: float = 1.0) -> dict:
    """Trayectoria real: con rozamiento lineal deja de ser una parábola.

    Esa es justo la gracia de simularlo en vez de aplicar la fórmula: la
    fórmula del libro SÓLO vale con k=0, y aquí se ve cuánto se aparta.
    """
    np = _np()
    a, az = math.radians(angulo), math.radians(azimut)
    v = [v0 * math.cos(a) * math.cos(az), v0 * math.cos(a) * math.sin(az),
         v0 * math.sin(a)]
    w = np.array(viento, dtype=float)

    def d(_t, y):
        vel = y[3:6]
        acc = np.array([0.0, 0.0, -G_TIERRA]) - (k_roce / masa) * (vel - w)
        return np.concatenate([vel, acc])

    dt = 0.004
    tiempos, estados = rk4(d, [0, 0, y0] + v, dt, 40000,
                           parar=lambda _t, y: y[2] < 0 and y[5] < 0)
    tiempos, estados = _diezmar(tiempos, estados)
    marcos = [[[_r(e[0]), _r(e[1]), _r(e[2])]] for e in estados]
    rapidez = [_r(math.sqrt(e[3] ** 2 + e[4] ** 2 + e[5] ** 2), 3) for e in estados]
    altura = [_r(e[2], 3) for e in estados]
    alcance = math.sqrt(estados[-1][0] ** 2 + estados[-1][1] ** 2)
    cima = max(e[2] for e in estados)

    notas = [f"Velocidad inicial {v0:g} m/s a {angulo:g}° "
             + (f"(azimut {azimut:g}°)" if azimut else ""),
             f"Alcance: {alcance:.2f} m",
             f"Altura máxima: {cima:.2f} m",
             f"Tiempo de vuelo: {tiempos[-1]:.2f} s"]
    if k_roce:
        ideal = (v0 ** 2) * math.sin(2 * math.radians(angulo)) / G_TIERRA
        notas.append(f"Sin rozamiento el alcance sería {ideal:.2f} m: "
                     f"el aire se ha comido {ideal - alcance:.2f} m.")
    else:
        notas.append("Sin rozamiento: la trayectoria es una parábola exacta.")
    return {"ok": True, "datos": _escena(
        f"Tiro a {v0:g} m/s y {angulo:g}°", [_cuerpo("proyectil", 0, 0.35)],
        marcos, tiempos[1] - tiempos[0] if len(tiempos) > 1 else 0.02,
        {"rapidez (m/s)": rapidez, "altura (m)": altura},
        lineas=[[[0, 0, 0], [alcance * 1.05, 0, 0]]], notas=notas), "notas": notas}


# ── 2. gravitación de N cuerpos ─────────────────────────────────────────────
_SISTEMAS = {
    # nombre: [(etiqueta, masa kg, x m, y m, vx m/s, vy m/s, radio dibujo)]
    "tierra-luna": [("Tierra", 5.972e24, 0, 0, 0, 0, 0.9),
                    ("Luna", 7.348e22, 3.844e8, 0, 0, 1022.0, 0.35)],
    "sol-tierra": [("Sol", 1.989e30, 0, 0, 0, 0, 1.4),
                   ("Tierra", 5.972e24, 1.496e11, 0, 0, 29780.0, 0.5)],
    "interior": [("Sol", 1.989e30, 0, 0, 0, 0, 1.4),
                 ("Mercurio", 3.301e23, 5.79e10, 0, 0, 47360.0, 0.3),
                 ("Venus", 4.867e24, 1.082e11, 0, 0, 35020.0, 0.42),
                 ("Tierra", 5.972e24, 1.496e11, 0, 0, 29780.0, 0.45),
                 ("Marte", 6.417e23, 2.279e11, 0, 0, 24070.0, 0.34)],
}


def orbita(sistema: str = "sol-tierra", vueltas: float = 1.4) -> dict:
    """Gravitación de Newton entre N cuerpos, integrada de verdad.

    No se dibuja la elipse de Kepler: se integran las fuerzas y la elipse
    APARECE. Con tres cuerpos ya no hay fórmula que valga, y ahí es donde esto
    deja de ser un adorno.
    """
    np = _np()
    cuerpos = _SISTEMAS.get((sistema or "").strip().lower())
    if not cuerpos:
        return {"ok": False, "pasos": [
            f"No conozco el sistema «{sistema}». Tengo: "
            + ", ".join(sorted(_SISTEMAS)) + "."]}

    masas = np.array([c[1] for c in cuerpos])
    pos = np.array([[c[2], c[3], 0.0] for c in cuerpos])
    vel = np.array([[c[4], c[5], 0.0] for c in cuerpos])
    n = len(cuerpos)
    # Todo se mide en unidades del cuerpo más lejano, para que quepa en pantalla.
    escala = max(float(np.linalg.norm(p)) for p in pos) or 1.0

    def d(_t, y):
        p = y[:3 * n].reshape(n, 3)
        v = y[3 * n:].reshape(n, 3)
        a = np.zeros_like(p)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                dif = p[j] - p[i]
                r = float(np.linalg.norm(dif)) or 1.0
                a[i] += G_GRAV * masas[j] * dif / r ** 3
        return np.concatenate([v.ravel(), a.ravel()])

    # Periodo de Kepler del cuerpo más lejano: así «una vuelta» es una vuelta.
    central = float(masas[0])
    periodo = 2 * math.pi * math.sqrt(escala ** 3 / (G_GRAV * central))
    total = periodo * vueltas
    pasos = 6000
    dt = total / pasos
    tiempos, estados = rk4(d, np.concatenate([pos.ravel(), vel.ravel()]), dt, pasos)
    tiempos, estados = _diezmar(tiempos, estados)

    marcos = []
    for e in estados:
        p = e[:3 * n].reshape(n, 3) / escala * 6.0     # 6 unidades de pantalla
        marcos.append([[_r(v[0], 3), _r(v[1], 3), _r(v[2], 3)] for v in p])

    energias = []
    for e in estados:
        p = e[:3 * n].reshape(n, 3)
        v = e[3 * n:].reshape(n, 3)
        cin = float(sum(0.5 * masas[i] * np.dot(v[i], v[i]) for i in range(n)))
        pot = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                r = float(np.linalg.norm(p[j] - p[i])) or 1.0
                pot -= G_GRAV * masas[i] * masas[j] / r
        energias.append(_r((cin + pot) / 1e33, 6))

    deriva = abs(energias[-1] - energias[0]) / (abs(energias[0]) or 1) * 100
    notas = [f"Sistema «{sistema}»: {n} cuerpos con la ley de Newton.",
             f"Periodo del más lejano: {periodo / 86400:.2f} días.",
             f"Simuladas {vueltas:g} vueltas con Runge-Kutta 4.",
             f"La energía total se conserva con un {deriva:.4f}% de deriva: "
             "eso mide lo buena que es la integración."]
    return {"ok": True, "datos": _escena(
        f"Órbitas · {sistema}",
        [_cuerpo(c[0], i, c[6]) for i, c in enumerate(cuerpos)],
        marcos, dt, {"energía total (×10³³ J)": energias}, notas=notas),
        "notas": notas}


# ── 3. péndulo simple y doble ───────────────────────────────────────────────
def pendulo(l1: float = 1.0, l2: float = 0.0, m1: float = 1.0, m2: float = 1.0,
            a1: float = 120.0, a2: float = 100.0, t_max: float = 20.0) -> dict:
    """Con `l2` a cero, péndulo simple. Con `l2`, el doble: caos puro."""
    np = _np()
    th1, th2 = math.radians(a1), math.radians(a2)
    doble = l2 > 0

    if not doble:
        def d(_t, y):
            return np.array([y[1], -(G_TIERRA / l1) * math.sin(y[0])])
        estado0 = [th1, 0.0]
    else:
        def d(_t, y):
            t1, w1, t2, w2 = y
            dl = t1 - t2
            den = 2 * m1 + m2 - m2 * math.cos(2 * dl)
            a_1 = (-G_TIERRA * (2 * m1 + m2) * math.sin(t1)
                   - m2 * G_TIERRA * math.sin(t1 - 2 * t2)
                   - 2 * math.sin(dl) * m2 * (w2 ** 2 * l2 + w1 ** 2 * l1 * math.cos(dl))
                   ) / (l1 * den)
            a_2 = (2 * math.sin(dl) * (w1 ** 2 * l1 * (m1 + m2)
                                       + G_TIERRA * (m1 + m2) * math.cos(t1)
                                       + w2 ** 2 * l2 * m2 * math.cos(dl))
                   ) / (l2 * den)
            return np.array([w1, a_1, w2, a_2])
        estado0 = [th1, 0.0, th2, 0.0]

    dt = 0.002
    tiempos, estados = rk4(d, estado0, dt, int(t_max / dt))
    tiempos, estados = _diezmar(tiempos, estados)

    marcos, energias = [], []
    for e in estados:
        x1, z1 = l1 * math.sin(e[0]), -l1 * math.cos(e[0])
        if doble:
            x2 = x1 + l2 * math.sin(e[2])
            z2 = z1 - l2 * math.cos(e[2])
            marcos.append([[_r(x1), 0, _r(z1)], [_r(x2), 0, _r(z2)]])
            v1 = l1 * e[1]
            v2s = (l1 ** 2 * e[1] ** 2 + l2 ** 2 * e[3] ** 2
                   + 2 * l1 * l2 * e[1] * e[3] * math.cos(e[0] - e[2]))
            ec = 0.5 * m1 * v1 ** 2 + 0.5 * m2 * v2s
            ep = m1 * G_TIERRA * z1 + m2 * G_TIERRA * z2
        else:
            marcos.append([[_r(x1), 0, _r(z1)]])
            ec = 0.5 * m1 * (l1 * e[1]) ** 2
            ep = m1 * G_TIERRA * z1
        energias.append(_r(ec + ep, 4))

    cuerpos = [_cuerpo("masa 1", 0, 0.12 + 0.05 * m1)]
    enlaces = [[-1, 0]]                       # -1 = el punto de anclaje
    if doble:
        cuerpos.append(_cuerpo("masa 2", 1, 0.12 + 0.05 * m2))
        enlaces.append([0, 1])

    notas = ([f"Péndulo doble: {l1:g} m y {l2:g} m, soltado en {a1:g}° y {a2:g}°.",
              "Dos condiciones iniciales casi idénticas se separan en segundos: "
              "eso es el caos, y por eso el tiempo no se predice a diez días.",
              "La energía se conserva, que es lo que distingue el caos del error."]
             if doble else
             [f"Péndulo simple de {l1:g} m soltado desde {a1:g}°.",
              f"Periodo para ángulo pequeño: T = 2π√(L/g) = "
              f"{2 * math.pi * math.sqrt(l1 / G_TIERRA):.3f} s.",
              "Desde un ángulo grande el periodo se alarga: la fórmula del libro "
              "sólo vale para oscilaciones pequeñas, y aquí se ve."])
    return {"ok": True, "datos": _escena(
        "Péndulo doble" if doble else "Péndulo simple", cuerpos, marcos,
        tiempos[1] - tiempos[0] if len(tiempos) > 1 else 0.02,
        {"energía (J)": energias}, enlaces=enlaces, notas=notas), "notas": notas}


# ── 4. oscilador: amortiguado y forzado ─────────────────────────────────────
def muelle(m: float = 1.0, k: float = 10.0, c: float = 0.3, F: float = 0.0,
           w: float = 0.0, x0: float = 1.0, t_max: float = 30.0) -> dict:
    """m·x'' + c·x' + k·x = F·cos(ω t). La resonancia se ve crecer."""
    np = _np()

    def d(t, y):
        return np.array([y[1], (F * math.cos(w * t) - c * y[1] - k * y[0]) / m])

    dt = 0.004
    tiempos, estados = rk4(d, [x0, 0.0], dt, int(t_max / dt))
    tiempos, estados = _diezmar(tiempos, estados)
    marcos = [[[_r(e[0]), 0, 0]] for e in estados]
    velocidad = [_r(e[1], 4) for e in estados]
    energia = [_r(0.5 * m * e[1] ** 2 + 0.5 * k * e[0] ** 2, 4) for e in estados]

    w0 = math.sqrt(k / m)
    gamma = c / (2 * m)
    if gamma == 0:
        regimen = "sin amortiguar"
    elif gamma < w0:
        regimen = "subamortiguado (oscila y se apaga)"
    elif abs(gamma - w0) < 1e-9:
        regimen = "amortiguamiento crítico (vuelve sin oscilar, lo más rápido posible)"
    else:
        regimen = "sobreamortiguado (vuelve despacio, sin oscilar)"
    notas = [f"m = {m:g} kg, k = {k:g} N/m, c = {c:g} N·s/m",
             f"Frecuencia propia ω₀ = √(k/m) = {w0:.4f} rad/s "
             f"({w0 / (2 * math.pi):.4f} Hz)",
             f"Régimen: {regimen}"]
    if F:
        notas.append(f"Forzado con F = {F:g} N a ω = {w:g} rad/s.")
        if abs(w - w0) < 0.15 * w0:
            notas.append("¡Está en RESONANCIA! La amplitud crece hasta que el "
                         "amortiguamiento la frena. Así se rompen los puentes.")
    return {"ok": True, "datos": _escena(
        "Oscilador masa-muelle", [_cuerpo("masa", 0, 0.3)], marcos,
        tiempos[1] - tiempos[0] if len(tiempos) > 1 else 0.02,
        {"x (m)": [mm[0][0] for mm in marcos], "v (m/s)": velocidad,
         "energía (J)": energia},
        enlaces=[[-1, 0]], notas=notas), "notas": notas}


# ── 5. carga en campo eléctrico y magnético ─────────────────────────────────
def carga(q: float = 1.0, masa: float = 1.0, E=(0, 0, 0), B=(0, 0, 1),
          v0=(1.0, 0, 0.4), t_max: float = 30.0) -> dict:
    """Fuerza de Lorentz: F = q(E + v×B). Con B en z sale la hélice."""
    np = _np()
    Ev, Bv = np.array(E, dtype=float), np.array(B, dtype=float)

    def d(_t, y):
        v = y[3:6]
        a = (q / masa) * (Ev + np.cross(v, Bv))
        return np.concatenate([v, a])

    dt = 0.004
    tiempos, estados = rk4(d, [0, 0, 0] + list(v0), dt, int(t_max / dt))
    tiempos, estados = _diezmar(tiempos, estados)
    marcos = [[[_r(e[0]), _r(e[1]), _r(e[2])]] for e in estados]
    rapidez = [_r(math.sqrt(e[3] ** 2 + e[4] ** 2 + e[5] ** 2), 4) for e in estados]

    modulo_b = float(np.linalg.norm(Bv))
    notas = [f"Carga q = {q:g} C, masa {masa:g} kg",
             f"Campo eléctrico E = {tuple(E)} N/C, magnético B = {tuple(B)} T"]
    if modulo_b:
        wc = abs(q) * modulo_b / masa
        notas += [f"Frecuencia de ciclotrón ω = |q|B/m = {wc:.4f} rad/s",
                  f"Periodo de giro: {2 * math.pi / wc:.4f} s"]
        if not any(E):
            notas.append("Sin campo eléctrico el módulo de la velocidad NO cambia: "
                         "el magnético curva pero no acelera, porque su fuerza es "
                         "siempre perpendicular a la velocidad.")
    # El campo, dibujado como una rejilla de líneas en su dirección.
    lineas = []
    if modulo_b:
        u = Bv / modulo_b
        for i in (-2, -1, 0, 1, 2):
            for j in (-2, -1, 0, 1, 2):
                base = np.array([i * 1.5, j * 1.5, 0.0])
                lineas.append([[_r(v) for v in (base - u * 4)],
                               [_r(v) for v in (base + u * 4)]])
    return {"ok": True, "datos": _escena(
        "Carga en campo electromagnético", [_cuerpo("carga", 0, 0.22)], marcos,
        tiempos[1] - tiempos[0] if len(tiempos) > 1 else 0.02,
        {"rapidez (m/s)": rapidez}, lineas=lineas, notas=notas), "notas": notas}


# ── 6. atractor de Lorenz ───────────────────────────────────────────────────
def lorenz(sigma: float = 10.0, rho: float = 28.0, beta: float = 8 / 3,
           t_max: float = 40.0, gemelo: bool = True) -> dict:
    """Dos puntos que empiezan a una millonésima se acaban separando del todo.

    Es el experimento de Lorenz de 1963, que es de donde sale la frase del
    aleteo de la mariposa. Con el gemelo puesto, se ve en directo.
    """
    np = _np()

    def d(_t, y):
        x, yy, z = y[:3]
        salida = [sigma * (yy - x), x * (rho - z) - yy, x * yy - beta * z]
        if len(y) > 3:
            x2, y2, z2 = y[3:]
            salida += [sigma * (y2 - x2), x2 * (rho - z2) - y2, x2 * y2 - beta * z2]
        return np.array(salida)

    inicial = [1.0, 1.0, 20.0] + ([1.000001, 1.0, 20.0] if gemelo else [])
    dt = 0.004
    tiempos, estados = rk4(d, inicial, dt, int(t_max / dt))
    tiempos, estados = _diezmar(tiempos, estados)

    esc = 0.22                                  # para que quepa en pantalla
    marcos, separacion = [], []
    for e in estados:
        marco = [[_r(e[0] * esc), _r(e[1] * esc), _r((e[2] - 25) * esc)]]
        if gemelo:
            marco.append([_r(e[3] * esc), _r(e[4] * esc), _r((e[5] - 25) * esc)])
            separacion.append(_r(math.dist(e[:3], e[3:6]), 5))
        marcos.append(marco)

    cuerpos = [_cuerpo("trayectoria", 0, 0.16)]
    if gemelo:
        cuerpos.append(_cuerpo("gemelo (+0,000001)", 3, 0.16))
    notas = [f"σ = {sigma:g}, ρ = {rho:g}, β = {beta:.4f}",
             "El sistema nunca se repite y nunca se escapa: por eso se llama "
             "atractor extraño."]
    if gemelo:
        notas.append(f"Los dos puntos salen separados por una millonésima y "
                     f"acaban a {separacion[-1]:.3f} de distancia. Eso es el "
                     "efecto mariposa, medido.")
    return {"ok": True, "datos": _escena(
        "Atractor de Lorenz", cuerpos, marcos,
        tiempos[1] - tiempos[0] if len(tiempos) > 1 else 0.02,
        {"separación entre gemelos": separacion} if gemelo else {},
        notas=notas), "notas": notas}


# ── 7. ondas: cuerda y membrana ─────────────────────────────────────────────
def cuerda(longitud: float = 6.0, modos=(1, 3), amplitud: float = 0.8,
           velocidad: float = 1.0, t_max: float = 12.0, nodos: int = 90) -> dict:
    """Onda estacionaria: la suma de modos con los extremos fijos."""
    np = _np()
    xs = np.linspace(0, longitud, nodos)
    dt = t_max / PASOS_MALLA
    marcos = []
    for i in range(PASOS_MALLA):
        t = i * dt
        y = np.zeros_like(xs)
        for n in modos:
            k = n * math.pi / longitud
            y += (amplitud / n) * np.sin(k * xs) * math.cos(velocidad * k * t)
        marcos.append([[_r(x - longitud / 2, 3), 0.0, _r(v, 3)]
                       for x, v in zip(xs, y)])
    cuerpos = [_cuerpo(f"x={x:.1f}", 0, 0.0, estela=False) for x in xs]
    frecuencias = [velocidad * n / (2 * longitud) for n in modos]
    notas = [f"Cuerda de {longitud:g} m con los extremos fijos.",
             f"Modos superpuestos: {', '.join(str(n) for n in modos)}.",
             "Frecuencias: " + ", ".join(f"{f:.3f} Hz" for f in frecuencias),
             "Los nodos no se mueven nunca: ahí los dos modos se cancelan siempre."]
    return {"ok": True, "datos": _escena(
        "Onda estacionaria en una cuerda", cuerpos, marcos, dt,
        enlaces=[[i, i + 1] for i in range(len(xs) - 1)], notas=notas),
        "notas": notas}


def membrana(modo=(1, 1), lado: float = 6.0, amplitud: float = 0.9,
             t_max: float = 10.0, n: int = 28) -> dict:
    """Un tambor cuadrado vibrando: la ecuación de ondas en dos dimensiones."""
    np = _np()
    m1, m2 = int(modo[0]), int(modo[1])
    xs = np.linspace(0, lado, n)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    forma = np.sin(m1 * math.pi * X / lado) * np.sin(m2 * math.pi * Y / lado)
    omega = math.pi * math.sqrt((m1 / lado) ** 2 + (m2 / lado) ** 2)

    caras = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b = i * n + j, i * n + j + 1
            c, d = (i + 1) * n + j + 1, (i + 1) * n + j
            caras += [(a, b, c), (a, c, d)]

    # Un modo puro es z(x,y,t) = forma(x,y)·cos(ωt). Mandar 240 fotogramas de
    # 784 vértices cada uno son 3,8 MB de HTML para repetir la misma forma
    # multiplicada por un coseno. Se manda la forma UNA vez y el coseno lo pone
    # el visor: 60 KB, y además sale perfectamente suave en vez de a saltos.
    dt = t_max / PASOS_MALLA
    base = [[_r(X[a, b] - lado / 2, 3), _r(Y[a, b] - lado / 2, 3), 0.0]
            for a in range(n) for b in range(n)]
    desplazamiento = [_r(forma[a, b] * amplitud, 4)
                      for a in range(n) for b in range(n)]
    notas = [f"Membrana cuadrada de {lado:g} m, modo ({m1}, {m2}).",
             f"Frecuencia del modo: ω = {omega:.4f} rad/s.",
             f"Líneas nodales: {m1 - 1} en un eje y {m2 - 1} en el otro. "
             "Ahí la membrana no se mueve, y es donde se acumula la arena en "
             "las figuras de Chladni."]
    return {"ok": True, "datos": _escena(
        f"Membrana vibrando · modo ({m1},{m2})", [], [], dt,
        malla={"caras": caras, "base": base, "forma": desplazamiento,
               "omega": _r(omega, 6), "marcos": PASOS_MALLA}, notas=notas),
        "notas": notas}


# ── 8. la molécula vibrando ─────────────────────────────────────────────────
def molecula(formula: str = "H2O", modo: str = "estiramiento",
             t_max: float = 6.0) -> dict:
    """La geometría RPECV de `quimica.py`, pero VIVA.

    Una molécula quieta es un dibujo; una vibrando explica por qué absorbe
    infrarrojo y por qué el CO₂ calienta el planeta y el N₂ no.
    """
    import quimica as Q
    g = Q.geometria_molecular(formula)
    if not g.get("ok"):
        return {"ok": False, "pasos": g.get("pasos", ["No entiendo esa fórmula."])}

    central, ligandos, pares = g["central"], g["ligandos"], g["pares"]
    dirs = Q._direcciones(g.get("dominios", len(ligandos)))
    usados = (dirs[pares:pares + len(ligandos)]
              if len(dirs) >= pares + len(ligandos) else dirs[:len(ligandos)])
    rc = Q._RADIO.get(central, 1.0)
    base = [(central, (0.0, 0.0, 0.0), rc)]
    for lig, d in zip(ligandos, usados):
        rl = Q._RADIO.get(lig, 0.9)
        dist = rc + rl
        base.append((lig, (d[0] * dist, d[1] * dist, d[2] * dist), rl))

    modo = (modo or "estiramiento").lower()
    simetrico = "asimetric" not in modo and "asimétric" not in modo
    flexion = "flexi" in modo or "tijera" in modo or "bending" in modo

    dt = t_max / PASOS_MALLA
    marcos = []
    for i in range(PASOS_MALLA):
        fase = math.cos(2 * math.pi * 2.0 * i * dt)
        marco = []
        for k, (_sim, pos, _r_) in enumerate(base):
            x, y, z = pos
            if k == 0:
                marco.append([_r(x), _r(y), _r(z)])
                continue
            if flexion:
                # Los ligandos se abren y cierran el ángulo, como unas tijeras.
                ang = 0.18 * fase * (1 if k % 2 else -1)
                ca, sa = math.cos(ang), math.sin(ang)
                x, y = x * ca - y * sa, x * sa + y * ca
                marco.append([_r(x), _r(y), _r(z)])
            else:
                # Estiramiento: el enlace se alarga y se acorta.
                s = 1 + 0.16 * fase * (1 if (simetrico or k % 2) else -1)
                marco.append([_r(x * s), _r(y * s), _r(z * s)])
        marcos.append(marco)

    cuerpos = []
    for k, (sim, _p, radio) in enumerate(base):
        col = Q._COLOR.get(sim, (0.55, 0.6, 0.7))
        cuerpos.append(_cuerpo(sim, k, radio * 0.42, estela=False, color=col))
    enlaces = [[0, k] for k in range(1, len(base))]

    nombre_modo = ("flexión (tijera)" if flexion else
                   "estiramiento simétrico" if simetrico else
                   "estiramiento asimétrico")
    notas = list(g["pasos"])[:4] + [
        f"Modo de vibración mostrado: {nombre_modo}.",
        "Un modo que cambia el momento dipolar absorbe infrarrojo; uno que no, "
        "es invisible a esa luz. Por eso el CO₂ es gas de efecto invernadero y "
        "el N₂ no lo es."]
    return {"ok": True, "datos": _escena(
        f"{formula} · {nombre_modo}", cuerpos, marcos, dt,
        enlaces=enlaces, notas=notas), "notas": notas}


# ── 9. LAS ECUACIONES QUE DICTE EL SEÑOR ────────────────────────────────────
def desde_ecuaciones(ecuaciones, inicial: dict = None, t_max: float = 20.0,
                     dt: float = 0.01, ejes=("x", "y", "z"),
                     titulo: str = "") -> dict:
    """Integra un sistema dictado. Es la puerta que quita el techo del módulo.

    Admite las dos formas en que se escribe esto a mano:

        {"x": "vx", "vx": "-9.8"}          derivadas primeras, estado explícito
        ["x'' = -9.8 - 0.1*x'"]            segundo orden, que se baja a primero

    Las variables que no aparezcan en `ejes` no se dibujan en el espacio, pero
    sí se enseñan en el panel de magnitudes: así un sistema de dos variables
    (presa-depredador, por ejemplo) también se puede mirar.
    """
    import sympy as sp

    derivadas = {}
    if isinstance(ecuaciones, dict):
        derivadas = {str(k): str(v) for k, v in ecuaciones.items()}
    else:
        lista = [ecuaciones] if isinstance(ecuaciones, str) else list(ecuaciones)
        for cruda in lista:
            texto = str(cruda).replace("^", "**")
            m = re.match(r"\s*([A-Za-z]\w*)\s*(''|'|\"|´´|´)?\s*=\s*(.+)$", texto)
            if not m:
                return {"ok": False, "pasos": [f"No entiendo la ecuación «{cruda}»."]}
            var, orden, lado = m.group(1), (m.group(2) or ""), m.group(3)
            # x' dentro del lado derecho se traduce a la variable de velocidad.
            lado = re.sub(r"\b([A-Za-z]\w*)\s*(?:''|\")", r"a_\1", lado)
            lado = re.sub(r"\b([A-Za-z]\w*)\s*(?:'|´)", r"v_\1", lado)
            if orden in ("''", '"', "´´"):
                derivadas[var] = f"v_{var}"
                derivadas[f"v_{var}"] = lado
            else:
                derivadas[var] = lado

    if not derivadas:
        return {"ok": False, "pasos": ["No me ha dado ninguna ecuación."]}

    nombres = list(derivadas)
    t = sp.Symbol("t")
    simbolos = [sp.Symbol(n) for n in nombres]
    try:
        expresiones = [sp.sympify(derivadas[n].replace("^", "**")) for n in nombres]
    except Exception as e:
        return {"ok": False, "pasos": [f"No pude leer las ecuaciones: {e}"]}

    libres = set()
    for ex in expresiones:
        libres |= {str(s) for s in ex.free_symbols}
    desconocidas = libres - set(nombres) - {"t"}
    if desconocidas:
        return {"ok": False, "pasos": [
            "Me faltan valores para " + ", ".join(sorted(desconocidas))
            + ". Dígamelos y lo simulo."]}

    f = sp.lambdify([t] + simbolos, expresiones, "math")
    np = _np()

    def d(tt, y):
        return np.array(f(tt, *y), dtype=float)

    inicial = {str(k): float(v) for k, v in (inicial or {}).items()}
    estado0 = [inicial.get(n, 1.0 if n in ejes else 0.0) for n in nombres]

    pasos_n = max(int(t_max / dt), 10)
    tiempos, estados = rk4(d, estado0, dt, pasos_n)
    if len(estados) < 3:
        return {"ok": False, "pasos": [
            "El sistema se dispara al infinito enseguida: revise los signos o "
            "las condiciones iniciales."]}
    tiempos, estados = _diezmar(tiempos, estados)

    indices = [nombres.index(e) if e in nombres else None for e in ejes]
    marcos = [[[_r(e[i], 4) if i is not None else 0.0 for i in indices]]
              for e in estados]
    escalares = {n: [_r(e[k], 4) for e in estados] for k, n in enumerate(nombres)}

    dibujadas = [e for e in ejes if e in nombres]
    notas = ["Sistema integrado con Runge-Kutta 4:"]
    notas += [f"  d{n}/dt = {derivadas[n]}" for n in nombres]
    notas.append("Estado inicial: "
                 + ", ".join(f"{n} = {estado0[k]:g}" for k, n in enumerate(nombres)))
    notas.append("En el espacio se dibuja " + (", ".join(dibujadas) or "nada")
                 + "; el resto está en el panel de magnitudes.")
    return {"ok": True, "datos": _escena(
        titulo or "Sistema dictado", [_cuerpo("estado", 0, 0.2)], marcos,
        tiempos[1] - tiempos[0] if len(tiempos) > 1 else dt,
        escalares, notas=notas), "notas": notas}


# ── el visor animado ────────────────────────────────────────────────────────
_VISOR_SIM = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITULO__</title>
<style>html,body{margin:0;height:100%;background:#04060a;overflow:hidden;
font-family:system-ui,Segoe UI,sans-serif;color:#9fdcff}
#cab{position:fixed;top:0;left:0;padding:10px 16px;color:#2ec6ff;font-size:13px;
letter-spacing:.14em;text-transform:uppercase;z-index:5}
#ctl{position:fixed;left:16px;bottom:16px;display:flex;gap:8px;align-items:center;
z-index:5;flex-wrap:wrap;max-width:70vw}
button{background:#080d14;color:#9fdcff;border:1px solid #123043;padding:7px 12px;
border-radius:6px;font-size:12px;cursor:pointer;letter-spacing:.06em}
button:hover{border-color:#2ec6ff;color:#fff}
input[type=range]{accent-color:#2ec6ff;width:180px}
#panel{position:fixed;top:44px;right:16px;background:rgba(4,8,14,.82);
border:1px solid #123043;border-radius:8px;padding:10px 14px;font-size:12px;
z-index:5;min-width:170px;max-width:42vw}
#panel b{color:#2ec6ff;font-weight:600}
#notas{position:fixed;left:16px;top:44px;background:rgba(4,8,14,.82);
border:1px solid #123043;border-radius:8px;padding:10px 14px;font-size:12px;
z-index:5;max-width:34vw;line-height:1.5;display:none}
#pie{position:fixed;right:16px;bottom:16px;color:#5f8ea3;font-size:11px}
.val{color:#eaf6ff;font-variant-numeric:tabular-nums}</style>
<script type="importmap">
{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}
</script></head><body>
<div id="cab">JARVIS · __TITULO__</div>
<div id="panel"></div><div id="notas"></div>
<div id="ctl">
  <button id="play">pausa</button>
  <input id="barra" type="range" min="0" max="100" value="0" step="1">
  <button id="lento">÷2</button><button id="rapido">×2</button>
  <button id="estela">estela</button><button id="ejes">ejes</button>
  <button id="texto">explicación</button>
</div>
<div id="pie">arrastra para orbitar · rueda para acercar</div>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const D=__DATOS__;
const S=new THREE.Scene();S.background=new THREE.Color(0x04060a);
S.fog=new THREE.FogExp2(0x04060a,0.012);
const C=new THREE.PerspectiveCamera(55,innerWidth/innerHeight,0.05,4000);
const R=new THREE.WebGLRenderer({antialias:true});
R.setPixelRatio(Math.min(devicePixelRatio,2));R.setSize(innerWidth,innerHeight);
document.body.appendChild(R.domElement);
const O=new OrbitControls(C,R.domElement);O.enableDamping=true;
S.add(new THREE.AmbientLight(0x8fbfd8,0.8));
const luz=new THREE.DirectionalLight(0xffffff,1.1);luz.position.set(6,9,7);S.add(luz);
const luz2=new THREE.PointLight(0x2ec6ff,0.7,120);luz2.position.set(-8,4,-6);S.add(luz2);

const marcos=D.marcos||[], nM=marcos.length;
const cuerpos=D.cuerpos||[], malla=D.malla||{};
// La malla llega de dos formas: fotograma a fotograma, o —cuando es un modo
// puro— como forma fija más su frecuencia, y el coseno lo ponemos aquí.
const analitica=Array.isArray(malla.forma);
const mallaMarcos=analitica?[]:(malla.marcos||[]);
const nMalla=analitica?(malla.marcos||240):mallaMarcos.length;
const total=Math.max(nM,nMalla);

// --- cuerpos ---
const esferas=[], estelas=[], puntosEstela=[];
cuerpos.forEach((c,i)=>{
  const col=new THREE.Color(c.color[0],c.color[1],c.color[2]);
  const rad=c.radio||0.2;
  if(rad>0.001){
    const m=new THREE.Mesh(new THREE.SphereGeometry(rad,24,18),
      new THREE.MeshStandardMaterial({color:col,roughness:0.35,metalness:0.15,
        emissive:col.clone().multiplyScalar(0.18)}));
    S.add(m);esferas.push(m);
  } else esferas.push(null);
  if(c.estela){
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(total*3),3));
    g.setDrawRange(0,0);
    const l=new THREE.Line(g,new THREE.LineBasicMaterial({color:col,transparent:true,opacity:0.75}));
    S.add(l);estelas.push(l);puntosEstela.push(g.attributes.position.array);
  } else {estelas.push(null);puntosEstela.push(null);}
});

// --- enlaces (varillas / cuerda) ---
const enlaces=D.enlaces||[];
let gEnl=null;
if(enlaces.length){
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(enlaces.length*6),3));
  gEnl=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x7fb6cf}));
  S.add(gEnl);
}

// --- malla animada (cuerda, membrana) ---
let mallaObj=null;
if(nMalla){
  const g=new THREE.BufferGeometry();
  const nV=analitica?malla.base.length:mallaMarcos[0].length;
  g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(nV*3),3));
  const idx=[];(malla.caras||[]).forEach(c=>idx.push(c[0],c[1],c[2]));
  g.setIndex(idx);
  mallaObj=new THREE.Mesh(g,new THREE.MeshStandardMaterial({color:0x2ec6ff,
    side:THREE.DoubleSide,roughness:0.4,metalness:0.1,flatShading:false,
    emissive:0x08243a}));
  S.add(mallaObj);
  S.add(new THREE.Mesh(g,new THREE.MeshBasicMaterial({color:0x6fe0ff,wireframe:true,
    transparent:true,opacity:0.14})));
}

// --- líneas fijas (campo, suelo) ---
(D.lineas||[]).forEach(par=>{
  const g=new THREE.BufferGeometry().setFromPoints(
    par.map(p=>new THREE.Vector3(p[0],p[1],p[2])));
  S.add(new THREE.Line(g,new THREE.LineBasicMaterial({color:0x14405c})));
});

const ejes=new THREE.AxesHelper(4);S.add(ejes);
const rejilla=new THREE.GridHelper(20,20,0x0f2c3e,0x0a1d29);
rejilla.rotation.x=Math.PI/2;S.add(rejilla);

// --- encuadre automático ---
function encuadrar(){
  const caja=new THREE.Box3();
  const mirar=(p)=>caja.expandByPoint(new THREE.Vector3(p[0],p[1],p[2]));
  const salto=Math.max(1,Math.floor(total/60));
  for(let i=0;i<nM;i+=salto) marcos[i].forEach(mirar);
  if(analitica) malla.base.forEach((b,n)=>{
    mirar([b[0],b[1],b[2]+malla.forma[n]]);mirar([b[0],b[1],b[2]-malla.forma[n]]);});
  else for(let i=0;i<mallaMarcos.length;i+=salto) mallaMarcos[i].forEach(mirar);
  if(caja.isEmpty()) caja.expandByPoint(new THREE.Vector3(3,3,3));
  const c=caja.getCenter(new THREE.Vector3()), t=caja.getSize(new THREE.Vector3());
  const r=Math.max(t.x,t.y,t.z,1)*1.15;
  O.target.copy(c);C.position.set(c.x+r*1.1,c.y-r*1.5,c.z+r*0.85);
  C.near=r/200;C.far=r*60;C.updateProjectionMatrix();O.update();
}
encuadrar();

// --- animación ---
let k=0, corriendo=true, vel=1, verEstela=true;
const panel=document.getElementById('panel');
const barra=document.getElementById('barra');
barra.max=Math.max(total-1,1);
const claves=Object.keys(D.escalares||{});

function pintar(i){
  if(nM){
    const marco=marcos[i];
    for(let b=0;b<marco.length&&b<esferas.length;b++){
      const p=marco[b];
      if(esferas[b]) esferas[b].position.set(p[0],p[1],p[2]);
      const arr=puntosEstela[b];
      if(arr){arr[i*3]=p[0];arr[i*3+1]=p[1];arr[i*3+2]=p[2];
        estelas[b].geometry.setDrawRange(0,verEstela?i+1:0);
        estelas[b].geometry.attributes.position.needsUpdate=true;}
    }
    if(gEnl){
      const pos=gEnl.geometry.attributes.position.array;
      enlaces.forEach((e,n)=>{
        const a=e[0]<0?[0,0,0]:marco[e[0]], b=e[1]<0?[0,0,0]:marco[e[1]];
        if(!a||!b) return;
        pos[n*6]=a[0];pos[n*6+1]=a[1];pos[n*6+2]=a[2];
        pos[n*6+3]=b[0];pos[n*6+4]=b[1];pos[n*6+5]=b[2];
      });
      gEnl.geometry.attributes.position.needsUpdate=true;
    }
  }
  if(nMalla&&mallaObj){
    const pos=mallaObj.geometry.attributes.position.array;
    if(analitica){
      const c=Math.cos(malla.omega*i*D.dt);
      for(let n=0;n<malla.base.length;n++){
        const b=malla.base[n];
        pos[n*3]=b[0];pos[n*3+1]=b[1];pos[n*3+2]=b[2]+malla.forma[n]*c;
      }
    } else {
      const v=mallaMarcos[Math.min(i,nMalla-1)];
      for(let n=0;n<v.length;n++){pos[n*3]=v[n][0];pos[n*3+1]=v[n][1];pos[n*3+2]=v[n][2];}
    }
    mallaObj.geometry.attributes.position.needsUpdate=true;
    mallaObj.geometry.computeVertexNormals();
  }
  let html='<b>t = '+(i*D.dt).toFixed(3)+' s</b><br>';
  claves.forEach(c=>{
    const s=D.escalares[c];
    if(s&&s.length) html+=c+': <span class="val">'+
      (s[Math.min(i,s.length-1)]).toFixed(4)+'</span><br>';
  });
  html+='<span style="color:#5f8ea3">marco '+(i+1)+' de '+total+'</span>';
  panel.innerHTML=html;
  barra.value=i;
}

document.getElementById('play').onclick=e=>{
  corriendo=!corriendo;e.target.textContent=corriendo?'pausa':'seguir';};
document.getElementById('lento').onclick=()=>vel=Math.max(vel/2,0.125);
document.getElementById('rapido').onclick=()=>vel=Math.min(vel*2,16);
document.getElementById('ejes').onclick=()=>{ejes.visible=!ejes.visible;
  rejilla.visible=!rejilla.visible;};
document.getElementById('estela').onclick=()=>{verEstela=!verEstela;};
const notas=document.getElementById('notas');
notas.innerHTML=(D.notas||[]).map(n=>'· '+n).join('<br>');
document.getElementById('texto').onclick=()=>{
  notas.style.display=notas.style.display==='block'?'none':'block';};
barra.oninput=e=>{corriendo=false;
  document.getElementById('play').textContent='seguir';
  k=+e.target.value;pintar(k);};

let acumulado=0;
function bucle(){
  requestAnimationFrame(bucle);
  if(corriendo&&total){
    acumulado+=vel;
    while(acumulado>=1){k=(k+1)%total;acumulado-=1;
      if(k===0){for(const a of puntosEstela) if(a) a.fill(0);}}
    pintar(k);
  }
  O.update();R.render(S,C);
}
pintar(0);bucle();
addEventListener('resize',()=>{C.aspect=innerWidth/innerHeight;
  C.updateProjectionMatrix();R.setSize(innerWidth,innerHeight);});
addEventListener('keydown',e=>{if(e.code==='Space'){e.preventDefault();
  document.getElementById('play').click();}});
</script></body></html>"""


def visor(datos: dict, ruta_html: str, titulo: str = "Simulación") -> str:
    """Escribe el visor con los marcos EMBEBIDOS, como el resto de visores.

    Van dentro a propósito: con `file://` el navegador bloquea cualquier lectura
    de un archivo de al lado, así que un visor que cargara los datos aparte no
    se vería al hacer doble clic.
    """
    if not datos:
        return ""
    crudo = json.dumps(datos, allow_nan=False, default=lambda o: None,
                       separators=(",", ":"))
    html = (_VISOR_SIM.replace("__TITULO__", (titulo or "Simulación").replace("<", ""))
                      .replace("__DATOS__", crudo))
    os.makedirs(os.path.dirname(ruta_html), exist_ok=True)
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(html)
    return ruta_html


# ── catálogo y despacho ─────────────────────────────────────────────────────
CATALOGO = {
    "tiro": (tiro, "proyectil en 3D con rozamiento y viento"),
    "orbita": (orbita, "N cuerpos con la gravitación de Newton"),
    "pendulo": (pendulo, "péndulo simple y doble (caos)"),
    "muelle": (muelle, "oscilador amortiguado y forzado, con resonancia"),
    "carga": (carga, "carga en campo eléctrico y magnético"),
    "lorenz": (lorenz, "atractor de Lorenz y el efecto mariposa"),
    "cuerda": (cuerda, "onda estacionaria en una cuerda"),
    "membrana": (membrana, "membrana vibrando (ondas en 2D)"),
    "molecula": (molecula, "molécula vibrando en sus modos"),
    "ecuaciones": (desde_ecuaciones, "las ecuaciones que dicte el señor"),
}


def simular(sistema: str, parametros: dict = None, carpeta: str = "",
            abrir_visor: bool = True, log=print) -> dict:
    """Corre un sistema del catálogo y deja el visor animado listo."""
    clave = (sistema or "").strip().lower()
    if clave not in CATALOGO:
        return {"ok": False, "pasos": [
            f"No sé simular «{sistema}». Sé de: "
            + ", ".join(f"{k} ({d})" for k, (_f, d) in CATALOGO.items()) + "."]}
    funcion = CATALOGO[clave][0]
    try:
        r = funcion(**(parametros or {}))
    except TypeError as e:
        return {"ok": False, "pasos": [f"Esos parámetros no encajan con «{clave}»: {e}"]}
    except Exception as e:
        log(f"[SIM] {clave} falló: {e}")
        return {"ok": False, "pasos": [f"La simulación de «{clave}» falló: {e}"]}
    if not r.get("ok"):
        return r

    datos = r["datos"]
    out = carpeta or M.carpeta_salida(f"simulacion-{clave}")
    html = visor(datos, os.path.join(out, "simulacion.html"), datos.get("titulo", clave))
    r.update({"html": html, "carpeta": out, "sistema": clave})
    r.setdefault("pasos", list(r.get("notas") or []))
    if abrir_visor and html:
        M.abrir(html, log=log)
    return r


def catalogo_texto() -> str:
    return "\n".join(f"  {k:12} {d}" for k, (_f, d) in CATALOGO.items())


def resumen_estado() -> dict:
    try:
        import numpy  # noqa: F401
        hay_numpy = True
    except Exception:
        hay_numpy = False
    try:
        import sympy  # noqa: F401
        hay_sympy = True
    except Exception:
        hay_sympy = False
    return {"sistemas": sorted(CATALOGO), "numpy": hay_numpy, "sympy": hay_sympy,
            "marcos_max": PASOS_MAX}


if __name__ == "__main__":
    print("Sistemas que sé simular:\n" + catalogo_texto())
