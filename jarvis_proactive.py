#!/usr/bin/env python3
"""
jarvis_proactive.py - Bucle Proactivo de Jarvis/Ultron
======================================================
Ejecuta comprobaciones periódicas y genera sugerencias/acciones autónomas
basadas en contexto temporal, estado del sistema, calendario, salud, etc.
"""
import os
import time
import threading
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class ProactivePriority(Enum):
    LOW = 1       # Info no urgente ("Hoy es martes, tu rutina habitual...")
    MEDIUM = 2    # Sugerencia útil ("Batería al 20%, ¿activo ahorro?")
    HIGH = 3      # Acción recomendada ("Reunión en 10 min, ¿preparo notas?")
    CRITICAL = 4  # Alerta inmediata ("Temperatura CPU 95°C, throttling inminente")


@dataclass
class ProactiveEvent:
    """Evento proactivo generado por el motor."""
    id: str
    priority: ProactivePriority
    category: str              # "calendar", "battery", "thermal", "network", "routine", "health", "security"
    title: str
    message: str
    suggested_action: str = "" # Acción sugerida: "notify", "ask_confirmation", "auto_execute"
    action_data: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    expires_at: float = 0      # 0 = no expira


class ProactiveEngine:
    """
    Motor proactivo que evalúa reglas cada N segundos y genera eventos.
    Se integra con JarvisCore via callback para TTS/notificaciones.
    """

    def __init__(self, core, log=print, interval: int = 60):
        self.core = core
        self.log = log
        self.interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._events: List[ProactiveEvent] = []
        self._lock = threading.Lock()
        self._rules: List[Callable[[], List[ProactiveEvent]]] = []

        # Registrar reglas built-in
        self._register_builtin_rules()

    def _register_builtin_rules(self):
        """Registra reglas por defecto."""
        self._rules.extend([
            self._check_calendar,
            self._check_battery,
            self._check_thermal,
            self._check_disk_space,
            self._check_network,
            self._check_routine,
            self._check_security,
            self._check_updates,
        ])

    def start(self):
        """Inicia el bucle proactivo en hilo daemon."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log(f"[PROACTIVE] Motor iniciado (intervalo {self.interval}s)")

    def stop(self):
        """Detiene el bucle."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        """Bucle principal: evalúa reglas cada intervalo."""
        while not self._stop.is_set():
            try:
                new_events = []
                for rule in self._rules:
                    try:
                        events = rule()
                        if events:
                            new_events.extend(events)
                    except Exception as e:
                        self.log(f"[PROACTIVE] Regla {rule.__name__} falló: {e}")

                if new_events:
                    with self._lock:
                        for ev in new_events:
                            # Evitar duplicados recientes (mismo category+title en últimos 5 min)
                            recent = [e for e in self._events
                                     if e.category == ev.category and e.title == ev.title
                                     and time.time() - e.timestamp < 300]
                            if not recent:
                                self._events.append(ev)
                                self._notify(ev)

                # Limpiar eventos antiguos (>24h)
                cutoff = time.time() - 86400
                with self._lock:
                    self._events = [e for e in self._events if e.timestamp > cutoff]

            except Exception as e:
                self.log(f"[PROACTIVE] Error en bucle: {e}")

            self._stop.wait(self.interval)

    def _notify(self, event: ProactiveEvent):
        """Notifica evento via callback del core (TTS, web, etc)."""
        try:
            # Callback TTS si está disponible
            if hasattr(self.core, 'tts_queue') and event.priority.value >= ProactivePriority.MEDIUM.value:
                msg = f"{event.title}. {event.message}"
                if event.suggested_action == "ask_confirmation":
                    msg += f" ¿Quieres que {event.action_data.get('confirm_text', 'lo haga')}?"
                self.core.tts_queue.put(msg)

            # Callback web socket si está disponible
            if hasattr(self.core, 'notify_web'):
                self.core.notify_web(event)

        except Exception as e:
            self.log(f"[PROACTIVE] Notify error: {e}")

    def get_events(self, unack_only: bool = False, category: str = None) -> List[ProactiveEvent]:
        with self._lock:
            events = list(self._events)
        if unack_only:
            events = [e for e in events if not e.acknowledged]
        if category:
            events = [e for e in events if e.category == category]
        return sorted(events, key=lambda e: (-e.priority.value, -e.timestamp))

    def acknowledge(self, event_id: str) -> bool:
        with self._lock:
            for e in self._events:
                if e.id == event_id:
                    e.acknowledged = True
                    return True
        return False

    def dismiss(self, event_id: str) -> bool:
        with self._lock:
            self._events = [e for e in self._events if e.id != event_id]
        return True

    # ─── REGLAS BUILT-IN ───

    def _check_calendar(self) -> List[ProactiveEvent]:
        """Próximas reuniones (requiere MCP Calendar)."""
        events = []
        try:
            # Intentar obtener eventos vía MCP client
            from mcp_client import MCPClient
            client = MCPClient({"calendar": "http://localhost:8002"})
            result = client.call("calendar", "cal_list_events", {
                "time_min": datetime.now().isoformat(),
                "time_max": (datetime.now() + timedelta(hours=2)).isoformat(),
                "max_results": 5
            })
            if isinstance(result, dict) and "result" in result:
                cal_events = result["result"]
                for ev in cal_events:
                    start = ev.get("start", "")
                    if start:
                        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        delta = dt - datetime.now(dt.tzinfo) if dt.tzinfo else dt - datetime.now()
                        mins = int(delta.total_seconds() / 60)
                        if 0 < mins <= 15:
                            events.append(ProactiveEvent(
                                id=f"cal_{ev['id'][:8]}",
                                priority=ProactivePriority.HIGH if mins <= 5 else ProactivePriority.MEDIUM,
                                category="calendar",
                                title=f"Reunión en {mins} min",
                                message=f"«{ev.get('summary', 'Sin título')}» empieza a las {dt.strftime('%H:%M')}",
                                suggested_action="notify",
                                action_data={"event_id": ev["id"]}
                            ))
        except Exception:
            pass
        return events

    def _check_battery(self) -> List[ProactiveEvent]:
        """Nivel de batería bajo."""
        events = []
        try:
            import psutil
            bat = psutil.sensors_battery()
            if bat and not bat.power_plugged:
                if bat.percent <= 10:
                    events.append(ProactiveEvent(
                        id=f"bat_{int(time.time())}",
                        priority=ProactivePriority.CRITICAL,
                        category="battery",
                        title="Batería crítica",
                        message=f"Solo {bat.percent}% restante. Conecta el cargador ya.",
                        suggested_action="notify"
                    ))
                elif bat.percent <= 20:
                    events.append(ProactiveEvent(
                        id=f"bat_{int(time.time())}",
                        priority=ProactivePriority.HIGH,
                        category="battery",
                        title="Batería baja",
                        message=f"{bat.percent}% restante. ¿Activo modo ahorro de energía?",
                        suggested_action="ask_confirmation",
                        action_data={"confirm_text": "active modo ahorro", "command": "powercfg /setactive SCHEME_MAX"}
                    ))
        except Exception:
            pass
        return events

    def _check_thermal(self) -> List[ProactiveEvent]:
        """Temperatura CPU alta."""
        events = []
        try:
            import subprocess
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty CurrentTemperature"],
                capture_output=True, text=True, timeout=5, creationflags=0x08000000
            )
            v = (r.stdout or "").strip()
            if v:
                temp_c = round((int(v) / 10) - 273.15, 1)
                if temp_c >= 90:
                    events.append(ProactiveEvent(
                        id=f"thermal_{int(time.time())}",
                        priority=ProactivePriority.CRITICAL,
                        category="thermal",
                        title="Sobrecalentamiento crítico",
                        message=f"CPU a {temp_c}°C. Riesgo de throttling/apagado.",
                        suggested_action="notify"
                    ))
                elif temp_c >= 80:
                    events.append(ProactiveEvent(
                        id=f"thermal_{int(time.time())}",
                        priority=ProactivePriority.HIGH,
                        category="thermal",
                        title="Temperatura alta",
                        message=f"CPU a {temp_c}°C. ¿Quiero que limpie temporales y baje prioridad de procesos pesados?",
                        suggested_action="ask_confirmation",
                        action_data={"confirm_text": "limpie y optimice", "command": "thermal_cleanup"}
                    ))
        except Exception:
            pass
        return events

    def _check_disk_space(self) -> List[ProactiveEvent]:
        """Espacio en disco bajo."""
        events = []
        try:
            import psutil
            disk = psutil.disk_usage("C:\\")
            free_gb = disk.free / 1073741824
            pct_free = (disk.free / disk.total) * 100
            if pct_free < 5 or free_gb < 2:
                events.append(ProactiveEvent(
                    id=f"disk_{int(time.time())}",
                    priority=ProactivePriority.HIGH,
                    category="storage",
                    title="Espacio en disco crítico",
                    message=f"Solo {free_gb:.1f} GB libres ({pct_free:.0f}%). ¿Ejecutar limpieza profunda?",
                    suggested_action="ask_confirmation",
                    action_data={"confirm_text": "limpie todo", "command": "deep_cleanup"}
                ))
            elif pct_free < 15:
                events.append(ProactiveEvent(
                    id=f"disk_{int(time.time())}",
                    priority=ProactivePriority.MEDIUM,
                    category="storage",
                    title="Espacio en disco bajo",
                    message=f"{free_gb:.1f} GB libres ({pct_free:.0f}%). Recomiendo limpieza de temporales.",
                    suggested_action="notify"
                ))
        except Exception:
            pass
        return events

    def _check_network(self) -> List[ProactiveEvent]:
        """Conectividad / latencia alta a servicios críticos."""
        events = []
        try:
            import requests
            # Test latencia a Ollama
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            latency = r.elapsed.total_seconds() * 1000
            if latency > 5000:
                events.append(ProactiveEvent(
                    id=f"net_{int(time.time())}",
                    priority=ProactivePriority.MEDIUM,
                    category="network",
                    title="Latencia alta al modelo local",
                    message=f"Ollama responde en {latency:.0f}ms. ¿Reinicio servicio?",
                    suggested_action="ask_confirmation",
                    action_data={"confirm_text": "reinicie Ollama", "command": "restart_ollama"}
                ))
        except Exception:
            pass
        return events

    def _check_routine(self) -> List[ProactiveEvent]:
        """Detección de rutinas basada en hora y historial."""
        events = []
        try:
            now = datetime.now()
            hour = now.hour
            weekday = now.weekday()  # 0=lunes

            # Rutinas matutinas (7-9h laborables)
            if weekday < 5 and 7 <= hour <= 9:
                events.append(ProactiveEvent(
                    id=f"routine_morning_{now.date()}",
                    priority=ProactivePriority.LOW,
                    category="routine",
                    title="Buenos días, señor",
                    message="Su rutina matutina habitual: revisar correo, calendario y noticias. ¿Quiere que empiece?",
                    suggested_action="ask_confirmation",
                    action_data={"confirm_text": "inicie la rutina", "command": "morning_routine"}
                ))

            # Rutina fin de jornada (18-20h)
            if weekday < 5 and 18 <= hour <= 20:
                events.append(ProactiveEvent(
                    id=f"routine_evening_{now.date()}",
                    priority=ProactivePriority.LOW,
                    category="routine",
                    title="Fin de jornada",
                    message="Hora habitual de cerrar tareas. ¿Quiere resumen del día y preparar mañana?",
                    suggested_action="ask_confirmation",
                    action_data={"confirm_text": "haga el resumen", "command": "evening_wrapup"}
                ))

        except Exception:
            pass
        return events

    def _check_security(self) -> List[ProactiveEvent]:
        """Escaneo de seguridad (conexiones sospechosas, etc)."""
        events = []
        try:
            # Solo si DigitalGuardian está disponible
            guardian = getattr(self.core, 'guardia_digital', None)
            if guardian:
                texto, sospechosas = guardian.escanear()
                if sospechosas:
                    events.append(ProactiveEvent(
                        id=f"sec_{int(time.time())}",
                        priority=ProactivePriority.HIGH,
                        category="security",
                        title="Intrusos digitales detectados",
                        message=f"{len(sospechosas)} IP(s) sospechosas: {', '.join(sospechosas[:3])}. ¿Bloqueo automático?",
                        suggested_action="ask_confirmation",
                        action_data={"confirm_text": "bloquee todo", "command": "block_suspicious_ips"}
                    ))
        except Exception:
            pass
        return events

    def _check_updates(self) -> List[ProactiveEvent]:
        """Actualizaciones pendientes (Windows, winget, etc)."""
        events = []
        try:
            import subprocess
            r = subprocess.run(["winget", "upgrade", "--source", "winget", "--accept-source-agreements"],
                              capture_output=True, text=True, timeout=30, creationflags=0x08000000)
            if r.returncode == 0 and "upgrades available" in r.stdout.lower():
                # Parsear número de actualizaciones
                import re
                m = re.search(r"(\d+)\s+upgrade", r.stdout, re.IGNORECASE)
                count = int(m.group(1)) if m else 1
                if count > 0:
                    events.append(ProactiveEvent(
                        id=f"updates_{int(time.time())}",
                        priority=ProactivePriority.LOW,
                        category="maintenance",
                        title=f"{count} actualizaciones disponibles",
                        message=f"Hay {count} paquete(s) con actualizaciones en winget. ¿Instalo automáticamente?",
                        suggested_action="ask_confirmation",
                        action_data={"confirm_text": "instale todo", "command": "winget_upgrade_all"}
                    ))
        except Exception:
            pass
        return events


# Instancia global lazy
_proactive_engine: Optional[ProactiveEngine] = None


def get_proactive_engine(core=None, log=print) -> ProactiveEngine:
    global _proactive_engine
    if _proactive_engine is None and core:
        _proactive_engine = ProactiveEngine(core, log=log)
    return _proactive_engine


def start_proactive(core, log=print, interval: int = 60) -> ProactiveEngine:
    """Inicia motor proactivo global."""
    engine = get_proactive_engine(core, log)
    engine.start()
    return engine


if __name__ == "__main__":
    # Test standalone
    class MockCore:
        def __init__(self):
            self.tts_queue = None
            def mock_put(x): print(f"[TTS] {x}")
            self.tts_queue = type('obj', (object,), {'put': mock_put})()

    core = MockCore()
    engine = ProactiveEngine(core, interval=10)
    engine.start()

    try:
        while True:
            time.sleep(30)
            evs = engine.get_events()
            print(f"Eventos activos: {len(evs)}")
            for e in evs:
                print(f"  [{e.priority.name}] {e.category}: {e.title} - {e.message}")
    except KeyboardInterrupt:
        engine.stop()