#!/usr/bin/env python3
"""
mcp_servers/calendar_server.py - Google Calendar MCP Server
Expone Google Calendar como herramientas MCP.
Requiere: google-api-python-client, google-auth-oauthlib, google-auth-httplib2
Config: GOOGLE_CREDENTIALS_JSON (path a credentials.json) + token.json generado en primer run
"""
import os
import json
import sys
import pickle
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from aiohttp import web

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False


SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_JSON", "token.json")


@dataclass
class CalendarConfig:
    credentials_file: str = CREDENTIALS_FILE
    token_file: str = TOKEN_FILE
    calendar_id: str = "primary"


class GoogleCalendarMCP:
    def __init__(self, config: CalendarConfig = None):
        self.config = config or CalendarConfig()
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service

        if not GOOGLE_AVAILABLE:
            raise RuntimeError("google-api-python-client no instalado")

        creds = None
        if os.path.exists(self.config.token_file):
            with open(self.config.token_file, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.config.credentials_file):
                    raise RuntimeError(f"Credentials no encontrado: {self.config.credentials_file}")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.config.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self.config.token_file, "wb") as f:
                pickle.dump(creds, f)

        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    # ─── Herramientas MCP ───

    async def list_events(self, time_min: str = None, time_max: str = None,
                          max_results: int = 20, query: str = None) -> List[Dict]:
        """Lista eventos en rango temporal."""
        def _run():
            service = self._get_service()
            now = datetime.now(timezone.utc).isoformat()
            events_result = service.events().list(
                calendarId=self.config.calendar_id,
                timeMin=time_min or now,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
                q=query
            ).execute()
            events = events_result.get("items", [])
            return [self._format_event(e) for e in events]
        return await asyncio.to_thread(_run)

    async def get_event(self, event_id: str) -> Dict:
        def _run():
            service = self._get_service()
            event = service.events().get(calendarId=self.config.calendar_id, eventId=event_id).execute()
            return self._format_event(event)
        return await asyncio.to_thread(_run)

    async def create_event(self, summary: str, start: str, end: str,
                           description: str = "", location: str = "",
                           attendees: List[str] = None, reminders: List[Dict] = None) -> Dict:
        """Crea evento. start/end en ISO format (2024-01-15T10:00:00)."""
        def _run():
            service = self._get_service()
            event = {
                "summary": summary,
                "location": location,
                "description": description,
                "start": {"dateTime": start, "timeZone": "Europe/Madrid"},
                "end": {"dateTime": end, "timeZone": "Europe/Madrid"},
            }
            if attendees:
                event["attendees"] = [{"email": email} for email in attendees]
            if reminders:
                event["reminders"] = {"useDefault": False, "overrides": reminders}
            else:
                event["reminders"] = {"useDefault": True}
            created = service.events().insert(calendarId=self.config.calendar_id, body=event).execute()
            return self._format_event(created)
        return await asyncio.to_thread(_run)

    async def update_event(self, event_id: str, **updates) -> Dict:
        """Actualiza campos de un evento."""
        def _run():
            service = self._get_service()
            event = service.events().get(calendarId=self.config.calendar_id, eventId=event_id).execute()
            for key, value in updates.items():
                if key in ("summary", "description", "location"):
                    event[key] = value
                elif key == "start":
                    event["start"]["dateTime"] = value
                elif key == "end":
                    event["end"]["dateTime"] = value
                elif key == "attendees":
                    event["attendees"] = [{"email": e} for e in value]
            updated = service.events().update(calendarId=self.config.calendar_id,
                                               eventId=event_id, body=event).execute()
            return self._format_event(updated)
        return await asyncio.to_thread(_run)

    async def delete_event(self, event_id: str) -> bool:
        def _run():
            service = self._get_service()
            service.events().delete(calendarId=self.config.calendar_id, eventId=event_id).execute()
            return True
        return await asyncio.to_thread(_run)

    async def get_free_busy(self, time_min: str, time_max: str,
                            calendars: List[str] = None) -> Dict:
        """Consulta disponibilidad (free/busy)."""
        def _run():
            service = self._get_service()
            cal_list = calendars or [self.config.calendar_id]
            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "items": [{"id": cal} for cal in cal_list]
            }
            result = service.freebusy().query(body=body).execute()
            return result.get("calendars", {})
        return await asyncio.to_thread(_run)

    async def list_calendars(self) -> List[Dict]:
        def _run():
            service = self._get_service()
            result = service.calendarList().list().execute()
            return result.get("items", [])
        return await asyncio.to_thread(_run)

    @staticmethod
    def _format_event(event: Dict) -> Dict:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        return {
            "id": event["id"],
            "summary": event.get("summary", "(Sin título)"),
            "start": start,
            "end": end,
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "attendees": [a.get("email") for a in event.get("attendees", [])],
            "htmlLink": event.get("htmlLink", "")
        }


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
            "cal_create_event": lambda: cal.create_event(args["summary"], args["start"], args["end"],
                                                          args.get("description", ""), args.get("location", ""),
                                                          args.get("attendees"), args.get("reminders")),
            "cal_update_event": lambda: cal.update_event(args["event_id"], **args.get("updates", {})),
            "cal_delete_event": lambda: cal.delete_event(args["event_id"]),
            "cal_free_busy": lambda: cal.get_free_busy(args["time_min"], args["time_max"],
                                                        args.get("calendars")),
            "cal_list_calendars": lambda: cal.list_calendars(),
        }

        if tool not in method_map:
            return web.json_response({"error": f"Herramienta desconocida: {tool}"}, status=404)

        result = await method_map[tool]()
        return web.json_response({"result": result})

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    cal = request.app["calendar"]
    try:
        cal._get_service()
        return web.json_response({"status": "ok", "server": "calendar-mcp"})
    except Exception:
        return web.json_response({"status": "error", "server": "calendar-mcp"}, status=503)


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
             "reminders": {"type": "array", "items": {"type": "object"}}}}, "required": ["summary", "start", "end"]},
        {"name": "cal_update_event", "description": "Actualiza un evento existente",
         "inputSchema": {"type": "object", "properties": {
             "event_id": {"type": "string"}, "updates": {"type": "object"}}}},
        {"name": "cal_delete_event", "description": "Borra un evento",
         "inputSchema": {"type": "object", "properties": {"event_id": {"type": "string"}}}},
        {"name": "cal_free_busy", "description": "Consulta disponibilidad (libre/ocupado)",
         "inputSchema": {"type": "object", "properties": {
             "time_min": {"type": "string", "format": "date-time"},
             "time_max": {"type": "string", "format": "date-time"},
             "calendars": {"type": "array", "items": {"type": "string"}}}}, "required": ["time_min", "time_max"]},
        {"name": "cal_list_calendars", "description": "Lista calendarios disponibles",
         "inputSchema": {"type": "object", "properties": {}}},
    ]
    return web.json_response({"tools": tools})


def create_app() -> web.Application:
    config = CalendarConfig()
    cal = GoogleCalendarMCP(config)

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