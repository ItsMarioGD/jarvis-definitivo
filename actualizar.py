#!/usr/bin/env python3
"""
actualizar.py - Actualizar sin quedarse sin asistente
=====================================================
Con 35 archivos nuevos y 20 modulos que se llaman entre si, la proxima
actualizacion que rompa algo deja al señor sin asistente y sin saber que
cambio. Este modulo hace que eso no pase:

    1. anota en que commit estamos AHORA,
    2. guarda una copia del cerebro (memoria y preferencias),
    3. trae los cambios (git pull),
    4. instala dependencias nuevas si el requirements cambio,
    5. pasa la bateria de pruebas completa,
    6. si algo falla, VUELVE al commit anterior y lo dice.

    python actualizar.py            comprobar y actualizar
    python actualizar.py --probar   solo mirar si hay novedades
    python actualizar.py --volver   deshacer la ultima actualizacion

La vuelta atras es un `git reset --hard` al commit anotado: por eso el paso 1
existe y por eso se exige que el arbol este limpio antes de empezar.
"""
import json
import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
REGISTRO = os.path.join(RAIZ, "jarvis_log", "actualizaciones.json")


def _git(*args, timeout: int = 120):
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True,
                          text=True, timeout=timeout)


def _commit_actual() -> str:
    r = _git("rev-parse", "HEAD")
    return (r.stdout or "").strip()[:12]


def _arbol_limpio() -> tuple:
    r = _git("status", "--porcelain")
    sucios = [l for l in (r.stdout or "").splitlines() if l.strip()]
    return (not sucios), sucios


def _anotar(entrada: dict):
    try:
        os.makedirs(os.path.dirname(REGISTRO), exist_ok=True)
        historial = []
        if os.path.exists(REGISTRO):
            with open(REGISTRO, encoding="utf-8") as f:
                historial = json.load(f) or []
        historial.append(entrada)
        with open(REGISTRO, "w", encoding="utf-8") as f:
            json.dump(historial[-30:], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _ultima() -> dict:
    try:
        with open(REGISTRO, encoding="utf-8") as f:
            historial = json.load(f) or []
        return historial[-1] if historial else {}
    except Exception:
        return {}


# ── comprobar ───────────────────────────────────────────────────────────────
def hay_novedades(log=print) -> dict:
    """¿Hay cambios nuevos en el remoto? Sin tocar nada."""
    r = _git("remote")
    if not (r.stdout or "").strip():
        return {"hay": False, "motivo": "este repositorio no tiene remoto configurado"}
    _git("fetch", "--quiet")
    local = _git("rev-parse", "HEAD").stdout.strip()
    remoto = _git("rev-parse", "@{u}").stdout.strip()
    if not remoto:
        return {"hay": False, "motivo": "la rama no sigue a ninguna remota"}
    if local == remoto:
        return {"hay": False, "motivo": "ya está al día"}
    conteo = _git("rev-list", "--count", "HEAD..@{u}").stdout.strip() or "?"
    resumen = _git("log", "--oneline", "-5", "HEAD..@{u}").stdout.strip()
    return {"hay": True, "commits": conteo, "resumen": resumen}


# ── actualizar ──────────────────────────────────────────────────────────────
def actualizar(log=print, forzar: bool = False) -> str:
    """El ciclo completo con vuelta atrás automática si algo falla."""
    limpio, sucios = _arbol_limpio()
    if not limpio and not forzar:
        return (f"Tiene {len(sucios)} archivos con cambios sin guardar, señor. "
                "No actualizo con el árbol sucio: se perderían. "
                "Guárdelos (git commit) o use --forzar si sabe lo que hace.")

    novedades = hay_novedades(log=log)
    if not novedades.get("hay"):
        return f"No hay nada que actualizar, señor: {novedades.get('motivo', '')}."

    commit_previo = _commit_actual()
    log(f"[ACTUALIZAR] Punto de retorno: {commit_previo}")

    # Copia del cerebro antes de tocar nada.
    copia = ""
    try:
        import cerebro_backup
        copia = cerebro_backup.exportar(log=log)
    except Exception as e:
        log(f"[ACTUALIZAR] No pude copiar el cerebro: {e}")

    requirements_antes = _hash_requirements()

    tiron = _git("pull", "--ff-only", timeout=300)
    if tiron.returncode != 0:
        return (f"No pude traer los cambios, señor: {(tiron.stderr or '')[:200]}. "
                "No he tocado nada.")

    # Dependencias nuevas, si el requirements cambió.
    if _hash_requirements() != requirements_antes:
        log("[ACTUALIZAR] requirements.txt ha cambiado: instalando…")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                        os.path.join(RAIZ, "requirements.txt"), "--quiet"],
                       cwd=RAIZ, capture_output=True, timeout=900)

    pruebas = subprocess.run([sys.executable, "test_regresion.py"], cwd=RAIZ,
                             capture_output=True, text=True, timeout=600)
    if pruebas.returncode != 0:
        salida = (pruebas.stdout or "")[-500:]
        volver(commit_previo, log=log)
        _anotar({"ts": time.strftime("%Y-%m-%d %H:%M"), "desde": commit_previo,
                 "resultado": "revertida", "motivo": "pruebas en rojo"})
        return ("La actualización rompía algo, señor, así que he vuelto a la "
                f"versión anterior ({commit_previo}). Lo que falló:\n{salida}")

    nuevo = _commit_actual()
    _anotar({"ts": time.strftime("%Y-%m-%d %H:%M"), "desde": commit_previo,
             "hasta": nuevo, "resultado": "ok", "copia": copia})
    return (f"Actualizado, señor: de {commit_previo} a {nuevo}, "
            f"{novedades.get('commits', '?')} cambios, y las pruebas siguen en verde. "
            "Reinícieme para que corra la versión nueva.")


def _hash_requirements() -> str:
    import hashlib
    try:
        with open(os.path.join(RAIZ, "requirements.txt"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return ""


def volver(commit: str = "", log=print) -> str:
    """Vuelve al commit anterior a la última actualización."""
    if not commit:
        commit = (_ultima() or {}).get("desde", "")
    if not commit:
        return "No tengo anotado ningún punto de retorno, señor."
    r = _git("reset", "--hard", commit)
    if r.returncode != 0:
        return f"No pude volver a {commit}, señor: {(r.stderr or '')[:150]}"
    log(f"[ACTUALIZAR] Vuelto a {commit}")
    return (f"He vuelto a la versión {commit}, señor. Reinícieme para que la "
            "cargue.")


def historial(limite: int = 5) -> str:
    try:
        with open(REGISTRO, encoding="utf-8") as f:
            entradas = json.load(f) or []
    except Exception:
        entradas = []
    if not entradas:
        return "No he hecho ninguna actualización todavía, señor."
    filas = "; ".join(f"{e['ts']} {e.get('desde', '?')}→{e.get('hasta', '?')} "
                      f"({e.get('resultado')})" for e in entradas[-limite:])
    return f"Últimas actualizaciones, señor: {filas}."


def main(argv) -> int:
    if "--probar" in argv or "--comprobar" in argv:
        datos = hay_novedades()
        if datos.get("hay"):
            print(f"Hay {datos['commits']} cambios nuevos:\n{datos['resumen']}")
        else:
            print(f"Sin novedades: {datos.get('motivo')}")
        return 0
    if "--volver" in argv:
        print(volver())
        return 0
    if "--historial" in argv:
        print(historial())
        return 0
    print(actualizar(forzar="--forzar" in argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
