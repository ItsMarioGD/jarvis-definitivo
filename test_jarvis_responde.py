#!/usr/bin/env python3
"""
test_jarvis_responde.py - Garantia de que JARVIS SIEMPRE contesta.

Ejecuta:  python test_jarvis_responde.py

No comprueba que la respuesta sea buena (eso depende del LLM), sino que
NUNCA se queda mudo: pase lo que pase con las habilidades, el LLM, la
memoria o la voz, process_text_stream() devuelve un texto util.

Cada prueba reproduce un fallo que en su dia dejo a JARVIS sin responder.
"""
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
os.environ.setdefault("JARVIS_DB_DIR", os.path.join(tempfile.gettempdir(), "jarvis_test_db"))

fallos = []


def comprobar(nombre, fn):
    try:
        fn()
        print(f"  [OK]  {nombre}")
    except AssertionError as e:
        fallos.append(f"{nombre}: {e}")
        print(f"  [MAL] {nombre}: {e}")
    except Exception as e:
        fallos.append(f"{nombre}: {type(e).__name__}: {e}")
        print(f"  [MAL] {nombre}: {type(e).__name__}: {e}")


def es_respuesta(r):
    assert isinstance(r, str), f"devolvio {type(r).__name__}, no un str"
    assert r.strip(), "devolvio una cadena vacia"
    return r


def main():
    import jarvis_core
    print("Modo degradado, falta:", jarvis_core.FALTANTES or "nada")

    print("\n=== ARRANQUE ===")
    core = jarvis_core.JarvisCore(log_callback=lambda m: None)

    def cola_tts():
        # Estaba tras el return de la property signal_processor: codigo muerto.
        assert hasattr(core, "tts_queue"), "no existe tts_queue"
        assert hasattr(core, "tts_thread"), "no existe tts_thread"
        assert core.tts_thread.is_alive(), "el worker de TTS no arranco"
    comprobar("la cola de voz existe y su worker corre", cola_tts)

    def memoria_absoluta():
        assert os.path.isabs(core.db_path), f"ruta relativa: {core.db_path}"
        assert os.path.exists(core.db_path), "la base no se creo"
    comprobar("la memoria usa una ruta absoluta", memoria_absoluta)

    print("\n=== SIEMPRE RESPONDE ===")
    comprobar("pregunta normal",
              lambda: es_respuesta(core.process_text_stream("Hola, que tal", speak_server=False)))
    comprobar("texto vacio",
              lambda: es_respuesta(core.process_text_stream("", speak_server=False)))
    comprobar("solo espacios",
              lambda: es_respuesta(core.process_text_stream("   \n\t ", speak_server=False)))
    comprobar("None como entrada",
              lambda: es_respuesta(core.process_text_stream(None, speak_server=False)))
    comprobar("texto de 20.000 caracteres",
              lambda: es_respuesta(core.process_text_stream("hola " * 4000, speak_server=False)))
    comprobar("emojis y acentos",
              lambda: es_respuesta(core.process_text_stream("¿Qué tal, señor? 🚀ñÑ", speak_server=False)))
    comprobar("consulta compuesta (se parte en dos)",
              lambda: es_respuesta(core.process_text_stream("apaga la luz y dame el clima", speak_server=False)))

    print("\n=== SOBREVIVE A FALLOS INTERNOS ===")

    class Explosivo:
        def handle(self, _):
            raise RuntimeError("habilidad rota a proposito")

    def skill_rota():
        original = core.skills
        core.skills = Explosivo()
        try:
            es_respuesta(core.process_text_stream("dame el clima", speak_server=False))
        finally:
            core.skills = original
    comprobar("una habilidad que lanza excepcion", skill_rota)

    def sin_skills():
        original = core.skills
        core.skills = None
        try:
            es_respuesta(core.process_text_stream("hola", speak_server=False))
        finally:
            core.skills = original
    comprobar("sin habilidades (skills = None)", sin_skills)

    def pc_roto():
        original = getattr(core, "pc", None)
        core.pc = Explosivo()
        try:
            es_respuesta(core.process_text_stream("abre el bloc de notas", speak_server=False))
        finally:
            core.pc = original
    comprobar("el control del PC lanza excepcion", pc_roto)

    def nucleo_roto():
        original = core._procesar
        core._procesar = lambda *a, **k: (_ for _ in ()).throw(ValueError("nucleo roto"))
        try:
            r = es_respuesta(core.process_text_stream("hola", speak_server=False))
            assert "ValueError" in r or "fallado" in r.lower(), f"no explica el fallo: {r}"
        finally:
            core._procesar = original
    comprobar("_procesar entero revienta", nucleo_roto)

    def devuelve_none():
        original = core._procesar
        core._procesar = lambda *a, **k: None
        try:
            es_respuesta(core.process_text_stream("hola", speak_server=False))
        finally:
            core._procesar = original
    comprobar("_procesar devuelve None", devuelve_none)

    def memoria_rota():
        original = core.save_to_memory
        core.save_to_memory = lambda *a, **k: (_ for _ in ()).throw(IOError("disco lleno"))
        try:
            es_respuesta(core.process_text_stream("hola", speak_server=False))
        finally:
            core.save_to_memory = original
    comprobar("la memoria falla al guardar", memoria_rota)

    print("\n=== RESUMEN ===")
    if fallos:
        for f in fallos:
            print("  - " + f)
        print(f"\n{len(fallos)} prueba(s) fallaron: JARVIS puede quedarse mudo.")
        return 1
    print("  JARVIS responde en todos los escenarios probados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
