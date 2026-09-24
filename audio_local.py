"""
audio_local.py - La voz de JARVIS suena dentro de JARVIS
========================================================
Antes, si pygame no podia reproducir (no instalado, o el mezclador sin
iniciar, como pasaba siempre con Piper), la voz se le pasaba a Windows con
os.startfile y Windows abria su reproductor de audio con cada frase.

reproducir() nunca abre ningun programa: prueba pygame y, en Windows, el
reproductor MCI del propio sistema (winmm), que suena dentro de este proceso
sin ventana. Si ninguno puede, devuelve False y quien llama sigue con otra voz.
"""
import os
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

_ALIAS = "jarvis_voz"
_parar = threading.Event()
_turno = threading.Lock()        # una frase detras de otra
_sin_pygame = False
_mci = None


def callar():
    """Corta la frase que este sonando."""
    _parar.set()


def reproducir(ruta: str) -> bool:
    """Reproduce el audio (WAV o MP3) y espera a que acabe o a callar().

    False si en este equipo no hay forma de reproducirlo aqui dentro.
    """
    if not ruta or not os.path.exists(ruta):
        return False
    with _turno:
        _parar.clear()
        return _con_pygame(ruta) or _con_mci(ruta)


def _con_pygame(ruta: str) -> bool:
    global _sin_pygame
    if _sin_pygame:
        return False
    try:
        import pygame
    except Exception:
        _sin_pygame = True
        return False
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(ruta)
        pygame.mixer.music.play()
    except Exception:
        return False
    try:
        while pygame.mixer.music.get_busy():
            if _parar.wait(0.05):
                pygame.mixer.music.stop()
                break
        pygame.mixer.music.unload()
    except Exception:
        pass
    return True


def _hay_mci() -> bool:
    return os.name == "nt"


def _orden_mci(orden: str):
    """Manda una orden MCI. Devuelve la respuesta, o None si falla."""
    global _mci
    import ctypes
    if _mci is None:
        from ctypes import wintypes
        _mci = ctypes.WinDLL("winmm").mciSendStringW
        _mci.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HANDLE]
        _mci.restype = wintypes.DWORD
    respuesta = ctypes.create_unicode_buffer(256)
    if _mci(orden, respuesta, len(respuesta), None) != 0:
        return None
    return respuesta.value


def _con_mci(ruta: str) -> bool:
    if not _hay_mci():
        return False
    tipo = "waveaudio" if ruta.lower().endswith(".wav") else "mpegvideo"
    try:
        _orden_mci(f"close {_ALIAS}")          # por si quedo abierto de antes
        if _orden_mci(f'open "{ruta}" type {tipo} alias {_ALIAS}') is None:
            return False
    except Exception:
        return False
    try:
        _orden_mci(f"set {_ALIAS} time format milliseconds")
        largo = _orden_mci(f"status {_ALIAS} length") or ""
        # Tope por si el dispositivo nunca dice que ha terminado.
        tope = time.monotonic() + 3.0 + (int(largo) / 1000.0 if largo.isdigit() else 120.0)
        if _orden_mci(f"play {_ALIAS}") is None:
            return False
        while not _parar.wait(0.05) and time.monotonic() < tope:
            if _orden_mci(f"status {_ALIAS} mode") not in ("playing", "seeking", "not ready"):
                break
        return True
    except Exception:
        return False
    finally:
        try:
            _orden_mci(f"stop {_ALIAS}")
            _orden_mci(f"close {_ALIAS}")
        except Exception:
            pass
