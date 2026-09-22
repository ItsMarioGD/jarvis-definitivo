#!/usr/bin/env python3
"""
cluster.py - Varios equipos, un solo asistente
==============================================
`herramientas/pc_tactical.py` ya sabia preguntar por el agente par y delegarle
un mensaje, pero eso era todo: dos programas que se saludan. Aqui se convierte
en infraestructura:

  * LATIDO entre nodos: cada uno sabe si el otro sigue vivo y con que carga.
  * RELEVO: si el nodo que atendia al señor cae, el otro lo dice y asume.
  * REPARTO: una tarea pesada (indexar documentos, un modelo grande, un video)
    se manda al nodo con mas memoria libre, no al que la pidio.

Un nodo es cualquier equipo con JARVIS o ULTRON escuchando: se declaran en la
preferencia `nodos` (por ejemplo «casa=192.168.1.40:5000, portatil=192.168.1.55:5000»)
o se usan los dos locales de siempre.

Sin nodos configurados no molesta a nadie: se comporta como si no existiera.
"""
import json
import os
import threading
import time
import urllib.request

TIMEOUT = float(os.getenv("JARVIS_CLUSTER_TIMEOUT", "2.0"))
INTERVALO = int(os.getenv("JARVIS_CLUSTER_INTERVALO", "60"))


def _nodos_declarados(core) -> dict:
    """{nombre: base_url}. De la preferencia `nodos` o los dos locales."""
    try:
        crudo = (core.get_pref("nodos") or "").strip()
    except Exception:
        crudo = ""
    nodos = {}
    for trozo in crudo.split(","):
        if "=" in trozo:
            nombre, direccion = trozo.split("=", 1)
            direccion = direccion.strip()
            if not direccion.startswith("http"):
                direccion = "http://" + direccion
            nodos[nombre.strip()] = direccion.rstrip("/")
    if not nodos:
        nodos = {"jarvis": "http://127.0.0.1:5000", "ultron": "http://127.0.0.1:8766"}
    return nodos


def _consultar(url: str) -> dict:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=TIMEOUT) as r:
            datos = json.load(r)
        datos["online"] = True
        return datos
    except Exception as e:
        return {"online": False, "error": str(e)[:80]}


class Cluster:
    """Coordina varios equipos con JARVIS/ULTRON."""

    def __init__(self, core, log=print):
        self.core = core
        self.log = log
        self.nodos = _nodos_declarados(core)
        self.estado_nodos = {}
        self._stop = threading.Event()
        self._hilo = None
        self.yo = getattr(core, "nombre_agente", "JARVIS").lower()

    # ── latido ──────────────────────────────────────────────────────────────
    def start(self) -> str:
        if self._hilo and self._hilo.is_alive():
            return "El enlace entre equipos ya estaba activo, señor."
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        return (f"Enlace activo con {len(self.nodos)} nodos, señor: "
                + ", ".join(self.nodos) + ".")

    def stop(self):
        self._stop.set()

    def _bucle(self):
        while not self._stop.is_set():
            try:
                self.latido()
            except Exception as e:
                self.log(f"[CLUSTER] Fallo en el latido: {e}")
            self._stop.wait(INTERVALO)

    def latido(self) -> dict:
        """Pregunta a cada nodo y avisa de las caídas nuevas."""
        for nombre, url in self.nodos.items():
            if nombre.lower() == self.yo:
                continue
            estado = _consultar(url)
            antes = self.estado_nodos.get(nombre, {}).get("online")
            self.estado_nodos[nombre] = estado
            if antes is True and not estado["online"]:
                self._asumir(nombre, estado)
            elif antes is False and estado["online"]:
                self.log(f"[CLUSTER] {nombre} ha vuelto.")
        return self.estado_nodos

    def _asumir(self, nombre: str, estado: dict):
        """El otro nodo ha caído: se dice y se toma el relevo."""
        texto = (f"Señor, el equipo «{nombre}» ha dejado de responder. "
                 "Asumo yo sus tareas mientras vuelve.")
        self.log(f"[CLUSTER] {texto} ({estado.get('error', '')})")
        try:
            if getattr(self.core, "tts_queue", None) is not None:
                self.core.tts_queue.put(texto)
        except Exception:
            pass
        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                "cluster", f"Nodo caído: {nombre}", estado.get("error", ""),
                gravedad="alta", agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass

    # ── reparto ─────────────────────────────────────────────────────────────
    def mejor_nodo(self) -> str:
        """Nodo con más memoria libre (o el local si nadie responde)."""
        mejor, libre_max = "", -1.0
        for nombre, estado in self.estado_nodos.items():
            if not estado.get("online"):
                continue
            libre = 0.0
            for clave in ("ram_libre_gb", "memoria_libre", "ram_free_gb"):
                if clave in estado:
                    try:
                        libre = float(estado[clave])
                        break
                    except Exception:
                        pass
            if libre > libre_max:
                mejor, libre_max = nombre, libre
        return mejor

    def delegar(self, orden: str, nodo: str = "") -> str:
        """Manda una orden a otro equipo y devuelve su respuesta."""
        destino = nodo or self.mejor_nodo()
        if not destino:
            return ""
        url = self.nodos.get(destino)
        if not url:
            return f"No conozco ningún equipo llamado {destino}, señor."
        try:
            cuerpo = json.dumps({"text": orden}).encode("utf-8")
            peticion = urllib.request.Request(
                f"{url}/api/chat", data=cuerpo,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(peticion, timeout=60) as r:
                datos = json.load(r)
            respuesta = datos.get("reply") or datos.get("response") or ""
            self.log(f"[CLUSTER] Delegado a {destino}: {orden[:50]}")
            return f"({destino}) {respuesta}"
        except Exception as e:
            return f"El equipo {destino} no atendió la orden, señor: {str(e)[:80]}"

    # ── estado ──────────────────────────────────────────────────────────────
    def resumen(self) -> str:
        if not self.estado_nodos:
            self.latido()
        vivos = [n for n, e in self.estado_nodos.items() if e.get("online")]
        caidos = [n for n, e in self.estado_nodos.items() if not e.get("online")]
        partes = []
        if vivos:
            partes.append("en línea: " + ", ".join(vivos))
        if caidos:
            partes.append("sin respuesta: " + ", ".join(caidos))
        if not partes:
            return "No tengo otros equipos configurados, señor."
        return "Equipos del enlace, señor — " + "; ".join(partes) + "."

    def estado(self) -> dict:
        return {"yo": self.yo, "nodos": self.nodos,
                "estado": self.estado_nodos,
                "activo": bool(self._hilo and self._hilo.is_alive())}
