#!/usr/bin/env python3
"""
mcp_servers/calendar_server.py - Google Calendar MCP Server (Híbrido y Resiliente)
===================================================================================
Expone Google Calendar como herramientas MCP con respaldo local en SQLite.
Si Google está configurado y autorizado, sincroniza con Google Calendar API v3.
Si no hay credenciales o está offline, persiste y gestiona eventos en SQLite localmente.
¡El servicio NUNCA falla!
"""
import os
import sys
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from aiohttp import web

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from calendar_engine import CalendarEngine, calendar_engine


class GoogleCalendarMCP:
    """Adaptador MCP que delega en el motor híbrido CalendarEngine."""

    def __init__(self, engine: CalendarEngine = None):
        self.engine = engine or calendar_engine

    def list_events(self, time_min: str = None, time_max: str = None,
                    max_results: int = 20, query: str = None) -> List[Dict]:
        return self.engine.list_events(time_min=time_min, time_max=time_max,
                                       query=query, max_results=max_results)

    def get_event(self, event_id: str) -> Dict:
        ev = self.engine.get_event(event_id)
        if not ev:
            raise KeyError(f"Evento {event_id} no encontrado")
        return ev

    def create_event(self, summary: str, start: str, end: str = None,
                     description: str = "", location: str = "",
                     attendees: List[str] = None, reminders: List[Dict] = None) -> Dict:
        return self.engine.create_event(
            summary=summary,
            start=start,
            end=end,
            description=description,
            location=location,
            attendees=attendees,
            reminders=reminders
        )

    def update_event(self, event_id: str, **updates) -> Dict:
        ev = self.engine.update_event(event_id, **updates)
        if not ev:
            raise KeyError(f"Evento {event_id} no encontrado para actualizar")
        return ev

    def reschedule_event(self, event_id: str, new_start: str, new_end: str = None) -> Dict:
        ev = self.engine.reschedule_event(event_id, new_start=new_start, new_end=new_end)
        if not ev:
            raise KeyError(f"Evento {event_id} no encontrado para reprogramar")
        return ev

    def delete_event(self, event_id: str) -> bool:
        return self.engine.delete_event(event_id)

    def get_free_busy(self, time_min: str, time_max: str,
                      calendars: List[str] = None) -> Dict:
        res = self.engine.check_availability(time_min, time_max)
        busy_list = [{"start": c["start"], "end": c["end"]} for c in res["conflicts"]]
        return {
            "primary": {
                "busy": busy_list
            },
            "available": res["available"]
        }

    def list_calendars(self) -> List[Dict]:
        status = self.engine.get_status()
        return [{
            "id": "primary",
            "summary": "Calendario Principal (JARVIS / ULTRON)",
            "primary": True,
            "mode": status["storage_mode"],
            "google_connected": status["google_connected"]
        }]

    def today_events(self) -> List[Dict]:
        return self.engine.get_today_events()

    def get_status(self) -> Dict[str, Any]:
        return self.engine.get_status()


# ─── HTTP Server ───

async def handle_mcp(request: web.Request) -> web.Response:
    cal = request.app["calendar"]
    try:
        body = await request.json()
        tool = body.get("tool")
        args = body.get("arguments", {})

        if not tool:
            return web.json_response({"error": "tool requerido"}, status=400)

        method_map = {
            "cal_list_events": lambda: cal.list_events(args.get("time_min"), args.get("time_max"),
                                                        args.get("max_results", 20), args.get("query")),
            "cal_get_event": lambda: cal.get_event(args["event_id"]),
            "cal_create_event": lambda: cal.create_event(args["summary"], args["start"], args.get("end"),
                                                          args.get("description", ""), args.get("location", ""),
                                                          args.get("attendees"), args.get("reminders")),
            "cal_update_event": lambda: cal.update_event(args["event_id"], **args.get("updates", {})),
            "cal_reschedule_event": lambda: cal.reschedule_event(args["event_id"], args["new_start"], args.get("new_end")),
            "cal_delete_event": lambda: cal.delete_event(args["event_id"]),
            "cal_free_busy": lambda: cal.get_free_busy(args["time_min"], args["time_max"],
                                                        args.get("calendars")),
            "cal_list_calendars": lambda: cal.list_calendars(),
            "cal_today_events": lambda: cal.today_events(),
            "cal_status": lambda: cal.get_status(),
        }

        if tool not in method_map:
            return web.json_response({"error": f"Herramienta desconocida: {tool}"}, status=404)

        import asyncio
        result = await asyncio.get_running_loop().run_in_executor(None, method_map[tool])
        return web.json_response({"result": result})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response(
            {"error": f"{type(e).__name__}: {e}"}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    cal = request.app["calendar"]
    st = cal.get_status()
    return web.json_response({
        "status": "ok",
        "server": "calendar-mcp",
        "storage_mode": st["storage_mode"],
        "google_connected": st["google_connected"],
        "total_events": st["total_events"]
    })


async def handle_tools_list(request: web.Request) -> web.Response:
    tools = [
        {"name": "cal_list_events", "description": "Lista eventos del calendario",
         "inputSchema": {"type": "object", "properties": {
             "time_min": {"type": "string", "format": "date-time"},
             "time_max": {"type": "string", "format": "date-time"},
             "max_results": {"type": "integer"}, "query": {"type": "string"}}}},
        {"name": "cal_get_event", "description": "Obtiene un evento por ID",
         "inputSchema": {"type": "object", "properties": {"event_id": {"type": "string"}}}},
        {"name": "cal_create_event", "description": "Crea un evento nuevo",
         "inputSchema": {"type": "object", "properties": {
             "summary": {"type": "string"}, "start": {"type": "string", "format": "date-time"},
             "end": {"type": "string", "format": "date-time"},
             "description": {"type": "string"}, "location": {"type": "string"},
             "attendees": {"type": "array", "items": {"type": "string"}},
             "reminders": {"type": "array", "items": {"type": "object"}}}}, "required": ["summary", "start"]},
        {"name": "cal_update_event", "description": "Actualiza un evento existente",
         "inputSchema": {"type": "object", "properties": {
             "event_id": {"type": "string"}, "updates": {"type": "object"}}}},
        {"name": "cal_reschedule_event", "description": "Reprograma un evento a nueva fecha/hora",
         "inputSchema": {"type": "object", "properties": {
             "event_id": {"type": "string"}, "new_start": {"type": "string"}, "new_end": {"type": "string"}},
             "required": ["event_id", "new_start"]}},
        {"name": "cal_delete_event", "description": "Borra un evento",
         "inputSchema": {"type": "object", "properties": {"event_id": {"type": "string"}}}},
        {"name": "cal_free_busy", "description": "Consulta disponibilidad (libre/ocupado)",
         "inputSchema": {"type": "object", "properties": {
             "time_min": {"type": "string", "format": "date-time"},
             "time_max": {"type": "string", "format": "date-time"},
             "calendars": {"type": "array", "items": {"type": "string"}}}}, "required": ["time_min", "time_max"]},
        {"name": "cal_list_calendars", "description": "Lista calendarios disponibles",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "cal_today_events", "description": "Retorna todos los eventos de hoy",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "cal_status", "description": "Retorna el estado de sincronización y métricas del calendario",
         "inputSchema": {"type": "object", "properties": {}}},
    ]
    return web.json_response({"tools": tools})


def create_app() -> web.Application:
    cal = GoogleCalendarMCP()
    app = web.Application()
    app["calendar"] = cal
    app.router.add_get("/health", handle_health)
    app.router.add_get("/tools", handle_tools_list)
    app.router.add_post("/call", handle_mcp)
    return app


def main():
    port = int(os.getenv("CAL_MCP_PORT", "8002"))
    web.run_app(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()