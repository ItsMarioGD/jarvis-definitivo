#!/usr/bin/env python3
"""
quimica.py - El químico de JARVIS y ULTRON
==========================================
Tabla periódica completa dentro del módulo (sin internet), masas molares,
balanceo de ecuaciones por álgebra lineal, estequiometría con reactivo
limitante, gases, disoluciones, pH y curvas de valoración, cinética,
equilibrio, termoquímica por la ley de Hess y electroquímica.

Y lo que pidió el señor: química que se VE. Además de las láminas 2D, arma la
GEOMETRÍA MOLECULAR en 3D por el modelo RPECV (VSEPR), la exporta a .obj/.stl
y abre el visor girable. La tabla periódica también se dibuja entera.

Todo se apoya en `matematica.py` para el dibujo, el visor y las mallas.
"""
import math
import os
import re

import matematica as M

# ── tabla periódica ────────────────────────────────────────────────────────
# Z|símbolo|nombre|masa|grupo|periodo|electronegatividad|categoría
# Masa entre corchetes = número másico del isótopo más estable.
_TABLA_CRUDA = """
1|H|hidrógeno|1.008|1|1|2.20|no metal
2|He|helio|4.0026|18|1|0|gas noble
3|Li|litio|6.94|1|2|0.98|metal alcalino
4|Be|berilio|9.0122|2|2|1.57|alcalinotérreo
5|B|boro|10.81|13|2|2.04|metaloide
6|C|carbono|12.011|14|2|2.55|no metal
7|N|nitrógeno|14.007|15|2|3.04|no metal
8|O|oxígeno|15.999|16|2|3.44|no metal
9|F|flúor|18.998|17|2|3.98|halógeno
10|Ne|neón|20.180|18|2|0|gas noble
11|Na|sodio|22.990|1|3|0.93|metal alcalino
12|Mg|magnesio|24.305|2|3|1.31|alcalinotérreo
13|Al|aluminio|26.982|13|3|1.61|metal
14|Si|silicio|28.085|14|3|1.90|metaloide
15|P|fósforo|30.974|15|3|2.19|no metal
16|S|azufre|32.06|16|3|2.58|no metal
17|Cl|cloro|35.45|17|3|3.16|halógeno
18|Ar|argón|39.95|18|3|0|gas noble
19|K|potasio|39.098|1|4|0.82|metal alcalino
20|Ca|calcio|40.078|2|4|1.00|alcalinotérreo
21|Sc|escandio|44.956|3|4|1.36|metal de transición
22|Ti|titanio|47.867|4|4|1.54|metal de transición
23|V|vanadio|50.942|5|4|1.63|metal de transición
24|Cr|cromo|51.996|6|4|1.66|metal de transición
25|Mn|manganeso|54.938|7|4|1.55|metal de transición
26|Fe|hierro|55.845|8|4|1.83|metal de transición
27|Co|cobalto|58.933|9|4|1.88|metal de transición
28|Ni|níquel|58.693|10|4|1.91|metal de transición
29|Cu|cobre|63.546|11|4|1.90|metal de transición
30|Zn|cinc|65.38|12|4|1.65|metal de transición
31|Ga|galio|69.723|13|4|1.81|metal
32|Ge|germanio|72.630|14|4|2.01|metaloide
33|As|arsénico|74.922|15|4|2.18|metaloide
34|Se|selenio|78.971|16|4|2.55|no metal
35|Br|bromo|79.904|17|4|2.96|halógeno
36|Kr|kriptón|83.798|18|4|3.00|gas noble
37|Rb|rubidio|85.468|1|5|0.82|metal alcalino
38|Sr|estroncio|87.62|2|5|0.95|alcalinotérreo
39|Y|itrio|88.906|3|5|1.22|metal de transición
40|Zr|circonio|91.224|4|5|1.33|metal de transición
41|Nb|niobio|92.906|5|5|1.60|metal de transición
42|Mo|molibdeno|95.95|6|5|2.16|metal de transición
43|Tc|tecnecio|[98]|7|5|1.90|metal de transición
44|Ru|rutenio|101.07|8|5|2.20|metal de transición
45|Rh|rodio|102.91|9|5|2.28|metal de transición
46|Pd|paladio|106.42|10|5|2.20|metal de transición
47|Ag|plata|107.87|11|5|1.93|metal de transición
48|Cd|cadmio|112.41|12|5|1.69|metal de transición
49|In|indio|114.82|13|5|1.78|metal
50|Sn|estaño|118.71|14|5|1.96|metal
51|Sb|antimonio|121.76|15|5|2.05|metaloide
52|Te|telurio|127.60|16|5|2.10|metaloide
53|I|yodo|126.90|17|5|2.66|halógeno
54|Xe|xenón|131.29|18|5|2.60|gas noble
55|Cs|cesio|132.91|1|6|0.79|metal alcalino
56|Ba|bario|137.33|2|6|0.89|alcalinotérreo
57|La|lantano|138.91|3|6|1.10|lantánido
58|Ce|cerio|140.12|0|6|1.12|lantánido
59|Pr|praseodimio|140.91|0|6|1.13|lantánido
60|Nd|neodimio|144.24|0|6|1.14|lantánido
61|Pm|prometio|[145]|0|6|1.13|lantánido
62|Sm|samario|150.36|0|6|1.17|lantánido
63|Eu|europio|151.96|0|6|1.20|lantánido
64|Gd|gadolinio|157.25|0|6|1.20|lantánido
65|Tb|terbio|158.93|0|6|1.20|lantánido
66|Dy|disprosio|162.50|0|6|1.22|lantánido
67|Ho|holmio|164.93|0|6|1.23|lantánido
68|Er|erbio|167.26|0|6|1.24|lantánido
69|Tm|tulio|168.93|0|6|1.25|lantánido
70|Yb|iterbio|173.05|0|6|1.10|lantánido
71|Lu|lutecio|174.97|0|6|1.27|lantánido
72|Hf|hafnio|178.49|4|6|1.30|metal de transición
73|Ta|tantalio|180.95|5|6|1.50|metal de transición
74|W|wolframio|183.84|6|6|2.36|metal de transición
75|Re|renio|186.21|7|6|1.90|metal de transición
76|Os|osmio|190.23|8|6|2.20|metal de transición
77|Ir|iridio|192.22|9|6|2.20|metal de transición
78|Pt|platino|195.08|10|6|2.28|metal de transición
79|Au|oro|196.97|11|6|2.54|metal de transición
80|Hg|mercurio|200.59|12|6|2.00|metal de transición
81|Tl|talio|204.38|13|6|1.62|metal
82|Pb|plomo|207.2|14|6|2.33|metal
83|Bi|bismuto|208.98|15|6|2.02|metal
84|Po|polonio|[209]|16|6|2.00|metaloide
85|At|ástato|[210]|17|6|2.20|halógeno
86|Rn|radón|[222]|18|6|0|gas noble
87|Fr|francio|[223]|1|7|0.70|metal alcalino
88|Ra|radio|[226]|2|7|0.90|alcalinotérreo
89|Ac|actinio|[227]|3|7|1.10|actínido
90|Th|torio|232.04|0|7|1.30|actínido
91|Pa|protactinio|231.04|0|7|1.50|actínido
92|U|uranio|238.03|0|7|1.38|actínido
93|Np|neptunio|[237]|0|7|1.36|actínido
94|Pu|plutonio|[244]|0|7|1.28|actínido
95|Am|americio|[243]|0|7|1.13|actínido
96|Cm|curio|[247]|0|7|1.28|actínido
97|Bk|berkelio|[247]|0|7|1.30|actínido
98|Cf|californio|[251]|0|7|1.30|actínido
99|Es|einstenio|[252]|0|7|1.30|actínido
100|Fm|fermio|[257]|0|7|1.30|actínido
101|Md|mendelevio|[258]|0|7|1.30|actínido
102|No|nobelio|[259]|0|7|1.30|actínido
103|Lr|lawrencio|[266]|0|7|1.30|actínido
104|Rf|rutherfordio|[267]|4|7|0|metal de transición
105|Db|dubnio|[268]|5|7|0|metal de transición
106|Sg|seaborgio|[269]|6|7|0|metal de transición
107|Bh|bohrio|[270]|7|7|0|metal de transición
108|Hs|hassio|[269]|8|7|0|metal de transición
109|Mt|meitnerio|[278]|9|7|0|metal de transición
110|Ds|darmstatio|[281]|10|7|0|metal de transición
111|Rg|roentgenio|[282]|11|7|0|metal de transición
112|Cn|copernicio|[285]|12|7|0|metal de transición
113|Nh|nihonio|[286]|13|7|0|metal
114|Fl|flerovio|[289]|14|7|0|metal
115|Mc|moscovio|[290]|15|7|0|metal
116|Lv|livermorio|[293]|16|7|0|metal
117|Ts|teneso|[294]|17|7|0|halógeno
118|Og|oganesón|[294]|18|7|0|gas noble
"""


def _cargar_tabla() -> dict:
    t = {}
    for linea in _TABLA_CRUDA.strip().splitlines():
        z, sim, nom, masa, gr, per, en, cat = linea.split("|")
        t[sim] = {"Z": int(z), "simbolo": sim, "nombre": nom,
                  "masa": float(masa.strip("[]")), "estimada": masa.startswith("["),
                  "grupo": int(gr), "periodo": int(per),
                  "electronegatividad": float(en) or None, "categoria": cat}
    return t


TABLA = _cargar_tabla()
POR_NOMBRE = {v["nombre"]: v for v in TABLA.values()}
POR_Z = {v["Z"]: v for v in TABLA.values()}

# Radios covalentes (Å) y color CPK, para el modelo 3D.
_RADIO = {"H": 0.31, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "P": 1.07,
          "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39, "B": 0.84, "Si": 1.11,
          "Na": 1.66, "K": 2.03, "Ca": 1.76, "Mg": 1.41, "Fe": 1.32, "Xe": 1.40,
          "Se": 1.20, "Be": 0.96, "Al": 1.21, "Li": 1.28, "N_def": 0.9}
_COLOR = {"H": (0.95, 0.95, 0.95), "C": (0.22, 0.22, 0.25), "N": (0.19, 0.31, 0.97),
          "O": (0.94, 0.15, 0.15), "F": (0.56, 0.88, 0.31), "Cl": (0.12, 0.94, 0.12),
          "Br": (0.65, 0.16, 0.16), "I": (0.58, 0.0, 0.58), "S": (1.0, 0.86, 0.19),
          "P": (1.0, 0.5, 0.0), "B": (1.0, 0.71, 0.71), "Si": (0.94, 0.78, 0.63)}
_ELECTRONES_VALENCIA = {1: 1, 2: 2, 13: 3, 14: 4, 15: 5, 16: 6, 17: 7, 18: 8}


def elemento(clave) -> dict:
    """Busca por símbolo, nombre o número atómico."""
    if isinstance(clave, int) or (isinstance(clave, str) and clave.isdigit()):
        return POR_Z.get(int(clave), {})
    c = (clave or "").strip()
    if c in TABLA:
        return TABLA[c]
    if c.capitalize() in TABLA:
        return TABLA[c.capitalize()]
    bajo = c.lower()
    for n, v in POR_NOMBRE.items():
        if n.lower() == bajo or n.lower().startswith(bajo):
            return v
    return {}


def ficha_elemento(clave) -> str:
    e = elemento(clave)
    if not e:
        return f"No encuentro el elemento «{clave}», señor."
    return (f"{e['nombre'].capitalize()} ({e['simbolo']}), Z = {e['Z']}. "
            f"Masa atómica {e['masa']:g} u"
            + (" (isótopo más estable)" if e["estimada"] else "")
            + f". Grupo {e['grupo'] or '—'}, periodo {e['periodo']}. "
            f"{e['categoria'].capitalize()}"
            + (f", electronegatividad {e['electronegatividad']:g} (Pauling)."
               if e["electronegatividad"] else "."))


def configuracion_electronica(clave) -> str:
    """Llenado por el principio de Aufbau, con la notación de gas noble."""
    e = elemento(clave)
    if not e:
        return ""
    orden = [("1s", 2), ("2s", 2), ("2p", 6), ("3s", 2), ("3p", 6), ("4s", 2),
             ("3d", 10), ("4p", 6), ("5s", 2), ("4d", 10), ("5p", 6), ("6s", 2),
             ("4f", 14), ("5d", 10), ("6p", 6), ("7s", 2), ("5f", 14), ("7d", 10),
             ("7p", 6)]
    quedan, partes = e["Z"], []
    for orb, cap in orden:
        if quedan <= 0:
            break
        n = min(cap, quedan)
        partes.append(f"{orb}{n}")
        quedan -= n
    return " ".join(partes)


# ── fórmulas y masas molares ───────────────────────────────────────────────
_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)|(\()|(\))(\d*)|([·\.\*])(\d*)")


def contar_atomos(formula: str) -> dict:
    """«Ca(OH)2» -> {'Ca':1,'O':2,'H':2}. Entiende hidratos «CuSO4·5H2O»."""
    f = (formula or "").strip().replace(" ", "")
    f = re.sub(r"\^?\d*[+-]$", "", f)          # quita la carga de los iones
    partes = re.split(r"[·•]", f)
    total = {}
    for parte in partes:
        m = re.match(r"^(\d+)", parte)
        mult = int(m.group(1)) if m else 1
        if m:
            parte = parte[m.end():]
        for sim, n in _contar_simple(parte).items():
            total[sim] = total.get(sim, 0) + n * mult
    return total


def _contar_simple(f: str) -> dict:
    pila = [{}]
    i = 0
    while i < len(f):
        c = f[i]
        if c == "(" or c == "[":
            pila.append({})
            i += 1
        elif c == ")" or c == "]":
            grupo = pila.pop()
            i += 1
            m = re.match(r"\d+", f[i:])
            n = int(m.group(0)) if m else 1
            i += m.end() if m else 0
            for k, v in grupo.items():
                pila[-1][k] = pila[-1].get(k, 0) + v * n
        else:
            m = re.match(r"([A-Z][a-z]?)(\d*)", f[i:])
            if not m:
                i += 1
                continue
            sim = m.group(1)
            n = int(m.group(2)) if m.group(2) else 1
            pila[-1][sim] = pila[-1].get(sim, 0) + n
            i += m.end()
    return pila[0]


def masa_molar(formula: str) -> dict:
    """Masa molar con el desglose elemento a elemento y el % en masa."""
    atomos = contar_atomos(formula)
    if not atomos:
        return {"ok": False, "pasos": [f"No entiendo la fórmula «{formula}»."]}
    total, filas, desconocidos = 0.0, [], []
    for sim, n in atomos.items():
        e = TABLA.get(sim)
        if not e:
            desconocidos.append(sim)
            continue
        aporte = e["masa"] * n
        total += aporte
        filas.append((sim, n, e["masa"], aporte))
    if desconocidos:
        return {"ok": False,
                "pasos": [f"No conozco el elemento «{', '.join(desconocidos)}»."]}
    pasos = [f"Fórmula: {formula}", "Suma de masas atómicas:"]
    for sim, n, ma, ap in sorted(filas, key=lambda r: -r[3]):
        pasos.append(f"   {sim}: {n} × {ma:g} u = {ap:.4f} u")
    pasos.append(f"Masa molar M = {total:.4f} g/mol")
    pasos.append("Composición centesimal:")
    for sim, n, ma, ap in sorted(filas, key=lambda r: -r[3]):
        pasos.append(f"   {sim}: {100 * ap / total:.2f} %")
    return {"ok": True, "masa_molar": total, "atomos": atomos,
            "composicion": {s: 100 * a / total for s, _n, _m, a in filas},
            "pasos": pasos}


# ── balanceo de ecuaciones ─────────────────────────────────────────────────
def balancear(ecuacion: str) -> dict:
    """Balancea por álgebra lineal: el núcleo de la matriz de elementos.

    «Fe + O2 -> Fe2O3» sale como «4 Fe + 3 O2 -> 2 Fe2O3».
    """
    import sympy as sp
    txt = (ecuacion or "").replace("→", "->").replace("=>", "->").replace("⇌", "->")
    if "->" not in txt and "=" in txt:
        txt = txt.replace("=", "->", 1)
    if "->" not in txt:
        return {"ok": False, "pasos": ["Falta la flecha: «A + B -> C»."]}
    izq_txt, der_txt = txt.split("->", 1)
    izq = [s.strip() for s in re.split(r"\+(?![^()]*\))", izq_txt) if s.strip()]
    der = [s.strip() for s in re.split(r"\+(?![^()]*\))", der_txt) if s.strip()]
    # Se quitan los coeficientes que traiga escritos: se recalculan.
    izq = [re.sub(r"^\d+\s*", "", s) for s in izq]
    der = [re.sub(r"^\d+\s*", "", s) for s in der]
    especies = izq + der
    cuentas = [contar_atomos(s) for s in especies]
    elementos = sorted({e for c in cuentas for e in c})
    filas = []
    for el in elementos:
        fila = [c.get(el, 0) for c in cuentas[:len(izq)]]
        fila += [-c.get(el, 0) for c in cuentas[len(izq):]]
        filas.append(fila)
    A = sp.Matrix(filas)
    nucleo = A.nullspace()
    if not nucleo:
        return {"ok": False, "pasos": [
            "Ese esqueleto no se puede balancear: revisa las fórmulas.",
            "Elementos detectados: " + ", ".join(elementos)]}
    v = nucleo[0]
    den = sp.lcm([sp.Rational(x).q for x in v])
    coef = [abs(int(sp.Rational(x) * den)) for x in v]
    g = 0
    for c in coef:
        g = math.gcd(g, c)
    coef = [c // (g or 1) for c in coef]
    if any(c == 0 for c in coef):
        return {"ok": False, "pasos": ["Salen coeficientes nulos: la reacción "
                                       "escrita no cuadra."]}

    def lado(esp, cs):
        return " + ".join((f"{c} {s}" if c != 1 else s) for s, c in zip(esp, cs))

    balanceada = f"{lado(izq, coef[:len(izq)])} → {lado(der, coef[len(izq):])}"
    pasos = ["Se asigna una incógnita a cada especie y se impone que cada "
             "elemento tenga los mismos átomos a los dos lados.",
             "Sistema homogéneo (una fila por elemento):"]
    for el, fila in zip(elementos, filas):
        pasos.append(f"   {el}: " + "  ".join(f"{x:+d}·x{i+1}" for i, x in enumerate(fila)))
    pasos.append("La solución es el núcleo de la matriz, escalado a enteros mínimos:")
    pasos.append("   " + ", ".join(f"x{i+1} = {c}" for i, c in enumerate(coef)))
    pasos.append(f"Ecuación ajustada:  {balanceada}")
    comprobacion = []
    for el in elementos:
        a = sum(c.get(el, 0) * k for c, k in zip(cuentas[:len(izq)], coef[:len(izq)]))
        b = sum(c.get(el, 0) * k for c, k in zip(cuentas[len(izq):], coef[len(izq):]))
        comprobacion.append(f"{el}: {a} = {b}")
    pasos.append("Comprobación — " + " · ".join(comprobacion))
    return {"ok": True, "ecuacion": balanceada, "coeficientes": coef,
            "reactivos": izq, "productos": der, "pasos": pasos}


def estequiometria(ecuacion: str, datos: dict, objetivo: str = "", log=print) -> dict:
    """Gramos/moles de cada especie a partir de los datos, con limitante.

    `datos` = {"Fe": {"g": 10}, "O2": {"mol": 0.5}}
    """
    bal = balancear(ecuacion)
    if not bal.get("ok"):
        return bal
    especies = bal["reactivos"] + bal["productos"]
    coef = bal["coeficientes"]
    pasos = list(bal["pasos"]) + ["", "Estequiometría:"]
    masas = {}
    for s in especies:
        mm = masa_molar(s)
        masas[s] = mm["masa_molar"] if mm.get("ok") else None
    moles = {}
    for s, d in (datos or {}).items():
        if s not in especies:
            continue
        if "mol" in d:
            moles[s] = float(d["mol"])
            pasos.append(f"   {s}: {moles[s]:.6g} mol (dato)")
        elif "g" in d and masas.get(s):
            moles[s] = float(d["g"]) / masas[s]
            pasos.append(f"   {s}: {float(d['g']):g} g ÷ {masas[s]:.4f} g/mol "
                         f"= {moles[s]:.6g} mol")
    if not moles:
        return {"ok": False, "pasos": pasos + ["No me has dado ninguna cantidad."]}
    # Reactivo limitante: el de menor cociente mol/coeficiente.
    razones = {s: moles[s] / coef[especies.index(s)]
               for s in moles if s in bal["reactivos"]}
    limitante = min(razones, key=razones.get) if razones else list(moles)[0]
    avance = razones.get(limitante, moles[limitante] / coef[especies.index(limitante)])
    if len(razones) > 1:
        pasos.append("Cociente mol/coeficiente de cada reactivo:")
        for s, r in razones.items():
            pasos.append(f"   {s}: {moles[s]:.6g}/{coef[especies.index(s)]} = {r:.6g}")
        pasos.append(f"El MENOR manda: el reactivo limitante es {limitante}.")
    pasos.append(f"Grado de avance ξ = {avance:.6g} mol de reacción.")
    salida = {}
    pasos.append("Cantidades de todas las especies:")
    for s, c in zip(especies, coef):
        n = avance * c
        g = n * masas[s] if masas.get(s) else None
        salida[s] = {"mol": n, "g": g}
        pasos.append(f"   {s}: {n:.6g} mol"
                     + (f" = {g:.6g} g" if g is not None else "")
                     + ("  (limitante)" if s == limitante else
                        "  (en exceso: sobran %.6g mol)" % (moles[s] - n)
                        if s in moles and s in bal["reactivos"] and moles[s] > n + 1e-12
                        else ""))
    res = {"ok": True, "ecuacion": bal["ecuacion"], "limitante": limitante,
           "avance": avance, "cantidades": salida, "pasos": pasos}
    if objetivo and objetivo in salida:
        res["resultado"] = salida[objetivo]
    return res


# ── disoluciones, gases, pH ────────────────────────────────────────────────
def disolucion(masa_g: float = None, formula: str = "", moles: float = None,
               volumen_L: float = None, molaridad: float = None) -> dict:
    """Rellena lo que falte entre masa, moles, volumen y molaridad."""
    pasos = []
    Mm = None
    if formula:
        mm = masa_molar(formula)
        if mm.get("ok"):
            Mm = mm["masa_molar"]
            pasos.append(f"M({formula}) = {Mm:.4f} g/mol")
    if moles is None and masa_g is not None and Mm:
        moles = masa_g / Mm
        pasos.append(f"n = m/M = {masa_g:g}/{Mm:.4f} = {moles:.6g} mol")
    if molaridad is None and moles is not None and volumen_L:
        molaridad = moles / volumen_L
        pasos.append(f"c = n/V = {moles:.6g}/{volumen_L:g} = {molaridad:.6g} mol/L")
    if moles is None and molaridad is not None and volumen_L:
        moles = molaridad * volumen_L
        pasos.append(f"n = c·V = {molaridad:g}·{volumen_L:g} = {moles:.6g} mol")
    if masa_g is None and moles is not None and Mm:
        masa_g = moles * Mm
        pasos.append(f"m = n·M = {moles:.6g}·{Mm:.4f} = {masa_g:.6g} g")
    if volumen_L is None and moles is not None and molaridad:
        volumen_L = moles / molaridad
        pasos.append(f"V = n/c = {volumen_L:.6g} L")
    return {"ok": True, "masa_g": masa_g, "moles": moles, "volumen_L": volumen_L,
            "molaridad": molaridad, "masa_molar": Mm, "pasos": pasos}


def dilucion(c1=None, v1=None, c2=None, v2=None) -> dict:
    """c₁V₁ = c₂V₂: se despeja lo que falte."""
    vals = {"c1": c1, "v1": v1, "c2": c2, "v2": v2}
    falta = [k for k, v in vals.items() if v is None]
    if len(falta) != 1:
        return {"ok": False, "pasos": ["Dame exactamente tres de los cuatro datos."]}
    k = falta[0]
    if k == "c1":
        vals["c1"] = c2 * v2 / v1
    elif k == "v1":
        vals["v1"] = c2 * v2 / c1
    elif k == "c2":
        vals["c2"] = c1 * v1 / v2
    else:
        vals["v2"] = c1 * v1 / c2
    return {"ok": True, **vals,
            "pasos": ["Ley de la dilución: c₁·V₁ = c₂·V₂",
                      f"   {vals['c1']:.6g}·{vals['v1']:.6g} = "
                      f"{vals['c2']:.6g}·{vals['v2']:.6g}",
                      f"Despejando {k} = {vals[k]:.6g}"]}


def gas_ideal(P=None, V=None, n=None, T=None, van_der_waals: str = "") -> dict:
    """pV = nRT en SI (Pa, m³, mol, K). Con van der Waals si se pide el gas."""
    R = 8.314462618
    vals = {"P": P, "V": V, "n": n, "T": T}
    falta = [k for k, v in vals.items() if v is None]
    pasos = ["Ecuación de los gases ideales: p·V = n·R·T",
             f"   R = {R} J/(mol·K); unidades en SI: Pa, m³, mol, K"]
    if len(falta) != 1:
        return {"ok": False, "pasos": pasos + ["Dame tres de los cuatro datos."]}
    k = falta[0]
    if k == "P":
        vals["P"] = n * R * T / V
    elif k == "V":
        vals["V"] = n * R * T / P
    elif k == "n":
        vals["n"] = P * V / (R * T)
    else:
        vals["T"] = P * V / (n * R)
    pasos.append(f"Despejando {k} = {vals[k]:.6g}")
    # Gases reales: a (Pa·m⁶/mol²) y b (m³/mol)
    VDW = {"He": (3.46e-3, 2.38e-5), "H2": (2.48e-2, 2.66e-5),
           "N2": (1.408e-1, 3.913e-5), "O2": (1.378e-1, 3.183e-5),
           "CO2": (3.640e-1, 4.267e-5), "CH4": (2.283e-1, 4.278e-5),
           "NH3": (4.225e-1, 3.707e-5), "H2O": (5.537e-1, 3.049e-5)}
    if van_der_waals in VDW and vals["V"] and vals["n"] and vals["T"]:
        a, b = VDW[van_der_waals]
        Vm = vals["V"] / vals["n"]
        Pr = R * vals["T"] / (Vm - b) - a / Vm**2
        pasos.append(f"Van der Waals para {van_der_waals} "
                     f"(a={a:g}, b={b:g}):  p = RT/(Vm−b) − a/Vm²")
        pasos.append(f"   p_real = {Pr:.6g} Pa frente a p_ideal = "
                     f"{vals['P']:.6g} Pa  "
                     f"(desviación {100 * (Pr - vals['P']) / vals['P']:+.2f} %)")
        vals["P_vdw"] = Pr
    return {"ok": True, **vals, "pasos": pasos}


def ph(concentracion: float, tipo: str = "acido fuerte", ka: float = None,
       kb: float = None) -> dict:
    """pH de ácidos/bases fuertes y débiles, con la aproximación justificada."""
    c = float(concentracion)
    t = (tipo or "").lower()
    pasos = [f"Concentración c = {c:g} mol/L", "Kw = 1,0·10⁻¹⁴ a 25 °C"]
    if "fuerte" in t and "base" not in t:
        h = c
        pasos.append("Ácido fuerte: se disocia del todo, [H⁺] = c")
    elif "fuerte" in t:
        oh = c
        h = 1e-14 / oh
        pasos.append("Base fuerte: [OH⁻] = c  →  [H⁺] = Kw/[OH⁻]")
    elif "base" in t and kb:
        oh = (-kb + math.sqrt(kb * kb + 4 * kb * c)) / 2
        h = 1e-14 / oh
        pasos.append(f"Base débil, Kb = {kb:g}. Equilibrio B + H₂O ⇌ BH⁺ + OH⁻")
        pasos.append("   Kb = x²/(c−x)  →  x resuelto sin aproximar: "
                     f"[OH⁻] = {oh:.6g} mol/L")
        pasos.append(f"   pOH = {-math.log10(oh):.4f}")
    elif ka:
        h = (-ka + math.sqrt(ka * ka + 4 * ka * c)) / 2
        pasos.append(f"Ácido débil, Ka = {ka:g}. Equilibrio HA ⇌ H⁺ + A⁻")
        pasos.append("   Ka = x²/(c−x)  →  x resuelto sin aproximar: "
                     f"[H⁺] = {h:.6g} mol/L")
        alfa = h / c
        pasos.append(f"   Grado de disociación α = {100 * alfa:.3f} %"
                     + ("  (la aproximación c−x≈c era válida)" if alfa < 0.05
                        else "  (α > 5 %: NO valía aproximar)"))
    else:
        return {"ok": False, "pasos": ["Dime si es fuerte o débil, y su Ka o Kb."]}
    pH = -math.log10(h)
    pasos.append(f"pH = −log[H⁺] = {pH:.4f}     pOH = {14 - pH:.4f}")
    pasos.append("Disolución " + ("ácida" if pH < 7 else "básica" if pH > 7 else "neutra"))
    return {"ok": True, "pH": pH, "pOH": 14 - pH, "H": h, "pasos": pasos}


def buffer(ka: float, c_acido: float, c_base: float) -> dict:
    """Henderson-Hasselbalch, con el aviso de cuándo deja de valer."""
    pka = -math.log10(ka)
    pH = pka + math.log10(c_base / c_acido)
    razon = c_base / c_acido
    return {"ok": True, "pH": pH, "pKa": pka,
            "pasos": [f"pKa = −log Ka = {pka:.4f}",
                      "Henderson-Hasselbalch: pH = pKa + log([base]/[ácido])",
                      f"   pH = {pka:.4f} + log({c_base:g}/{c_acido:g}) = {pH:.4f}",
                      f"Relación base/ácido = {razon:.4g}: "
                      + ("tampón eficaz (entre 0,1 y 10)" if 0.1 <= razon <= 10
                         else "fuera del rango útil de tamponamiento")]}


def curva_valoracion(c_acido: float, v_acido_L: float, c_base: float,
                     ka: float = None, carpeta: str = "", log=print) -> dict:
    """Curva de valoración completa, con el punto de equivalencia marcado."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    Kw = 1e-14
    n_ac = c_acido * v_acido_L
    v_eq = n_ac / c_base
    vs = np.linspace(0, v_eq * 2, 1400)
    phs = []
    for v in vs:
        n_b = c_base * v
        vt = v_acido_L + v
        if ka is None:                                   # ácido fuerte
            neto = (n_ac - n_b) / vt
            h = neto if neto > 0 else Kw / (-neto if neto < 0 else 1e-7)
            if abs(neto) < 1e-12:
                h = 1e-7
        else:                                            # ácido débil
            if n_b <= 0:
                h = (-ka + math.sqrt(ka * ka + 4 * ka * c_acido)) / 2
            elif n_b < n_ac:
                h = ka * (n_ac - n_b) / n_b               # tampón
            elif abs(n_b - n_ac) < 1e-15:
                cb = n_ac / vt                            # hidrólisis de la sal
                kb = Kw / ka
                oh = math.sqrt(kb * cb)
                h = Kw / oh
            else:
                h = Kw / ((n_b - n_ac) / vt)
        phs.append(-math.log10(max(h, 1e-16)))
    phs = np.array(phs)
    fig, ax = plt.subplots(figsize=(10.5, 6.4), dpi=190, facecolor=M._FONDO)
    ax.plot(vs * 1000, phs, color=M._ACENTO[0], linewidth=2.4)
    ax.axvline(v_eq * 1000, color=M._ACENTO[3], linestyle="--",
               label=f"equivalencia: {v_eq * 1000:.3g} mL")
    ax.axhline(7, color=M._REJILLA, linestyle=":")
    if ka is not None:
        ax.axvline(v_eq * 500, color=M._ACENTO[2], linestyle=":",
                   label=f"semiequivalencia: pH = pKa = {-math.log10(ka):.2f}")
    ax.set_ylim(0, 14)
    M._estilo(ax, "Curva de valoración", "volumen de base añadido (mL)", "pH")
    ax.legend(facecolor=M._PANEL, edgecolor=M._REJILLA, labelcolor=M._TINTA, fontsize=9)
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("valoracion")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    pasos = [f"Moles de ácido: n = c·V = {c_acido:g}·{v_acido_L:g} = {n_ac:.6g} mol",
             f"Volumen de base en la equivalencia: V = n/c = {v_eq * 1000:.4g} mL",
             f"pH inicial = {phs[0]:.3f}",
             f"pH en la equivalencia = {phs[np.argmin(abs(vs - v_eq))]:.3f}"
             + (" (>7: la sal de ácido débil hidroliza)" if ka else " (=7: sal neutra)"),
             "El salto brusco alrededor de la equivalencia es lo que ve el indicador."]
    datos = {"tipo": "2d", "x": (vs * 1000).tolist(),
             "series": [{"nombre": "pH", "y": phs.tolist()}]}
    return {"ok": True, "png": png, "carpeta": out, "v_equivalencia": v_eq,
            "pasos": pasos,
            "html": M.visor_web(datos, os.path.join(out, "visor.html"), "Valoración")}


# ── cinética, equilibrio, termoquímica, electroquímica ─────────────────────
def cinetica(orden: int = 1, k: float = 0.1, c0: float = 1.0, t_max: float = 50.0,
             carpeta: str = "", log=print) -> dict:
    """Ley integrada de velocidad de orden 0, 1 o 2, con la recta que linealiza."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    ts = np.linspace(0, float(t_max), 800)
    if orden == 0:
        c = np.maximum(c0 - k * ts, 0)
        lin, etiqueta, t12 = c, "[A] frente a t", c0 / (2 * k)
        ley = "[A] = [A]₀ − k·t"
    elif orden == 2:
        c = 1 / (1 / c0 + k * ts)
        lin, etiqueta, t12 = 1 / c, "1/[A] frente a t", 1 / (k * c0)
        ley = "1/[A] = 1/[A]₀ + k·t"
    else:
        c = c0 * np.exp(-k * ts)
        lin, etiqueta, t12 = np.log(c), "ln[A] frente a t", math.log(2) / k
        ley = "ln[A] = ln[A]₀ − k·t"
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5.8), dpi=190, facecolor=M._FONDO)
    ax.plot(ts, c, color=M._ACENTO[0], linewidth=2.3)
    ax.axhline(c0 / 2, color=M._REJILLA, linestyle=":")
    ax.axvline(t12, color=M._ACENTO[3], linestyle="--", label=f"t½ = {t12:.4g} s")
    ax.legend(facecolor=M._PANEL, edgecolor=M._REJILLA, labelcolor=M._TINTA, fontsize=9)
    M._estilo(ax, f"Cinética de orden {orden}", "t (s)", "[A] (mol/L)")
    ax2.plot(ts, lin, color=M._ACENTO[1], linewidth=2.3)
    M._estilo(ax2, f"Linealización: {etiqueta}", "t (s)", etiqueta.split(" ")[0])
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("cinetica")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    pasos = [f"Orden {orden}: v = k·[A]^{orden}",
             f"Ley integrada: {ley}",
             f"k = {k:g} (unidades de orden {orden})",
             f"Tiempo de semirreacción t½ = {t12:.6g} s"
             + ("  (independiente de la concentración: marca del orden 1)"
                if orden == 1 else ""),
             f"A t = {t_max:g} s queda [A] = {c[-1]:.6g} mol/L "
             f"({100 * c[-1] / c0:.2f} % del inicial)",
             "Si al representar " + etiqueta + " sale una RECTA, el orden es correcto."]
    datos = {"tipo": "2d", "x": ts.tolist(),
             "series": [{"nombre": "[A] (mol/L)", "y": c.tolist()},
                        {"nombre": etiqueta.split(" ")[0], "y": lin.tolist()}]}
    return {"ok": True, "png": png, "carpeta": out, "t_medio": t12, "pasos": pasos,
            "html": M.visor_web(datos, os.path.join(out, "visor.html"), "Cinética")}


def arrhenius(Ea_kJ: float, A: float = 1e13, T1: float = 298.0, T2: float = 0.0,
              carpeta: str = "", log=print) -> dict:
    """k(T) de Arrhenius y la recta de ln k frente a 1/T."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    R = 8.314462618
    Ea = Ea_kJ * 1000
    Ts = np.linspace(250, 600, 600)
    ks = A * np.exp(-Ea / (R * Ts))
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5.6), dpi=190, facecolor=M._FONDO)
    ax.plot(Ts, ks, color=M._ACENTO[0], linewidth=2.3)
    ax.set_yscale("log")
    M._estilo(ax, "k(T) de Arrhenius", "T (K)", "k (escala log)")
    ax2.plot(1 / Ts, np.log(ks), color=M._ACENTO[1], linewidth=2.3)
    M._estilo(ax2, "ln k frente a 1/T  ·  pendiente = −Eₐ/R", "1/T (1/K)", "ln k")
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("arrhenius")
    png = os.path.join(out, "lamina.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    k1 = A * math.exp(-Ea / (R * T1))
    pasos = [f"k = A·e^(−Eₐ/RT)   con A = {A:g} y Eₐ = {Ea_kJ:g} kJ/mol",
             f"A {T1:g} K:  k = {k1:.6g}"]
    if T2:
        k2 = A * math.exp(-Ea / (R * T2))
        pasos.append(f"A {T2:g} K:  k = {k2:.6g}")
        pasos.append(f"La velocidad se multiplica por {k2 / k1:.4g} al pasar de "
                     f"{T1:g} K a {T2:g} K.")
        pasos.append("Forma de dos puntos: ln(k₂/k₁) = −Eₐ/R · (1/T₂ − 1/T₁)")
    pasos.append("La pendiente de ln k frente a 1/T es −Eₐ/R: así se mide Eₐ "
                 "en el laboratorio.")
    return {"ok": True, "png": png, "carpeta": out, "pasos": pasos, "html": ""}


def equilibrio(K: float, iniciales: dict, coeficientes: dict, log=print) -> dict:
    """Tabla ICE resuelta: `coeficientes` negativo para reactivos.

    equilibrio(0.5, {"A": 1.0, "B": 1.0, "C": 0}, {"A": -1, "B": -1, "C": 1})
    """
    import sympy as sp
    x = sp.Symbol("x", real=True)
    expr_num, expr_den = sp.Integer(1), sp.Integer(1)
    filas = []
    for esp, c in coeficientes.items():
        ini = iniciales.get(esp, 0.0)
        eq = sp.nsimplify(ini) + c * x
        filas.append((esp, ini, c, eq))
        if c > 0:
            expr_num *= eq**c
        elif c < 0:
            expr_den *= eq**(-c)
    ec = sp.Eq(expr_num / expr_den, sp.nsimplify(K))
    pasos = ["Tabla ICE (inicial, cambio, equilibrio):"]
    for esp, ini, c, eq in filas:
        pasos.append(f"   {esp}: {ini:g}  {c:+g}x  →  {sp.sstr(eq)}")
    pasos.append(f"Kc = {sp.sstr(expr_num / expr_den)} = {K:g}")
    soluciones = [s for s in sp.solve(ec, x) if s.is_real]
    validas = []
    for s in soluciones:
        v = float(s)
        if all(float(eq.subs(x, v)) >= -1e-12 for _e, _i, _c, eq in filas):
            validas.append(v)
    if not validas:
        return {"ok": False, "pasos": pasos + ["Ninguna raíz da concentraciones "
                                               "positivas: revisa los datos."]}
    xv = min(validas, key=abs)
    pasos.append(f"Raíces: {', '.join(f'{float(s):.6g}' for s in soluciones)}"
                 f"  →  la físicamente válida es x = {xv:.6g}")
    conc = {}
    pasos.append("Concentraciones en el equilibrio:")
    for esp, _i, _c, eq in filas:
        conc[esp] = float(eq.subs(x, xv))
        pasos.append(f"   [{esp}] = {conc[esp]:.6g} mol/L")
    return {"ok": True, "x": xv, "concentraciones": conc, "pasos": pasos}


# Entalpías de formación estándar (kJ/mol) de lo que más sale en los ejercicios.
ENTALPIAS_FORMACION = {
    "H2O(l)": -285.8, "H2O(g)": -241.8, "CO2(g)": -393.5, "CO(g)": -110.5,
    "CH4(g)": -74.6, "C2H6(g)": -84.0, "C2H4(g)": 52.4, "C2H2(g)": 227.4,
    "C3H8(g)": -103.8, "C4H10(g)": -125.7, "C6H6(l)": 49.1, "C8H18(l)": -250.1,
    "C2H5OH(l)": -277.6, "CH3OH(l)": -239.2, "C6H12O6(s)": -1273.3,
    "NH3(g)": -45.9, "NO(g)": 91.3, "NO2(g)": 33.2, "N2O4(g)": 11.1,
    "SO2(g)": -296.8, "SO3(g)": -395.7, "H2S(g)": -20.6,
    "HCl(g)": -92.3, "HF(g)": -273.3, "HBr(g)": -36.3, "HI(g)": 26.5,
    "NaCl(s)": -411.2, "CaCO3(s)": -1207.6, "CaO(s)": -634.9,
    "Ca(OH)2(s)": -985.2, "Fe2O3(s)": -824.2, "Al2O3(s)": -1675.7,
    "MgO(s)": -601.6, "CuO(s)": -157.3, "ZnO(s)": -350.5,
    "H2(g)": 0.0, "O2(g)": 0.0, "N2(g)": 0.0, "C(s)": 0.0, "Fe(s)": 0.0,
    "Cl2(g)": 0.0, "Na(s)": 0.0, "Ca(s)": 0.0, "Al(s)": 0.0, "Cu(s)": 0.0,
}


def entalpia_reaccion(reactivos: dict, productos: dict) -> dict:
    """ΔH°r = Σ n·ΔH°f(productos) − Σ n·ΔH°f(reactivos). Ley de Hess."""
    pasos = ["Ley de Hess: ΔH°r = Σ n·ΔH°f(productos) − Σ n·ΔH°f(reactivos)"]
    faltan = []
    total_p, total_r = 0.0, 0.0
    for lado, dic, signo in (("Productos", productos, 1), ("Reactivos", reactivos, -1)):
        pasos.append(f"{lado}:")
        for esp, n in dic.items():
            dh = ENTALPIAS_FORMACION.get(esp)
            if dh is None:
                faltan.append(esp)
                continue
            pasos.append(f"   {n:g} × {esp}: {n:g} × ({dh:g}) = {n * dh:.2f} kJ")
            if signo > 0:
                total_p += n * dh
            else:
                total_r += n * dh
    if faltan:
        pasos.append("No tengo ΔH°f de: " + ", ".join(faltan)
                     + ". Escríbelo como «CO2(g)», con el estado.")
        return {"ok": False, "pasos": pasos}
    dh = total_p - total_r
    pasos.append(f"ΔH°r = ({total_p:.2f}) − ({total_r:.2f}) = {dh:.2f} kJ")
    pasos.append("Reacción " + ("EXOTÉRMICA: desprende calor." if dh < 0
                                else "ENDOTÉRMICA: absorbe calor."))
    return {"ok": True, "delta_H": dh, "pasos": pasos}


# Potenciales estándar de reducción (V).
POTENCIALES = {
    "Li+/Li": -3.04, "K+/K": -2.93, "Ca2+/Ca": -2.87, "Na+/Na": -2.71,
    "Mg2+/Mg": -2.37, "Al3+/Al": -1.66, "Zn2+/Zn": -0.76, "Fe2+/Fe": -0.44,
    "Ni2+/Ni": -0.25, "Sn2+/Sn": -0.14, "Pb2+/Pb": -0.13, "H+/H2": 0.00,
    "Cu2+/Cu": 0.34, "I2/I-": 0.54, "Fe3+/Fe2+": 0.77, "Ag+/Ag": 0.80,
    "Br2/Br-": 1.09, "O2/H2O": 1.23, "Cl2/Cl-": 1.36, "MnO4-/Mn2+": 1.51,
    "F2/F-": 2.87,
}


def pila(catodo: str, anodo: str, n: int = 2, Q: float = 1.0, T: float = 298.15) -> dict:
    """Fuerza electromotriz estándar, Nernst, ΔG y constante de equilibrio."""
    R, F = 8.314462618, 96485.0
    ec = POTENCIALES.get(catodo)
    ea = POTENCIALES.get(anodo)
    if ec is None or ea is None:
        return {"ok": False, "pasos": [
            "No tengo ese par redox. Los que conozco: " + ", ".join(sorted(POTENCIALES))]}
    E0 = ec - ea
    E = E0 - (R * T / (n * F)) * math.log(Q) if Q > 0 else E0
    dG = -n * F * E0
    K = math.exp(n * F * E0 / (R * T))
    return {"ok": True, "E0": E0, "E": E, "delta_G": dG, "K": K,
            "pasos": [f"Cátodo (reducción): {catodo}, E° = {ec:+.2f} V",
                      f"Ánodo (oxidación):  {anodo}, E° = {ea:+.2f} V",
                      f"E°pila = E°cátodo − E°ánodo = {ec:+.2f} − ({ea:+.2f}) = {E0:+.3f} V",
                      "Espontánea" if E0 > 0 else "NO espontánea tal como está escrita",
                      f"Nernst: E = E° − (RT/nF)·ln Q = {E:+.4f} V  (Q = {Q:g}, n = {n})",
                      f"ΔG° = −nFE° = {dG / 1000:.2f} kJ/mol",
                      f"Constante de equilibrio K = e^(nFE°/RT) = {K:.4g}"]}


# ── geometría molecular en 3D (RPECV / VSEPR) ──────────────────────────────
# (dominios, pares solitarios) -> (nombre, ángulo aproximado)
_GEOMETRIAS = {
    (2, 0): ("lineal", 180.0), (3, 0): ("trigonal plana", 120.0),
    (3, 1): ("angular", 118.0), (4, 0): ("tetraédrica", 109.5),
    (4, 1): ("pirámide trigonal", 107.0), (4, 2): ("angular", 104.5),
    (5, 0): ("bipirámide trigonal", 90.0), (5, 1): ("balancín", 89.0),
    (5, 2): ("forma de T", 88.0), (5, 3): ("lineal", 180.0),
    (6, 0): ("octaédrica", 90.0), (6, 1): ("pirámide cuadrada", 89.0),
    (6, 2): ("plano cuadrada", 90.0),
}
# Electrones que el átomo central comparte con cada tipo de ligando.
_ENLACES = {"H": 1, "F": 1, "Cl": 1, "Br": 1, "I": 1, "O": 2, "S": 2, "Se": 2,
            "N": 3, "P": 3, "C": 4}
# Cuánto se acorta un enlace al subir de orden, respecto del simple. Valores
# empíricos de uso común: con ellos el N≡N sale a 111 pm (mide 110) y el C=O
# del CO2 a 122 (mide 116), en vez de a 142 los dos.
_ACORTA = {1: 1.00, 2: 0.86, 3: 0.78}


def _direcciones(dominios: int) -> list:
    """Vectores unitarios de los dominios electrónicos, en orden de preferencia."""
    s3 = 1 / math.sqrt(3)
    if dominios <= 2:
        return [(0, 0, 1), (0, 0, -1)]
    if dominios == 3:
        return [(math.cos(a), math.sin(a), 0)
                for a in (math.pi / 2, math.pi / 2 + 2 * math.pi / 3,
                          math.pi / 2 + 4 * math.pi / 3)]
    if dominios == 4:
        return [(s3, s3, s3), (-s3, -s3, s3), (-s3, s3, -s3), (s3, -s3, -s3)]
    if dominios == 5:
        # Ecuatoriales primero: los pares solitarios se colocan ahí.
        return [(1, 0, 0), (-0.5, math.sqrt(3) / 2, 0), (-0.5, -math.sqrt(3) / 2, 0),
                (0, 0, 1), (0, 0, -1)]
    return [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]


def geometria_molecular(formula: str) -> dict:
    """Modelo RPECV: átomo central, dominios, pares solitarios y forma."""
    f = (formula or "").strip()
    carga = 0
    mc = re.search(r"([+-]\d*|\d*[+-])$", f)
    if mc and mc.group(1):
        s = mc.group(1)
        n = int(re.sub(r"[+-]", "", s) or 1)
        carga = n if "+" in s else -n
        f = f[:mc.start()]
    atomos = contar_atomos(f)
    if not atomos:
        return {"ok": False, "pasos": [f"No entiendo «{formula}»."]}
    if len(atomos) == 1 and sum(atomos.values()) <= 2:
        sim = list(atomos)[0]
        return {"ok": True, "central": sim, "ligandos": [sim] * (atomos[sim] - 1),
                "pares": 0, "forma": "lineal", "angulo": 180.0,
                "pasos": [f"{formula}: molécula diatómica, necesariamente lineal."]}
    # El central es el menos electronegativo que no sea hidrógeno.
    candidatos = [s for s in atomos if s != "H"]
    central = min(candidatos, key=lambda s: (TABLA.get(s, {}).get("electronegatividad")
                                             or 9, -atomos[s]))
    if atomos[central] > 1 and len(candidatos) > 1:
        central = min(candidatos, key=lambda s: atomos[s])
    ligandos = []
    for s, n in atomos.items():
        ligandos += [s] * (n - (1 if s == central else 0))
    e = TABLA.get(central, {})
    valencia = _ELECTRONES_VALENCIA.get(e.get("grupo", 0), 4) - carga
    compartidos = sum(_ENLACES.get(l, 1) for l in ligandos)
    pares = max(int(round((valencia - compartidos) / 2)), 0)
    dominios = len(ligandos) + pares
    forma, angulo = _GEOMETRIAS.get((dominios, pares), ("compleja", 109.5))
    pasos = [f"Fórmula: {formula}" + (f" (carga {carga:+d})" if carga else ""),
             f"Átomo central: {central} ({e.get('nombre', '')}), "
             f"{valencia} electrones de valencia"
             + (f" ajustados por la carga {carga:+d}" if carga else ""),
             f"Ligandos: {len(ligandos)} ({', '.join(sorted(set(ligandos))) or '—'})",
             f"Electrones compartidos en los enlaces: {compartidos}",
             f"Pares solitarios = ({valencia} − {compartidos}) / 2 = {pares}",
             f"Dominios electrónicos = {len(ligandos)} enlaces + {pares} pares "
             f"= {dominios}",
             f"Geometría ELECTRÓNICA: "
             + _GEOMETRIAS.get((dominios, 0), ("compleja", 0))[0],
             f"Geometría MOLECULAR: {forma}, ángulos ≈ {angulo:g}°"]
    en_c = e.get("electronegatividad") or 0
    difs = [abs(en_c - (TABLA.get(l, {}).get("electronegatividad") or 0))
            for l in ligandos]
    if difs:
        d = max(difs)
        pasos.append(f"Mayor diferencia de electronegatividad: {d:.2f} → enlace "
                     + ("iónico" if d > 1.7 else
                        "covalente polar" if d > 0.4 else "covalente apolar"))
    simetrica = pares == 0 and len(set(ligandos)) == 1
    pasos.append("Molécula " + ("APOLAR: los dipolos se anulan por simetría."
                                if simetrica else
                                "POLAR: los dipolos no llegan a anularse."))
    return {"ok": True, "central": central, "ligandos": ligandos, "pares": pares,
            "dominios": dominios, "forma": forma, "angulo": angulo,
            "polar": not simetrica, "pasos": pasos}


def _esfera(centro, r: float, n: int = 14):
    """Malla UV de una esfera: los átomos del modelo de bolas y varillas."""
    verts, caras = [], []
    for i in range(n + 1):
        lat = math.pi * i / n
        for j in range(n):
            lon = 2 * math.pi * j / n
            verts.append((centro[0] + r * math.sin(lat) * math.cos(lon),
                          centro[1] + r * math.sin(lat) * math.sin(lon),
                          centro[2] + r * math.cos(lat)))
    for i in range(n):
        for j in range(n):
            a = i * n + j
            b = i * n + (j + 1) % n
            caras.append((a, b, b + n, a + n))
    return verts, caras


def _separar(destino, orden: int, hueco: float = 0.16) -> list:
    """Los extremos de las `orden` varillas de un enlace simple, doble o triple.

    Se apartan del eje en una dirección perpendicular cualquiera: lo que se
    quiere ver es CUÁNTAS varillas hay, no en qué plano están.
    """
    import numpy as np
    q = np.asarray(destino, dtype=float)
    if orden <= 1:
        return [((0.0, 0.0, 0.0), tuple(q))]
    eje = q / (np.linalg.norm(q) or 1.0)
    # Un vector que no sea paralelo al eje, para el producto vectorial.
    auxiliar = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(eje, auxiliar))) > 0.9:
        auxiliar = np.array([1.0, 0.0, 0.0])
    perp = np.cross(eje, auxiliar)
    perp = perp / (np.linalg.norm(perp) or 1.0) * hueco
    if orden == 2:
        corrimientos = [perp, -perp]
    else:
        corrimientos = [perp, -perp, np.zeros(3)]
    return [(tuple(c), tuple(q + c)) for c in corrimientos]


def _cilindro(p, q, r: float, n: int = 10):
    """Varilla entre dos átomos."""
    import numpy as np
    p, q = np.asarray(p, dtype=float), np.asarray(q, dtype=float)
    eje = q - p
    L = np.linalg.norm(eje)
    if L < 1e-9:
        return [], []
    eje = eje / L
    ref = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(eje, ref))) > 0.95:
        ref = np.array([1.0, 0.0, 0.0])
    u = np.cross(eje, ref)
    u /= np.linalg.norm(u)
    v = np.cross(eje, u)
    verts, caras = [], []
    for base in (p, q):
        for k in range(n):
            a = 2 * math.pi * k / n
            verts.append(tuple(base + r * (math.cos(a) * u + math.sin(a) * v)))
    for k in range(n):
        a, b = k, (k + 1) % n
        caras.append((a, b, b + n, a + n))
    return verts, caras


def modelo_3d_molecula(formula: str, carpeta: str = "", abrir_visor: bool = False,
                       log=print) -> dict:
    """Construye la molécula en 3D (bolas y varillas) y la deja girable.

    Coloca el átomo central en el origen y los ligandos en las direcciones
    que manda la RPECV, a la distancia que suman sus radios covalentes.
    """
    g = geometria_molecular(formula)
    if not g.get("ok"):
        return g
    central, ligandos, pares = g["central"], g["ligandos"], g["pares"]
    dirs = _direcciones(g.get("dominios", len(ligandos)))
    # Los pares solitarios se quedan los sitios de delante (ecuatoriales en la
    # bipirámide); los ligandos ocupan el resto.
    usados = dirs[pares:pares + len(ligandos)] if len(dirs) >= pares + len(ligandos) \
        else dirs[:len(ligandos)]
    rc = _RADIO.get(central, 1.0)
    atomos = [(central, (0.0, 0.0, 0.0), rc)]
    for lig, d in zip(ligandos, usados):
        rl = _RADIO.get(lig, 0.9)
        # Los radios covalentes tabulados son de ENLACE SIMPLE. Un doble enlace
        # es más corto, y un triple más todavía: sin corregirlo, el N≡N salía a
        # 142 pm cuando mide 110, y el modelo dejaba de ser preciso justo en las
        # moléculas donde el orden de enlace es lo interesante.
        dist = (rc + rl) * _ACORTA.get(max(1, min(_ENLACES.get(lig, 1), 3)), 1.0)
        atomos.append((lig, (d[0] * dist, d[1] * dist, d[2] * dist), rl))
    verts, caras, colores = [], [], []

    def _pegar(v, c, color):
        nonlocal verts, caras, colores
        base = len(verts)
        verts += v
        caras += [tuple(i + base for i in cara) for cara in c]
        colores += [color] * len(v)

    for sim, pos, r in atomos:
        _pegar(*_esfera(pos, r * 0.42, 14), _COLOR.get(sim, (0.55, 0.6, 0.7)))

    # Enlaces con su ORDEN: uno, dos o tres varillas paralelas. Un doble enlace
    # dibujado como uno simple no es un detalle estético: es el dato que dice
    # que el CO2 es lineal y rígido, y que el eteno no gira sobre su enlace.
    ordenes = []
    for (sim, pos, _r), orden in zip(atomos[1:], [_ENLACES.get(l, 1) for l in ligandos]):
        orden = max(1, min(int(orden), 3))
        ordenes.append((sim, orden))
        for desplazado in _separar(pos, orden):
            _pegar(*_cilindro(desplazado[0], desplazado[1], 0.075, 10),
                   (0.62, 0.72, 0.80))

    # Pares solitarios: los dominios que NO llevan ligando. Son los que doblan
    # el ángulo del agua a 104,5° y los que hacen básico al amoniaco, así que
    # verlos importa tanto como ver los enlaces.
    lobulos = dirs[:pares] if len(dirs) >= pares else []
    for d in lobulos:
        centro = (d[0] * rc * 1.45, d[1] * rc * 1.45, d[2] * rc * 1.45)
        _pegar(*_esfera(centro, rc * 0.30, 10), (0.45, 0.85, 1.00))
    out = carpeta or M.carpeta_salida(f"molecula-{formula}")
    obj = M.exportar_obj(verts, caras, os.path.join(out, "molecula.obj"), formula)
    stl = M.exportar_stl(verts, caras, os.path.join(out, "molecula.stl"), formula)
    datos = {"tipo": "3d", "vertices": verts, "caras": M._triangular(caras),
             "colores": colores, "titulo": f"{formula} · {g['forma']}"}
    html = M.visor_web(datos, os.path.join(out, "visor.html"), f"Molécula {formula}")
    mm = masa_molar(formula)
    pasos = list(g["pasos"])
    # Cada enlace, con su orden y su longitud: el dato concreto, no el dibujo.
    nombres_orden = {1: "simple", 2: "doble", 3: "triple"}
    for (sim, orden), (_s, pos, _r) in zip(ordenes, atomos[1:]):
        longitud = math.sqrt(sum(c * c for c in pos))
        pasos.append(f"Enlace {central}–{sim}: {nombres_orden.get(orden, 'múltiple')}"
                     f", longitud ≈ {longitud * 100:.0f} pm "
                     f"(suma de radios covalentes {_RADIO.get(central, 1.0):.2f} + "
                     f"{_RADIO.get(sim, 0.9):.2f} Å)")
    if pares:
        pasos.append(f"{pares} par{'es' if pares > 1 else ''} solitario"
                     f"{'s' if pares > 1 else ''} dibujado"
                     f"{'s' if pares > 1 else ''} como lóbulos azules: "
                     "ocupan más sitio que un enlace y por eso cierran el ángulo.")
    if mm.get("ok"):
        pasos.append(f"Masa molar M = {mm['masa_molar']:.4f} g/mol")
    pasos.append(f"Modelo 3D con {len(atomos)} átomos guardado en {out}")
    if abrir_visor:
        M.abrir(html, log=log)
    return {"ok": True, "obj": obj, "stl": stl, "html": html, "carpeta": out,
            "forma": g["forma"], "pasos": pasos, "datos": datos}


def tabla_periodica_grafica(colorear: str = "categoria", carpeta: str = "",
                            log=print) -> dict:
    """Dibuja la tabla periódica entera, coloreada por familia o por una propiedad."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Rectangle
    familias = {"no metal": "#7bed9f", "gas noble": "#c56cf0",
                "metal alcalino": "#ff6b81", "alcalinotérreo": "#ff9f43",
                "metal de transición": "#2ec6ff", "metal": "#4ecdc4",
                "metaloide": "#ffd166", "halógeno": "#f78fb3",
                "lantánido": "#8e9bff", "actínido": "#ff7f50"}
    fig, ax = plt.subplots(figsize=(19, 10.5), dpi=150, facecolor=M._FONDO)
    ax.set_facecolor(M._FONDO)
    ens = [e["electronegatividad"] for e in TABLA.values() if e["electronegatividad"]]
    cmap = plt.cm.turbo
    for e in TABLA.values():
        z, grupo, periodo = e["Z"], e["grupo"], e["periodo"]
        if 57 <= z <= 71:                      # lantánidos, fila aparte
            col, fila = z - 57 + 3, 9
        elif 89 <= z <= 103:                   # actínidos
            col, fila = z - 89 + 3, 10
        else:
            col, fila = grupo, periodo
        x, y = col, -fila
        if colorear == "electronegatividad" and e["electronegatividad"]:
            c = cmap((e["electronegatividad"] - min(ens)) / (max(ens) - min(ens)))
        elif colorear == "masa":
            c = cmap(e["masa"] / 300)
        else:
            c = familias.get(e["categoria"], "#5f8ea3")
        ax.add_patch(Rectangle((x - 0.46, y - 0.46), 0.92, 0.92, facecolor=c,
                               edgecolor=M._FONDO, linewidth=1.4, alpha=0.93))
        ax.text(x - 0.40, y + 0.30, str(z), fontsize=6.5, color="#04060a")
        ax.text(x, y + 0.02, e["simbolo"], fontsize=15, color="#04060a",
                ha="center", va="center", fontweight="bold")
        ax.text(x, y - 0.30, f"{e['masa']:.5g}", fontsize=5.6, color="#04060a",
                ha="center")
    ax.text(2.5, -9, "lantánidos", color=M._TINTA, fontsize=9, ha="right", va="center")
    ax.text(2.5, -10, "actínidos", color=M._TINTA, fontsize=9, ha="right", va="center")
    ax.set_xlim(0.2, 19)
    ax.set_ylim(-12.2, 0.6)
    ax.axis("off")
    ax.set_title("TABLA PERIÓDICA DE LOS ELEMENTOS  ·  JARVIS",
                 color=M._ACENTO[0], fontsize=19, pad=16, fontweight="bold")
    if colorear == "categoria":
        # La leyenda va DEBAJO: arriba pisaba la casilla del hidrógeno.
        for i, (nombre, c) in enumerate(familias.items()):
            ax.add_patch(Rectangle((1.2 + i * 1.75, -11.75), 0.34, 0.34, facecolor=c))
            ax.text(1.65 + i * 1.75, -11.58, nombre, color=M._TINTA, fontsize=7.6,
                    va="center")
    fig.tight_layout()
    out = carpeta or M.carpeta_salida("tabla-periodica")
    png = os.path.join(out, "tabla_periodica.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    return {"ok": True, "png": png, "carpeta": out,
            "pasos": [f"Tabla completa: {len(TABLA)} elementos, coloreada por "
                      f"{colorear}."]}
