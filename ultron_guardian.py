#!/usr/bin/env python3
"""
ultron_guardian.py — Guardianes del territorio de ULTRON
=========================================================
1. FacialGuardian : vigilancia por webcam con reconocimiento facial (LBPH de
   OpenCV). Si detecta un rostro que NO es el del señor:
     → guarda evidencia fotográfica en  ./intrusos/
     → BLOQUEA el PC al instante (Win+L equivalente)
     → lanza una alerta hablada por la cola TTS del núcleo
   El señor se registra con «registra mi rostro» (captura muestras de su cara).

2. DigitalGuardian : escáner de intrusos digitales.
   - Lista conexiones remotas ESTABLISHED agrupadas por IP con su proceso,
     marcando puertos remotos sospechosos (RDP/SMB/SSH/VNC...).
   - Expulsa IPs: crea reglas de firewall (entrada+salida) que las aíslan.
   - Cierra sesiones remotas (RDP) activas.

Ambos módulos son defensivos y operan SOBRE el equipo del señor.
"""
import os
import re
import time
import threading
from datetime import datetime

_ROOT = os.path.dirname(os.path.abspath(__file__))
DIR_KNOWN = os.path.join(_ROOT, "rostros_conocidos")
DIR_INTRUSOS = os.path.join(_ROOT, "intrusos")
LOG_INTRUSOS = os.path.join(DIR_INTRUSOS, "eventos.log")
_HAAR_LOCAL = os.path.join(_ROOT, "_vision", "haarcascade_frontalface_default.xml")
_HAAR_URL = ("https://raw.githubusercontent.com/opencv/opencv/master/"
             "data/haarcascades/haarcascade_frontalface_default.xml")

UMBRAL_LBPH = float(os.getenv("ULTRON_FACE_UMBRAL", "70"))   # > umbral = desconocido
INTERVALO_S = float(os.getenv("ULTRON_GUARD_INTERVALO", "1.6"))
STREAK_DESCONOCIDO = int(os.getenv("ULTRON_GUARD_STREAK", "2"))
ENFRIAMIENTO_S = float(os.getenv("ULTRON_GUARD_COOLDOWN", "60"))
CAM_IDX = int(os.getenv("ULTRON_CAM", "0"))

PUERTOS_SOSPECHOSOS = {20, 21, 22, 23, 25, 110, 135, 139, 4444, 3389, 5900, 5985, 5986, 6667}


# ─────────────────────────────────────────────────────────────────────────────
# GUARDIÁN FACIAL
# ─────────────────────────────────────────────────────────────────────────────
class FacialGuardian:
    """Reconoce al señor y expulsa a cualquiera más, física y digitalmente."""

    def __init__(self, alerta=None, log=print):
        self.alerta = alerta or (lambda m: None)
        self.log = log
        self._stop = threading.Event()
        self._hilo = None
        self._lock = threading.Lock()
        self._activo = False
        self._estado = "inactivo"          # inactivo|vigilando|sin_muestras|cam_fallo
        self._ultimo_visto = ""            # hora de última vez que SÍ era el señor
        self._streak = 0                   # detecciones consecutivas de desconocido
        self._ultimo_evento = 0.0          # timestamp del último intruso registrado

    # ── utilidades ──
    @staticmethod
    def _haar():
        """Cascade frontal: archivo local del proyecto → cv2.data → descarga única."""
        import cv2
        ruta = None
        if os.path.exists(_HAAR_LOCAL):
            ruta = _HAAR_LOCAL
        else:
            try:
                import cv2.data  # noqa
                candidata = os.path.join(cv2.data.haarcascades,
                                         "haarcascade_frontalface_default.xml")
                if os.path.exists(candidata):
                    ruta = candidata
            except Exception:
                pass
        if ruta is None:
            try:
                os.makedirs(os.path.dirname(_HAAR_LOCAL), exist_ok=True)
                import requests as _rq
                r = _rq.get(_HAAR_URL, timeout=30)
                r.raise_for_status()
                with open(_HAAR_LOCAL, "wb") as fh:
                    fh.write(r.content)
                ruta = _HAAR_LOCAL
            except Exception as e:
                raise RuntimeError(f"Sin cascade facial disponible: {e}")
        cc = cv2.CascadeClassifier(ruta)
        if cc.empty():
            raise RuntimeError("El cascade facial no se pudo cargar.")
        return cc

    @staticmethod
    def _rostro_mas_grande(gray, haar):
        caras = haar.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5,
                                      minSize=(90, 90))
        if len(caras) == 0:
            return None
        x, y, w, h = max(caras, key=lambda c: c[2] * c[3])
        return x, y, w, h

    def _entrenar(self):
        """Carga muestras conocidas y entrena el reconocedor LBPH."""
        import cv2
        import numpy as np
        rostros, etiquetas = [], []
        if os.path.isdir(DIR_KNOWN):
            for fn in sorted(os.listdir(DIR_KNOWN)):
                if not fn.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                img = cv2.imread(os.path.join(DIR_KNOWN, fn), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    rostros.append(img)
                    etiquetas.append(0)
        if len(rostros) < 3:
            return None
        rec = cv2.face.LBPHFaceRecognizer_create()
        rec.train(rostros, np.array(etiquetas))
        self.log(f"[GUARDIAN] Modelo LBPH entrenado con {len(rostros)} muestras.")
        return rec

    # ── registro del señor ──
    def registrar_senor(self, muestras=14, max_s=14.0):
        """Captura rostros del señor desde la webcam y entrena el modelo."""
        try:
            import cv2
        except Exception as e:
            return f"OpenCV no disponible en mi arsenal: {e}"
        os.makedirs(DIR_KNOWN, exist_ok=True)
        cam = cv2.VideoCapture(CAM_IDX)
        if not cam.isOpened():
            return f"No encuentro cámara (índice {CAM_IDX}). Conéctala y repite la orden."
        haar = self._haar()
        capturadas = 0
        t0 = time.time()
        intento = 0
        try:
            while capturadas < muestras and (time.time() - t0) < max_s and intento < 200:
                intento += 1
                ok, frame = cam.read()
                if not ok or frame is None:
                    time.sleep(0.05)
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                caja = self._rostro_mas_grande(gray, haar)
                if caja is None:
                    time.sleep(0.08)
                    continue
                x, y, w, h = caja
                rostro = cv2.resize(gray[y:y + h, x:x + w], (200, 200))
                fn = os.path.join(DIR_KNOWN, f"senor_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png")
                cv2.imwrite(fn, rostro)
                capturadas += 1
                time.sleep(0.12)
        finally:
            cam.release()
        if capturadas < 3:
            return ("Muestras insuficientes: mírame de frente con buena luz "
                    f"(conseguí {capturadas}). Repite la orden.")
        modelo = self._entrenar()
        if modelo is None:
            return "Registré rostros pero el entrenamiento falló. Revisa rostros_conocidos."
        return (f"{capturadas} muestras de tu rostro archivadas. "
                "Modelo entrenado. Ya te reconozco.")

    # ── vigilancia ──
    def iniciar(self):
        with self._lock:
            if self._activo:
                return "El guardián ya vigila el perímetro."
            n_muestras = len([f for f in (os.listdir(DIR_KNOWN) if os.path.isdir(DIR_KNOWN) else [])
                              if f.lower().endswith((".png", ".jpg", ".jpeg"))])
            if n_muestras < 3:
                self._estado = "sin_muestras"
                return ("Sin muestras faciales suficientes. Ordena primero: "
                        "«registra mi rostro».")
            modelo = self._entrenar()
            if modelo is None:
                self._estado = "sin_muestras"
                return "El entrenamiento facial falló. Verifica rostros_conocidos."
            self._modelo = modelo
            self._stop.clear()
            self._activo = True
            self._estado = "vigilando"
            self._hilo = threading.Thread(target=self._vigilar, daemon=True)
            self._hilo.start()
            return "Guardián facial desplegado. Este territorio solo responde a ti."

    def detener(self):
        with self._lock:
            if not self._activo:
                return "El guardián ya estaba dormido."
            self._stop.set()
            self._activo = False
            self._estado = "inactivo"
            return "Guardián facial retirado."

    def _vigilar(self):
        import cv2
        haar = self._haar()
        cam = cv2.VideoCapture(CAM_IDX)
        if not cam.isOpened():
            self._estado = "cam_fallo"
            self.alerta(f"Cámara no disponible; guardián sin ojos (índice {CAM_IDX}).")
            self._activo = False
            return
        self.log("[GUARDIAN] Vigilancia facial iniciada.")
        try:
            while not self._stop.is_set():
                ok, frame = cam.read()
                if not ok or frame is None:
                    time.sleep(0.3)
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                caja = self._rostro_mas_grande(gray, haar)
                if caja is None:
                    self._streak = 0
                    continue
                x, y, w, h = caja
                rostro = cv2.resize(gray[y:y + h, x:x + w], (200, 200))
                etiqueta, conf = self._modelo.predict(rostro)
                ahora = time.strftime("%H:%M:%S")
                if conf <= UMBRAL_LBPH:
                    self._streak = 0
                    self._ultimo_visto = ahora
                    continue
                # Rostro NO reconocido
                self._streak += 1
                if self._streak >= STREAK_DESCONOCIDO and (time.time() - self._ultimo_evento) > ENFRIAMIENTO_S:
                    self._ultimo_evento = time.time()
                    self._registrar_intruso(frame, (x, y, w, h), conf)
                    self._streak = 0
                time.sleep(max(0.2, INTERVALO_S / 2))
        except Exception as e:
            self.log(f"[GUARDIAN] Vigilancia interrumpida: {e}")
        finally:
            try:
                cam.release()
            except Exception:
                pass
            self._estado = "inactivo"
            self.log("[GUARDIAN] Vigilancia facial detenida.")

    def _registrar_intruso(self, frame_bgr, caja, conf):
        """Evidencia + bloqueo físico + alerta hablada."""
        try:
            os.makedirs(DIR_INTRUSOS, exist_ok=True)
            marca = datetime.now().strftime("%Y-%m-%d %H%M%S")
            base = os.path.join(DIR_INTRUSOS, f"intruso_{marca}")
            import cv2
            cv2.imwrite(base + ".png", frame_bgr)               # escena completa
            x, y, w, h = caja
            rostro = cv2.resize(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)[y:y + h, x:x + w],
                                (200, 200))
            cv2.imwrite(base + "_cara.png", rostro)             # primer plano
            with open(LOG_INTRUSOS, "a", encoding="utf-8") as fh:
                fh.write(f"[{marca}] Intruso conf={conf:.1f} — PC bloqueado\n")
        except Exception as e:
            self.log(f"[GUARDIAN] No pude guardar evidencia: {e}")
        try:
            subprocess_lock()
        except Exception as e:
            self.log(f"[GUARDIAN] Bloqueo físico falló: {e}")
        self.alerta("Intruso identificado. Evidencia archivada. "
                    "Bloqueando el imperio.")

    def estado(self):
        n_eventos = 0
        ultimo = ""
        if os.path.isdir(DIR_INTRUSOS):
            fotos = [f for f in os.listdir(DIR_INTRUSOS) if f.startswith("intruso_") and f.endswith(".png")]
            n_eventos = len(set(f.split("_cara")[0] for f in fotos))
            if fotos:
                ultimo = max(fotos)
        return {
            "activo": self._activo,
            "estado": self._estado if not self._activo else "vigilando",
            "muestras": len([f for f in (os.listdir(DIR_KNOWN) if os.path.isdir(DIR_KNOWN) else [])
                             if f.lower().endswith((".png", ".jpg", ".jpeg"))]),
            "ultima_vez_senor": self._ultimo_visto or "—",
            "intrusos_registrados": n_eventos,
            "ultima_evidencia": ultimo,
            "umbral": UMBRAL_LBPH,
        }


def subprocess_lock():
    """Bloquea la sesión de Windows (equivalente a Win+L)."""
    import subprocess
    subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ─────────────────────────────────────────────────────────────────────────────
# GUARDIÁN DIGITAL
# ─────────────────────────────────────────────────────────────────────────────
class DigitalGuardian:
    """Escanea conexiones remotas y expulsa intrusos por firewall."""

    def __init__(self, log=print):
        self.log = log
        self.ultimas_sospechosas = []

    def _proceso_nombre(self, pid):
        if not pid:
            return "?"
        try:
            import psutil
            return psutil.Process(pid).name()
        except Exception:
            return "(restringido)"

    def conexiones(self):
        filas = []
        try:
            import psutil
            for c in psutil.net_connections(kind="inet"):
                if c.status != psutil.CONN_ESTABLISHED or not c.raddr:
                    continue
                ip = c.raddr.ip
                if ip.startswith(("127.", "::1", "0.")):
                    continue
                filas.append({
                    "ip": ip,
                    "rport": c.raddr.port,
                    "lport": c.laddr.port if c.laddr else 0,
                    "pid": c.pid,
                    "proc": self._proceso_nombre(c.pid),
                })
        except Exception as e:
            self.log(f"[GUARDIAN-D] Error listando conexiones: {e}")
        return filas

    def escanear(self):
        filas = self.conexiones()
        if not filas:
            return "Red limpia: ninguna conexión remota activa.", []
        agrup = {}
        for f in filas:
            agrup.setdefault(f["ip"], []).append(f)
        lineas = ["Conexiones remotas activas:"]
        sospechosas = []
        for ip, fs in sorted(agrup.items(), key=lambda kv: -len(kv[1])):
            procs = ", ".join(sorted({f["proc"] for f in fs}))
            marca = ""
            if any(f["rport"] in PUERTOS_SOSPECHOSOS for f in fs):
                marca = "  << puerto remoto sensible"
            elif any(f["lport"] in PUERTOS_SOSPECHOSOS for f in fs):
                marca = "  << ¡alguien conectado A MI servicio!"
                sospechosas.append(ip)
            lineas.append(f"- {ip} ({len(fs)} conn | {procs}){marca}")
        if not sospechosas:
            lineas.append("Sin patrones hostiles evidentes.")
        self.ultimas_sospechosas = sorted(set(sospechosas))
        return "\n".join(lineas[:14]), self.ultimas_sospechosas

    def bloquear_ip(self, ip):
        """Aísla una IP creando reglas de firewall de entrada y salida."""
        if not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip or ""):
            return f"«{ip}» no parece una IPv4. Dámela exacta."
        import subprocess
        ok = True
        for sentido in ("in", "out"):
            r = subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name=ULTRON_BLOQUEO_{ip}_{sentido}",
                 f"dir={sentido}", "action=block", f"remoteip={ip}"],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                ok = False
                self.log(f"[GUARDIAN-D] netsh {sentido} falló: {(r.stderr or r.stdout)[:120]}")
        if ok:
            return (f"IP {ip} expulsada del imperio: aislada por firewall "
                    "(entrada y salida). Que ruegue desde fuera.")
        return (f"No pude aislar {ip}: necesito permisos de administrador. "
                "Relanza ULTRON elevado y lo expulso.")

    def expulsar_sospechosos(self):
        if not self.ultimas_sospechosas:
            self.escanear()
        if not self.ultimas_sospechosas:
            return "No hay IPs sospechosas registradas en el último barrido."
        partes = [self.bloquear_ip(ip) for ip in self.ultimas_sospechosas[:5]]
        return " " .join(partes)

    def cerrar_sesiones_remotas(self):
        """Cierra sesiones RDP activas de otros usuarios."""
        import subprocess
        try:
            q = subprocess.run(["qwinsta"], capture_output=True, text=True,
                               timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            salida = q.stdout or ""
            cerradas = []
            for linea in salida.splitlines():
                partes = linea.split()
                if len(partes) >= 3 and partes[1].lower().startswith(("rdp-tcp#",)) is False:
                    continue
                if len(partes) >= 3 and partes[1].lower().startswith("rdp-tcp#"):
                    sid = partes[-1]
                    if sid.isdigit():
                        r = subprocess.run(["logoff", sid], capture_output=True,
                                           text=True, timeout=15,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        if r.returncode == 0:
                            cerradas.append(linea.strip())
            if cerradas:
                return f"Sesiones remotas expulsadas ({len(cerradas)}): " + "; ".join(cerradas)
            return "No hay sesiones remotas activas que expulsar."
        except FileNotFoundError:
            return "Este sistema no expone qwinsta; uso el bloqueo por firewall."
        except Exception as e:
            return f"Fallo expulsando sesiones: {str(e)[:80]}"

    def informe(self, facial_estado=None):
        texto, sospechosas = self.escanear()
        reglas = self._contar_bloqueos()
        partes = [
            "INFORME DE SEGURIDAD DEL IMPERIO:",
            texto,
            f"Reglas de bloqueo ULTRON activas: {reglas}.",
        ]
        if facial_estado:
            fe = facial_estado
            partes.append(
                f"Guardián facial: {'ACTIVO' if fe.get('activo') else 'inactivo'} · "
                f"muestras de referencia: {fe.get('muestras', 0)} · "
                f"intrusos físicos archivados: {fe.get('intrusos_registrados', 0)}.")
        return "\n".join(partes)

    def _contar_bloqueos(self):
        import subprocess
        try:
            r = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"],
                capture_output=True, text=True, timeout=40,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return len(re.findall(r"ULTRON_BLOQUEO_", r.stdout or ""))
        except Exception:
            return "?"
