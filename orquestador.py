#!/usr/bin/env python3
"""
orquestador.py - Que las piezas se hablen entre ellas
=====================================================
Habia calendario, prediccion de habitos, turno de noche, enjambre y registro de
acciones. Cinco piezas buenas y ninguna sabia de las otras: el turno de noche
limpiaba temporales mientras la agenda decia que a las ocho habia reunion, y la
prediccion sabia que el señor abre siempre las mismas tres cosas antes de una
reunion pero no se lo decia a nadie.

Aqui se juntan en dos rutinas que es lo que la gente espera de verdad de un
asistente:

  parte_de_manana()   qué pasó anoche, qué hay hoy, qué conviene preparar
  preparar_para(cita) abrir lo que el señor abre siempre antes de algo asi

Nada de esto inventa capacidades: solo consulta lo que ya existe y lo ordena en
una sola frase. Es pegamento, y el pegamento es justo lo que faltaba.
"""
import re
from datetime import datetime, timedelta


def _orden(core, frase: str) -> str:
    for despachador in (getattr(core, "conectores", None),
                        getattr(core, "skills", None),
                        getattr(core, "pc", None)):
        if despachador is None:
            continue
        try:
            r = despachador.handle(frase)
        except Exception:
            continue
        if r:
            return str(r)
    return ""


# ── parte de la mañana ──────────────────────────────────────────────────────
def parte_de_manana(core, log=print) -> str:
    """Todo lo que el señor necesita saber al sentarse: anoche, hoy y consejo."""
    partes = []

    # 1. Qué hizo el turno de noche.
    try:
        if getattr(core, "nocturno", None) is not None:
            informe = core.nocturno.informe_ultimo()
            if informe and "todavía no" not in informe.lower():
                primera = informe.splitlines()[0]
                partes.append(f"Anoche: {primera}")
    except Exception as e:
        log(f"[ORQUESTADOR] Turno de noche: {e}")

    # 2. Qué hay en la agenda.
    agenda = _orden(core, "que tengo hoy")
    if agenda:
        partes.append(f"Hoy: {agenda[:200]}")

    # 3. Qué vieron los especialistas sin llegar a molestar.
    try:
        if getattr(core, "enjambre", None) is not None:
            resumen = core.enjambre.resumen()
            if "no tienen nada" not in resumen.lower():
                partes.append(resumen[:200])
    except Exception:
        pass

    # 4. Qué falló ayer, que es lo que suele doler.
    try:
        from storage import get_storage
        fallos = get_storage(log=log).acciones_recientes(4, solo_fallos=True)
        if fallos:
            detalle = "; ".join(f["orden"][:40] or f["comando"][:40] for f in fallos)
            partes.append(f"Ayer fallaron: {detalle}")
    except Exception:
        pass

    # 5. Qué suele pedir a esta hora.
    try:
        import prediccion
        sugerencia = prediccion.frase_sugerencia(log=log)
        if sugerencia:
            partes.append(sugerencia)
    except Exception:
        pass

    # 6. Recados sin leer.
    try:
        import recados
        resumen_recados = recados.resumen(marcar_leidos=False)
        if "no hay recados" not in resumen_recados.lower():
            partes.append(resumen_recados[:200])
    except Exception:
        pass

    if not partes:
        return "Buenos días, señor. Todo tranquilo: nada que reportar."
    saludo = "Buenos días, señor." if datetime.now().hour < 13 else "Al día, señor."
    return saludo + " " + " ".join(partes)


# ── preparación anticipada ──────────────────────────────────────────────────
def _proxima_cita(core, horas: int = 3, log=print) -> str:
    """Texto de la próxima cita dentro de N horas, o cadena vacía."""
    texto = _orden(core, "que tengo hoy")
    if not texto:
        return ""
    ahora = datetime.now()
    limite = ahora + timedelta(hours=horas)
    for hora, minuto, resto in re.findall(r"(\d{1,2})[:.](\d{2})\s*([^;,\n]{0,60})", texto):
        try:
            momento = ahora.replace(hour=int(hora), minute=int(minuto),
                                    second=0, microsecond=0)
        except ValueError:
            continue
        if ahora < momento <= limite:
            return f"{hora}:{minuto} {resto.strip()}"
    return ""


def preparar_para(core, cita: str = "", log=print) -> str:
    """Abre lo que el señor suele abrir antes de algo así. Nunca a ciegas."""
    if not cita:
        cita = _proxima_cita(core, log=log)
    if not cita:
        return "No veo nada inminente en su agenda, señor."

    try:
        import prediccion
        candidatas = prediccion.sugerencias(log=log)
    except Exception:
        candidatas = []

    if not candidatas:
        return (f"Tiene «{cita}» a la vista, señor. Todavía no sé qué suele "
                "preparar para algo así; dígamelo una vez y lo recordaré.")

    # Solo se ofrece; ejecutar sin permiso es lo que hace odiosos a los
    # asistentes que se adelantan.
    ofrecidas = ", ".join(f"«{orden}»" for orden, _v, _c in candidatas[:3])
    return (f"Tiene «{cita}» a la vista, señor. A esta hora suele pedirme "
            f"{ofrecidas}. ¿Se lo preparo?")


def ejecutar_preparacion(core, log=print) -> str:
    """Ejecuta de verdad la preparación (cuando el señor dice que sí)."""
    try:
        import prediccion
        candidatas = prediccion.sugerencias(log=log)
    except Exception:
        candidatas = []
    if not candidatas:
        return "No tengo nada que preparar, señor."
    hechas = []
    for orden, _veces, _conf in candidatas[:3]:
        r = _orden(core, orden)
        if r:
            hechas.append(orden)
    if not hechas:
        return "No he podido preparar nada, señor."
    return "Preparado, señor: " + ", ".join(hechas) + "."


# ── enlace con el turno de noche ────────────────────────────────────────────
def tareas_segun_agenda(core, log=print) -> list:
    """Qué conviene hacer esta noche según lo que haya mañana.

    Si mañana hay algo temprano, la rutina se acorta para no dejar el equipo
    ocupado a las siete; si no hay nada, se hace todo.
    """
    manana = _orden(core, "que tengo mañana")
    temprano = bool(re.search(r"\b(0?[5-8])[:.]\d{2}", manana or ""))
    if temprano:
        log("[ORQUESTADOR] Mañana hay algo temprano: turno de noche corto.")
        return ["descargas", "memoria", "copia"]
    return None      # None = todas las tareas
