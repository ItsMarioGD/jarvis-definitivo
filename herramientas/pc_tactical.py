#!/usr/bin/env python3
"""
herramientas/pc_tactical.py — Arsenal Táctico del Sistema para JARVIS y ULTRON
=============================================================================
Funciones avanzadas de supervisión y control del host:
- Terminación forzosa de procesos por nombre o PID.
- Purga masiva y optimización de memoria RAM (EmptyWorkingSet).
- Bloqueo instantáneo de la estación de trabajo (LockWorkStation).
- Capturas de pantalla de auditoría de seguridad.
- Radar de conexiones de red y puertos activos.
- Bloqueo de IPs sospechosas vía Windows Firewall.
- Protocolo de enlace y delegación inter-agentes (Jarvis <-> Ultron).
"""

import os
import sys
import gc
import ctypes
import time
import subprocess
import requests
from typing import Dict, Any, List, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def list_top_processes(limit: int = 15, sort_by: str = "cpu") -> List[Dict[str, Any]]:
    """Lista los procesos principales ordenados por uso de CPU o memoria."""
    if not PSUTIL_AVAILABLE:
        return []
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info']):
        try:
            info = p.info
            mem_mb = round((info.get('memory_info').rss if info.get('memory_info') else 0) / (1024 * 1024), 1)
            procs.append({
                "pid": info.get('pid'),
                "name": info.get('name') or "desconocido",
                "cpu": round(info.get('cpu_percent') or 0.0, 1),
                "mem_pct": round(info.get('memory_percent') or 0.0, 1),
                "mem_mb": mem_mb,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if sort_by == "mem":
        procs.sort(key=lambda x: x["mem_mb"], reverse=True)
    else:
        procs.sort(key=lambda x: x["cpu"], reverse=True)

    return procs[:limit]


def kill_process(target: Any) -> Dict[str, Any]:
    """
    Termina un proceso forzosamente por PID o por nombre (ej. 'chrome', 'notepad.exe').
    """
    if not target:
        return {"ok": False, "error": "Objetivo no especificado"}

    target_str = str(target).strip()
    killed = []
    errors = []

    # Caso 1: PID numérico
    if target_str.isdigit():
        pid = int(target_str)
        try:
            if PSUTIL_AVAILABLE:
                p = psutil.Process(pid)
                name = p.name()
                p.kill()
                killed.append(f"{name} (PID {pid})")
            else:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=True)
                killed.append(f"PID {pid}")
        except Exception as e:
            errors.append(f"PID {pid}: {e}")
        return {"ok": len(killed) > 0, "killed": killed, "errors": errors}

    # Caso 2: Nombre de proceso
    name_query = target_str.lower()
    if not name_query.endswith(".exe") and "." not in name_query:
        name_query_exe = name_query + ".exe"
    else:
        name_query_exe = name_query

    if PSUTIL_AVAILABLE:
        for p in psutil.process_iter(['pid', 'name']):
            try:
                pname = (p.info.get('name') or "").lower()
                if pname == name_query or pname == name_query_exe or name_query in pname:
                    pid = p.info.get('pid')
                    p.kill()
                    killed.append(f"{pname} (PID {pid})")
            except Exception as e:
                errors.append(str(e))
    else:
        try:
            r = subprocess.run(["taskkill", "/F", "/IM", name_query_exe], capture_output=True, text=True)
            if r.returncode == 0:
                killed.append(name_query_exe)
            else:
                errors.append(r.stderr or "No encontrado")
        except Exception as e:
            errors.append(str(e))

    return {
        "ok": len(killed) > 0,
        "killed": killed,
        "count": len(killed),
        "errors": errors
    }


def clean_ram() -> Dict[str, Any]:
    """
    Ejecuta una purga de memoria RAM:
    1. Garbage collector de Python.
    2. Vaciado del Working Set de todos los procesos accesibles en Windows.
    """
    gc.collect()
    mem_before = 0
    mem_after = 0
    pct_before = 0
    pct_after = 0

    if PSUTIL_AVAILABLE:
        vm0 = psutil.virtual_memory()
        mem_before = vm0.used
        pct_before = vm0.percent

    # Windows API: EmptyWorkingSet
    purged_count = 0
    try:
        psapi = ctypes.windll.psapi
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_SET_QUOTA = 0x0100

        if PSUTIL_AVAILABLE:
            for p in psutil.process_iter(['pid']):
                pid = p.info.get('pid')
                if pid and pid > 4:
                    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid)
                    if h:
                        try:
                            if psapi.EmptyWorkingSet(h):
                                purged_count += 1
                        finally:
                            kernel32.CloseHandle(h)
    except Exception as e:
        print(f"[PC-TACTICAL] Error en EmptyWorkingSet: {e}")

    if PSUTIL_AVAILABLE:
        time.sleep(0.3)
        vm1 = psutil.virtual_memory()
        mem_after = vm1.used
        pct_after = vm1.percent

    freed_mb = round(max(0, mem_before - mem_after) / (1024 * 1024), 1)

    return {
        "ok": True,
        "freed_mb": freed_mb,
        "ram_before_pct": pct_before,
        "ram_after_pct": pct_after,
        "processes_purged": purged_count,
        "message": f"Purga completada. {freed_mb} MB liberados. RAM reducida de {pct_before}% a {pct_after}%."
    }


def lockdown_station() -> Dict[str, Any]:
    """Bloquea inmediatamente la sesión de Windows (LockWorkStation)."""
    try:
        res = ctypes.windll.user32.LockWorkStation()
        return {
            "ok": bool(res),
            "message": "Estación de trabajo bloqueada con éxito." if res else "Llamada a LockWorkStation falló."
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def take_screenshot(prefix: str = "tactical") -> Dict[str, Any]:
    """Captura la pantalla completa y la guarda en la carpeta de capturas de JARVIS/ULTRON."""
    home = os.path.expanduser("~")
    caps_dir = os.path.join(home, "Descargas", "JARVIS", "Capturas")
    os.makedirs(caps_dir, exist_ok=True)
    filename = f"{prefix}_{int(time.time())}.png"
    filepath = os.path.join(caps_dir, filename)

    # Intento 1: PIL / ImageGrab
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(filepath)
        return {"ok": True, "path": filepath, "filename": filename}
    except Exception:
        pass

    # Intento 2: PowerShell
    try:
        cmd = f"""
        Add-Type -AssemblyName System.Windows.Forms,System.Drawing;
        $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;
        $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height;
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap);
        $graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size);
        $bitmap.Save('{filepath}', [System.Drawing.Imaging.ImageFormat]::Png);
        $graphics.Dispose();
        $bitmap.Dispose();
        """
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True)
        if r.returncode == 0 and os.path.exists(filepath):
            return {"ok": True, "path": filepath, "filename": filename}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "No se pudo generar la captura"}


def scan_network_connections(limit: int = 25) -> List[Dict[str, Any]]:
    """Escanea las conexiones de red activas e identifica conexiones remotas."""
    if not PSUTIL_AVAILABLE:
        return []
    conns = []
    suspicious_ports = {4444, 1337, 31337, 6667, 5555, 8888, 9999}
    try:
        for c in psutil.net_connections(kind='inet'):
            try:
                laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                r_ip = c.raddr.ip if c.raddr else ""
                r_port = c.raddr.port if c.raddr else 0
                is_local = (r_ip.startswith("127.") or r_ip.startswith("192.168.")
                            or r_ip.startswith("10.") or r_ip.startswith("172.16.")
                            or not r_ip)
                is_suspicious = bool((not is_local and r_ip) or (r_port in suspicious_ports))
                pname = ""
                if c.pid:
                    try:
                        pname = psutil.Process(c.pid).name()
                    except Exception:
                        pname = "?"

                conns.append({
                    "fd": c.fd,
                    "family": "IPv4" if c.family == 2 else "IPv6",
                    "type": "TCP" if c.type == 1 else "UDP",
                    "local": laddr,
                    "remote": raddr,
                    "remote_ip": r_ip,
                    "remote_port": r_port,
                    "status": c.status,
                    "pid": c.pid,
                    "process": pname,
                    "is_suspicious": is_suspicious
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[PC-TACTICAL] Error en escaneo de red: {e}")

    # Priorizar conexiones remotas y sospechosas
    conns.sort(key=lambda x: (x["is_suspicious"], bool(x["remote"])), reverse=True)
    return conns[:limit]


def block_ip_firewall(ip: str) -> Dict[str, Any]:
    """Añade una regla de bloqueo entrante/saliente en Windows Firewall para una IP."""
    clean_ip = ip.strip()
    if not clean_ip or len(clean_ip) > 45:
        return {"ok": False, "error": "IP inválida"}
    rule_name = f"ULTRON_BLOCK_{clean_ip.replace(':', '_')}"
    try:
        cmd = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name}",
            "dir=in",
            "action=block",
            f"remoteip={clean_ip}"
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return {"ok": True, "message": f"IP {clean_ip} bloqueada en Windows Firewall.", "rule": rule_name}
        return {"ok": False, "error": r.stderr or r.stdout}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── PROTOCOLO INTER-AGENTES ───

def get_peer_status(agent: str = "jarvis") -> Dict[str, Any]:
    """Consulta el estado del agente par (Jarvis en puerto 5000 o Ultron en puerto 8766)."""
    target = agent.lower()
    port = 5000 if target == "jarvis" else 8766
    url = f"http://127.0.0.1:{port}"
    try:
        r = requests.get(f"{url}/health", timeout=1.5)
        if r.status_code == 200:
            data = r.json()
            return {
                "online": True,
                "agent": data.get("agente") or target.upper(),
                "model": data.get("llm") or data.get("model") or "desconocido",
                "port": port,
                "url": url,
                "details": data
            }
    except Exception:
        pass
    return {
        "online": False,
        "agent": target.upper(),
        "port": port,
        "url": url,
        "error": "No responde o está apagado"
    }


def delegate_to_peer(target_agent: str, message: str) -> Dict[str, Any]:
    """Envía un comando o mensaje al otro agente para ejecución remota."""
    target = target_agent.lower()
    port = 5000 if target == "jarvis" else 8766
    url = f"http://127.0.0.1:{port}/chat"
    try:
        r = requests.post(url, json={"text": message, "speak_server": False}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return {
                "ok": True,
                "target": target.upper(),
                "reply": data.get("reply") or "(sin respuesta)"
            }
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:120]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
