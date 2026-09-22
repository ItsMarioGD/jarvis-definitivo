#!/usr/bin/env python3
"""
colisiones.py - Detector de habilidades que se pisan
====================================================
SkillsManager despacha recorriendo una lista de mas de trescientos handlers y
quedandose con el primero que responde. Eso significa que el ORDEN de la lista
es una regla de negocio invisible: si una habilidad nueva reconoce una frase
que ya atendia otra, la roba, y nadie se entera hasta que algo deja de
funcionar en produccion. Hoy mismo hemos visto un caso real: dos handlers
distintos saben cancelar un apagado.

Este modulo lo hace visible. En vez de leer trescientas expresiones regulares a
ojo, prueba cada frase contra TODOS los handlers por separado (en modo seguro,
sin ejecutar nada) y dice cuales responderian.

    python colisiones.py                 informe completo
    python colisiones.py "apaga el pc"   quien atiende esta frase

Uso recomendado: pasarlo despues de añadir habilidades, igual que las pruebas.
"""
import sys

# Frases representativas de cada familia de ordenes. No pretende ser
# exhaustivo: pretende cubrir lo que el señor dice de verdad.
CORPUS = [
    "apaga el pc", "apaga el pc en 10 minutos", "apagate en 5 minutos",
    "cancela el apagado", "reinicia el equipo", "bloquea el pc",
    "suspende el equipo", "hiberna el pc", "cierra la sesion",
    "abre spotify", "cierra spotify", "abre la calculadora",
    "sube el volumen", "baja el volumen", "volumen al 30%", "silencia el audio",
    "que hora es", "que dia es hoy", "que tiempo hace", "clima en madrid",
    "haz una captura de pantalla", "copia hola al portapapeles",
    "anota comprar pan", "muestra mis notas", "recuerdame llamar al banco",
    "temporizador de 5 minutos", "alarma a las 8:30",
    "busca recetas de paella", "busca gatos en youtube", "investiga sobre marte",
    "reproduce musica", "pon la radio", "pon un podcast",
    "cuanta bateria queda", "como esta el pc", "que procesos pesan mas",
    "organiza la carpeta de descargas", "limpia los temporales",
    "vacia la papelera", "busca archivos informe",
    "que tengo mañana", "agenda una reunion el jueves a las 5",
    "manda un whatsapp a marta", "lee mis correos",
    "cuentame un chiste", "traduce hola al ingles", "calcula 15 por 8",
    "enciende las luces", "apaga las luces del salon",
    "haz una copia de seguridad", "actualiza mis programas",
]


def _handlers(despachador, marca="for handler in ("):
    """Handlers reales del despachador, en el orden en que se consultan.

    Se leen del propio codigo fuente para no tener que mantener una copia de
    la lista aqui: si alguien añade una habilidad, este analisis la ve sola.
    """
    import inspect
    fuente = inspect.getsource(despachador.handle)
    nombres, dentro = [], False
    for linea in fuente.splitlines():
        if marca in linea:
            dentro = True
            linea = linea.split(marca, 1)[1]
        if dentro:
            if linea.strip().startswith("):") or linea.strip() == ")":
                break
            for trozo in linea.replace(" ", "").split(","):
                trozo = trozo.strip("():")
                if trozo.startswith("self."):
                    nombres.append(trozo[len("self."):])
    vistos, salida = set(), []
    for n in nombres:
        if hasattr(despachador, n) and n not in vistos:
            vistos.add(n)
            salida.append((n, getattr(despachador, n)))
    return salida


def analizar(corpus=None, log=print) -> dict:
    """{frase: [handlers que responderían]}. Modo seguro: no ejecuta nada."""
    from jarvis_skills import SkillsManager
    from pc_control import PCControl
    sm = SkillsManager(log=lambda *a: None, safe=True)
    pc = PCControl(log=lambda *a: None, safe=True)

    # Los dos despachadores que atienden ordenes del sistema, en el mismo orden
    # en que los consulta el nucleo: primero habilidades, luego control del PC.
    handlers = ([(f"skills.{n}", h) for n, h in _handlers(sm)]
                + [(f"pc.{n}", h) for n, h in _handlers(pc, "for fn in (")])
    if not handlers:
        log("[COLISIONES] No pude leer la lista de handlers.")
        return {}

    resultado = {}
    for frase in (corpus or CORPUS):
        sm._orig = pc_orig = frase
        sm._orig_lower = frase.lower()
        responden = []
        for nombre, handler in handlers:
            t = sm._norm(frase) if nombre.startswith("skills.") else _norm_pc(frase)
            try:
                if handler(t) is not None:
                    responden.append(nombre)
            except Exception:
                continue        # un handler que revienta no es una colisión
        resultado[frase] = responden
        _ = pc_orig
    return resultado


def _norm_pc(frase: str) -> str:
    from pc_control import _norm
    return _norm(frase)


def informe(corpus=None, log=print) -> str:
    datos = analizar(corpus, log=log)
    if not datos:
        return "No pude analizar las habilidades."

    conflictos = {f: hs for f, hs in datos.items() if len(hs) > 1}
    huerfanas = [f for f, hs in datos.items() if not hs]

    lineas = [f"Frases analizadas: {len(datos)}",
              f"Con más de un candidato: {len(conflictos)}",
              f"Sin ninguna habilidad (irían al cerebro): {len(huerfanas)}", ""]

    if conflictos:
        lineas.append("COLISIONES (gana el primero de la lista):")
        for frase, handlers in sorted(conflictos.items(), key=lambda x: -len(x[1])):
            lineas.append(f"  «{frase}»")
            lineas.append(f"      gana {handlers[0]} · también responderían: "
                          + ", ".join(handlers[1:]))
        lineas.append("")

    if huerfanas:
        lineas.append("SIN HABILIDAD (las atiende el cerebro con herramientas):")
        for frase in huerfanas:
            lineas.append(f"  «{frase}»")

    return "\n".join(lineas)


def quien_atiende(frase: str, log=print) -> str:
    datos = analizar([frase], log=log)
    handlers = datos.get(frase, [])
    if not handlers:
        return f"«{frase}»: ninguna habilidad la reconoce; iría al cerebro."
    if len(handlers) == 1:
        return f"«{frase}»: la atiende {handlers[0]}, sin competencia."
    return (f"«{frase}»: gana {handlers[0]}, pero también responderían "
            + ", ".join(handlers[1:]) + ".")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(quien_atiende(" ".join(sys.argv[1:])))
    else:
        print(informe())
