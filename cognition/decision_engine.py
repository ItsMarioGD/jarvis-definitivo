#!/usr/bin/env python3
"""
cognition/decision_engine.py - Árbol de decisión y gestión de riesgo (Fase 2)
===============================================================================
Soft skill: "Pensamiento Analítico & Toma de Decisiones".

Antes de ejecutar una acción crítica, Jarvis evalúa múltiples caminos:
  1. identificar el tipo de operación (archivo/sistema/red/proceso/registro)
  2. calcular el nivel de riesgo (bajo/medio/alto/bloqueado) con su motivo
  3. proponer mitigación y, para riesgo alto, exigir confirmación explícita

Toda decisión queda registrada (audit_log) para trazabilidad.
"""
import re
import time


class DecisionEngine:
    """Evaluador de riesgo de acciones del usuario."""

    def __init__(self, log=print, db=None):
        self.log = log
        self._db = db

    # reglas: (regex, nivel, motivo, mitigacion)
    _REGLAS = [
        (re.compile(r"format|fdisk|diskpart|rm\s+-rf|rd\s+/s|del\s+/[sfq]|reg\s+delete"),
         "bloqueado", "destrucción irreversible de datos", "ninguna (bloqueado por diseño)"),
        (re.compile(r"shutdown|reiniciar|apagar"), "alto",
         "apagado/reinicio del sistema", "guardar trabajo antes de continuar"),
        (re.compile(r"del\s+.*(?:windows|system32|program files)", re.I),
         "bloqueado", "borrado en directorios críticos", "ninguna (bloqueado por diseño)"),
        (re.compile(r"taskkill|kill\s+-9|stop-process"),
         "alto", "terminación de procesos", "verificar que no sea un proceso del sistema"),
        (re.compile(r"netsh\s+wlan\s+connect|sc\s+stop|net\s+user"),
         "medio", "cambio de configuración de red/servicios", "se puede revertir con el comando inverso"),
        (re.compile(r"del\s+|remove-item|borra.*archivo"),
         "medio", "eliminación de archivos (va a papelera si es posible)",
         "el archivo se mueve a la papelera antes de borrado definitivo"),
        (re.compile(r"copy|move|ren\s+|mkdir|echo\s+>|type\s+>" ),
         "bajo", "operación de archivos no destructiva", "ninguna"),
        (re.compile(r"ipconfig|systeminfo|ping|dir|list\s+.*(?:archivo|proceso)"),
         "bajo", "consulta de información", "ninguna"),
    ]
    _DEFECTO = ("medio", "operación no clasificada", "comprobar la salida tras ejecutar")

    def evaluar(self, comando: str):
        """Devuelve dict: {nivel, motivo, mitigacion}."""
        c = comando.strip().lower()
        for rx, nivel, motivo, mitig in self._REGLAS:
            if rx.search(c):
                return {"nivel": nivel, "motivo": motivo, "mitigacion": mitig}
        nivel, motivo, mitig = self._DEFECTO
        return {"nivel": nivel, "motivo": motivo, "mitigacion": mitig}

    def decidir(self, comando: str, confirmar=None):
        """Árbol completo: evalúa, y si es alto pide confirmación.

        confirmar: callable(pregunta) -> bool. Devuelve dict con la decisión.
        """
        r = self.evaluar(comando)
        accion = "ejecutar"
        if r["nivel"] == "bloqueado":
            accion = "bloquear"
        elif r["nivel"] == "alto":
            if confirmar is not None:
                accion = "ejecutar" if confirmar(
                    f"Acción de alto riesgo ({r['motivo']}). ¿Confirmo {comando}?") \
                    else "rechazar"
            else:
                accion = "requiere confirmación"
        self._registrar(comando, r["nivel"], accion)
        return {**r, "decision": accion}

    def _registrar(self, comando, nivel, accion):
        if self._db is None:
            return
        try:
            self._db.auditar(f"[decision] {comando}", f"{nivel} -> {accion}", nivel)
        except Exception as e:
            self.log(f"decision: auditoría: {e}")