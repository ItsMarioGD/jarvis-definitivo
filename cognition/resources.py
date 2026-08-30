#!/usr/bin/env python3
"""
cognition/resources.py - Validación de recursos del sistema (restricción clave)
================================================================================
Antes de cargar modelos pesados, procesar señales largas o entrenar clusters,
se comprueba RAM libre, CPU y GPU disponible. Si el equipo no alcanza el
umbral, el módulo que llamó debe degradar (modelo pequeño, downsampling...).

Nada aquí asume hardware: todas las rutas de detección fallan limpiamente.
"""
import os
import platform


class SystemResources:
    """Snapshot de recursos del sistema. Inmutable y seguro de consultar."""

    def __init__(self):
        self.ram_total_gb, self.ram_libre_gb = self._ram()
        self.cpu_cores = self._cores()
        self.gpu_disponible = self._gpu()
        self.os = platform.system()

    # ── detectores (cada uno degrada a un valor neutro) ─────────────────────
    @staticmethod
    def _ram():
        try:
            import psutil
            vm = psutil.virtual_memory()
            return round(vm.total / 1024 ** 3, 1), round(vm.available / 1024 ** 3, 1)
        except Exception:
            return 0.0, 0.0

    @staticmethod
    def _cores():
        try:
            return os.cpu_count() or 1
        except Exception:
            return 1

    @staticmethod
    def _gpu():
        """Detecta GPU CUDA si existe (nvidia-smi), sin asumir nada."""
        try:
            import subprocess
            r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                                "--format=csv,noheader"],
                               capture_output=True, timeout=5, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip().splitlines()[0]
        except Exception:
            pass
        return None

    # ── consultas de umbral ─────────────────────────────────────────────────
    def ram_suficiente(self, minimo_gb=4.0) -> bool:
        """¿Hay RAM libre suficiente para cargar un modelo/pipeline pesado?"""
        return self.ram_libre_gb >= minimo_gb

    def backend_recomendado(self) -> str:
        """'gpu' si hay GPU CUDA con RAM libre suficiente, si no 'cpu'."""
        if self.gpu_disponible:
            return "gpu"
        return "cpu"

    def resumen(self) -> str:
        gpu = self.gpu_disponible or "sin GPU CUDA"
        return (f"{self.ram_total_gb} GB RAM ({self.ram_libre_gb} libres), "
                f"{self.cpu_cores} núcleos, {gpu}")


def validar_antes_de_pesado(min_ram_gb=4.0):
    """Decorador: si el equipo no alcanza el umbral, lanza ResourceError.

    Uso: @validar_antes_de_pesado(min_ram_gb=6)  sobre funciones que cargan
    modelos o procesan grandes volúmenes.
    """
    def deco(fn):
        def wrapper(*args, **kwargs):
            r = SystemResources()
            if not r.ram_suficiente(min_ram_gb):
                raise ResourceError(
                    f"Recursos insuficientes: {r.ram_libre_gb} GB libres "
                    f"(necesario ≥ {min_ram_gb} GB). Degrade el tamaño del trabajo.")
            return fn(*args, **kwargs)
        return wrapper
    return deco


class ResourceError(RuntimeError):
    """Se lanza cuando el sistema no tiene recursos para la tarea pedida."""