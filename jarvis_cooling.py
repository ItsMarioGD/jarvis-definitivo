"""
jarvis_cooling.py — Módulo de refrigeración para J.A.R.V.I.S.
Usa LibreHardwareMonitor para leer temperatura y controlar ventiladores.
Pone ventiladores al máx por 5 minutos para bajar la CPU.
"""
import os
import sys
import time
import subprocess
import threading
import tempfile

_DIR = os.path.dirname(os.path.abspath(__file__))
_LHM_DIR = os.path.join(_DIR, "_lhm")
_LHM_EXE = os.path.join(_LHM_DIR, "LibreHardwareMonitor.exe")
_WMI_NS = "root/LibreHardwareMonitor"
_COOLDOWN_SECONDS = 300  # 5 minutos

_lhm_process = None
_wmi_conn = None
_original_controls = {}
_cooldown_active = False
_cooldown_timer = None


def _ensure_wmi():
    """Instala módulo WMI si falta."""
    try:
        import wmi as _wmi
        return _wmi
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "WMI", "-q"],
                       capture_output=True)
        import wmi as _wmi
        return _wmi


def _start_lhm():
    """Eleva y lanza LibreHardwareMonitor en background."""
    global _lhm_process
    if _lhm_process and _lhm_process.poll() is None:
        return True  # ya corriendo

    if not os.path.exists(_LHM_EXE):
        raise FileNotFoundError(f"LHM no encontrado en {_LHM_EXE}")

    # Lanzar como admin con ventana oculta
    ps_cmd = (
        f'Start-Process -FilePath "{_LHM_EXE}" '
        f'-Verb RunAs -WindowStyle Hidden -PassThru'
    )
    try:
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # Esperar que el UAC acepte y LHM inicie
        time.sleep(4)

        # Verificar que LHM esté corriendo
        check = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq LibreHardwareMonitor.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if "LibreHardwareMonitor" in check.stdout:
            return True
        return False
    except Exception:
        return False


def _connect_wmi():
    """Conecta al namespace WMI de LibreHardwareMonitor."""
    global _wmi_conn
    wmi_mod = _ensure_wmi()
    try:
        _wmi_conn = wmi_mod.WMI(namespace=_WMI_NS)
        # Test: intentar leer sensores
        _wmi_conn.Sensor()
        return True
    except Exception:
        _wmi_conn = None
        return False


def _stop_lhm():
    """Mata el proceso LHM."""
    global _lhm_process
    subprocess.run(
        ["taskkill", "/F", "/IM", "LibreHardwareMonitor.exe"],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    _lhm_process = None


def get_temperatures():
    """Lee temperaturas de CPU y GPU. Devuelve dict {sensor: valor}."""
    if not _wmi_conn:
        return {}
    temps = {}
    try:
        sensors = _wmi_conn.Sensor()
        for s in sensors:
            if s.SensorType == "Temperature" and s.Value is not None:
                temps[s.Name] = {
                    "value": float(s.Value),
                    "parent": s.Parent,
                    "id": s.Identifier
                }
    except Exception:
        pass
    return temps


def get_fan_controls():
    """Lee controles de ventiladores. Devuelve dict {sensor: info}."""
    if not _wmi_conn:
        return {}
    controls = {}
    try:
        sensors = _wmi_conn.Sensor()
        for s in sensors:
            if s.SensorType == "Control" and s.Value is not None:
                controls[s.Name] = {
                    "value": float(s.Value),
                    "parent": s.Parent,
                    "id": s.Identifier,
                    "min": float(s.Min) if s.Min else 0,
                    "max": float(s.Max) if s.Max else 100
                }
    except Exception:
        pass
    return controls


def set_fan_speed(speed_percent):
    """Pone todos los ventiladores al porcentaje dado (0-100)."""
    if not _wmi_conn:
        return False
    global _original_controls
    try:
        sensors = _wmi_conn.Sensor()
        set_count = 0
        for s in sensors:
            if s.SensorType == "Control":
                # Guardar valor original
                if s.Name not in _original_controls:
                    _original_controls[s.Name] = float(s.Value) if s.Value else 0
                # Usar la propiedad Write para ajustar
                try:
                    s.Value = speed_percent
                    set_count += 1
                except Exception:
                    pass
        return set_count > 0
    except Exception:
        return False


def restore_fans():
    """Restaura ventiladores a valores originales."""
    global _original_controls
    if not _wmi_conn or not _original_controls:
        return False
    try:
        sensors = _wmi_conn.Sensor()
        for s in sensors:
            if s.SensorType == "Control" and s.Name in _original_controls:
                try:
                    s.Value = _original_controls[s.Name]
                except Exception:
                    pass
        _original_controls.clear()
        return True
    except Exception:
        return False


def _cooldown_loop(callback=None):
    """Loop de 5 min: mantiene ventiladores al máximo y monitorea."""
    global _cooldown_active
    _cooldown_active = True
    start = time.time()

    while _cooldown_active and (time.time() - start) < _COOLDOWN_SECONDS:
        # Re-leer y re-aplicar max风扇
        set_fan_speed(100)
        temps = get_temperatures()
        elapsed = int(time.time() - start)
        remaining = _COOLDOWN_SECONDS - elapsed

        if callback:
            cpu_temp = None
            for name, info in temps.items():
                if "cpu" in name.lower() or "package" in name.lower() or "core" in name.lower():
                    if cpu_temp is None or info["value"] > cpu_temp:
                        cpu_temp = info["value"]
            callback(cpu_temp, elapsed, remaining)

        time.sleep(3)

    # Restaurar al terminar
    restore_fans()
    _cooldown_active = False
    if callback:
        callback(None, _COOLDOWN_SECONDS, 0)


def start_cooling(callback=None):
    """Inicia el protocolo de refrigeración (5 min)."""
    global _cooldown_timer, _cooldown_active

    if _cooldown_active:
        return False, "Ya hay un ciclo de refrigeración activo."

    # 1. Lanzar LHM si no está corriendo
    wmi_mod = _ensure_wmi()
    try:
        test = wmi_mod.WMI(namespace=_WMI_NS)
        test.Sensor()
    except Exception:
        if not _start_lhm():
            return False, "No pude iniciar LibreHardwareMonitor. Se necesita permisos de admin."
        # Esperar a que WMI esté listo
        for _ in range(8):
            time.sleep(1)
            if _connect_wmi():
                break
        else:
            return False, "LHM iniciado pero WMI no responde. Intenta ejecutar como admin."

    # 2. Leer temperaturas iniciales
    temps = get_temperatures()
    controls = get_fan_controls()
    if not controls:
        return False, "No se detectaron controles de ventiladores. Tu placa puede no ser compatible."

    # 3. Poner ventiladores al máximo
    set_fan_speed(100)

    # 4. Iniciar timer de 5 minutos
    _cooldown_active = True
    _cooldown_timer = threading.Thread(target=_cooldown_loop, args=(callback,), daemon=True)
    _cooldown_timer.start()

    info = {
        "temps": temps,
        "controls": controls,
        "duration": _COOLDOWN_SECONDS
    }
    return True, info


def stop_cooling():
    """Detiene el ciclo de refrigeración y restaura ventiladores."""
    global _cooldown_active
    _cooldown_active = False
    restore_fans()
    return True


def get_status():
    """Estado actual del módulo de refrigeración."""
    global _cooldown_active
    temps = get_temperatures()
    controls = get_fan_controls()
    return {
        "active": _cooldown_active,
        "temps": temps,
        "controls": controls,
    }


def shutdown():
    """Apaga LHM y limpia."""
    global _cooldown_active
    _cooldown_active = False
    restore_fans()
    _stop_lhm()
