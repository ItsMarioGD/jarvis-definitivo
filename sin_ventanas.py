"""
sin_ventanas.py - Que JARVIS no abra ventanas negras de consola
================================================================
JARVIS corre en segundo plano con pythonw, sin consola. En Windows, cada
programa de consola que se lanza desde ahi (powershell, tailscale, netsh,
ping...) abre SU PROPIA ventana negra, que aparece y desaparece. Emparejar el
movil preguntaba a PowerShell y a Tailscale cada pocos segundos: una lluvia de
ventanas de cmd encima de lo que el señor estuviera haciendo.

activar() hace que todo lo que lance este proceso salga oculto, salvo lo que
pida una consola a proposito (CREATE_NEW_CONSOLE o DETACHED_PROCESS). Los
programas con ventana propia (el bloc de notas, el navegador...) no cambian:
la bandera solo afecta a los de consola.
"""
import os
import subprocess

CREATE_NO_WINDOW = 0x08000000
_PIDE_CONSOLA = 0x00000010 | 0x00000008     # CREATE_NEW_CONSOLE | DETACHED_PROCESS


def _ajustar(args, kwargs) -> dict:
    """Añade CREATE_NO_WINDOW salvo que se pida consola a propósito."""
    # creationflags es el argumento 14 de Popen: nadie lo pasa por posición,
    # pero si alguien lo hiciera no se toca.
    if len(args) < 14:
        banderas = kwargs.get("creationflags", 0) or 0
        if not banderas & _PIDE_CONSOLA:
            kwargs["creationflags"] = banderas | CREATE_NO_WINDOW
    return kwargs


def envolver(clase):
    """Hace que `clase` (subprocess.Popen) lance sin ventana. Idempotente."""
    if getattr(clase, "_sin_ventanas", False):
        return
    original = clase.__init__

    def __init__(self, *args, **kwargs):
        original(self, *args, **_ajustar(args, kwargs))

    clase.__init__ = __init__
    clase._sin_ventanas = True


def activar():
    """Solo en Windows: fuera de él no existen esas ventanas."""
    if os.name == "nt":
        envolver(subprocess.Popen)
