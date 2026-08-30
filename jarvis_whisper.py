#!/usr/bin/env python3
"""
jarvis_whisper.py - STT Local con Whisper.cpp (ggml)
=====================================================
Integración offline, rápida y sin API keys.
Requiere: whisper.cpp compilado (main.exe) + modelo ggml (base.en, small.es, etc)

Instalación rápida Windows:
1. Descargar whisper.cpp release: https://github.com/ggerganov/whisper.cpp/releases
2. Extraer main.exe a: %USERPROFILE%\Descargas\JARVIS\Models\whisper\
3. Descargar modelo ggml-base.es.bin a misma carpeta
   (o ggml-small.es.bin para mejor precisión)
4. Añadir carpeta al PATH o configurar WHISPER_CPP_PATH en .env
"""
import os
import subprocess
import tempfile
import threading
import time
import wave
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class WhisperConfig:
    exe_path: str = ""
    model_path: str = ""
    language: str = "es"
    threads: int = 4
    translate: bool = False
    no_timestamps: bool = True
    vad: bool = True  # Voice Activity Detection


class WhisperCppSTT:
    """
    Wrapper para whisper.cpp (main.exe).
    Uso:
        stt = WhisperCppSTT()
        text = stt.transcribe(audio_wav_bytes)
    """

    def __init__(self, config: WhisperConfig = None, log=print):
        self.config = config or WhisperConfig()
        self.log = log
        self._exe = None
        self._model = None
        self._resolve_paths()

    def _resolve_paths(self):
        """Resuelve rutas de ejecutable y modelo."""
        base = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Models", "whisper")

        # Ejecutable
        if self.config.exe_path and os.path.exists(self.config.exe_path):
            self._exe = self.config.exe_path
        else:
            candidates = [
                os.path.join(base, "main.exe"),
                os.path.join(base, "whisper.exe"),
                "whisper.cpp-main.exe",  # en PATH
                "main.exe",  # en PATH
            ]
            for c in candidates:
                if os.path.exists(c) or (c != base and self._which(c)):
                    self._exe = c if os.path.exists(c) else self._which(c)
                    break

        # Modelo
        if self.config.model_path and os.path.exists(self.config.model_path):
            self._model = self.config.model_path
        else:
            # Preferir modelo español
            candidates = [
                os.path.join(base, "ggml-base.es.bin"),
                os.path.join(base, "ggml-small.es.bin"),
                os.path.join(base, "ggml-medium.es.bin"),
                os.path.join(base, "ggml-base.bin"),
                os.path.join(base, "ggml-small.bin"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    self._model = c
                    break

    @staticmethod
    def _which(cmd: str) -> Optional[str]:
        try:
            r = subprocess.run(["where", cmd], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return r.stdout.strip().splitlines()[0]
        except Exception:
            pass
        return None

    def is_ready(self) -> bool:
        return bool(self._exe and self._model and os.path.exists(self._exe) and os.path.exists(self._model))

    def get_info(self) -> Dict[str, Any]:
        return {
            "ready": self.is_ready(),
            "exe": self._exe,
            "model": self._model,
            "language": self.config.language,
        }

    def transcribe(self, audio_wav_bytes: bytes, timeout: int = 30) -> str:
        """
        Transcribe audio WAV (16kHz, 16-bit, mono) a texto.
        Returns: texto transcrito o "" si falla.
        """
        if not self.is_ready():
            self.log(f"[WHISPER] No listo: exe={self._exe}, model={self._model}")
            return ""

        # Guardar WAV temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(audio_wav_bytes)
            wav_path = f.name

        try:
            cmd = [
                self._exe,
                "-m", self._model,
                "-f", wav_path,
                "-l", self.config.language,
                "-t", str(self.config.threads),
            ]
            if self.config.no_timestamps:
                cmd.append("-nt")
            if self.config.translate:
                cmd.append("-tr")
            if self.config.vad:
                cmd.append("-vad")

            self.log(f"[WHISPER] Ejecutando: {' '.join(cmd[:5])}...")

            start = time.time()
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='ignore')
            elapsed = time.time() - start

            if r.returncode != 0:
                self.log(f"[WHISPER] Error ({r.returncode}): {r.stderr[:200]}")
                return ""

            text = r.stdout.strip()
            self.log(f"[WHISPER] Transcrito en {elapsed:.1f}s: {text[:80]}")
            return text

        except subprocess.TimeoutExpired:
            self.log(f"[WHISPER] Timeout (> {timeout}s)")
            return ""
        except Exception as e:
            self.log(f"[WHISPER] Excepción: {e}")
            return ""
        finally:
            try:
                os.unlink(wav_path)
            except Exception:
                pass

    def transcribe_file(self, wav_path: str, timeout: int = 60) -> str:
        """Transcribe archivo WAV existente."""
        if not self.is_ready() or not os.path.exists(wav_path):
            return ""

        cmd = [
            self._exe,
            "-m", self._model,
            "-f", wav_path,
            "-l", self.config.language,
            "-t", str(self.config.threads),
        ]
        if self.config.no_timestamps:
            cmd.append("-nt")
        if self.config.translate:
            cmd.append("-tr")
        if self.config.vad:
            cmd.append("-vad")

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='ignore')
            if r.returncode != 0:
                self.log(f"[WHISPER] Error archivo: {r.stderr[:200]}")
                return ""
            return r.stdout.strip()
        except Exception as e:
            self.log(f"[WHISPER] Excepción archivo: {e}")
            return ""


class WhisperCppStreamingSTT:
    """
    STT Streaming con whisper.cpp (para futuro: requiere servidor whisper.cpp con -ws)
    Por ahora: placeholder para arquitectura futura.
    """
    def __init__(self, config: WhisperConfig = None, log=print):
        self.config = config or WhisperConfig()
        self.log = log

    async def start_stream(self, callback):
        """Inicia streaming desde micrófono (requiere whisper.cpp server mode)."""
        self.log("[WHISPER-STREAM] Streaming no implementado aún. Usa transcribe() por chunks.")
        pass


# Instancia global lazy
_whisper_instance: Optional[WhisperCppSTT] = None


def get_whisper_stt(config: WhisperConfig = None, log=print) -> WhisperCppSTT:
    global _whisper_instance
    if _whisper_instance is None:
        _whisper_instance = WhisperCppSTT(config, log)
    return _whisper_instance


# Helper para integración en jarvis_core.py
def transcribe_audio_whisper(audio_wav_bytes: bytes, log=print) -> str:
    """Punto de entrada simple para jarvis_core.listen()"""
    stt = get_whisper_stt(log=log)
    return stt.transcribe(audio_wav_bytes)


# Auto-descarga de modelo (opcional)
def download_model(model_name: str = "ggml-base.es.bin", dest_dir: str = None) -> str:
    """
    Descarga modelo ggml desde HuggingFace.
    model_name: ggml-base.es.bin, ggml-small.es.bin, ggml-medium.es.bin, ggml-base.bin, etc
    """
    if dest_dir is None:
        dest_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Models", "whisper")
    os.makedirs(dest_dir, exist_ok=True)

    dest = os.path.join(dest_dir, model_name)
    if os.path.exists(dest):
        return dest

    url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{model_name}"
    try:
        import urllib.request
        print(f"[WHISPER] Descargando {model_name}...")
        urllib.request.urlretrieve(url, dest)
        print(f"[WHISPER] Modelo guardado en {dest}")
        return dest
    except Exception as e:
        print(f"[WHISPER] Error descarga: {e}")
        return ""


if __name__ == "__main__":
    # Test rápido
    stt = WhisperCppSTT()
    info = stt.get_info()
    print(f"Whisper.cpp STT: {info}")

    if info["ready"]:
        # Generar WAV de prueba (silencio 1s)
        import wave, struct
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            wav_path = f.name
        with wave.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack('<h', 0) * 16000)

        with open(wav_path, 'rb') as f:
            audio = f.read()

        text = stt.transcribe(audio)
        print(f"Test silencio: '{text}'")

        os.unlink(wav_path)
    else:
        print("Para usar Whisper.cpp:")
        print("1. Descarga whisper.cpp release desde GitHub")
        print("2. Copia main.exe a ~/Descargas/JARVIS/Models/whisper/")
        print("3. Descarga modelo: python -c \"from jarvis_whisper import download_model; download_model('ggml-base.es.bin')\"")