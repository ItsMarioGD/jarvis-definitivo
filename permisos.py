#!/usr/bin/env python3
"""
permisos.py - Qué puede hacer el agente sin preguntar y qué no
============================================================
El bucle de `herramientas_llm.py` ejecutaba TODO lo que el modelo pedía. Con
escritura de ficheros, `git_commit`, envío de correo y shell por medio, eso es
demasiada confianza en una sola frase mal entendida.

Aquí cada herramienta tiene una política:

    directo     se ejecuta sin más (lectura, cosas triviales y reversibles)
    confirmar   se PARA y se le pide al señor un «confirma» explícito
    prohibido   no se ejecuta nunca desde el bucle del modelo

Modos de operación (JARVIS_AGENTE_MODO o Prefs/permisos.json -> "modo"):

    normal   respeta la tabla (por defecto)
    auto     todo lo que no sea "prohibido" pasa como "directo"
    lectura  solo se permiten herramientas de lectura; el resto se niega

Prefs/permisos.json puede sobreescribir políticas por herramienta:
    {"modo": "normal", "politicas": {"git_commit": "directo"}}
"""
import json
import os

_CFG = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "permisos.json")

# Lectura pura: nunca cambian nada.
_LECTURA = {
    "estado_pc", "listar_procesos", "leer_notas", "clima", "agenda_dia",
    "buscar_archivos", "buscar_web", "recados_pendientes", "buscar_en_documentos",
    "mirar_pantalla", "ensayar_orden", "ensayar_orden_movil", "leer_archivo",
    "listar_dir", "buscar_en_archivos", "git_estado", "git_diff", "revisar_pr",
    "revisar_correo", "analizar_imagen", "analizar_documento", "buscar_en_memoria",
}

# Efecto real: se paran y piden confirmación en modo normal.
_CONFIRMAR = {
    "escribir_archivo", "editar_archivo", "mover_archivos", "organizar_descargas",
    "cerrar_app", "cerrar_proceso", "apagar_equipo", "reiniciar_equipo",
    "bloquear_equipo", "ajustar_volumen", "enviar_telegram", "enviar_correo",
    "git_crear_rama", "git_commit", "correr_tests", "pilotar_pantalla",
    "reproducir_musica", "analizar_con_codigo", "delegar_subtarea",
    "procesar_reunion", "automejorar", "mision_larga",
}

# Todo lo demás (abrir_app, crear_nota, temporizador, recordatorio, captura,
# deshacer_ultimo, orden_libre, mcp__*...) queda en "directo".

_POR_DEFECTO = "directo"


def _config() -> dict:
    try:
        with open(_CFG, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def modo() -> str:
    m = (os.getenv("JARVIS_AGENTE_MODO") or _config().get("modo") or "normal").lower()
    return m if m in ("normal", "auto", "lectura") else "normal"


def es_lectura(nombre: str) -> bool:
    return nombre in _LECTURA


def evaluar(nombre: str) -> str:
    """'directo' | 'confirmar' | 'prohibido' para esta herramienta y el modo activo."""
    override = (_config().get("politicas") or {}).get(nombre)
    base = override or (
        "directo" if nombre in _LECTURA else
        "confirmar" if nombre in _CONFIRMAR else
        _POR_DEFECTO)

    m = modo()
    if m == "auto":
        return "directo" if base != "prohibido" else "prohibido"
    if m == "lectura":
        return "directo" if nombre in _LECTURA else "prohibido"
    return base


AFIRMACIONES = (
    "confirma", "confirmado", "confirmo", "adelante", "hazlo", "procede",
    "si procede", "sí procede", "dale", "correcto", "de acuerdo", "ok hazlo",
    "venga", "sigue", "continua", "continúa",
)


def es_afirmacion(texto: str) -> bool:
    t = (texto or "").strip().lower()
    if not t:
        return False
    return any(a in t for a in AFIRMACIONES) or t in ("si", "sí", "ok", "vale")
