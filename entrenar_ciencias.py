#!/usr/bin/env python3
"""
entrenar_ciencias.py - El examen con el que JARVIS y ULTRON aprenden ciencias
=============================================================================
Un módulo nuevo no «sabe» nada hasta que se comprueba que acierta. Aquí está
esa comprobación, y además el mecanismo por el que lo aprendido SE QUEDA:

    1. BANCO. Enunciados reales de matemáticas, física y química —muchos
       escritos como se DICTAN, con «equis al cuadrado» y no con «x**2»— junto
       con la respuesta correcta y la acción que debía elegir el enrutador.

    2. EXAMEN. `evaluar()` le pasa cada enunciado al enrutador de `ciencias`,
       compara el resultado con la respuesta correcta (por número con
       tolerancia, o por texto que debe aparecer) y saca la nota por materia.

    3. APRENDIZAJE. De cada fallo de ENRUTADO se guarda la huella de la frase
       con la acción correcta en `Prefs/ciencias_aprendido.json`. `ciencias`
       consulta ese fichero ANTES de decidir por reglas, así que la próxima vez
       esa forma de hablar ya se entiende. El señor también puede enseñarle a
       mano con `ensenar()`.

    4. MEMORIA. Al terminar se apunta en la memoria permanente (JARVIS.md) y en
       la memoria unificada qué sabe hacer ahora, para que los dos agentes lo
       tengan presente en cada conversación.

Uso:
    python entrenar_ciencias.py              examen completo y aprendizaje
    python entrenar_ciencias.py --solo-examen
    python entrenar_ciencias.py --materia quimica
"""
import json
import os
import re
import time
import unicodedata

_PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
_APRENDIDO = os.path.join(_PREFS, "ciencias_aprendido.json")
_INFORMES = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Ciencia",
                         "entrenamiento")

# ── banco de problemas ─────────────────────────────────────────────────────
# accion   = lo que el enrutador DEBE elegir (es lo que se aprende si falla)
# numero   = valor que tiene que aparecer en la respuesta (con tolerancia)
# texto    = trozos que tienen que aparecer, todos
BANCO = [
    # ── matemáticas: dictado ──
    {"m": "matematica", "e": "resuélveme equis al cuadrado menos cinco equis más seis igual a cero",
     "accion": "ecuacion", "texto": ["2", "3"]},
    {"m": "matematica", "e": "resuelve equis al cuadrado menos cuatro igual a cero",
     "accion": "ecuacion", "texto": ["2", "-2"]},
    {"m": "matematica", "e": "resuelve dos equis más tres igual a once",
     "accion": "ecuacion", "numero": 4.0},
    {"m": "matematica", "e": "derívame equis al cubo",
     "accion": "derivar", "texto": ["x^2"]},
    {"m": "matematica", "e": "derivada de seno de equis por coseno de equis",
     "accion": "derivar", "texto": ["cos", "sin"]},
    {"m": "matematica", "e": "segunda derivada de equis a la cuatro",
     "accion": "derivar", "texto": ["12"]},
    {"m": "matematica", "e": "integra x**2 de 0 a 3", "accion": "integrar", "numero": 9.0},
    {"m": "matematica", "e": "integral de seno de x de 0 a pi",
     "accion": "integrar", "numero": 2.0},
    {"m": "matematica", "e": "cuál es el límite de seno de x entre x cuando x tiende a 0",
     "accion": "limite", "numero": 1.0},
    {"m": "matematica", "e": "límite de 1 entre x cuando x tiende a infinito",
     "accion": "limite", "numero": 0.0},
    {"m": "matematica", "e": "simplifica (x**2 - 1)/(x - 1)",
     "accion": "simplificar", "texto": ["x + 1"]},
    {"m": "matematica", "e": "factoriza x**2 - 5*x + 6",
     "accion": "simplificar", "texto": ["x - 2", "x - 3"]},
    {"m": "matematica", "e": "resuelve el sistema x + y = 10; x - y = 2",
     "accion": "sistema", "texto": ["6", "4"]},
    {"m": "matematica", "e": "determinante de [[1,2],[3,4]]",
     "accion": "matriz", "numero": -2.0},
    {"m": "matematica", "e": "serie de taylor de exp(x)",
     "accion": "serie", "texto": ["x^2/2"]},
    {"m": "matematica", "e": "media y desviación típica de 2 4 4 4 5 5 7 9",
     "accion": "estadistica", "texto": ["5"]},
    {"m": "matematica", "e": "gráfica de x**3 - 3*x", "accion": "grafica2d",
     "archivo": "png"},
    {"m": "matematica", "e": "gráficame en tres dimensiones seno de x por coseno de y",
     "accion": "superficie3d", "archivo": "obj"},
    {"m": "matematica", "e": "resuelve la ecuación diferencial y' - y = 0",
     "accion": "edo", "texto": ["exp"]},

    # ── física ──
    {"m": "fisica", "e": "energía cinética de una masa de 2 kg que va a 10 m/s",
     "accion": "formula_fisica", "numero": 100.0},
    {"m": "fisica", "e": "ley de ohm con 12 V y una resistencia de 4 ohmios",
     "accion": "formula_fisica", "numero": 3.0},
    {"m": "fisica", "e": "energía potencial de 5 kg a 10 m de altura",
     "accion": "formula_fisica", "numero": 490.3, "tol": 1.0},
    {"m": "fisica", "e": "periodo de un péndulo de 1 m",
     "accion": "formula_fisica", "numero": 2.006, "tol": 0.02},
    {"m": "fisica", "e": "una pelota se lanza a 25 m/s con un ángulo de 40 grados",
     "accion": "tiro", "numero": 62.76, "tol": 0.5},
    {"m": "fisica", "e": "tiro parabólico a 20 m/s con 45 grados, dibújamelo",
     "accion": "tiro", "numero": 40.79, "tol": 0.5},
    {"m": "fisica", "e": "oscilador armónico con masa 1 kg y constante 4 N/m",
     "accion": "oscilador", "archivo": "png"},
    {"m": "fisica", "e": "onda viajera de longitud de onda 2 m y frecuencia 3 Hz",
     "accion": "onda", "archivo": "obj"},
    {"m": "fisica", "e": "campo eléctrico de dos cargas puntuales",
     "accion": "campo_electrico", "archivo": "png"},
    {"m": "fisica", "e": "circuito rc con 1000 ohmios y 0.000001 faradios",
     "accion": "circuito_rc", "archivo": "png"},

    # ── química ──
    {"m": "quimica", "e": "cuál es la masa molar del H2SO4",
     "accion": "masa_molar", "numero": 98.07, "tol": 0.1},
    {"m": "quimica", "e": "masa molar del CO2", "accion": "masa_molar",
     "numero": 44.01, "tol": 0.05},
    {"m": "quimica", "e": "masa molar del Ca(OH)2", "accion": "masa_molar",
     "numero": 74.09, "tol": 0.05},
    {"m": "quimica", "e": "balancea C3H8 + O2 -> CO2 + H2O", "accion": "balancear",
     "texto": ["5 O2", "3 CO2", "4 H2O"]},
    {"m": "quimica", "e": "balancea Fe + O2 -> Fe2O3", "accion": "balancear",
     "texto": ["4 Fe", "3 O2", "2 Fe2O3"]},
    {"m": "quimica", "e": "ajusta KMnO4 + HCl -> KCl + MnCl2 + H2O + Cl2",
     "accion": "balancear", "texto": ["16 HCl", "5 Cl2"]},
    {"m": "quimica", "e": "pH de una disolución 0.01 molar de ácido fuerte",
     "accion": "ph", "numero": 2.0},
    {"m": "quimica", "e": "geometría molecular del agua", "accion": "molecula",
     "texto": ["angular"]},
    {"m": "quimica", "e": "hazme el modelo 3d de la molécula de metano",
     "accion": "molecula", "texto": ["tetraédrica"], "archivo": "obj"},
    {"m": "quimica", "e": "configuración electrónica del hierro",
     "accion": "configuracion", "texto": ["3d6"]},
    {"m": "quimica", "e": "qué es el elemento wolframio", "accion": "elemento",
     "texto": ["74"]},
    {"m": "quimica", "e": "enséñame la tabla periódica", "accion": "tabla_periodica",
     "archivo": "png"},

    # ── encargos largos: el enunciado viene envuelto en prosa e instrucciones.
    # Es como se pide de verdad, y es donde el módulo se caía al principio.
    {"m": "matematica",
     "e": "Actúa como un tutor experto en matemáticas. Resuelve paso a paso la "
          "siguiente ecuación cuadrática: 3x² - 5x - 2 = 0. Requisitos de "
          "respuesta: 1. Identifica los coeficientes (a, b, c). 2. Aplica la "
          "fórmula general mostrando cada paso explícito en LaTeX. 3. Encuentra "
          "y simplifica los dos valores posibles para x. 4. Explica brevemente "
          "el significado del discriminante obtenido.",
     "accion": "ecuacion", "texto": ["-1/3", "2", "49"]},
    {"m": "matematica",
     "e": "Determina el valor de x en la ecuación 2x + 7 = 19, explicando cada paso.",
     "accion": "ecuacion", "numero": 6.0},
    {"m": "matematica",
     "e": "Explícame qué es una derivada y para qué sirve en la vida real",
     "accion": "sin_calculo", "solo_accion": True},
    {"m": "fisica",
     "e": "Se deja caer una piedra desde 45 m de altura. ¿Cuánto tarda en "
          "llegar al suelo?",
     "accion": "formula_fisica", "numero": 3.0294, "tol": 0.01},
    {"m": "fisica",
     "e": "Un móvil parte del reposo con aceleración de 2 m/s2. ¿Qué velocidad "
          "tiene a los 5 s?",
     "accion": "formula_fisica", "numero": 10.0},
    {"m": "fisica",
     "e": "Un coche que va a 20 m/s frena hasta detenerse en 4 s. ¿Qué "
          "aceleración lleva?",
     "accion": "formula_fisica", "numero": -5.0},
    {"m": "fisica",
     "e": "Un resistor de 4 ohmios conectado a 12 V. ¿Qué intensidad circula?",
     "accion": "formula_fisica", "numero": 3.0},
    {"m": "fisica",
     "e": "Calcula la presión de 2 moles de gas a 300 K en un volumen de 0.05 m3",
     "accion": "formula_fisica", "numero": 99773.6, "tol": 5.0},
    {"m": "quimica",
     "e": "Balancea la siguiente reacción química e indica los coeficientes: "
          "Al + O2 -> Al2O3",
     "accion": "balancear", "texto": ["4 Al", "3 O2", "2 Al2O3"]},
]


# ── memoria de frases aprendidas ───────────────────────────────────────────
def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def huella(texto: str) -> str:
    """Forma reducida de la frase: sin números, sin tildes y sin relleno.

    Dos maneras de pedir lo mismo con distintos datos dan la misma huella, que
    es justo lo que hay que recordar: la FORMA de pedirlo.
    """
    t = _sin_tildes((texto or "").lower())
    t = re.sub(r"[-+]?\d+(?:[.,]\d+)?(?:e-?\d+)?", " ", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    vacias = {"me", "el", "la", "los", "las", "un", "una", "unos", "unas", "de",
              "del", "al", "a", "en", "y", "o", "que", "por", "con", "para",
              "cual", "cuanto", "es", "son", "por favor", "jarvis", "ultron",
              "lo", "le", "se", "su", "mi", "yo", "tu"}
    palabras = [p for p in t.split() if p and p not in vacias and len(p) > 1]
    return " ".join(palabras)


def _cargar() -> dict:
    try:
        with open(_APRENDIDO, encoding="utf-8") as f:
            d = json.load(f) or {}
            if isinstance(d, dict) and isinstance(d.get("patrones"), list):
                return d
    except Exception:
        pass
    return {"patrones": []}


def _guardar(d: dict):
    os.makedirs(_PREFS, exist_ok=True)
    with open(_APRENDIDO, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def aprendido() -> list:
    return _cargar()["patrones"]


def ensenar(frase: str, accion: str, origen: str = "manual", extra: dict = None) -> str:
    """Enseña que esta forma de pedir las cosas corresponde a esta acción."""
    h = huella(frase)
    if not h or not accion:
        return "Me falta la frase o la acción, señor."
    d = _cargar()
    for p in d["patrones"]:
        if p.get("huella") == h:
            p.update({"accion": accion, "origen": origen, "ts": time.time(),
                      "extra": extra or p.get("extra") or {}})
            _guardar(d)
            return f"Actualizado: «{h}» → {accion}"
    d["patrones"].append({"huella": h, "accion": accion, "origen": origen,
                          "ejemplo": frase[:160], "extra": extra or {},
                          "ts": time.time()})
    _guardar(d)
    return f"Aprendido: «{h}» → {accion}"


def olvidar(frase: str = "") -> str:
    d = _cargar()
    if not frase:
        n = len(d["patrones"])
        _guardar({"patrones": []})
        return f"Olvidadas las {n} frases aprendidas."
    h = huella(frase)
    antes = len(d["patrones"])
    d["patrones"] = [p for p in d["patrones"] if p.get("huella") != h]
    _guardar(d)
    return f"Olvidadas {antes - len(d['patrones'])} frases."


def buscar(texto: str, minimo: float = 0.72):
    """Busca la acción aprendida para esta frase. Exacta o por parecido."""
    h = huella(texto)
    if not h:
        return None
    patrones = _cargar()["patrones"]
    for p in patrones:
        if p.get("huella") == h:
            return p
    mias = set(h.split())
    if not mias:
        return None
    mejor, mejor_v = None, 0.0
    for p in patrones:
        suyas = set((p.get("huella") or "").split())
        if not suyas:
            continue
        j = len(mias & suyas) / len(mias | suyas)
        if j > mejor_v:
            mejor, mejor_v = p, j
    return mejor if mejor_v >= minimo else None


# ── examen ─────────────────────────────────────────────────────────────────
def _numeros_de(texto: str) -> list:
    return [float(x.replace(",", ".")) for x in
            re.findall(r"-?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", texto or "")]


def _acierta(caso: dict, respuesta: str, r: dict) -> tuple:
    """(ok, motivo) comparando la respuesta con lo que esperaba el banco."""
    texto = (r.get("titular", "") + "\n" + "\n".join(r.get("pasos", [])))
    if caso.get("solo_accion"):
        # Casos en los que lo correcto es NO calcular («explícame qué es una
        # derivada»): lo que se juzga es a dónde enrutó, no el resultado.
        elegida = r.get("accion", "")
        return elegida == caso.get("accion"), f"enrutó a «{elegida}»"
    if "numero" in caso:
        tol = caso.get("tol", max(abs(caso["numero"]) * 0.01, 1e-6))
        nums = _numeros_de(r.get("titular", "")) + _numeros_de(texto)
        if any(abs(n - caso["numero"]) <= tol for n in nums):
            return True, ""
        return False, f"esperaba {caso['numero']}, no aparece"
    if "texto" in caso:
        faltan = [s for s in caso["texto"] if s.lower() not in texto.lower()]
        if not faltan:
            return True, ""
        return False, "falta: " + ", ".join(faltan)
    if "archivo" in caso:
        clave = caso["archivo"]
        ruta = r.get(clave) or ""
        if ruta and os.path.exists(ruta) and os.path.getsize(ruta) > 400:
            return True, ""
        return False, f"no generó el archivo .{clave}"
    return bool(respuesta), "sin respuesta"


def evaluar(core=None, materia: str = "", usar_cerebro: bool = False, log=print) -> dict:
    """Pasa el banco entero y devuelve la nota por materia y los fallos."""
    import ciencias
    casos = [c for c in BANCO if not materia or c["m"] == materia]
    resultados = []
    t0 = time.time()
    for i, caso in enumerate(casos, 1):
        e = caso["e"]
        try:
            p = ciencias.plan(core if usar_cerebro else None, e, log=lambda *a: None)
            r = ciencias.ejecutar(core, p, log=lambda *a: None)
            ok, motivo = _acierta(caso, r.get("titular", ""), r)
            resultados.append({"enunciado": e, "materia": caso["m"],
                               "accion_esperada": caso.get("accion", ""),
                               "accion_elegida": p.get("accion", ""),
                               "ok": ok, "motivo": motivo,
                               "titular": r.get("titular", "")[:180]})
        except Exception as ex:
            resultados.append({"enunciado": e, "materia": caso["m"],
                               "accion_esperada": caso.get("accion", ""),
                               "accion_elegida": "EXCEPCIÓN", "ok": False,
                               "motivo": f"{type(ex).__name__}: {str(ex)[:110]}",
                               "titular": ""})
        if log and i % 5 == 0:
            log(f"[ENTRENAMIENTO] {i}/{len(casos)} casos")
    por_materia = {}
    for r in resultados:
        d = por_materia.setdefault(r["materia"], {"ok": 0, "total": 0})
        d["total"] += 1
        d["ok"] += 1 if r["ok"] else 0
    aciertos = sum(1 for r in resultados if r["ok"])
    return {"resultados": resultados, "aciertos": aciertos, "total": len(resultados),
            "nota": 10.0 * aciertos / max(len(resultados), 1),
            "por_materia": por_materia, "segundos": round(time.time() - t0, 1),
            "fallos": [r for r in resultados if not r["ok"]]}


def _grafica_informe(antes: dict, despues: dict, carpeta: str) -> str:
    """Barras de nota por materia, antes y después de aprender."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import matematica as M
    except Exception:
        return ""
    materias = sorted(set(list(antes["por_materia"]) + list(despues["por_materia"])))
    def nota(d, m):
        v = d["por_materia"].get(m, {"ok": 0, "total": 1})
        return 10.0 * v["ok"] / max(v["total"], 1)
    x = np.arange(len(materias))
    fig, ax = plt.subplots(figsize=(9.5, 5.6), dpi=190, facecolor=M._FONDO)
    ax.bar(x - 0.19, [nota(antes, m) for m in materias], 0.36,
           color=M._ACENTO[3], label="antes de aprender")
    ax.bar(x + 0.19, [nota(despues, m) for m in materias], 0.36,
           color=M._ACENTO[0], label="después")
    for i, m in enumerate(materias):
        ax.annotate(f"{nota(despues, m):.1f}", (i + 0.19, nota(despues, m)),
                    ha="center", va="bottom", color=M._TINTA, fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(materias)
    ax.set_ylim(0, 10.6)
    M._estilo(ax, "Entrenamiento en ciencias · nota sobre 10", "", "nota")
    ax.legend(facecolor=M._PANEL, edgecolor=M._REJILLA, labelcolor=M._TINTA)
    fig.tight_layout()
    os.makedirs(carpeta, exist_ok=True)
    png = os.path.join(carpeta, "entrenamiento.png")
    fig.savefig(png, facecolor=M._FONDO)
    plt.close(fig)
    return png


_NOTA_MEMORIA = (
    "Sé matemáticas, física y química: resuelvo el problema dictado y lo "
    "GRAFICO (2D anotada, superficie 3D girable y malla .obj/.stl imprimible) "
    "con los módulos ciencias/matematica/fisica/quimica. Basta con decírmelo "
    "en voz alta; para ver la gráfica, pedir «grafícalo» o «en 3D»."
)


def entrenar(core=None, materia: str = "", aprender: bool = True,
             usar_cerebro: bool = False, log=print) -> str:
    """Examen, aprendizaje de los fallos de enrutado y segundo examen."""
    antes = evaluar(core, materia, usar_cerebro, log=log)
    aprendidas = 0
    if aprender:
        for f in antes["fallos"]:
            esperada = f.get("accion_esperada")
            # Solo se aprende cuando el fallo fue de ENRUTADO: si eligió bien la
            # acción y aun así falló, el problema está en el cálculo y
            # memorizarlo no arreglaría nada.
            if esperada and f.get("accion_elegida") != esperada:
                ensenar(f["enunciado"], esperada, origen="entrenamiento")
                aprendidas += 1
    despues = evaluar(core, materia, usar_cerebro, log=log) if aprendidas else antes

    carpeta = os.path.join(_INFORMES, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(carpeta, exist_ok=True)
    informe = {"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "materia": materia or "todas",
               "antes": {k: antes[k] for k in ("aciertos", "total", "nota",
                                               "por_materia", "segundos")},
               "despues": {k: despues[k] for k in ("aciertos", "total", "nota",
                                                   "por_materia", "segundos")},
               "frases_aprendidas": aprendidas,
               "fallos": [{k: f[k] for k in ("enunciado", "accion_esperada",
                                             "accion_elegida", "motivo")}
                          for f in despues["fallos"]]}
    with open(os.path.join(carpeta, "informe.json"), "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)
    png = _grafica_informe(antes, despues, carpeta)

    if aprender:
        try:
            import memoria_proyecto
            memoria_proyecto.anadir(_NOTA_MEMORIA, "Notas", log=log)
        except Exception as e:
            log(f"[ENTRENAMIENTO] memoria permanente: {e}")
        try:
            import memoria_grafo
            memoria_grafo.recordar(
                f"Entrenamiento de ciencias: nota {despues['nota']:.1f}/10 en "
                f"{despues['total']} problemas ({time.strftime('%Y-%m-%d')}).",
                tipo="nota", log=log)
        except Exception as e:
            log(f"[ENTRENAMIENTO] memoria unificada: {e}")

    lineas = [f"Entrenamiento terminado, señor. Nota {despues['nota']:.1f} sobre 10 "
              f"({despues['aciertos']} de {despues['total']} problemas) en "
              f"{antes['segundos'] + despues['segundos']:.0f} segundos."]
    for m, d in sorted(despues["por_materia"].items()):
        lineas.append(f"   {m}: {d['ok']}/{d['total']}")
    if aprendidas:
        lineas.append(f"He aprendido {aprendidas} formas nuevas de pedir las cosas "
                      f"(nota antes: {antes['nota']:.1f}).")
    if despues["fallos"]:
        lineas.append("Se me resisten todavía:")
        for f in despues["fallos"][:8]:
            lineas.append(f"   «{f['enunciado'][:70]}» — {f['motivo']}")
    lineas.append(f"Informe en {carpeta}")
    if png:
        lineas.append(f"Gráfica del progreso: {os.path.basename(png)}")
    return "\n".join(lineas)


def estado() -> dict:
    """Para el panel: última nota y cuántas frases lleva aprendidas."""
    ultimo = {}
    try:
        carpetas = sorted(os.listdir(_INFORMES)) if os.path.isdir(_INFORMES) else []
        if carpetas:
            with open(os.path.join(_INFORMES, carpetas[-1], "informe.json"),
                      encoding="utf-8") as f:
                ultimo = json.load(f)
    except Exception:
        pass
    return {"casos_banco": len(BANCO), "frases_aprendidas": len(aprendido()),
            "ultimo_informe": ultimo.get("fecha", ""),
            "ultima_nota": (ultimo.get("despues") or {}).get("nota"),
            "carpeta_informes": _INFORMES}


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    mat = ""
    if "--materia" in args:
        mat = args[args.index("--materia") + 1]
    solo = "--solo-examen" in args
    print(entrenar(None, materia=mat, aprender=not solo))
