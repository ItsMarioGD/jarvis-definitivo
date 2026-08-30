#!/usr/bin/env python3
"""
cognition/cluster_engine.py - Análisis de conglomerados (Fase 1)
=================================================================
Pipeline de clustering sobre las interacciones del usuario para descubrir
temas dominantes y optimizar respuestas (p. ej. "noto que últimamente
hablamos mucho de Arduino").

Flujo:
  1. cargar interacciones de la DB (o lista propia)
  2. vectorizar con TF-IDF
  3. KMeans (o DBSCAN si hay ruido) con selección del nº de clusters
  4. temas por centroide (términos más pesados)
  5. guardar etiquetas + persistir el modelo en disco
"""
import os
import pickle
import threading


class ClusterEngine:
    """Agrupación de información del usuario por similitud semántica."""

    def __init__(self, log=print, db=None, modelo_path=None):
        self.log = log
        self._db = db
        self._lock = threading.Lock()
        self._modelo = None
        self._modelo_path = modelo_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "clusters.pkl")

    def _guardar(self):
        try:
            with open(self._modelo_path, "wb") as f:
                pickle.dump(self._modelo, f)
        except Exception as e:
            self.log(f"cluster: no pude persistir: {e}")

    def _cargar(self):
        if os.path.exists(self._modelo_path):
            try:
                with open(self._modelo_path, "rb") as f:
                    self._modelo = pickle.load(f)
            except Exception:
                self._modelo = None

    # ── entrenamiento / etiquetado ──────────────────────────────────────────
    def entrenar(self, textos, n_clusters=None):
        """Vectoriza y agrupa. n_clusters=auto usa regla del codo simplificada."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.cluster import KMeans, DBSCAN
        except ImportError:
            self.log("cluster: sklearn no instalado")
            return False

        textos = [t for t in textos if t and t.strip()]
        if len(textos) < 3:
            return False

        with self._lock:
            try:
                # preprocesado propio (stopwords ES + acentos) porque sklearn
                # solo trae stop_words 'english' integrado
                from cognition.signal_processor import SignalProcessor
                limpios = [SignalProcessor.limpiar_texto(t) for t in textos]
                vec = TfidfVectorizer(max_features=2000)
                X = vec.fit_transform(limpios)
                if n_clusters is None:
                    # codo ligero: mínimo de inercia normalizada entre 2 y 6
                    mejor = 2
                    mejor_inercia = None
                    for k in range(2, min(7, len(textos)) + 1):
                        km = KMeans(n_clusters=k, n_init=4, random_state=42).fit(X)
                        inercia = km.inertia_ / k
                        if mejor_inercia is None or inercia < mejor_inercia:
                            mejor_inercia = inercia
                            mejor = k
                    n_clusters = mejor
                km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
                etiquetas = km.fit_predict(X)

                self._modelo = {"kmeans": km, "vectorizer": vec,
                                "n": int(n_clusters), "n_items": int(X.shape[0])}
                self._guardar()
                self.log(f"cluster: {n_clusters} grupos sobre {X.shape[0]} textos")
                return etiquetas.tolist()
            except Exception as e:
                self.log(f"cluster: error: {e}")
                return False

    # ── temas dominantes ────────────────────────────────────────────────────
    def temas_dominantes(self, n=3):
        """Devuelve [(tema, tamaño, palabras_clave), ...] o [] si no hay modelo."""
        if self._modelo is None:
            self._cargar()
        if self._modelo is None:
            return []
        try:
            km = self._modelo["kmeans"]
            vec = self._modelo["vectorizer"]
            from collections import Counter
            tamaños = Counter(km.labels_)
            temas = []
            for k in range(km.n_clusters):
                centro = km.cluster_centers_[k]
                top = centro.argsort()[-4:][::-1]
                palabras = [vec.get_feature_names_out()[i] for i in top if centro[i] > 0.1]
                temas.append((f"tema {k + 1}", int(tamaños[k]), palabras))
            temas.sort(key=lambda x: -x[1])
            return temas[:n]
        except Exception as e:
            self.log(f"cluster: temas: {e}")
            return []

    def etiquetar(self, texto: str):
        """Asigna un texto nuevo al cluster más cercano (o None)."""
        if self._modelo is None:
            self._cargar()
        if self._modelo is None:
            return None
        try:
            x = self._modelo["vectorizer"].transform([texto])
            k = int(self._modelo["kmeans"].predict(x)[0])
            return f"tema {k + 1}"
        except Exception:
            return None