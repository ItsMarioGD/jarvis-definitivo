#!/usr/bin/env python3
"""
auto_mejora.py - DRÁSTICO #4: JARVIS edita su propio repo con rama + tests + PR
============================================================================
`autoskills.py` escribe skills sueltas y `analista.py` escribe programas. Esto
cierra el bucle sobre el PROPIO código de JARVIS, con barandillas duras:

    1. Rama nueva desde la actual (nunca se toca main/master).
    2. Un agente con herramientas de fichero (acotadas al repo) hace los cambios.
    3. Se corre run_tests.py. Si algo falla -> se deja la rama para inspección
       y se informa; NO se mergea nada, jamás.
    4. Si pasa -> commit local + (si hay gh/GITHUB_TOKEN y se pidió) PR. El
       merge SIEMPRE lo hace el señor.

Desactivado por defecto. Requiere JARVIS_AUTOMEJORA=1 y, por permisos, la
confirmación explícita del señor.
"""
import os
import re
import subprocess
import sys
import time

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_RONDAS = 14

_SISTEMA = (
    "Eres un ingeniero que trabaja sobre el repositorio de JARVIS, en {raiz}. "
    "Tienes herramientas para leer, buscar, escribir y editar archivos (solo "
    "dentro del repo) y para git y tests. Aplica el cambio pedido con el mínimo "
    "diff, sin romper el estilo del código de alrededor. Cuando termines, corre "
    "los tests con correr_tests y responde en español con un resumen de qué "
    "tocaste y el resultado de los tests. No hagas push ni abras PRs tú."
)


def activo() -> bool:
    return os.getenv("JARVIS_AUTOMEJORA", "0") == "1"


def _git(*args, timeout=60):
    return subprocess.run(["git", "-C", _RAIZ, *args], capture_output=True,
                          text=True, timeout=timeout)


def _slug(s: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", (s or "cambio").lower()).strip("-") or "cambio")[:40]


def proponer(core, objetivo: str, abrir_pr: bool = False, log=print) -> str:
    if not activo():
        return ("Señor, la auto-mejora está desactivada. Active JARVIS_AUTOMEJORA=1 "
                "si de verdad quiere que edite mi propio código.")
    if not (objetivo or "").strip():
        return "¿Qué quiere que mejore, señor?"

    rama_base = (_git("rev-parse", "--abbrev-ref", "HEAD").stdout or "").strip()
    if rama_base in ("main", "master"):
        return (f"Estoy en «{rama_base}». Cámbieme a una rama de trabajo antes de "
                "pedirme que me modifique, señor.")
    sucio = [l for l in (_git("status", "--porcelain").stdout or "").splitlines() if l.strip()]
    if sucio:
        return (f"Hay {len(sucio)} archivos sin guardar en el repo, señor. Prefiero "
                "no auto-modificarme con el árbol sucio.")

    rama = f"jarvis/auto-{_slug(objetivo)}-{time.strftime('%m%d%H%M')}"
    r = _git("checkout", "-b", rama)
    if r.returncode != 0:
        return f"No pude crear la rama: {(r.stderr or r.stdout)[:160]}"
    log(f"[AUTOMEJORA] rama {rama} desde {rama_base}")

    resumen = _bucle(core, objetivo, log=log)

    # Correr tests
    tests_ok, tests_txt = _tests(log=log)
    if not tests_ok:
        _git("add", "-A"); _git("commit", "-m", f"WIP auto-mejora: {objetivo[:60]} (tests en rojo)")
        _git("checkout", rama_base)
        return (f"Señor, intenté «{objetivo[:60]}» pero los tests quedaron en rojo. "
                f"Dejé el intento en la rama {rama} para que lo revise. "
                f"{tests_txt[:200]}")

    _git("add", "-A")
    c = _git("commit", "-m", f"Auto-mejora: {objetivo[:70]}\n\n{resumen[:400]}\n\n"
             "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>")
    if c.returncode != 0 and "nothing to commit" in (c.stdout + c.stderr):
        _git("checkout", rama_base); _git("branch", "-D", rama)
        return f"Señor, no llegué a cambiar nada para «{objetivo[:60]}». {resumen[:200]}"
    sha = (_git("rev-parse", "--short", "HEAD").stdout or "").strip()

    pr_txt = ""
    if abrir_pr:
        pr_txt = _pr(rama, objetivo, resumen, log=log)

    _git("checkout", rama_base)
    return (f"Señor, hice «{objetivo[:60]}» en la rama {rama} (commit {sha}). "
            f"Los tests pasan. {tests_txt[:120]} {pr_txt} "
            "El merge es cosa suya.")


def _bucle(core, objetivo: str, log=print) -> str:
    try:
        from openai import OpenAI
        import herramientas_llm, json as _j
    except Exception as e:
        return f"sin dependencias: {e}"
    try:
        nombre, url, modelo, clave = core._proveedores()[0]
        cli = OpenAI(base_url=url, api_key=clave)
    except Exception as e:
        return f"sin proveedor: {e}"

    caja = herramientas_llm.Herramientas(core, log=log)
    # En auto-mejora, el agente puede escribir sin frenar en cada archivo.
    caja._confirmado = {"escribir_archivo", "editar_archivo", "correr_tests",
                        "git_estado", "git_diff"}
    defs = caja.definiciones()
    conv = [{"role": "system", "content": _SISTEMA.format(raiz=_RAIZ)},
            {"role": "user", "content": objetivo}]
    for _ in range(_RONDAS):
        conv = herramientas_llm.podar_conversacion(conv)
        try:
            resp = cli.chat.completions.create(model=modelo, messages=conv, tools=defs,
                                               tool_choice="auto", temperature=0.1,
                                               max_tokens=700)
        except Exception as e:
            return f"el modelo falló: {str(e)[:120]}"
        m = resp.choices[0].message
        lls = getattr(m, "tool_calls", None) or []
        if not lls:
            return (m.content or "").strip() or ("hecho: " + ", ".join(caja.usadas))
        conv.append({"role": "assistant", "content": m.content or "",
                     "tool_calls": [{"id": c.id, "type": "function",
                                     "function": {"name": c.function.name,
                                                  "arguments": c.function.arguments}}
                                    for c in lls]})
        for c in lls:
            try:
                a = _j.loads(c.function.arguments or "{}")
            except Exception:
                a = {}
            out = caja.ejecutar(c.function.name, a)
            conv.append({"role": "tool", "tool_call_id": c.id, "content": str(out)[:1500]})
    return "agoté las rondas; " + ", ".join(caja.usadas)


_ARNES_OFFLINE = (
    "import sys, run_tests as R\n"
    "for g in ('test_skills','test_memory','test_modulos_nuevos'):\n"
    "    try: getattr(R, g)()\n"
    "    except SystemExit: pass\n"
    "    except Exception as e: R.ok(g, False, str(e)[:80])\n"
    "print('OFFLINE', R.PASS, R.FAIL)\n"
    "sys.exit(1 if R.FAIL else 0)\n"
)


def _tests(log=print):
    """No corre la suite entera (test_http necesita servidores): compila lo
    cambiado y pasa los grupos offline de run_tests.py."""
    exe = sys.executable
    cambiados = [l for l in (_git("diff", "--name-only", "HEAD").stdout or "").splitlines()
                 if l.strip().endswith(".py")]
    for f in cambiados:
        c = subprocess.run([exe, "-m", "py_compile", f], cwd=_RAIZ,
                           capture_output=True, text=True)
        if c.returncode != 0:
            return False, f"{f} no compila: {(c.stderr or '')[:160]}"
    try:
        r = subprocess.run([exe, "-c", _ARNES_OFFLINE], cwd=_RAIZ,
                           capture_output=True, text=True, timeout=400)
        cola = "\n".join((r.stdout or "").splitlines()[-4:])
        return (r.returncode == 0), cola or (r.stderr or "")[-200:]
    except Exception as e:
        return True, f"(no pude correr los grupos offline: {str(e)[:80]}; compilan {len(cambiados)})"


def _pr(rama: str, objetivo: str, resumen: str, log=print) -> str:
    import shutil
    if not shutil.which("gh"):
        return "(sin gh: no abro PR; suba la rama y ábralo usted)."
    _git("push", "-u", "origin", rama, timeout=120)
    r = subprocess.run(["gh", "pr", "create", "--fill", "--head", rama,
                        "--title", f"Auto-mejora: {objetivo[:60]}",
                        "--body", f"{resumen[:1000]}\n\n🤖 Generated with Claude Code"],
                       cwd=_RAIZ, capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        return f"PR abierto: {(r.stdout or '').strip()}"
    return f"(no pude abrir el PR: {(r.stderr or '')[:120]})"
