#!/usr/bin/env python3
"""
cerebro_salud.py - Backoff y cuarentena por proveedor de LLM
==========================================================
`_rate_limit_ok` en jarvis_core es un `sleep` global tosco. Esto es lo que
faltaba: si un proveedor concreto falla (429, caída, timeout), se le pone en
**cuarentena** un rato que crece de forma exponencial con cada fallo seguido,
y el núcleo pasa al siguiente proveedor sin perder tiempo con el que está roto.

    fallo 1 -> 15 s     fallo 2 -> 30 s     fallo 3 -> 60 s ...   tope 900 s

Un éxito lo resetea. Todo en memoria: es estado de la sesión, no de disco.
"""
import time

_BASE = 15.0
_TOPE = 900.0
_estado = {}   # clave -> {"fallos": int, "hasta": float, "ultimo": str}


def _c(clave: str) -> dict:
    return _estado.setdefault(clave, {"fallos": 0, "hasta": 0.0, "ultimo": ""})


def en_cuarentena(clave: str) -> bool:
    return time.time() < _c(clave)["hasta"]


def segundos_restantes(clave: str) -> int:
    return max(0, int(_c(clave)["hasta"] - time.time()))


def registrar_fallo(clave: str, error: str = "", log=print):
    d = _c(clave)
    d["fallos"] += 1
    d["ultimo"] = str(error)[:160]
    espera = min(_BASE * (2 ** (d["fallos"] - 1)), _TOPE)
    d["hasta"] = time.time() + espera
    log(f"[CEREBRO-SALUD] «{clave}» en cuarentena {int(espera)} s "
        f"(fallo {d['fallos']}): {d['ultimo']}")


def registrar_exito(clave: str):
    d = _c(clave)
    if d["fallos"] or d["hasta"]:
        d.update(fallos=0, hasta=0.0, ultimo="")


def estado() -> dict:
    ahora = time.time()
    return {k: {"fallos": v["fallos"],
                "cuarentena_s": max(0, int(v["hasta"] - ahora)),
                "ultimo_error": v["ultimo"]}
            for k, v in _estado.items() if v["fallos"] or v["hasta"] > ahora}


def informe() -> str:
    e = estado()
    if not e:
        return "Todos mis proveedores de cerebro están sanos, señor."
    partes = [f"{k}: {v['fallos']} fallos, {v['cuarentena_s']} s de cuarentena"
              for k, v in e.items()]
    return "Proveedores con problemas, señor — " + "; ".join(partes) + "."
