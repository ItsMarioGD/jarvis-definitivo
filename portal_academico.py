#!/usr/bin/env python3
"""
portal_academico.py - JARVIS entra en tu campus y te dice qué debes
===================================================================
El campus virtual es donde vive la carrera: los cursos, el material, las
entregas y —sobre todo— las fechas que se pasan sin avisar. Mirarlo a mano
todos los días es justo el trabajo que un asistente debería quitarte.

Esto lo hace con las tuberías que ya existen:

    navegador.py          entra, pulsa y lee la página de verdad
    navegador.datos()     lee el JSON que la web pide por detrás
    indice_documentos.py  el material descargado pasa a ser buscable
    conectores.py         las entregas van al calendario
    jarvis_proactive.py   y avisan antes de que venzan

Por qué leer la API y no la página
----------------------------------
Moodle y Canvas pintan la pantalla con JavaScript a partir de un JSON. Rascar
el texto renderizado funciona hasta el primer rediseño; leer el JSON da el dato
exacto —id del curso, fecha límite en segundos, si está entregado— y no se
rompe. Si el portal no es ninguno de los conocidos, se cae al modo general:
el modelo mira la página como la miraría el señor.

Dos cosas que NO hace, y no son negociables
-------------------------------------------
* **No teclea tu contraseña.** La primera vez entras tú en la ventana de
  JARVIS; la sesión queda guardada en su perfil y a partir de ahí entra solo.
  `navegador.escribir()` se niega en seco ante cualquier campo de contraseña.
* **No pulsa «entregar».** Prepara el borrador, te lo enseña y el botón lo
  pulsas tú. Una entrega no se deshace, y el que responde delante del tribunal
  eres tú. Comprueba además la norma de tu universidad sobre uso de IA: varían
  mucho.

Configuración en `Prefs/portal.json` (se siembra en el primer uso):
    {"url": "", "plataforma": "auto", "carpeta": "", "avisar_dias": 3}
"""
import json
import os
import re
import time

_BASE = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS")
_CFG = os.path.join(_BASE, "Prefs", "portal.json")
_ESTADO = os.path.join(_BASE, "Prefs", "portal_estado.json")
_MATERIAL = os.path.join(_BASE, "Campus")

AVISAR_DIAS = int(os.getenv("JARVIS_PORTAL_AVISO_DIAS", "3"))

# Cómo se reconoce cada plataforma en el HTML que sirve.
_HUELLAS = (
    ("moodle", r"moodle|/course/view\.php|M\.cfg"),
    ("canvas", r"canvas|instructure|/api/v1/courses"),
    ("blackboard", r"blackboard|/ultra/|bb-"),
    ("classroom", r"classroom\.google\.com"),
)


# ── configuración ───────────────────────────────────────────────────────────
def _cfg() -> dict:
    d = {"url": "", "plataforma": "auto", "carpeta": _MATERIAL,
         "avisar_dias": AVISAR_DIAS}
    try:
        with open(_CFG, encoding="utf-8") as f:
            d.update(json.load(f) or {})
    except Exception:
        pass
    return d


def _guardar_cfg(d: dict):
    try:
        os.makedirs(os.path.dirname(_CFG), exist_ok=True)
        with open(_CFG, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def configurar(url: str = "", plataforma: str = "") -> str:
    d = _cfg()
    if url:
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url.strip()
        d["url"] = url.rstrip("/")
    if plataforma:
        d["plataforma"] = plataforma.strip().lower()
    _guardar_cfg(d)
    if not d["url"]:
        return ("Dígame la dirección de su campus, señor: «configura mi portal "
                "en campus.universidad.es».")
    return (f"Apuntado, señor: su campus es {d['url']}"
            + (f" ({d['plataforma']})" if d["plataforma"] != "auto" else "")
            + ". La primera vez tendrá que entrar usted con su contraseña; "
              "después la sesión queda guardada y entro solo.")


def _estado_leer() -> dict:
    try:
        with open(_ESTADO, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _estado_guardar(d: dict):
    try:
        os.makedirs(os.path.dirname(_ESTADO), exist_ok=True)
        with open(_ESTADO, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── entrar ──────────────────────────────────────────────────────────────────
def _plataforma(nav, log=print) -> str:
    """Qué campus es. Se mira el HTML, no se cree lo que diga la configuración."""
    d = _cfg()
    if d.get("plataforma") and d["plataforma"] != "auto":
        return d["plataforma"]
    try:
        pista = (nav.url() + " " + nav.js("document.documentElement.outerHTML.slice(0,4000)"))
    except Exception:
        pista = nav.url()
    for nombre, patron in _HUELLAS:
        if re.search(patron, pista or "", re.I):
            return nombre
    return "general"


def _hay_sesion(nav) -> bool:
    """¿Estamos dentro?

    Mirar solo si hay un campo de contraseña no basta: la pantalla de acceso de
    Canvas no lo trae en el DOM inicial (lo monta después), así que daba
    «dentro» estando fuera. Se cruzan tres señales, y con cualquiera de ellas
    se considera que NO hay sesión, que es el lado seguro: como mucho se le
    pide al señor que entre una vez de más.
    """
    try:
        d = nav.js("""(() => {
          const p = [...document.querySelectorAll('input[type=password]')]
              .some(x => x.getClientRects().length > 0);
          const u = location.href.toLowerCase();
          const enRutaDeAcceso = /\\/(login|signin|sign_in|auth|sso|cas)\\b/.test(u);
          const formulario = [...document.querySelectorAll('form')]
              .some(f => /login|signin|sign_in|auth/i.test(f.action || ''));
          return {password: p, ruta: enRutaDeAcceso, formulario: formulario};
        })()""") or {}
    except Exception:
        return False
    return not (d.get("password") or d.get("ruta") or d.get("formulario"))


def entrar(log=print) -> dict:
    """Abre el campus y dice si hay sesión. NO escribe ninguna contraseña."""
    import navegador
    d = _cfg()
    if not d.get("url"):
        return {"ok": False, "mensaje": configurar()}

    nav = navegador.obtener(log=log)
    ok, motivo = nav.conectar()
    if not ok:
        return {"ok": False, "mensaje": f"No pude abrir el navegador, señor: {motivo}"}

    nav.abrir(d["url"])
    plataforma = _plataforma(nav, log=log)
    if not _hay_sesion(nav):
        return {"ok": False, "necesita_login": True, "plataforma": plataforma,
                "mensaje": ("Su campus pide la contraseña, señor. Yo no la "
                            "tecleo: entre usted en la ventana que acabo de "
                            "abrir y dígame «ya entré». La sesión se queda "
                            "guardada en mi perfil y a partir de ahí entro solo.")}

    estado = _estado_leer()
    estado["ultima_entrada"] = time.time()
    estado["plataforma"] = plataforma
    _estado_guardar(estado)
    return {"ok": True, "plataforma": plataforma, "nav": nav,
            "mensaje": f"Dentro del campus, señor ({plataforma})."}


# ── cursos y tareas ─────────────────────────────────────────────────────────
def _json_de(nav, patron: str, log=print):
    """El JSON de una petición que ya hizo la página, si encaja con el patrón."""
    try:
        crudo = nav.datos(patron, tope=120000)
    except Exception as e:
        log(f"[PORTAL] No pude leer la API ({patron}): {e}")
        return None
    if not crudo or "\n\n" not in crudo:
        return None
    cuerpo = crudo.split("\n\n", 1)[1]
    try:
        return json.loads(cuerpo)
    except Exception:
        return None


def _fecha(valor) -> float:
    """Fechas de Moodle (segundos) y de Canvas (ISO) a un mismo número."""
    if valor in (None, "", 0):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("Z", "+00:00")
    try:
        from datetime import datetime
        return datetime.fromisoformat(texto).timestamp()
    except Exception:
        return 0.0


def cursos(log=print) -> dict:
    """Las asignaturas del señor."""
    r = entrar(log=log)
    if not r.get("ok"):
        return r
    nav, plataforma = r["nav"], r["plataforma"]

    encontrados = []
    if plataforma == "canvas":
        nav.abrir(_cfg()["url"] + "/api/v1/courses?per_page=50")
        datos = _json_de(nav, "api/v1/courses", log=log)
        for c in (datos or []):
            if isinstance(c, dict) and c.get("name"):
                encontrados.append({"id": str(c.get("id")), "nombre": c["name"],
                                    "url": f"{_cfg()['url']}/courses/{c.get('id')}"})
    elif plataforma == "moodle":
        # Moodle pinta el panel con una llamada a lib/ajax/service.php.
        datos = _json_de(nav, "service.php", log=log)
        for bloque in (datos or []):
            cursos_bloque = (((bloque or {}).get("data") or {}).get("courses") or [])
            for c in cursos_bloque:
                if c.get("fullname"):
                    encontrados.append({"id": str(c.get("id")),
                                        "nombre": c["fullname"],
                                        "url": c.get("viewurl") or ""})

    if not encontrados:
        # Modo general: los enlaces que parecen una asignatura.
        try:
            crudo = nav.js("""(() => {
              const vistos = new Set(), salida = [];
              for (const a of document.querySelectorAll('a[href]')) {
                const t = (a.innerText || '').replace(/\\s+/g,' ').trim();
                const h = a.href;
                if (t.length < 4 || t.length > 90) continue;
                if (!/course|curso|asignatura|materia|subject|class/i.test(h + ' ' + t)) continue;
                if (vistos.has(t)) continue;
                vistos.add(t);
                salida.push({nombre: t, url: h});
              }
              return salida.slice(0, 40);
            })()""") or []
        except Exception:
            crudo = []
        encontrados = [{"id": "", "nombre": c["nombre"], "url": c["url"]}
                       for c in crudo]

    estado = _estado_leer()
    estado["cursos"] = encontrados
    _estado_guardar(estado)
    return {"ok": True, "plataforma": plataforma, "cursos": encontrados,
            "mensaje": (f"{len(encontrados)} asignaturas, señor."
                        if encontrados else
                        "No he sabido leer sus asignaturas de este campus, señor.")}


def tareas(log=print) -> dict:
    """Las entregas pendientes, con su fecha límite."""
    r = entrar(log=log)
    if not r.get("ok"):
        return r
    nav, plataforma = r["nav"], r["plataforma"]
    base = _cfg()["url"]
    pendientes = []

    if plataforma == "canvas":
        nav.abrir(f"{base}/api/v1/users/self/todo")
        for t in (_json_de(nav, "users/self/todo", log=log) or []):
            tarea = (t or {}).get("assignment") or {}
            if tarea.get("name"):
                pendientes.append({
                    "titulo": tarea["name"],
                    "curso": str(t.get("context_name") or ""),
                    "vence": _fecha(tarea.get("due_at")),
                    "url": tarea.get("html_url") or "",
                    "entregado": False})
    elif plataforma == "moodle":
        # El bloque «Línea de tiempo» del panel trae justo esto.
        nav.abrir(base + "/my/")
        for bloque in (_json_de(nav, "service.php", log=log) or []):
            eventos = (((bloque or {}).get("data") or {}).get("events") or [])
            for e in eventos:
                if not e.get("name"):
                    continue
                pendientes.append({
                    "titulo": e["name"],
                    "curso": ((e.get("course") or {}).get("fullname") or ""),
                    "vence": _fecha(e.get("timesort") or e.get("timestart")),
                    "url": e.get("url") or e.get("viewurl") or "",
                    "entregado": bool((e.get("action") or {}).get("actionable") is False)})

    if not pendientes:
        pendientes = _tareas_leyendo(nav, log=log)

    pendientes.sort(key=lambda t: t["vence"] or 9e18)
    estado = _estado_leer()
    estado["tareas"] = pendientes
    estado["ultima_revision"] = time.time()
    _estado_guardar(estado)
    return {"ok": True, "plataforma": plataforma, "tareas": pendientes,
            "mensaje": _parte(pendientes)}


def _tareas_leyendo(nav, log=print) -> list:
    """Modo general: mirar la página como la miraría el señor."""
    try:
        texto = nav.texto(3000)
    except Exception:
        return []
    salida = []
    # «Entregar antes del 12 de octubre», «Due Oct 12», «Vence 12/10».
    for linea in texto.split("\n"):
        if re.search(r"entrega|vence|due|l[ií]mite|plazo", linea, re.I):
            limpia = linea.strip()[:120]
            if len(limpia) > 12:
                salida.append({"titulo": limpia, "curso": "", "vence": 0.0,
                               "url": nav.url(), "entregado": False})
    return salida[:20]


def _parte(pendientes: list) -> str:
    if not pendientes:
        return "No veo ninguna entrega pendiente, señor."
    ahora = time.time()
    urgentes = [t for t in pendientes
                if t["vence"] and 0 < t["vence"] - ahora < 86400 * AVISAR_DIAS]
    lineas = []
    for t in pendientes[:10]:
        cuando = _cuando(t["vence"])
        curso = f" ({t['curso']})" if t.get("curso") else ""
        lineas.append(f"  · {t['titulo']}{curso} — {cuando}")
    cabeza = f"{len(pendientes)} entregas pendientes, señor."
    if urgentes:
        cabeza += f" {len(urgentes)} vencen en menos de {AVISAR_DIAS} días."
    return cabeza + "\n" + "\n".join(lineas)


def _cuando(marca: float) -> str:
    if not marca:
        return "sin fecha"
    faltan = marca - time.time()
    if faltan < 0:
        return "VENCIDA"
    dias = int(faltan // 86400)
    if dias == 0:
        return f"hoy, en {int(faltan // 3600)} horas"
    if dias == 1:
        return "mañana"
    return f"en {dias} días"


# ── material ────────────────────────────────────────────────────────────────
def material(curso: str = "", log=print) -> dict:
    """Baja los documentos del campus y los mete en el índice buscable.

    Lo importante no es bajarlos: es que después se puedan PREGUNTAR. Por eso
    acaba llamando al índice, que con el motor de significado encuentra un
    apunte aunque no use las mismas palabras que la pregunta.
    """
    r = entrar(log=log)
    if not r.get("ok"):
        return r
    nav = r["nav"]

    if curso:
        elegido = _buscar_curso(curso)
        if elegido and elegido.get("url"):
            nav.abrir(elegido["url"])

    try:
        enlaces = nav.js("""(() => {
          const ext = /\\.(pdf|docx?|pptx?|xlsx?|txt|md|zip)(\\?|$)/i;
          const vistos = new Set(), salida = [];
          for (const a of document.querySelectorAll('a[href]')) {
            const h = a.href;
            if (!ext.test(h) && !/resource|mod\\/resource|files\\//i.test(h)) continue;
            if (vistos.has(h)) continue;
            vistos.add(h);
            salida.push({url: h, texto: (a.innerText||'').replace(/\\s+/g,' ').trim().slice(0,80)});
          }
          return salida.slice(0, 40);
        })()""") or []
    except Exception as e:
        return {"ok": False, "mensaje": f"No pude leer los enlaces, señor: {e}"}

    if not enlaces:
        return {"ok": True, "bajados": 0,
                "mensaje": "No veo material descargable en esta página, señor."}

    bajados = 0
    for e in enlaces[:25]:
        try:
            nav.abrir(e["url"])
            bajados += 1
            time.sleep(0.4)
        except Exception as ex:
            log(f"[PORTAL] No pude bajar {e['texto'][:40]}: {ex}")

    # Lo descargado va a la carpeta del navegador; de ahí, al índice.
    indexado = ""
    try:
        import indice_documentos
        import navegador as _nav
        indexado = indice_documentos.indexar(
            [_nav.obtener(log=log).descargas], log=log, max_archivos=200)
    except Exception as ex:
        log(f"[PORTAL] No pude indexar lo bajado: {ex}")

    return {"ok": True, "bajados": bajados,
            "mensaje": (f"He bajado {bajados} documentos del campus, señor. "
                        + (indexado or "Quedan en la carpeta de descargas.")
                        + " Ya puede preguntarme por su contenido.")}


def _buscar_curso(nombre: str):
    pedido = (nombre or "").strip().lower()
    for c in (_estado_leer().get("cursos") or []):
        if pedido in (c.get("nombre") or "").lower():
            return c
    return None


# ── al calendario ───────────────────────────────────────────────────────────
def al_calendario(core=None, log=print) -> str:
    """Mete las entregas con fecha en el calendario del señor.

    Solo las que tienen fecha y no están entregadas, y no se repiten: la marca
    queda guardada, porque pasar dos veces llenaría la agenda de duplicados.
    """
    estado = _estado_leer()
    pendientes = estado.get("tareas") or []
    if not pendientes:
        r = tareas(log=log)
        if not r.get("ok"):
            return r.get("mensaje", "No pude leer sus entregas, señor.")
        pendientes = r["tareas"]

    try:
        from calendar_engine import CalendarEngine
        agenda = CalendarEngine()
    except Exception as e:
        return (f"No tengo el calendario conectado, señor ({e}). "
                "Ejecute «python autorizar_google.py» y lo repito.")

    ya = set(estado.get("agendadas") or [])
    puestas, fallos = 0, 0
    from datetime import datetime
    for t in pendientes:
        if not t.get("vence") or t.get("entregado"):
            continue
        firma = f"{t['titulo']}|{int(t['vence'])}"
        if firma in ya:
            continue
        try:
            cuando = datetime.fromtimestamp(t["vence"])
            agenda.crear_evento(
                summary=f"Entrega: {t['titulo']}",
                start_time=cuando,
                description=(f"Asignatura: {t.get('curso', '')}\n"
                             f"{t.get('url', '')}\n\nPuesto por JARVIS."))
            ya.add(firma)
            puestas += 1
        except Exception as e:
            fallos += 1
            log(f"[PORTAL] No pude agendar «{t['titulo'][:40]}»: {e}")

    estado["agendadas"] = sorted(ya)
    _estado_guardar(estado)
    if not puestas and not fallos:
        return "Sus entregas ya estaban todas en el calendario, señor."
    parte = f"He puesto {puestas} entregas en su calendario, señor."
    if fallos:
        parte += f" {fallos} no pude ponerlas; están en el registro."
    return parte


# ── borradores ──────────────────────────────────────────────────────────────
def borrador(core, tarea: str, log=print) -> str:
    """Prepara un borrador de una entrega. NO la envía.

    Lo escribe con lo que el campus dice del encargo y con lo que hay en los
    apuntes del señor sobre el tema, y lo deja en un archivo. Enviarlo es cosa
    suya: una entrega no se deshace.
    """
    pedido = (tarea or "").strip()
    if not pedido:
        return "¿De qué entrega, señor?"

    estado = _estado_leer()
    encontrada = None
    for t in (estado.get("tareas") or []):
        if pedido.lower() in (t.get("titulo") or "").lower():
            encontrada = t
            break

    enunciado = pedido
    if encontrada and encontrada.get("url"):
        try:
            import navegador
            nav = navegador.obtener(log=log)
            nav.conectar()
            nav.abrir(encontrada["url"])
            enunciado = f"{encontrada['titulo']}\n\n{nav.texto(2500)}"
        except Exception as e:
            log(f"[PORTAL] No pude leer el enunciado: {e}")

    # Lo que el señor ya tiene escrito sobre el tema pesa más que lo que el
    # modelo recuerde: se le pasa como material de partida.
    apuntes = ""
    try:
        import indice_documentos
        trozos = indice_documentos.buscar(pedido, k=4, log=log)
        apuntes = "\n\n".join(f"[{os.path.basename(r)}] {t[:700]}"
                              for r, t, _p in trozos)
    except Exception:
        pass

    try:
        from proveedor_claude import cliente as OpenAI, sin_pensamiento
        _n, url, modelo, clave = core._proveedores()[0]
        c = OpenAI(base_url=url, api_key=clave)
        r = c.chat.completions.create(
            model=modelo, temperature=0.4, max_tokens=2500,
            messages=[
                {"role": "system", "content":
                    "Eres un estudiante de ingeniería preparando un borrador de "
                    "entrega. Escribe en español, estructurado, con los cálculos "
                    "desarrollados si los hay. Si el enunciado pide algo que no "
                    "puedes saber (datos de laboratorio, mediciones propias), "
                    "DÉJALO MARCADO entre corchetes en vez de inventarlo. No "
                    "afirmes nada que no se siga del enunciado o de los apuntes."},
                {"role": "user", "content":
                    f"Encargo:\n{enunciado}\n\n"
                    + (f"Mis apuntes sobre el tema:\n{apuntes}\n\n" if apuntes else "")
                    + "Escribe el borrador."}])
        texto = sin_pensamiento(r.choices[0].message.content or "").strip()
    except Exception as e:
        return f"No pude redactar el borrador, señor: {e}"

    if not texto:
        return "El cerebro no devolvió nada, señor. Inténtelo otra vez."

    carpeta = os.path.join(_MATERIAL, "Borradores")
    os.makedirs(carpeta, exist_ok=True)
    nombre = re.sub(r"[^\w\s-]", "", pedido)[:50].strip().replace(" ", "_")
    ruta = os.path.join(carpeta, f"{nombre or 'borrador'}-{time.strftime('%Y%m%d')}.md")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(f"# Borrador: {pedido}\n\n"
                f"_Preparado por JARVIS el {time.strftime('%d/%m/%Y')}. "
                f"REVÍSELO ANTES DE ENTREGAR._\n\n{texto}\n")

    return (f"Borrador listo en {ruta}, señor.\n\n{texto[:600]}"
            + ("…" if len(texto) > 600 else "")
            + "\n\nNo lo he entregado: eso lo hace usted, y conviene que lo "
              "revise antes. Compruebe también qué dice su universidad sobre "
              "el uso de IA en las entregas.")


# ── resumen y estado ────────────────────────────────────────────────────────
def resumen(log=print) -> str:
    d = _cfg()
    if not d.get("url"):
        return ("No tengo configurado su campus, señor. Dígame «configura mi "
                "portal en campus.universidad.es».")
    estado = _estado_leer()
    pendientes = estado.get("tareas") or []
    cuando = estado.get("ultima_revision")
    parte = [f"Campus: {d['url']} ({estado.get('plataforma', 'sin detectar')})."]
    if cuando:
        horas = (time.time() - cuando) / 3600
        parte.append(f"Última revisión hace {horas:.0f} horas.")
    parte.append(f"{len(estado.get('cursos') or [])} asignaturas conocidas.")
    parte.append(_parte(pendientes))
    return "\n".join(parte)


def urgentes(dias: int = None, log=print) -> list:
    """Entregas que vencen pronto. Lo que consulta el motor proactivo."""
    dias = dias if dias is not None else _cfg().get("avisar_dias", AVISAR_DIAS)
    ahora = time.time()
    return [t for t in (_estado_leer().get("tareas") or [])
            if t.get("vence") and not t.get("entregado")
            and 0 < t["vence"] - ahora < 86400 * dias]


def resumen_estado() -> dict:
    d = _cfg()
    estado = _estado_leer()
    return {"configurado": bool(d.get("url")), "url": d.get("url", ""),
            "plataforma": estado.get("plataforma", ""),
            "cursos": len(estado.get("cursos") or []),
            "tareas": len(estado.get("tareas") or []),
            "urgentes": len(urgentes())}


if __name__ == "__main__":
    try:
        import consola_utf8  # noqa: F401
    except Exception:
        pass
    print(resumen())
