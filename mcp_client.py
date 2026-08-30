#!/usr/bin/env python3
"""
mcp_client.py - Cliente MCP con circuit breaker, retry y health checks
"""
import json
import time
import threading
import requests
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable
from functools import wraps


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 30.0  # seconds before half-open
    excluded_exceptions: tuple = ()


@dataclass
class CircuitBreaker:
    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.config.timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
            return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError(f"Circuit '{self.name}' is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.excluded_exceptions:
            raise
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN


class CircuitOpenError(Exception):
    pass


class MCPClient:
    """Cliente HTTP para servidores MCP con circuit breaker por servidor."""

    def __init__(self, base_urls: Dict[str, str], default_timeout: float = 10.0):
        """
        base_urls: {"calendar": "http://localhost:8001", "ha": "http://localhost:8002", ...}
        """
        self.base_urls = base_urls
        self.default_timeout = default_timeout
        self.circuits: Dict[str, CircuitBreaker] = {}
        self._session = requests.Session()
        self._init_circuits()

    def _init_circuits(self):
        for name in self.base_urls:
            self.circuits[name] = CircuitBreaker(
                name=name,
                config=CircuitBreakerConfig(
                    failure_threshold=3,
                    success_threshold=2,
                    timeout=20.0
                )
            )

    def call(self, server: str, tool: str, arguments: Dict[str, Any]) -> Any:
        """Llama a una herramienta MCP en un servidor específico."""
        if server not in self.base_urls:
            raise ValueError(f"Servidor MCP desconocido: {server}")

        url = f"{self.base_urls[server]}/call"
        payload = {"tool": tool, "arguments": arguments}

        def _do_call():
            resp = self._session.post(url, json=payload, timeout=self.default_timeout)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise MCPError(data["error"])
            return data.get("result")

        return self.circuits[server].call(_do_call)

    def health_check(self, server: str) -> bool:
        """Verifica si un servidor MCP está sano."""
        if server not in self.base_urls:
            return False
        try:
            resp = self._session.get(f"{self.base_urls[server]}/health", timeout=3.0)
            return resp.status_code == 200 and resp.json().get("status") == "ok"
        except Exception:
            return False

    def health_check_all(self) -> Dict[str, bool]:
        return {name: self.health_check(name) for name in self.base_urls}

    def get_circuit_states(self) -> Dict[str, str]:
        return {name: cb.state.value for name, cb in self.circuits.items()}


class MCPError(Exception):
    pass


# Decorador para fácil uso
def mcp_call(client: MCPClient, server: str, tool: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            arguments = func(*args, **kwargs) or {}
            return client.call(server, tool, arguments)
        return wrapper
    return decorator