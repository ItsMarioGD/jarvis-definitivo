#!/usr/bin/env python3
"""
enjambre.py - Agentes especialistas con presupuesto
===================================================
La idea 1 del IDEAS.MD (topologia multi-agente) llevaba tiempo escrita como
concepto. El problema de los enjambres de agentes no es tecnico, es social: en
cuanto varios procesos pueden hablarte, te sepultan. Un asistente que
interrumpe ocho veces al dia se silencia el primer dia.

Por eso aqui cada agente tiene tres limites duros:

    intervalo     cada cuanto puede mirar (no cada segundo: cada media hora)
    presupuesto   cuantas veces al dia puede trabajar; agotado, calla
    importancia   cuanto tiene que valer un hallazgo para INTERRUMPIR

Lo que no llega al umbral no se pierde: se acumula y sale en el resumen cuando
el señor pregunte, o en el parte de la mañana. Interrumpir es caro; informar es
gratis.

Agentes incluidos (todos degradan solos si les falta lo que necesitan):
  codigo     repositorios git con cambios sin guardar o sin subir
  disco      carpetas que crecen de forma anomala
  seguridad  eventos criticos registrados por el guardian o los señuelos
  casa       estado de Home Assistant, si esta configurado
  mercado    cotizaciones vigiladas, si hay yfinance y tickers guardados
"""
import os
import threading
import time
from collections import defaultdict
from datetime import datetime

UMBRAL_INTERRUPCION = float(os.getenv("JARVIS_ENJAMBRE_UMBRAL", "0.7"))
PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")


class Hallazgo:
    def __init__(self, agente, titulo, detalle="", importancia=0.5):
        self.agente = agente
        self.titulo = titulo
        self.detalle = detalle
        self.importancia = max(0.0, min(float(importancia), 1.0))
        self.momento = time.time()

    def __repr__(self):
        return f"<{self.agente}: {self.titulo} ({self.importancia:.2f})>"


class Agente:
    def __init__(self, nombre, descripcion, funcion, intervalo_s=1800,
                 presupuesto_dia=24):
        self.nombre = nombre
        self.descripcion = descripcion
        self.funcion = funcion
        self.intervalo_s = intervalo_s
        self.presupuesto_dia = presupuesto_dia
        self.ultimo = 0.0
        self.gastado = 0
        self.dia = datetime.now().strftime("%Y-%m-%d")

    def puede_trabajar(self) -> bool:
        hoy = datetime.now().strftime("%Y-%m-%d")
        if hoy != self.dia:                 # día nuevo, presupuesto nuevo
            self.dia, self.gastado = hoy, 0
        if self.gastado >= self.presupuesto_dia:
            return False
        return (time.time() - self.ultimo) >= self.intervalo_s


class Enjambre:
    """Coordina a los especialistas y decide qué merece interrumpir."""

    def __init__(self, core, log=print, umbral=UMBRAL_INTERRUPCION):
        self.core = core
        self.log = log
        self.umbral = umbral
        self._stop = threading.Event()
        self._hilo = None
        self._lock = threading.Lock()
        self.pendientes = []          # hallazgos que no llegaron al umbral
        # Memoria de lo ya contado: sin esto, el agente de seguridad vuelve a
        # leer el mismo evento en cada ronda y el señor recibe la misma alerta
        # cada dos minutos, que es la forma mas rapida de que silencie el
        # enjambre entero.
        self._ya_contado = {}         # (agente, titulo) -> momento
        self.agentes = self._agentes()

    # ── agentes ─────────────────────────────────────────────────────────────
    def _agentes(self) -> list:
        return [
            Agente("codigo", "repositorios con trabajo sin guardar",
                   self._ag_codigo, intervalo_s=3600, presupuesto_dia=12),
            Agente("disco", "carpetas que crecen de forma anómala",
                   self._ag_disco, intervalo_s=7200, presupuesto_dia=8),
            Agente("seguridad", "eventos críticos del guardián y los señuelos",
                   self._ag_seguridad, intervalo_s=600, presupuesto_dia=48),
            Agente("casa", "estado de la domótica",
                   self._ag_casa, intervalo_s=3600, presupuesto_dia=8),
            Agente("mercado", "cotizaciones vigiladas",
                   self._ag_mercado, intervalo_s=1800, presupuesto_dia=16),
            Agente("correo", "correos sin leer que parecen importantes",
                   self._ag_correo, intervalo_s=1800, presupuesto_dia=20),
        ]

    def _ag_correo(self) -> list:
        """Bandeja de Gmail: avisa solo si hay correo que parece importante."""
        try:
            import correo_gmail
        except Exception:
            return []
        hallazgos = []
        try:
            for titulo, detalle, importancia in correo_gmail.hallazgos_para_enjambre(log=self.log):
                hallazgos.append(Hallazgo("correo", titulo, detalle, importancia))
        except Exception as e:
            self.log(f"[ENJAMBRE] correo: {e}")
        return hallazgos

    def _ag_codigo(self) -> list:
        """Repos git con cambios sin commitear: trabajo en riesgo de perderse."""
        import ejecutor
        hallazgos = []
        raices = [os.path.join(os.path.expanduser("~"), c)
                  for c in ("Documentos", "Documents", "Descargas", "Downloads",
                            "Proyectos", "Projects")]
        revisados = 0
        for raiz in raices:
            if not os.path.isdir(raiz) or revisados >= 12:
                continue
            for nombre in os.listdir(raiz):
                if revisados >= 12:
                    break
                repo = os.path.join(raiz, nombre)
                if not os.path.isdir(os.path.join(repo, ".git")):
                    continue
                revisados += 1
                res = ejecutor.ejecutar(["git", "-C", repo, "status", "--porcelain"],
                                        origen="enjambre", orden=f"estado de {nombre}",
                                        shell=False, timeout=15, log=self.log)
                sucios = [l for l in (res["salida"] or "").splitlines() if l.strip()]
                if len(sucios) >= 5:
                    hallazgos.append(Hallazgo(
                        "codigo", f"{nombre}: {len(sucios)} archivos sin guardar en git",
                        "Trabajo sin commitear que se perdería en un formateo.",
                        importancia=0.5 + min(len(sucios), 40) / 100))
        return hallazgos

    def _ag_disco(self) -> list:
        """Compara el tamaño de las carpetas con la medición anterior."""
        import json
        registro = os.path.join(PREFS, "enjambre_disco.json")
        anterior = {}
        try:
            with open(registro, encoding="utf-8") as f:
                anterior = json.load(f)
        except Exception:
            pass

        actual, hallazgos = {}, []
        hogar = os.path.expanduser("~")
        for nombre in ("Descargas", "Downloads", "Documentos", "Documents"):
            carpeta = os.path.join(hogar, nombre)
            if not os.path.isdir(carpeta):
                continue
            total = 0
            try:
                for base, _dirs, ficheros in os.walk(carpeta):
                    for f in ficheros:
                        try:
                            total += os.path.getsize(os.path.join(base, f))
                        except Exception:
                            continue
                    if total > 80 * 1024 ** 3:      # tope: no auditar eternamente
                        break
            except Exception:
                continue
            gb = round(total / 1024 ** 3, 2)
            actual[carpeta] = gb
            previo = anterior.get(carpeta)
            if previo and gb - previo >= 5:
                hallazgos.append(Hallazgo(
                    "disco", f"{nombre} ha crecido {gb - previo:.1f} GB",
                    f"Ahora ocupa {gb} GB.", importancia=0.55))
        try:
            os.makedirs(PREFS, exist_ok=True)
            with open(registro, "w", encoding="utf-8") as f:
                json.dump(actual, f)
        except Exception:
            pass
        return hallazgos

    def _ag_seguridad(self) -> list:
        try:
            from storage import get_storage
            db = get_storage(log=self.log)
        except Exception:
            return []
        hallazgos = []
        for tipo, importancia in (("ransomware", 1.0), ("intruso", 0.9), ("caida", 0.6)):
            for e in db.eventos_recientes(3, tipo=tipo, horas=1):
                hallazgos.append(Hallazgo("seguridad", e["titulo"],
                                          e.get("detalle", ""), importancia))
        return hallazgos

    def _ag_casa(self) -> list:
        conectores = getattr(self.core, "conectores", None)
        if conectores is None:
            return []
        try:
            r = conectores.handle("estado de la casa")
        except Exception:
            return []
        if not r:
            return []
        return [Hallazgo("casa", "Estado de la casa", str(r)[:200], 0.3)]

    def _ag_mercado(self) -> list:
        tickers = []
        try:
            tickers = [t.strip() for t in
                       (self.core.get_pref("tickers") or "").split(",") if t.strip()]
        except Exception:
            pass
        if not tickers:
            return []
        try:
            import yfinance
        except Exception:
            return []
        hallazgos = []
        for ticker in tickers[:5]:
            try:
                datos = yfinance.Ticker(ticker).history(period="2d")
                if len(datos) < 2:
                    continue
                ayer, hoy = datos["Close"].iloc[-2], datos["Close"].iloc[-1]
                variacion = (hoy - ayer) / ayer * 100
                if abs(variacion) >= 4:
                    hallazgos.append(Hallazgo(
                        "mercado", f"{ticker} {variacion:+.1f}%",
                        f"De {ayer:.2f} a {hoy:.2f}.",
                        importancia=0.6 + min(abs(variacion), 20) / 50))
            except Exception as e:
                self.log(f"[ENJAMBRE] {ticker}: {e}")
        return hallazgos

    # ── ciclo ───────────────────────────────────────────────────────────────
    def start(self) -> str:
        if self._hilo and self._hilo.is_alive():
            return "El enjambre ya estaba trabajando, señor."
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        return (f"Enjambre en marcha, señor: {len(self.agentes)} especialistas. "
                f"Solo le interrumpirán si algo pasa de {int(self.umbral * 100)} "
                "sobre 100 de importancia.")

    def stop(self):
        self._stop.set()

    def _bucle(self):
        self._stop.wait(60)
        while not self._stop.is_set():
            try:
                self.ronda()
            except Exception as e:
                self.log(f"[ENJAMBRE] Fallo en la ronda: {e}")
            self._stop.wait(120)

    def ronda(self) -> list:
        """Da la vuelta a los agentes que tocan y reparte lo encontrado."""
        nuevos = []
        for agente in self.agentes:
            if not agente.puede_trabajar():
                continue
            agente.ultimo = time.time()
            agente.gastado += 1
            try:
                hallazgos = agente.funcion() or []
            except Exception as e:
                self.log(f"[ENJAMBRE] {agente.nombre} falló: {e}")
                continue
            for h in hallazgos:
                if self._repetido(h):
                    continue
                nuevos.append(h)
                if h.importancia >= self.umbral:
                    self._interrumpir(h)
                else:
                    with self._lock:
                        self.pendientes.append(h)
        if nuevos:
            self.log(f"[ENJAMBRE] {len(nuevos)} hallazgos en esta ronda")
        return nuevos

    def _repetido(self, hallazgo: Hallazgo, olvido_s: int = 21600) -> bool:
        """¿Ya se contó esto? Se olvida a las seis horas para poder repetirlo."""
        clave = (hallazgo.agente, hallazgo.titulo[:80])
        ahora = time.time()
        with self._lock:
            self._ya_contado = {k: t for k, t in self._ya_contado.items()
                                if ahora - t < olvido_s}
            if clave in self._ya_contado:
                return True
            self._ya_contado[clave] = ahora
        return False

    def _interrumpir(self, hallazgo: Hallazgo):
        texto = f"Señor, {hallazgo.titulo}. {hallazgo.detalle}".strip()
        self.log(f"[ENJAMBRE] Interrumpo: {hallazgo}")
        try:
            if getattr(self.core, "tts_queue", None) is not None:
                self.core.tts_queue.put(texto)
        except Exception:
            pass
        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                f"enjambre:{hallazgo.agente}", hallazgo.titulo, hallazgo.detalle,
                gravedad="alta" if hallazgo.importancia >= 0.85 else "aviso",
                agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass

    # ── consulta ────────────────────────────────────────────────────────────
    def resumen(self, limpiar: bool = True) -> str:
        """Lo que los agentes vieron y no valía la pena interrumpir."""
        with self._lock:
            pendientes = list(self.pendientes)
            if limpiar:
                self.pendientes = []
        if not pendientes:
            return "Los especialistas no tienen nada que reportar, señor."
        por_agente = defaultdict(list)
        for h in pendientes:
            por_agente[h.agente].append(h.titulo)
        partes = [f"{agente}: {'; '.join(titulos[:3])}"
                  for agente, titulos in por_agente.items()]
        return "Sin urgencia, señor — " + " | ".join(partes) + "."

    def estado(self) -> dict:
        return {
            "activo": bool(self._hilo and self._hilo.is_alive()),
            "umbral": self.umbral,
            "pendientes": len(self.pendientes),
            "agentes": [{"nombre": a.nombre, "cada_s": a.intervalo_s,
                         "gastado_hoy": a.gastado, "presupuesto": a.presupuesto_dia}
                        for a in self.agentes],
        }
