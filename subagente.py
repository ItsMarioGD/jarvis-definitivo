#!/usr/bin/env python3
"""
subagente.py - Delegar una subtarea a un agente aparte
=====================================================
`enjambre.py` son vigilantes periódicos; `mision.py` son objetivos de horas.
Faltaba el intermedio: "resuelve esto AHORA mientras yo sigo hablándote".

`delegar(core, tarea)` lanza un agente con su propio bucle de herramientas
(hasta 8 rondas, su propio presupuesto) sobre una subtarea concreta, y
devuelve un resumen. En segundo plano, el resumen llega por voz al terminar.

Reusa la caja de herramientas de `herramientas_llm.py`, así que hereda los
permisos (una tool "confirmar" para el sub-agente igual que para el principal:
no ejecuta sola nada que necesite el «confirma» del señor).
"""
import threading
import time

RONDAS_SUBAGENTE = 8

_SISTEMA = (
    "Eres un sub-agente de JARVIS. Se te ha delegado UNA subtarea concreta. "
    "Usa las herramientas disponibles para resolverla, sin conversar. "
    "Cuando termines, responde en español con un resumen breve de qué hiciste "
    "y el resultado. Si no puedes, di por qué en una frase."
)

_activos = {}          # id -> {tarea, estado, inicio, resultado}
_lock = threading.Lock()
_contador = [0]
_CORE_REF = [None]     # último core, para el aviso por voz al terminar


def _correr(core, tarea: str, sid: int, log=print):
    try:
        from openai import OpenAI
        import herramientas_llm
        import json as _j
    except Exception as e:
        _fin(sid, f"sub-agente sin dependencias: {e}", log)
        return
    try:
        nombre, url, modelo, clave = core._proveedores()[0]
        _local = ("localhost" in url) or ("127.0.0.1" in url)
        if not _local:
            try:
                import presupuesto
                if not presupuesto.permite_nube():
                    _fin(sid, "no delego: tope de gasto del día alcanzado", log)
                    return
            except Exception:
                pass
        cliente = OpenAI(base_url=url, api_key=clave)
    except Exception as e:
        _fin(sid, f"sub-agente sin proveedor: {e}", log)
        return

    caja = herramientas_llm.Herramientas(core, log=log)
    definiciones = caja.definiciones()
    conversacion = [
        {"role": "system", "content": _SISTEMA},
        {"role": "user", "content": tarea},
    ]
    for _ronda in range(RONDAS_SUBAGENTE):
        try:
            resp = cliente.chat.completions.create(
                model=modelo, messages=conversacion, tools=definiciones,
                tool_choice="auto", temperature=0.2, max_tokens=500)
        except Exception as e:
            _fin(sid, f"el modelo falló: {str(e)[:120]}", log)
            return
        msg = resp.choices[0].message
        llamadas = getattr(msg, "tool_calls", None) or []
        if not llamadas:
            texto = (msg.content or "").strip()
            if "</think>" in texto:
                texto = texto.split("</think>", 1)[1].strip()
            _fin(sid, texto or ("hecho: " + ", ".join(caja.usadas)), log)
            return
        conversacion.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name,
                                         "arguments": c.function.arguments}}
                           for c in llamadas]})
        for c in llamadas:
            try:
                args = _j.loads(c.function.arguments or "{}")
            except Exception:
                args = {}
            r = caja.ejecutar(c.function.name, args)
            conversacion.append({"role": "tool", "tool_call_id": c.id,
                                 "content": str(r)[:1500]})
            if caja.pendiente:
                _fin(sid, f"paré: «{r}» (necesita su confirmación, señor)", log)
                return
    _fin(sid, "agoté las rondas; hecho en parte: " + ", ".join(caja.usadas), log)


def _fin(sid: int, resultado: str, log=print):
    with _lock:
        info = _activos.get(sid)
        if info:
            info["estado"] = "listo"
            info["resultado"] = resultado
            info["fin"] = time.time()
    log(f"[SUBAGENTE {sid}] {resultado[:150]}")
    # Aviso por voz al terminar, si el sub-agente corría en segundo plano.
    try:
        if info and info.get("segundo_plano") and getattr(_CORE_REF[0], "tts_queue", None):
            _CORE_REF[0].tts_queue.put(f"Señor, terminé la subtarea: {resultado[:200]}")
            info["entregado"] = True
    except Exception:
        pass
    try:
        from storage import get_storage
        get_storage(log=log).registrar_evento(
            "subagente", (info or {}).get("tarea", "")[:120], resultado[:400],
            gravedad="info")
    except Exception:
        pass


def delegar(core, tarea: str, en_segundo_plano: bool = True, log=print) -> str:
    """Lanza el sub-agente. Si en_segundo_plano, devuelve al instante y el
    resumen llega por voz; si no, espera hasta 90 s y devuelve el resumen."""
    if not (tarea or "").strip():
        return "¿Qué subtarea le delego, señor?"
    _CORE_REF[0] = core
    with _lock:
        _contador[0] += 1
        sid = _contador[0]
        _activos[sid] = {"tarea": tarea, "estado": "corriendo",
                         "inicio": time.time(), "resultado": "",
                         "segundo_plano": bool(en_segundo_plano)}

    hilo = threading.Thread(target=_correr, args=(core, tarea, sid),
                            kwargs={"log": log}, daemon=True)
    hilo.start()

    if en_segundo_plano:
        return (f"En marcha, señor. Un sub-agente se encarga de «{tarea[:60]}» "
                "y le aviso cuando termine.")

    hilo.join(timeout=90)
    with _lock:
        info = _activos.get(sid, {})
    if info.get("estado") == "listo":
        return f"Subtarea resuelta, señor: {info['resultado']}"
    return (f"La subtarea «{tarea[:50]}» sigue en curso, señor; le aviso al "
            "terminar.")


def entregar_pendientes(core, log=print) -> list:
    """Resúmenes de sub-agentes que acabaron y aún no se han contado.
    Lo llama el bucle proactivo / el saludo para soltar los avisos por voz."""
    salida = []
    with _lock:
        for sid, info in list(_activos.items()):
            if info.get("estado") == "listo" and not info.get("entregado"):
                info["entregado"] = True
                salida.append(f"Sub-agente: {info['resultado']}")
    return salida


def estado() -> dict:
    with _lock:
        return {sid: {"tarea": i["tarea"][:60], "estado": i["estado"]}
                for sid, i in _activos.items()}
