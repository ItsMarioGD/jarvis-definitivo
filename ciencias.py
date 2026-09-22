#!/usr/bin/env python3
"""
ciencias.py - El profesor: entiende el problema hablado y lo resuelve
=====================================================================
Es la puerta de entrada. El señor DICTA un problema de matemáticas, física o
química y este módulo:

    1. Entiende qué pide (con el cerebro si está disponible; si no, con reglas
       que funcionan sin internet).
    2. Llama al módulo que toca: `matematica`, `fisica` o `quimica`.
    3. Arma la respuesta: una frase corta para la voz y el desarrollo completo
       paso a paso para leerlo.
    4. Si hay que graficar, dibuja la lámina, escribe el visor interactivo,
       exporta la malla 3D cuando procede y ABRE el resultado.

Órdenes que reconoce (ejemplos reales):
    «resuélveme equis al cuadrado menos cinco equis más seis igual a cero»
    «derívame equis cubo por seno de equis y grafícalo»
    «grafícame en tres dimensiones zeta igual a seno de equis por coseno de ye»
    «una pelota sale a veinticinco metros por segundo con cuarenta grados,
      ¿qué alcance tiene? y dibújamelo en 3D»
    «balancea Fe más O2 da Fe2O3»
    «hazme el modelo 3D de la molécula de agua»
    «enséñame la tabla periódica»
"""
import json
import math
import os
import re

import matematica as M

_MATERIAS = ("matematica", "fisica", "quimica")

# Palabras que delatan que la frase es un problema de ciencias.
_DISPARA = re.compile(
    # Ojo con los enclíticos: «resuélveme», «derívamelo», «grafícamelo». Sin el
    # \w* final, el \b del cierre no casa y la frase se escapa del enrutador.
    r"\b(resu[eé]lv\w*|resolver|calcul\w*|der[ií]v\w*|integra\w*|"
    r"l[ií]mite|ecuaci[oó]n|inecuaci[oó]n|sistema\s+de\s+ecuaciones|matriz|"
    r"determinante|autovalor|factoriza\w*|simplifica\w*|polinomio|funci[oó]n|"
    r"gr[aá][fp][ií]c\w*|dibuja\w*\s+(?:la\s+)?(?:gr[aá]fica|funci[oó]n)|"
    r"traza\w*\s+la\s+gr[aá]fica|superficie|par[aá]bola|hip[eé]rbola|elipse|"
    r"seno|coseno|tangente|logaritmo|exponencial|ra[ií]z\s+cuadrada|"
    r"estad[ií]stic|media\s+aritm|desviaci[oó]n\s+t[ií]pica|varianza|probabilidad|"
    r"tiro\s+parab[oó]lico|proyectil|ca[ií]da\s+libre|velocidad|aceleraci[oó]n|"
    r"fuerza\s+neta|energ[ií]a\s+(?:cin[eé]tica|potencial|mec[aá]nica)|"
    r"momento\s+(?:lineal|angular|de\s+inercia)|ley\s+de\s+(?:newton|hooke|ohm|"
    r"coulomb|snell|faraday|boyle|gay|charles)|p[eé]ndulo|oscilador|"
    r"circuito|condensador|resistencia\s+de|campo\s+(?:el[eé]ctrico|magn[eé]tico)|"
    r"relatividad|fot[oó]n|de\s+broglie|onda\s+(?:viajera|estacionaria)|efecto\s+doppler|"
    r"masa\s+molar|peso\s+molecular|balancea|ajusta\s+la\s+(?:ecuaci[oó]n|reacci[oó]n)|"
    r"estequiometr|reactivo\s+limitante|mol(?:es|aridad)?\b|disoluci[oó]n|diluci[oó]n|"
    r"\bph\b|p\s*h\s+de|valoraci[oó]n|titulaci[oó]n|cin[eé]tica\s+qu[ií]mica|arrhenius|"
    r"equilibrio\s+qu[ií]mico|entalp[ií]a|ley\s+de\s+hess|pila|nernst|electroqu[ií]mic|"
    r"tabla\s+peri[oó]dica|configuraci[oó]n\s+electr[oó]nica|geometr[ií]a\s+molecular|"
    r"mol[eé]cula\s+de|elemento\s+qu[ií]mico|n[uú]mero\s+at[oó]mico|"
    # Simulaciones: «simula», «anímame», «quiero verlo moverse».
    r"simula\w*|simulaci[oó]n|an[ií]ma\w*|atractor|efecto\s+mariposa|"
    r"[oó]rbita\w*|ciclotr[oó]n|onda\s+estacionaria)\b",
    re.IGNORECASE)

_PIDE_GRAFICA = re.compile(
    r"\b(gr[aá][fp][ií]c\w*|dib[uú]ja\w*|traza\w*|repres[eé]nta\w*|mu[eé]stra\w*\s+"
    r"(?:la\s+)?(?:gr[aá]fica|curva)|pl[oó]tea\w*|enseñame\s+la\s+gr[aá]fica)\b",
    re.IGNORECASE)
_PIDE_3D = re.compile(r"(\b3\s*-?\s*d\b|tres\s+dimensiones|tridimensional|"
                      r"superficie|holograma|en\s+relieve|volumen)", re.IGNORECASE)
_PIDE_HOLOGRAMA = re.compile(r"\bholograma\b", re.IGNORECASE)


def es_problema(texto: str) -> bool:
    """¿Esta frase es un problema de ciencias? Se usa para enrutar."""
    t = (texto or "").strip()
    if not t or len(t) > 1200:
        return False
    if _DISPARA.search(t):
        return True
    # «cuánto es 15 % de 240», «2x + 3 = 11»: aritmética descarada.
    if re.search(r"\d\s*[+\-*/^=]\s*\d", t) and re.search(
            r"\b(cu[aá]nto|resultado|calcula|es)\b", t, re.I):
        return True
    # Lo mismo dictado: «cuánto es dos mil trescientos entre cinco». Se exige
    # que al traducir las palabras a cifras quede una cuenta de verdad, para no
    # tragarse un «cuánto es la temperatura de fuera».
    if re.search(r"\bcu[aá]nto\s+(?:es|vale|da|suman?|hacen?)\b", t, re.I):
        cuenta = M.normalizar_expresion(t)
        if re.search(r"\d", cuenta) and re.search(r"[+\-*/=]|\*\*", cuenta):
            return True
    return bool(re.search(r"^[\d\s+\-*/^().x y=]+$", t) and re.search(r"[+\-*/^=]", t))


# ── el cerebro convierte la frase en un plan ───────────────────────────────
_PROMPT = """Eres el analizador de enunciados de un asistente científico.
Traduce el problema del usuario a UN JSON, sin texto alrededor, sin markdown.

Esquema:
{
 "materia": "matematica" | "fisica" | "quimica",
 "accion": una de [
   "ecuacion","sistema","derivar","integrar","limite","serie","matriz","edo",
   "estadistica","simplificar","evaluar",
   "grafica2d","superficie3d","implicita3d","parametrica2d","parametrica3d",
   "curva3d","campo2d","campo3d","polar","datos",
   "formula_fisica","tiro","rectilineo","oscilador","onda","campo_electrico",
   "circuito_rc","diagrama_pv","lente","relatividad",
   "masa_molar","balancear","estequiometria","ph","valoracion","cinetica",
   "arrhenius","equilibrio","hess","pila","molecula","elemento",
   "tabla_periodica","configuracion","simular"],
 "simulacion": "con accion=simular: tiro|orbita|pendulo|muelle|carga|lorenz|cuerda|membrana|molecula|ecuaciones",
 "parametros": "con accion=simular: diccionario de parametros, p.ej. {\"l1\":1,\"l2\":0.8}",
 "expresion": "la expresion en notacion Python/sympy, con ** para potencias",
 "expresiones": ["varias, si hay varias curvas o ecuaciones"],
 "variable": "x",
 "rango": [min, max],
 "rango_y": [min, max],
 "limites": [a, b],
 "punto": "0",
 "orden": 1,
 "formula": "clave del banco de fisica si aplica",
 "datos": {"simbolo": numero},
 "incognita": "simbolo a despejar",
 "graficar": true/false,
 "dim": 2 o 3,
 "titulo": "titulo corto"
}
Usa solo las claves que hagan falta. Los numeros van como numeros.
Angulos en grados si el enunciado los da en grados.
Si el usuario pide ver la grafica, "graficar": true. Si dice 3D o superficie,
"dim": 3.

Enunciado: """


def plan(core, enunciado: str, log=print) -> dict:
    """Plan estructurado del enunciado. Primero el cerebro, luego las reglas."""
    base = plan_por_reglas(enunciado)
    # Lo aprendido en el entrenamiento manda sobre las reglas: si esta forma de
    # hablar ya se corrigió una vez, no se vuelve a fallar igual.
    try:
        import entrenar_ciencias
        ap = entrenar_ciencias.buscar(enunciado)
        if ap and ap.get("accion"):
            base = dict(base, accion=ap["accion"], _fuente="aprendido")
            base.update(ap.get("extra") or {})
    except Exception as e:
        log(f"[CIENCIAS] memoria de frases no disponible: {str(e)[:70]}")
    if core is None:
        return base
    try:
        # Por `pensar` y no a mano: con 700 tokens y un modelo que razona
        # —qwen3:8b lo hace— el plan volvía VACÍO, se caía a las reglas y nadie
        # entendía por qué el cerebro «no ayudaba» en los enunciados largos.
        import pensar
        p = pensar.estructura(core, _PROMPT, enunciado, tope=1800, log=log)
        if not isinstance(p, dict) or not p.get("accion"):
            return base
        # Las reglas mandan en lo que ellas ven claro (gráfica y 3D del texto).
        p.setdefault("materia", base.get("materia", "matematica"))
        if base.get("graficar"):
            p["graficar"] = True
        if base.get("dim") == 3:
            p["dim"] = 3
        p["_fuente"] = "cerebro"
        return p
    except Exception as e:
        log(f"[CIENCIAS] el cerebro no pudo planear ({str(e)[:90]}); voy con reglas")
        return base


def _materia(t: str) -> str:
    quim = len(re.findall(r"\b(mol|moles|molar|balance|reacci[oó]n|[aá]cido|base|"
                          r"ph|disoluci[oó]n|entalp[ií]a|elemento|at[oó]mic|"
                          r"mol[eé]cula|peri[oó]dica|estequiometr|gramos?\s+de|"
                          r"reactivo|producto|valencia|enlace)\b", t, re.I))
    fis = len(re.findall(r"\b(velocidad|aceleraci[oó]n|fuerza|energ[ií]a|masa\s+de|"
                         r"movimiento|proyectil|ca[ií]da|cae|caer|p[eé]ndulo|onda|"
                         r"circuito|corriente|voltaje|tensi[oó]n|campo|calor|"
                         r"temperatura|presi[oó]n|trabajo|potencia|newton|julios?|"
                         r"vatios?|metros?\s+por\s+segundo|kil[oó]gramos?|reposo|"
                         r"altura|suelo|frena\w*|choca\w*|recorre|tarda|gravedad|"
                         r"muelle|resorte|oscila\w*|lanza\w*|empuja\w*|rozamiento)\b",
                         t, re.I))
    # Una unidad del SI pegada a un número es la pista más fuerte de todas.
    fis += 2 * len(re.findall(
        r"\d\s*(?:m/s2|m/s²|m/s|km/h|m³|m3|m²|m2|kg|N\b|J\b|W\b|V\b|A\b|Hz|K\b|Pa|"
        r"[ºº°]C|newtons?|julios?|vatios?|voltios?|amperios?|ohmios?|pascales?|"
        r"metros?|segundos?|kil[oó]gramos?|grados)\b", t, re.I))
    if quim > fis and quim:
        return "quimica"
    if fis:
        return "fisica"
    return "matematica"


def _numeros(t: str) -> list:
    """Números del enunciado. El «3D» de «dibújamelo en 3D» NO es un dato."""
    limpio = re.sub(r"\b(?:en\s+)?3\s*-?\s*d\b", " ", t.lower())
    limpio = re.sub(r"\b(?:dos|tres)\s+dimensiones\b", " ", limpio)
    return [float(x.replace(",", ".")) for x in
            re.findall(r"-?\d+(?:[.,]\d+)?", M._palabras_a_numeros(limpio))]


def _expresion_del_texto(t: str) -> str:
    """Saca la parte matemática de la frase quitando el verbo de la orden."""
    s = t
    s = re.sub(r"^\s*(?:por\s+favor\s*,?\s*)?(?:jarvis|ultron)\s*,?\s*", "", s, flags=re.I)
    s = re.sub(r"^\s*[¿¡]?\s*(?:cu[aá]l\s+es|cu[aá]nto\s+(?:es|vale|da)|"
               r"qu[eé]\s+(?:es|vale|da))\b", " ", s, flags=re.I)
    s = re.sub(r"\b(res[uú][eé]lve\w*|calcul[ae]\w*|halla\w*|obt[eé]n\w*|dame|"
               r"determin[ae]\w*|averigua\w*|indica\w*|plantea\w*|comprueba\w*|"
               r"dime|necesito|quiero|h[aá]zme|hazme|haz|encuentra\w*|"
               r"(?:la\s+)?(?:primera|segunda|tercera|cuarta)\s+derivada(?:\s+de)?|"
               r"der[ií]v[ae]\w*|derivada\s+de|"
               r"(?:la\s+)?serie\s+de\s+taylor(?:\s+de)?|maclaurin(?:\s+de)?|"
               r"(?:el\s+)?desarrollo\s+de\s+taylor(?:\s+de)?|"
               r"(?:la\s+)?ecuaci[oó]n\s+diferencial|(?:el\s+)?sistema(?:\s+de\s+ecuaciones)?|"
               r"integra\w*|simplifica\w*|factoriza\w*|gr[aá][fp][ií]c\w*|"
               r"dib[uú]ja\w*|traza\w*|repres[eé]nta\w*|mu[eé]stra\w*|pl[oó]tea\w*|"
               r"ens[eé][ñn]a\w*|el\s+l[ií]mite\s+de|la\s+derivada\s+de|"
               r"la\s+integral\s+de|la\s+funci[oó]n|la\s+ecuaci[oó]n|"
               r"la\s+gr[aá]fica\s+de|en\s+3\s*-?\s*d|en\s+tres\s+dimensiones|"
               r"tridimensional|por\s+favor|me\b)\b", " ", s, flags=re.I)
    s = re.sub(r"\b(respecto\s+a\s+\w+|con\s+respecto\s+a\s+\w+)\b", " ", s, flags=re.I)
    s = re.sub(r"^\s*(?:de|del|la|el|los|las|un|una)\s+", "", s, flags=re.I)
    # Restos de la conjunción con la que se encadenaba la orden de dibujar:
    # «derívame x**3 y grafícalo» deja un « y » colgando al final. Ojo: en
    # «coseno de y» esa misma letra es la VARIABLE, así que no se toca cuando
    # detrás de ella hay una preposición o un operador esperando argumento.
    s = re.sub(r"\s*,\s*$", "", s.strip())
    m = re.search(r"^(.*?)\s+(?:y|e)$", s.strip(), flags=re.I)
    if m and not re.search(r"(?:\b(?:de|por|m[aá]s|menos|entre|sobre|con|a)|"
                           r"[+\-*/^(,])\s*$", m.group(1), flags=re.I):
        s = m.group(1)
    s = s.strip(" ,.;:¿?¡!")
    return s


# ── simulaciones: de la frase al sistema y sus parámetros ──────────────────
_PIDE_SIMULAR = re.compile(
    r"\b(simula\w*|simulaci[oó]n|anima\w*|animaci[oó]n|en\s+movimiento|"
    r"mu[eé]ve\w*|evoluci[oó]n\s+de|ver\s+c[oó]mo\s+se\s+mueve)\b", re.I)

# Palabra que delata cada sistema del catálogo.
_SISTEMAS_SIM = (
    ("lorenz", r"\blorenz\b|efecto\s+mariposa|atractor|caos\s+determinista"),
    ("orbita", r"\b[oó]rbit\w*|planeta|sistema\s+solar|kepler|gravitaci|"
               r"tierra\s+y\s+la\s+luna|sol\s+y\s+la\s+tierra"),
    ("pendulo", r"\bp[eé]ndulo\b"),
    ("carga", r"carga\s+(el[eé]ctrica|en\s+un\s+campo)|lorentz|ciclotr[oó]n|"
              r"part[ií]cula\s+cargada"),
    ("membrana", r"\bmembrana\b|\btambor\b|chladni|ondas?\s+en\s+(2|dos)\s*d"),
    ("cuerda", r"\bcuerda\b|onda\s+estacionaria|arm[oó]nico\s+de\s+una"),
    ("muelle", r"\bmuelle\b|\bresorte\b|masa[- ]muelle|oscilador|resonancia|"
               r"amortigua\w*"),
    ("molecula", r"\bmol[eé]cula\b|vibraci[oó]n\s+molecular|modo\s+normal"),
    ("tiro", r"tiro\s+parab|proyectil|trayectoria|lanz\w*|ca[ñn][oó]n|"
             r"rozamiento\s+del\s+aire"),
)


# Cosas que sólo tienen sentido animadas: no hace falta decir «simula».
_SIMULA_SOLO = re.compile(
    r"\blorenz\b|efecto\s+mariposa|atractor|ciclotr[oó]n|p[eé]ndulo\s+doble", re.I)


def _plan_simulacion(texto: str, bajo: str, base: dict):
    """¿Pide ver algo MOVERSE? Entonces no es una gráfica: es una simulación."""
    if not (_PIDE_SIMULAR.search(bajo) or _SIMULA_SOLO.search(bajo)):
        return None
    nums = _numeros(bajo)

    def _num(i, por_defecto):
        """Los números del enunciado por posición, con valor de reserva."""
        return float(nums[i]) if len(nums) > i else por_defecto

    # Ecuaciones dictadas: «simula x'' = -9.8 - 0.1*x'»
    if re.search(r"[A-Za-z]\s*(''|\"|´´)\s*=", texto) or \
            re.search(r"\bd[A-Za-z]\s*/\s*dt\s*=", texto):
        trozos = [x.strip() for x in re.split(r"[;\n]|\by\b(?=\s*[A-Za-z]\w*\s*')",
                                              texto) if "=" in x]
        limpias = []
        for x in trozos:
            m = re.search(r"([A-Za-z]\w*\s*(?:''|\"|´´|'|´)?\s*=\s*.+)$", x)
            if m:
                limpias.append(m.group(1).strip(" .?!"))
        if limpias:
            return {**base, "accion": "simular", "simulacion": "ecuaciones",
                    "parametros": {"ecuaciones": limpias}}

    for nombre, patron in _SISTEMAS_SIM:
        if not re.search(patron, bajo, re.I):
            continue
        params = {}
        if nombre == "pendulo":
            if re.search(r"\bdoble\b", bajo):
                params = {"l1": _num(0, 1.0), "l2": _num(1, 0.8)}
            else:
                params = {"l1": _num(0, 1.0), "l2": 0.0}
        elif nombre == "orbita":
            if re.search(r"luna", bajo):
                params = {"sistema": "tierra-luna"}
            elif re.search(r"sistema\s+solar|planeta|interior", bajo):
                params = {"sistema": "interior"}
            else:
                params = {"sistema": "sol-tierra"}
        elif nombre == "tiro":
            params = {"v0": _num(0, 25.0), "angulo": _num(1, 45.0)}
            if re.search(r"rozamiento|aire|resistencia", bajo):
                params["k_roce"] = 0.12
        elif nombre == "muelle":
            params = {"k": _num(0, 10.0)}
            if re.search(r"resonancia", bajo):
                params.update({"F": 1.0, "w": math.sqrt(params["k"]), "c": 0.15})
        elif nombre == "molecula":
            # Primero el nombre en castellano («agua», «amoniaco»), que es como
            # se dicta; la fórmula escrita sólo si no hay nombre conocido.
            comun = _busca_formula_comun(texto)
            m = re.search(r"\b((?:[A-Z][a-z]?\d*){1,6})\b", texto)
            params = {"formula": comun or (m.group(1) if m else "H2O")}
            if re.search(r"flexi|tijera", bajo):
                params["modo"] = "flexion"
            elif re.search(r"asim[eé]tric", bajo):
                params["modo"] = "asimetrico"
        elif nombre == "membrana" and len(nums) >= 2:
            params = {"modo": (int(nums[0]), int(nums[1]))}
        return {**base, "accion": "simular", "simulacion": nombre,
                "parametros": params}

    # Pide simular pero no dice de qué: que lo diga el catálogo.
    return {**base, "accion": "simular", "simulacion": "", "parametros": {}}


def plan_por_reglas(enunciado: str) -> dict:
    """Analizador sin LLM. Cubre los casos que se dicen a diario."""
    t = (enunciado or "").strip()
    bajo = t.lower()
    # El enunciado entero y todos sus números viajan SIEMPRE en el plan: así
    # cualquier acción (incluida una aprendida que no venía de esta rama)
    # tiene con qué trabajar.
    p = {"materia": _materia(bajo), "graficar": bool(_PIDE_GRAFICA.search(bajo)),
         "dim": 3 if _PIDE_3D.search(bajo) else 2, "_fuente": "reglas",
         "enunciado": t, "datos": {"nums": _numeros(bajo)}}
    if _PIDE_HOLOGRAMA.search(bajo):
        p["holograma"] = True

    # ── simulaciones: van PRIMERO porque «simula la órbita» también casa con
    # las reglas de física, y lo que el señor ha pedido es verlo moverse ──
    sim = _plan_simulacion(t, bajo, p)
    if sim:
        return sim

    # ── química ──
    if re.search(r"\btabla\s+peri[oó]dica\b", bajo):
        return {**p, "accion": "tabla_periodica"}
    if re.search(r"\bconfiguraci[oó]n\s+electr[oó]nica\b", bajo):
        m = re.search(r"de(?:l)?\s+([A-Za-zÁ-ú]+)\s*$", t.strip(" .?!"))
        return {**p, "accion": "configuracion", "expresion": m.group(1) if m else ""}
    if re.search(r"\b(mol[eé]cula|geometr[ií]a\s+molecular|forma\s+de\s+la\s+mol)", bajo):
        m = re.search(r"\b([A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)+|[A-Z][a-z]?\d+)\b", t)
        nombre = _busca_formula_comun(bajo)
        return {**p, "accion": "molecula",
                "expresion": nombre or (m.group(1) if m else "H2O")}
    if re.search(r"\b(balancea|ajusta|equilibra)\b", bajo) or "->" in t or "→" in t:
        limpio = re.sub(r"^.*?\b(?:balancea\w*|ajusta\w*|equilibra\w*)\b\s*:?\s*",
                        "", t, flags=re.I)
        m = re.search(r"([A-Za-z0-9()·\s\+]+(?:->|→|=)[A-Za-z0-9()·\s\+]+)", limpio)
        if m:
            return {**p, "accion": "balancear", "expresion": m.group(1).strip()}
    if re.search(r"\b(masa\s+molar|peso\s+molecular|masa\s+molecular)\b", bajo):
        m = re.search(r"\b((?:[A-Z][a-z]?\d*|\([A-Za-z0-9]+\)\d*|·)+)\b", t)
        return {**p, "accion": "masa_molar", "expresion": m.group(1) if m else ""}
    if re.search(r"\bp\s*h\b", bajo):
        nums = _numeros(bajo)
        if re.search(r"valoraci[oó]n|titulaci[oó]n|curva", bajo):
            return {**p, "accion": "valoracion", "datos": {"nums": nums}}
        return {**p, "accion": "ph", "datos": {"nums": nums},
                "expresion": "debil" if "débil" in bajo or "debil" in bajo else "fuerte"}
    if re.search(r"\b(elemento|n[uú]mero\s+at[oó]mico|s[ií]mbolo\s+de)\b", bajo):
        m = re.search(r"\b(?:del?|sobre)\s+([A-Za-zÁ-ú]{2,14})\b", t)
        return {**p, "accion": "elemento", "expresion": m.group(1) if m else t.split()[-1]}

    # ── física ──
    if re.search(r"\b(tiro\s+parab[oó]lico|proyectil|se\s+lanza|se\s+dispara|"
                 r"lanza\w*\s+(?:una|un|el|la))\b", bajo) and re.search(r"grados?|[°]", bajo):
        nums = _numeros(bajo)
        return {**p, "accion": "tiro", "datos": {"nums": nums}}
    # «periodo de un péndulo de 1 m» es despejar una fórmula, no simular un
    # oscilador entero: solo se va al simulador si piden el movimiento.
    if re.search(r"\bp[eé]ndulo\b", bajo) and not re.search(
            r"\b(simula|dibuja|gr[aá]fic|energ[ií]as|espacio\s+de\s+fases)", bajo):
        return {**p, "accion": "formula_fisica", "formula": "periodo_pendulo"}
    if re.search(r"\b(p[eé]ndulo|oscilad\w+|movimiento\s+arm[oó]nico|muelle\s+de|"
                 r"resorte)\b", bajo):
        return {**p, "accion": "oscilador", "datos": {"nums": _numeros(bajo)}}
    if re.search(r"\bonda\b", bajo) and re.search(r"\b(viajera|propaga|longitud\s+de\s+onda|"
                                                  r"frecuencia)\b", bajo):
        return {**p, "accion": "onda", "datos": {"nums": _numeros(bajo)}}
    if re.search(r"\bcircuito\s+rc\b|carga\s+del?\s+condensador|descarga\s+del?\s+"
                 r"condensador", bajo):
        return {**p, "accion": "circuito_rc", "datos": {"nums": _numeros(bajo)}}
    if re.search(r"\bcampo\s+el[eé]ctrico\b|\bcargas?\s+puntuales?\b", bajo):
        return {**p, "accion": "campo_electrico", "datos": {"nums": _numeros(bajo)}}
    if re.search(r"\brelativ|dilataci[oó]n\s+del\s+tiempo|factor\s+de\s+lorentz", bajo):
        return {**p, "accion": "relatividad", "datos": {"nums": _numeros(bajo)}}
    if re.search(r"\blente|espejo\s+(?:c[oó]ncavo|convexo)|distancia\s+focal", bajo):
        return {**p, "accion": "lente", "datos": {"nums": _numeros(bajo)}}
    if p["materia"] == "fisica":
        import fisica as F
        claves = F.buscar_formula(bajo)
        if claves:
            return {**p, "accion": "formula_fisica", "formula": claves[0],
                    "enunciado": t}
        # Nadie dice «usa la fórmula de la velocidad»: se dan los datos y ya.
        # Que la elija el propio banco por las unidades del enunciado.
        ley = F.elegir_ley(t, log=lambda *a: None)
        if ley:
            return {**p, "accion": "formula_fisica", "formula": ley}
        if re.search(r"\b(movimiento\s+rectil[ií]neo|mru|mrua|velocidad\s+constante|"
                     r"acelera\w*\s+a)\b", bajo):
            return {**p, "accion": "rectilineo", "datos": {"nums": _numeros(bajo)}}

    # ── matemáticas ──
    expr = _expresion_del_texto(t)
    # Si quitar verbos no ha dejado matemática limpia, es que el encargo trae
    # prosa alrededor (un enunciado de examen, una tanda de requisitos).
    # Entonces se va a BUSCAR la expresión dentro del texto.
    # «Explícame qué es una derivada»: hay palabra clave de ciencias pero NO hay
    # nada que calcular. Se corta aquí y contesta el cerebro. El rescate de la
    # expresión va al FINAL, porque las ramas con verbo propio (límite,
    # estadística, sistema, EDO) ya saben recortar su enunciado solas.
    if not _hay_matematica(expr) and not _extraer_matematica(t):
        return {**p, "accion": "sin_calculo", "expresion": expr}
    if re.search(r"\bmatriz|determinante|inversa\s+de|autovalor", bajo):
        return {**p, "accion": "matriz", "expresion": expr}
    if re.search(r"\b(media|mediana|moda|desviaci[oó]n|varianza|estad[ií]stic|"
                 r"promedio)\b", bajo):
        return {**p, "accion": "estadistica", "datos": {"nums": _numeros(bajo)}}
    if re.search(r"\bl[ií]mite\b", bajo):
        m = re.search(r"(?:cuando|si)\s+(\w+)\s+(?:tiende|se\s+acerca)\s+a\s+"
                      r"([\w\-\.]+|infinito|menos\s+infinito)", bajo)
        punto = "oo"
        var = "x"
        if m:
            var = m.group(1)
            punto = m.group(2).replace("infinito", "oo").replace("menos oo", "-oo")
        expr = re.split(r"\bcuando\b|\bsi\b", expr, 1)[0]
        return {**p, "accion": "limite", "expresion": expr, "variable": var,
                "punto": punto}
    if re.search(r"\bder[ií]v", bajo):
        orden = 2 if re.search(r"segunda\s+derivada|derivada\s+segunda", bajo) else \
                3 if re.search(r"tercera\s+derivada", bajo) else 1
        m = re.search(r"respecto\s+a\s+(\w)", bajo)
        return {**p, "accion": "derivar", "expresion": expr, "orden": orden,
                "variable": m.group(1) if m else ""}
    if re.search(r"\bintegra", bajo):
        # Los límites se buscan DENTRO de la expresión ya limpia: buscarlos en
        # la frase entera daba índices que no sirven para recortarla.
        m = re.search(r"\s+(?:de|desde|entre)\s+(-?[\w\.]+)\s+(?:a|hasta|y)\s+"
                      r"(-?[\w\.]+)\s*$", expr, re.I)
        lim = [m.group(1), m.group(2)] if m else None
        if m:
            expr = expr[:m.start()].strip() or expr
        return {**p, "accion": "integrar", "expresion": expr, "limites": lim}
    if re.search(r"\bserie\s+de\s+taylor|desarrollo\s+de\s+taylor|maclaurin", bajo):
        return {**p, "accion": "serie", "expresion": expr}
    if re.search(r"\becuaci[oó]n\s+diferencial|\bedo\b|y\s*''|y\s*'", bajo):
        return {**p, "accion": "edo", "expresion": expr}
    if re.search(r"\bsistema\b", bajo) or expr.count("=") > 1:
        partes = [s for s in re.split(r"[;\n]|,(?=[^=]*=)", expr) if "=" in s]
        return {**p, "accion": "sistema", "expresiones": partes or [expr]}
    # Aquí ya no queda ninguna rama con limpieza propia: si lo que hay sigue
    # siendo prosa, se va a BUSCAR la expresión dentro del encargo. Es lo que
    # salva los enunciados largos de examen con su lista de requisitos.
    if _es_prosa_pura(expr):
        rescatada = _extraer_matematica(t)
        if rescatada:
            expr = rescatada
    # Si lo que hay es una IGUALDAD, es una ecuación y punto: va antes que
    # «simplifica», que en un encargo largo aparece como un requisito más
    # («…3. Encuentra y simplifica los dos valores de x») y desviaba la orden.
    # «igual a cero» solo se convierte en «=» al normalizar: hay que mirar ahí.
    try:
        normal = M.normalizar_expresion(expr)
    except Exception:
        normal = expr
    if "=" in expr or "=" in normal:
        return {**p, "accion": "ecuacion", "expresion": expr}
    if re.search(r"\b(simplifica|factoriza|desarrolla|expande)\b", bajo):
        return {**p, "accion": "simplificar", "expresion": expr}
    # Sin verbo claro: si pide gráfica es gráfica; si no, se simplifica/evalúa.
    if p["graficar"] or re.search(r"\bfunci[oó]n\b", bajo):
        if p["dim"] == 3 or re.search(r"\by\b.*\bx\b|f\s*\(\s*x\s*,\s*y\s*\)", expr):
            return {**p, "accion": "superficie3d", "expresion": expr, "dim": 3}
        return {**p, "accion": "grafica2d", "expresion": expr}
    # Si lo que queda es prosa y no hay ninguna expresión que rescatar, no hay
    # cálculo que hacer: se dice, y la frase sigue hasta el cerebro en vez de
    # intentar «simplificar» un párrafo entero y reventar.
    if _tiene_prosa(expr) and not _extraer_matematica(t):
        return {**p, "accion": "sin_calculo", "expresion": expr}
    return {**p, "accion": "simplificar", "expresion": expr}


def _normaliza(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


# ── sacar la matemática de dentro de un encargo largo ──────────────────────
# Un enunciado de verdad no viene solo: «Actúa como un tutor experto… resuelve
# 3x² - 5x - 2 = 0 … 1. Identifica los coeficientes…». Quitar verbos no basta;
# hay que ir a buscar el trozo que ES matemática y dejar la prosa fuera.
_FUNCIONES = ("sin", "cos", "tan", "sen", "log", "ln", "exp", "sqrt", "abs",
              "sinh", "cosh", "tanh", "asin", "acos", "atan", "pi")


def _ficha_matematica(tok: str) -> bool:
    if not tok:
        return False
    if tok.lower() in _FUNCIONES:
        return True
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?", tok):
        return True
    if re.fullmatch(r"[+\-*/^=<>]+", tok):
        return True
    if re.fullmatch(r"[()\[\]]", tok):
        return True
    # Variable con coeficiente pegado o subíndice: x, 3x, x2, 5x
    return bool(re.fullmatch(r"\d*[a-zA-Z]\d*", tok))


def _extraer_matematica(texto: str) -> str:
    """Devuelve el trozo del texto que es una expresión o ecuación, o ''."""
    t = texto or ""
    for k, v in M._SUPER.items():
        t = t.replace(k, "^" + v[-1])
    t = (t.replace("×", "*").replace("·", "*").replace("÷", "/")
          .replace("−", "-").replace("–", "-").replace("≤", "<=").replace("≥", ">="))
    t = re.sub(r"([+\-*/^=()\[\]<>])", r" \1 ", t)
    # La puntuación que cierra frase se separa: sin esto, «= 19,» dejaba fuera
    # el 19 y la ecuación se quedaba coja. Los decimales no se tocan porque el
    # punto de «3.14» no va seguido de espacio.
    t = re.sub(r"([,;:.])(\s|$)", r" \1\2", t)
    fichas = t.split()
    mejor, mejor_p = [], -1
    actual = []
    for f in fichas + [""]:
        if _ficha_matematica(f):
            actual.append(f)
            continue
        if actual:
            # Puntuación: manda tener «=», luego cuántos operadores y fichas.
            ops = sum(1 for x in actual if re.fullmatch(r"[+\-*/^]+", x))
            tiene_var = any(re.fullmatch(r"\d*[a-zA-Z]\d*", x) for x in actual)
            p = (60 if any("=" in x for x in actual) else 0) + ops * 8 \
                + len(actual) + (10 if tiene_var else 0)
            if ops >= 1 and len(actual) >= 3 and p > mejor_p:
                mejor, mejor_p = actual, p
            actual = []
    if not mejor:
        return ""
    # Un operador suelto en los bordes sobra («= 0 .» o «- 2»).
    while mejor and re.fullmatch(r"[+*/^=<>]+", mejor[-1]):
        mejor.pop()
    return " ".join(mejor).strip()


def _sympifica(expresion: str) -> bool:
    """¿Esto lo entiende sympy? Sirve para decidir si hay que ir a buscar mejor."""
    if not (expresion or "").strip():
        return False
    try:
        M.sympificar(expresion)
        return True
    except Exception:
        return False


# Nombres de varias letras que SÍ son magnitudes y no prosa.
_SIMBOLOS_LARGOS = {"theta", "alpha", "beta", "gamma", "delta", "omega", "lamda",
                    "lambda", "phi", "rho", "tau", "mu", "epsilon", "sigma",
                    "pi", "oo", "inf", "nan"}


def _hay_matematica(expresion: str) -> bool:
    """¿Queda algo que calcular, una vez traducido el dictado?

    Cifras, una llamada a función, o un operador entre dos operandos. Si no hay
    nada de eso, la frase es una pregunta de teoría y no un ejercicio.
    """
    try:
        n = M.normalizar_expresion(expresion)
    except Exception:
        n = expresion or ""
    if re.search(r"\d", n):
        return True
    if re.search(r"[A-Za-z_]\w*\s*\(", n):
        return True
    return bool(re.search(r"[A-Za-z)]\s*[+\-*/^]\s*[A-Za-z(]", n))


def _es_prosa_pura(expresion: str) -> bool:
    """Prosa que sigue siendo prosa DESPUÉS de traducir el dictado.

    Hay que normalizar antes de juzgar: «equis al cubo por seno de equis» está
    lleno de palabras, pero al traducirlo queda `x**3*sin(x)` y es matemática
    perfecta. Lo que no sobrevive a la traducción es una pregunta de verdad.
    """
    try:
        return _tiene_prosa(M.normalizar_expresion(expresion))
    except Exception:
        return _tiene_prosa(expresion)


def _tiene_prosa(expresion: str) -> bool:
    """¿Queda castellano dentro de lo que debería ser solo matemática?

    `_sympifica` no basta como criterio: sympy se traga «el valor de x en la
    ecuación» como un producto de símbolos y devuelve algo sin protestar. Lo
    que delata la prosa son las palabras largas que no son funciones.
    """
    for palabra in re.findall(r"[A-Za-zÁ-Úá-úñÑ]{3,}", expresion or ""):
        p = palabra.lower()
        if p not in _FUNCIONES and p not in _SIMBOLOS_LARGOS:
            return True
    return False


_INSTRUCTIVO = re.compile(
    r"(act[uú]a\s+como|haz\s+de\s+tutor|como\s+(?:un\s+)?(?:tutor|profesor|experto)|"
    r"paso\s+a\s+paso|expl[ií]ca\w*|just[ií]fic\w*|demuestra|razona|interpreta|"
    r"detalladamente|en\s+detalle|latex|requisitos?\s+de\s+respuesta|"
    r"significado\s+del?|por\s+qu[eé]|\n\s*\d[\.\)]|\d[\.\)]\s+[A-ZÁ-Ú])",
    re.IGNORECASE)


def es_instructivo(texto: str) -> bool:
    """¿El señor pide además una EXPLICACIÓN, no solo el resultado?"""
    t = texto or ""
    if _INSTRUCTIVO.search(t):
        return True
    return len(t.split()) > 35


def pide_latex(texto: str) -> bool:
    return bool(re.search(r"\blatex\b|\$\$|\\\\\(", texto or "", re.I))


_PROMPT_TUTOR = """Eres un tutor experto de matemáticas, física y química.
El alumno ha pedido lo siguiente:

--- ENCARGO ---
{encargo}
--- FIN DEL ENCARGO ---

Un motor de cálculo simbólico (sympy) YA ha resuelto el problema. Estos
resultados son EXACTOS y verificados. NO los recalcules, NO los contradigas y
NO cambies ningún número:

--- RESULTADOS VERIFICADOS ---
{desarrollo}
{bloque_latex}--- FIN DE LOS RESULTADOS ---

Escribe ahora la respuesta para el alumno:
- Responde a TODOS los puntos que pide el encargo, en su orden y numeración.
- Explica el porqué de cada paso, no solo el qué.
- Usa exclusivamente los valores verificados de arriba.
- {formato}
- En español, directo, sin presentarte ni decir que eres una IA.
Si algún punto del encargo no se puede contestar con los datos verificados,
dilo con claridad en vez de inventarlo."""


def explicar(core, enunciado: str, r: dict, log=print) -> str:
    """Convierte el cálculo exacto en la explicación de tutor que se ha pedido.

    El cálculo lo hace sympy y el cerebro solo REDACTA: así la explicación es
    didáctica sin arriesgar que el modelo se invente la aritmética, que es
    justo lo que hacen mal los modelos de lenguaje solos.
    """
    if core is None:
        return ""
    pasos = [s for s in (r.get("pasos") or []) if s]
    if not pasos and not r.get("titular"):
        return ""
    tex = r.get("latex") or []
    bloque = ("\nEn LaTeX:\n" + "\n".join(f"  {x}" for x in tex) + "\n") if tex else ""
    formato = ("Escribe las fórmulas en LaTeX, cada una en su propio bloque $$…$$."
               if pide_latex(enunciado) else
               "Escribe las fórmulas en texto llano, legibles en voz alta.")
    prompt = _PROMPT_TUTOR.format(
        encargo=enunciado.strip()[:1500],
        desarrollo="\n".join(f"  {s}" for s in ([r.get("titular", "")] + pasos))[:3000],
        bloque_latex=bloque, formato=formato)
    try:
        # El tutor redacta largo, así que es justo donde más duele quedarse
        # sin tokens a mitad de razonamiento y devolver la nada.
        import pensar
        return pensar.texto(core, "Eres un profesor que explica con claridad.",
                            prompt, tope=3000, temperatura=0.2, log=log)
    except Exception as e:
        log(f"[CIENCIAS] el tutor no pudo redactar ({str(e)[:90]}); va el desarrollo seco")
        return ""


# Moléculas que el señor puede nombrar en castellano.
_FORMULA_COMUN = {}
for _frase, _f in (("agua", "H2O"), ("amoniaco", "NH3"), ("amoníaco", "NH3"),
                   ("metano", "CH4"), ("dióxido de carbono", "CO2"),
                   ("monóxido de carbono", "CO"), ("sal", "NaCl"),
                   ("cloruro de sodio", "NaCl"), ("ácido sulfúrico", "H2SO4"),
                   ("ácido clorhídrico", "HCl"), ("ácido nítrico", "HNO3"),
                   ("glucosa", "C6H12O6"), ("etanol", "C2H5OH"),
                   ("benceno", "C6H6"), ("ozono", "O3"), ("peróxido", "H2O2"),
                   ("agua oxigenada", "H2O2"), ("sosa", "NaOH"),
                   ("hidróxido de sodio", "NaOH"), ("cal", "CaO"),
                   ("carbonato de calcio", "CaCO3"), ("propano", "C3H8"),
                   ("butano", "C4H10"), ("acetileno", "C2H2"),
                   ("hexafluoruro de azufre", "SF6"), ("trifluoruro de boro", "BF3")):
    _FORMULA_COMUN[_frase] = _f


def _busca_formula_comun(texto: str) -> str:
    t = _normaliza(texto)
    for frase, f in sorted(_FORMULA_COMUN.items(), key=lambda kv: -len(kv[0])):
        if frase in t:
            return f
    return ""


# ── ejecución del plan ─────────────────────────────────────────────────────
# Lo último que se calculó, para «y ahora enséñamelo en 3D» o «el holograma de eso».
ULTIMO = {"carpeta": "", "obj": "", "html": "", "png": "", "expresion": "",
          "materia": "", "accion": ""}


def _rango(p, clave="rango", por_defecto=(-10, 10)):
    r = p.get(clave)
    if isinstance(r, (list, tuple)) and len(r) == 2:
        try:
            return (float(r[0]), float(r[1]))
        except (TypeError, ValueError):
            pass
    return por_defecto


def _n(datos, i, por_defecto=None):
    nums = (datos or {}).get("nums") or []
    return nums[i] if len(nums) > i else por_defecto


def ejecutar(core, p: dict, log=print) -> dict:
    """Ejecuta un plan. Devuelve {titular, pasos, png, html, obj, stl, carpeta}."""
    import fisica as F
    import quimica as Q
    accion = p.get("accion", "simplificar")
    expr = (p.get("expresion") or "").strip()
    exprs = p.get("expresiones") or ([expr] if expr else [])
    var = p.get("variable") or ""
    datos = p.get("datos") or {}
    graficar = bool(p.get("graficar"))
    dim = int(p.get("dim") or 2)
    titulo = p.get("titulo") or ""
    r = {"titular": "", "pasos": [], "png": "", "html": "", "obj": "", "stl": "",
         "carpeta": "", "accion": accion}

    # ── simulación: lo único que se MUEVE ──
    if accion == "simular":
        import simulacion as SIM
        sistema = (p.get("simulacion") or "").strip().lower()
        if not sistema:
            r["titular"] = "¿Qué quiere que simule, señor?"
            r["pasos"] = ["Sé simular esto:"] + [
                f"  {k} — {d}" for k, (_f, d) in SIM.CATALOGO.items()]
            return r
        s = SIM.simular(sistema, p.get("parametros") or {},
                        abrir_visor=False, log=log)
        r["pasos"] = s.get("pasos") or s.get("notas") or []
        if not s.get("ok"):
            r["titular"] = "No pude montar esa simulación, señor."
            return r
        r.update({"html": s.get("html", ""), "carpeta": s.get("carpeta", "")})
        r["titular"] = f"Simulación lista, señor: {s['datos'].get('titulo', sistema)}."
        return r

    # ── matemáticas ──
    if accion == "ecuacion":
        s = M.resolver_ecuacion(expr, var)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        sols = s.get("soluciones") or []
        r["titular"] = ("La solución es " + ", ".join(M.bonito(x) for x in sols)
                        if sols else "Esa ecuación no tiene solución real.")
        if graficar or len(sols) > 0:
            izq, der = M.partir_ecuacion(expr)
            g = M.grafica_2d(izq - der, rango=_dominio_util(sols),
                             titulo=titulo or "Solución gráfica", variable=str(
                                 s.get("variable") or "x"))
            r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
    elif accion == "sistema":
        s = M.resolver_sistema(exprs)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        sol = s.get("soluciones") or []
        r["titular"] = ("Solución: " + ", ".join(f"{k} = {M.bonito(v)}"
                                                 for k, v in sol[0].items())
                        if sol else "El sistema no tiene solución.")
        if graficar and len(exprs) == 2:
            try:
                despejadas = []
                import sympy as sp
                y = sp.Symbol("y")
                for e in exprs:
                    izq, der = M.partir_ecuacion(e)
                    for d in sp.solve(sp.Eq(izq, der), y):
                        despejadas.append(d)
                if despejadas:
                    g = M.grafica_2d(despejadas, rango=(-10, 10),
                                     titulo=titulo or "Sistema: corte de las rectas")
                    r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
            except Exception as e:
                log(f"[CIENCIAS] no pude dibujar el sistema: {e}")
    elif accion == "derivar":
        s = M.derivar(expr, var, int(p.get("orden") or 1))
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = f"La derivada es {M.bonito(s['resultado'])}"
        if graficar:
            g = M.grafica_2d([s["expr"], s["resultado"]], rango=_rango(p),
                             titulo=titulo or "Función y su derivada",
                             variable=s["variable"])
            r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
    elif accion == "integrar":
        lim = p.get("limites")
        a, b = (lim[0], lim[1]) if lim and len(lim) == 2 else (None, None)
        s = M.integrar(expr, var, a, b)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = (f"La integral vale {M.bonito(s['resultado'])}" if a is not None
                        else f"La primitiva es {M.bonito(s['resultado'])} + C")
        if graficar or a is not None:
            g = M.grafica_2d(s["expr"], rango=_rango(p, por_defecto=(
                float(M.sympificar(str(a))) - 2 if a is not None else -10,
                float(M.sympificar(str(b))) + 2 if b is not None else 10)),
                titulo=titulo or "Área bajo la curva", variable=s["variable"],
                area=(a, b) if a is not None else None)
            r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
    elif accion == "limite":
        s = M.limite(expr, var, p.get("punto", "0"))
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = f"El límite vale {M.bonito(s['resultado'])}"
        if graficar:
            g = M.grafica_2d(s["expr"], rango=_rango(p),
                             titulo=titulo or "Comportamiento cerca del punto",
                             variable=s["variable"])
            r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
    elif accion == "serie":
        s = M.serie_taylor(expr, var, p.get("punto", "0"), int(p.get("orden") or 6))
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = f"El desarrollo es {M.bonito(s['resultado'])}"
        if graficar:
            g = M.grafica_2d([s["expr"], s["resultado"]], rango=_rango(p, por_defecto=(-4, 4)),
                             titulo=titulo or "Función y su serie de Taylor",
                             variable=s["variable"])
            r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
    elif accion == "matriz":
        filas = _leer_matriz(expr)
        if not filas:
            r["titular"] = "No he entendido la matriz. Escríbela como [[1,2],[3,4]]."
        else:
            s = M.matriz(filas)
            r["pasos"] = s["pasos"]
            r["latex"] = s.get("latex") or []
            r["titular"] = ("Determinante " + M.bonito(s["det"]) if "det" in s
                            else "Matriz analizada.")
    elif accion == "edo":
        s = M.ecuacion_diferencial(expr)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = f"Solución general: {M.bonito(s['resultado'].rhs)}"
        if graficar:
            try:
                lado = expr.split("=")[0]
                campo = re.sub(r"\by\s*'", "", lado)
                g = M.campo_direcciones(campo or "y", titulo=titulo or "Campo de pendientes")
                r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
            except Exception as e:
                log(f"[CIENCIAS] campo de pendientes: {e}")
    elif accion == "estadistica":
        nums = datos.get("nums") or []
        s = M.estadistica(nums)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        d = s.get("resultado") or {}
        r["titular"] = (f"Media {d.get('media', 0):.4g}, mediana "
                        f"{d.get('mediana', 0):.4g}, desviación típica "
                        f"{d.get('desviacion_muestral', 0):.4g}" if d else "Sin datos.")
        if nums:
            g = M.grafica_datos(nums, clase="histograma",
                                titulo=titulo or "Distribución de los datos")
            r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
    elif accion in ("simplificar", "evaluar"):
        s = M.simplificar(expr)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        try:
            import sympy as sp
            val = sp.N(s["resultado"])
            r["titular"] = (f"{M.bonito(s['resultado'])}"
                            + (f" ≈ {float(val):.10g}" if val.is_number else ""))
        except Exception:
            r["titular"] = M.bonito(s["resultado"])
        if graficar:
            g = M.grafica_2d(s["expr"], rango=_rango(p), titulo=titulo or "Gráfica")
            r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})

    # ── gráficas pedidas a propósito ──
    elif accion == "grafica2d":
        g = M.grafica_2d(exprs or [expr], rango=_rango(p), titulo=titulo or "Gráfica",
                         variable=var or "x")
        r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
        r["pasos"] = g["notas"] or ["Curva dibujada."]
        r["titular"] = "Ahí tiene la gráfica, señor."
    elif accion == "superficie3d":
        g = M.superficie_3d(expr, rango_x=_rango(p, por_defecto=(-5, 5)),
                            rango_y=_rango(p, "rango_y", (-5, 5)),
                            titulo=titulo or "Superficie", log=log)
        r.update({k: g.get(k, "") for k in ("png", "html", "obj", "stl", "carpeta")})
        r["pasos"] = g["notas"]
        r["titular"] = "Superficie levantada en 3D, señor."
    elif accion == "implicita3d":
        lim = _rango(p, por_defecto=(-3, 3))
        g = M.implicita_3d(expr, limites=(lim, lim, lim), titulo=titulo or "Superficie")
        r.update({k: g.get(k, "") for k in ("png", "html", "obj", "stl", "carpeta")})
        r["pasos"] = g["notas"]
        r["titular"] = "Superficie implícita reconstruida en 3D."
    elif accion == "parametrica2d":
        g = M.grafica_parametrica_2d(exprs[0], exprs[1] if len(exprs) > 1 else "t",
                                     rango=_rango(p, por_defecto=(0, 6.2832)),
                                     titulo=titulo or "Curva paramétrica")
        r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
        r["titular"] = "Curva paramétrica dibujada."
    elif accion in ("parametrica3d", "curva3d"):
        e = (exprs + ["cos(t)", "sin(t)", "t"])[:3]
        if accion == "curva3d":
            g = M.curva_3d(e[0], e[1], e[2], rango=_rango(p, por_defecto=(0, 12.566)),
                           titulo=titulo or "Curva en el espacio")
        else:
            g = M.superficie_parametrica(e[0], e[1], e[2], titulo=titulo or "Superficie")
        r.update({k: g.get(k, "") for k in ("png", "html", "obj", "stl", "carpeta")})
        r["pasos"] = g.get("notas", [])
        r["titular"] = "Listo en 3D, señor."
    elif accion == "campo2d":
        g = M.campo_direcciones(expr, titulo=titulo or "Campo de direcciones")
        r.update({k: g.get(k, "") for k in ("png", "html", "carpeta")})
        r["titular"] = "Campo de direcciones dibujado."
    elif accion == "campo3d":
        e = (exprs + ["-y", "x", "0"])[:3]
        g = M.campo_vectorial_3d(e[0], e[1], e[2], titulo=titulo or "Campo vectorial")
        r.update({k: g.get(k, "") for k in ("png", "carpeta")})
        r["pasos"] = g["notas"]
        r["titular"] = "Campo vectorial en 3D, con divergencia y rotacional."
    elif accion == "polar":
        g = M.grafica_polar(expr, titulo=titulo or "Curva polar")
        r.update({k: g.get(k, "") for k in ("png", "carpeta")})
        r["titular"] = "Curva polar dibujada."
    elif accion == "datos":
        g = M.grafica_datos(datos.get("nums") or [], clase=p.get("clase", "auto"),
                            titulo=titulo or "Datos", ajuste=p.get("ajuste", ""))
        r.update({k: g.get(k, "") for k in ("png", "carpeta")})
        r["pasos"] = g["notas"]
        r["titular"] = "Datos representados."

    # ── física ──
    elif accion == "formula_fisica":
        ley = p.get("formula") or ""
        if not ley and p.get("enunciado"):
            candidatas = F.buscar_formula(p["enunciado"])
            ley = candidatas[0] if candidatas else ""
        conocidos = {k: v for k, v in (datos or {}).items()
                     if isinstance(v, (int, float))}
        if not conocidos and p.get("enunciado"):
            conocidos = _datos_por_contexto(p["enunciado"], ley)
        s = F.resolver_formula(ley, conocidos, p.get("incognita", ""), log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = (f"{s['incognita']} = {s['resultado']:.6g} {s['unidad']}"
                        if s.get("ok") else "Me faltan datos para despejar.")
    elif accion == "tiro":
        nums = datos.get("nums") or []
        v0 = _n(datos, 0, 20.0)
        ang = _n(datos, 1, 45.0)
        # Si el primer número parece un ángulo y el segundo una rapidez, se cambian.
        if len(nums) >= 2 and nums[0] <= 90 and nums[1] > 90:
            v0, ang = nums[1], nums[0]
        y0 = _n(datos, 2, 0.0) if len(nums) > 2 else 0.0
        s = F.tiro_parabolico(float(v0), float(ang), float(y0),
                              tridimensional=(dim == 3), log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "html", "obj", "stl", "carpeta")})
        r["titular"] = (f"Alcanza {s['alcance']:.4g} metros, sube hasta "
                        f"{s['altura_max']:.4g} metros y vuela {s['t_vuelo']:.4g} segundos.")
    elif accion == "rectilineo":
        s = F.movimiento_rectilineo(_n(datos, 0, 0.0) or 0.0, _n(datos, 1, 0.0) or 0.0,
                                    _n(datos, 2, 0.0) or 0.0, _n(datos, 3, 10.0) or 10.0,
                                    log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "html", "carpeta")})
        r["titular"] = f"Acaba en {s['x_final']:.4g} m a {s['v_final']:.4g} m/s."
    elif accion == "oscilador":
        s = F.oscilador_armonico(_n(datos, 0, 1.0) or 1.0, _n(datos, 1, 1.0) or 1.0,
                                 _n(datos, 2, 1.0) or 1.0, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "html", "carpeta")})
        r["titular"] = f"Periodo {s['periodo']:.4g} s, pulsación {s['omega']:.4g} rad/s."
    elif accion == "onda":
        s = F.onda_viajera(_n(datos, 0, 1.0) or 1.0, _n(datos, 1, 2.0) or 2.0,
                           _n(datos, 2, 1.0) or 1.0, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "html", "obj", "stl", "carpeta")})
        r["titular"] = f"La onda viaja a {s['velocidad']:.4g} metros por segundo."
    elif accion == "campo_electrico":
        cargas = p.get("cargas") or [(1.0, -1.5, 0.0), (-1.0, 1.5, 0.0)]
        s = F.campo_electrico(cargas, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "html", "obj", "stl", "carpeta")})
        r["titular"] = "Campo y potencial dibujados; el potencial también en 3D."
    elif accion == "circuito_rc":
        s = F.circuito_rc(_n(datos, 0, 1000.0) or 1000.0, _n(datos, 1, 1e-6) or 1e-6,
                          _n(datos, 2, 5.0) or 5.0, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "html", "carpeta")})
        r["titular"] = f"Constante de tiempo {s['tau']:.4g} segundos."
    elif accion == "diagrama_pv":
        s = F.diagrama_pv(p.get("puntos") or [(0.001, 200000), (0.003, 200000),
                                              (0.003, 100000), (0.001, 100000)], log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "carpeta")})
        r["titular"] = f"El ciclo produce {s['trabajo']:.5g} julios por vuelta."
    elif accion == "lente":
        s = F.lente_delgada(_n(datos, 0, 0.1) or 0.1, _n(datos, 1, 0.3) or 0.3, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "carpeta")})
        r["titular"] = (f"Imagen a {s['s_imagen']:.4g} m, aumento {s['aumento']:.4g}."
                        if "s_imagen" in s else "Caso degenerado.")
    elif accion == "relatividad":
        s = F.energia_relativista(_n(datos, 0, 1.0) or 1.0,
                                  _n(datos, 1, 0.9 * 299792458) or 0.0, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "carpeta")})
        r["titular"] = f"Factor de Lorentz γ = {s['gamma']:.6g}."

    # ── química ──
    elif accion == "masa_molar":
        s = Q.masa_molar(expr)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = (f"La masa molar de {expr} es {s['masa_molar']:.4f} gramos por mol."
                        if s.get("ok") else s["pasos"][0])
    elif accion == "balancear":
        s = Q.balancear(expr)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = (f"Ajustada: {s['ecuacion']}" if s.get("ok")
                        else "No he podido ajustarla.")
    elif accion == "estequiometria":
        s = Q.estequiometria(expr, p.get("cantidades") or {}, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = (f"El limitante es {s['limitante']}." if s.get("ok")
                        else "Faltan datos.")
    elif accion == "ph":
        nums = datos.get("nums") or [0.1]
        debil = "debil" in (expr or "")
        s = Q.ph(nums[0], "acido debil" if debil else "acido fuerte",
                 ka=(nums[1] if debil and len(nums) > 1 else None))
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = f"El pH es {s['pH']:.3f}." if s.get("ok") else s["pasos"][0]
    elif accion == "valoracion":
        nums = datos.get("nums") or []
        s = Q.curva_valoracion(_n(datos, 0, 0.1) or 0.1, (_n(datos, 1, 25.0) or 25.0) / 1000,
                               _n(datos, 2, 0.1) or 0.1,
                               ka=(nums[3] if len(nums) > 3 else None), log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "html", "carpeta")})
        r["titular"] = f"Equivalencia a {s['v_equivalencia'] * 1000:.4g} mililitros."
    elif accion == "cinetica":
        s = Q.cinetica(int(p.get("orden") or 1), _n(datos, 0, 0.1) or 0.1,
                       _n(datos, 1, 1.0) or 1.0, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "html", "carpeta")})
        r["titular"] = f"Tiempo de semirreacción {s['t_medio']:.4g} segundos."
    elif accion == "arrhenius":
        s = Q.arrhenius(_n(datos, 0, 50.0) or 50.0, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r.update({k: s.get(k, "") for k in ("png", "carpeta")})
        r["titular"] = "Curva de Arrhenius dibujada."
    elif accion == "equilibrio":
        s = Q.equilibrio(p.get("K", 1.0), p.get("iniciales") or {},
                         p.get("coeficientes") or {}, log=log)
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = (f"Avance x = {s['x']:.5g} mol/L." if s.get("ok")
                        else "No se pudo resolver el equilibrio.")
    elif accion == "hess":
        s = Q.entalpia_reaccion(p.get("reactivos") or {}, p.get("productos") or {})
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = (f"ΔH de reacción = {s['delta_H']:.2f} kilojulios."
                        if s.get("ok") else "Me faltan entalpías de formación.")
    elif accion == "pila":
        s = Q.pila(p.get("catodo", "Cu2+/Cu"), p.get("anodo", "Zn2+/Zn"),
                   int(p.get("orden") or 2))
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = (f"La pila da {s['E0']:+.3f} voltios." if s.get("ok")
                        else "Ese par redox no lo tengo.")
    elif accion == "molecula":
        s = Q.modelo_3d_molecula(expr or "H2O", log=log)
        r["pasos"] = s.get("pasos", [])
        r.update({k: s.get(k, "") for k in ("html", "obj", "stl", "carpeta")})
        r["titular"] = (f"{expr}: geometría {s['forma']}. Le abro el modelo 3D."
                        if s.get("ok") else "No pude construir esa molécula.")
    elif accion == "elemento":
        r["titular"] = Q.ficha_elemento(expr)
        r["pasos"] = [r["titular"],
                      "Configuración electrónica: " + Q.configuracion_electronica(expr)]
    elif accion == "configuracion":
        cfg = Q.configuracion_electronica(expr)
        r["titular"] = f"{expr}: {cfg}" if cfg else f"No encuentro «{expr}»."
        r["pasos"] = [Q.ficha_elemento(expr), f"Configuración: {cfg}"]
    elif accion == "tabla_periodica":
        s = Q.tabla_periodica_grafica(p.get("colorear", "categoria"), log=log)
        r.update({k: s.get(k, "") for k in ("png", "carpeta")})
        r["pasos"] = s["pasos"]
        r["latex"] = s.get("latex") or []
        r["titular"] = "Aquí tiene la tabla periódica completa, señor."
    elif accion == "sin_calculo":
        # Titular vacío a propósito: `resolver` lo lee como «no tengo nada» y
        # deja que conteste el cerebro.
        r["titular"] = ""
    else:
        r["titular"] = f"No sé hacer «{accion}» todavía, señor."
    return r


def _dominio_util(soluciones) -> tuple:
    """Rango de x que enseña todas las raíces con margen."""
    import sympy as sp
    reales = []
    for s in soluciones or []:
        try:
            v = complex(sp.N(s))
            if abs(v.imag) < 1e-9:
                reales.append(v.real)
        except Exception:
            pass
    if not reales:
        return (-10, 10)
    lo, hi = min(reales), max(reales)
    m = max((hi - lo) * 0.6, 3.0)
    return (lo - m, hi + m)


def _leer_matriz(texto: str):
    """«[[1,2],[3,4]]» o «1 2; 3 4» -> lista de listas."""
    t = (texto or "").strip()
    m = re.search(r"\[\s*\[.*\]\s*\]", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0).replace("'", '"'))
        except Exception:
            pass
    filas = [f for f in re.split(r"[;\n]", t) if re.search(r"\d", f)]
    salida = []
    for f in filas:
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", f)]
        if nums:
            salida.append(nums)
    return salida if len(salida) > 1 or (salida and len(salida[0]) > 1) else []


def _datos_por_contexto(enunciado: str, clave_formula: str) -> dict:
    """Casa los números del enunciado con los símbolos de la ley.

    Lo hace `fisica.casar_datos`, que además de las unidades entiende lo que el
    enunciado da por sabido («parte del reposo» es v₀ = 0).
    """
    import fisica as F
    return F.casar_datos(enunciado, clave_formula)


# ── API pública ────────────────────────────────────────────────────────────
def resolver(core, enunciado: str, abrir: bool = True, log=print) -> str:
    """Resuelve el problema dictado y devuelve la respuesta lista para hablar."""
    if not M.disponible():
        falta = ", ".join(M.faltantes())
        return (f"Señor, me falta {falta} para hacer ciencias. Dígame «instala las "
                "librerías de ciencias» y lo arreglo.")
    enunciado = (enunciado or "").strip()
    if not enunciado:
        return "Dígame el problema, señor."
    try:
        p = plan(core, enunciado, log=log)
    except Exception as e:
        log(f"[CIENCIAS] el plan falló: {e}")
        p = plan_por_reglas(enunciado)
    log(f"[CIENCIAS] plan ({p.get('_fuente')}): {p.get('accion')} · "
        f"{str(p.get('expresion'))[:60]}")
    try:
        r = ejecutar(core, p, log=log)
    except Exception as e:
        log(f"[CIENCIAS] fallo al ejecutar {p.get('accion')}: {e}")
        # Segundo intento con el analizador de reglas, por si el plan del
        # cerebro traía una expresión mal formada.
        r = None
        if p.get("_fuente") == "cerebro":
            try:
                r = ejecutar(core, plan_por_reglas(enunciado), log=log)
            except Exception as e2:
                log(f"[CIENCIAS] tampoco con reglas: {e2}")
        if r is None:
            # Cadena vacía y NO un mensaje de error: así `_orden_ciencias`
            # devuelve None y la frase sigue su camino normal hasta el cerebro,
            # que al menos contestará algo. Un callejón sin salida es peor que
            # una respuesta conversada.
            return ""

    if not r.get("titular") and not r.get("pasos") and not r.get("png"):
        log("[CIENCIAS] no hay cálculo que hacer aquí; que conteste el cerebro")
        return ""

    ULTIMO.update({"carpeta": r.get("carpeta", ""), "obj": r.get("obj", ""),
                   "html": r.get("html", ""), "png": r.get("png", ""),
                   "expresion": p.get("expresion", ""),
                   "materia": p.get("materia", ""), "accion": r.get("accion", "")})

    # Se abre lo más rico que haya: visor interactivo antes que lámina.
    abierto = ""
    if abrir:
        for ruta in (r.get("html"), r.get("png")):
            if ruta and os.path.exists(ruta) and M.abrir(ruta, log=log):
                abierto = ruta
                break
    if p.get("holograma") and r.get("obj"):
        h = M.a_holograma(core, r["obj"], log=log)
        if h:
            r["pasos"].append(h)

    # Si el encargo pedía además que se EXPLIQUE (tutor, paso a paso, LaTeX,
    # una lista de requisitos), el cerebro redacta la clase encima del cálculo
    # ya verificado. Si no hay cerebro o falla, queda el desarrollo de siempre.
    leccion = ""
    if es_instructivo(enunciado):
        leccion = explicar(core, enunciado, r, log=log)

    partes = [r.get("titular") or "Hecho, señor."]
    if leccion:
        partes.append("\n\n" + leccion)
    pasos = [s for s in (r.get("pasos") or []) if s]
    if pasos:
        partes.append(("\n\nDesarrollo verificado (sympy):\n" if leccion
                       else "\n\nDesarrollo:\n")
                      + "\n".join(f"  {s}" for s in pasos[:40]))
    if pide_latex(enunciado) and r.get("latex") and not leccion:
        partes.append("\n\nEn LaTeX:\n"
                      + "\n".join(f"  $$ {x} $$" for x in r["latex"]))
    archivos = []
    for etiqueta, clave in (("lámina", "png"), ("visor interactivo", "html"),
                            ("malla .obj", "obj"), ("malla .stl", "stl")):
        if r.get(clave):
            archivos.append(f"{etiqueta}: {os.path.basename(r[clave])}")
    if archivos:
        partes.append(f"\n\nArchivos en {r.get('carpeta')}\n  " + "\n  ".join(archivos))
    if abierto:
        partes.append(f"\nLe he abierto {os.path.basename(abierto)}.")
    return "".join(partes)


def resumen_estado() -> dict:
    """Para el panel: qué hay instalado y qué se hizo por última vez."""
    import fisica as F
    import quimica as Q
    e = M.estado()
    e.update({"formulas_fisica": len(F.FORMULAS),
              "elementos": len(Q.TABLA),
              "constantes": len(F.CONSTANTES),
              "ultimo": dict(ULTIMO)})
    return e
