#!/usr/bin/env python3
"""
ultron_arsenal.py — Seguridad ofensiva-defensiva de ULTRON, acotada siempre
al equipo y a la red local del señor (límite sagrado: jamás un objetivo
remoto arbitrario). Complementa a ultron_guardian.py, que ya cubre
conexiones remotas ESTABLISHED, bloqueo por firewall y sesiones RDP:

  1. SurfaceAuditor  — qué puertos tiene el propio equipo en escucha
     (superficie de ataque expuesta; hoy nadie audita esto).
  2. NetworkSweeper   — barrido activo de la subred local (TCP connect
     scan multihilo sobre puertos comunes) para descubrir hosts vivos,
     más profundo que la caché ARP pasiva que ya usa Jarvis en
     «quién está en mi red» (jarvis_skills.py:_quien_red).
  3. CredentialVault  — vault de credenciales cifrado en disco (Fernet +
     PBKDF2 sobre una contraseña maestra que nunca se persiste).
"""
import os
import json
import socket
import base64
import ipaddress
import concurrent.futures
from datetime import datetime

PUERTOS_COMUNES = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 80: "HTTP", 110: "POP3",
    135: "RPC", 139: "NetBIOS", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL", 5900: "VNC",
    5985: "WinRM", 6379: "Redis", 8080: "HTTP-alt", 8443: "HTTPS-alt",
    27017: "MongoDB",
}
PUERTOS_ALTO_RIESGO = {21, 23, 135, 139, 445, 3389, 5900, 5985}


def _ip_local() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ─────────────────────────────────────────────────────────────────────────
# 1. SUPERFICIE DE ATAQUE PROPIA (puertos en escucha)
# ─────────────────────────────────────────────────────────────────────────
class SurfaceAuditor:
    """Audita qué puertos tiene el propio equipo en escucha (LISTEN)."""

    def __init__(self, log=print):
        self.log = log

    def escanear(self):
        """Devuelve (texto, [puertos_de_alto_riesgo])."""
        try:
            import psutil
        except Exception as e:
            return f"No tengo psutil disponible para auditar puertos: {e}", []
        filas = {}
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.status != psutil.CONN_LISTEN or not c.laddr:
                    continue
                puerto = c.laddr.port
                if puerto in filas:
                    continue
                proc = "?"
                if c.pid:
                    try:
                        proc = psutil.Process(c.pid).name()
                    except Exception:
                        proc = "(restringido)"
                filas[puerto] = proc
        except Exception as e:
            self.log(f"[ARSENAL] escaneo de puertos falló: {e}")
            return f"No pude auditar los puertos en escucha: {e}", []
        if not filas:
            return "Ningún puerto en escucha detectado. Superficie de ataque mínima.", []
        riesgo = []
        lineas = ["Puertos en escucha en este equipo:"]
        for puerto, proc in sorted(filas.items()):
            servicio = PUERTOS_COMUNES.get(puerto, "")
            marca = ""
            if puerto in PUERTOS_ALTO_RIESGO:
                marca = "  << expuesto, alto riesgo si es alcanzable desde fuera"
                riesgo.append(puerto)
            etiqueta = f" ({servicio})" if servicio else ""
            lineas.append(f"- {puerto}{etiqueta}: {proc}{marca}")
        if riesgo:
            lineas.append(f"Puertos de alto riesgo: {', '.join(str(p) for p in riesgo)}. "
                          "Si no los necesitas expuestos a la red, ciérralos.")
        return "\n".join(lineas[:22]), riesgo


# ─────────────────────────────────────────────────────────────────────────
# 2. BARRIDO ACTIVO DE LA RED LOCAL
# ─────────────────────────────────────────────────────────────────────────
class NetworkSweeper:
    """Descubre hosts vivos en la red local (/24) sondeando puertos comunes.

    Solo opera sobre la subred local detectada automáticamente — jamás
    acepta un objetivo remoto arbitrario (límite sagrado del imperio)."""

    PUERTOS_SONDA = (22, 80, 135, 139, 443, 445, 3389, 8080)

    def __init__(self, log=print):
        self.log = log

    def _subred(self):
        ip = _ip_local()
        red = ipaddress.ip_network(f"{ip}/24", strict=False)
        return ip, red

    @staticmethod
    def _probar_puerto(ip, puerto, timeout=0.3) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return s.connect_ex((str(ip), puerto)) == 0
        except Exception:
            return False

    def _sondear_host(self, ip):
        abiertos = [p for p in self.PUERTOS_SONDA if self._probar_puerto(ip, p)]
        if not abiertos:
            return None
        nombre = ""
        try:
            nombre = socket.gethostbyaddr(str(ip))[0].split(".")[0]
        except Exception:
            pass
        return {"ip": str(ip), "nombre": nombre, "puertos": abiertos}

    def escanear(self, max_hilos: int = 64):
        """Lista de hosts vivos: [{ip, nombre, puertos}, ...] (best-effort:
        solo detecta hosts que respondan en alguno de los puertos sondeados)."""
        propia, red = self._subred()
        hosts = [h for h in red.hosts() if str(h) != propia]
        vivos = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_hilos) as ex:
            futuros = [ex.submit(self._sondear_host, h) for h in hosts]
            for fut in concurrent.futures.as_completed(futuros):
                r = fut.result()
                if r:
                    vivos.append(r)
        vivos.sort(key=lambda x: tuple(int(p) for p in x["ip"].split(".")))
        return vivos

    def informe(self):
        vivos = self.escanear()
        if not vivos:
            return "Barrido activo completo: ningún host respondió en los puertos sondeados."
        partes = []
        for h in vivos[:12]:
            etiqueta = h["nombre"] or h["ip"]
            servicios = ", ".join(f"{p}({PUERTOS_COMUNES.get(p, '?')})" for p in h["puertos"])
            partes.append(f"{etiqueta} [{h['ip']}]: {servicios}")
        return f"Barrido activo: {len(vivos)} host(s) vivos. " + " | ".join(partes)


# ─────────────────────────────────────────────────────────────────────────
# 3. VAULT DE CREDENCIALES CIFRADO
# ─────────────────────────────────────────────────────────────────────────
class CredentialVault:
    """Credenciales cifradas en disco (Fernet + PBKDF2 sobre una contraseña
    maestra). La contraseña maestra NUNCA se persiste: solo vive en memoria
    tras desbloquear el vault en la sesión actual."""

    def __init__(self, path=None, log=print):
        self.log = log
        self._path = path or os.path.join(
            os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "ultron_vault.enc")
        self._fernet = None

    def desbloqueado(self) -> bool:
        return self._fernet is not None

    def bloquear(self):
        self._fernet = None

    def desbloquear(self, master_password: str) -> bool:
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        except Exception as e:
            self.log(f"[VAULT] cryptography no disponible: {e}")
            return False
        salt = self._salt()
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
        key = base64.urlsafe_b64encode(kdf.derive(master_password.encode("utf-8")))
        self._fernet = Fernet(key)
        # Verificar contra el contenido existente (si lo hay); si la clave es
        # incorrecta, _leer_todo() devolverá None y re-bloqueamos.
        if os.path.exists(self._path) and self._leer_todo() is None:
            self._fernet = None
            return False
        return True

    def _salt_path(self):
        return self._path + ".salt"

    def _salt(self):
        sp = self._salt_path()
        if os.path.exists(sp):
            with open(sp, "rb") as f:
                return f.read()
        salt = os.urandom(16)
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        with open(sp, "wb") as f:
            f.write(salt)
        return salt

    def _leer_todo(self):
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "rb") as f:
                blob = f.read()
            if not blob:
                return {}
            data = self._fernet.decrypt(blob)
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None  # contraseña incorrecta o archivo corrupto

    def _escribir_todo(self, datos: dict):
        blob = self._fernet.encrypt(json.dumps(datos).encode("utf-8"))
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "wb") as f:
            f.write(blob)

    def guardar(self, servicio: str, usuario: str, secreto: str) -> str:
        if not self.desbloqueado():
            return "El vault está bloqueado. Dame la contraseña maestra primero."
        datos = self._leer_todo()
        if datos is None:
            return "Contraseña maestra incorrecta o vault corrupto."
        datos[servicio.lower()] = {
            "usuario": usuario, "secreto": secreto,
            "guardado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self._escribir_todo(datos)
        return f"Credencial de «{servicio}» cifrada y archivada."

    def leer(self, servicio: str) -> str:
        if not self.desbloqueado():
            return "El vault está bloqueado. Dame la contraseña maestra primero."
        datos = self._leer_todo()
        if datos is None:
            return "Contraseña maestra incorrecta o vault corrupto."
        entrada = datos.get(servicio.lower())
        if not entrada:
            return f"No tengo ninguna credencial archivada para «{servicio}»."
        return (f"«{servicio}»: usuario {entrada['usuario']}, secreto {entrada['secreto']} "
                f"(guardado el {entrada['guardado']}).")

    def listar(self) -> str:
        if not self.desbloqueado():
            return "El vault está bloqueado. Dame la contraseña maestra primero."
        datos = self._leer_todo()
        if datos is None:
            return "Contraseña maestra incorrecta o vault corrupto."
        if not datos:
            return "El vault está vacío."
        return "Credenciales archivadas: " + ", ".join(sorted(datos.keys()))

    def borrar(self, servicio: str) -> str:
        if not self.desbloqueado():
            return "El vault está bloqueado. Dame la contraseña maestra primero."
        datos = self._leer_todo()
        if datos is None:
            return "Contraseña maestra incorrecta o vault corrupto."
        if servicio.lower() not in datos:
            return f"No tengo ninguna credencial de «{servicio}»."
        del datos[servicio.lower()]
        self._escribir_todo(datos)
        return f"Credencial de «{servicio}» eliminada."
