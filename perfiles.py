#!/usr/bin/env python3
"""
perfiles.py - Perfiles de contexto (trabajo, juego, noche, invitado)
====================================================================
El proyecto tenia `modo_gaming`, `modo_noche`, `modo_invitado`, `modo_dictado` y
`modo_enfoque` como habilidades sueltas: cada una tocaba una cosa y ninguna
sabia de las demas. Al final el señor acababa encadenando cuatro ordenes para
ponerse a trabajar y otras cuatro para dejarlo.

Un perfil agrupa todo lo que cambia a la vez:

    verbosidad     cuanto habla (respuestas cortas mientras juegas)
    proactividad   si puede interrumpir, y con que umbral
    voz            si habla o solo escribe
    escucha        si el microfono sigue atento
    acciones       ordenes que se ejecutan al entrar y al salir del perfil

Cambiar de perfil es una sola frase, y volver atras tambien: al salir se
restaura lo que habia antes, no unos valores por defecto inventados.
"""
import json
import os

PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
ESTADO = os.path.join(PREFS, "perfil_actual.json")

PERFILES = {
    "trabajo": {
        "descripcion": "concentración: pocas interrupciones y respuestas al grano",
        "prefs": {"avisos_proactivos": "1", "voz_windows": "off"},
        "enjambre_umbral": 0.85,
        "verbosidad": "breve",
        "al_entrar": ["modo enfoque"],
        "al_salir": [],
    },
    "juego": {
        "descripcion": "nada de interrupciones y el equipo a pleno rendimiento",
        "prefs": {"avisos_proactivos": "0", "escucha_continua": "0"},
        "enjambre_umbral": 0.95,
        "verbosidad": "minima",
        "al_entrar": ["modo gaming"],
        "al_salir": [],
    },
    "noche": {
        "descripcion": "voz baja, pantalla suave y sin avisos salvo urgencias",
        "prefs": {"avisos_proactivos": "1"},
        "enjambre_umbral": 0.9,
        "verbosidad": "breve",
        "al_entrar": ["modo noche"],
        "al_salir": [],
    },
    "invitado": {
        "descripcion": "sin memoria personal ni acciones destructivas",
        "prefs": {"exigir_voz": "1", "avisos_proactivos": "0",
                  "escucha_continua": "0"},
        "enjambre_umbral": 1.0,
        "verbosidad": "normal",
        "al_entrar": ["modo invitado"],
        "al_salir": [],
    },
    "normal": {
        "descripcion": "el comportamiento de siempre",
        "prefs": {"avisos_proactivos": "1"},
        "enjambre_umbral": 0.7,
        "verbosidad": "normal",
        "al_entrar": [],
        "al_salir": [],
    },
}

CLAVES_GUARDADAS = ("avisos_proactivos", "escucha_continua", "voz_windows",
                    "exigir_voz", "stt_local")


def _leer_estado() -> dict:
    try:
        with open(ESTADO, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _guardar_estado(datos: dict):
    os.makedirs(PREFS, exist_ok=True)
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def actual() -> str:
    return _leer_estado().get("perfil", "normal")


def activar(core, nombre: str, log=print) -> str:
    """Cambia de perfil guardando antes lo que había, para poder volver."""
    nombre = (nombre or "").strip().lower()
    if nombre not in PERFILES:
        return (f"No conozco el perfil «{nombre}», señor. Tengo: "
                + ", ".join(PERFILES) + ".")

    perfil = PERFILES[nombre]
    estado = _leer_estado()

    # Solo se guarda el «antes» la primera vez que se sale de normal: si no,
    # encadenar dos perfiles haría perder el estado original.
    if not estado.get("anterior"):
        anterior = {}
        for clave in CLAVES_GUARDADAS:
            try:
                anterior[clave] = core.get_pref(clave) or ""
            except Exception:
                pass
        estado["anterior"] = anterior

    for clave, valor in perfil["prefs"].items():
        try:
            core.set_pref(clave, valor)
        except Exception as e:
            log(f"[PERFILES] No pude poner {clave}: {e}")

    # Umbral de interrupción del enjambre.
    try:
        if getattr(core, "enjambre", None) is not None:
            core.enjambre.umbral = perfil["enjambre_umbral"]
    except Exception:
        pass

    hechas = []
    for orden in perfil["al_entrar"]:
        r = _orden(core, orden)
        if r:
            hechas.append(orden)

    estado["perfil"] = nombre
    _guardar_estado(estado)

    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "perfil", f"Perfil {nombre}", perfil["descripcion"], gravedad="info",
            agente=getattr(core, "nombre_agente", "JARVIS"))
    except Exception:
        pass

    extra = f" He aplicado además: {', '.join(hechas)}." if hechas else ""
    return f"Perfil {nombre} activo, señor: {perfil['descripcion']}.{extra}"


def restaurar(core, log=print) -> str:
    """Vuelve exactamente al estado anterior al primer cambio de perfil."""
    estado = _leer_estado()
    anterior = estado.get("anterior") or {}
    if not anterior and estado.get("perfil", "normal") == "normal":
        return "Ya estaba en el perfil normal, señor."

    for clave, valor in anterior.items():
        try:
            core.set_pref(clave, valor)
        except Exception:
            pass
    try:
        if getattr(core, "enjambre", None) is not None:
            core.enjambre.umbral = PERFILES["normal"]["enjambre_umbral"]
    except Exception:
        pass

    _guardar_estado({"perfil": "normal"})
    return "Vuelvo al perfil normal, señor, con los ajustes que tenía antes."


def _orden(core, frase: str):
    for despachador in (getattr(core, "skills", None), getattr(core, "pc", None)):
        if despachador is None:
            continue
        try:
            r = despachador.handle(frase)
        except Exception:
            continue
        if r:
            return r
    return None


def verbosidad(core) -> str:
    """Cuánto debe hablar en el perfil actual (lo usa el prompt del cerebro)."""
    return PERFILES.get(actual(), PERFILES["normal"])["verbosidad"]


def instruccion_prompt(core) -> str:
    """Línea que se añade al prompt para que el tono siga al perfil."""
    nivel = verbosidad(core)
    if nivel == "minima":
        return "[Perfil juego: responde en menos de diez palabras, sin cortesías.]"
    if nivel == "breve":
        return "[Perfil de concentración: una o dos frases, sin rodeos.]"
    return ""


def estado() -> dict:
    datos = _leer_estado()
    nombre = datos.get("perfil", "normal")
    return {"perfil": nombre,
            "descripcion": PERFILES.get(nombre, {}).get("descripcion", ""),
            "disponibles": list(PERFILES),
            "hay_estado_anterior": bool(datos.get("anterior"))}
