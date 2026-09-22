#!/usr/bin/env python3
"""
calendar_engine.py — Motor de Calendario Híbrido y Resiliente para JARVIS y ULTRON
===================================================================================
Proporciona gestión completa de agenda y operaciones temporales:
1. Google Calendar API v3 (si hay credenciales/token autorizados).
2. SQLite Local Persistente (calendar_events.db): garantizado al 100%, nunca falla,
   funciona offline y almacena eventos con o sin cuenta de Google.
3. Sincronización transparente y enriquecimiento de eventos.
4. Detección de disponibilidad, conflictos y reprogramación.
"""

import os
import sys
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import jarvis_config
    CREDENTIALS_FILE = jarvis_config.buscar_credenciales_google() or "credentials.json"
    TOKEN_FILE = jarvis_config.ruta_token_google()
except Exception:
    CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_JSON", os.path.join(_ROOT, "credentials.json"))
    TOKEN_FILE = os.getenv("GOOGLE_TOKEN_JSON", os.path.join(_ROOT, "token.json"))

# Base de datos SQLite para persistencia local
DB_PATH = os.path.join(_ROOT, "calendar_events.db")

# Intentar cargar librerías de Google
GOOGLE_AVAILABLE = False
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _obtener_zona_horaria() -> str:
    tz = os.getenv("JARVIS_TIMEZONE", "").strip()
    if tz:
        return tz
    try:
        local_now = datetime.now().astimezone()
        offset = local_now.strftime("%z")
        return f"UTC{offset[:3]}:{offset[3:]}"
    except Exception:
        return "UTC"


class CalendarEngine:
    _instancia = None

    @classmethod
    def get_instance(cls):
        if cls._instancia is None:
            cls._instancia = cls()
        return cls._instancia

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._service = None
        self._google_checked = False
        self._init_db()

    def _init_db(self):
        """Inicializa las tablas locales en SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    google_id TEXT,
                    summary TEXT NOT NULL,
                    start_iso TEXT NOT NULL,
                    end_iso TEXT NOT NULL,
                    description TEXT,
                    location TEXT,
                    attendees TEXT,
                    reminders TEXT,
                    source TEXT DEFAULT 'local',
                    status TEXT DEFAULT 'confirmed',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    def _get_google_service(self):
        """Intenta obtener o refrescar el servicio de Google Calendar."""
        if not GOOGLE_AVAILABLE:
            return None

        creds = None
        if os.path.exists(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except Exception:
                try:
                    import pickle
                    with open(TOKEN_FILE, "rb") as f:
                        creds = pickle.load(f)
                except Exception:
                    creds = None

        if creds and not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    try:
                        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                            f.write(creds.to_json())
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[CALENDAR-ENGINE] No se pudo refrescar token de Google: {e}")
                    creds = None
            else:
                creds = None

        if creds and creds.valid:
            try:
                self._service = build("calendar", "v3", credentials=creds)
                return self._service
            except Exception as e:
                print(f"[CALENDAR-ENGINE] Error construyendo cliente Google Calendar: {e}")
                return None
        return None

    @property
    def is_google_connected(self) -> bool:
        srv = self._get_google_service()
        return srv is not None

    def get_status(self) -> Dict[str, Any]:
        """Devuelve el estado de conectividad y métricas del calendario."""
        google_ok = self.is_google_connected
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM events WHERE status != 'cancelled'")
            total_local = cursor.fetchone()[0]

        hoy_inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        hoy_fin = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        eventos_hoy = self.list_events(time_min=hoy_inicio, time_max=hoy_fin)

        return {
            "google_connected": google_ok,
            "storage_mode": "HÍBRIDO (Google + Local)" if google_ok else "LOCAL AUTÓNOMO (SQLite)",
            "credentials_file": CREDENTIALS_FILE if os.path.exists(CREDENTIALS_FILE) else None,
            "token_file": TOKEN_FILE if os.path.exists(TOKEN_FILE) else None,
            "total_events": total_local,
            "today_events_count": len(eventos_hoy),
            "timezone": _obtener_zona_horaria(),
        }

    # ─── MÉTODOS CRUD COMPLETOS ───

    def list_events(self, time_min: Optional[str] = None, time_max: Optional[str] = None,
                    query: Optional[str] = None, max_results: int = 50) -> List[Dict[str, Any]]:
        """Lista eventos. Si Google Calendar está activo, sincroniza y combina; si no, usa SQLite local."""
        srv = self._get_google_service()
        google_events_map = {}

        if srv:
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                t_min = time_min or now_iso
                res = srv.events().list(
                    calendarId="primary",
                    timeMin=t_min if ("Z" in t_min or "+" in t_min or "-" in t_min[-6:]) else t_min + "Z",
                    timeMax=(time_max if ("Z" in time_max or "+" in time_max or "-" in time_max[-6:]) else time_max + "Z") if time_max else None,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                    q=query,
                ).execute()

                for it in res.get("items", []):
                    ev_fmt = self._format_google_event(it)
                    google_events_map[ev_fmt["id"]] = ev_fmt
                    self._upsert_local_cache(ev_fmt, google_id=it["id"])
            except Exception as e:
                print(f"[CALENDAR-ENGINE] Aviso: consulta Google falló, recurriendo a DB local: {e}")

        # Consultar DB local
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            sql = "SELECT * FROM events WHERE status != 'cancelled'"
            params = []
            if time_min:
                sql += " AND end_iso >= ?"
                params.append(time_min)
            if time_max:
                sql += " AND start_iso <= ?"
                params.append(time_max)
            if query:
                sql += " AND (summary LIKE ? OR description LIKE ?)"
                params.extend([f"%{query}%", f"%{query}%"])
            sql += " ORDER BY start_iso ASC LIMIT ?"
            params.append(max_results)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

        events = []
        for r in rows:
            events.append({
                "id": r["id"],
                "google_id": r["google_id"],
                "summary": r["summary"],
                "start": r["start_iso"],
                "end": r["end_iso"],
                "description": r["description"] or "",
                "location": r["location"] or "",
                "attendees": json.loads(r["attendees"]) if r["attendees"] else [],
                "reminders": json.loads(r["reminders"]) if r["reminders"] else [],
                "source": r["source"],
                "status": r["status"]
            })
        return events

    def get_today_events(self) -> List[Dict[str, Any]]:
        """Retorna todos los eventos programados para hoy."""
        hoy = datetime.now()
        inicio = hoy.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
        fin = hoy.replace(hour=23, minute=59, second=59, microsecond=999999).strftime("%Y-%m-%dT%H:%M:%S")
        return self.list_events(time_min=inicio, time_max=fin)

    def get_upcoming_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """Retorna eventos para los próximos N días a partir de ahora."""
        ahora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        limite = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        return self.list_events(time_min=ahora, time_max=limite)

    def create_event(self, summary: str, start: str, end: Optional[str] = None,
                     description: str = "", location: str = "",
                     attendees: Optional[List[str]] = None, reminders: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Crea un evento en el calendario.
        start / end deben ser strings en formato ISO (ej. 2026-09-08T10:00:00).
        Si no se pasa 'end', se asume 1 hora después de 'start'.
        """
        if not end:
            try:
                st_dt = datetime.fromisoformat(start.replace("Z", ""))
                end = (st_dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:
                end = start

        event_id = str(uuid.uuid4())[:12]
        now_ts = datetime.now().isoformat()
        google_id = None
        html_link = ""
        source = "local"

        # 1. Intentar en Google Calendar
        srv = self._get_google_service()
        if srv:
            try:
                g_body = {
                    "summary": summary,
                    "location": location,
                    "description": description,
                    "start": {"dateTime": start if "T" in start else f"{start}T09:00:00", "timeZone": _obtener_zona_horaria()},
                    "end": {"dateTime": end if "T" in end else f"{end}T10:00:00", "timeZone": _obtener_zona_horaria()},
                }
                if attendees:
                    g_body["attendees"] = [{"email": a} for a in attendees]
                if reminders:
                    g_body["reminders"] = {"useDefault": False, "overrides": reminders}
                else:
                    g_body["reminders"] = {"useDefault": True}

                g_res = srv.events().insert(calendarId="primary", body=g_body).execute()
                google_id = g_res.get("id")
                html_link = g_res.get("htmlLink", "")
                source = "google"
            except Exception as e:
                print(f"[CALENDAR-ENGINE] Aviso: Creación en Google falló ({e}). Guardando localmente.")

        # 2. Guardar en SQLite local
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (id, google_id, summary, start_iso, end_iso, description, location,
                                    attendees, reminders, source, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?)
            """, (
                event_id, google_id, summary, start, end, description, location,
                json.dumps(attendees or []), json.dumps(reminders or []), source, now_ts, now_ts
            ))
            conn.commit()

        return {
            "id": event_id,
            "google_id": google_id,
            "summary": summary,
            "start": start,
            "end": end,
            "description": description,
            "location": location,
            "source": source,
            "htmlLink": html_link,
            "status": "confirmed"
        }

    def update_event(self, event_id: str, **updates) -> Optional[Dict[str, Any]]:
        """Actualiza campos de un evento (summary, start, end, description, location)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events WHERE id = ? OR google_id = ?", (event_id, event_id))
            ev = cursor.fetchone()
            if not ev:
                return None

            google_id = ev["google_id"]
            campos = []
            valores = []
            for k in ("summary", "start_iso", "end_iso", "description", "location"):
                alt_k = "start" if k == "start_iso" else ("end" if k == "end_iso" else k)
                if alt_k in updates:
                    campos.append(f"{k} = ?")
                    valores.append(updates[alt_k])
                elif k in updates:
                    campos.append(f"{k} = ?")
                    valores.append(updates[k])

            now_ts = datetime.now().isoformat()
            campos.append("updated_at = ?")
            valores.append(now_ts)
            valores.append(ev["id"])

            cursor.execute(f"UPDATE events SET {', '.join(campos)} WHERE id = ?", valores)
            conn.commit()

        # Si estaba en Google Calendar, actualizar remotamente
        srv = self._get_google_service()
        if srv and google_id:
            try:
                patch_body = {}
                if "summary" in updates:
                    patch_body["summary"] = updates["summary"]
                if "description" in updates:
                    patch_body["description"] = updates["description"]
                if "location" in updates:
                    patch_body["location"] = updates["location"]
                if "start" in updates:
                    patch_body["start"] = {"dateTime": updates["start"], "timeZone": _obtener_zona_horaria()}
                if "end" in updates:
                    patch_body["end"] = {"dateTime": updates["end"], "timeZone": _obtener_zona_horaria()}
                if patch_body:
                    srv.events().patch(calendarId="primary", eventId=google_id, body=patch_body).execute()
            except Exception as e:
                print(f"[CALENDAR-ENGINE] Aviso: actualización en Google falló ({e})")

        return self.get_event(ev["id"])

    def reschedule_event(self, event_id: str, new_start: str, new_end: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Mueve un evento a una nueva fecha/hora."""
        if not new_end:
            try:
                st = datetime.fromisoformat(new_start.replace("Z", ""))
                new_end = (st + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:
                new_end = new_start
        return self.update_event(event_id, start=new_start, end=new_end)

    def delete_event(self, event_id: str) -> bool:
        """Elimina un evento de SQLite y de Google Calendar si correspondiera."""
        google_id = None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT google_id FROM events WHERE id = ? OR google_id = ?", (event_id, event_id))
            row = cursor.fetchone()
            if row:
                google_id = row[0]
            cursor.execute("DELETE FROM events WHERE id = ? OR google_id = ?", (event_id, event_id))
            conn.commit()

        srv = self._get_google_service()
        if srv and google_id:
            try:
                srv.events().delete(calendarId="primary", eventId=google_id).execute()
            except Exception as e:
                print(f"[CALENDAR-ENGINE] Aviso: borrado en Google falló ({e})")

        return True

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene un evento por su ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events WHERE id = ? OR google_id = ?", (event_id, event_id))
            r = cursor.fetchone()
            if not r:
                return None
            return {
                "id": r["id"],
                "google_id": r["google_id"],
                "summary": r["summary"],
                "start": r["start_iso"],
                "end": r["end_iso"],
                "description": r["description"] or "",
                "location": r["location"] or "",
                "source": r["source"],
                "status": r["status"]
            }

    def check_availability(self, start: str, end: str) -> Dict[str, Any]:
        """Comprueba si un intervalo de tiempo tiene colisiones con eventos existentes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM events
                WHERE status != 'cancelled'
                  AND start_iso < ?
                  AND end_iso > ?
            """, (end, start))
            conflicts = [dict(r) for r in cursor.fetchall()]

        return {
            "available": len(conflicts) == 0,
            "conflicts_count": len(conflicts),
            "conflicts": [{
                "id": c["id"],
                "summary": c["summary"],
                "start": c["start_iso"],
                "end": c["end_iso"]
            } for c in conflicts]
        }

    # ─── HELPERS INTERNOS ───
    def _format_google_event(self, item: Dict[str, Any]) -> Dict[str, Any]:
        st = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date") or ""
        en = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date") or ""
        return {
            "id": item.get("id"),
            "summary": item.get("summary", "(Sin título)"),
            "start": st,
            "end": en,
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "attendees": [a.get("email") for a in item.get("attendees", [])],
            "htmlLink": item.get("htmlLink", ""),
            "source": "google",
            "status": item.get("status", "confirmed")
        }

    def _upsert_local_cache(self, fmt_event: Dict[str, Any], google_id: str):
        now_ts = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (id, google_id, summary, start_iso, end_iso, description, location,
                                    attendees, reminders, source, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'google', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    google_id = excluded.google_id,
                    summary = excluded.summary,
                    start_iso = excluded.start_iso,
                    end_iso = excluded.end_iso,
                    description = excluded.description,
                    location = excluded.location,
                    status = excluded.status,
                    updated_at = excluded.updated_at
            """, (
                fmt_event["id"], google_id, fmt_event["summary"], fmt_event["start"], fmt_event["end"],
                fmt_event.get("description", ""), fmt_event.get("location", ""),
                json.dumps(fmt_event.get("attendees") or []), "[]",
                fmt_event.get("status", "confirmed"), now_ts, now_ts
            ))
            conn.commit()


    # Aliases en español para máxima compatibilidad
    def crear_evento(self, summary: str, start_time: Any, end_time: Optional[Any] = None,
                     description: str = "", location: str = "") -> Dict[str, Any]:
        start_str = start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time)
        end_str = end_time.isoformat() if hasattr(end_time, "isoformat") else (str(end_time) if end_time else None)
        return self.create_event(summary=summary, start=start_str, end=end_str, description=description, location=location)

    def listar_eventos(self, max_results: int = 10, time_min: Optional[str] = None,
                       time_max: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.list_events(time_min=time_min, time_max=time_max, max_results=max_results)

    def eventos_hoy(self) -> List[Dict[str, Any]]:
        return self.get_today_events()

    def proximos_eventos(self, days: int = 7) -> List[Dict[str, Any]]:
        return self.get_upcoming_events(days=days)

    def eliminar_evento(self, event_id: str) -> Dict[str, Any]:
        ok = self.delete_event(event_id)
        return {"success": ok}

    def reprogramar_evento(self, event_id: str, nueva_fecha_hora: Any) -> Dict[str, Any]:
        start_str = nueva_fecha_hora.isoformat() if hasattr(nueva_fecha_hora, "isoformat") else str(nueva_fecha_hora)
        ev = self.reschedule_event(event_id, new_start=start_str)
        return {"success": bool(ev), "event": ev}

    def verificar_disponibilidad(self, fecha_hora: Any, duracion_minutos: int = 60) -> Dict[str, Any]:
        if hasattr(fecha_hora, "isoformat"):
            start_dt = fecha_hora
        else:
            try:
                start_dt = datetime.fromisoformat(str(fecha_hora))
            except Exception:
                start_dt = datetime.now()
        end_dt = start_dt + timedelta(minutes=duracion_minutos)
        return self.check_availability(start_dt.isoformat(), end_dt.isoformat())

    def sync_status(self) -> Dict[str, Any]:
        return self.get_status()


# Instancia por defecto y función de acceso
calendar_engine = CalendarEngine.get_instance()


def get_calendar_engine() -> CalendarEngine:
    return CalendarEngine.get_instance()


if __name__ == "__main__":
    print("=== TEST CALENDAR ENGINE ===")
    eng = CalendarEngine.get_instance()
    st = eng.get_status()
    print("Estado:", st)
    ev = eng.create_event(
        summary="Prueba de Agente",
        start=datetime.now().strftime("%Y-%m-%dT15:00:00"),
        description="Evento generado por CalendarEngine"
    )
    print("Evento creado:", ev)
    hoy = eng.get_today_events()
    print(f"Eventos hoy ({len(hoy)}):", [e['summary'] for e in hoy])
    eng.delete_event(ev["id"])
    print("Evento eliminado.")
