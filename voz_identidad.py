#!/usr/bin/env python3
"""
voz_identidad.py - ¿Quien esta hablando?
========================================
ULTRON reconoce la CARA del señor con el guardian facial, pero su VOZ no la
reconoce nadie. Con la escucha continua encendida, eso significa que cualquiera
que entre en la habitacion y diga «Jarvis, apaga el pc» es obedecido igual que
el dueño. Un microfono siempre abierto sin identidad es un agujero.

Como funciona
-------------
Se calcula una huella de voz a partir del espectro (banco de filtros mel hecho
con numpy, sin dependencias nuevas) y se compara con la registrada. Es una
huella modesta: distingue bien «el señor» de «otra persona» con el mismo
microfono y en la misma habitacion, que es justo el caso de uso. No pretende
ser biometria forense, y se dice claramente en vez de aparentar lo contrario.

Si estan instalados `resemblyzer` o `librosa`, se usan en su lugar y la
precision sube bastante; no hacen falta para que esto funcione.

Uso tipico
----------
    registrar(varios_wav)      una vez, con 3-5 frases del señor
    verificar(wav)             -> (es_el_señor, parecido)
    exigir_para_criticas       preferencia: si esta activa, las ordenes
                               destructivas solo se obedecen si la voz coincide
"""
import io
import json
import os
import wave

import numpy as np

PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
HUELLA = os.path.join(PREFS, "huella_voz.json")
UMBRAL = float(os.getenv("JARVIS_VOZ_UMBRAL", "0.82"))
N_MEL = 40


# ── señal ───────────────────────────────────────────────────────────────────
def _leer_wav(datos: bytes):
    """(muestras float32 mono, frecuencia). Acepta bytes de un WAV PCM."""
    with wave.open(io.BytesIO(datos), "rb") as w:
        canales = w.getnchannels()
        ancho = w.getsampwidth()
        frecuencia = w.getframerate()
        crudo = w.readframes(w.getnframes())
    if ancho != 2:
        raise ValueError("solo se admite WAV de 16 bits")
    señal = np.frombuffer(crudo, dtype=np.int16).astype(np.float32) / 32768.0
    if canales > 1:
        señal = señal.reshape(-1, canales).mean(axis=1)
    return señal, frecuencia


def _banco_mel(n_fft: int, frecuencia: int, n_mel: int = N_MEL):
    """Banco de filtros mel en numpy puro (evita depender de librosa)."""
    def a_mel(hz):
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def a_hz(mel):
        return 700.0 * (10 ** (mel / 2595.0) - 1.0)

    bordes = a_hz(np.linspace(a_mel(80), a_mel(min(7600, frecuencia // 2)), n_mel + 2))
    bins = np.floor((n_fft + 1) * bordes / frecuencia).astype(int)
    banco = np.zeros((n_mel, n_fft // 2 + 1), dtype=np.float32)
    for i in range(1, n_mel + 1):
        izq, centro, der = bins[i - 1], bins[i], bins[i + 1]
        if centro == izq:
            centro = izq + 1
        if der <= centro:
            der = centro + 1
        for k in range(izq, min(centro, banco.shape[1])):
            banco[i - 1, k] = (k - izq) / max(centro - izq, 1)
        for k in range(centro, min(der, banco.shape[1])):
            banco[i - 1, k] = (der - k) / max(der - centro, 1)
    return banco


def caracteristicas(datos_wav: bytes, log=print):
    """Huella de voz: media y desviación del espectro mel, normalizadas."""
    # Motores mejores, si el señor los tiene instalados.
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
        señal, frecuencia = _leer_wav(datos_wav)
        vector = VoiceEncoder().embed_utterance(preprocess_wav(señal, frecuencia))
        return np.asarray(vector, dtype=np.float32)
    except Exception:
        pass
    try:
        import librosa
        señal, frecuencia = _leer_wav(datos_wav)
        mfcc = librosa.feature.mfcc(y=señal, sr=frecuencia, n_mfcc=20)
        return np.concatenate([mfcc.mean(axis=1), mfcc.std(axis=1)]).astype(np.float32)
    except Exception:
        pass

    # Camino por defecto: numpy y nada más.
    señal, frecuencia = _leer_wav(datos_wav)
    if señal.size < frecuencia // 4:
        raise ValueError("el audio es demasiado corto (menos de 0,25 s)")

    # Quitar silencios: los espacios en blanco no identifican a nadie.
    ventana = int(0.02 * frecuencia)
    energia = np.array([np.abs(señal[i:i + ventana]).mean()
                        for i in range(0, len(señal) - ventana, ventana)])
    if energia.size:
        umbral = max(energia.mean() * 0.35, 1e-4)
        trozos = [señal[i * ventana:(i + 1) * ventana]
                  for i, e in enumerate(energia) if e > umbral]
        if trozos:
            señal = np.concatenate(trozos)

    n_fft, salto = 512, 256
    banco = _banco_mel(n_fft, frecuencia)
    ventana_hann = np.hanning(n_fft).astype(np.float32)
    marcos = []
    for i in range(0, len(señal) - n_fft, salto):
        trozo = señal[i:i + n_fft] * ventana_hann
        espectro = np.abs(np.fft.rfft(trozo)) ** 2
        marcos.append(np.log(banco @ espectro + 1e-8))
    if not marcos:
        raise ValueError("no hay voz suficiente en el audio")
    matriz = np.stack(marcos)
    vector = np.concatenate([matriz.mean(axis=0), matriz.std(axis=0)])
    norma = np.linalg.norm(vector)
    return (vector / norma).astype(np.float32) if norma else vector.astype(np.float32)


def _parecido(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if not na or not nb:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ── registro y verificación ─────────────────────────────────────────────────
def registrar(muestras_wav, log=print) -> str:
    """Guarda la huella del señor a partir de varias frases suyas."""
    vectores = []
    for i, datos in enumerate(muestras_wav, 1):
        try:
            vectores.append(caracteristicas(datos, log=log))
        except Exception as e:
            log(f"[VOZ] Muestra {i} descartada: {e}")
    if len(vectores) < 2:
        return ("Necesito al menos dos frases claras suyas, señor. "
                "Dígame algo de cinco segundos un par de veces.")

    plantilla = np.mean(np.stack(vectores), axis=0)
    dispersion = float(np.mean([_parecido(v, plantilla) for v in vectores]))
    os.makedirs(PREFS, exist_ok=True)
    with open(HUELLA, "w", encoding="utf-8") as f:
        json.dump({"plantilla": plantilla.tolist(), "muestras": len(vectores),
                   "coherencia": round(dispersion, 3)}, f)
    return (f"Voz registrada, señor: {len(vectores)} muestras, coherencia "
            f"{dispersion:.2f}. Ya distingo su voz de la de otros.")


def _plantilla():
    try:
        with open(HUELLA, encoding="utf-8") as f:
            datos = json.load(f)
        return np.asarray(datos.get("plantilla") or [], dtype=np.float32)
    except Exception:
        return np.asarray([], dtype=np.float32)


def hay_huella() -> bool:
    return _plantilla().size > 0


def verificar(datos_wav: bytes, log=print, umbral: float = UMBRAL):
    """(es_el_señor, parecido). Sin huella registrada devuelve (True, 0.0)."""
    plantilla = _plantilla()
    if plantilla.size == 0:
        return True, 0.0        # sin registro no se bloquea nada
    try:
        vector = caracteristicas(datos_wav, log=log)
    except Exception as e:
        log(f"[VOZ] No pude analizar la voz: {e}")
        return True, 0.0        # ante la duda, no se niega el servicio
    parecido = _parecido(vector, plantilla)
    return parecido >= umbral, round(parecido, 3)


def exige_verificacion(core, texto: str) -> bool:
    """¿Esta orden es de las que solo debe poder dar el señor?"""
    try:
        if (core.get_pref("exigir_voz") or "0") != "1":
            return False
    except Exception:
        return False
    criticas = ("apaga", "reinicia", "borra", "elimina", "formatea", "desinstala",
                "transfiere", "compra", "manda", "envia", "publica")
    t = (texto or "").lower()
    return any(p in t for p in criticas)


def estado() -> dict:
    plantilla = _plantilla()
    motor = "numpy (básico)"
    try:
        import resemblyzer  # noqa: F401
        motor = "resemblyzer (preciso)"
    except Exception:
        try:
            import librosa  # noqa: F401
            motor = "librosa (medio)"
        except Exception:
            pass
    return {"registrada": plantilla.size > 0, "dimensiones": int(plantilla.size),
            "umbral": UMBRAL, "motor": motor, "archivo": HUELLA}
