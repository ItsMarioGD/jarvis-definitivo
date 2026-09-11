#!/usr/bin/env python3
"""
fisica.py - El físico de JARVIS y ULTRON
========================================
Monta sobre `matematica.py`. Dos capas:

1. BANCO DE FÓRMULAS. Cada ley está escrita una sola vez como ecuación de
   sympy con sus símbolos, sus unidades y su nombre. Se le dan los datos que
   se conocen y se le pide la incógnita: el módulo despeja SOLO (no hay una
   versión «despejada» por cada caso) y devuelve el desarrollo. Cubre
   cinemática, dinámica, energía, momento, rotación, gravitación, fluidos,
   oscilaciones, ondas, sonido, termodinámica, electrostática, circuitos,
   magnetismo, óptica y física moderna.

2. ANÁLISIS CON GRÁFICA. Situaciones completas que además dibujan:
   tiro parabólico (2D + trayectoria 3D imprimible), movimiento rectilíneo
   (x-t, v-t, a-t), oscilador armónico (x-t + espacio de fases), onda viajera
   (superficie 3D y(x,t)), campo eléctrico de varias cargas (líneas 2D +
   superficie 3D de potencial), circuito RC/RLC y diagrama p-V.

Las unidades se manejan con `pint` si está instalado; si no, se trabaja en el
SI y se avisa.
"""
import math
import os
import re

import matematica as M

# ── constantes en SI ───────────────────────────────────────────────────────
CONSTANTES = {
    "g": (9.80665, "m/s²", "gravedad en la superficie terrestre"),
    "G": (6.67430e-11, "N·m²/kg²", "constante de gravitación universal"),
    "c": (299792458.0, "m/s", "velocidad de la luz en el vacío"),
    "h": (6.62607015e-34, "J·s", "constante de Planck"),
    "hbar": (1.054571817e-34, "J·s", "Planck reducida"),
    "k_B": (1.380649e-23, "J/K", "constante de Boltzmann"),
    "N_A": (6.02214076e23, "1/mol", "número de Avogadro"),
    "R": (8.314462618, "J/(mol·K)", "constante de los gases"),
    "e": (1.602176634e-19, "C", "carga elemental"),
    "m_e": (9.1093837015e-31, "kg", "masa del electrón"),
    "m_p": (1.67262192369e-27, "kg", "masa del protón"),
    "m_n": (1.67492749804e-27, "kg", "masa del neutrón"),
    "epsilon_0": (8.8541878128e-12, "F/m", "permitividad del vacío"),
    "mu_0": (1.25663706212e-6, "T·m/A", "permeabilidad del vacío"),
    "k_e": (8.9875517923e9, "N·m²/C²", "constante de Coulomb"),
    "sigma": (5.670374419e-8, "W/(m²·K⁴)", "constante de Stefan-Boltzmann"),
    "u": (1.66053906660e-27, "kg", "unidad de masa atómica"),
    "atm": (101325.0, "Pa", "presión atmosférica normal"),
    "M_T": (5.972e24, "kg", "masa de la Tierra"),
    "R_T": (6.371e6, "m", "radio medio de la Tierra"),
}


def constante(nombre: str):
    n = (nombre or "").strip()
    if n in CONSTANTES:
        return CONSTANTES[n]
    for k, v in CONSTANTES.items():
        if k.lower() == n.lower() or n.lower() in v[2].lower():
            return v
    return None


# ── banco de fórmulas ──────────────────────────────────────────────────────
# (clave, tema, enunciado en sympy, {símbolo: (qué es, unidad)})
FORMULAS = {
    # cinemática
    "mru": ("cinemática", "x - x0 - v*t",
            {"x": ("posición", "m"), "x0": ("posición inicial", "m"),
             "v": ("velocidad", "m/s"), "t": ("tiempo", "s")}),
    "mrua_posicion": ("cinemática", "x - x0 - v0*t - a*t**2/2",
                      {"x": ("posición", "m"), "x0": ("posición inicial", "m"),
                       "v0": ("velocidad inicial", "m/s"),
                       "a": ("aceleración", "m/s²"), "t": ("tiempo", "s")}),
    "mrua_velocidad": ("cinemática", "v - v0 - a*t",
                       {"v": ("velocidad final", "m/s"), "v0": ("velocidad inicial", "m/s"),
                        "a": ("aceleración", "m/s²"), "t": ("tiempo", "s")}),
    "torricelli": ("cinemática", "v**2 - v0**2 - 2*a*d",
                   {"v": ("velocidad final", "m/s"), "v0": ("velocidad inicial", "m/s"),
                    "a": ("aceleración", "m/s²"), "d": ("desplazamiento", "m")}),
    "caida_libre": ("cinemática", "h - v0*t - g*t**2/2",
                    {"h": ("altura caída", "m"), "v0": ("velocidad inicial", "m/s"),
                     "g": ("gravedad", "m/s²"), "t": ("tiempo", "s")}),
    "alcance_proyectil": ("cinemática", "R - v0**2*sin(2*theta)/g",
                          {"R": ("alcance", "m"), "v0": ("rapidez inicial", "m/s"),
                           "theta": ("ángulo", "rad"), "g": ("gravedad", "m/s²")}),
    "altura_maxima": ("cinemática", "H - v0**2*sin(theta)**2/(2*g)",
                      {"H": ("altura máxima", "m"), "v0": ("rapidez inicial", "m/s"),
                       "theta": ("ángulo", "rad"), "g": ("gravedad", "m/s²")}),
    "circular_velocidad": ("cinemática", "v - omega*r",
                           {"v": ("velocidad tangencial", "m/s"),
                            "omega": ("velocidad angular", "rad/s"), "r": ("radio", "m")}),
    "aceleracion_centripeta": ("cinemática", "a_c - v**2/r",
                               {"a_c": ("aceleración centrípeta", "m/s²"),
                                "v": ("velocidad", "m/s"), "r": ("radio", "m")}),
    "periodo_circular": ("cinemática", "T - 2*pi/omega",
                         {"T": ("periodo", "s"), "omega": ("velocidad angular", "rad/s")}),
    # dinámica
    "newton2": ("dinámica", "F - m*a",
                {"F": ("fuerza neta", "N"), "m": ("masa", "kg"),
                 "a": ("aceleración", "m/s²")}),
    "peso": ("dinámica", "P - m*g",
             {"P": ("peso", "N"), "m": ("masa", "kg"), "g": ("gravedad", "m/s²")}),
    "rozamiento": ("dinámica", "f - mu*N",
                   {"f": ("fuerza de rozamiento", "N"),
                    "mu": ("coeficiente de rozamiento", "—"), "N": ("normal", "N")}),
    "plano_inclinado": ("dinámica", "a - g*(sin(theta) - mu*cos(theta))",
                        {"a": ("aceleración", "m/s²"), "g": ("gravedad", "m/s²"),
                         "theta": ("inclinación", "rad"),
                         "mu": ("coeficiente de rozamiento", "—")}),
    "hooke": ("dinámica", "F - k*x",
              {"F": ("fuerza del muelle", "N"), "k": ("constante elástica", "N/m"),
               "x": ("deformación", "m")}),
    "impulso": ("dinámica", "J - F*t",
                {"J": ("impulso", "N·s"), "F": ("fuerza", "N"), "t": ("tiempo", "s")}),
    "momento_lineal": ("dinámica", "p - m*v",
                       {"p": ("cantidad de movimiento", "kg·m/s"),
                        "m": ("masa", "kg"), "v": ("velocidad", "m/s")}),
    # energía
    "energia_cinetica": ("energía", "E_c - m*v**2/2",
                         {"E_c": ("energía cinética", "J"), "m": ("masa", "kg"),
                          "v": ("velocidad", "m/s")}),
    "energia_potencial": ("energía", "E_p - m*g*h",
                          {"E_p": ("energía potencial", "J"), "m": ("masa", "kg"),
                           "g": ("gravedad", "m/s²"), "h": ("altura", "m")}),
    "energia_elastica": ("energía", "E_e - k*x**2/2",
                         {"E_e": ("energía elástica", "J"),
                          "k": ("constante elástica", "N/m"), "x": ("deformación", "m")}),
    "trabajo": ("energía", "W - F*d*cos(theta)",
                {"W": ("trabajo", "J"), "F": ("fuerza", "N"), "d": ("distancia", "m"),
                 "theta": ("ángulo fuerza-desplazamiento", "rad")}),
    "potencia": ("energía", "P - W/t",
                 {"P": ("potencia", "W"), "W": ("trabajo", "J"), "t": ("tiempo", "s")}),
    "rendimiento": ("energía", "eta - W_util/W_total",
                    {"eta": ("rendimiento", "—"), "W_util": ("trabajo útil", "J"),
                     "W_total": ("energía aportada", "J")}),
    # rotación
    "torque": ("rotación", "tau - r*F*sin(theta)",
               {"tau": ("momento de fuerza", "N·m"), "r": ("brazo", "m"),
                "F": ("fuerza", "N"), "theta": ("ángulo", "rad")}),
    "newton2_rotacion": ("rotación", "tau - I*alpha",
                         {"tau": ("momento resultante", "N·m"),
                          "I": ("momento de inercia", "kg·m²"),
                          "alpha": ("aceleración angular", "rad/s²")}),
    "momento_angular": ("rotación", "L - I*omega",
                        {"L": ("momento angular", "kg·m²/s"),
                         "I": ("momento de inercia", "kg·m²"),
                         "omega": ("velocidad angular", "rad/s")}),
    "energia_rotacion": ("rotación", "E_r - I*omega**2/2",
                         {"E_r": ("energía cinética de rotación", "J"),
                          "I": ("momento de inercia", "kg·m²"),
                          "omega": ("velocidad angular", "rad/s")}),
    # gravitación
    "gravitacion": ("gravitación", "F - G*m1*m2/r**2",
                    {"F": ("fuerza gravitatoria", "N"), "G": ("constante G", "N·m²/kg²"),
                     "m1": ("masa 1", "kg"), "m2": ("masa 2", "kg"),
                     "r": ("distancia", "m")}),
    "velocidad_orbital": ("gravitación", "v - sqrt(G*Mc/r)",
                          {"v": ("velocidad orbital", "m/s"), "G": ("constante G", "N·m²/kg²"),
                           "Mc": ("masa central", "kg"), "r": ("radio de la órbita", "m")}),
    "velocidad_escape": ("gravitación", "v_e - sqrt(2*G*Mc/r)",
                         {"v_e": ("velocidad de escape", "m/s"),
                          "G": ("constante G", "N·m²/kg²"), "Mc": ("masa del astro", "kg"),
                          "r": ("radio", "m")}),
    "tercera_kepler": ("gravitación", "T**2 - 4*pi**2*r**3/(G*Mc)",
                       {"T": ("periodo orbital", "s"), "r": ("semieje mayor", "m"),
                        "G": ("constante G", "N·m²/kg²"), "Mc": ("masa central", "kg")}),
    # fluidos
    "presion": ("fluidos", "P - F/A",
                {"P": ("presión", "Pa"), "F": ("fuerza", "N"), "A": ("área", "m²")}),
    "presion_hidrostatica": ("fluidos", "P - rho*g*h",
                             {"P": ("presión hidrostática", "Pa"),
                              "rho": ("densidad", "kg/m³"), "g": ("gravedad", "m/s²"),
                              "h": ("profundidad", "m")}),
    "arquimedes": ("fluidos", "E - rho*g*V",
                   {"E": ("empuje", "N"), "rho": ("densidad del fluido", "kg/m³"),
                    "g": ("gravedad", "m/s²"), "V": ("volumen desalojado", "m³")}),
    "continuidad": ("fluidos", "A1*v1 - A2*v2",
                    {"A1": ("sección 1", "m²"), "v1": ("velocidad 1", "m/s"),
                     "A2": ("sección 2", "m²"), "v2": ("velocidad 2", "m/s")}),
    "bernoulli": ("fluidos", "P1 + rho*v1**2/2 + rho*g*h1 - P2 - rho*v2**2/2 - rho*g*h2",
                  {"P1": ("presión 1", "Pa"), "P2": ("presión 2", "Pa"),
                   "v1": ("velocidad 1", "m/s"), "v2": ("velocidad 2", "m/s"),
                   "h1": ("altura 1", "m"), "h2": ("altura 2", "m"),
                   "rho": ("densidad", "kg/m³"), "g": ("gravedad", "m/s²")}),
    # oscilaciones y ondas
    "periodo_pendulo": ("oscilaciones", "T - 2*pi*sqrt(L/g)",
                        {"T": ("periodo", "s"), "L": ("longitud", "m"),
                         "g": ("gravedad", "m/s²")}),
    "periodo_muelle": ("oscilaciones", "T - 2*pi*sqrt(m/k)",
                       {"T": ("periodo", "s"), "m": ("masa", "kg"),
                        "k": ("constante elástica", "N/m")}),
    "frecuencia": ("oscilaciones", "f - 1/T",
                   {"f": ("frecuencia", "Hz"), "T": ("periodo", "s")}),
    "onda": ("ondas", "v - lamda*f",
             {"v": ("velocidad de la onda", "m/s"), "lamda": ("longitud de onda", "m"),
              "f": ("frecuencia", "Hz")}),
    "doppler": ("ondas", "f_obs - f*(v + v_o)/(v - v_f)",
                {"f_obs": ("frecuencia observada", "Hz"), "f": ("frecuencia emitida", "Hz"),
                 "v": ("velocidad del sonido", "m/s"),
                 "v_o": ("velocidad del observador", "m/s"),
                 "v_f": ("velocidad de la fuente", "m/s")}),
    "intensidad_sonora": ("ondas", "beta - 10*log(I/I0, 10)",
                          {"beta": ("nivel sonoro", "dB"), "I": ("intensidad", "W/m²"),
                           "I0": ("umbral 1e-12", "W/m²")}),
    # termodinámica
    "gases_ideales": ("termodinámica", "P*V - n*R*T",
                      {"P": ("presión", "Pa"), "V": ("volumen", "m³"),
                       "n": ("moles", "mol"), "R": ("constante de los gases", "J/(mol·K)"),
                       "T": ("temperatura", "K")}),
    "calor_sensible": ("termodinámica", "Q - m*ce*DT",
                       {"Q": ("calor", "J"), "m": ("masa", "kg"),
                        "ce": ("calor específico", "J/(kg·K)"),
                        "DT": ("variación de temperatura", "K")}),
    "calor_latente": ("termodinámica", "Q - m*L",
                      {"Q": ("calor", "J"), "m": ("masa", "kg"),
                       "L": ("calor latente", "J/kg")}),
    "primera_ley": ("termodinámica", "DU - Q + W",
                    {"DU": ("variación de energía interna", "J"),
                     "Q": ("calor absorbido", "J"), "W": ("trabajo hecho por el gas", "J")}),
    "rendimiento_carnot": ("termodinámica", "eta - 1 + Tf/Tc",
                           {"eta": ("rendimiento de Carnot", "—"),
                            "Tf": ("temperatura del foco frío", "K"),
                            "Tc": ("temperatura del foco caliente", "K")}),
    "dilatacion_lineal": ("termodinámica", "DL - alpha*L0*DT",
                          {"DL": ("alargamiento", "m"),
                           "alpha": ("coeficiente de dilatación", "1/K"),
                           "L0": ("longitud inicial", "m"), "DT": ("salto térmico", "K")}),
    # electricidad
    "coulomb": ("electrostática", "F - k_e*q1*q2/r**2",
                {"F": ("fuerza eléctrica", "N"), "k_e": ("constante de Coulomb", "N·m²/C²"),
                 "q1": ("carga 1", "C"), "q2": ("carga 2", "C"), "r": ("distancia", "m")}),
    "campo_electrico": ("electrostática", "E - k_e*q/r**2",
                        {"E": ("campo eléctrico", "N/C"),
                         "k_e": ("constante de Coulomb", "N·m²/C²"),
                         "q": ("carga", "C"), "r": ("distancia", "m")}),
    "potencial_electrico": ("electrostática", "V - k_e*q/r",
                            {"V": ("potencial", "V"),
                             "k_e": ("constante de Coulomb", "N·m²/C²"),
                             "q": ("carga", "C"), "r": ("distancia", "m")}),
    "capacidad": ("electrostática", "C - Q/V",
                  {"C": ("capacidad", "F"), "Q": ("carga", "C"), "V": ("tensión", "V")}),
    "energia_condensador": ("electrostática", "U - C*V**2/2",
                            {"U": ("energía almacenada", "J"), "C": ("capacidad", "F"),
                             "V": ("tensión", "V")}),
    "ohm": ("circuitos", "V - I*Rr",
            {"V": ("tensión", "V"), "I": ("intensidad", "A"), "Rr": ("resistencia", "Ω")}),
    "potencia_electrica": ("circuitos", "P - V*I",
                           {"P": ("potencia", "W"), "V": ("tensión", "V"),
                            "I": ("intensidad", "A")}),
    "resistividad": ("circuitos", "Rr - rho*L/A",
                     {"Rr": ("resistencia", "Ω"), "rho": ("resistividad", "Ω·m"),
                      "L": ("longitud", "m"), "A": ("sección", "m²")}),
    "carga_rc": ("circuitos", "tau - Rr*C",
                 {"tau": ("constante de tiempo", "s"), "Rr": ("resistencia", "Ω"),
                  "C": ("capacidad", "F")}),
    # magnetismo
    "lorentz": ("magnetismo", "F - q*v*B*sin(theta)",
                {"F": ("fuerza magnética", "N"), "q": ("carga", "C"),
                 "v": ("velocidad", "m/s"), "B": ("campo magnético", "T"),
                 "theta": ("ángulo v-B", "rad")}),
    "fuerza_conductor": ("magnetismo", "F - I*L*B*sin(theta)",
                         {"F": ("fuerza", "N"), "I": ("intensidad", "A"),
                          "L": ("longitud del conductor", "m"),
                          "B": ("campo magnético", "T"), "theta": ("ángulo", "rad")}),
    "campo_solenoide": ("magnetismo", "B - mu_0*N*I/L",
                        {"B": ("campo en el interior", "T"),
                         "mu_0": ("permeabilidad", "T·m/A"), "N": ("número de espiras", "—"),
                         "I": ("intensidad", "A"), "L": ("longitud", "m")}),
    "faraday": ("magnetismo", "fem + N*dPhi/dt",
                {"fem": ("fuerza electromotriz", "V"), "N": ("espiras", "—"),
                 "dPhi": ("variación de flujo", "Wb"), "dt": ("tiempo", "s")}),
    "radio_ciclotron": ("magnetismo", "r - m*v/(q*B)",
                        {"r": ("radio de la órbita", "m"), "m": ("masa", "kg"),
                         "v": ("velocidad", "m/s"), "q": ("carga", "C"),
                         "B": ("campo", "T")}),
    # óptica
    "snell": ("óptica", "n1*sin(theta1) - n2*sin(theta2)",
              {"n1": ("índice medio 1", "—"), "theta1": ("ángulo de incidencia", "rad"),
               "n2": ("índice medio 2", "—"), "theta2": ("ángulo de refracción", "rad")}),
    "lentes": ("óptica", "1/f - 1/s_o - 1/s_i",
               {"f": ("distancia focal", "m"), "s_o": ("distancia al objeto", "m"),
                "s_i": ("distancia a la imagen", "m")}),
    "aumento": ("óptica", "m_a + s_i/s_o",
                {"m_a": ("aumento", "—"), "s_i": ("distancia imagen", "m"),
                 "s_o": ("distancia objeto", "m")}),
    "young": ("óptica", "y - m_o*lamda*Ld/d",
              {"y": ("posición de la franja", "m"), "m_o": ("orden", "—"),
               "lamda": ("longitud de onda", "m"), "Ld": ("distancia a la pantalla", "m"),
               "d": ("separación de rendijas", "m")}),
    # moderna
    "fotoelectrico": ("moderna", "E_k - h*f + W_t",
                      {"E_k": ("energía cinética máxima", "J"),
                       "h": ("constante de Planck", "J·s"), "f": ("frecuencia", "Hz"),
                       "W_t": ("trabajo de extracción", "J")}),
    "energia_foton": ("moderna", "E - h*c/lamda",
                      {"E": ("energía del fotón", "J"), "h": ("Planck", "J·s"),
                       "c": ("velocidad de la luz", "m/s"),
                       "lamda": ("longitud de onda", "m")}),
    "de_broglie": ("moderna", "lamda - h/(m*v)",
                   {"lamda": ("longitud de onda", "m"), "h": ("Planck", "J·s"),
                    "m": ("masa", "kg"), "v": ("velocidad", "m/s")}),
    "equivalencia_masa": ("moderna", "E - m*c**2",
                          {"E": ("energía", "J"), "m": ("masa", "kg"),
                           "c": ("velocidad de la luz", "m/s")}),
    "dilatacion_tiempo": ("moderna", "Dt - Dt0/sqrt(1 - v**2/c**2)",
                          {"Dt": ("tiempo medido", "s"), "Dt0": ("tiempo propio", "s"),
                           "v": ("velocidad", "m/s"), "c": ("velocidad de la luz", "m/s")}),
    "contraccion_longitud": ("moderna", "L - L0*sqrt(1 - v**2/c**2)",
                             {"L": ("longitud medida", "m"), "L0": ("longitud propia", "m"),
                              "v": ("velocidad", "m/s"), "c": ("luz", "m/s")}),
    "decaimiento": ("moderna", "N - N0*exp(-lamda*t)",
                    {"N": ("núcleos restantes", "—"), "N0": ("núcleos iniciales", "—"),
                     "lamda": ("constante de desintegración", "1/s"),
                     "t": ("tiempo", "s")}),
    "semivida": ("moderna", "t_med - log(2)/lamda",
                 {"t_med": ("periodo de semidesintegración", "s"),
                  "lamda": ("constante de desintegración", "1/s")}),
}

# Sinónimos hablados -> clave del banco.
_ALIAS = {
    "segunda ley de newton": "newton2", "fuerza neta": "newton2",
    "ley de hooke": "hooke", "muelle": "hooke", "resorte": "hooke",
    "energia cinetica": "energia_cinetica", "energía cinética": "energia_cinetica",
    "energia potencial": "energia_potencial", "energía potencial": "energia_potencial",
    "ley de ohm": "ohm", "ohm": "ohm",
    "ley de coulomb": "coulomb", "coulomb": "coulomb",
    "gases ideales": "gases_ideales", "ley de los gases": "gases_ideales",
    "pendulo": "periodo_pendulo", "péndulo": "periodo_pendulo",
    "efecto doppler": "doppler", "doppler": "doppler",
    "ley de snell": "snell", "refraccion": "snell", "refracción": "snell",
    "lente": "lentes", "espejo": "lentes",
    "gravitacion universal": "gravitacion", "gravitación universal": "gravitacion",
    "velocidad de escape": "velocidad_escape",
    "efecto fotoelectrico": "fotoelectrico", "efecto fotoeléctrico": "fotoelectrico",
    "de broglie": "de_broglie", "planck": "energia_foton",
    "relatividad": "dilatacion_tiempo",
    "primera ley de la termodinamica": "primera_ley",
    "carnot": "rendimiento_carnot",
    "arquimedes": "arquimedes", "arquímedes": "arquimedes",
    "bernoulli": "bernoulli", "presion hidrostatica": "presion_hidrostatica",
    "torricelli": "torricelli", "caida libre": "caida_libre", "caída libre": "caida_libre",
    "tiro parabolico": "alcance_proyectil", "tiro parabólico": "alcance_proyectil",
}


def buscar_formula(texto: str) -> list:
    """Devuelve las claves del banco que encajan con lo que se ha dicho."""
    t = (texto or "").lower()
    hits = []
    for frase, clave in _ALIAS.items():
        if frase in t:
            hits.append(clave)
    for clave, (tema, _e, _s) in FORMULAS.items():
        if clave.replace("_", " ") in t and clave not in hits:
            hits.append(clave)
    return hits


def _plano(t: str) -> str:
    """Minúsculas y sin tildes: «óptica» y «optica» son el mismo tema."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                   if unicodedata.category(c) != "Mn")


def formulario(tema: str = "") -> str:
    """Chuleta legible de todo el banco, o de un tema."""
    t = _plano(tema).strip()
    if t in ("fisica", "todo", "completo"):
        t = ""
    lineas, actual = [], ""
    for clave, (tm, ec, sim) in sorted(FORMULAS.items(), key=lambda kv: kv[1][0]):
        if t and t not in _plano(tm) and t not in _plano(clave):
            continue
        if tm != actual:
            actual = tm
            lineas.append(f"\n── {tm.upper()} ──")
        # `ecuacion()` y no `M.sympificar()`: estas cadenas ya están en notación
        # de sympy, y hay que forzar los símbolos (I, E, N, Q, beta).
        lineas.append(f"  {clave}: {M.bonito(ecuacion(clave))} = 0")
    return "\n".join(lineas) or "No tengo ese tema en el formulario."


def ecuacion(clave: str):
    """La ley como expresión de sympy, con TODOS sus símbolos forzados.

    Sin forzarlos, sympy se come varias letras que aquí son magnitudes: `I` es
    su unidad imaginaria, `E` el número e, `N` su evaluador numérico, `Q` el
    objeto de suposiciones y `beta` la función beta. Con `I*alpha` eso dejaba de
    ser el momento angular para pasar a ser un número complejo.
    """
    import sympy as sp
    _tema, ec_txt, simbolos = FORMULAS[clave]
    locales = {n: sp.Symbol(n) for n in simbolos}
    locales.update({n: sp.Symbol(n) for n in CONSTANTES})
    return sp.sympify(ec_txt, locals=locales)


def resolver_formula(clave: str, conocidos: dict, incognita: str = "", log=print) -> dict:
    """Despeja la incógnita de una ley con los datos que haya, y lo explica."""
    import sympy as sp
    if clave not in FORMULAS:
        posibles = buscar_formula(clave)
        if not posibles:
            return {"ok": False, "pasos": [f"No tengo «{clave}» en el formulario."]}
        clave = posibles[0]
    tema, ec_txt, simbolos = FORMULAS[clave]
    ec = ecuacion(clave)
    conocidos = {k: v for k, v in (conocidos or {}).items() if v is not None}
    # Las constantes universales se rellenan solas si el enunciado no las da.
    for s in ec.free_symbols:
        n = s.name
        if n not in conocidos and n in CONSTANTES:
            conocidos[n] = CONSTANTES[n][0]
    libres = [s for s in ec.free_symbols if s.name not in conocidos]
    if incognita:
        inc = sp.Symbol(incognita)
    elif len(libres) == 1:
        inc = libres[0]
    else:
        return {"ok": False, "clave": clave,
                "pasos": [f"Ley «{clave}»: {M.bonito(ec)} = 0",
                          "Faltan datos. Sin despejar quedan: "
                          + ", ".join(sorted(s.name for s in libres))]}
    pasos = [f"Ley aplicada ({tema}): {clave}",
             f"   {M.bonito(ec)} = 0"]
    for k, v in sorted(conocidos.items()):
        d = simbolos.get(k, ("", ""))
        pasos.append(f"   {k} = {v:g} {d[1]}" if isinstance(v, (int, float))
                     else f"   {k} = {v}")
    try:
        despejes = sp.solve(ec, inc)
    except Exception as e:
        return {"ok": False, "clave": clave, "pasos": pasos + [f"No pude despejar: {e}"]}
    if not despejes:
        return {"ok": False, "clave": clave, "pasos": pasos + ["No se puede despejar."]}
    pasos.append(f"Despejando {inc}:  {inc} = " +
                 "  ó  ".join(M.bonito(d) for d in despejes))
    valores = []
    for d in despejes:
        try:
            # Claves como Symbol y no como texto: «E» en texto volvería a ser
            # el número e al sympificarlo.
            v = complex(sp.N(d.subs({sp.Symbol(k): val
                                     for k, val in conocidos.items()})))
            if abs(v.imag) < 1e-9:
                valores.append(float(v.real))
        except Exception:
            pass
    ud = simbolos.get(inc.name, ("", ""))[1]
    if valores:
        pasos.append(f"Sustituyendo: {inc} = " +
                     "  ó  ".join(f"{v:.6g} {ud}" for v in valores))
    return {"ok": bool(valores), "clave": clave, "tema": tema, "incognita": inc.name,
            "unidad": ud, "valores": valores, "simbolos": simbolos,
            "resultado": valores[0] if valores else None, "pasos": pasos}


# ── lectura de datos del enunciado hablado ────────────────────────────────
# «una masa de 5 kg», «a 20 m/s», «con un ángulo de 30 grados», «en 3 segundos»
_UNIDADES = [
    (r"(?:km/h|kil[oó]metros?\s+por\s+hora)", "km/h", 1 / 3.6),
    (r"(?:m/s2|m/s²|metros?\s+por\s+segundo\s+al\s+cuadrado)", "m/s²", 1.0),
    (r"(?:m/s|metros?\s+por\s+segundo)", "m/s", 1.0),
    (r"(?:kg|kilogramos?|kilos?)", "kg", 1.0),
    (r"(?:gramos?|g\b)", "g", 1e-3),
    (r"(?:km|kil[oó]metros?)", "km", 1000.0),
    (r"(?:cm|cent[ií]metros?)", "cm", 0.01),
    (r"(?:mm|mil[ií]metros?)", "mm", 0.001),
    (r"(?:m\b|metros?)", "m", 1.0),
    (r"(?:grados?|°)", "grados", math.pi / 180),
    (r"(?:radianes?|rad)", "rad", 1.0),
    (r"(?:segundos?|s\b)", "s", 1.0),
    (r"(?:minutos?|min)", "min", 60.0),
    (r"(?:horas?|h\b)", "h", 3600.0),
    (r"(?:newtons?|N\b)", "N", 1.0),
    (r"(?:julios?|joules?|J\b)", "J", 1.0),
    (r"(?:vatios?|watts?|W\b)", "W", 1.0),
    (r"(?:voltios?|volts?|V\b)", "V", 1.0),
    (r"(?:amperios?|amps?|A\b)", "A", 1.0),
    (r"(?:ohmios?|ohms?|Ω)", "ohm", 1.0),
    (r"(?:culombios?|coulombs?|C\b)", "C", 1.0),
    (r"(?:kelvin|K\b)", "K", 1.0),
    (r"(?:grados\s+cent[ií]grados|°C|celsius)", "°C", 1.0),
    (r"(?:pascales?|Pa)", "Pa", 1.0),
    (r"(?:atm[oó]sferas?|atm)", "atm", 101325.0),
    (r"(?:hercios?|hertz|Hz)", "Hz", 1.0),
    (r"(?:moles?|mol)", "mol", 1.0),
    (r"(?:litros?|L\b|l\b)", "L", 1e-3),
]


def datos_del_enunciado(texto: str) -> list:
    """[(valor_SI, unidad, valor_original, contexto), ...] leído de la frase."""
    t = M._palabras_a_numeros((texto or "").lower())
    out = []
    for m in re.finditer(r"(-?\d+(?:[.,]\d+)?(?:\s*[eE]\s*-?\d+)?)\s*"
                         r"([a-zA-Zµ°Ω/²³]{0,12})", t):
        try:
            val = float(m.group(1).replace(",", ".").replace(" ", ""))
        except ValueError:
            continue
        cola = t[m.start(2):m.start(2) + 26]
        unidad, factor = "", 1.0
        for pat, nom, fac in _UNIDADES:
            if re.match(pat, cola, re.I):
                unidad, factor = nom, fac
                break
        ctx = t[max(0, m.start() - 45):m.start()].strip()
        out.append((val * factor, unidad, val, ctx))
    return out


# ── análisis completos, con gráfica ────────────────────────────────────────
def tiro_parabolico(v0: float, angulo_grados: float, y0: float = 0.0,
                    g: float = 9.80665, graficar: bool = True, tridimensional: bool = False,
                    azimut_grados: float = 0.0, carpeta: str = "", log=print) -> dict:
    """Proyectil completo: alcance, altura, tiempos, energía y trayectoria.

    En 3D se dibuja la trayectoria como tubo (se puede imprimir) girada el
    azimut que se pida, para los enunciados de «lanza hacia el noreste».
    """
    import numpy as np
    th = math.radians(float(angulo_grados))
    vx, vy = v0 * math.cos(th), v0 * math.sin(th)
    # Tiempo de vuelo: raíz positiva de y0 + vy t - g t²/2 = 0
    disc = vy * vy + 2 * g * y0
    t_vuelo = (vy + math.sqrt(max(disc, 0.0))) / g if g else 0.0
    t_sub = vy / g if g else 0.0
    h_max = y0 + vy * vy / (2 * g) if g else y0
    alcance = vx * t_vuelo
    v_impacto = math.hypot(vx, vy - g * t_vuelo)
    pasos = [
        f"Descomposición: v0x = v0·cos θ = {v0:g}·cos({angulo_grados:g}°) = {vx:.6g} m/s",
        f"                v0y = v0·sen θ = {v0:g}·sen({angulo_grados:g}°) = {vy:.6g} m/s",
        f"Subida: t_sub = v0y/g = {vy:.6g}/{g:g} = {t_sub:.6g} s",
        f"Altura máxima: H = y0 + v0y²/(2g) = {h_max:.6g} m",
        f"Tiempo de vuelo (raíz de y0 + v0y·t − g·t²/2 = 0): t = {t_vuelo:.6g} s",
        f"Alcance: R = v0x·t_vuelo = {vx:.6g}·{t_vuelo:.6g} = {alcance:.6g} m",
        f"Velocidad al llegar al suelo: {v_impacto:.6g} m/s",
        f"Ecuación de la trayectoria: y = {y0:g} + {math.tan(th):.6g}·x "
        f"− {g / (2 * vx * vx) if vx else 0:.6g}·x²",
    ]
    res = {"vx": vx, "vy": vy, "t_vuelo": t_vuelo, "t_subida": t_sub,
           "altura_max": h_max, "alcance": alcance, "v_impacto": v_impacto,
           "pasos": pasos}
    if not graficar:
        return res
    out = carpeta or M.carpeta_salida("tiro-parabolico")
    ts = np.linspace(0, t_vuelo, 700)
    xs, ys = vx * ts, y0 + vy * ts - g * ts**2 / 2
    if tridimensional:
        az = math.radians(float(azimut_grados))
        r = M.curva_3d(f"{vx * math.cos(az)}*t", f"{vx * math.sin(az)}*t",
                       f"{y0} + {vy}*t - {g / 2}*t**2", rango=(0, t_vuelo),
                       titulo="Trayectoria del proyectil", carpeta=out, puntos=900,
                       grosor=0.012)
        res.update(r)
        return res

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13.5, 6.2), dpi=190, facecolor=M._FONDO)
    ax.plot(xs, ys, color=M._ACENTO[0], linewidth=2.4)
    ax.fill_between(xs, 0, ys, color=M._ACENTO[0], alpha=0.12)
    ax.plot([vx * t_sub], [h_max], "^", color=M._ACENTO[3], markersize=10)
    ax.annotate(f"H = {h_max:.4g} m", (vx * t_sub, h_max), color=M._ACENTO[3],
                textcoords="offset points", xytext=(8, 6), fontsize=9)
    ax.plot([alcance], [0], "o", color=M._ACENTO[2], markersize=9)
    ax.annotate(f"R = {alcance:.4g} m", (alcance, 0), color=M._ACENTO[2],
                textcoords="offset points", xytext=(-70, 12), fontsize=9)
    # Vectores velocidad a lo largo del vuelo.
    for k in np.linspace(0, len(ts) - 1, 9).astype(int):
        ax.arrow(xs[k], ys[k], vx * t_vuelo * 0.055, (vy - g * ts[k]) * t_vuelo * 0.055,
                 head_width=max(alcance, 1) * 0.012, color=M._ACENTO[1], alpha=0.85,
                 length_includes_head=True)
    M._estilo(ax, f"Tiro parabólico · v₀ = {v0:g} m/s · θ = {angulo_grados:g}°",
              "x (m)", "y (m)")
    ax.set_ylim(bottom=0)
    vxs = np.full_like(ts, vx)
    vys = vy - g * ts
    ax2.plot(ts, vxs, color=M._ACENTO[0], label="vₓ (constante)")
    ax2.plot(ts, vys, color=M._ACENTO[1], label="v_y")
    ax2.plot(ts, np.hypot(vxs, vys), color=M._ACENTO[2], label="|v|")
    ax2.axhline(0, color=M._TINTA, alpha=0.4)
    ax2.axvline(t_sub, color=M._ACENTO[3], linestyle=":", label=f"cima t={t_sub:.3g} s")
    M._estilo(ax2, "Componentes de la velocidad", "t (s)", "v (m/s)")
    ax2.legend(facecolor=M._PANEL, edgecolor=M._REJILLA, labelcolor=M._TINTA, fontsize=9)
    fig.tight_layout()
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    datos = {"tipo": "2d", "x": xs.tolist(),
             "series": [{"nombre": "y(x) trayectoria", "y": ys.tolist()}]}
    res.update({"png": png, "carpeta": out,
                "html": M.visor_web(datos, os.path.join(out, "visor.html"),
                                    "Tiro parabólico")})
    return res


def movimiento_rectilineo(x0: float = 0.0, v0: float = 0.0, a: float = 0.0,
                          t_max: float = 10.0, carpeta: str = "", log=print) -> dict:
    """x-t, v-t y a-t en una sola lámina, con el área que es el desplazamiento."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    ts = np.linspace(0, float(t_max), 800)
    xs = x0 + v0 * ts + a * ts**2 / 2
    vs = v0 + a * ts
    fig, ejes = plt.subplots(3, 1, figsize=(10, 10.5), dpi=185, facecolor=M._FONDO,
                             sharex=True)
    ejes[0].plot(ts, xs, color=M._ACENTO[0], linewidth=2.2)
    M._estilo(ejes[0], "Posición", "", "x (m)")
    ejes[1].plot(ts, vs, color=M._ACENTO[1], linewidth=2.2)
    ejes[1].fill_between(ts, 0, vs, color=M._ACENTO[1], alpha=0.15)
    ejes[1].annotate(f"área = desplazamiento = {xs[-1] - x0:.5g} m",
                     (ts[len(ts) // 2], vs[len(ts) // 2] / 2), color=M._TINTA, fontsize=9)
    M._estilo(ejes[1], "Velocidad", "", "v (m/s)")
    ejes[2].plot(ts, np.full_like(ts, a), color=M._ACENTO[2], linewidth=2.2)
    M._estilo(ejes[2], "Aceleración", "t (s)", "a (m/s²)")
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("movimiento-rectilineo")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    pasos = [f"x(t) = {x0:g} + {v0:g}·t + ½·{a:g}·t²",
             f"v(t) = {v0:g} + {a:g}·t",
             f"a(t) = {a:g} m/s² (constante)",
             f"En t = {t_max:g} s:  x = {xs[-1]:.6g} m,  v = {vs[-1]:.6g} m/s",
             f"Desplazamiento total = {xs[-1] - x0:.6g} m"]
    datos = {"tipo": "2d", "x": ts.tolist(),
             "series": [{"nombre": "x(t) (m)", "y": xs.tolist()},
                        {"nombre": "v(t) (m/s)", "y": vs.tolist()},
                        {"nombre": "a(t) (m/s²)", "y": [a] * len(ts)}]}
    return {"png": png, "carpeta": out, "pasos": pasos,
            "html": M.visor_web(datos, os.path.join(out, "visor.html"),
                                "Movimiento rectilíneo"),
            "x_final": float(xs[-1]), "v_final": float(vs[-1])}


def oscilador_armonico(A: float = 1.0, m: float = 1.0, k: float = 1.0,
                       fase: float = 0.0, amortiguamiento: float = 0.0,
                       carpeta: str = "", log=print) -> dict:
    """MAS (o amortiguado): elongación, velocidad, energías y espacio de fases."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    w0 = math.sqrt(k / m)
    b = float(amortiguamiento)
    gamma = b / (2 * m)
    wd = math.sqrt(max(w0**2 - gamma**2, 0.0))
    T = 2 * math.pi / (wd or w0)
    ts = np.linspace(0, 4 * T, 2400)
    env = np.exp(-gamma * ts)
    xs = A * env * np.cos(wd * ts + fase)
    vs = np.gradient(xs, ts)
    Ec = 0.5 * m * vs**2
    Ep = 0.5 * k * xs**2
    fig = plt.figure(figsize=(13.5, 8.6), dpi=185, facecolor=M._FONDO)
    ax1 = fig.add_subplot(221)
    ax1.plot(ts, xs, color=M._ACENTO[0], linewidth=1.8)
    if gamma:
        ax1.plot(ts, A * env, color=M._ACENTO[3], linestyle="--", alpha=0.7,
                 label="envolvente")
        ax1.plot(ts, -A * env, color=M._ACENTO[3], linestyle="--", alpha=0.7)
        ax1.legend(facecolor=M._PANEL, edgecolor=M._REJILLA, labelcolor=M._TINTA, fontsize=8)
    M._estilo(ax1, "Elongación x(t)", "t (s)", "x (m)")
    ax2 = fig.add_subplot(222)
    ax2.plot(ts, vs, color=M._ACENTO[1], linewidth=1.8)
    M._estilo(ax2, "Velocidad v(t)", "t (s)", "v (m/s)")
    ax3 = fig.add_subplot(223)
    ax3.plot(ts, Ec, color=M._ACENTO[2], label="cinética")
    ax3.plot(ts, Ep, color=M._ACENTO[4], label="potencial")
    ax3.plot(ts, Ec + Ep, color=M._ACENTO[5], linewidth=2, label="total")
    ax3.legend(facecolor=M._PANEL, edgecolor=M._REJILLA, labelcolor=M._TINTA, fontsize=9)
    M._estilo(ax3, "Energías", "t (s)", "E (J)")
    ax4 = fig.add_subplot(224)
    pts = ax4.scatter(xs, m * vs, c=ts, cmap="turbo", s=3)
    fig.colorbar(pts, ax=ax4, label="t (s)").ax.tick_params(colors=M._TINTA, labelsize=7)
    M._estilo(ax4, "Espacio de fases (x, p)", "x (m)", "p (kg·m/s)")
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("oscilador")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    pasos = [f"ω₀ = √(k/m) = √({k:g}/{m:g}) = {w0:.6g} rad/s",
             f"Periodo T = 2π/ω = {T:.6g} s     frecuencia f = {1/T:.6g} Hz"]
    if gamma:
        pasos += [f"γ = b/2m = {gamma:.6g} s⁻¹   →   ω_d = √(ω₀²−γ²) = {wd:.6g} rad/s",
                  "Régimen: " + ("subamortiguado" if gamma < w0 else
                                 "crítico" if abs(gamma - w0) < 1e-9 else "sobreamortiguado")]
    pasos += [f"x(t) = {A:g}·e^(−{gamma:.4g}t)·cos({wd:.6g}·t + {fase:g})",
              f"Energía mecánica inicial E = ½kA² = {0.5 * k * A * A:.6g} J"]
    datos = {"tipo": "2d", "x": ts.tolist(),
             "series": [{"nombre": "x(t)", "y": xs.tolist()},
                        {"nombre": "v(t)", "y": vs.tolist()},
                        {"nombre": "E total", "y": (Ec + Ep).tolist()}]}
    return {"png": png, "carpeta": out, "pasos": pasos, "omega": w0, "periodo": T,
            "html": M.visor_web(datos, os.path.join(out, "visor.html"), "Oscilador")}


def onda_viajera(A: float = 1.0, lamda: float = 2.0, f: float = 1.0,
                 sentido: int = 1, carpeta: str = "", log=print) -> dict:
    """y(x,t) = A·sen(kx ∓ ωt) como SUPERFICIE 3D: el tiempo es el tercer eje."""
    k = 2 * math.pi / lamda
    w = 2 * math.pi * f
    v = w / k
    signo = "-" if sentido >= 0 else "+"
    out = carpeta or M.carpeta_salida("onda-viajera")
    r = M.superficie_3d(f"{A}*sin({k}*x {signo} {w}*y)",
                        rango_x=(0, 3 * lamda), rango_y=(0, 3 / f), n=150,
                        titulo=f"Onda y(x,t) · λ={lamda:g} m · f={f:g} Hz",
                        carpeta=out, log=log)
    r["pasos"] = [
        f"Número de onda k = 2π/λ = {k:.6g} rad/m",
        f"Pulsación ω = 2πf = {w:.6g} rad/s",
        f"Velocidad de propagación v = ω/k = λ·f = {v:.6g} m/s",
        f"Periodo T = 1/f = {1/f:.6g} s",
        f"y(x,t) = {A:g}·sen({k:.4g}x {signo} {w:.4g}t)",
        "En la superficie, el eje horizontal es x y el de profundidad es t: "
        "cortes a t constante dan la foto de la onda; cortes a x constante, "
        "la oscilación de una partícula.",
    ]
    r["velocidad"] = v
    return r


def campo_electrico(cargas, limites=(-5, 5), carpeta: str = "", log=print) -> dict:
    """Cargas puntuales: líneas de campo, equipotenciales y potencial en 3D.

    `cargas` = [(q_en_nC, x, y), ...]
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    ke = CONSTANTES["k_e"][0]
    cargas = [(float(q), float(px), float(py)) for q, px, py in cargas]
    a, b = float(limites[0]), float(limites[1])
    X, Y = np.meshgrid(np.linspace(a, b, 320), np.linspace(a, b, 320))
    Ex = np.zeros_like(X)
    Ey = np.zeros_like(X)
    V = np.zeros_like(X)
    for q, px, py in cargas:
        dx, dy = X - px, Y - py
        r2 = dx * dx + dy * dy + 1e-9
        r = np.sqrt(r2)
        Q = q * 1e-9
        Ex += ke * Q * dx / (r2 * r)
        Ey += ke * Q * dy / (r2 * r)
        V += ke * Q / r
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 6.8), dpi=185, facecolor=M._FONDO)
    Mod = np.hypot(Ex, Ey)
    ax.streamplot(X, Y, Ex, Ey, color=np.log10(Mod + 1e-12), cmap="turbo",
                  density=1.7, linewidth=0.9, arrowsize=0.9)
    for q, px, py in cargas:
        ax.plot([px], [py], "o", markersize=13,
                color="#ff6b81" if q > 0 else "#2ec6ff",
                markeredgecolor="white", markeredgewidth=1)
        ax.annotate(f"{q:+g} nC", (px, py), color="white", fontsize=9, ha="center",
                    va="center")
    M._estilo(ax, "Líneas de campo eléctrico", "x (m)", "y (m)")
    lim = np.nanpercentile(np.abs(V), 96)
    cs = ax2.contourf(X, Y, np.clip(V, -lim, lim), levels=46, cmap="coolwarm")
    ax2.contour(X, Y, np.clip(V, -lim, lim), levels=22, colors="#04060a", linewidths=0.5)
    fig.colorbar(cs, ax=ax2, label="V (V)").ax.tick_params(colors=M._TINTA, labelsize=7)
    M._estilo(ax2, "Potencial y equipotenciales", "x (m)", "y (m)")
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("campo-electrico")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    # El potencial también en 3D: los picos son las cargas.
    expr = " + ".join(f"{ke * q * 1e-9:.6g}/sqrt((x-{px})**2 + (y-{py})**2 + 0.04)"
                      for q, px, py in cargas)
    r3 = M.superficie_3d(expr, rango_x=(a, b), rango_y=(a, b), n=150,
                         titulo="Potencial eléctrico V(x, y)", carpeta=out, log=log)
    pasos = [f"Superposición de {len(cargas)} cargas puntuales.",
             "Campo: E = k·q/r² (vector, suma vectorial de todas).",
             "Potencial: V = k·q/r (escalar, suma algebraica).",
             f"k = {ke:.6g} N·m²/C²"]
    for q, px, py in cargas:
        pasos.append(f"   q = {q:+g} nC en ({px:g}, {py:g}) m")
    return {"png": png, "png_3d": r3.get("png"), "html": r3.get("html"),
            "obj": r3.get("obj"), "stl": r3.get("stl"), "carpeta": out, "pasos": pasos}


def circuito_rc(R: float, C: float, V: float = 5.0, descarga: bool = False,
                carpeta: str = "", log=print) -> dict:
    """Carga o descarga de un RC: tensión, corriente y constante de tiempo."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    tau = R * C
    ts = np.linspace(0, 6 * tau, 1200)
    if descarga:
        vc = V * np.exp(-ts / tau)
        i = -V / R * np.exp(-ts / tau)
    else:
        vc = V * (1 - np.exp(-ts / tau))
        i = V / R * np.exp(-ts / tau)
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5.6), dpi=190, facecolor=M._FONDO)
    ax.plot(ts, vc, color=M._ACENTO[0], linewidth=2.2)
    for n in (1, 2, 3, 5):
        ax.axvline(n * tau, color=M._REJILLA, linestyle=":", alpha=0.9)
        ax.annotate(f"{n}τ", (n * tau, V * 0.05), color=M._TINTA, fontsize=8)
    ax.axhline(V, color=M._ACENTO[3], linestyle="--", alpha=0.6)
    M._estilo(ax, f"{'Descarga' if descarga else 'Carga'} del condensador",
              "t (s)", "V_C (V)")
    ax2.plot(ts, i * 1000, color=M._ACENTO[1], linewidth=2.2)
    M._estilo(ax2, "Corriente", "t (s)", "i (mA)")
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("circuito-rc")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    pasos = [f"Constante de tiempo τ = R·C = {R:g}·{C:g} = {tau:.6g} s",
             ("V_C(t) = V₀·e^(−t/τ)" if descarga else "V_C(t) = V₀·(1 − e^(−t/τ))"),
             f"A t = τ el condensador está al {36.8 if descarga else 63.2:.1f} % ",
             f"Se considera terminado a 5τ = {5 * tau:.6g} s",
             f"Energía almacenada a plena carga U = ½CV² = {0.5 * C * V * V:.6g} J"]
    datos = {"tipo": "2d", "x": ts.tolist(),
             "series": [{"nombre": "V_C (V)", "y": vc.tolist()},
                        {"nombre": "i (mA)", "y": (i * 1000).tolist()}]}
    return {"png": png, "carpeta": out, "pasos": pasos, "tau": tau,
            "html": M.visor_web(datos, os.path.join(out, "visor.html"), "Circuito RC")}


def diagrama_pv(puntos, n: float = 1.0, carpeta: str = "", log=print) -> dict:
    """Ciclo termodinámico a partir de los vértices [(V m³, P Pa), ...].

    Calcula el trabajo del ciclo por el área encerrada y las isotermas que
    pasan por cada vértice.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    P = [(float(v), float(p)) for v, p in puntos]
    if P[0] != P[-1]:
        P.append(P[0])
    V = np.array([p[0] for p in P])
    Pr = np.array([p[1] for p in P])
    # Área por la fórmula del polígono: es el trabajo neto del ciclo.
    W = 0.0
    for i in range(len(P) - 1):
        W += (V[i + 1] - V[i]) * (Pr[i + 1] + Pr[i]) / 2
    fig, ax = plt.subplots(figsize=(9.5, 7), dpi=190, facecolor=M._FONDO)
    ax.plot(V, Pr, color=M._ACENTO[0], linewidth=2.4, marker="o", markersize=7,
            markerfacecolor=M._ACENTO[3])
    ax.fill(V, Pr, color=M._ACENTO[0], alpha=0.14)
    R = CONSTANTES["R"][0]
    vv = np.linspace(V.min() * 0.85, V.max() * 1.15, 300)
    for (v, p) in P[:-1]:
        T = p * v / (n * R)
        ax.plot(vv, n * R * T / vv, color=M._REJILLA, linestyle="--", linewidth=0.9)
        ax.annotate(f"T={T:.0f} K", (v, p), color=M._TINTA, fontsize=8,
                    textcoords="offset points", xytext=(8, 8))
    ax.set_ylim(bottom=0)
    M._estilo(ax, "Diagrama p–V", "V (m³)", "p (Pa)")
    ax.annotate(f"W del ciclo = {W:.6g} J\n({'horario: motor' if W > 0 else 'antihorario: frigorífico'})",
                (V.mean(), Pr.mean()), color="white", fontsize=11, ha="center")
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("diagrama-pv")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    pasos = [f"Vértices del ciclo: {', '.join(f'({v:g} m³, {p:g} Pa)' for v, p in P[:-1])}",
             "El trabajo del ciclo es el ÁREA encerrada en el diagrama p–V.",
             f"W = ∮ p dV = {W:.6g} J",
             "Signo positivo: recorrido horario, el gas produce trabajo neto (motor).",
             f"Temperatura en cada vértice con pV = nRT y n = {n:g} mol."]
    return {"png": png, "carpeta": out, "pasos": pasos, "trabajo": W, "html": ""}


def lente_delgada(f_focal: float, s_objeto: float, altura: float = 1.0,
                  carpeta: str = "", log=print) -> dict:
    """Trazado de rayos de una lente delgada, con la imagen y el aumento."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    f, so = float(f_focal), float(s_objeto)
    if abs(so - f) < 1e-12:
        return {"pasos": ["El objeto está en el foco: la imagen se va al infinito."],
                "png": "", "carpeta": "", "html": ""}
    si = 1 / (1 / f - 1 / so)
    m = -si / so
    hi = m * altura
    fig, ax = plt.subplots(figsize=(12, 6.2), dpi=190, facecolor=M._FONDO)
    ax.axhline(0, color=M._TINTA, linewidth=1)
    ax.axvline(0, color=M._ACENTO[0], linewidth=3, alpha=0.6)
    for xf, nombre in ((f, "F′"), (-f, "F")):
        ax.plot([xf], [0], "x", color=M._ACENTO[3], markersize=9)
        ax.annotate(nombre, (xf, 0), color=M._ACENTO[3], fontsize=9,
                    textcoords="offset points", xytext=(2, -14))
    ax.arrow(-so, 0, 0, altura, color=M._ACENTO[2], width=abs(so) * 0.008,
             length_includes_head=True, head_length=abs(altura) * 0.12)
    ax.arrow(si, 0, 0, hi, color=M._ACENTO[1], width=abs(so) * 0.008,
             length_includes_head=True, head_length=abs(hi) * 0.12 or 0.05)
    # Los tres rayos de libro.
    ax.plot([-so, 0, max(si, so) * 1.3], [altura, altura, altura + (hi - altura) *
            (max(si, so) * 1.3) / (si if si else 1)], color=M._ACENTO[0],
            linewidth=1.1, alpha=0.9)
    ax.plot([-so, 0], [altura, altura], color=M._ACENTO[0], linewidth=1.1)
    ax.plot([-so, si], [altura, hi], color=M._ACENTO[4], linewidth=1.1, alpha=0.9)
    ax.plot([0, si], [altura, hi], color=M._ACENTO[5], linewidth=1.1, alpha=0.9)
    M._estilo(ax, "Lente delgada · trazado de rayos", "posición (m)", "altura (m)")
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("lente")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    pasos = [f"Ecuación de la lente: 1/f = 1/s_o + 1/s_i   con f = {f:g} m, s_o = {so:g} m",
             f"   1/s_i = 1/f − 1/s_o  →  s_i = {si:.6g} m "
             + ("(imagen REAL, al otro lado)" if si > 0 else "(imagen VIRTUAL, mismo lado)"),
             f"Aumento m = −s_i/s_o = {m:.6g} "
             + ("(invertida)" if m < 0 else "(derecha)")
             + (" y más grande" if abs(m) > 1 else " y más pequeña"),
             f"Altura de la imagen h_i = m·h_o = {hi:.6g} m"]
    return {"png": png, "carpeta": out, "pasos": pasos, "s_imagen": si, "aumento": m,
            "html": ""}


def energia_relativista(m_kg: float = 0.0, v_ms: float = 0.0, carpeta: str = "",
                        log=print) -> dict:
    """Factor de Lorentz, energías y la curva γ(v) que enseña el muro de c."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    c = CONSTANTES["c"][0]
    beta = v_ms / c
    gamma = 1 / math.sqrt(1 - beta**2) if abs(beta) < 1 else float("inf")
    E0 = m_kg * c**2
    E = gamma * E0
    fig, ax = plt.subplots(figsize=(10, 6), dpi=190, facecolor=M._FONDO)
    bs = np.linspace(0, 0.9995, 1500)
    ax.plot(bs, 1 / np.sqrt(1 - bs**2), color=M._ACENTO[0], linewidth=2.2,
            label="γ(β)")
    if abs(beta) < 1:
        ax.plot([beta], [gamma], "o", color=M._ACENTO[3], markersize=9)
        ax.annotate(f"β={beta:.4g}, γ={gamma:.4g}", (beta, gamma), color=M._ACENTO[3],
                    textcoords="offset points", xytext=(8, 8), fontsize=9)
    ax.set_ylim(0, 12)
    M._estilo(ax, "Factor de Lorentz", "β = v/c", "γ")
    ax.legend(facecolor=M._PANEL, edgecolor=M._REJILLA, labelcolor=M._TINTA)
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("relatividad")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    pasos = [f"β = v/c = {v_ms:g}/{c:g} = {beta:.6g}",
             f"γ = 1/√(1−β²) = {gamma:.6g}",
             f"Energía en reposo E₀ = mc² = {E0:.6g} J = {E0 / 1.602176634e-19 / 1e6:.6g} MeV",
             f"Energía total E = γmc² = {E:.6g} J",
             f"Energía cinética relativista K = (γ−1)mc² = {(gamma - 1) * E0:.6g} J",
             f"El tiempo se dilata ×{gamma:.6g} y la longitud se contrae ÷{gamma:.6g}."]
    return {"png": png, "carpeta": out, "pasos": pasos, "gamma": gamma, "html": ""}
