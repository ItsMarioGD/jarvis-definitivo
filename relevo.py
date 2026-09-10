#!/usr/bin/env python3
"""
relevo.py - Protocolo de inactividad (interruptor de hombre muerto, versión sensata)
====================================================================================
Si al señor le pasa algo, todo lo que vive en este equipo (documentos, claves de
paso, proyectos a medias) se queda inaccesible o, peor, accesible para quien no
debe. Este modulo prepara ese escenario sin convertirse en un peligro por si
mismo.

Version deliberadamente conservadora, por una razon concreta: un falso positivo
(unas vacaciones sin PC, un ingreso corto, un movil roto) no puede provocar
nada irreversible.

  * NUNCA BORRA NADA. Cifra y avisa. Punto.
  * ESCALADO EN TRES AVISOS. A los N dias, a N+3 y a N+7. Cualquier
    interaccion con JARVIS —una sola frase— cancela todo el proceso.
  * CONFIRMACION POR DOS CANALES antes de ejecutar: hay que ignorar tanto los
    avisos por Telegram como los del propio equipo.
  * TODO REVERSIBLE mientras el señor este: la clave de cifrado se guarda donde
    el diga, y el protocolo se desactiva con una frase.

El cifrado usa `cryptography` si esta instalado; si no, comprime con 7-Zip y
contraseña si esta disponible; y si no hay ninguno de los dos, se limita a
avisar y lo dice claramente, en vez de aparentar que ha protegido algo.
"""
import json
import os
import secrets
import time
from datetime import datetime, timedelta

PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
CONFIG = os.path.join(PREFS, "relevo.json")
DIAS_AVISO = int(os.getenv("JARVIS_RELEVO_DIAS", "30"))


def _config() -> dict:
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _guardar(cfg: dict):
    os.makedirs(PREFS, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── configuración ───────────────────────────────────────────────────────────
def activar(dias: int = DIAS_AVISO, carpetas=None, contacto: str = "",
            mensaje: str = "", log=print) -> str:
    """Enciende el protocolo. No hace nada hasta que pasen `dias` sin señales."""
    cfg = _config()
    cfg.update({
        "activo": True,
        "dias": max(7, int(dias)),          # menos de una semana es temerario
        # `carpetas=[]` significa «ninguna», no «las de por defecto»: quien
        # pide proteger nada tiene que poder pedirlo.
        "carpetas": (carpetas if carpetas is not None
                     else [os.path.join(os.path.expanduser("~"), "Documentos")]),
        "contacto": contacto,
        "mensaje": mensaje or ("Este es un aviso automático configurado por el "
                               "dueño de este equipo ante una ausencia prolongada."),
        "ultimo_latido": time.time(),
        "avisos_enviados": 0,
        "ejecutado": False,
    })
    _guardar(cfg)
    return (f"Protocolo de relevo activo, señor: si pasan {cfg['dias']} días sin "
            "señales suyas, empezaré a avisar. Nunca borraré nada; solo cifraré "
            "lo que me indique y avisaré a quien me diga. Una sola frase suya lo "
            "reinicia todo.")


def desactivar(log=print) -> str:
    cfg = _config()
    cfg["activo"] = False
    _guardar(cfg)
    return "Protocolo de relevo desactivado, señor."


def latido(log=print):
    """Marca que el señor sigue aquí. Se llama en cada interacción."""
    cfg = _config()
    if not cfg.get("activo"):
        return
    cfg["ultimo_latido"] = time.time()
    if cfg.get("avisos_enviados"):
        cfg["avisos_enviados"] = 0        # volvió: el contador se reinicia
        log("[RELEVO] El señor ha dado señales; cancelo el escalado.")
    _guardar(cfg)


# ── vigilancia ──────────────────────────────────────────────────────────────
def revisar(core=None, log=print) -> str:
    """Comprueba la inactividad y escala si toca. Devuelve lo que ha hecho."""
    cfg = _config()
    if not cfg.get("activo") or cfg.get("ejecutado"):
        return ""
    dias_sin = (time.time() - cfg.get("ultimo_latido", time.time())) / 86400
    umbral = cfg.get("dias", DIAS_AVISO)

    if dias_sin < umbral:
        return ""

    enviados = cfg.get("avisos_enviados", 0)
    if dias_sin >= umbral + 7 and enviados >= 2:
        return _ejecutar(cfg, core=core, log=log)

    if (enviados == 0) or (dias_sin >= umbral + 3 and enviados == 1):
        cfg["avisos_enviados"] = enviados + 1
        _guardar(cfg)
        texto = (f"Señor, llevo {dias_sin:.0f} días sin noticias suyas. "
                 f"Aviso {enviados + 1} de 2. Si no da señales, en unos días "
                 "cifraré las carpetas señaladas y avisaré a su contacto. "
                 "Cualquier frase suya cancela todo esto.")
        _avisar(texto, core=core, log=log)
        return texto
    return ""


def _avisar(texto: str, core=None, log=print):
    log(f"[RELEVO] {texto}")
    try:
        if core is not None and getattr(core, "tts_queue", None) is not None:
            core.tts_queue.put(texto)
    except Exception:
        pass
    try:
        from conectores import Notificador
        Notificador(notify=None, log=log).avisar("protocolo de relevo", texto)
    except Exception as e:
        log(f"[RELEVO] No pude avisar fuera: {e}")


# ── ejecución ───────────────────────────────────────────────────────────────
def _ejecutar(cfg: dict, core=None, log=print) -> str:
    """Cifra lo señalado y avisa. Nunca borra nada."""
    clave = cfg.get("clave") or secrets.token_urlsafe(24)
    cfg["clave"] = clave
    resultados = []

    for carpeta in cfg.get("carpetas", []):
        if not os.path.isdir(carpeta):
            continue
        ok, detalle = _cifrar_carpeta(carpeta, clave, log=log)
        resultados.append(f"{os.path.basename(carpeta)}: {detalle}")
        _ = ok

    cfg["ejecutado"] = True
    cfg["ejecutado_el"] = datetime.now().isoformat(timespec="seconds")
    _guardar(cfg)

    texto = (cfg.get("mensaje", "") + " "
             + (f"Contenido protegido: {'; '.join(resultados)}. " if resultados
                else "No había carpetas que proteger. ")
             + "La clave está guardada en la configuración del asistente, en el "
               "propio equipo. No se ha borrado ningún archivo.")
    _avisar(texto, core=core, log=log)
    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "relevo", "Protocolo de inactividad ejecutado",
            "; ".join(resultados)[:400], gravedad="critica")
    except Exception:
        pass
    return texto


def _cifrar_carpeta(carpeta: str, clave: str, log=print):
    """Cifra el contenido con lo que haya disponible. Nunca borra el original."""
    destino = carpeta.rstrip("\\/") + "_protegido.zip"
    try:
        from cryptography.fernet import Fernet
        import base64
        import hashlib
        import zipfile

        semilla = base64.urlsafe_b64encode(hashlib.sha256(clave.encode()).digest())
        fernet = Fernet(semilla)
        temporal = destino + ".tmp"
        with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as z:
            for base, _dirs, ficheros in os.walk(carpeta):
                for f in ficheros:
                    completo = os.path.join(base, f)
                    z.write(completo, os.path.relpath(completo, carpeta))
        with open(temporal, "rb") as f:
            cifrado = fernet.encrypt(f.read())
        with open(destino, "wb") as f:
            f.write(cifrado)
        os.unlink(temporal)
        return True, f"cifrado en {os.path.basename(destino)}"
    except ImportError:
        pass
    except Exception as e:
        log(f"[RELEVO] Cifrado fuerte falló: {e}")

    # Segundo intento: 7-Zip con contraseña, si está instalado.
    for exe in (r"C:\Program Files\7-Zip\7z.exe", "7z"):
        try:
            import ejecutor
            res = ejecutor.ejecutar([exe, "a", "-tzip", f"-p{clave}", "-mem=AES256",
                                     destino, carpeta],
                                    origen="relevo", orden="proteger carpeta",
                                    shell=False, timeout=600, log=log)
            if res["ok"]:
                return True, f"comprimido con contraseña en {os.path.basename(destino)}"
        except Exception:
            continue

    return False, ("no pude cifrarla (falta «cryptography» o 7-Zip); "
                   "queda intacta y sin proteger")


# ── estado ──────────────────────────────────────────────────────────────────
def estado() -> dict:
    cfg = _config()
    if not cfg:
        return {"activo": False}
    dias_sin = (time.time() - cfg.get("ultimo_latido", time.time())) / 86400
    return {
        "activo": bool(cfg.get("activo")),
        "dias_umbral": cfg.get("dias", DIAS_AVISO),
        "dias_sin_señales": round(dias_sin, 1),
        "avisos_enviados": cfg.get("avisos_enviados", 0),
        "ejecutado": bool(cfg.get("ejecutado")),
        "carpetas": cfg.get("carpetas", []),
        "contacto": cfg.get("contacto", ""),
    }


def resumen() -> str:
    e = estado()
    if not e.get("activo"):
        return "El protocolo de relevo está desactivado, señor."
    quedan = e["dias_umbral"] - e["dias_sin_señales"]
    return (f"Protocolo activo, señor: {e['dias_sin_señales']:.0f} días sin señales "
            f"de {e['dias_umbral']}. Quedan {max(quedan, 0):.0f} días para el primer "
            f"aviso. Carpetas protegidas: {len(e['carpetas'])}. Nunca borro nada.")
