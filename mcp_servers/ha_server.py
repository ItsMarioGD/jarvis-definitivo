#!/usr/bin/env python3
"""
mcp_servers/ha_server.py - Home Assistant MCP Server
Expone control de entidades HA como herramientas MCP.
"""
import os
import sys
import json
import asyncio
import aiohttp
from aiohttp import web
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class HAConfig:
    url: str = os.getenv("HA_URL", "http://localhost:8123")
    token: str = os.getenv("HA_TOKEN", "")
    verify_ssl: bool = False


class HomeAssistantMCP:
    def __init__(self, config: HAConfig = None):
        self.config = config or HAConfig()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.config.token}",
                         "Content-Type": "application/json"},
                connector=aiohttp.TCPConnector(ssl=self.config.verify_ssl)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ─── Herramientas MCP ───

    async def get_states(self, entity_id: str = None) -> Dict:
        """Obtiene estados de entidades. Si entity_id es None, todas."""
        session = await self._get_session()
        url = f"{self.config.url}/api/states"
        if entity_id:
            url += f"/{entity_id}"
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def call_service(self, domain: str, service: str,
                           entity_id: str = None, data: Dict = None) -> Dict:
        """Llama a un servicio HA (ej: light.turn_on, climate.set_temperature)."""
        session = await self._get_session()
        url = f"{self.config.url}/api/services/{domain}/{service}"
        payload = data or {}
        if entity_id:
            payload["entity_id"] = entity_id
        async with session.post(url, json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_config(self) -> Dict:
        session = await self._get_session()
        async with session.get(f"{self.config.url}/api/config") as resp:
            resp.raise_for_status()
            return await resp.json()

    # ─── Wrappers de alto nivel ───

    async def light_control(self, entity_id: str, action: str, **kwargs) -> str:
        """Control de luces: on, off, toggle, brightness, color."""
        if action in ("on", "off", "toggle"):
            await self.call_service("light", action, entity_id=entity_id)
        elif action == "brightness":
            await self.call_service("light", "turn_on", entity_id=entity_id,
                                    data={"brightness_pct": kwargs.get("brightness", 50)})
        elif action == "color":
            await self.call_service("light", "turn_on", entity_id=entity_id,
                                    data={"rgb_color": kwargs.get("rgb", [255, 255, 255])})
        return f"Luz {entity_id} → {action}"

    async def climate_control(self, entity_id: str, action: str, **kwargs) -> str:
        """Control de clima: set_temperature, set_hvac_mode, set_fan_mode."""
        data = {}
        if action == "temperature":
            data["temperature"] = kwargs.get("temp", 22)
        elif action == "mode":
            data["hvac_mode"] = kwargs.get("mode", "heat")
        elif action == "fan":
            data["fan_mode"] = kwargs.get("fan", "auto")
        await self.call_service("climate", f"set_{action}", entity_id=entity_id, data=data)
        return f"Clima {entity_id} → {action}"

    async def lock_control(self, entity_id: str, action: str) -> str:
        """Cerraduras: lock, unlock, open."""
        await self.call_service("lock", action, entity_id=entity_id)
        return f"Cerradura {entity_id} → {action}"

    async def switch_control(self, entity_id: str, action: str) -> str:
        """Interruptores genéricos: on, off, toggle."""
        await self.call_service("switch", action, entity_id=entity_id)
        return f"Switch {entity_id} → {action}"

    async def media_player_control(self, entity_id: str, action: str, **kwargs) -> str:
        """Media players: play, pause, volume_set, media_play."""
        data = {}
        if action == "volume":
            data["volume_level"] = kwargs.get("level", 0.5)
        elif action == "play_media":
            data["media_content_id"] = kwargs.get("media_id")
            data["media_content_type"] = kwargs.get("media_type", "music")
        await self.call_service("media_player", action, entity_id=entity_id, data=data)
        return f"Media {entity_id} → {action}"

    async def notify(self, message: str, target: str = "notify.mobile_app") -> str:
        """Envía notificación a dispositivo."""
        await self.call_service("notify", target.split(".")[-1], data={"message": message})
        return f"Notificación enviada: {message[:50]}"


# ─── HTTP Server (MCP compatible) ───

async def handle_mcp(request: web.Request) -> web.Response:
    """Endpoint MCP compatible: POST /call {tool, arguments}"""
    ha = request.app["ha"]
    try:
        body = await request.json()
        tool = body.get("tool")
        args = body.get("arguments", {})

        if not tool:
            return web.json_response({"error": "tool requerido"}, status=400)

        # Mapeo tool → método
        method_map = {
            "ha_get_states": lambda: ha.get_states(args.get("entity_id")),
            "ha_call_service": lambda: ha.call_service(args["domain"], args["service"],
                                                        args.get("entity_id"), args.get("data")),
            "ha_light_control": lambda: ha.light_control(args["entity_id"], args["action"],
                                                         **args.get("params", {})),
            "ha_climate_control": lambda: ha.climate_control(args["entity_id"], args["action"],
                                                              **args.get("params", {})),
            "ha_lock_control": lambda: ha.lock_control(args["entity_id"], args["action"]),
            "ha_switch_control": lambda: ha.switch_control(args["entity_id"], args["action"]),
            "ha_media_control": lambda: ha.media_player_control(args["entity_id"], args["action"],
                                                                 **args.get("params", {})),
            "ha_notify": lambda: ha.notify(args["message"], args.get("target")),
        }

        if tool not in method_map:
            return web.json_response({"error": f"Herramienta desconocida: {tool}"}, status=404)

        result = await method_map[tool]()
        return web.json_response({"result": result})

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    ha = request.app["ha"]
    try:
        await ha.get_config()
        return web.json_response({"status": "ok", "server": "ha-mcp"})
    except Exception:
        return web.json_response({"status": "error", "server": "ha-mcp"}, status=503)


async def handle_tools_list(request: web.Request) -> web.Response:
    tools = [
        {"name": "ha_get_states", "description": "Obtiene estados de entidades HA",
         "inputSchema": {"type": "object", "properties": {"entity_id": {"type": "string"}}}},
        {"name": "ha_call_service", "description": "Llama a cualquier servicio HA",
         "inputSchema": {"type": "object", "properties": {
             "domain": {"type": "string"}, "service": {"type": "string"},
             "entity_id": {"type": "string"}, "data": {"type": "object"}}}},
        {"name": "ha_light_control", "description": "Control de luces",
         "inputSchema": {"type": "object", "properties": {
             "entity_id": {"type": "string"}, "action": {"type": "string", "enum": ["on", "off", "toggle", "brightness", "color"]},
             "params": {"type": "object"}}}},
        {"name": "ha_climate_control", "description": "Control de termostatos/clima",
         "inputSchema": {"type": "object", "properties": {
             "entity_id": {"type": "string"}, "action": {"type": "string", "enum": ["temperature", "mode", "fan"]},
             "params": {"type": "object"}}}},
        {"name": "ha_lock_control", "description": "Control de cerraduras inteligentes",
         "inputSchema": {"type": "object", "properties": {
             "entity_id": {"type": "string"}, "action": {"type": "string", "enum": ["lock", "unlock", "open"]}}}},
        {"name": "ha_switch_control", "description": "Control de switches",
         "inputSchema": {"type": "object", "properties": {
             "entity_id": {"type": "string"}, "action": {"type": "string", "enum": ["on", "off", "toggle"]}}}},
        {"name": "ha_media_control", "description": "Control de media players",
         "inputSchema": {"type": "object", "properties": {
             "entity_id": {"type": "string"}, "action": {"type": "string"}, "params": {"type": "object"}}}},
        {"name": "ha_notify", "description": "Envía notificación a dispositivo móvil",
         "inputSchema": {"type": "object", "properties": {
             "message": {"type": "string"}, "target": {"type": "string"}}}},
    ]
    return web.json_response({"tools": tools})


def create_app() -> web.Application:
    config = HAConfig()
    ha = HomeAssistantMCP(config)

    app = web.Application()
    app["ha"] = ha
    app.router.add_get("/health", handle_health)
    app.router.add_get("/tools", handle_tools_list)
    app.router.add_post("/call", handle_mcp)

    async def cleanup(app):
        await ha.close()
    app.on_cleanup.append(cleanup)

    return app


def main():
    port = int(os.getenv("HA_MCP_PORT", "8001"))
    web.run_app(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()