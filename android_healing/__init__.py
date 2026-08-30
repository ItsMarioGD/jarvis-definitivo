"""android_healing — motor de auto-reparación de selectores Android (Ultron).

Antes vivía en `ultron_skills/self_healing.py`, un paquete que colisionaba
con el módulo `ultron_skills.py` (mismo nombre, distinto tipo) y por tanto
era inalcanzable por import. Ver mcp_servers/android_server.py, que ahora
enruta `android_find_tap` a través de `execute_android_action`.
"""
from android_healing.self_healing import SelfHealingEngine, execute_android_action

__all__ = ["SelfHealingEngine", "execute_android_action"]
