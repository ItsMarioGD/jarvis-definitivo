#!/usr/bin/env python3
"""
skills/plugins/home_assistant.py - Plugin Home Assistant
Control de luces, clima, cerraduras, switches, media players, notificaciones.
"""
from skills.plugins import SkillPlugin
import json


class HomeAssistantSkill:
    """Skill de Home Assistant via MCP client."""

    patterns = [
        r"\b(enciende|apaga|toggle)\s+(la\s+)?luz",
        r"\b(brillo|brillante|intensidad)\s+(de\s+la\s+)?luz",
        r"\b(color|cambia\s+color)\s+(de\s+la\s+)?luz",
        r"\b(temperatura|clima|calefaccion|aire)\s+(de\s+la\s+)?(casa|habitacion|salon)",
        r"\b(abre|cierra|bloquea|desbloquea)\s+(la\s+)?(puerta|cerradura)",
        r"\b(enciende|apaga)\s+(el\s+)?(switch|interruptor|enchufe)",
        r"\b(reproduce|pausa|siguiente|anterior|volumen)\s+(en\s+)?(spotify|sonos|media)",
        r"\bnotifica|avisa|mandame\s+(un\s+)?mensaje",
    ]
    priority = 10
    description = "Control Home Assistant: luces, clima, cerraduras, media, notificaciones"

    def __init__(self):
        self._mcp_client = None

    def _get_mcp(self):
        if self._mcp_client is None:
            try:
                from mcp_client import MCPClient
                self._mcp_client = MCPClient({"ha": "http://localhost:8001"})
            except Exception:
                pass
        return self._mcp_client

    def handle(self, text: str, core) -> str | None:
        t = text.lower()
        mcp = self._get_mcp()

        if not mcp:
            return "Home Assistant MCP no disponible. Verifica servidor en puerto 8001."

        try:
            # Luces
            if any(k in t for k in ("enciende", "apaga", "toggle")) and "luz" in t:
                entity = self._extract_entity(t, "luz") or "light.salon"
                action = "on" if "enciende" in t else ("off" if "apaga" in t else "toggle")
                return mcp.call("ha", "ha_light_control", {"entity_id": entity, "action": action})

            if "brillo" in t or "intensidad" in t:
                entity = self._extract_entity(t, "luz") or "light.salon"
                import re
                m = re.search(r"(\d{1,3})\s*%", t)
                brightness = int(m.group(1)) if m else 50
                return mcp.call("ha", "ha_light_control",
                                {"entity_id": entity, "action": "brightness", "params": {"brightness": brightness}})

            if "color" in t and "luz" in t:
                entity = self._extract_entity(t, "luz") or "light.salon"
                return mcp.call("ha", "ha_light_control",
                                {"entity_id": entity, "action": "color", "params": {"rgb": [255, 100, 100]}})

            # Clima
            if any(k in t for k in ("temperatura", "clima", "calefaccion", "aire")):
                entity = self._extract_entity(t, "clima") or "climate.salon"
                if "temperatura" in t:
                    import re
                    m = re.search(r"(\d{1,2})\s*°?\s*[cf]?", t)
                    temp = int(m.group(1)) if m else 22
                    return mcp.call("ha", "ha_climate_control",
                                    {"entity_id": entity, "action": "temperature", "params": {"temp": temp}})
                elif "modo" in t:
                    mode = "heat" if "calor" in t else ("cool" if "frio" in t else "auto")
                    return mcp.call("ha", "ha_climate_control",
                                    {"entity_id": entity, "action": "mode", "params": {"mode": mode}})

            # Cerraduras
            if any(k in t for k in ("abre", "cierra", "bloquea", "desbloquea")) and "puerta" in t:
                entity = self._extract_entity(t, "puerta") or "lock.puerta_principal"
                action = "unlock" if "abre" in t or "desbloquea" in t else "lock"
                return mcp.call("ha", "ha_lock_control", {"entity_id": entity, "action": action})

            # Switches
            if any(k in t for k in ("enciende", "apaga")) and any(k in t for k in ("switch", "interruptor", "enchufe")):
                entity = self._extract_entity(t, "switch") or "switch.enchufe_1"
                action = "on" if "enciende" in t else "off"
                return mcp.call("ha", "ha_switch_control", {"entity_id": entity, "action": action})

            # Media
            if any(k in t for k in ("reproduce", "pausa", "siguiente", "anterior", "volumen")):
                entity = self._extract_entity(t, "media") or "media_player.spotify"
                action_map = {"reproduce": "media_play", "pausa": "media_pause",
                              "siguiente": "media_next_track", "anterior": "media_previous_track"}
                for k, v in action_map.items():
                    if k in t:
                        return mcp.call("ha", "ha_media_control",
                                        {"entity_id": entity, "action": v})
                if "volumen" in t:
                    import re
                    m = re.search(r"(\d{1,3})\s*%", t)
                    level = int(m.group(1)) / 100 if m else 0.5
                    return mcp.call("ha", "ha_media_control",
                                    {"entity_id": entity, "action": "volume", "params": {"level": level}})

            # Notificaciones
            if "notifica" in t or "avisa" in t or "mandame" in t:
                import re
                msg_match = re.search(r"(?:notifica|avisa|mandame).+?(?:que|diciendo)\s+(.+)$", t)
                message = msg_match.group(1) if msg_match else text
                return mcp.call("ha", "ha_notify", {"message": message.strip()})

        except Exception as e:
            return f"Error Home Assistant: {e}"

        return None

    def _extract_entity(self, text: str, keyword: str) -> str | None:
        """Extrae entity_id del texto: 'luz del salon' -> 'light.salon'"""
        import re
        patterns = [
            rf"{keyword}\s+(?:de\s+|del\s+|la\s+)?(\w+(?:\s+\w+)*)",
            rf"(?:la\s+|el\s+)?(\w+(?:\s+\w+)*)\s+{keyword}",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                name = m.group(1).strip().replace(" ", "_").lower()
                return f"light.{name}" if keyword == "luz" else f"{keyword}.{name}"
        return None


def register() -> SkillPlugin:
    return SkillPlugin(
        name="home_assistant",
        patterns=HomeAssistantSkill.patterns,
        handler=HomeAssistantSkill().handle,
        priority=HomeAssistantSkill.priority,
        description=HomeAssistantSkill.description
    )