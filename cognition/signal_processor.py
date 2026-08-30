#!/usr/bin/env python3
"""
cognition/signal_processor.py - Procesamiento de señales (audio/texto)
Fase 1: Stub para paralingüística (estrés, fatiga, emoción)
Fase 2: Modelos TinyML reales (TF Lite / ONNX)
"""
import os
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class AudioFeatures:
    mfcc: np.ndarray          # (n_mfcc, n_frames)
    rms_energy: float         # Energía total
    spectral_centroid: float  # Brillo perceptual
    zero_crossing_rate: float # Noisiness
    pitch_mean: float         # F0 promedio (Hz)
    pitch_std: float          # Variabilidad de pitch
    tempo: float              # BPM estimado
    duration: float           # Segundos


@dataclass
class ParalinguisticResult:
    stress_level: float       # 0.0 - 1.0
    fatigue_level: float      # 0.0 - 1.0
    arousal: float            # 0.0 - 1.0 (activación)
    valence: float            # -1.0 - 1.0 (negativo a positivo)
    confidence: float         # Confianza global
    features: AudioFeatures


class SignalProcessor:
    """
    Procesador de señales de audio para características paralingüísticas.
    Fase 1: Stub que devuelve valores neutros + logging.
    Fase 2: Modelos cuantizados TF Lite / ONNX Runtime.
    """

    def __init__(self, log=print):
        self.log = log
        self._model_loaded = False
        self._model_path = os.path.join(
            os.path.expanduser("~"), "Descargas", "JARVIS", "Models", "paralinguistic.tflite"
        )
        self._load_model()

    def _load_model(self):
        """Carga modelo TinyML si existe."""
        if os.path.exists(self._model_path):
            try:
                import tflite_runtime.interpreter as tflite
                self._interpreter = tflite.Interpreter(model_path=self._model_path)
                self._interpreter.allocate_tensors()
                self._input_details = self._interpreter.get_input_details()
                self._output_details = self._interpreter.get_output_details()
                self._model_loaded = True
                self.log(f"[SIGNAL] Modelo paralingüístico cargado: {self._model_path}")
            except Exception as e:
                self.log(f"[SIGNAL] No se pudo cargar modelo TFLite: {e}")
        else:
            self.log("[SIGNAL] Modelo paralingüístico no encontrado, usando stub")

    def audio_features(self, audio_path: str) -> AudioFeatures:
        """Extrae características acústicas básicas (librosa/essentia)."""
        try:
            import librosa
            y, sr = librosa.load(audio_path, sr=16000)

            # MFCC (13 coef)
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)

            # RMS Energy
            rms = librosa.feature.rms(y=y)[0]
            rms_energy = float(np.mean(rms))

            # Spectral Centroid
            cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            spectral_centroid = float(np.mean(cent))

            # Zero Crossing Rate
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            zero_crossing_rate = float(np.mean(zcr))

            # Pitch (piptrack)
            pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
            pitch_vals = pitches[magnitudes > np.median(magnitudes)]
            pitch_mean = float(np.mean(pitch_vals)) if len(pitch_vals) > 0 else 0.0
            pitch_std = float(np.std(pitch_vals)) if len(pitch_vals) > 0 else 0.0

            # Tempo
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo = float(librosa.beat.tempo(onset_envelope=onset_env, sr=sr)[0])

            duration = len(y) / sr

            return AudioFeatures(
                mfcc=mfcc,
                rms_energy=rms_energy,
                spectral_centroid=spectral_centroid,
                zero_crossing_rate=zero_crossing_rate,
                pitch_mean=pitch_mean,
                pitch_std=pitch_std,
                tempo=tempo,
                duration=duration
            )
        except Exception as e:
            self.log(f"[SIGNAL] Error extrayendo features: {e}")
            return self._empty_features()

    def _empty_features(self) -> AudioFeatures:
        return AudioFeatures(
            mfcc=np.zeros((13, 1)),
            rms_energy=0.0,
            spectral_centroid=0.0,
            zero_crossing_rate=0.0,
            pitch_mean=0.0,
            pitch_std=0.0,
            tempo=0.0,
            duration=0.0
        )

    def analyze_paralinguistic(self, audio_path: str) -> ParalinguisticResult:
        """
        Análisis paralingüístico completo.
        Fase 1: Stub basado en heurísticas simples de features.
        Fase 2: Inferencia con modelo neuronal.
        """
        features = self.audio_features(audio_path)

        if self._model_loaded:
            return self._infer_model(features)

        # Heurísticas simples (Fase 1 stub)
        stress = self._heuristic_stress(features)
        fatigue = self._heuristic_fatigue(features)
        arousal = self._heuristic_arousal(features)
        valence = self._heuristic_valence(features)

        return ParalinguisticResult(
            stress_level=stress,
            fatigue_level=fatigue,
            arousal=arousal,
            valence=valence,
            confidence=0.3,  # Baja confianza en stub
            features=features
        )

    def _heuristic_stress(self, f: AudioFeatures) -> float:
        # Pitch alto + variabilidad alta + energía alta + tempo rápido
        score = 0.0
        if f.pitch_mean > 200: score += 0.3
        if f.pitch_std > 50: score += 0.2
        if f.rms_energy > 0.1: score += 0.2
        if f.tempo > 140: score += 0.3
        return min(1.0, score)

    def _heuristic_fatigue(self, f: AudioFeatures) -> float:
        # Pitch bajo + energía baja + tempo lento + pausas largas
        score = 0.0
        if f.pitch_mean < 120 and f.pitch_mean > 0: score += 0.3
        if f.rms_energy < 0.02: score += 0.3
        if f.tempo > 0 and f.tempo < 80: score += 0.2
        if f.zero_crossing_rate < 0.01: score += 0.2
        return min(1.0, score)

    def _heuristic_arousal(self, f: AudioFeatures) -> float:
        # Activación general: energía + pitch + tempo
        score = (min(f.rms_energy * 5, 1.0) * 0.4 +
                 min(f.pitch_mean / 300, 1.0) * 0.3 +
                 min(f.tempo / 180, 1.0) * 0.3)
        return min(1.0, score)

    def _heuristic_valence(self, f: AudioFeatures) -> float:
        # Valence aproximado: spectral centroid (brillo) + pitch stability
        brightness = min(f.spectral_centroid / 4000, 1.0)
        stability = 1.0 - min(f.pitch_std / 100, 1.0)
        return (brightness * 0.6 + stability * 0.4) * 2 - 1  # -1 a 1

    def _infer_model(self, features: AudioFeatures) -> ParalinguisticResult:
        """Inferencia con modelo TFLite (Fase 2)."""
        try:
            # Preparar input: flatten MFCC + features escalares
            mfcc_flat = features.mfcc.flatten()[:130]  # 13*10 frames
            if len(mfcc_flat) < 130:
                mfcc_flat = np.pad(mfcc_flat, (0, 130 - len(mfcc_flat)))

            input_vector = np.concatenate([
                mfcc_flat,
                [features.rms_energy, features.spectral_centroid / 4000,
                 features.zero_crossing_rate, features.pitch_mean / 300,
                 features.pitch_std / 100, features.tempo / 200,
                 features.duration / 30]
            ]).astype(np.float32)

            self._interpreter.set_tensor(self._input_details[0]['index'], [input_vector])
            self._interpreter.invoke()

            output = self._interpreter.get_tensor(self._output_details[0]['index'])[0]
            # Output: [stress, fatigue, arousal, valence_normalized]
            stress, fatigue, arousal, valence_norm = output[:4]
            valence = valence_norm * 2 - 1

            return ParalinguisticResult(
                stress_level=float(stress),
                fatigue_level=float(fatigue),
                arousal=float(arousal),
                valence=float(valence),
                confidence=0.85,
                features=features
            )
        except Exception as e:
            self.log(f"[SIGNAL] Error en inferencia modelo: {e}")
            return self.analyze_paralinguistic.__wrapped__(self, "")  # fallback heurístico

    def text_features(self, text: str) -> Dict[str, Any]:
        """Features lingüísticas básicas (longitud, complejidad, sentimiento)."""
        words = text.split()
        return {
            "word_count": len(words),
            "char_count": len(text),
            "avg_word_len": np.mean([len(w) for w in words]) if words else 0,
            "sentence_count": text.count('.') + text.count('!') + text.count('?'),
            "question_marks": text.count('?'),
            "exclamation_marks": text.count('!'),
            "uppercase_ratio": sum(1 for c in text if c.isupper()) / max(len(text), 1)
        }


# Función helper para integración fácil
def analyze_user_audio(audio_path: str, log=print) -> Optional[ParalinguisticResult]:
    """Punto de entrada simple para jarvis_core.py:listen()"""
    processor = SignalProcessor(log=log)
    return processor.analyze_paralinguistic(audio_path)