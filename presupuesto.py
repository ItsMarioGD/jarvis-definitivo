#!/usr/bin/env python3
"""
presupuesto.py - Un tope de gasto que corta de verdad
====================================================
`metricas.py` estima el gasto de voz de ElevenLabs, pero nadie contaba los
tokens del cerebro. Con un proveedor de nube de pago (y sin la barra de "te
quedan X creditos" delante), una tarde de pruebas puede costar dinero sin que
nadie se entere hasta la factura.

Esto lleva la cuenta del dia y **corta**:

* `registrar_uso(proveedor, modelo, tokens_in, tokens_out)` tras cada llamada.
* `excedido()` -> True cuando se pasa del tope en dolares O en tokens.
* El nucleo consulta `permite_nube()` antes de llamar a un proveedor de nube:
  si se paso, se salta la nube y usa el modelo local; si no hay local, avisa.

Topes (variables de entorno):
    JARVIS_PRESUPUESTO_USD      tope diario en dolares  (0 = sin tope)   def 1.0
    JARVIS_PRESUPUESTO_TOKENS   tope diario en tokens   (0 = sin tope)   def 0
    JARVIS_PRECIO_DEFECTO_USD_1M  precio por 1M tokens de un modelo sin
                                  tarifa conocida (p. ej. Kimi)          def 0

Precios por 1M de tokens (entrada/salida) en `Prefs/precios_llm.json`; si no
existe se siembra con unos pocos conocidos. Un modelo sin tarifa cuenta tokens
pero suma 0 dolares salvo que se ponga JARVIS_PRECIO_DEFECTO_USD_1M.
"""
import json
import os
import threading
import time

_PREFS = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs")
_ESTADO = os.path.join(_PREFS, "presupuesto.json")
_PRECIOS = os.path.join(_PREFS, "precios_llm.json")

_TOPE_USD = float(os.getenv("JARVIS_PRESUPUESTO_USD", "1.0"))
_TOPE_TOKENS = int(os.getenv("JARVIS_PRESUPUESTO_TOKENS", "0"))
_PRECIO_DEFECTO = float(os.getenv("JARVIS_PRECIO_DEFECTO_USD_1M", "0"))

_PRECIOS_BASE = {
    # modelo (substring, minusculas): [usd_1M_entrada, usd_1M_salida]
    "gpt-4o-mini":       [0.15, 0.60],
    "gpt-4o":            [2.50, 10.0],
    "gpt-4.1-mini":      [0.40, 1.60],
    "o4-mini":           [1.10, 4.40],
    "claude-3-5-haiku":  [0.80, 4.0],
    "claude-3-5-sonnet": [3.0, 15.0],
    "claude-sonnet":     [3.0, 15.0],
    "deepseek-chat":     [0.27, 1.10],
    "llama-3.1-70b":     [0.59, 0.79],
    "groq":              [0.10, 0.10],
}

_lock = threading.RLock()
_mem = None


def _hoy() -> str:
    return time.strftime("%Y-%m-%d")


def _cargar() -> dict:
    global _mem
    if _mem is not None and _mem.get("dia") == _hoy():
        return _mem
    d = {"dia": _hoy(), "usd": 0.0, "tokens": 0, "por_proveedor": {}}
    try:
        with open(_ESTADO, encoding="utf-8") as f:
            guardado = json.load(f)
        if guardado.get("dia") == _hoy():
            d = guardado
    except Exception:
        pass
    _mem = d
    return d


def _guardar():
    try:
        os.makedirs(_PREFS, exist_ok=True)
        with open(_ESTADO, "w", encoding="utf-8") as f:
            json.dump(_mem, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _precios() -> dict:
    try:
        with open(_PRECIOS, encoding="utf-8") as f:
            return {**_PRECIOS_BASE, **(json.load(f) or {})}
    except Exception:
        pass
    try:
        os.makedirs(_PREFS, exist_ok=True)
        with open(_PRECIOS, "w", encoding="utf-8") as f:
            json.dump(_PRECIOS_BASE, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return dict(_PRECIOS_BASE)


def _tarifa(modelo: str):
    m = (modelo or "").lower()
    for clave, par in _precios().items():
        if clave in m:
            return par
    return [_PRECIO_DEFECTO, _PRECIO_DEFECTO]


def coste_estimado(modelo: str, tokens_in: int, tokens_out: int) -> float:
    ent, sal = _tarifa(modelo)
    return (tokens_in / 1_000_000) * ent + (tokens_out / 1_000_000) * sal


# ── API ────────────────────────────────────────────────────────────────────
def registrar_uso(proveedor: str, modelo: str, tokens_in: int = 0,
                  tokens_out: int = 0, log=print):
    """Suma el gasto de una llamada al cerebro. Nunca falla."""
    try:
        with _lock:
            d = _cargar()
            usd = coste_estimado(modelo, tokens_in or 0, tokens_out or 0)
            d["usd"] = round(d["usd"] + usd, 6)
            d["tokens"] += int(tokens_in or 0) + int(tokens_out or 0)
            p = d["por_proveedor"].setdefault(
                proveedor or modelo or "?", {"usd": 0.0, "tokens": 0})
            p["usd"] = round(p["usd"] + usd, 6)
            p["tokens"] += int(tokens_in or 0) + int(tokens_out or 0)
            _guardar()
            if usd:
                log(f"[PRESUPUESTO] {proveedor}/{modelo}: "
                    f"+{usd:.4f} USD (dia {d['usd']:.4f})")
    except Exception as e:
        log(f"[PRESUPUESTO] no pude registrar: {e}")


def registrar_uso_estimado(proveedor: str, modelo: str, texto_in: str,
                           texto_out: str, log=print):
    """Cuando el proveedor no devuelve `usage` (streaming): ~4 car/token."""
    registrar_uso(proveedor, modelo,
                  len(texto_in or "") // 4, len(texto_out or "") // 4, log=log)


def excedido() -> bool:
    with _lock:
        d = _cargar()
        if _TOPE_USD and d["usd"] >= _TOPE_USD:
            return True
        if _TOPE_TOKENS and d["tokens"] >= _TOPE_TOKENS:
            return True
        return False


def permite_nube() -> bool:
    """False cuando hay que dejar de llamar a proveedores de pago hoy."""
    return not excedido()


def aviso_corte() -> str:
    d = _cargar()
    return (f"Señor, hoy he alcanzado el tope de gasto del cerebro en la nube "
            f"({d['usd']:.2f} de {_TOPE_USD:.2f} dolares). Sigo con el modelo "
            f"local hasta mañana, o suba JARVIS_PRESUPUESTO_USD si lo necesita.")


def estado() -> dict:
    with _lock:
        d = dict(_cargar())
    d["tope_usd"] = _TOPE_USD
    d["tope_tokens"] = _TOPE_TOKENS
    d["excedido"] = excedido()
    return d


def informe() -> str:
    d = estado()
    trozos = [f"{n}: {v['usd']:.3f} USD / {v['tokens']} tokens"
              for n, v in d.get("por_proveedor", {}).items()]
    cuerpo = "; ".join(trozos) or "sin gasto hoy"
    tope = f" (tope {d['tope_usd']:.2f} USD)" if d["tope_usd"] else ""
    estado_txt = " — TOPE ALCANZADO" if d["excedido"] else ""
    return f"Gasto del cerebro hoy — {cuerpo}. Total {d['usd']:.3f} USD{tope}{estado_txt}."


def reiniciar():
    global _mem
    with _lock:
        _mem = {"dia": _hoy(), "usd": 0.0, "tokens": 0, "por_proveedor": {}}
        _guardar()
