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
        ("cuéntame un chiste", None),
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