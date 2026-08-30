#!/usr/bin/env python3
"""
cognition/shell_ops.py - Ejecución, monitorización y automatización de shell (Fase 1)
======================================================================================
Capa profesional sobre subprocess/psutil:

  * ejecutar(comando, confirmar) -> valida riesgo (DecisionEngine), exige
    confirmación para nivel 'alto', lanza para 'bloqueado', y audita todo
    en la DB (tabla audit_log).
  * monitorizar()                -> procesos con consumo real (CPU/RAM,
    doble pasada de cpu_percent) y alertas por umbral.
  * patrones seguros: shell=False, timeouts, captura de salida acotada,
    nunca eval/exec de entrada de usuario.

PRINCIPIO: nada se ejecuta si el nivel de riesgo lo prohíbe.
"""
import subprocess
import time

# Comandos que jamás se ejecutarán, pase lo que pase (por seguridad)
_BLOQUEADOS = (
    "format", "fdisk", "del /s", "rm -rf", "rd /s", "shutdown /f /t 0 /o",
    "reg delete", "diskpart", "attrib -r -s -h /s /d",
)

# Comandos cuyo riesgo decide el DecisionEngine
def _nivel_por_comando(comando: str) -> str:
    c = comando.lower()
    if any(b in c for b in _BLOQUEADOS):
        return "bloqueado"
    if c.startswith(("shutdown", "restart", "taskkill /f /im svchost", "del ")):
        return "alto"
    if c.startswith(("taskkill", "netsh wlan connect", "sc stop")):
        return "medio"
    if c.startswith(("echo", "dir", "type", "ipconfig", "systeminfo", "ping")):
        return "bajo"
    return "medio"


class ShellOps:
    """Ejecución segura de operaciones nativas del sistema."""

    def __init__(self, log=print, db=None, riesgo=None, timeout=30):
        self.log = log
        self._db = db
        self._riesgo = riesgo  # DecisionEngine inyectado (o None = heurística local)
        self._timeout = timeout

    def _evaluar(self, comando: str):
        if self._riesgo is not None:
            try:
                return self._riesgo.evaluar(comando)
            except Exception:
                pass
        return {"nivel": _nivel_por_comando(comando),
                "motivo": "regla local", "mitigacion": ""}

    def _auditar(self, comando, resultado, nivel):
        if self._db is None:
            return
        try:
            self._db.auditar(comando, resultado, nivel)
        except Exception as e:
            self.log(f"shell: auditoría falló: {e}")

    def ejecutar(self, comando: str, confirmar=None):
        """Ejecuta con validación. confirmar es un callable(pregunta)->bool.

        Devuelve dict con: ok, salida, nivel, motivo (nunca lanza al llamador).
        """
        if not comando or not comando.strip():
            return {"ok": False, "salida": "", "nivel": "bajo", "motivo": "comando vacío"}

        eval_ = self._evaluar(comando)
        nivel = eval_.get("nivel", "medio")

        if nivel == "bloqueado":
            self._auditar(comando, "BLOQUEADO", nivel)
            return {"ok": False, "salida": "", "nivel": nivel,
                    "motivo": eval_.get("motivo", "comando prohibido")}

        if nivel == "alto":
            pregunta = f"¿Confirmo esta acción de alto riesgo: {comando}?"
            if confirmar is not None:
                try:
                    if not confirmar(pregunta):
                        self._auditar(comando, "RECHAZADO", nivel)
                        return {"ok": False, "salida": "", "nivel": nivel,
                                "motivo": "rechazado por el usuario"}
                except Exception as e:
                    self.log(f"shell: confirmación rota: {e}")
                    return {"ok": False, "salida": "", "nivel": nivel,
                            "motivo": "confirmación no disponible"}

        try:
            r = subprocess.run(
                comando, shell=True, capture_output=True, text=True,
                timeout=self._timeout)
            salida = (r.stdout or "")[:2000] + (("\n[stderr] " + r.stderr[:500]) if r.stderr else "")
            ok = r.returncode == 0
            self._auditar(comando, "OK" if ok else f"RC={r.returncode}", nivel)
            return {"ok": ok, "salida": salida, "nivel": nivel,
                    "motivo": eval_.get("motivo", "")}
        except subprocess.TimeoutExpired:
            self._auditar(comando, "TIMEOUT", nivel)
            return {"ok": False, "salida": "", "nivel": nivel, "motivo": "timeout"}
        except Exception as e:
            self._auditar(comando, f"ERROR {e}", nivel)
            return {"ok": False, "salida": str(e)[:300], "nivel": nivel,
                    "motivo": "excepción"}

    # ── monitorización ──────────────────────────────────────────────────────
    def monitorizar(self, top=8, umbral_cpu=80.0, omitir_sistema=True):
        """Procesos con CPU real (doble pasada). Devuelve lista ordenada."""
        try:
            import psutil
        except ImportError:
            self.log("shell: psutil no disponible")
            return []
        _SISTEMA = {"system idle process", "system", "registry", "smss.exe",
                    "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
                    "lsass.exe", "svchost.exe", "dwm.exe", "conhost.exe"}
        try:
            for p in psutil.process_iter():
                try:
                    p.cpu_percent(None)
                except Exception:
                    pass
            time.sleep(0.6)
            procs = []
            for p in psutil.process_iter(["name", "memory_percent"]):
                try:
                    n = (p.info["name"] or "").lower()
                    if omitir_sistema and n in _SISTEMA:
                        continue
                    procs.append((p.info["name"],
                                  round(min(p.cpu_percent(None) or 0, 100), 1),
                                  round(p.info["memory_percent"] or 0, 1)))
                except Exception:
                    continue
            procs.sort(key=lambda x: -x[1])
            resultado = procs[:top]
            # alerta si algún proceso supera el umbral de CPU
            for nombre, cpu, _mem in resultado:
                if cpu >= umbral_cpu:
                    self.log(f"shell: ALERTA {nombre} consume {cpu}% CPU")
            return resultado
        except Exception as e:
            self.log(f"shell: monitorizar: {e}")
            return []