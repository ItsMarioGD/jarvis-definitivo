#!/usr/bin/env python3
"""
microfono.py - Micrófono del PC sin PyAudio
===========================================
SpeechRecognition solo sabe abrir el micrófono con PyAudio, y PyAudio no tiene
paquete para el Python del proyecto (3.14): pip intenta compilarlo y falla. El
resultado era que la escucha continua y el botón de micrófono de la interfaz
de escritorio decían «falta PyAudio» y JARVIS no oía nada en el PC.

Aquí se graba con la API de audio que Windows trae de serie (winmm, waveIn),
por ctypes: nada que instalar. Si PyAudio sí está, se usa ese, como siempre.

    with microfono.abrir() as fuente:
        audio = reconocedor.listen(fuente)
"""
import ctypes
import sys
import threading
import time

try:
    import speech_recognition as sr
    _Base = sr.AudioSource
except Exception:
    sr = None
    _Base = object

FRECUENCIA = 16000      # lo que piden Whisper y Google; menos datos que 48 kHz
TROZO = 1024            # muestras por lectura (64 ms a 16 kHz)
_MAX_SEGUNDOS = 10      # si nadie lee (transcribiendo), se guarda como mucho esto


def hay_pyaudio() -> bool:
    try:
        import pyaudio  # noqa: F401
        return True
    except Exception:
        return False


def hay_winmm() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return ctypes.windll.winmm.waveInGetNumDevs() > 0
    except Exception:
        return False


def disponible() -> tuple:
    """(bool, motivo). Explica por qué no hay micrófono, si no lo hay."""
    if sr is None:
        return False, "falta la librería SpeechRecognition"
    if hay_pyaudio() or hay_winmm():
        return True, ""
    if sys.platform == "win32":
        return False, "Windows no ve ningún micrófono conectado"
    return False, "falta PyAudio (micrófono)"


def abrir():
    """Fuente de audio para SpeechRecognition: PyAudio si está, si no winmm."""
    if hay_pyaudio():
        return sr.Microphone()
    return MicrofonoWindows()


# ── winmm por ctypes ────────────────────────────────────────────────────────
if sys.platform == "win32":
    from ctypes import wintypes

    class _WAVEFORMATEX(ctypes.Structure):
        _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                    ("nSamplesPerSec", wintypes.DWORD), ("nAvgBytesPerSec", wintypes.DWORD),
                    ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                    ("cbSize", wintypes.WORD)]

    class _WAVEHDR(ctypes.Structure):
        pass

    _WAVEHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
                         ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
                         ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
                         ("lpNext", ctypes.POINTER(_WAVEHDR)), ("reserved", ctypes.c_size_t)]

    _WAVE_MAPPER = 0xFFFFFFFF
    _WHDR_DONE = 0x1
    _HDR = ctypes.sizeof(_WAVEHDR)

    def _winmm():
        w = ctypes.windll.winmm
        w.waveInOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.UINT,
                                 ctypes.POINTER(_WAVEFORMATEX), ctypes.c_size_t,
                                 ctypes.c_size_t, wintypes.DWORD]
        for nombre in ("waveInPrepareHeader", "waveInUnprepareHeader", "waveInAddBuffer"):
            getattr(w, nombre).argtypes = [ctypes.c_void_p, ctypes.POINTER(_WAVEHDR),
                                           wintypes.UINT]
        for nombre in ("waveInStart", "waveInStop", "waveInReset", "waveInClose"):
            getattr(w, nombre).argtypes = [ctypes.c_void_p]
        return w


class _Flujo:
    """Lo que SpeechRecognition espera en `fuente.stream`: read(n) bloqueante."""

    def __init__(self, fuente):
        self._fuente = fuente

    def read(self, muestras: int) -> bytes:
        return self._fuente._leer(muestras)

    def close(self):
        pass


class MicrofonoWindows(_Base):
    """Micrófono por defecto de Windows, 16 kHz mono 16 bits, sin PyAudio."""

    def __init__(self, frecuencia: int = FRECUENCIA, trozo: int = TROZO, buffers: int = 8):
        self.SAMPLE_RATE = frecuencia
        self.SAMPLE_WIDTH = 2
        self.CHUNK = trozo
        self.stream = None
        self._n = buffers
        self._handle = ctypes.c_void_p()
        self._cabeceras = []
        self._datos = []
        self._pendiente = bytearray()
        self._cond = threading.Condition()
        self._parar = threading.Event()
        self._hilo = None
        self._error = None

    def __enter__(self):
        w = _winmm()
        fmt = _WAVEFORMATEX(1, 1, self.SAMPLE_RATE, self.SAMPLE_RATE * 2, 2, 16, 0)
        r = w.waveInOpen(ctypes.byref(self._handle), _WAVE_MAPPER, ctypes.byref(fmt), 0, 0, 0)
        if r != 0:
            raise OSError(f"Windows no pudo abrir el micrófono (waveInOpen={r})")
        try:
            tam = self.CHUNK * 2
            for _ in range(self._n):
                datos = ctypes.create_string_buffer(tam)
                cab = _WAVEHDR()
                cab.lpData = ctypes.cast(datos, ctypes.c_void_p)
                cab.dwBufferLength = tam
                self._datos.append(datos)        # que el recolector no los libere
                self._cabeceras.append(cab)
                self._comprobar(w.waveInPrepareHeader(self._handle, ctypes.byref(cab), _HDR),
                                "preparar búfer")
                self._comprobar(w.waveInAddBuffer(self._handle, ctypes.byref(cab), _HDR),
                                "encolar búfer")
            self._comprobar(w.waveInStart(self._handle), "empezar a grabar")
        except Exception:
            self._cerrar(w)
            raise
        self._parar.clear()
        self._hilo = threading.Thread(target=self._recoger, daemon=True)
        self._hilo.start()
        self.stream = _Flujo(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._parar.set()
        with self._cond:
            self._cond.notify_all()
        if self._hilo is not None:
            self._hilo.join(timeout=2)
        self._cerrar(_winmm())
        self.stream = None

    @staticmethod
    def _comprobar(resultado, que):
        if resultado != 0:
            raise OSError(f"Micrófono: no pude {que} (código {resultado})")

    def _cerrar(self, w):
        if not self._handle:
            return
        try:
            w.waveInReset(self._handle)     # devuelve todos los búferes
            for cab in self._cabeceras:
                w.waveInUnprepareHeader(self._handle, ctypes.byref(cab), _HDR)
            w.waveInClose(self._handle)
        finally:
            self._handle = ctypes.c_void_p()
            self._cabeceras, self._datos = [], []

    def _recoger(self):
        """Saca los búferes que Windows ya llenó y los vuelve a encolar.

        Se recogen en un hilo aparte para no perder audio mientras la escucha
        transcribe: lo que el señor diga en esos segundos se lee después.
        """
        w = _winmm()
        i = 0
        tope = _MAX_SEGUNDOS * self.SAMPLE_RATE * 2
        while not self._parar.is_set():
            cab = self._cabeceras[i]
            if not cab.dwFlags & _WHDR_DONE:
                time.sleep(0.01)
                continue
            trozo = ctypes.string_at(cab.lpData, cab.dwBytesRecorded)
            with self._cond:
                self._pendiente.extend(trozo)
                if len(self._pendiente) > tope:
                    del self._pendiente[:len(self._pendiente) - tope]
                self._cond.notify_all()
            cab.dwFlags &= ~_WHDR_DONE
            cab.dwBytesRecorded = 0
            r = w.waveInAddBuffer(self._handle, ctypes.byref(cab), _HDR)
            if r != 0:
                self._error = f"el micrófono dejó de responder (código {r})"
                with self._cond:
                    self._cond.notify_all()
                return
            i = (i + 1) % self._n

    def _leer(self, muestras: int) -> bytes:
        falta = muestras * self.SAMPLE_WIDTH
        with self._cond:
            while len(self._pendiente) < falta:
                if self._error:
                    raise OSError(self._error)
                if self._parar.is_set():
                    raise OSError("micrófono cerrado")
                self._cond.wait(timeout=1.0)
            trozo = bytes(self._pendiente[:falta])
            del self._pendiente[:falta]
        return trozo
