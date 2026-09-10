#!/usr/bin/env python3
"""
sandbox_android.py - Ensayo previo de acciones en el móvil (idea 2 del IDEAS.MD)
=============================================================================
La idea 2 pedía un emulador Android en el backend para ejecutar miles de
variantes antes de tocar el teléfono real. Ese emulador es infra aparte (AVD /
QEMU headless) y no está aquí. Lo que sí se puede hacer sin él, y es donde
estaba el 90 % del valor, es un **pre-vuelo de confianza** sobre el dispositivo
real, igual que `sandbox.py` hace para Windows:

    1. Lee el árbol de accesibilidad (uiautomator dump) varias veces.
    2. Comprueba que el selector del objetivo resuelve a UN solo nodo y que es
       estable entre lecturas (no hay "selector drift").
    3. Comprueba que el nodo está en pantalla y admite la acción pedida.
    4. Devuelve un % de confianza. <95 % => pedir confirmación al señor.

No ejecuta nada: solo mira. Si no hay dispositivo, lo dice y recomienda
confirmar a mano.
"""
import os
import re
import time

_UMBRAL = float(os.getenv("JARVIS_MOVIL_UMBRAL", "0.95"))
_LECTURAS = 3


def _mcp():
    try:
        import mcp_generico
        return mcp_generico
    except Exception:
        return None


def _dump(mcp) -> str:
    try:
        r = mcp.llamar("mcp__android__android_dump_ui", {"compressed": True},
                       log=lambda *a: None)
        return r if isinstance(r, str) else str(r)
    except Exception:
        return ""


def _nodos(xml: str, texto: str = "", resource_id: str = "") -> list:
    """Cuenta nodos que casan con el selector, sin parsear XML completo."""
    if not xml:
        return []
    encontrados = []
    for m in re.finditer(r"<node\b[^>]*>", xml):
        frag = m.group(0)
        if texto:
            t = re.search(r'text="([^"]*)"', frag)
            if not t or texto.lower() not in t.group(1).lower():
                continue
        if resource_id:
            r = re.search(r'resource-id="([^"]*)"', frag)
            if not r or resource_id not in r.group(1):
                continue
        if not texto and not resource_id:
            continue
        bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', frag)
        enabled = 'enabled="true"' in frag
        encontrados.append({"bounds": bounds.groups() if bounds else None,
                            "enabled": enabled})
    return encontrados


def ensayar(objetivo: str, texto: str = "", resource_id: str = "",
            accion: str = "tap", log=print) -> dict:
    """Devuelve {confianza, ok, motivo, detalle}."""
    mcp = _mcp()
    if mcp is None:
        return {"confianza": 0.0, "ok": False,
                "motivo": "sin cliente MCP", "detalle": "no puedo mirar el móvil"}

    lecturas = []
    for _ in range(_LECTURAS):
        xml = _dump(mcp)
        malo = (not xml or "<node" not in xml
                or re.search(r"error|fall[oó]|sin dispositivo|no hay m[oó]vil", xml[:120], re.I))
        if malo:
            return {"confianza": 0.0, "ok": False,
                    "motivo": "sin dispositivo",
                    "detalle": "no hay móvil conectado o el volcado falló; pide confirmación al señor"}
        lecturas.append(_nodos(xml, texto, resource_id))
        time.sleep(0.3)

    conteos = [len(l) for l in lecturas]
    if all(c == 0 for c in conteos):
        return {"confianza": 0.0, "ok": False, "motivo": "no encontrado",
                "detalle": f"el selector «{texto or resource_id}» no aparece en pantalla"}

    # Estabilidad: mismo número de coincidencias en todas las lecturas.
    estable = len(set(conteos)) == 1
    unico = conteos[-1] == 1
    ultimo = lecturas[-1]
    habilitado = bool(ultimo and ultimo[0].get("enabled"))
    en_pantalla = bool(ultimo and ultimo[0].get("bounds"))

    confianza = 0.0
    confianza += 0.4 if unico else (0.15 if conteos[-1] <= 3 else 0.0)
    confianza += 0.3 if estable else 0.0
    confianza += 0.15 if habilitado else 0.0
    confianza += 0.15 if en_pantalla else 0.0
    if accion == "text_input" and not habilitado:
        confianza *= 0.5

    motivo = []
    if not unico:
        motivo.append(f"{conteos[-1]} coincidencias, no una")
    if not estable:
        motivo.append(f"el selector varía entre lecturas ({conteos})")
    if not habilitado:
        motivo.append("el elemento no parece activable")

    return {
        "confianza": round(min(1.0, confianza), 2),
        "ok": confianza >= _UMBRAL,
        "motivo": "; ".join(motivo) or "selector único y estable",
        "detalle": f"«{objetivo}»: {conteos[-1]} nodo(s), estable={estable}, "
                   f"activable={habilitado}",
    }


def informe(objetivo: str, texto: str = "", resource_id: str = "",
            accion: str = "tap", log=print) -> str:
    r = ensayar(objetivo, texto, resource_id, accion, log=log)
    pct = int(r["confianza"] * 100)
    if r["ok"]:
        return (f"Ensayo del móvil, señor: {pct}% de confianza en «{objetivo}». "
                f"{r['detalle']}. Procedo.")
    return (f"Ensayo del móvil, señor: solo {pct}% de confianza en «{objetivo}» "
            f"({r['motivo']}). Prefiero que lo confirme antes de tocar el teléfono.")
