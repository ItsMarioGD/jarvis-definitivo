#!/usr/bin/env python3
"""
test_regresion.py - Red de seguridad de JARVIS/ULTRON
=====================================================
Por que existe: SkillsManager despacha 360 handlers recorriendo una lista en
orden y quedandose con el primero que devuelve algo. Cada habilidad nueva puede
robarle frases a una vieja sin que nadie lo note, porque no habia ninguna prueba
que fijara «esta frase la atiende ESTE handler». Aqui se fija.

Cubre ademas los fallos que ya nos mordieron una vez:
  * el apagado que solo obedecia la primera vez (Windows error 1190),
  * el detector de eco que se tragaba «cancela el apagado»,
  * las ordenes que decian «hecho» sin comprobar el codigo de salida.

Uso:
    python test_regresion.py          (no necesita pytest)
    pytest test_regresion.py          (tambien funciona)

Todo corre en modo seguro o con dobles: ninguna prueba apaga el equipo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_FALLOS = []


def _check(condicion, descripcion, detalle=""):
    if condicion:
        print(f"  PASS | {descripcion}")
    else:
        print(f"  FAIL | {descripcion} {detalle}")
        _FALLOS.append(descripcion)
    return bool(condicion)


# ── 1. Ejecutor: los errores dejan de ser invisibles ────────────────────────
def test_ejecutor_detecta_fallos():
    print("\n== 1. EJECUTOR ==")
    import ejecutor
    ok = ejecutor.ejecutar("echo hola", origen="test", orden="test")
    _check(ok["ok"] and "hola" in ok["salida"], "comando correcto devuelve ok=True")

    mal = ejecutor.ejecutar("exit 7", origen="test", orden="test")
    _check(not mal["ok"] and mal["codigo"] == 7,
           "codigo de salida distinto de cero se reporta", f"-> {mal}")
    _check(bool(mal["error"]), "un fallo trae mensaje de error para decirlo en voz alta")

    arranco, error, _ = ejecutor.lanzar("cmd /c exit 4", origen="test", orden="test",
                                        verificar_ms=250)
    _check(not arranco and "4" in error,
           "lanzar() detecta el proceso que muere al instante", f"-> {error}")


# ── 2. Energia: el apagado obedece siempre, no solo la primera vez ──────────
def test_energia_obedece_siempre():
    print("\n== 2. ENERGIA (apagado repetido) ==")
    import energia

    llamadas = []
    original = energia._ejecutar

    def _falso(args, timeout=20, orden=""):
        llamadas.append(list(args))
        # Simula Windows: el segundo /s seguido sin cancelar daria 1190.
        if args[0] == "/a":
            return {"ok": True, "salida": "", "error": "", "codigo": 0}
        previos = [c for c in llamadas[:-1] if c and c[0] in ("/s", "/r")]
        cancelado = any(c == ["/a"] for c in llamadas[-2:-1])
        if previos and not cancelado:
            return {"ok": False, "salida": "", "error": "ya programado", "codigo": 1190}
        return {"ok": True, "salida": "", "error": "", "codigo": 0}

    energia._ejecutar = _falso
    try:
        r1 = energia.apagar(30, "prueba")
        r2 = energia.apagar(30, "prueba")
        r3 = energia.apagar(30, "prueba")
        _check(r1[0] and r2[0] and r3[0],
               "tres apagados seguidos se aceptan los tres", f"-> {r1} {r2} {r3}")
        cancelaciones = [c for c in llamadas if c == ["/a"]]
        _check(len(cancelaciones) >= 3,
               "cada apagado anula antes el pendiente (shutdown /a)",
               f"-> {len(cancelaciones)} cancelaciones")
        _check(energia.reiniciar(30, "prueba")[0], "el reinicio usa el mismo camino")
    finally:
        energia._ejecutar = original


def test_energia_reporta_rechazo():
    print("\n== 3. ENERGIA (Windows rechaza) ==")
    import energia
    original = energia._ejecutar
    energia._ejecutar = lambda args, timeout=20, orden="": {
        "ok": False, "salida": "", "error": "Acceso denegado.(5)", "codigo": 5}
    try:
        ok, error = energia.apagar(30, "prueba")
        _check(not ok, "un rechazo de Windows NO se cuenta como exito")
        _check("denegado" in error.lower(), "el motivo real llega a quien llama", f"-> {error}")
    finally:
        energia._ejecutar = original


# ── 4. Skills: cada frase la atiende el handler correcto ────────────────────
_RUTAS = [
    ("apaga el pc", "_apagar"),
    ("apagate en 5 minutos", "_apagado_programado"),
    # Dos handlers saben cancelar (_apagado_programado va antes en la lista);
    # lo que importa es que la cancelacion la atienda uno de ellos.
    ("cancela el apagado", ("_cancela_apagado", "_apagado_programado")),
    ("reinicia el equipo", "_reiniciar"),
    ("bloquea el pc", "_bloquear"),
    ("abre la calculadora", "_abrir_app"),
    ("cierra el notepad", "_cerrar_app"),
    ("sube el volumen", "_volumen"),
    ("que hora es", "_hora_fecha"),
    ("captura de pantalla", "_captura"),
    ("cuanto es 2+2", "_calculadora"),
    ("bateria", "_bateria"),
]

_SIN_HABILIDAD = [
    "hola jarvis como estas",
    "escribe un poema de amor",
    "genera una imagen de un gato",
    "explicame la teoria de la relatividad",
]


def _handler_de(sm, frase):
    """Devuelve el nombre del handler que atendio la frase (o None)."""
    visto = []
    log_original = sm.log
    sm.log = lambda m: visto.append(str(m))
    try:
        respuesta = sm.handle(frase)
    finally:
        sm.log = log_original
    nombre = None
    for linea in visto:
        if "Habilidad ejecutada:" in linea:
            nombre = linea.split("Habilidad ejecutada:")[1].split("<-")[0].strip()
    return nombre, respuesta


def test_rutas_de_habilidades():
    print("\n== 4. RUTAS DE HABILIDADES ==")
    from jarvis_skills import SkillsManager
    sm = SkillsManager(log=lambda *a: None, safe=True)
    for frase, esperado in _RUTAS:
        handler, _ = _handler_de(sm, frase)
        validos = esperado if isinstance(esperado, tuple) else (esperado,)
        _check(handler in validos, f"«{frase}» -> {' o '.join(validos)}",
               f"(fue {handler})")


def test_conversacion_no_secuestrada():
    print("\n== 5. CONVERSACION LIBRE ==")
    from jarvis_skills import SkillsManager
    sm = SkillsManager(log=lambda *a: None, safe=True)
    for frase in _SIN_HABILIDAD:
        handler, respuesta = _handler_de(sm, frase)
        _check(respuesta is None, f"«{frase}» va al LLM", f"(la atrapo {handler})")


# ── 6. Detector de eco: no se traga las ordenes del señor ───────────────────
def test_detector_de_eco():
    print("\n== 6. DETECTOR DE ECO ==")
    from jarvis_core import JarvisCore

    class _Falso:
        pass

    falso = _Falso()
    falso._norm_eco = JarvisCore._norm_eco
    falso._tts_hist = ["Apagando el equipo en 30 segundos, señor. "
                       "Si cambia de idea, digame cancela el apagado."]
    falso._ORDENES_DIRECTAS = JarvisCore._ORDENES_DIRECTAS

    es_eco = lambda texto: JarvisCore._es_eco(falso, texto)
    _check(not es_eco("cancela el apagado"),
           "«cancela el apagado» NO se descarta aunque JARVIS acabe de decirlo")
    _check(not es_eco("apaga el pc"), "una orden repetida nunca es eco")
    _check(es_eco("si cambia de idea digame"), "el eco real sigue filtrandose")

    # Una frase corta que aparece de pasada en un párrafo largo mío ya no se
    # descarta: era la causa de que órdenes cortas desaparecieran sin traza.
    falso._tts_hist = ["He revisado su agenda y tiene tres citas hoy; la primera "
                       "es a las nueve con el equipo de compras, senor."]
    _check(not es_eco("tres citas hoy"),
           "una coincidencia corta dentro de un parrafo largo no es eco")
    falso._tts_hist = ["He revisado su agenda, senor."]
    _check(es_eco("he revisado su agenda senor"),
           "repetir casi entera mi frase si es eco")


# ── 7. Almacen: las acciones quedan registradas ─────────────────────────────
def test_registro_de_acciones():
    print("\n== 7. REGISTRO ==")
    import tempfile
    from storage import Storage
    ruta = os.path.join(tempfile.gettempdir(), "jarvis_test_audit.db")
    if os.path.exists(ruta):
        os.unlink(ruta)
    db = Storage(ruta=ruta, log=lambda *a: None)
    db.registrar_accion("test", "apaga el pc", "shutdown /s /t 30", False, "1190", 12)
    db.registrar_evento("intruso", "Rostro desconocido", "conf=0.9", "alta")
    fallos = db.acciones_recientes(10, solo_fallos=True)
    _check(len(fallos) == 1 and "1190" in fallos[0]["detalle"],
           "un fallo queda con su motivo consultable")
    _check(db.resumen(24)["fallos"] == 1, "el resumen cuenta los fallos")
    _check(len(db.eventos_recientes(10, tipo="intruso")) == 1,
           "los eventos se pueden filtrar por tipo")
    db.cerrar()


# ── 8. Cognicion: el hub existe y degrada sin romper ────────────────────────
def test_hub_cognitivo():
    print("\n== 8. HUB COGNITIVO ==")
    from cognition import CognitionHub
    hub = CognitionHub(log=lambda *a: None)
    res = hub.ejecutar("echo cognicion")
    _check(res["ok"] and "cognicion" in res["salida"],
           "el hub ejecuta comandos y lee el resultado")
    _check(hub.decisiones.evaluar("shutdown /s")["nivel"] == "alto",
           "el motor de riesgo clasifica el apagado como alto")
    _check(isinstance(hub.estado(), dict), "el hub informa de su estado")


# ── 9. Escucha continua: palabra de activación y ventana de gracia ──────────
def test_escucha_palabra_activacion():
    print("\n== 9. ESCUCHA CONTINUA ==")
    from jarvis_escucha import EscuchaContinua
    e = EscuchaContinua(core=None, log=lambda *a: None, palabras=("jarvis", "ultron"))

    _check(e._extraer_orden("jarvis apaga el pc") == "apaga el pc",
           "«jarvis apaga el pc» -> orden limpia")
    _check(e._extraer_orden("oye jarvis, que hora es") == "que hora es",
           "acepta «oye jarvis» y quita la coma")
    _check(e._extraer_orden("ultron ejecuta el comando dir") == "ejecuta el comando dir",
           "ULTRON responde a su propio nombre")
    _check(e._extraer_orden("jarvis") == "", "solo el nombre abre la ventana de gracia")
    _check(e._extraer_orden("apaga la tele") is None,
           "sin nombre y fuera de la ventana, no se ejecuta nada")

    import time as _t
    e._ultima_orden = _t.time()
    _check(e._extraer_orden("y ahora sube el volumen") == "y ahora sube el volumen",
           "dentro de la ventana de gracia no hay que repetir el nombre")
    e._ultima_orden = _t.time() - (e.gracia_s + 5)
    _check(e._extraer_orden("sube el volumen") is None,
           "pasada la ventana de gracia vuelve a hacer falta el nombre")


# ── 10. ULTRON: shell auditado y cadenas de órdenes ─────────────────────────
def test_arsenal_ultron():
    print("\n== 10. ARSENAL DE ULTRON ==")
    import ultron_skills

    ejecutadas = []

    class _CoreFalso:
        log = staticmethod(lambda *a: None)
        cognition = None

        def process_text_stream(self, t, speak_server=True):
            ejecutadas.append(t)
            return f"[ok: {t}]"

    us = ultron_skills.UltronSkills(_CoreFalso())

    r = us._shell("", "ejecuta el comando echo prueba")
    _check(r is not None and "prueba" in r, "el shell libre devuelve la salida real", f"-> {r}")

    r = us._cadena("", "abre la calculadora y luego dime la hora")
    _check(len(ejecutadas) == 2, "una cadena ejecuta las dos órdenes", f"-> {ejecutadas}")
    _check(r is not None and "Secuencia" in r, "la cadena resume lo hecho")

    ejecutadas.clear()
    _check(us._cadena("", "apaga el pc") is None,
           "una orden simple NO se trata como cadena")


# ── 11. Olvido: la memoria deja de crecer sin límite ────────────────────────
def test_olvido_del_grafo():
    print("\n== 11. OLVIDO ==")
    import jarvis_grafo
    antes = jarvis_grafo.estadisticas()
    r = jarvis_grafo.olvidar(dias=45)
    _check(isinstance(r, dict) and "nodos_borrados" in r,
           "olvidar() informa de lo que podó", f"-> {r}")
    _check(isinstance(antes, dict) and "nodos" in antes,
           "estadisticas() dice el tamaño del grafo", f"-> {antes}")


# ── 12. Guardián: los eventos quedan consultables ───────────────────────────
def test_historial_guardian():
    print("\n== 12. HISTORIAL DEL GUARDIÁN ==")
    import tempfile
    from storage import Storage
    ruta = os.path.join(tempfile.gettempdir(), "jarvis_test_guardian.db")
    if os.path.exists(ruta):
        os.unlink(ruta)
    db = Storage(ruta=ruta, log=lambda *a: None)
    db.registrar_evento("intruso", "Rostro no reconocido", "confianza=88", "alta",
                        agente="ULTRON")
    db.registrar_evento("presencia", "El señor está frente al equipo", "", "info",
                        agente="ULTRON")
    intrusos = db.eventos_recientes(10, tipo="intruso")
    _check(len(intrusos) == 1 and "88" in intrusos[0]["detalle"],
           "un intruso queda con fecha y confianza")
    _check(len(db.eventos_recientes(10, tipo="presencia")) == 1,
           "también se registra cuándo se vio al señor")
    db.cerrar()


# ── 13. Deshacer: las acciones dejan de ser definitivas ─────────────────────
def test_deshacer():
    print("\n== 13. DESHACER ==")
    import shutil
    import tempfile
    import deshacer

    tmp = tempfile.mkdtemp(prefix="undo_test_")
    origen = os.path.join(tmp, "a")
    destino = os.path.join(tmp, "b")
    os.makedirs(origen)
    os.makedirs(destino)
    ficheros = []
    for i in range(3):
        ruta = os.path.join(origen, f"doc{i}.pdf")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("x")
        ficheros.append(ruta)

    movimientos = []
    for ruta in ficheros:
        nuevo = os.path.join(destino, os.path.basename(ruta))
        shutil.move(ruta, nuevo)
        movimientos.append([ruta, nuevo])
    deshacer.anotar("mover_archivos", "prueba: moví 3 pdf",
                    {"movimientos": movimientos}, log=lambda *a: None)

    _check(len(os.listdir(origen)) == 0, "los archivos se movieron")
    texto = deshacer.deshacer_ultimo(1, log=lambda *a: None)
    _check(len(os.listdir(origen)) == 3 and len(os.listdir(destino)) == 0,
           "«deshaz eso» devuelve los archivos a su sitio", f"-> {texto}")
    # El almacén es el real y compartido, así que puede haber otras acciones
    # pendientes: lo que se comprueba es que ESTA ya no vuelve a aparecer.
    pendiente = deshacer.listar(limite=20, log=lambda *a: None)
    _check("prueba: moví 3 pdf" not in pendiente,
           "una acción ya deshecha desaparece de la lista de reversibles")
    shutil.rmtree(tmp, ignore_errors=True)


# ── 14. Vigilante: detecta y levanta lo que se cae ──────────────────────────
def test_vigilante():
    print("\n== 14. VIGILANTE ==")
    import queue
    import threading
    import time as _t
    from vigilante import Vigilante

    class _Nucleo:
        nombre_agente = "JARVIS"

        def __init__(self):
            self.tts_queue = queue.Queue()
            self.tts_thread = threading.Thread(target=lambda: None)
            self.tts_thread.start()
            self.proactivo = None
            self.escucha = None

        def _tts_worker(self):
            _t.sleep(3)

    nucleo = _Nucleo()
    nucleo.tts_thread.join()          # simula el hilo de voz muerto
    v = Vigilante(nucleo, log=lambda *a: None)
    parte = v.revisar()
    _check(parte.get("voz") == "caido", "detecta el hilo de voz muerto", f"-> {parte}")
    _check(nucleo.tts_thread.is_alive(), "lo levanta solo")
    _check(v.revisar().get("voz") == "ok", "en la siguiente ronda ya está sano")


# ── 15. Modo privado: cierra las salidas y sabe volver atrás ────────────────
def test_modo_privado():
    print("\n== 15. MODO PRIVADO ==")
    import privacidad

    prefs = {}

    class _Nucleo:
        nombre_agente = "JARVIS"
        log = staticmethod(lambda *a: None)
        base_url = "http://localhost:11434/v1"
        model = "qwen3:4b"
        api_key = "ollama"
        elevenlabs_key = "sk-secreta"

        def get_pref(self, k):
            return prefs.get(k)

        def set_pref(self, k, v):
            prefs[k] = v

        def _voz_piper_activa(self):
            return False

    nucleo = _Nucleo()
    nucleo._cerebro = {"proveedores": [
        {"nombre": "ollama", "url": "http://localhost:11434/v1", "modelo": "q", "clave": "x"},
        {"nombre": "nube", "url": "https://api.ejemplo.com/v1", "modelo": "g", "clave": "y"}]}

    salidas = [n for n, _q, _a in privacidad.auditar(nucleo)]
    _check("voz" in salidas, "detecta que la voz pasa por un servicio externo", f"-> {salidas}")
    _check(any("cerebro" in n for n in salidas), "detecta el proveedor de cerebro remoto")

    privacidad.activar(nucleo)
    _check(nucleo.elevenlabs_key == "", "el modo privado corta la voz en la nube")
    _check(len(nucleo._cerebro["proveedores"]) == 1, "deja solo el cerebro local")
    _check(prefs.get("stt_local") == "1", "fuerza el dictado local")

    privacidad.desactivar(nucleo)
    _check(nucleo.elevenlabs_key == "sk-secreta", "al desactivarlo restaura la clave")
    _check(len(nucleo._cerebro["proveedores"]) == 2, "y restaura los proveedores")


# ── 16. Herramientas del LLM ────────────────────────────────────────────────
def test_herramientas_llm():
    print("\n== 16. HERRAMIENTAS DEL CEREBRO ==")
    from herramientas_llm import Herramientas

    ejecutadas = []

    class _Skills:
        def handle(self, texto):
            ejecutadas.append(texto)
            return f"hecho: {texto}"

    class _Nucleo:
        log = staticmethod(lambda *a: None)
        skills = _Skills()
        pc = None
        msg = None
        conectores = None
        set_pref = staticmethod(lambda k, v: None)

    caja = Herramientas(_Nucleo(), log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    _check(len(nombres) >= 20, f"hay catálogo de herramientas ({len(nombres)})")
    _check("orden_libre" in nombres, "existe la salida de emergencia orden_libre")

    caja.ejecutar("abrir_app", {"nombre": "spotify"})
    _check(ejecutadas and "abre spotify" in ejecutadas[-1],
           "una herramienta se traduce a la frase que ya entienden las habilidades")

    caja.ejecutar("ajustar_volumen", {"nivel": 300})
    _check("100%" in ejecutadas[-1], "los parámetros fuera de rango se acotan",
           f"-> {ejecutadas[-1]}")

    respuesta = caja.ejecutar("no_existe", {})
    _check("No tengo ninguna herramienta" in respuesta,
           "una herramienta inventada por el modelo no rompe nada")


# ── 17. Detección de órdenes (cuándo merece la pena usar herramientas) ──────
def test_parece_orden():
    print("\n== 17. ¿ORDEN O CHARLA? ==")
    from jarvis_core import JarvisCore
    ordenes = ["organiza la carpeta de descargas y avisame",
               "necesito que muevas los pdf a documentos",
               "apaga el pc en diez minutos"]
    charla = ["buenos dias", "cuentame un chiste", "que opinas de la vida"]
    for frase in ordenes:
        _check(JarvisCore._parece_orden(frase), f"«{frase[:40]}» es orden")
    for frase in charla:
        _check(not JarvisCore._parece_orden(frase), f"«{frase[:40]}» es charla")


# ── 18. Encender y apagar: «desactiva X» contiene «activa X» ────────────────
def test_pares_activar_desactivar():
    print("\n== 18. ACTIVAR / DESACTIVAR ==")
    from jarvis_core import JarvisCore

    prefs = {"enjambre": "1", "avisos_proactivos": "1", "escucha_continua": "1",
             "modo_privado": "1"}
    c = JarvisCore.__new__(JarvisCore)
    c.log = lambda *a: None
    c.skills = c.cognition = c.enjambre = c.escucha = c.proactivo = c.nocturno = None
    c.nombre_agente = "JARVIS"
    c._estado_animo = {"ts": 0}
    c.get_pref = lambda k: prefs.get(k, "")
    c.set_pref = lambda k, v: prefs.__setitem__(k, v)
    c.elevenlabs_key = ""
    c._cerebro = {"proveedores": []}
    c._voz_piper_activa = lambda: True

    casos = [
        ("desactiva el enjambre", "detenido"),
        ("desactiva la escucha", "desactivada"),
        ("silencia los avisos", "silenciados"),
        ("desactiva el modo privado", "desactivado"),
    ]
    for orden, esperado in casos:
        r = str(c._ordenes_meta(orden) or "").lower()
        _check(esperado in r, f"«{orden}» apaga de verdad", f"-> {r[:60]}")


# ── 19. Buscar dentro de los documentos ─────────────────────────────────────
def test_indice_documentos():
    print("\n== 19. ÍNDICE DE DOCUMENTOS ==")
    import shutil
    import tempfile
    import indice_documentos as idx

    tmp = tempfile.mkdtemp(prefix="idx_test_")
    with open(os.path.join(tmp, "contrato.txt"), "w", encoding="utf-8") as f:
        f.write("La fianza sera de dos mensualidades y se devuelve en 30 dias.")
    with open(os.path.join(tmp, "apuntes.md"), "w", encoding="utf-8") as f:
        f.write("Un indice invertido mapea cada termino a sus documentos.")

    idx.indexar([tmp], log=lambda *a: None, con_vectores=False)
    fianza = idx.buscar("fianza", k=3, log=lambda *a: None)
    _check(any("contrato" in r for r, _t, _p in fianza),
           "encuentra por contenido, no por nombre de archivo")
    invertido = idx.buscar("indice invertido", k=3, log=lambda *a: None)
    _check(any("apuntes" in r for r, _t, _p in invertido),
           "distingue entre documentos distintos")
    _check(idx.estado(log=lambda *a: None)["archivos"] >= 2,
           "el estado del índice cuenta los archivos")
    shutil.rmtree(tmp, ignore_errors=True)


# ── 20. Identidad por voz ───────────────────────────────────────────────────
def test_identidad_por_voz():
    print("\n== 20. IDENTIDAD POR VOZ ==")
    import io as _io
    import wave
    import numpy as np
    import voz_identidad as vi

    def voz(frecuencias, semilla):
        rng = np.random.default_rng(semilla)
        sr, dur = 16000, 1.5
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        s = sum(np.sin(2 * np.pi * f * t) / (i + 1)
                for i, f in enumerate(frecuencias))
        s = s / np.max(np.abs(s)) * 0.6 + rng.normal(0, 0.02, t.shape)
        b = _io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((np.clip(s, -1, 1) * 32767).astype(np.int16).tobytes())
        return b.getvalue()

    original = vi.HUELLA
    vi.HUELLA = os.path.join(os.path.dirname(original), "huella_voz_test.json")
    try:
        vi.registrar([voz([120, 480, 1200], i) for i in range(3)], log=lambda *a: None)
        mismo, parecido_mismo = vi.verificar(voz([120, 480, 1200], 99), log=lambda *a: None)
        otro, parecido_otro = vi.verificar(voz([260, 900, 2400], 5), log=lambda *a: None)
        _check(mismo, "reconoce la voz registrada", f"-> {parecido_mismo}")
        _check(not otro, "rechaza una voz distinta", f"-> {parecido_otro}")
        _check(parecido_mismo > parecido_otro, "la voz propia se parece más que la ajena")
    finally:
        try:
            os.unlink(vi.HUELLA)
        except Exception:
            pass
        vi.HUELLA = original


# ── 21. Habilidades que se escribe él solo ──────────────────────────────────
def test_autoskills_valida():
    print("\n== 21. AUTO-PROGRAMACIÓN ==")
    import autoskills

    malos = [
        ("exec('x')\nclass A:\n patterns=['a']\n def handle(s,t,c): pass", "exec"),
        ("import subprocess\nclass A:\n patterns=['a']\n"
         " def handle(s,t,c): subprocess.run('dir')", "subprocess"),
        ("class A:\n patterns=['a']", "sin handle"),
        ("def roto(:", "sintaxis rota"),
    ]
    for codigo, que in malos:
        ok, _motivo = autoskills.validar(codigo)
        _check(not ok, f"rechaza código con {que}")

    bueno = ('import ejecutor\n\n\nclass Saludo:\n'
             '    patterns = [r"buenos dias jarvis"]\n'
             '    priority = 40\n    description = "saluda"\n\n'
             '    def handle(self, text, core):\n        return "Buenos dias."\n')
    ok, _motivo = autoskills.validar(bueno)
    _check(ok, "acepta una habilidad que cumple el contrato")


# ── 22. Registro de plugins (estaba muerto por falta de __init__) ───────────
def test_registro_plugins():
    print("\n== 22. PLUGINS MODULARES ==")
    from skills.plugins import get_plugin_registry
    registro = get_plugin_registry(log=lambda *a: None)
    _check(len(registro.catalogo()) >= 1,
           f"se cargan plugins ({len(registro.catalogo())})")
    _check(registro.handle("una frase que no reconoce nadie 12345", None) is None,
           "una frase sin patrón no la atiende ningún plugin")


# ── 23. Protocolo de relevo (nunca borra, y una señal lo cancela) ───────────
def test_relevo():
    print("\n== 23. PROTOCOLO DE RELEVO ==")
    import time as _t
    import relevo

    original = relevo.CONFIG
    relevo.CONFIG = os.path.join(os.path.dirname(original), "relevo_test.json")
    try:
        relevo.activar(dias=30, carpetas=[], contacto="prueba", log=lambda *a: None)
        _check(relevo.estado()["activo"], "el protocolo queda activo")
        _check(relevo.revisar(log=lambda *a: None) == "",
               "sin inactividad no hace nada")

        cfg = relevo._config()
        cfg["ultimo_latido"] = _t.time() - 35 * 86400
        relevo._guardar(cfg)
        aviso = relevo.revisar(log=lambda *a: None)
        _check("Aviso 1" in aviso, "a los 35 días manda el primer aviso", f"-> {aviso[:60]}")
        _check(not relevo.estado()["ejecutado"], "el primer aviso NO ejecuta nada")

        relevo.latido(log=lambda *a: None)
        _check(relevo.estado()["avisos_enviados"] == 0,
               "una sola señal del señor cancela el escalado")
    finally:
        try:
            os.unlink(relevo.CONFIG)
        except Exception:
            pass
        relevo.CONFIG = original


# ── 24. Recados: clasificar sin cerebro no rompe nada ───────────────────────
def test_recados():
    print("\n== 24. RECADOS ==")
    import recados

    original = recados.LIBRETA
    recados.LIBRETA = os.path.join(os.path.dirname(original), "recados_test.json")
    try:
        class _NucleoSinCerebro:
            tts_queue = None
            msg = None

            def get_pref(self, k):
                return "Mario"

            def _proveedores(self):
                raise RuntimeError("sin cerebro")

        r = recados.atender(_NucleoSinCerebro(), "Ana", "llámame cuando puedas",
                            canal="telegram", log=lambda *a: None, responder=False)
        _check(r["categoria"] == "NORMAL",
               "sin cerebro disponible, el recado se guarda como NORMAL")
        _check("Ana" in recados.resumen(), "el resumen nombra a quien escribió")
    finally:
        try:
            os.unlink(recados.LIBRETA)
        except Exception:
            pass
        recados.LIBRETA = original


# ── 25. Ensayo antes de actuar ──────────────────────────────────────────────
def test_sandbox():
    print("\n== 25. ENSAYO ==")
    import sandbox
    _check(sandbox.disponible()["ensayo_seco"], "siempre hay ensayo en seco")
    texto = sandbox.ensayar_orden("apaga el pc en 10 minutos", log=lambda *a: None)
    _check("modo seguro" in texto or "haría" in texto,
           "el ensayo dice qué pasaría sin ejecutarlo", f"-> {texto[:70]}")
    impacto = sandbox.impacto_archivos("mueve todos los pdf de descargas a documentos",
                                       log=lambda *a: None)
    _check(impacto["reconocida"], "reconoce una orden de mover en lote")


# ── 26. Interfaz web: la superficie más expuesta ────────────────────────────
def test_interfaz_web():
    print("\n== 26. INTERFAZ WEB ==")
    # Se importa el módulo del servidor sin arrancarlo. Solo se tocan rutas que
    # NO necesitan el núcleo, para que la prueba sea rápida y no levante hilos.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "web_interface"))
    try:
        import app as servidor
    except Exception as e:
        _check(False, "el servidor web se puede importar", f"-> {e}")
        return

    cliente = servidor.app.test_client()
    pin = servidor.AUTH_TOKEN

    # 1. Sin PIN no se entra a ningún endpoint con mando.
    for ruta, metodo in (("/api/panel", "get"),
                         ("/api/panel/accion", "post"),
                         ("/rotate_token", "post")):
        r = getattr(cliente, metodo)(ruta, json={})
        _check(r.status_code == 403, f"{ruta} sin PIN devuelve 403",
               f"-> {r.status_code}")

    # 2. El agujero que encontramos: cualquiera podía auto-autorizarse.
    r = cliente.post("/allow_my_ip", json={})
    _check(r.status_code == 403, "«/allow_my_ip» exige PIN (regresión del agujero)")
    r = cliente.post("/allow_my_ip", json={"token": "000000-mal"})
    _check(r.status_code == 403, "un PIN inventado tampoco vale")

    # 3. Con PIN correcto, el estado de emparejamiento responde.
    r = cliente.get("/pair_status", headers={"X-Token": pin})
    _check(r.status_code == 200, "«/pair_status» responde con PIN correcto")
    datos = r.get_json() or {}
    _check("pin_dias" in datos and "emparejados" in datos,
           "el estado de emparejamiento trae caducidad y aparatos")

    # 4. Un mando inventado no se ejecuta aunque el PIN sea bueno.
    r = cliente.post("/api/panel/accion", json={"accion": "formatea_el_disco"},
                     headers={"X-Token": pin})
    _check(r.status_code == 400, "un mando desconocido se rechaza",
           f"-> {r.status_code}")

    # 5. El NEXUS: la interfaz unificada se sirve y su API exige PIN.
    r = cliente.get("/nexus")
    _check(r.status_code == 200 and b"NEXUS" in r.data,
           "«/nexus» sirve la interfaz unificada", f"-> {r.status_code}")
    r = cliente.post("/api/nexus/cmd", json={"agente": "jarvis", "texto": "hola"})
    _check(r.status_code == 403, "el mando del NEXUS exige PIN")
    r = cliente.get("/api/nexus/estado")
    _check(r.status_code == 403, "el estado del NEXUS exige PIN")

    # 5b. AEON: la interfaz de gala y los modulos que comparte con el NEXUS.
    r = cliente.get("/aeon")
    _check(r.status_code == 200 and b'data-modo="jarvis"' in r.data,
           "«/aeon» sirve la interfaz nueva", f"-> {r.status_code}")
    r = cliente.get("/modulos.js")
    _check(r.status_code == 200 and b"MODULOS" in r.data,
           "«/modulos.js» sirve los modulos compartidos", f"-> {r.status_code}")

    # 6. La caducidad del PIN y del emparejamiento están puestas.
    _check(servidor.PIN_DIAS > 0, "el PIN caduca")
    _check(servidor.PAIR_DIAS > 0, "los emparejamientos caducan")


# ── 27. Panel: el estado no se rompe aunque falte un módulo ─────────────────
def test_panel_api():
    print("\n== 27. PANEL DE CONTROL ==")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "web_interface"))
    import panel_api

    datos = panel_api.panel(core=None)
    esperados = ("deshacer", "registro", "perfil", "metricas", "indice",
                 "recados", "habilidades", "servicio")
    for bloque_nombre in esperados:
        _check(bloque_nombre in datos, f"el panel trae el bloque «{bloque_nombre}»")

    # Un bloque que reviente no puede tumbar el panel entero.
    original = panel_api._seguro
    _check(isinstance(original("prueba", lambda: (_ for _ in ()).throw(RuntimeError("x"))),
                      dict), "un módulo roto se aísla y devuelve su error")

    r = panel_api.ejecutar(None, "accion_inventada")
    _check(not r["ok"], "el panel rechaza mandos que no existen")


# ── 28. Arrepentimiento: «no» corto sí, orden nueva no ──────────────────────
def test_arrepentimiento():
    print("\n== 28. VENTANA DE ARREPENTIMIENTO ==")
    import arrepentimiento as arr

    arr.cerrar()
    _check(not arr.es_arrepentimiento("no"), "sin ventana abierta, «no» no revierte nada")

    arr.abrir("He movido 214 archivos.", segundos=30, log=lambda *a: None)
    _check(arr.abierta(), "la ventana queda abierta")
    _check(arr.es_arrepentimiento("no"), "«no» dentro de la ventana revierte")
    _check(arr.es_arrepentimiento("eso no"), "«eso no» también")
    _check(not arr.es_arrepentimiento("no, mejor busca otra cosa en internet"),
           "una orden nueva que empieza por «no» NO revierte")
    arr.cerrar()
    _check(not arr.abierta(), "cerrarla la cierra")

    _check(arr.merece_ventana("mueve todos los pdf a documentos"),
           "una orden masiva y reversible merece ventana")
    _check(not arr.merece_ventana("que hora es"),
           "una consulta no abre ninguna ventana")


# ── 29. Perfiles: cambiar y volver exactamente al estado anterior ───────────
def test_perfiles():
    print("\n== 29. PERFILES ==")
    import perfiles

    original = perfiles.ESTADO
    perfiles.ESTADO = os.path.join(os.path.dirname(original), "perfil_test.json")
    prefs = {"avisos_proactivos": "1", "escucha_continua": "1"}

    class _Nucleo:
        skills = pc = enjambre = None
        nombre_agente = "JARVIS"

        def get_pref(self, k):
            return prefs.get(k, "")

        def set_pref(self, k, v):
            prefs[k] = v

    nucleo = _Nucleo()
    try:
        perfiles.activar(nucleo, "juego", log=lambda *a: None)
        _check(prefs["avisos_proactivos"] == "0", "el perfil juego calla los avisos")
        _check(perfiles.actual() == "juego", "el perfil activo se recuerda")
        _check("diez palabras" in perfiles.instruccion_prompt(nucleo),
               "el perfil cambia también el tono del cerebro")

        perfiles.restaurar(nucleo, log=lambda *a: None)
        _check(prefs["avisos_proactivos"] == "1",
               "al volver a normal se restaura lo que había, no un valor inventado")
    finally:
        try:
            os.unlink(perfiles.ESTADO)
        except Exception:
            pass
        perfiles.ESTADO = original


# ── 30. Valoraciones ────────────────────────────────────────────────────────
def test_feedback():
    print("\n== 30. VALORACIONES ==")
    import feedback
    signo, correccion = feedback.clasificar_frase("eso estuvo mal, queria abrir spotify")
    _check(signo == -1 and "spotify" in correccion,
           "detecta la crítica y lo que el señor quería", f"-> {signo}, {correccion}")
    _check(feedback.clasificar_frase("asi si")[0] == 1, "detecta el elogio")
    _check(feedback.clasificar_frase("abre spotify")[0] == 0,
           "una orden normal no se confunde con una valoración")
    _check(feedback.clasificar_frase(
        "no me sirve porque necesito que además me lo mandes por correo "
        "y lo guardes en la carpeta")[0] == 0,
        "una frase larga no se cuenta como valoración")


# ── 31. Consejo: detectar cuándo las dos voces discrepan de verdad ─────────
def test_consejo_desacuerdo():
    print("\n== 31. CONSEJO ==")
    import consejo

    _check(consejo.hay_desacuerdo("Sí. Borra la carpeta. No hay tiempo para dudas.",
                                  "No borres la carpeta: podría perderse algo."),
           "detecta el desacuerdo aunque el «sí» lleve un «no» dentro")
    _check(not consejo.hay_desacuerdo("Hazlo ya, no hay riesgo real.",
                                      "Adelante, es reversible."),
           "dos síes no son desacuerdo")
    _check(not consejo.hay_desacuerdo("No lo hagas todavía.",
                                      "Mejor no: espere a tener copia."),
           "dos noes tampoco")

    r = consejo.deliberar_estructurado(None, "no")
    _check(not r["ok"], "un asunto vacío no convoca al consejo")


# ── 32. Velocidad: nada de frenos artificiales con el modelo local ─────────
def test_sin_freno_local():
    print("\n== 32. VELOCIDAD ==")
    import time as _t
    from jarvis_core import JarvisCore

    c = JarvisCore.__new__(JarvisCore)
    c.log = lambda *a: None
    c._cerebro = {"min_segundos": 2, "max_por_hora": 40}
    c._llm_ultimo = _t.time()          # acabamos de hablar: el freno mordería
    c._llm_hora = [_t.time()] * 80     # y además pasaríamos del tope por hora
    c.base_url = "http://localhost:11434/v1"
    c.model = "qwen3:4b-instruct"
    c.api_key = "ollama"

    t0 = _t.time()
    permitido = c._rate_limit_ok()
    tardanza = _t.time() - t0
    _check(permitido, "con el cerebro local NO se rechaza por cuota horaria")
    _check(tardanza < 0.15,
           "con el cerebro local no se duerme entre respuestas", f"-> {tardanza:.2f}s")

    # Con un proveedor en la nube el freno debe seguir existiendo: está para
    # proteger cuotas de verdad.
    c._cerebro = {"proveedores": [{"nombre": "nube", "url": "https://api.ejemplo.com/v1",
                                   "modelo": "x", "clave": "y"}],
                  "min_segundos": 2, "max_por_hora": 40}
    _check(not c._solo_cerebro_local(), "un proveedor remoto sí se considera de pago")


# ── 33. Voz local en proceso (sin arrancar PowerShell por frase) ────────────
def test_voz_en_proceso():
    print("\n== 33. VOZ LOCAL ==")
    import voz_rapida
    tipo = voz_rapida.preparar(log=lambda *a: None)
    _check(tipo in ("sapi", "pyttsx3", "powershell", "no"),
           f"el motor de voz se resuelve ({tipo})")
    e = voz_rapida.estado()
    _check("motor" in e and "en_proceso" in e, "el estado de la voz es consultable")
    if e["en_proceso"]:
        _check(True, "hay motor en proceso: la voz empieza sin arrancar PowerShell")


# ── 34. Voz propia: cada personalidad con la suya ───────────────────────────
def test_voz_propia():
    print("\n== 34. VOZ PROPIA ==")
    import voz_propia
    import jarvis_piper

    # La carpeta de voces la manda jarvis_piper: si cambia el nombre de la
    # constante, voz_propia dejaria de ver las voces sin decir nada.
    _check(hasattr(jarvis_piper, "DIR"), "jarvis_piper sigue publicando DIR")
    _check(voz_propia.VOCES["jarvis"] != voz_propia.VOCES["ultron"],
           "JARVIS y ULTRON no comparten voz")
    for voz in (voz_propia.VOCES["jarvis"], voz_propia.VOCES["ultron"]):
        _check(voz in jarvis_piper.VOICES,
               f"«{voz}» se puede descargar (está en el catálogo de Piper)")

    prefs = {"voz_ultron": "es_MX-ald-medium"}
    falso = type("C", (), {"get_pref": lambda self, k: prefs.get(k, ""),
                           "set_pref": lambda self, k, v: prefs.__setitem__(k, v)})()
    _check(voz_propia.voz_de("ultron", falso) == "es_MX-ald-medium",
           "la preferencia guardada manda sobre la voz por defecto")
    e = voz_propia.estado(falso)
    _check("motores" in e and "catalogo" in e, "el estado de la voz es consultable")


# ── 35. El movil no revienta cuando no hay movil ────────────────────────────
def test_movil_sin_telefono():
    print("\n== 35. MÓVIL ==")
    import movil

    hay, motivo = movil.disponible()
    _check(isinstance(hay, bool) and isinstance(motivo, str),
           "disponible() responde siempre, con o sin teléfono")
    if not hay:
        _check("adb" in motivo.lower() or "teléfono" in motivo.lower(),
               "y explica qué falta")
        # Nada de excepciones cuando el telefono no esta: el asistente sigue vivo.
        for funcion in (movil.bateria, movil.notificaciones, movil.ubicacion):
            _check(funcion() in ({}, []), f"{funcion.__name__}() no revienta sin teléfono")
    _check("adb" in movil.resumen().lower() or "teléfono" in movil.resumen().lower(),
           "el resumen se puede decir en voz alta")

    # Las reglas se guardan en las preferencias, no en memoria volatil.
    prefs = {}
    falso = type("C", (), {"get_pref": lambda self, k: prefs.get(k, ""),
                           "set_pref": lambda self, k, v: prefs.__setitem__(k, v),
                           "log": lambda self, *a: None})()
    puente = movil.Puente(falso, log=lambda *a: None)
    puente.añadir("el banco", "")
    _check("movil_reglas" in prefs, "la regla queda guardada entre arranques")
    otro = movil.Puente(falso, log=lambda *a: None)
    _check(len(otro.cargar()) == 1, "y se recupera al arrancar de nuevo")


# ── 36. El observador solo mira cuando hay atasco ───────────────────────────
def test_observador_prudente():
    print("\n== 36. OBSERVADOR ==")
    import observador

    prefs = {"avisos_proactivos": "1"}
    falso = type("C", (), {"get_pref": lambda self, k: prefs.get(k, ""),
                           "set_pref": lambda self, k, v: prefs.__setitem__(k, v)})()
    obs = observador.Observador(falso, log=lambda *a: None)

    miradas = []
    obs.mirar = lambda ventana="": miradas.append(ventana) or ""

    # Primera vuelta: ventana nueva, no mira.
    obs._ventana_previa = ""
    import rebobinar
    original = rebobinar._ventana_activa
    rebobinar._ventana_activa = lambda: "proyecto - Visual Studio Code"
    try:
        for _ in range(observador.RONDAS_PARA_ATASCO - 1):
            obs.ronda()
        _check(not miradas, "trabajar tranquilo no gasta ni una captura")
        obs.ronda()
        _check(len(miradas) == 1, "al cuarto minuto sin cambiar, mira una vez")

        # Ventana que no interesa: ni con atasco.
        miradas.clear()
        obs._ventana_previa = ""
        obs._rondas_igual = 0
        rebobinar._ventana_activa = lambda: "Netflix"
        for _ in range(observador.RONDAS_PARA_ATASCO + 2):
            obs.ronda()
        _check(not miradas, "una película quieta no es un atasco")

        # Y con los avisos silenciados, ni mira la ventana.
        prefs["avisos_proactivos"] = "0"
        _check(obs._callado(), "con los avisos apagados se queda callado")
    finally:
        rebobinar._ventana_activa = original


# ── 37. El afinado no aprende de lo que salió mal ───────────────────────────
def test_afinado_respeta_feedback():
    print("\n== 37. AFINADO ==")
    import afinar

    _check(afinar._parecidas("borra los temporales", {"borra los temporales"}),
           "reconoce la orden exacta que se valoró mal")
    _check(afinar._parecidas("borra los archivos temporales",
                             {"borra los temporales archivos"}),
           "y la misma orden dicha con otro orden de palabras")
    _check(not afinar._parecidas("pon música", {"borra los temporales"}),
           "sin confundirla con otra cosa")

    e = afinar.estado(log=lambda *a: None)
    for clave in ("conversaciones", "suficiente", "mal_valoradas", "equipo"):
        _check(clave in e, f"el estado del afinado trae «{clave}»")
    _check(isinstance(afinar.resumen(log=lambda *a: None), str),
           "y se puede contar en voz alta")


# ── 38. El QR nunca puede apuntar a una IP muerta ───────────────────────────
def test_direccion_del_movil():
    print("\n== 38. EMPAREJAR EL MÓVIL ==")
    import red_movil

    lista = red_movil.ips_lan()
    _check(isinstance(lista, list), "ips_lan() devuelve la lista de direcciones")
    for e in lista:
        ip = e["ip"]
        _check(not ip.startswith(("127.", "169.254", "100.")),
               f"{ip} es una dirección por la que se puede entrar")
        _check("interfaz" in e and "perfil" in e,
               f"{ip} viene con interfaz y perfil, para poder explicarlo")

    mejor = red_movil.mejor_ip()
    _check(mejor == (lista[0]["ip"] if lista else "127.0.0.1"),
           f"la del QR es la mejor de la lista ({mejor})")

    # Lo importante: se pregunta cada vez. Una IP cacheada es justo el fallo que
    # dejaba al teléfono cargando contra la dirección de anteayer.
    red_movil._cache["ts"] = 0
    _check(red_movil.mejor_ip() == mejor, "y se puede volver a preguntar sin cachear")

    motivos = red_movil.diagnostico()
    _check(all("que" in m and "hacer" in m for m in motivos),
           "cada problema viene con su solución")
    _check(isinstance(red_movil.resumen(), str) and "://" in red_movil.resumen(),
           "el resumen trae la dirección lista para escribir")

    fw = red_movil.firewall()
    _check("hace_falta" in fw, "sabe si el cortafuegos está cerrando el paso")


# ── 39. Entrar desde fuera de casa ──────────────────────────────────────────
def test_acceso_remoto():
    print("\n== 39. ACCESO REMOTO ==")
    import remoto

    e = remoto.estado()
    for clave in ("instalado", "red", "publicado", "urls"):
        _check(clave in e, f"el estado del acceso remoto trae «{clave}»")
    _check(isinstance(remoto.resumen(), str), "y se puede contar en voz alta")

    if not e["instalado"]:
        _check("Tailscale" in remoto.activar(log=lambda *a: None),
               "sin Tailscale, explica cómo ponerlo en vez de fallar")
        return

    # Publicar en Internet no puede pasar por accidente: hace falta decirlo dos
    # veces. Es la unica puerta que deja entrar a desconocidos.
    aviso = remoto.publicar_en_internet(confirmado=False, log=lambda *a: None)
    _check("Internet" in aviso and "confirmo" in aviso,
           "abrir a Internet avisa y exige confirmación expresa")
    _check(not remoto.publicado().get("funnel"),
           "y no queda abierto a Internet por haber preguntado")

    for u in e["urls"]:
        _check(u["url"].startswith(("http://", "https://")),
               f"{u['url'][:48]} es una dirección utilizable")
    seguras = [u for u in e["urls"] if u.get("segura")]
    for u in seguras:
        _check(u["url"].startswith("https://"),
               "la dirección recomendada va cifrada (si no, el móvil apaga el micrófono)")


# ── 40. Seis cifras no se adivinan a lo bruto ───────────────────────────────
def test_freno_del_pin():
    print("\n== 40. FRENO DEL PIN ==")
    import importlib.util
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "web_interface", "app.py")
    fuente = open(ruta, encoding="utf-8").read()

    # Sin arrancar Flask: se comprueba que el freno existe y con que numeros.
    _check("_bloqueado" in fuente and "_anotar_fallo" in fuente,
           "hay freno para quien prueba PINes en cadena")
    _check("INTENTOS_MAX" in fuente and "CASTIGO_SEG" in fuente,
           "con un tope de intentos y un castigo configurables")
    _check('if ip in LOCALES:' in fuente,
           "el propio PC nunca se castiga a sí mismo")
    _check("_auth_ok(auth.get('token', ''))" in fuente,
           "el socket también pasa por la misma puerta")


def main():
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for prueba in pruebas:
        try:
            prueba()
        except Exception as e:
            print(f"  ERROR| {prueba.__name__}: {e}")
            _FALLOS.append(prueba.__name__)
    print("\n" + "=" * 60)
    if _FALLOS:
        print(f"FALLARON {len(_FALLOS)}: {', '.join(_FALLOS)}")
        return 1
    print("TODO EN VERDE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
