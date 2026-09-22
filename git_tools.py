#!/usr/bin/env python3
"""
git_tools.py - Idea 4 del IDEAS.MD: JARVIS ante repositorios de codigo
====================================================================
El enjambre ya avisa de repos con trabajo sin guardar (`_ag_codigo`). Esto le
da manos para actuar sobre ellos, siempre en LOCAL y sin nada hacia fuera:

    git_estado(repo)      rama, archivos sin guardar, commits sin subir
    git_diff(repo, ruta)  el diff, recortado
    correr_tests(repo)    detecta pytest / npm test / go test y lo ejecuta
    crear_rama(repo, x)   rama nueva desde la actual (si el arbol esta limpio)
    commit(repo, msg)     stage de todo + commit (NO push)
    revisar_pr(objetivo)  trae el diff de un PR (gh o API de GitHub) y deja que
                          el cerebro lo revise; solo lectura

Nada de push, merge, ni crear PRs: eso sale del equipo del señor y necesita su
mano. `commit` es lo mas lejos que llega, y queda en el log.
"""
import json
import os
import re
import shutil

_MAX_DIFF = 12000


def _run(args, repo=None, timeout=60, log=print) -> dict:
    import ejecutor
    cmd = list(args)
    if repo:
        cmd = ["git", "-C", repo] + cmd[1:] if cmd and cmd[0] == "git" else cmd
    return ejecutor.ejecutar(cmd, origen="git_tools", orden=" ".join(args),
                             shell=False, timeout=timeout, log=log)


def _es_repo(repo: str) -> bool:
    return bool(repo) and os.path.isdir(os.path.join(repo, ".git"))


def _resolver(repo: str) -> str:
    repo = os.path.abspath(os.path.expanduser((repo or ".").strip()))
    return repo


# ── lectura ────────────────────────────────────────────────────────────────
def git_estado(repo: str = ".", log=print) -> str:
    repo = _resolver(repo)
    if not _es_repo(repo):
        return f"{repo} no es un repositorio git."
    rama = (_run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo, log=log)
            .get("salida", "") or "").strip()
    estado = _run(["git", "status", "--porcelain"], repo, log=log).get("salida", "") or ""
    sucios = [l for l in estado.splitlines() if l.strip()]
    adelante = (_run(["git", "rev-list", "--count", "@{u}..HEAD"], repo, log=log)
                .get("salida", "") or "0").strip()
    try:
        adelante_n = int(adelante)
    except ValueError:
        adelante_n = 0
    lineas = [f"Repo: {repo}", f"Rama: {rama or '?'}",
              f"Archivos sin guardar: {len(sucios)}",
              f"Commits sin subir: {adelante_n}"]
    if sucios:
        lineas.append("Cambios:")
        lineas += [f"  {l}" for l in sucios[:30]]
    return "\n".join(lineas)


def git_diff(repo: str = ".", ruta: str = "", log=print) -> str:
    repo = _resolver(repo)
    if not _es_repo(repo):
        return f"{repo} no es un repositorio git."
    args = ["git", "diff"]
    if ruta:
        args += ["--", ruta]
    d = _run(args, repo, log=log).get("salida", "") or ""
    if not d.strip():
        d = _run(["git", "diff", "--cached"] + (["--", ruta] if ruta else []),
                 repo, log=log).get("salida", "") or ""
    if not d.strip():
        return "No hay cambios en el diff."
    return d[:_MAX_DIFF] + ("\n… (diff recortado)" if len(d) > _MAX_DIFF else "")


def correr_tests(repo: str = ".", log=print) -> str:
    repo = _resolver(repo)
    if not os.path.isdir(repo):
        return f"{repo} no existe."
    # Detectar el sistema de tests
    if os.path.exists(os.path.join(repo, "package.json")):
        try:
            pkg = json.load(open(os.path.join(repo, "package.json"), encoding="utf-8"))
            if "test" in (pkg.get("scripts") or {}):
                r = _run(["npm", "test", "--silent"], repo, timeout=300, log=log)
                return _parte_tests("npm test", r)
        except Exception:
            pass
    if any(os.path.exists(os.path.join(repo, x))
           for x in ("pytest.ini", "pyproject.toml", "setup.cfg", "tests", "test")):
        py = shutil.which("pytest") or None
        cmd = ["pytest", "-q"] if py else ["python", "-m", "pytest", "-q"]
        r = _run(cmd, repo, timeout=300, log=log)
        return _parte_tests("pytest", r)
    if os.path.exists(os.path.join(repo, "go.mod")):
        r = _run(["go", "test", "./..."], repo, timeout=300, log=log)
        return _parte_tests("go test", r)
    return "No reconozco el sistema de tests de este repo (ni npm, ni pytest, ni go)."


def _parte_tests(nombre: str, r: dict) -> str:
    cola = ((r.get("salida", "") or "") + "\n" + (r.get("error", "") or "")).strip()
    cola = "\n".join(cola.splitlines()[-25:])
    estado = "PASARON" if r.get("ok") else f"FALLARON (codigo {r.get('codigo')})"
    return f"{nombre}: {estado}\n{cola}"


# ── escritura local (sin push) ─────────────────────────────────────────────
def crear_rama(repo: str, nombre: str, log=print) -> str:
    repo = _resolver(repo)
    if not _es_repo(repo):
        return f"{repo} no es un repositorio git."
    nombre = re.sub(r"[^\w./-]+", "-", (nombre or "").strip()) or "jarvis-cambios"
    r = _run(["git", "checkout", "-b", nombre], repo, log=log)
    if r.get("ok"):
        return f"Rama «{nombre}» creada y activa en {os.path.basename(repo)}."
    return f"No pude crear la rama: {(r.get('error') or r.get('salida') or '')[:160]}"


def commit(repo: str, mensaje: str, log=print) -> str:
    repo = _resolver(repo)
    if not _es_repo(repo):
        return f"{repo} no es un repositorio git."
    if not (mensaje or "").strip():
        return "Hace falta un mensaje de commit."
    rama = (_run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo, log=log)
            .get("salida", "") or "").strip()
    if rama in ("main", "master"):
        return (f"Estás en «{rama}». No hago commit directo ahí; crea una rama "
                "primero («crea la rama ...»).")
    _run(["git", "add", "-A"], repo, log=log)
    r = _run(["git", "commit", "-m", mensaje.strip()], repo, log=log)
    if r.get("ok"):
        sha = (_run(["git", "rev-parse", "--short", "HEAD"], repo, log=log)
               .get("salida", "") or "").strip()
        return f"Commit {sha} hecho en «{rama}» ({os.path.basename(repo)}). Sin subir."
    return f"El commit falló: {(r.get('error') or r.get('salida') or '')[:160]}"


# ── revision de PR (solo lectura) ─────────────────────────────────────────
def _diff_pr(objetivo: str, repo: str = ".", log=print) -> tuple[str, str]:
    """Devuelve (titulo, diff). Usa gh si está; si no, la API de GitHub."""
    objetivo = (objetivo or "").strip()
    num = None
    slug = None
    m = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", objetivo)
    if m:
        slug, num = m.group(1), m.group(2)
    elif objetivo.isdigit():
        num = objetivo
    if shutil.which("gh"):
        args = ["gh", "pr", "view", num or objetivo, "--json", "title"]
        if slug:
            args += ["--repo", slug]
        meta = _run(args, repo if not slug else None, log=log)
        titulo = ""
        try:
            titulo = json.loads(meta.get("salida", "{}") or "{}").get("title", "")
        except Exception:
            pass
        dargs = ["gh", "pr", "diff", num or objetivo]
        if slug:
            dargs += ["--repo", slug]
        d = _run(dargs, repo if not slug else None, log=log).get("salida", "") or ""
        return titulo, d
    # API REST
    tok = os.getenv("GITHUB_TOKEN", "")
    if slug and num:
        try:
            import requests
            h = {"Accept": "application/vnd.github.v3.diff"}
            if tok:
                h["Authorization"] = f"Bearer {tok}"
            u = f"https://api.github.com/repos/{slug}/pulls/{num}"
            d = requests.get(u, headers=h, timeout=20).text
            return f"PR #{num} de {slug}", d
        except Exception as e:
            return "", f"(no pude traer el PR: {e})"
    return "", "(necesito la URL completa del PR de GitHub o la herramienta gh)"


def revisar_pr(objetivo: str, core=None, repo: str = ".", log=print) -> str:
    titulo, diff = _diff_pr(objetivo, repo=repo, log=log)
    if not diff or diff.startswith("("):
        return f"No pude revisar el PR: {diff or 'sin diff'}"
    diff = diff[:_MAX_DIFF]
    prompt = ("Eres un revisor de código senior. Revisa este diff y responde en "
              "español, breve y concreto: 1) qué hace, 2) riesgos o bugs, "
              "3) veredicto (aprobar / cambios menores / bloquear). Diff:\n\n" + diff)
    try:
        from openai import OpenAI
        nombre, url, modelo, clave = core._proveedores()[0]
        cli = OpenAI(base_url=url, api_key=clave)
        r = cli.chat.completions.create(
            model=modelo, messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=600)
        rev = (r.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Traje el diff de «{titulo or objetivo}» pero no pude analizarlo: {e}"
    return f"Revisión de «{titulo or objetivo}»:\n{rev}"
