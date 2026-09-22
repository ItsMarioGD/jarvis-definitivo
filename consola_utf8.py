"""
consola_utf8.py - Que la consola de Windows no tumbe los scripts.

La consola de Windows usa cp1252 por defecto, y cp1252 no sabe representar ni
las flechas (->) ni las comillas angulares que aparecen en los mensajes de
ayuda. Al intentar imprimirlas, Python lanza UnicodeEncodeError y el script
muere con un traceback justo cuando estaba explicando como arreglar algo. Es
decir: el mensaje de ayuda mataba al programa que iba a dar la ayuda.

Basta con importar este modulo lo primero:

    import consola_utf8  # noqa: F401

Intenta poner la salida en UTF-8 y, si la consola no lo admite, al menos deja
que los caracteres raros se sustituyan por «?» en vez de reventar.
"""
import sys


def _preparar(flujo):
    if flujo is None:
        return
    try:
        # errors="replace" es lo que garantiza que nunca vuelva a fallar:
        # pase lo que pase, el mensaje se imprime.
        flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            flujo.reconfigure(errors="replace")
        except Exception:
            pass


def preparar_consola():
    """Deja stdout y stderr a prueba de caracteres no representables."""
    # En Windows, pedirle a la consola la pagina de codigos UTF-8 hace que
    # ademas se vean bien, no solo que no falle.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass
    _preparar(sys.stdout)
    _preparar(sys.stderr)


preparar_consola()
