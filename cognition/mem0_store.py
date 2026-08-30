#!/usr/bin/env python3
"""
cognition/mem0_store.py - Integración Mem0 (Vector + KV + Graph)
Reemplaza/extiende jarvis_grafo.py y SQLite interactions
"""
import os
import json
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class MemoryConfig:
    api_key: str = ""
    user_id: str = "jarvis_user"
    org_id: str = "jarvis_org"
    base_url: str = "https://api.mem0.ai"


class Mem0Store:
    """
    Cliente Mem0 con fallback local si no hay API key.
    Interfaz compatible con jarvis_grafo.py + memoria episódica.
    """

    def __init__(self, config: Optional[MemoryConfig] = None, log=print):
        self.config = config or MemoryConfig(
            api_key=os.getenv("MEM0_API_KEY", ""),
            user_id=os.getenv("MEM0_USER_ID", "jarvis_user"),
            org_id=os.getenv("MEM0_ORG_ID", "jarvis_org"),
        )
        self.log = log
        self._client = None
        self._local_fallback = {}
        self._init_client()

    def _init_client(self):
        if self.config.api_key and not self.config.api_key.startswith("tu_"):
            try:
                from mem0 import MemoryClient
                self._client = MemoryClient(api_key=self.config.api_key)
                self.log("[MEM0] Cliente Mem0 inicializado (cloud)")
            except ImportError:
                self.log("[MEM0] mem0ai no instalado, usando fallback local")
            except Exception as e:
                self.log(f"[MEM0] Error inicializando cliente: {e}")
        else:
            self.log("[MEM0] Sin API key válida, usando fallback local")

    # ─── API Principal ───

    def add(self, messages: List[Dict[str, str]], metadata: Dict = None) -> Dict:
        """Añade memorias desde mensajes de conversación."""
        metadata = metadata or {}
        metadata.setdefault("timestamp", time.time())
        metadata.setdefault("source", "conversation")

        if self._client:
            try:
                return self._client.add(
                    messages=messages,
                    user_id=self.config.user_id,
                    metadata=metadata
                )
            except Exception as e:
                self.log(f"[MEM0] Error añadiendo memoria: {e}")

        # Fallback local
        return self._local_add(messages, metadata)

    def search(self, query: str, limit: int = 5, filters: Dict = None) -> List[Dict]:
        """Búsqueda semántica en memoria."""
        filters = filters or {}
        filters.setdefault("user_id", self.config.user_id)

        if self._client:
            try:
                return self._client.search(
                    query=query,
                    user_id=self.config.user_id,
                    limit=limit,
                    filters=filters
                )
            except Exception as e:
                self.log(f"[MEM0] Error buscando: {e}")

        return self._local_search(query, limit)

    def get_graph(self, entity: str = None) -> Dict:
        """Obtiene grafo de conocimiento (entidades + relaciones)."""
        if self._client:
            try:
                return self._client.get_graph(user_id=self.config.user_id)
            except Exception as e:
                self.log(f"[MEM0] Error obteniendo grafo: {e}")

        return self._local_graph(entity)

    def get_all(self, limit: int = 100) -> List[Dict]:
        """Todas las memorias del usuario."""
        if self._client:
            try:
                return self._client.get_all(user_id=self.config.user_id, limit=limit)
            except Exception as e:
                self.log(f"[MEM0] Error get_all: {e}")

        return list(self._local_fallback.values())[:limit]

    def delete(self, memory_id: str) -> bool:
        if self._client:
            try:
                self._client.delete(memory_id=memory_id)
                return True
            except Exception as e:
                self.log(f"[MEM0] Error borrando: {e}")
        return False

    # ─── Compatibilidad con jarvis_grafo.py ───

    def aprender(self, texto: str) -> bool:
        """Extrae hechos y guarda (兼容 jarvis_grafo.aprender)."""
        # Reutiliza lógica de jarvis_grafo pero guarda en Mem0
        from jarvis_grafo import aprender as grafo_aprender
        grafo_aprender(texto)  # Mantiene grafo local como backup
        # También guarda en Mem0 como episodio
        self.add([
            {"role": "user", "content": texto}
        ], metadata={"type": "fact_extraction"})
        return True

    def consultar(self, texto: str, limite: int = 6) -> str:
        """Consulta memoria relacionada (兼容 jarvis_grafo.consultar)."""
        resultados = self.search(texto, limit=limite)
        if not resultados:
            return ""
        lineas = []
        for r in resultados:
            content = r.get("memory") or r.get("content") or str(r)
            lineas.append(content[:200])
        return " ".join(lineas)

    def contexto(self, limite: int = 10) -> str:
        """Top memorias para inyección general (兼容 jarvis_grafo.contexto)."""
        memorias = self.get_all(limit=limite)
        if not memorias:
            return ""
        return "Memoria Mem0: " + ", ".join(
            (m.get("memory") or m.get("content") or str(m))[:100] for m in memorias
        )

    # ─── Fallback Local (JSON simple) ───

    def _local_add(self, messages, metadata):
        mem_id = f"local_{int(time.time() * 1000)}"
        entry = {
            "id": mem_id,
            "messages": messages,
            "metadata": metadata,
            "created_at": time.time()
        }
        self._local_fallback[mem_id] = entry
        return {"id": mem_id, "status": "stored_locally"}

    def _local_search(self, query: str, limit: int) -> List[Dict]:
        query_lower = query.lower()
        results = []
        for entry in self._local_fallback.values():
            for msg in entry.get("messages", []):
                content = msg.get("content", "").lower()
                if query_lower in content:
                    results.append({"memory": msg.get("content", ""), **entry})
                    break
            if len(results) >= limit:
                break
        return results

    def _local_graph(self, entity: str = None) -> Dict:
        return {"entities": [], "relations": []}


# Instancia global lazy
_mem0_instance: Optional[Mem0Store] = None


def get_mem0(log=print) -> Mem0Store:
    global _mem0_instance
    if _mem0_instance is None:
        _mem0_instance = Mem0Store(log=log)
    return _mem0_instance