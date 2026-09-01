#!/usr/bin/env python3
"""
jarvis_piper.py - Voz neuronal gratuita (Piper TTS, es_ES-davefx-medium).
Adaptado de isair/jarvis (output/tts.py): el modelo (~63 MB, offline) se
descarga de HuggingFace la primera vez y se cachea en
Descargas\\JARVIS\\Voz\\piper. Si algo falla, devuelve False y la cadena
de voz normal de Jarvis continúa.

Uso:
    from jarvis_piper import hablar, descargar_modelo, get_info
    hablar("Hola señor, sistemas operativos.")
"""
import os
import tempfile
import threading
import time
import wave
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Configuración de voces disponibles
VOICES = {
    "es_ES-davefx-medium": {
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium",
        "size_mb": 63,
        "quality": "high",
        "speaker": "davefx"
    },
    "es_ES-carlfm-x_low": {
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/carlfm/x_low",
        "size_mb": 8,
        "quality": "low",
        "speaker": "carlfm"
    },
    "es_ES-sharvard-medium": {
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/sharvard/medium",
        "size_mb": 58,
        "quality": "high",
        "speaker": "sharvard"
    },
}

DEFAULT_VOICE = "es_ES-davefx-medium"

DIR = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Voz", "piper")
_lock = threading.RLock()  # reentrante: _cargar() lo toma y llama a
                          # _descargar(), que vuelve a tomarlo. Con un
                          # Lock normal eso es un deadlock permanente.
_voz_cache: Dict[str, Any] = {}
_descargando: set = set()


def _ruta(voice_id: str, ext: str) -> str:
    return os.path.join(DIR, voice_id + ext)


def disponible(voice_id: str = DEFAULT_VOICE) -> bool:
    """Verifica si el modelo está descargado y válido."""
    return os.path.exists(_ruta(voice_id, ".onnx")) and os.path.getsize(_ruta(voice_id, ".onnx")) > 1000000


def _descargar(voice_id: str = DEFAULT_VOICE) -> bool:
    """Descarga modelo y config si no existen."""
    global _descargando
    with _lock:
        if voice_id in _descargando:
            # Esperar a que termine otra descarga
            for _ in range(30):
                time.sleep(0.5)
                if disponible(voice_id):
                    return True
            return False
        _descargando.add(voice_id)

    try:
        if voice_id not in VOICES:
            return False

        os.makedirs(DIR, exist_ok=True)
        from urllib.request import urlretrieve

        voice_info = VOICES[voice_id]
        base_url = voice_info["url"]

        for ext in (".onnx", ".onnx.json"):
            ruta = _ruta(voice_id, ext)
            if not os.path.exists(ruta) or os.path.getsize(ruta) < 100:
                print(f"[PIPER] Descargando {voice_id}{ext}...")
                urlretrieve(base_url + "/" + voice_id + ext, ruta)

        return disponible(voice_id)

    except Exception as e:
        print(f"[PIPER] Error descarga: {e}")
        return False
    finally:
        _descargando.discard(voice_id)


def _cargar(voice_id: str = DEFAULT_VOICE):
    """Carga voz en memoria (cacheada)."""
    global _voz_cache
    with _lock:
        if voice_id not in _voz_cache:
            if not disponible(voice_id) and not _descargar(voice_id):
                return None
            try:
                from piper import PiperVoice
                _voz_cache[voice_id] = PiperVoice.load(_ruta(voice_id, ".onnx"))
            except Exception as e:
                print(f"[PIPER] Error carga: {e}")
                return None
    return _voz_cache.get(voice_id)


def _reproducir(wav_path: str):
    """Reproduce WAV usando pygame o fallback a reproductor del sistema."""
    try:
        import pygame
        pygame.mixer.music.load(wav_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()
    except Exception:
        try:
            os.startfile(wav_path)
        except Exception:
            raise


def sintetizar_bytes(texto: str, voice_id: str = DEFAULT_VOICE, speed: float = 1.0):
    """Sintetiza a WAV y devuelve los bytes, SIN reproducir en el PC.

    Es lo que necesita el navegador (y el movil): hablar() reproduce por los
    altavoces del equipo, que no sirve de nada para una peticion remota.
    Devuelve None si Piper no esta disponible.
    """
    if not texto or not texto.strip():
        return None
    try:
        v = _cargar(voice_id)
        if v is None:
            return None
        wav_path = os.path.join(tempfile.gettempdir(),
                                f"jarvis_piper_web_{os.getpid()}_{voice_id}.wav")
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(v.config.sample_rate)
            v.synthesize_wav(texto.strip(), w)
        if speed != 1.0:
            wav_path = _change_speed(wav_path, speed)
        try:
            with open(wav_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass
    except Exception as e:
        print(f"[PIPER] Error sintetizando bytes: {e}")
        return None


def hablar(texto: str, voice_id: str = DEFAULT_VOICE, speed: float = 1.0) -> bool:
    """
    Sintetiza y reproduce texto.
    Args:
        texto: Texto a sintetizar
        voice_id: ID de voz (es_ES-davefx-medium, es_ES-carlfm-x_low, etc)
        speed: Velocidad (0.5 - 2.0)
    Returns:
        True si se reprodujo correctamente, False si falló
    """
    if not texto or not texto.strip():
        return False

    try:
        v = _cargar(voice_id)
        if v is None:
            return False

        wav_path = os.path.join(tempfile.gettempdir(), f"jarvis_piper_{voice_id}.wav")

        # Sintetizar a WAV
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(v.config.sample_rate)
            v.synthesize_wav(texto.strip(), w)

        # Ajustar velocidad si no es 1.0 (requiere sox/ffmpeg)
        if speed != 1.0:
            wav_path = _change_speed(wav_path, speed)

        _reproducir(wav_path)

        # Limpiar
        try:
            os.remove(wav_path)
        except Exception:
            pass

        return True

    except Exception as e:
        print(f"[PIPER] Error síntesis: {e}")
        return False


def _change_speed(wav_path: str, speed: float) -> str:
    """Cambia velocidad de audio (requiere ffmpeg)."""
    try:
        import subprocess
        out_path = wav_path.replace(".wav", f"_{speed}x.wav")
        subprocess.run([
            "ffmpeg", "-y", "-i", wav_path,
            "-filter:a", f"atempo={speed}",
            out_path
        ], capture_output=True, timeout=30, creationflags=0x08000000)
        os.remove(wav_path)
        return out_path
    except Exception:
        return wav_path  # fallback: velocidad original


def descargar_modelo(voice_id: str = DEFAULT_VOICE) -> bool:
    """Descarga modelo explícitamente."""
    return _descargar(voice_id)


def get_info(voice_id: str = DEFAULT_VOICE) -> Dict[str, Any]:
    """Info del estado de la voz."""
    info = {
        "voice_id": voice_id,
        "available": disponible(voice_id),
        "model_path": _ruta(voice_id, ".onnx") if disponible(voice_id) else None,
        "config_path": _ruta(voice_id, ".onnx.json") if disponible(voice_id) else None,
    }
    if voice_id in VOICES:
        info.update(VOICES[voice_id])
    return info


def list_voices() -> Dict[str, Any]:
    """Lista voces disponibles con info."""
    result = {}
    for vid, info in VOICES.items():
        result[vid] = {
            **info,
            "downloaded": disponible(vid),
            "current": vid == DEFAULT_VOICE
        }
    return result


# Test rápido
if __name__ == "__main__":
    print("Piper TTS - Estado:")
    for vid, info in list_voices().items():
        status = "✓" if info["downloaded"] else "✗"
        print(f"  {status} {vid} ({info['quality']}, {info['size_mb']}MB)")

    if disponible():
        print("\nProbando síntesis...")
        ok = hablar("Prueba de voz Piper en español. Sistemas operativos.")
        print(f"Resultado: {'OK' if ok else 'FALLO'}")
    else:
        print("\nModelo no descargado. Ejecuta:")
        print("  from jarvis_piper import descargar_modelo")
        print("  descargar_modelo()")