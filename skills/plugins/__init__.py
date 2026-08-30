#!/usr/bin/env python3
"""
skills/plugins/__init__.py — Registro de plugins de habilidades de Jarvis.

Cada archivo .py de este paquete (salvo __init__.py y los que empiezan por
"_") es un plugin: expone una función register() que devuelve un
SkillPlugin. El registro se descubre automáticamente al primer uso y se
cachea por proceso (get_plugin_registry).

Contrato de un plugin (ver home_assistant.py como referencia):
    from skills.plugins import SkillPlugin

    def register() -> SkillPlugin:
        return SkillPlugin(
            name="mi_plugin",
            patterns=[r"regex1", r"regex2"],
            handler=mi_funcion_o_metodo,   # (text: str, core) -> str | None
            priority=10,                    # mayor = se evalúa antes
            description="Qué hace este plugin",
        )
"""
import os
import re
import importlib
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class SkillPlugin:
    name: str
    patterns: List[str]
    handler: Callable[[str, object], Optional[str]]
    priority: int = 0
    description: str = ""
    _compiled: list = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def matches(self, text: str) -> bool:
        return any(p.search(text) for p in self._compiled)


class PluginRegistry:
    """Descubre y despacha los plugins de skills/plugins/."""

    def __init__(self, log=print):
        self.log = log
        self._plugins: List[SkillPlugin] = []
        self._cargar()

    def _cargar(self):
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        for fn in sorted(os.listdir(pkg_dir)):
            if not fn.endswith(".py") or fn == "__init__.py" or fn.startswith("_"):
                continue
            modname = f"skills.plugins.{fn[:-3]}"
            try:
                mod = importlib.import_module(modname)
                registrar = getattr(mod, "register", None)
                if registrar is None:
                    continue
                plugin = registrar()
                if isinstance(plugin, SkillPlugin):
                    self._plugins.append(plugin)
                    self.log(f"[PLUGINS] «{plugin.name}» cargado.")
            except Exception as e:
                self.log(f"[PLUGINS] {fn} no se pudo cargar: {e}")
        self._plugins.sort(key=lambda p: -p.priority)

    def handle(self, text: str, core) -> Optional[str]:
        for plugin in self._plugins:
            if not plugin.matches(text):
                continue
            try:
                reply = plugin.handler(text, core)
            except Exception as e:
                self.log(f"[PLUGINS] «{plugin.name}» falló: {e}")
                continue
            if reply:
                return reply
        return None


_REGISTRY: Optional[PluginRegistry] = None


def get_plugin_registry(log=print) -> PluginRegistry:
    """Registro cacheado por proceso (se construye una sola vez)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PluginRegistry(log=log)
    return _REGISTRY
