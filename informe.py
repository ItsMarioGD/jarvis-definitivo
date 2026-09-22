#!/usr/bin/env python3
"""
informe.py - Prácticas, memorias y trabajos, con sus fórmulas
=============================================================
Lo último que falta de la carrera: entregar. Un informe de prácticas siempre
tiene la misma forma —objetivo, fundamento teórico, método, datos, resultados,
discusión, conclusiones— y siempre se pierde la misma tarde en darle formato.

Aquí sale en tres formatos a la vez, y cada uno sirve para algo distinto:

    .tex    para LaTeX y Overleaf, que es lo que piden en ingeniería
    .docx   para entregar por el campus, que es lo que se suele exigir
    .md     para leerlo y corregirlo sin abrir nada pesado

Tres cosas que lo separan de pedirle un texto al modelo y pegarlo
-----------------------------------------------------------------
1. **Las fórmulas se calculan, no se recuerdan.** Si el informe lleva cuentas,
   pasan por `fisica_general` o `matematica`, con sus unidades. Lo que se
   escribe está resuelto con sympy, no recordado por un modelo.
2. **Se apoya en TUS apuntes.** Lo que haya indexado sobre el tema entra como
   material de partida y se cita el archivo del que sale.
3. **Lo que no puede saber, lo deja marcado.** Las mediciones de laboratorio,
   los datos propios y las fechas van entre corchetes en vez de inventados.
   Un informe con datos inventados es peor que uno sin terminar.

No compila el PDF porque en este equipo no hay LaTeX instalado; el `.tex` sale
listo para Overleaf y el `.docx` se entrega tal cual.
"""
import os
import re
import time

_BASE = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Informes")

SECCIONES = ("Objetivo", "Fundamento teórico", "Material y método",
             "Datos experimentales", "Resultados", "Discusión",
             "Conclusiones", "Referencias")

_PROMPT = """Eres un estudiante de ingeniería redactando un informe de
prácticas. Escribe en español, en tono técnico y sobrio, sin florituras.

Responde SOLO con un JSON:

{"titulo": "...",
 "secciones": [{"titulo": "Objetivo", "texto": "..."}, ...],
 "formulas": [{"nombre": "...", "latex": "F = m a", "explicacion": "..."}],
 "referencias": ["..."]}

Reglas que NO se saltan:
- Usa las secciones que te doy, en ese orden.
- Lo que no puedas saber (mediciones del laboratorio, valores propios, la
  fecha de la sesión, el nombre del grupo) va entre corchetes:
  [medición pendiente]. NO te lo inventes.
- Si te doy apuntes, apóyate en ellos y menciona de qué archivo sale cada
  cosa importante.
- Si te doy cálculos ya resueltos, úsalos tal cual: están verificados.
- Las fórmulas, en LaTeX sin los signos de dólar.
- Nada de rellenar por rellenar: una sección corta y correcta vale más.

Secciones: {secciones}
"""


def _escapar_tex(texto: str) -> str:
    """Los caracteres que LaTeX se toma como órdenes.

    Sin esto, un simple «100 % de rendimiento» comenta el resto de la línea y
    el informe sale mutilado sin que se vea por qué.
    """
    reemplazos = (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                  ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                  ("}", r"\}"), ("~", r"\textasciitilde{}"),
                  ("^", r"\textasciicircum{}"))
    for viejo, nuevo in reemplazos:
        texto = texto.replace(viejo, nuevo)
    return texto


def _plantilla_tex(titulo: str, autor: str, secciones: list,
                   formulas: list, referencias: list) -> str:
    cuerpo = []
    for s in secciones:
        cuerpo.append(f"\\section{{{_escapar_tex(s['titulo'])}}}")
        cuerpo.append(_escapar_tex(s["texto"]).replace("\n\n", "\n\n"))
        cuerpo.append("")
    if formulas:
        cuerpo.append("\\section{Formulario empleado}")
        for f in formulas:
            cuerpo.append(f"\\paragraph{{{_escapar_tex(f.get('nombre', ''))}}}")
            # El LaTeX de la fórmula NO se escapa: es LaTeX a propósito.
            cuerpo.append("\\begin{equation}")
            cuerpo.append(f.get("latex", ""))
            cuerpo.append("\\end{equation}")
            if f.get("explicacion"):
                cuerpo.append(_escapar_tex(f["explicacion"]))
            cuerpo.append("")
    if referencias:
        cuerpo.append("\\begin{thebibliography}{9}")
        for i, r in enumerate(referencias, 1):
            cuerpo.append(f"\\bibitem{{ref{i}}} {_escapar_tex(r)}")
        cuerpo.append("\\end{thebibliography}")

    return f"""\\documentclass[11pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[spanish,es-noshorthands]{{babel}}
\\usepackage{{amsmath,amssymb,siunitx,graphicx,booktabs}}
\\usepackage[margin=2.5cm]{{geometry}}

\\title{{{_escapar_tex(titulo)}}}
\\author{{{_escapar_tex(autor)}}}
\\date{{{time.strftime('%d de %B de %Y')}}}

\\begin{{document}}
\\maketitle

{chr(10).join(cuerpo)}

\\end{{document}}
"""


def _plantilla_md(titulo: str, autor: str, secciones: list,
                  formulas: list, referencias: list) -> str:
    partes = [f"# {titulo}", "", f"**{autor}** · {time.strftime('%d/%m/%Y')}", ""]
    for s in secciones:
        partes += [f"## {s['titulo']}", "", s["texto"], ""]
    if formulas:
        partes += ["## Formulario empleado", ""]
        for f in formulas:
            partes += [f"**{f.get('nombre', '')}**", "",
                       f"$${f.get('latex', '')}$$", ""]
            if f.get("explicacion"):
                partes += [f.get("explicacion"), ""]
    if referencias:
        partes += ["## Referencias", ""]
        partes += [f"{i}. {r}" for i, r in enumerate(referencias, 1)]
    return "\n".join(partes)


def _escribir_docx(ruta: str, titulo: str, autor: str, secciones: list,
                   formulas: list, referencias: list, log=print) -> str:
    """El .docx, que es lo que suele pedir el campus."""
    try:
        from docx import Document
        from docx.shared import Pt
    except Exception as e:
        log(f"[INFORME] Sin python-docx no hay .docx: {e}")
        return ""
    doc = Document()
    doc.add_heading(titulo, level=0)
    p = doc.add_paragraph(f"{autor} · {time.strftime('%d/%m/%Y')}")
    p.runs[0].font.size = Pt(10)
    for s in secciones:
        doc.add_heading(s["titulo"], level=1)
        for parrafo in (s["texto"] or "").split("\n\n"):
            if parrafo.strip():
                doc.add_paragraph(parrafo.strip())
    if formulas:
        doc.add_heading("Formulario empleado", level=1)
        for f in formulas:
            doc.add_heading(f.get("nombre", ""), level=2)
            # Word no compone LaTeX: va como texto monoespaciado, que se lee y
            # se puede pegar en el editor de ecuaciones.
            eq = doc.add_paragraph(f.get("latex", ""))
            eq.runs[0].font.name = "Consolas"
            if f.get("explicacion"):
                doc.add_paragraph(f["explicacion"])
    if referencias:
        doc.add_heading("Referencias", level=1)
        for r in referencias:
            doc.add_paragraph(r, style="List Number")
    doc.save(ruta)
    return ruta


def _nombre_archivo(titulo: str) -> str:
    limpio = re.sub(r"[^\w\s-]", "", titulo or "informe")[:50].strip()
    return (limpio.replace(" ", "_") or "informe") + "-" + time.strftime("%Y%m%d")


def redactar(core, encargo: str, autor: str = "", secciones=None,
             calculos: str = "", log=print) -> dict:
    """Escribe el informe entero y lo deja en tres formatos.

    `calculos` es texto ya resuelto (de `fisica_general`, `vectores` o
    `ciencias`) que se le pasa al modelo como verdad: así los números del
    informe están calculados, no recordados.
    """
    encargo = (encargo or "").strip()
    if not encargo:
        return {"ok": False, "mensaje": "¿Sobre qué informe, señor?"}

    secciones = list(secciones or SECCIONES)

    # Los apuntes del señor sobre el tema, si los tiene indexados.
    apuntes, fuentes = "", []
    try:
        import indice_documentos
        trozos = indice_documentos.buscar(encargo, k=5, log=log)
        if trozos:
            apuntes = "\n\n".join(f"[{os.path.basename(r)}]\n{t[:900]}"
                                  for r, t, _p in trozos)
            fuentes = sorted({os.path.basename(r) for r, _t, _p in trozos})
    except Exception as e:
        log(f"[INFORME] Sin apuntes: {e}")

    entrada = [f"Encargo: {encargo}"]
    if apuntes:
        entrada.append(f"Mis apuntes sobre el tema:\n{apuntes}")
    if calculos:
        entrada.append(f"Cálculos YA RESUELTOS y verificados (úsalos tal cual):\n"
                       f"{calculos}")

    import pensar
    datos = pensar.estructura(
        core, _PROMPT.replace("{secciones}", ", ".join(secciones)),
        "\n\n".join(entrada), tope=5000, log=log)
    if not datos:
        return {"ok": False,
                "mensaje": "El cerebro no devolvió un informe que pueda escribir, señor."}

    titulo = str(datos.get("titulo") or encargo)[:120]
    lista = [s for s in (datos.get("secciones") or [])
             if isinstance(s, dict) and s.get("titulo")]
    for s in lista:
        s["texto"] = str(s.get("texto") or "").strip()
    if not lista:
        return {"ok": False, "mensaje": "El informe salió sin secciones, señor."}

    formulas = [f for f in (datos.get("formulas") or []) if isinstance(f, dict)]
    referencias = [str(r) for r in (datos.get("referencias") or []) if r]
    for f in fuentes:
        referencias.append(f"Apuntes propios: {f}")

    autor = autor or os.getenv("JARVIS_AUTOR", "").strip() or "[su nombre]"
    os.makedirs(_BASE, exist_ok=True)
    base = os.path.join(_BASE, _nombre_archivo(titulo))

    rutas = {}
    try:
        with open(base + ".tex", "w", encoding="utf-8") as fh:
            fh.write(_plantilla_tex(titulo, autor, lista, formulas, referencias))
        rutas["tex"] = base + ".tex"
    except Exception as e:
        log(f"[INFORME] No pude escribir el .tex: {e}")
    try:
        with open(base + ".md", "w", encoding="utf-8") as fh:
            fh.write(_plantilla_md(titulo, autor, lista, formulas, referencias))
        rutas["md"] = base + ".md"
    except Exception as e:
        log(f"[INFORME] No pude escribir el .md: {e}")
    docx = _escribir_docx(base + ".docx", titulo, autor, lista, formulas,
                          referencias, log=log)
    if docx:
        rutas["docx"] = docx

    pendientes = sum(len(re.findall(r"\[[^\]]{3,60}\]", s["texto"])) for s in lista)
    mensaje = (f"Informe «{titulo}» listo, señor, en {len(rutas)} formatos:\n"
               + "\n".join(f"  · {os.path.basename(v)}" for v in rutas.values()))
    if fuentes:
        mensaje += f"\nMe he apoyado en {', '.join(fuentes)}."
    if pendientes:
        mensaje += (f"\nHay {pendientes} huecos entre corchetes: son los datos "
                    "que no puedo saber yo (mediciones, fechas, su nombre). "
                    "Rellénelos antes de entregar.")
    mensaje += "\nNo lo he entregado: eso lo hace usted."
    return {"ok": True, "titulo": titulo, "rutas": rutas, "carpeta": _BASE,
            "huecos": pendientes, "mensaje": mensaje}


def listar(limite: int = 12) -> str:
    if not os.path.isdir(_BASE):
        return "No ha hecho ningún informe todavía, señor."
    archivos = sorted((f for f in os.listdir(_BASE) if f.endswith(".md")),
                      key=lambda f: os.path.getmtime(os.path.join(_BASE, f)),
                      reverse=True)
    if not archivos:
        return "No ha hecho ningún informe todavía, señor."
    return ("Sus informes, señor:\n"
            + "\n".join(f"  · {f[:-3]}" for f in archivos[:limite]))


def resumen_estado() -> dict:
    n = 0
    if os.path.isdir(_BASE):
        n = len([f for f in os.listdir(_BASE) if f.endswith(".md")])
    try:
        import docx  # noqa: F401
        hay_docx = True
    except Exception:
        hay_docx = False
    return {"informes": n, "docx": hay_docx, "carpeta": _BASE,
            "formatos": ["tex", "md"] + (["docx"] if hay_docx else [])}


if __name__ == "__main__":
    try:
        import consola_utf8  # noqa: F401
    except Exception:
        pass
    print(listar())
    print(resumen_estado())
