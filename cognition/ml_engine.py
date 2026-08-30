#!/usr/bin/env python3
"""
cognition/ml_engine.py - Consumo de modelos preentrenados (ML/DL)
==================================================================
Principio: NO se asume hardware ni paquetes pesados. La carga de
TensorFlow/PyTorch es diferida y opcional; el motor siempre funciona
con un pipeline local sklearn (TF-IDF + regresión logística) entrenado
con las interacciones del propio usuario.

Flujo:
  1. clasificar(texto)      -> intención conocida (o None)
  2. entrenar(datos)        -> reentrena el pipeline local con ejemplos nuevos
  3. cargar_torch(ruta)     -> opcional: modelo PyTorch si está instalado y hay RAM
  4. cargar_tensorflow(ruta)-> opcional: modelo TF si está instalado y hay RAM
"""
import os
import pickle
import threading


class MLEngine:
    """Motor ML de Jarvis: sklearn local siempre disponible + DL opcional."""

    _INTENCIONES = ["crear archivo", "abrir app", "buscar web", "clima",
                    "temporizador", "nota", "voz", "arduino", "sistema",
                    "calculadora", "qr", "azar", "otro"]

    # si se amplían los ejemplos base, se sube la versión y el pipeline
    # persistido se reentrena automáticamente al arrancar
    VERSION_DATOS = 4

    def __init__(self, log=print, modelo_path=None):
        self.log = log
        self._lock = threading.RLock()  # RLock: entrenar() se invoca desde _get_pipeline()
        self._pipeline = None
        self._torch_model = None
        self._tf_model = None
        self._modelo_path = modelo_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "modelo_intenciones.pkl")

    # ── pipeline local (sklearn, carga perezosa) ────────────────────────────
    def _get_pipeline(self):
        """Carga o entrena el pipeline local. Nunca lanza por falta de sklearn."""
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.linear_model import LogisticRegression
                from sklearn.pipeline import Pipeline
                if os.path.exists(self._modelo_path):
                    with open(self._modelo_path, "rb") as f:
                        cargado = pickle.load(f)
                    # formato (version, pipeline); si la versión no coincide
                    # con los ejemplos base actuales, se reentrena
                    if isinstance(cargado, tuple) and cargado[0] == self.VERSION_DATOS:
                        self._pipeline = cargado[1]
                    else:
                        self.log("ML: ejemplos base cambiados, reentrenando pipeline")
                        self._pipeline = None
                if self._pipeline is None:
                    # pipeline mínimo para que clasificar() nunca falle
                    self._pipeline = Pipeline([
                        ("tfidf", TfidfVectorizer(max_features=4000, ngram_range=(1, 2))),
                        ("clf", LogisticRegression(C=3.0, max_iter=500,
                                                  class_weight="balanced")),
                    ])
                    self.entrenar(self._ejemplos_base())
            except Exception as e:
                self.log(f"ML local no disponible: {e}")
                self._pipeline = None
            return self._pipeline

    @staticmethod
    def _ejemplos_base():
        return [
            ("crea una carpeta en el escritorio", "crear archivo"),
            ("crea una carpeta", "crear archivo"),
            ("crea un archivo", "crear archivo"),
            ("haz un archivo llamado notas", "crear archivo"),
            ("abre chrome", "abrir app"),
            ("abre la calculadora", "abrir app"),
            ("busca gatos en youtube", "buscar web"),
            ("busca en google", "buscar web"),
            ("que clima hace", "clima"),
            ("como esta el clima", "clima"),
            ("pon un temporizador de 5 minutos", "temporizador"),
            ("alarma a las 7", "temporizador"),
            ("anota que comprar pan", "nota"),
            ("crea una nota", "nota"),
            ("habla mas fuerte", "voz"),
            ("sube el volumen", "voz"),
            ("genera un codigo de arduino", "arduino"),
            ("sube el sketch a la placa", "arduino"),
            ("que procesos hay", "sistema"),
            ("estado del pc", "sistema"),
            ("cuanto es 5 mas 3", "calculadora"),
            ("cuanto es 2 elevado a 10", "calculadora"),
            ("cuanto es 12 por 8", "calculadora"),
            ("cual es mi ip publica", "sistema"),
            ("genera un qr con hola mundo", "qr"),
            ("lanza un dado", "azar"),
            ("que redes wifi hay", "sistema"),
            ("cuantos puertos arduino hay", "arduino"),
            ("que hora es", "hora"),
            ("dime la hora", "hora"),
            ("que dia es hoy", "fecha"),
            ("hola", "otro"),
            ("gracias", "otro"),
        ]

    def clasificar(self, texto: str):
        """Devuelve la intención más probable o None si no hay pipeline."""
        p = self._get_pipeline()
        if p is None:
            return None
        try:
            probs = p.predict_proba([texto])[0]
            idx = int(probs.argmax())
            conf = float(probs[idx])
            # umbral: con 10 clases el azar es 0.10; 0.25 exige señal real
            if conf < 0.25:
                return None
            return {"intencion": p.classes_[idx], "confianza": round(conf, 3)}
        except Exception as e:
            self.log(f"clasificar: {e}")
            return None

    def entrenar(self, ejemplos):
        """Reentrena el pipeline local con (texto, intencion) nuevos."""
        p = self._get_pipeline()
        if p is None:
            return False
        try:
            textos = [t for t, _ in ejemplos]
            etiquetas = [i for _, i in ejemplos]
            if len(set(etiquetas)) < 2:
                self.log("ML: se necesitan al menos 2 clases para entrenar")
                return False
            p.fit(textos, etiquetas)
            with open(self._modelo_path, "wb") as f:
                pickle.dump((self.VERSION_DATOS, p), f)
            self.log(f"ML: pipeline entrenado con {len(ejemplos)} ejemplos")
            return True
        except Exception as e:
            self.log(f"ML: error entrenando: {e}")
            return False

    # ── deep learning opcional (nunca obligatorio) ──────────────────────────
    def cargar_torch(self, ruta, min_ram_gb=4.0):
        """Carga un modelo PyTorch si: está instalado, existe la ruta y hay RAM."""
        try:
            from cognition.resources import SystemResources
            if not SystemResources().ram_suficiente(min_ram_gb):
                self.log("torch: RAM insuficiente, no cargo el modelo")
                return False
            if not os.path.exists(ruta):
                self.log(f"torch: no existe {ruta}")
                return False
            import torch  # import diferido: solo si el usuario lo instala
            self._torch_model = torch.load(ruta, map_location="cpu")
            self._torch_model.eval()
            self.log(f"torch: modelo cargado desde {ruta}")
            return True
        except ImportError:
            self.log("torch no está instalado (pip install torch)")
            return False
        except Exception as e:
            self.log(f"torch: error de carga: {e}")
            return False

    def cargar_tensorflow(self, ruta, min_ram_gb=5.0):
        """Carga un modelo TensorFlow (SavedModel) con las mismas garantías."""
        try:
            from cognition.resources import SystemResources
            if not SystemResources().ram_suficiente(min_ram_gb):
                self.log("tf: RAM insuficiente")
                return False
            if not os.path.exists(ruta):
                self.log(f"tf: no existe {ruta}")
                return False
            import tensorflow as tf  # import diferido
            self._tf_model = tf.saved_model.load(ruta)
            self.log(f"tf: modelo cargado desde {ruta}")
            return True
        except ImportError:
            self.log("tensorflow no está instalado")
            return False
        except Exception as e:
            self.log(f"tf: error de carga: {e}")
            return False

    def predecir_torch(self, entrada):
        if self._torch_model is None:
            return None
        try:
            import torch
            with torch.no_grad():
                return self._torch_model(entrada)
        except Exception as e:
            self.log(f"torch predict: {e}")
            return None

    def estado(self):
        """Resumen útil para la telemetría del HUD."""
        return {
            "sklearn": self._pipeline is not None,
            "torch": self._torch_model is not None,
            "tensorflow": self._tf_model is not None,
        }