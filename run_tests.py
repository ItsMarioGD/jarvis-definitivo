#!/usr/bin/env python3
"""
run_tests.py - Batería de pruebas de Jarvis (fase de perfeccionamiento)
Cobertura: habilidades (variantes de lenguaje), memoria, MCP, endpoints HTTP,
robustez y generador universal. Reporte PASS/FAIL con conteo final.
"""
import sys, os, json, time, urllib.request, urllib.error, io, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE = "http://127.0.0.1:5000"

PASS = 0
FAIL = 0
FAILS = []


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS | {name}")
    else:
        FAIL += 1
        FAILS.append(name)
        print(f"  FAIL | {name} {extra}")


def http(path, obj=None, method="POST", timeout=120):
    if obj is not None:
        data = json.dumps(obj).encode()
        req = urllib.request.Request(BASE + path, data=data,
                                     headers={"Content-Type": "application/json"}, method=method)
    else:
        req = urllib.request.Request(BASE + path, method=method)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"error": f"HTTP {e.code}"}


# ══════════════ 1. HABILIDADES (variantes de lenguaje natural) ══════════════
def test_skills():
    from jarvis_skills import SkillsManager
    sm = SkillsManager(safe=True)
    SKILL_TESTS = [
        # (frase, habilidad esperada)
        ("abre la calculadora", "abrir"),
        ("abre chrome", "abrir"),
        ("abre el explorador", "abrir"),
        ("abreme spotify", "abrir"),
        ("inicia youtube", "abrir"),
        ("ejecuta el notepad", "abrir"),
        ("pon la calculadora", "abrir"),
        ("cierra chrome", "cerrar"),
        ("cierra el notepad", "cerrar"),
        ("termina spotify", "cerrar"),
        ("sube el volumen", "volumen"),
        ("sube el volumen un poco", "volumen"),
        ("baja el volumen", "volumen"),
        ("volumen al 50%", "volumen"),
        ("muta el audio", "mutar"),
        ("desmuta el audio", "mutar"),
        ("qué hora es", "hora"),
        ("dime la hora", "hora"),
        ("qué día es hoy", "fecha"),
        ("a qué día estamos", "fecha"),
        ("clima en madrid", "clima"),
        ("qué tiempo hace en londres", "clima"),
        ("crea una nota: comprar pan", "nota"),
        ("anota llamar al banco", "nota"),
        ("muestra mis notas", "nota"),
        ("temporizador de 30 segundos", "temporizador"),
        ("temporiza 2 minutos", "temporizador"),
        ("alarma a las 8:30", "alarma"),
        ("pon una alarma a las 7:45", "alarma"),
        ("recuérdame que pagar la luz a las 20:00", "recordatorio"),
        ("captura de pantalla", "captura"),
        ("toma un pantallazo", "captura"),
        ("copia 1234 al portapapeles", "portapapeles"),
        ("busca recetas de paella", "buscar"),
        ("googlea inteligencia artificial", "buscar"),
        ("batería", "bateria"),
        ("cuánta batería queda", "bateria"),
        ("bloquea el pc", "bloquear"),
        ("apaga el pc", "apagar"),
        ("reinicia el equipo", "reiniciar"),
        ("cuánto es 2+2", "calculadora"),
        ("cuánto es 5 mas 3", "calculadora"),
        # NO debe matchear (conversación normal → LLM)
        ("hola jarvis, ¿cómo estás?", None),
        ("genera una imagen de un gato", None),
        # Desde que existe la habilidad _chiste, esta frase SI la atiende una
        # habilidad. La expectativa antigua (mandarla al LLM) llevaba meses
        # marcando un fallo que no lo era.
        ("cuéntame un chiste", "chiste"),
        ("escribe un poema de amor", None),
    ]
    print("\n== 1. HABILIDADES (variantes de lenguaje) ==")
    for frase, esperado in SKILL_TESTS:
        r = sm.handle(frase)
        got = "ninguna" if r is None else "habilidad"
        if esperado is None:
            ok(f"no-habilidad: {frase[:45]}", r is None, f"(match inesperado: {got})")
        else:
            ok(f"{esperado}: {frase[:45]}", r is not None, f"(sin match)")


# ══════════════ 2. MEMORIA ══════════════
def test_memory():
    print("\n== 2. MEMORIA ==")
    from jarvis_core import JarvisCore
    core = JarvisCore()
    r = core.remember_from("mi nombre es Prueba Tester")
    ok("aprende nombre", r is not None and "Prueba Tester" in r)
    r = core.remember_from("me gusta el te verde")
    ok("aprende gusto", r is not None and "te verde" in r)
    r = core.remember_from("recuerda que debo comprar tinta")
    ok("aprende recuerdo", r is not None and "tinta" in r)
    ctx = core.get_prefs_context()
    ok("prefs en contexto", "Prueba Tester" in ctx and "te verde" in ctx)
    core.add_reminder("test rem 1", "23:59")
    ctx = core.get_reminders_context()
    ok("recordatorio en contexto", "test rem 1" in ctx)
    core.mark_reminder_done("test rem 1")
    ctx = core.get_reminders_context()
    ok("recordatorio marcado hecho", "test rem 1" not in ctx)
    core.shutdown()


# ══════════════ 3. MCP SERVER ══════════════
def test_mcp():
    print("\n== 3. MCP SERVER (HTTP :5001) ==")
    try:
        d = json.loads(urllib.request.urlopen("http://127.0.0.1:5001/health", timeout=5).read().decode())
        ok("health mcp", d.get("status") == "ok")
    except Exception as e:
        ok("health mcp", False, str(e))
    try:
        d = json.loads(urllib.request.urlopen("http://127.0.0.1:5001/tools", timeout=5).read().decode())
        tools = d.get("tools", [])
        ok("tools mcp", len(tools) == 5, f"({len(tools)} herramientas)")
    except Exception as e:
        ok("tools mcp", False, str(e))
    try:
        r = http_mcp({"tool": "ejecutar_habilidad", "arguments": {"texto": "que hora es"}})
        ok("mcp skill", "exactamente" in r.get("result", "").lower(), f"({r.get('result', '')[:60]})")
    except Exception as e:
        ok("mcp skill", False, str(e))


def http_mcp(obj, timeout=30):
    data = json.dumps(obj).encode()
    req = urllib.request.Request("http://127.0.0.1:5001/call", data=data,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())


# ══════════════ 4. ENDPOINTS HTTP ══════════════
def test_http():
    print("\n== 4. ENDPOINTS HTTP ==")
    ok("health", http("/health", method="GET").get("status") == "ok")
    ok("greet", "señor" in http("/greet", method="GET").get("response", "").lower())
    ok("farewell", "señor" in http("/farewell", method="GET").get("response", "").lower())
    ok("set_mode sleep", http("/set_mode/sleep", method="GET").get("mode") == "sleep")
    ok("set_mode focus", http("/set_mode/focus", method="GET").get("mode") == "focus")
    ok("set_mode normal", http("/set_mode/normal", method="GET").get("mode") == "normal")
    ok("set_mode invalido", http("/set_mode/xyz", method="GET").get("error") is not None)
    ok("tts", http("/tts", {"text": "prueba de voz"}) .get("status") == "ok")
    ok("tts_stop", http("/tts_stop").get("status") == "stopped")
    ok("tts texto vacio", http("/tts", {"text": ""}).get("error") is not None)
    s = http("/stats", method="GET")
    ok("stats cpu", s.get("cpu") != "--")
    ok("stats cores", len(s.get("cpu_cores", [])) > 0, f"({len(s.get('cpu_cores', []))})")
    ok("stats ram", s.get("ram") != "--" and s.get("ram_total") != "--")
    ok("stats uptime", s.get("uptime", 0) > 0)
    ok("stats bateria", s.get("battery") is not None)


# ══════════════ 5. ROBUSTEZ ══════════════
def test_robustez():
    print("\n== 5. ROBUSTEZ ==")
    r = http("/process_text", {"text": ""})
    ok("texto vacio", r.get("response") is not None and len(r.get("response", "")) > 0,
       f"({r.get('response', '')[:40]})")
    r = http("/process_text", {"text": "😀😀😀 emoji test"})
    ok("emojis", r.get("response") is not None)
    r = http("/process_text", {"text": "x" * 1500}, timeout=180)
    ok("texto largo 1500", len(r.get("response", "")) > 0, f"({r.get('response','')[:40]})")
    t0 = time.time()
    r = http("/process_text", {"text": "abre la calculadora"})
    dt = time.time() - t0
    ok("skill rapida (<2s)", dt < 2, f"({dt:.2f}s)")


# ══════════════ 6. GENERADOR UNIVERSAL ══════════════
def test_generator():
    print("\n== 6. GENERADOR UNIVERSAL ==")
    casos = [
        ("generar imagen: ciudad futurista", "image"),
        ("generar modelo 3d: cubo de metal", "3d_model"),
        ("generar documento: contrato de alquiler", "document"),
        ("generar diagrama: arquitectura de red", "diagram"),
        ("generar plano: casa de dos pisos", "blueprint"),
        ("generar codigo: calculadora en python", "code"),
        ("generar plan: plan semanal de ejercicio", "plan"),
        ("generar excel: inventario de productos", "excel"),
        ("generar word: carta formal", "word"),
        ("generar powerpoint: presentacion de ventas", "pptx"),
        ("generar musica: melodia relajante", "audio"),
    ]
    for prompt, tipo in casos:
        try:
            d = http("/generate", {"prompt": prompt})
            if d.get("error"):
                ok(f"gen {tipo}", False, f"(error: {d['error']})")
                continue
            ruta = d.get("path", "")
            existe = os.path.exists(ruta) if ruta else False
            ok(f"gen {tipo}", d.get("type") == tipo and existe and d.get("size", 0) > 0,
               f"({d.get('type')}, size={d.get('size', 0)})")
        except Exception as e:
            ok(f"gen {tipo}", False, str(e)[:60])


def test_modulos_nuevos():
    """Harness ampliado: ficheros, permisos, presupuesto, relación, git,
    paralingüística temporal, MCP genérico, pre-vuelo del móvil. Sin red."""
    print("\n== 7. MÓDULOS NUEVOS DEL HARNESS ==")
    import tempfile, importlib

    # herramientas_fs: escribir/editar/leer + raíces vetadas
    try:
        import herramientas_fs as fs
        d = tempfile.mkdtemp(dir=os.path.expanduser("~"))
        p = os.path.join(d, "t.txt")
        fs.escribir_archivo(p, "uno\ndos\n")
        fs.editar_archivo(p, "dos", "DOS")
        cont = open(p, encoding="utf-8").read()
        ok("fs: escribir+editar", cont == "uno\nDOS\n", f"({cont!r})")
        ok("fs: veta credenciales",
           "protegido" in fs.escribir_archivo(os.path.expanduser("~/.env"), "x"))
        ok("fs: veta fuera de raíz",
           "permitidas" in fs.leer_archivo("C:/Windows/system.ini"))
        import shutil; shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        ok("fs: módulo", False, str(e)[:80])

    # permisos: políticas y afirmaciones
    try:
        import permisos
        ok("permisos: lectura=directo", permisos.evaluar("leer_archivo") == "directo")
        ok("permisos: escritura=confirmar", permisos.evaluar("escribir_archivo") == "confirmar")
        ok("permisos: afirmación", permisos.es_afirmacion("venga, confirma")
           and not permisos.es_afirmacion("mejor no"))
    except Exception as e:
        ok("permisos: módulo", False, str(e)[:80])

    # presupuesto: corte por tope
    try:
        os.environ["JARVIS_PRESUPUESTO_USD"] = "0.01"
        import presupuesto; importlib.reload(presupuesto)
        presupuesto.reiniciar()
        ok("presupuesto: parte sin exceder", presupuesto.permite_nube())
        presupuesto.registrar_uso("openai", "gpt-4o", 100000, 100000)
        ok("presupuesto: corta al pasarse", not presupuesto.permite_nube())
        presupuesto.reiniciar()
        os.environ.pop("JARVIS_PRESUPUESTO_USD", None)
    except Exception as e:
        ok("presupuesto: módulo", False, str(e)[:80])

    # relación: niveles por umbral
    try:
        import relacion
        class _C:
            def __init__(s): s.d = {}
            def get_pref(s, k): return s.d.get(k)
            def set_pref(s, k, v): s.d[k] = v
            log = staticmethod(lambda *a: None)
        c = _C()
        for _ in range(3):
            relacion.registrar_interaccion(c, "hola")
        ok("relación: arranca en conocimiento", relacion.nivel(c)[1] == "conocimiento")
        c.d["rel_interacciones"] = "700"; c.d["rel_desde"] = "2023-01-01"
        ok("relación: veterano llega a asesor", relacion.nivel(c)[0] == 4)
    except Exception as e:
        ok("relación: módulo", False, str(e)[:80])

    # git_tools: estado sobre este mismo repo
    try:
        import git_tools
        est = git_tools.git_estado(".", log=lambda *a: None)
        ok("git: lee su propio repo", "Rama:" in est)
        ok("git: rechaza no-repo",
           "no es un repositorio" in git_tools.git_estado("C:/Windows", log=lambda *a: None))
    except Exception as e:
        ok("git: módulo", False, str(e)[:80])

    # paralingüística temporal: mezcla con prior
    try:
        from cognition import paralinguistica_patron as plp
        plp._ARCHIVO = os.path.join(tempfile.gettempdir(), "plp_test.json")
        plp._cache = {"muestras": [], "correcciones": {}}
        for _ in range(10):
            m = plp.mezclar(0.9, 0.1, 0.5, 0.0, 0.4, log=lambda *a: None)
        ok("paraling: aplica patrón tras N muestras", m.get("patron") is True)
        try: os.remove(plp._ARCHIVO)
        except OSError: pass
    except Exception as e:
        ok("paraling: módulo", False, str(e)[:80])

    # mcp_generico: degrada sin servidores
    try:
        import mcp_generico
        ok("mcp: descubre sin reventar",
           isinstance(mcp_generico.descubrir(log=lambda *a: None), list))
    except Exception as e:
        ok("mcp: módulo", False, str(e)[:80])

    # sandbox_android: sin dispositivo pide confirmación
    try:
        import sandbox_android
        r = sandbox_android.informe("abrir ajustes", texto="Ajustes", log=lambda *a: None)
        ok("móvil: sin dispositivo pide confirmar", "confirme" in r or "confianza" in r)
    except Exception as e:
        ok("móvil: módulo", False, str(e)[:80])

    # correo_gmail: degrada sin credenciales
    try:
        import correo_gmail
        ok("correo: degrada sin token",
           "autorizar_google" in correo_gmail.resumen(log=lambda *a: None))
    except Exception as e:
        ok("correo: módulo", False, str(e)[:80])

    # memoria_grafo: recall, episódico, entidad
    try:
        import memoria_grafo as MG
        MG._DB = os.path.join(tempfile.gettempdir(), "mem_unica_test.db")
        try: os.remove(MG._DB)
        except OSError: pass
        MG._conn = None
        MG.recordar("al señor le gusta el café solo", tipo="preferencia",
                    sujeto="señor", entidades=["café"])
        MG.recordar("ayer estuve con el bug de audio", tipo="nota",
                    ts=time.time() - 86400)
        ok("memoria: recall temático",
           any("café" in h["texto"] for h in MG.recall("café mañana")))
        ok("memoria: episódico de ayer",
           any("audio" in h["texto"] for h in MG.episodico("ayer")))
        ok("memoria: entidad", MG.entidad("café").get("entidad", {}).get("nombre") == "café")
        ok("memoria: contexto no vacío", bool(MG.contexto("qué hice ayer con el audio")))
        MG._conn.close(); MG._conn = None
        try: os.remove(MG._DB)
        except OSError: pass
    except Exception as e:
        ok("memoria: módulo", False, str(e)[:80])

    # permisos incluye las tools de los slices drásticos
    try:
        import permisos
        ok("permisos: buscar_en_memoria es lectura",
           permisos.evaluar("buscar_en_memoria") == "directo")
    except Exception as e:
        ok("permisos drásticos: módulo", False, str(e)[:80])

    # modelado3d: encuentra Blender y construye desde una receta
    try:
        import modelado3d as M3D, tempfile as _tf, json as _j, glob as _g
        ok("3d: encuentra Blender", M3D.disponible(),
           "(pon BLENDER_EXE si lo tienes en otra ruta)")
        if M3D.disponible():
            _d = _tf.mkdtemp()
            _rp = os.path.join(_d, "receta.json")
            _j.dump({"nombre": "t", "piezas": [{"forma": "esfera", "pos": [0, 0, 0],
                     "escala": [0.3, 0.3, 0.3], "rot_grados": [0, 0, 0],
                     "color": [0.6, 0.6, 0.7], "metal": 0.1, "rugosidad": 0.5}]},
                    open(_rp, "w"))
            _r = M3D._run_blender(M3D._SB_CONSTRUIR, [_rp, "", _d], timeout=400,
                                  log=lambda *a: None)
            ok("3d: Blender construye y exporta",
               _r["ok"] and os.path.isfile(os.path.join(_d, "modelo.glb")),
               _r.get("error", "")[:80])
            ok("3d: render de la foto hero",
               os.path.isfile(os.path.join(_d, "modelo_hero.png")))
            ok("3d: genera visor holográfico HTML",
               os.path.isfile(M3D._holo_web(os.path.join(_d, "modelo.glb"),
                                            os.path.join(_d, "h.html"), "t")))
    except Exception as e:
        ok("3d: módulo", False, str(e)[:120])


def main():
    t0 = time.time()
    print("=" * 60)
    print("BATERÍA DE PRUEBAS JARVIS")
    print("=" * 60)
    try:
        test_skills()
        test_memory()
        test_mcp()
        test_http()
        test_robustez()
        test_generator()
        test_modulos_nuevos()
    except Exception as e:
        print(f"\n!! Error global en las pruebas: {e}")
        import traceback
        traceback.print_exc()
    dt = time.time() - t0
    print("=" * 60)
    print(f"RESULTADO: {PASS} PASS | {FAIL} FAIL | {dt:.1f}s")
    if FAILS:
        print("Fallos:")
        for f in FAILS:
            print(f"  - {f}")
    print("=" * 60)
    # Salida forzada: los timers/hilos de pruebas no deben colgar la suite
    os._exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()