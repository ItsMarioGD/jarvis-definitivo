#!/usr/bin/env python3
"""
cognition/__init__.py — CognitionHub: fachada única sobre los motores de la
capa de cognición (Fase 1+2): clasificación de intención (ml_engine),
clustering temático (cluster_engine), evaluación de riesgo/decisiones
(decision_engine) y ejecución auditada de shell (shell_ops).

jarvis_core.py solo habla con este hub — nunca con los motores sueltos —
así que si alguno de ellos falla al cargar (p. ej. sklearn no instalado),
el hub sigue funcionando con los demás en vez de tumbar toda la cognición.
"""
from cognition.ml_engine import MLEngine
from cognition.cluster_engine import ClusterEngine
from cognition.decision_engine import DecisionEngine
from cognition.shell_ops import ShellOps


class CognitionHub:
    """Punto de entrada único a la capa de cognición de Jarvis."""

    def __init__(self, log=print, db=None):
        self.log = log
        self._db = db
        self.ml = MLEngine(log=log)
        self.cluster = ClusterEngine(log=log, db=db)
        self.decision = DecisionEngine(log=log, db=db)
        self.shell = ShellOps(log=log, db=db, riesgo=self.decision)

    def clasificar_intencion(self, texto: str):
        """Intención probable del texto de usuario, o None si no hay señal clara."""
        return self.ml.clasificar(texto)

    def evaluar_riesgo(self, comando: str):
        """Nivel de riesgo/motivo/mitigación de un comando, sin ejecutarlo."""
        return self.decision.evaluar(comando)

    def ejecutar_shell(self, comando: str, confirmar=None):
        """Ejecuta un comando de shell con validación de riesgo y auditoría."""
        return self.shell.ejecutar(comando, confirmar=confirmar)

    def temas_dominantes(self, n: int = 3):
        """Temas dominantes detectados en las interacciones del usuario."""
        return self.cluster.temas_dominantes(n=n)

    def reentrenar_cluster(self, textos=None, n_clusters=None):
        """Reentrena el clustering; sin `textos`, usa el historial de storage."""
        if textos is None and self._db is not None:
            filas = self._db.ultimas_interacciones(limite=500)
            textos = [f[1] for f in filas if f[1]]
        if not textos:
            return False
        return self.cluster.entrenar(textos, n_clusters=n_clusters)
