#!/usr/bin/env python3
"""
deshacer.py - Diario reversible: «deshaz eso»
=============================================
Hasta ahora toda accion del asistente era definitiva. Mover doscientos archivos
a la carpeta equivocada, cerrar la app con el trabajo sin guardar o vaciar una
carpeta no tenian vuelta atras, y esa es la razon de fondo por la que da miedo
darle autonomia de verdad: no porque se equivoque mas que un humano, sino
porque sus errores no se podian revertir.

Aqui cada accion peligrosa anota **como se revierte** antes de ejecutarse:

    deshacer.anotar("mover_archivos", "moví 12 PDF a Documentos",
                    {"movimientos": [[origen, destino], ...]})

Y luego basta con decir «deshaz eso». El registro vive en storage.py, o sea que
sobrevive a reinicios: se puede deshacer algo hecho ayer.

Tipos reversibles admitidos
---------------------------
  mover_archivos  {"movimientos": [[origen, destino], ...]}
  renombrar       {"cambios": [[ruta_antes, ruta_despues], ...]}
  papelera        {"rutas": [...]}          (restaura desde la papelera)
  comando         {"inverso": "shutdown /a"}
  app_cerrada     {"comando": "notepad.exe", "nombre": "Bloc de notas"}
  preferencia     {"clave": "voz_windows", "antes": "on"}

Lo que NO se puede deshacer se dice claramente en vez de fingir que si.
"""
import json
import os
import shutil

_SIN_VENTANA = 0x08000000 if os.name == "nt" else 0


def _almacen(log=print):
    from storage import get_storage
    return get_storage(log=log)


# ── registrar ───────────────────────────────────────────────────────────────
def anotar(tipo: str, descripcion: str, datos: dict, agente: str = "JARVIS",
           log=print) -> int:
    """Apunta como revertir una accion recien hecha."""
    try:
        return _almacen(log).anotar_deshacer(tipo, descripcion,
                                             json.dumps(datos, ensure_ascii=False),
                                             agente=agente)
    except Exception as e:
        log(f"deshacer: no pude anotar «{descripcion[:40]}»: {e}")
        return 0


def a_papelera(ruta: str, log=print) -> bool:
    """Borra mandando a la papelera (reversible) en vez de destruir.

    Un borrado normal no se puede deshacer de ninguna manera; la papelera si.
    Devuelve True si el archivo acabo en la papelera.
    """
    if not os.path.exists(ruta):
        return False
    try:
        from send2trash import send2trash
        send2trash(ruta)
        return True
    except Exception:
        pass
    # Sin send2trash: la Shell de Windows tambien sabe hacerlo.
    try:
        import ejecutor
        ps = ("$sh = New-Object -ComObject Shell.Application; "
              f"$item = $sh.NameSpace(0).ParseName('{ruta}'); "
              "if ($item) { $item.InvokeVerb('delete') }")
        res = ejecutor.powershell(ps, origen="papelera", orden=ruta, log=log)
        return res["ok"]
    except Exception as e:
        log(f"deshacer: no pude enviar a la papelera {ruta}: {e}")
        return False


# ── revertir ────────────────────────────────────────────────────────────────
def _revertir_mover(datos, log):
    hechos, fallos = 0, 0
    for origen, destino in datos.get("movimientos", []):
        try:
            if os.path.exists(destino):
                os.makedirs(os.path.dirname(origen) or ".", exist_ok=True)
                shutil.move(destino, origen)
                hechos += 1
            else:
                fallos += 1
        except Exception as e:
            log(f"deshacer: no pude devolver {destino}: {e}")
            fallos += 1
    return hechos, fallos


def _revertir_renombrar(datos, log):
    hechos, fallos = 0, 0
    for antes, despues in datos.get("cambios", []):
        try:
            if os.path.exists(despues):
                os.rename(despues, antes)
                hechos += 1
            else:
                fallos += 1
        except Exception as e:
            log(f"deshacer: no pude renombrar {despues}: {e}")
            fallos += 1
    return hechos, fallos


def _revertir_papelera(datos, log):
    """Restaura desde la papelera con la Shell de Windows."""
    hechos, fallos = 0, 0
    try:
        import ejecutor
    except Exception:
        return 0, len(datos.get("rutas", []))
    for ruta in datos.get("rutas", []):
        nombre = os.path.basename(ruta)
        ps = ("$sh = New-Object -ComObject Shell.Application; "
              "$papelera = $sh.NameSpace(10); "
              f"$item = $papelera.Items() | Where-Object {{ $_.Name -eq '{nombre}' }} | "
              "Select-Object -First 1; "
              "if ($item) { $item.InvokeVerb('restore'); 'ok' } else { 'no' }")
        res = ejecutor.powershell(ps, origen="deshacer", orden=f"restaurar {nombre}", log=log)
        if res["ok"] and "ok" in (res["salida"] or ""):
            hechos += 1
        else:
            fallos += 1
    return hechos, fallos


def _revertir_comando(datos, log):
    import ejecutor
    inverso = datos.get("inverso")
    if not inverso:
        return 0, 1
    res = ejecutor.ejecutar(inverso, origen="deshacer", orden="revertir", log=log)
    return (1, 0) if res["ok"] else (0, 1)


def _revertir_app(datos, log):
    import ejecutor
    comando = datos.get("comando")
    if not comando:
        return 0, 1
    ok, _error, _p = ejecutor.lanzar(comando, origen="deshacer",
                                     orden=f"reabrir {datos.get('nombre', '')}",
                                     verificar_ms=400, log=log)
    return (1, 0) if ok else (0, 1)


def _revertir_preferencia(datos, log, set_pref):
    if set_pref is None or not datos.get("clave"):
        return 0, 1
    try:
        set_pref(datos["clave"], datos.get("antes", ""))
        return 1, 0
    except Exception as e:
        log(f"deshacer: preferencia {datos.get('clave')}: {e}")
        return 0, 1


_REVERSORES = {
    "mover_archivos": _revertir_mover,
    "renombrar": _revertir_renombrar,
    "papelera": _revertir_papelera,
    "comando": _revertir_comando,
    "app_cerrada": _revertir_app,
}


def deshacer_ultimo(n: int = 1, log=print, set_pref=None, agente: str = "") -> str:
    """Revierte las n ultimas acciones reversibles. Devuelve el parte para decirlo."""
    db = _almacen(log)
    pendientes = db.deshacer_pendientes(limite=max(1, n), agente=agente)
    if not pendientes:
        return "No tengo nada que deshacer, señor."

    partes, total_ok, total_mal = [], 0, 0
    for entrada in pendientes:          # ya vienen de la mas reciente hacia atras
        try:
            datos = json.loads(entrada.get("datos") or "{}")
        except Exception:
            datos = {}
        tipo = entrada.get("tipo", "")
        if tipo == "preferencia":
            hechos, fallos = _revertir_preferencia(datos, log, set_pref)
        else:
            reversor = _REVERSORES.get(tipo)
            if reversor is None:
                partes.append(f"«{entrada['descripcion'][:50]}» no se puede deshacer")
                continue
            hechos, fallos = reversor(datos, log)
        total_ok += hechos
        total_mal += fallos
        db.marcar_deshecho(entrada["id"])
        estado = "revertido" if hechos and not fallos else (
            "revertido a medias" if hechos else "no se pudo revertir")
        partes.append(f"«{entrada['descripcion'][:50]}»: {estado}")
        try:
            db.registrar_evento("deshacer", entrada["descripcion"][:80],
                                f"{hechos} revertidos, {fallos} fallidos",
                                gravedad="info", agente=entrada.get("agente", "JARVIS"))
        except Exception:
            pass

    resumen = "; ".join(partes)
    if total_mal and not total_ok:
        return f"No pude deshacerlo, señor: {resumen}."
    if total_mal:
        return f"Deshecho en parte, señor: {resumen}."
    return f"Deshecho, señor: {resumen}."


def listar(limite: int = 5, log=print, agente: str = "") -> str:
    """Que se puede deshacer ahora mismo."""
    pendientes = _almacen(log).deshacer_pendientes(limite=limite, agente=agente)
    if not pendientes:
        return "No hay nada reversible pendiente, señor."
    filas = "; ".join(f"{e['ts'][5:16]} {e['descripcion'][:50]}" for e in pendientes)
    return f"Puedo deshacer: {filas}."
