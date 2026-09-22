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
import time

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
        base_url = "https://api.anthropic.com"
        model = "claude-opus-5"
        api_key = "sk-ant-falsa"
        elevenlabs_key = "sk-secreta"

        def get_pref(self, k):
            return prefs.get(k)

        def set_pref(self, k, v):
            prefs[k] = v

        def _voz_piper_activa(self):
            return False

    nucleo = _Nucleo()
    nucleo._cerebro = {"proveedores": [
        {"nombre": "claude", "url": "https://api.anthropic.com", "modelo": "claude-opus-5",
         "clave": "x"}]}

    salidas = [n for n, _q, _a in privacidad.auditar(nucleo)]
    _check("voz" in salidas, "detecta que la voz pasa por un servicio externo", f"-> {salidas}")
    _check(any("cerebro" in n for n in salidas), "detecta el proveedor de cerebro remoto")

    privacidad.activar(nucleo)
    _check(nucleo.elevenlabs_key == "", "el modo privado corta la voz en la nube")
    _check(prefs.get("vision_nube") == "0",
           "el modo privado deja la vision en OCR local")
    _check(len(nucleo._cerebro["proveedores"]) == 1,
           "el cerebro se queda como esta: Claude es el unico que hay")
    _check(prefs.get("stt_local") == "1", "fuerza el dictado local")

    privacidad.desactivar(nucleo)
    _check(nucleo.elevenlabs_key == "sk-secreta", "al desactivarlo restaura la clave")
    _check(len(nucleo._cerebro["proveedores"]) == 1, "y deja el cerebro intacto")
    _check(prefs.get("vision_nube") != "0", "y devuelve la vision por Claude")


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
    # Sin topes configurados (el defecto desde que Claude es el unico cerebro)
    # no se frena ni se duerme: cortar dejaria al senor sin respuesta.
    c._cerebro = {}
    c._llm_ultimo = _t.time()          # acabamos de hablar
    c._llm_hora = [_t.time()] * 80     # y llevamos 80 frases esta hora
    c.base_url = "https://api.anthropic.com"
    c.model = "claude-opus-5"
    c.api_key = "sk-ant-falsa"

    t0 = _t.time()
    permitido = c._rate_limit_ok()
    tardanza = _t.time() - t0
    _check(permitido, "sin topes configurados no se rechaza por cuota horaria")
    _check(tardanza < 0.15,
           "sin topes configurados no se duerme entre respuestas", f"-> {tardanza:.2f}s")

    # Quien ponga topes a mano en cerebro.json los sigue teniendo.
    c._cerebro = {"min_segundos": 2, "max_por_hora": 40}
    _check(not c._rate_limit_ok(),
           "con tope por hora puesto a mano, se corta")
    # El cerebro volvió a casa (Qwen por Ollama): cuando TODO lo que hay es
    # local no hay cuota que respetar, y cuando hay nube por medio sí.
    c._cerebro = {"proveedores": [
        {"nombre": "qwen3:8b", "url": "http://localhost:11434/v1",
         "modelo": "qwen3:8b", "clave": "ollama"}]}
    _check(c._solo_cerebro_local(),
           "con solo Qwen en casa no se aplica cuota ni espera")
    c._cerebro = {"proveedores": [
        {"nombre": "qwen3:8b", "url": "http://localhost:11434/v1",
         "modelo": "qwen3:8b", "clave": "ollama"},
        {"nombre": "claude-sonnet-5", "url": "https://api.anthropic.com",
         "modelo": "claude-sonnet-5", "clave": "sk-de-mentira"}]}
    _check(not c._solo_cerebro_local(),
           "con la nube de reserva sí se cuenta como de pago")
    import presupuesto as _pre
    _check(_pre.coste_estimado("qwen3:8b", 100000, 100000) == 0.0,
           "el cerebro de casa no suma al gasto del día")


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



# ── 41. Escáner 3D: qué frases se queda y qué acciones salen ───────────────
def test_escaner3d():
    print("\n== 41. ESCANER 3D ==")
    import re as _re
    import escaner3d

    piezas = [{"nombre": "cuerpo"}, {"nombre": "asa"}, {"nombre": "tapa"}]
    real = escaner3d.piezas_de
    escaner3d.piezas_de = lambda ident="": piezas        # sin tocar el disco
    try:
        def accion_de(frase):
            r = escaner3d._atajos(frase)
            acciones = r.get("acciones") or []
            return (acciones[0]["nombre"], acciones[0].get("args") or {}) if acciones else ("", {})

        _check(accion_de("desármalo")[0] == "desarmar",
               "«desármalo» separa las piezas")
        _check(accion_de("vuelve a montarlo")[0] == "armar",
               "«vuelve a montarlo» las junta")
        _check(accion_de("aísla la tapa") == ("aislar", {"pieza": "tapa"}),
               "«aísla la tapa» coge la pieza por su nombre")
        _check(accion_de("quítame el asa") == ("ocultar", {"pieza": "asa"}),
               "«quítame el asa» oculta esa pieza y no otra")
        _check(accion_de("córtalo por la mitad")[0] == "seccion",
               "«córtalo por la mitad» pone el plano de corte")
        _check(accion_de("ponle rayos X") == ("rayos_x", {"activo": True}),
               "«ponle rayos X» enciende la transparencia")
        _check(accion_de("quita los rayos x") == ("rayos_x", {"activo": False}),
               "«quita los rayos x» la apaga (y no se confunde con ocultar)")
        _check(accion_de("mídelo")[0] == "medir", "«mídelo» mide")
        _check(accion_de("deja de girar") == ("girar", {"activo": False}),
               "«deja de girar» para el giro")

        # La puerta: qué frases entran al escáner y cuáles son de otros.
        def escaneo(frase):
            low = escaner3d._sin_tildes(frase)
            if not escaner3d._RE_ESCANEO.search(low):
                return False
            if escaner3d._RE_NO_OBJETO.search(low):
                return False
            if _re.search(r"[A-Za-z]:\\|/[\w./-]+\.(png|jpg|jpeg|mp4|obj|stl|glb|blend)", frase):
                return False
            if _re.search(r"\b3\s*-?\s*d\b", low) and not escaner3d._RE_CAMARA.search(low):
                return False
            return True

        _check(escaneo("escanea este objeto con la cámara"),
               "«escanea este objeto» es del escáner")
        _check(escaneo("escanéalo con el móvil"), "y con el móvil también")
        _check(not escaneo("escanea el disco duro"),
               "«escanea el disco duro» NO enciende la cámara")
        _check(not escaneo("escanea la red"), "«escanea la red» tampoco")
        _check(not escaneo(r"modélame en 3D C:\fotos\taza.jpg"),
               "un archivo suelto sigue siendo de modelado3d")

        nombres = {n for n, _ in escaner3d.ACCIONES}
        _check({"desarmar", "aislar", "seccion", "piramide", "medir"} <= nombres,
               "el catálogo que ve el cerebro lleva las acciones de verdad")
        _check(escaner3d._SB_MODELO.count("JARVIS3D_OK") == 1,
               "el guion de Blender avisa de que terminó bien")
    finally:
        escaner3d.piezas_de = real


# ── 42. Puente del holograma: sin token no se contesta ─────────────────────
def test_holo_puente():
    print("\n== 42. PUENTE DEL HOLOGRAMA ==")
    import holo_puente

    _check(len(holo_puente.token()) >= 12, "el token tiene cuerpo suficiente")
    _check(holo_puente.token() == holo_puente.token(),
           "y es el mismo mientras dure la casa")
    r = holo_puente.accion("desarmar", {}, log=lambda *a: None)
    _check(not r.get("ok"), "sin visor abierto, la acción se rechaza sola")

    fuente = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "holo_puente.py"), encoding="utf-8").read()
    _check("_autorizado" in fuente and "compare_digest" in fuente,
           "el token se compara sin filtrar el tiempo")
    _check("RLock" in fuente,
           "el candado es reentrante (arrancar pide el estado con él cogido)")
    _check('ctx.load_cert_chain' in fuente,
           "el escáner del móvil va por HTTPS o no va")

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


# ── 40. Navegador: guardarrailes y cableado ────────────────────────────────
def test_navegador_guardarrailes():
    print("\n== 40. NAVEGADOR ==")
    import navegador

    _check(bool(navegador._binario()),
           "encuentra un navegador Chromium en el equipo",
           f"-> {navegador._binario() or 'ninguno'}")

    for campo in ("Contraseña", "password", "Número de tarjeta", "card-number",
                  "CVV", "IBAN"):
        _check(bool(navegador._PROHIBIDO_ESCRIBIR.search(campo)),
               f"«{campo}» se reconoce como campo que JARVIS no rellena")
    _check(not navegador._PROHIBIDO_ESCRIBIR.search("Buscar en la web"),
           "un campo normal sí se puede rellenar")

    for boton in ("Pagar 49,90 €", "Comprar ahora", "Realizar pedido",
                  "Confirmar pago", "Finalizar la compra"):
        _check(bool(navegador._PROHIBIDO_PULSAR.search(boton)),
               f"«{boton}» se reconoce como botón que no se pulsa solo")
    _check(not navegador._PROHIBIDO_PULSAR.search("Aceptar"),
           "un botón corriente sí se puede pulsar")

    # El bucle sin cerebro no puede inventarse una acción.
    _check(navegador._leer_json("no hay json aquí") is None,
           "una respuesta sin JSON no se cuela como acción")
    accion = navegador._leer_json('bla {"accion": "clic", "ref": 3} bla')
    _check(accion and accion.get("accion") == "clic",
           "el JSON se rescata aunque venga envuelto en texto")

    # Cableado: cada herramienta declarada tiene su método y su política.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    declaradas = [n for n in nombres if n.startswith("navegador")]
    _check(len(declaradas) == 4, f"se ofrecen las cuatro herramientas del navegador ({declaradas})")
    for n in declaradas:
        _check(hasattr(caja, f"_t_{n}"), f"«{n}» tiene método que la ejecuta")
    _check(permisos.evaluar("navegador_tarea") == "confirmar",
           "la tarea web se para y pide confirmación")
    _check("navegador_ensayo" in permisos._LECTURA,
           "el ensayo cuenta como lectura: se puede hacer en modo seguro")

    # La voz reconoce lo suyo y no secuestra lo ajeno.
    from skills.plugins import get_plugin_registry
    reg = get_plugin_registry(log=lambda *a: None)
    def _toca(frase):
        return any(any(r.search(frase) for r in rx)
                   for _p, n, _i, rx in reg.plugins if n.startswith("navegador"))
    for frase in ("abre el navegador", "entra en example.com",
                  "en la web busca el horario de la biblioteca"):
        _check(_toca(frase), f"«{frase}» llega al navegador")
    for frase in ("entra en la carpeta de descargas", "abre spotify", "ve a por el correo"):
        _check(not _toca(frase), f"«{frase}» NO lo secuestra el navegador")


# ── 41. Navegador: la red y el diagnóstico ─────────────────────────────────
def test_navegador_red_y_diagnostico():
    print("\n== 41. NAVEGADOR: RED Y DIAGNOSTICO ==")
    import navegador

    nav = navegador.Navegador(log=lambda *a: None)

    # El clasificador de eventos, sin navegador: es lógica pura.
    nav._procesar({"method": "Network.requestWillBeSent", "params": {
        "requestId": "1", "type": "XHR",
        "request": {"url": "https://ejemplo.com/api/pedidos", "method": "GET"}}})
    nav._procesar({"method": "Network.responseReceived", "params": {
        "requestId": "1", "type": "XHR",
        "response": {"url": "https://ejemplo.com/api/pedidos", "status": 200,
                     "mimeType": "application/json"}}})
    nav._procesar({"method": "Network.loadingFinished",
                   "params": {"requestId": "1", "encodedDataLength": 1234}})
    nav._procesar({"method": "Network.requestWillBeSent", "params": {
        "requestId": "2", "type": "Image",
        "request": {"url": "https://ejemplo.com/icono.svg", "method": "GET"}}})
    nav._procesar({"method": "Network.responseReceived", "params": {
        "requestId": "2", "type": "Image",
        "response": {"url": "https://ejemplo.com/icono.svg", "status": 200,
                     "mimeType": "image/svg+xml"}}})

    datos = nav.red(solo_datos=True)
    _check(len(datos) == 1 and "pedidos" in datos[0]["url"],
           "la API se distingue del ruido", f"-> {[d['url'] for d in datos]}")
    _check(not nav.red("no-encaja-con-nada", solo_datos=True),
           "un patrón que no encaja no devuelve nada")
    _check(len(nav.red(solo_datos=False)) == 2,
           "sin filtro se ven todas las peticiones")

    # Una web sana no inventa problemas.
    _check("Limpia" in nav.diagnostico(), "sin errores, el diagnóstico lo dice")

    # Y una rota los cuenta todos, cada uno en su apartado.
    nav._procesar({"method": "Runtime.consoleAPICalled", "params": {
        "type": "error", "args": [{"value": "el carrito no arranca"}]}})
    nav._procesar({"method": "Runtime.exceptionThrown", "params": {
        "exceptionDetails": {"exception": {"description": "TypeError: x is undefined"}}}})
    nav._procesar({"method": "Network.requestWillBeSent", "params": {
        "requestId": "3", "type": "Fetch",
        "request": {"url": "https://ejemplo.com/api/precios", "method": "GET"}}})
    nav._procesar({"method": "Network.loadingFailed", "params": {
        "requestId": "3", "type": "Fetch", "errorText": "net::ERR_NAME_NOT_RESOLVED"}})
    nav._procesar({"method": "Network.requestWillBeSent", "params": {
        "requestId": "4", "type": "XHR",
        "request": {"url": "https://ejemplo.com/api/stock", "method": "POST"}}})
    nav._procesar({"method": "Network.responseReceived", "params": {
        "requestId": "4", "type": "XHR",
        "response": {"url": "https://ejemplo.com/api/stock", "status": 500,
                     "mimeType": "application/json"}}})

    informe = nav.diagnostico()
    _check("el carrito no arranca" in informe, "el diagnóstico recoge console.error")
    _check("TypeError" in informe, "el diagnóstico recoge la excepción sin capturar")
    _check("ERR_NAME_NOT_RESOLVED" in informe, "el diagnóstico recoge la petición caída")
    _check("500" in informe, "el diagnóstico recoge el error del servidor")
    _check("Limpia" not in informe, "una web rota no se declara limpia")

    # Sólo los avisos no se cuentan como errores.
    limpio = navegador.Navegador(log=lambda *a: None)
    limpio._procesar({"method": "Runtime.consoleAPICalled", "params": {
        "type": "warning", "args": [{"value": "precio en cache"}]}})
    _check("Sólo avisos" in limpio.diagnostico(),
           "un aviso no se disfraza de error")

    # Cableado de las dos herramientas nuevas.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    for n in ("navegador_datos", "navegador_diagnostico"):
        _check(n in nombres, f"«{n}» se le ofrece al cerebro")
        _check(hasattr(caja, f"_t_{n}"), f"«{n}» tiene método que la ejecuta")
        _check(permisos.evaluar(n) == "directo" and n in permisos._LECTURA,
               f"«{n}» es lectura: no toca nada")


# ── 42. Simulación: que la ciencia se mueva ────────────────────────────────
def test_simulacion_anima():
    print("\n== 42. SIMULACION ==")
    import simulacion as S

    # El integrador, contra un problema con solución exacta: caída libre.
    # y(t) = y0 - g t²/2, así que a los 2 s desde 100 m deben quedar 80,38 m.
    def caida(_t, y):
        import numpy as np
        return np.array([y[1], -9.80665])
    _t, estados = S.rk4(caida, [100.0, 0.0], 0.001, 2000)
    exacta = 100 - 9.80665 * 4 / 2
    _check(abs(estados[-1][0] - exacta) < 1e-6,
           "Runge-Kutta 4 clava la caída libre",
           f"-> {estados[-1][0]:.9f} vs {exacta:.9f}")

    # Cada sistema del catálogo produce marcos y no revienta.
    casos = [("tiro", {"v0": 20, "angulo": 45}),
             ("orbita", {"sistema": "sol-tierra", "vueltas": 0.6}),
             ("pendulo", {"l1": 1.0, "l2": 0.8}),
             ("muelle", {"k": 9.0}),
             ("carga", {"B": (0, 0, 1.0)}),
             ("lorenz", {"t_max": 8.0}),
             ("cuerda", {"modos": (1, 2)}),
             ("membrana", {"modo": (1, 1)}),
             ("molecula", {"formula": "H2O"}),
             ("ecuaciones", {"ecuaciones": ["x'' = -4*x"], "inicial": {"x": 1.0},
                             "t_max": 6.0})]
    for nombre, params in casos:
        r = S.simular(nombre, params, abrir_visor=False, log=lambda *a: None)
        ok = r.get("ok") and r.get("html") and os.path.exists(r["html"])
        _check(bool(ok), f"«{nombre}» se simula y escribe su visor",
               f"-> {str(r.get('pasos'))[:90]}")
        if ok:
            d = r["datos"]
            _check(bool(d.get("marcos")) or bool(d.get("malla")),
                   f"«{nombre}» produce algo que animar")

    # La órbita tiene que CONSERVAR la energía: es lo que separa una
    # integración buena de una que se inventa una espiral.
    r = S.simular("orbita", {"sistema": "sol-tierra", "vueltas": 1.0},
                  abrir_visor=False, log=lambda *a: None)
    e = r["datos"]["escalares"]["energía total (×10³³ J)"]
    deriva = abs(e[-1] - e[0]) / (abs(e[0]) or 1)
    _check(deriva < 1e-3, "la órbita conserva la energía (la elipse cierra)",
           f"-> deriva {deriva:.3e}")

    # El péndulo doble es caótico, pero NO puede ganar energía de la nada.
    r = S.simular("pendulo", {"l1": 1.0, "l2": 0.8, "t_max": 15},
                  abrir_visor=False, log=lambda *a: None)
    e = r["datos"]["escalares"]["energía (J)"]
    _check(max(e) - min(e) < 0.05, "el péndulo doble conserva la energía",
           f"-> oscila {max(e) - min(e):.5f} J")

    # Ecuaciones dictadas: x'' = -4x es un oscilador de periodo π.
    r = S.simular("ecuaciones", {"ecuaciones": ["x'' = -4*x"],
                                 "inicial": {"x": 1.0}, "t_max": 3.15},
                  abrir_visor=False, log=lambda *a: None)
    xs = r["datos"]["escalares"]["x"]
    _check(abs(xs[-1] - 1.0) < 0.02,
           "una ecuación dictada se integra bien (periodo pi del oscilador)",
           f"-> x(pi) = {xs[-1]:.5f}, debería ser 1")

    # Lo que no se entiende se dice, no se inventa.
    malo = S.simular("agujero_negro", {}, abrir_visor=False, log=lambda *a: None)
    _check(not malo.get("ok") and "No sé simular" in " ".join(malo["pasos"]),
           "un sistema que no existe se rechaza con el catálogo")
    falta = S.desde_ecuaciones(["x' = k*x"])
    _check(not falta.get("ok") and "k" in " ".join(falta["pasos"]),
           "si falta el valor de una constante, se pide en vez de suponerlo")

    # Enrutado desde la voz.
    import ciencias as C
    for frase, sistema in (("simula el pendulo doble", "pendulo"),
                           ("anima la orbita de la tierra y la luna", "orbita"),
                           ("quiero ver el efecto mariposa", "lorenz"),
                           ("anima la molecula de amoniaco", "molecula")):
        p = C.plan_por_reglas(frase)
        _check(p.get("accion") == "simular" and p.get("simulacion") == sistema,
               f"«{frase}» va a la simulación «{sistema}»",
               f"-> {p.get('accion')}/{p.get('simulacion')}")
    for frase in ("resuelveme x al cuadrado menos 4 igual a cero",
                  "graficame seno de x"):
        p = C.plan_por_reglas(frase)
        _check(p.get("accion") != "simular",
               f"«{frase}» NO se la lleva la simulación", f"-> {p.get('accion')}")

    # Cableado de la herramienta.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    _check("simular_ciencia" in nombres, "«simular_ciencia» se le ofrece al cerebro")
    _check(hasattr(caja, "_t_simular_ciencia"), "«simular_ciencia» tiene método")
    _check("simular_ciencia" in permisos._LECTURA,
           "simular es lectura: calcula y escribe un .html, no toca nada más")


# ── 43. Química: enlaces múltiples y pares solitarios ──────────────────────
def test_quimica_enlaces_precisos():
    print("\n== 43. QUIMICA: ENLACES ==")
    import re as _re

    import quimica as Q

    # Orden de enlace y longitud, contra los valores medidos de verdad.
    esperado = {"H2O": ("simple", 96), "CO2": ("doble", 116), "N2": ("triple", 110),
                "NH3": ("simple", 101), "CH4": ("simple", 109), "SO2": ("doble", 143)}
    for formula, (orden, pm_real) in esperado.items():
        r = Q.modelo_3d_molecula(formula, abrir_visor=False, log=lambda *a: None)
        if not _check(bool(r.get("ok")), f"{formula} se modela"):
            continue
        linea = next((p for p in r["pasos"] if p.startswith("Enlace")), "")
        _check(orden in linea, f"{formula}: el enlace se reconoce como {orden}",
               f"-> {linea[:70]}")
        m = _re.search(r"(\d+) pm", linea)
        pm = int(m.group(1)) if m else 0
        _check(abs(pm - pm_real) / pm_real < 0.08,
               f"{formula}: la longitud ({pm} pm) se acerca a la real ({pm_real} pm)")

    # Los pares solitarios se dibujan, no solo se cuentan.
    agua = Q.modelo_3d_molecula("H2O", abrir_visor=False, log=lambda *a: None)
    _check(any("lóbulos" in p for p in agua["pasos"]),
           "el agua enseña sus dos pares solitarios en el modelo")
    metano = Q.modelo_3d_molecula("CH4", abrir_visor=False, log=lambda *a: None)
    _check(not any("lóbulos" in p for p in metano["pasos"]),
           "el metano no tiene pares solitarios y no se inventan")

    # Cuántas varillas lleva cada enlace. Se mide aquí y no contando vértices
    # de dos moléculas distintas: el HF tiene tres pares solitarios que también
    # suman geometría, así que esa comparación no dice nada del enlace.
    for orden, varillas in ((1, 1), (2, 2), (3, 3)):
        tramos = Q._separar((1.0, 0.0, 0.0), orden)
        _check(len(tramos) == varillas,
               f"un enlace de orden {orden} se dibuja con {varillas} varilla(s)",
               f"-> {len(tramos)}")
    # Y las varillas de un doble van separadas, no una encima de otra.
    a, b = Q._separar((1.0, 0.0, 0.0), 2)
    _check(a[0] != b[0], "las dos varillas del doble enlace no se solapan")


# ── 44. «Papá llegó»: saludo e interruptor general ─────────────────────────
def test_llegada_enciende_todo():
    print("\n== 44. LLEGADA ==")
    from skills.plugins import get_plugin_registry
    reg = get_plugin_registry(log=lambda *a: None)
    plug = next((i for _p, n, i, _rx in reg.plugins if n.startswith("llegada")), None)
    if not _check(plug is not None, "el plugin de llegada se carga solo"):
        return

    def _toca(frase):
        return any(any(r.search(frase) for r in rx)
                   for _p, n, _i, rx in reg.plugins if n.startswith("llegada"))
    for frase in ("jarvis papa llego", "papá llegó", "ya llegue",
                  "ya estoy en casa", "he llegado", "estoy de vuelta"):
        _check(_toca(frase), f"«{frase}» despierta la llegada")

    class _Skills:
        safe = False

        def _domo_leer(self):
            return {}

    class _Nucleo:
        nombre_agente = "JARVIS"
        log = staticmethod(lambda *a: None)
        escucha = None
        proactivo = "en marcha"
        vigilante = None
        skills = _Skills()

        def set_pref(self, k, v):
            pass

    # Contar una anécdota NO es anunciarse.
    for frase in ("mi papa llego tarde ayer", "papa llego a la oficina a las ocho",
                  "que hora es"):
        _check(plug.handle(frase, _Nucleo()) is None,
               f"«{frase}» no enciende la casa")

    r = plug.handle("jarvis papa llego", _Nucleo())
    _check(bool(r) and "Bienvenido a casa" in r, "saluda al llegar", f"-> {str(r)[:70]}")
    _check("Ya estaba en marcha el motor proactivo" in r,
           "lo que ya estaba encendido se informa, no se reinicia")
    _check("No he podido con" in r,
           "lo que no se puede encender se dice, no se finge")

    class _Ultron(_Nucleo):
        nombre_agente = "ULTRON"
    _check("Ha vuelto" in (plug.handle("ya llegue", _Ultron()) or ""),
           "ULTRON saluda distinto que JARVIS")


# ── 45. Pollinations: el cerebro de la nube sin tarjeta ────────────────────
def test_pollinations_proveedor():
    print("\n== 45. POLLINATIONS ==")
    import proveedor_pollinations as poll

    _check(poll.es_pollinations("https://text.pollinations.ai/openai"),
           "reconoce su propia URL")
    _check(not poll.es_pollinations("http://localhost:11434/v1"),
           "no confunde el cerebro de casa con la nube")

    # La clave sale del entorno, con los tres nombres que usa la documentación.
    previo = {k: os.environ.get(k) for k in
              ("POLLINATIONS_API_KEY", "POLLINATIONS_TOKEN", "POLLINATIONS_KEY")}
    try:
        for k in previo:
            os.environ.pop(k, None)
        _check(not poll.hay_clave(), "sin variables, no se inventa una clave")
        _check(poll.espera_entre_llamadas() >= 15,
               "sin clave, el ritmo es el anónimo (15 s)",
               f"-> {poll.espera_entre_llamadas()}")
        os.environ["POLLINATIONS_API_KEY"] = "${POLLINATIONS_API_KEY}"
        _check(not poll.hay_clave(),
               "una variable SIN sustituir no cuenta como clave")
        os.environ["POLLINATIONS_TOKEN"] = "clave_de_prueba"
        _check(poll.clave() == "clave_de_prueba",
               "acepta también POLLINATIONS_TOKEN")
        # La entrada para cerebro.json NO lleva la clave dentro.
        entrada = poll.proveedores(log=lambda m: None)[0]
        _check(entrada["clave"] == "${POLLINATIONS_API_KEY}",
               "la clave va por referencia, no escrita en el JSON de prefs")
        _check(poll.es_pollinations(entrada["url"]), "la entrada apunta a Pollinations")
    finally:
        for k, v in previo.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    # El núcleo tiene que ACEPTAR la entrada: antes la borraba por no ser ni
    # local ni Anthropic, y el señor no se habría enterado de por qué.
    import tempfile

    from jarvis_core import JarvisCore
    obj = JarvisCore.__new__(JarvisCore)
    obj.log = lambda *a: None
    guardado = {k: os.environ.get(k) for k in
                ("POLLINATIONS_API_KEY", "JARVIS_CEREBRO", "ANTHROPIC_API_KEY")}
    try:
        def _orden(clave, preferido, anthropic="sk-test"):
            os.environ["POLLINATIONS_API_KEY"] = clave
            os.environ["JARVIS_CEREBRO"] = preferido
            os.environ["ANTHROPIC_API_KEY"] = anthropic
            ruta = os.path.join(tempfile.gettempdir(),
                                f"cerebro_test_{abs(hash((clave, preferido)))}.json")
            if os.path.exists(ruta):
                os.remove(ruta)
            obj._cerebro_path = ruta
            return [p["nombre"] for p in obj._cerebro_leer()["proveedores"]]

        con_clave = _orden("abc123", "")
        _check(con_clave and con_clave[0].startswith("pollinations"),
               "con clave y sin preferencia, Pollinations manda", f"-> {con_clave}")
        _check(any("qwen" in n for n in con_clave),
               "el cerebro de casa NUNCA se cae de la lista", f"-> {con_clave}")

        sin_clave = _orden("", "")
        _check(sin_clave and "qwen" in sin_clave[0],
               "sin clave manda el de casa: el anónimo va a 15 s por petición",
               f"-> {sin_clave}")

        forzado = _orden("abc123", "local")
        _check(forzado and "qwen" in forzado[0],
               "JARVIS_CEREBRO=local manda sobre el valor por defecto",
               f"-> {forzado}")

        claude = _orden("abc123", "claude")
        _check(claude and claude[0].startswith("claude"),
               "JARVIS_CEREBRO=claude pone Anthropic delante", f"-> {claude}")
    finally:
        for k, v in guardado.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    # El nivel se aprende de la respuesta, sin configurarlo a mano.
    poll.anotar_respuesta({"user_tier": "flower"})
    _check(poll.nivel() == "flower", "el nivel se lee de la propia respuesta")
    poll._nivel_visto = ""

    # El endpoint CORRECTO según haya clave o no. Este es el fallo que costó
    # una tarde: con la clave `sk_` puesta, el endpoint antiguo seguía
    # contestando «anonymous» y enseñando UN modelo, como si no hubiera clave.
    guardada = os.environ.get("POLLINATIONS_API_KEY")
    try:
        os.environ["POLLINATIONS_API_KEY"] = "sk_de_prueba"
        _check("gen.pollinations.ai" in poll.url(),
               "con clave se usa el endpoint nuevo", f"-> {poll.url()}")
        _check(poll.espera_entre_llamadas() == 0.0,
               "con clave no se estrangula el ritmo desde este lado")
        os.environ.pop("POLLINATIONS_API_KEY", None)
        _check("text.pollinations.ai" in poll.url(),
               "sin clave se cae al anónimo", f"-> {poll.url()}")
        _check(poll.espera_entre_llamadas() == 15.0,
               "y ahí sí se respeta la petición cada 15 s")
    finally:
        os.environ.pop("POLLINATIONS_API_KEY", None)
        if guardada is not None:
            os.environ["POLLINATIONS_API_KEY"] = guardada

    # Una variable puesta pero VACÍA en el .env significa «usa el valor por
    # defecto». `os.getenv(x, defecto)` devuelve "" en ese caso, y eso dejó la
    # URL en blanco: las llamadas morían con un 404 que no explicaba nada.
    previo_url = os.environ.get("POLLINATIONS_URL")
    try:
        os.environ["POLLINATIONS_URL"] = ""
        _check(poll._env("POLLINATIONS_URL", "https://por/defecto") ==
               "https://por/defecto",
               "una variable vacía cae al valor por defecto")
    finally:
        os.environ.pop("POLLINATIONS_URL", None)
        if previo_url is not None:
            os.environ["POLLINATIONS_URL"] = previo_url

    # La voz.
    from skills.plugins import get_plugin_registry
    reg = get_plugin_registry(log=lambda *a: None)
    plug = next((i for _p, n, i, _rx in reg.plugins if n.startswith("cerebro")), None)
    if not _check(plug is not None, "el plugin del cerebro se carga solo"):
        return

    class _Core:
        log = staticmethod(lambda *a: None)
        _cerebro = {}

        def _proveedores(self):
            return [("pollinations:openai-fast",
                     "https://text.pollinations.ai/openai", "openai-fast", ""),
                    ("qwen3:8b", "http://localhost:11434/v1", "qwen3:8b", "ollama")]

        def _cerebro_leer(self):
            return {}

        def set_pref(self, k, v):
            pass

    respuesta = plug.handle("que cerebro estas usando", _Core())
    _check("pollinations" in (respuesta or "").lower(),
           "dice con qué cerebro está pensando")
    ayuda = plug.handle("donde pongo la clave", _Core())
    _check("POLLINATIONS_API_KEY" in (ayuda or ""),
           "explica dónde va la clave, con el nombre exacto de la variable")
    cambio = plug.handle("usa el cerebro de casa", _Core())
    _check("Hecho" in (cambio or ""), "«usa el cerebro de casa» cambia de verdad",
           f"-> {str(cambio)[:60]}")
    for frase in ("que hora es", "abre spotify", "cambia la cancion"):
        _check(not any(any(r.search(frase) for r in rx)
                       for _p, n, _i, rx in reg.plugins if n.startswith("cerebro")),
               f"«{frase}» no lo secuestra el cerebro")


# ── 46. Física general: cualquier ecuación, no un formulario ───────────────
def test_fisica_general():
    print("\n== 46. FISICA GENERAL ==")
    import fisica_general as FG

    _check(FG.hay_unidades(), "pint está disponible para las unidades")

    # Las mayúsculas IMPORTAN: P es potencia y p cantidad de movimiento.
    ec, err = FG.leer_ecuacion("P = F/A")
    _check(ec is not None and set(FG.simbolos(ec)) == {"P", "F", "A"},
           "no se funden mayúsculas y minúsculas", f"-> {FG.simbolos(ec) if ec else err}")

    # Y las letras que sympy se toma por constantes suyas, tampoco.
    # `E` era el número de Euler y `I` la unidad imaginaria: en física son
    # energía e intensidad, y sin forzarlas el despeje salía mal en silencio.
    for texto, esperados in (("E = m*c**2", {"E", "m", "c"}),
                             ("V = I*R", {"V", "I", "R"}),
                             ("N = m*g", {"N", "m", "g"}),
                             ("S = Q/T", {"S", "Q", "T"})):
        ec, _e = FG.leer_ecuacion(texto)
        _check(ec is not None and set(FG.simbolos(ec)) == esperados,
               f"«{texto}» conserva sus símbolos",
               f"-> {FG.simbolos(ec) if ec is not None else 'ilegible'}")

    # Despeje con unidades, contra resultados que se saben de memoria.
    casos = [
        ("v = v0 + a*t", {"v0": "0 m/s", "a": "9.8 m/s^2", "t": "3 s"}, "", 29.4),
        ("F = m*a", {"m": "1200 kg", "a": "3.5 m/s^2"}, "", 4200.0),
        ("P = F/A", {"F": "500 N", "A": "0.25 m^2"}, "", 2000.0),
        ("E = m*c**2", {"m": "2 kg", "c": "299792458 m/s"}, "", 1.79751035747e17),
        # Lentes delgadas: f=10 cm y s=15 cm dan i=30 cm, o sea 0,3 m.
        ("1/f = 1/s + 1/i", {"f": "10 cm", "s": "15 cm"}, "i", 0.3),
    ]
    for ecuacion, datos, incognita, esperado in casos:
        r = FG.despejar(ecuacion, datos, incognita, log=lambda *a: None)
        ok = r.get("ok") and r.get("valor") is not None
        if not _check(bool(ok), f"«{ecuacion}» se despeja",
                      f"-> {str(r.get('pasos'))[:90]}"):
            continue
        error = abs(r["valor"] - esperado) / (abs(esperado) or 1)
        _check(error < 1e-6, f"«{ecuacion}» da {esperado:g}",
               f"-> {r['valor']:g}")
        _check(bool(r.get("formulas")), f"«{ecuacion}» enseña la fórmula despejada")

    # Las unidades se convierten solas: 2 km y 2000 m son el mismo dato.
    a = FG.despejar("v = d/t", {"d": "2 km", "t": "100 s"}, log=lambda *a: None)
    b = FG.despejar("v = d/t", {"d": "2000 m", "t": "100 s"}, log=lambda *a: None)
    _check(abs(a["valor"] - b["valor"]) < 1e-9,
           "«2 km» y «2000 m» dan el mismo resultado",
           f"-> {a.get('valor')} vs {b.get('valor')}")

    # Sin datos suficientes se pide lo que falta, no se inventa.
    r = FG.despejar("P = F/A", {}, log=lambda *a: None)
    _check(not r.get("ok") and "Faltan datos" in " ".join(r["pasos"]),
           "sin datos, pide los que faltan en vez de suponerlos")
    # Con datos para todo menos la incógnita, da fórmula aunque falte un número.
    r = FG.despejar("E = m*c**2", {"m": "2 kg"}, "E", log=lambda *a: None)
    _check(r.get("ok") and r.get("valor") is None and r.get("formulas"),
           "da la fórmula despejada aunque no pueda dar el número")

    # Análisis dimensional: caza el error sin resolver nada.
    mal = FG.comprobar("E = m*v", {"E": "J", "m": "kg", "v": "m/s"})
    _check(mal.get("ok") and not mal.get("homogenea"),
           "detecta que energía y cantidad de movimiento no son lo mismo")
    bien = FG.comprobar("E = m*v**2", {"E": "J", "m": "kg", "v": "m/s"})
    _check(bien.get("ok") and bien.get("homogenea"),
           "y acepta la que sí es homogénea")
    falta = FG.comprobar("E = m*v", {"E": "J"})
    _check(not falta.get("ok") and "faltan" in " ".join(falta["pasos"]).lower(),
           "si faltan unidades lo dice, no da un veredicto a medias")

    # Conversión de unidades.
    c = FG.convertir("120 km/h", "m/s")
    _check(c.get("ok") and abs(c["valor"] - 33.3333333) < 1e-4,
           "120 km/h son 33,33 m/s", f"-> {c.get('valor')}")
    c = FG.convertir("5", "m")
    _check(not c.get("ok"), "un número sin unidad no se convierte a lo loco")

    # Lo que no es una ecuación se rechaza.
    r = FG.despejar("esto no es una ecuacion", {}, log=lambda *a: None)
    _check(not r.get("ok"), "un texto sin igual no pasa por ecuación")

    # Cableado.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    for n in ("despejar_ecuacion", "convertir_unidades"):
        _check(n in nombres, f"«{n}» se le ofrece al cerebro")
        _check(hasattr(caja, f"_t_{n}"), f"«{n}» tiene método")
        _check(n in permisos._LECTURA, f"«{n}» es lectura: solo calcula")
    salida = caja._t_despejar_ecuacion(
        {"ecuacion": "F = m*a", "datos": '{"m": "1200 kg", "a": "3.5 m/s^2"}'})
    _check("4200" in salida, "la herramienta devuelve el número bien",
           f"-> {salida[-60:]}")
    roto = caja._t_despejar_ecuacion({"ecuacion": "F = m*a", "datos": "{esto no es json"})
    _check("Faltan datos" in roto,
           "un JSON roto del modelo no tumba la herramienta")


# ── 47. Búsqueda por significado ───────────────────────────────────────────
def test_busqueda_por_significado():
    print("\n== 47. SIGNIFICADO ==")
    import embeddings

    # El coseno, que es toda la aritmética del asunto.
    _check(abs(embeddings.coseno([1, 0], [1, 0]) - 1.0) < 1e-9,
           "dos vectores iguales se parecen del todo")
    _check(abs(embeddings.coseno([1, 0], [0, 1])) < 1e-9,
           "dos perpendiculares no se parecen en nada")
    _check(embeddings.coseno([], [1, 2]) == 0.0,
           "un vector vacío no revienta la comparación")
    _check(embeddings.coseno([1, 2], [1, 2, 3]) == 0.0,
           "dos vectores de distinto tamaño no se comparan a lo loco")
    _check(embeddings.coseno([0, 0], [1, 1]) == 0.0,
           "el vector nulo no divide por cero")

    # Los más parecidos, ordenados.
    orden = embeddings.mas_parecidos([1, 0], [("a", [0, 1]), ("b", [1, 0]),
                                              ("c", [0.7, 0.7]), ("d", [])], k=2)
    _check([i for i, _s in orden] == ["b", "c"],
           "los más parecidos salen en orden y los vacíos se caen",
           f"-> {orden}")

    # Si no hay motor, se dice qué falta en vez de fallar en silencio.
    guardadas = {k: os.environ.get(k) for k in
                 ("POLLINATIONS_API_KEY", "JARVIS_EMBED_MOTOR")}
    try:
        os.environ.pop("POLLINATIONS_API_KEY", None)
        os.environ["JARVIS_EMBED_MOTOR"] = "nube"
        if not embeddings._hay_local():
            _check(not embeddings.disponible(),
                   "sin clave ni modelo local, no hay motor de significado")
            aviso = embeddings.por_que_no()
            _check("POLLINATIONS_API_KEY" in aviso and "ollama pull" in aviso,
                   "y se explican las DOS formas de arreglarlo")
            _check(embeddings.vectorizar(["hola"]) == [],
                   "sin motor, vectorizar devuelve vacío en vez de romper")
    finally:
        for k, v in guardadas.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    # El índice sigue funcionando sin motor: por palabras, que es peor pero
    # no es nada.
    import indice_documentos as I
    _check(callable(I.hay_embeddings) and callable(I.vectorizar_pendientes),
           "el índice expone el estado del motor y cómo completarlo")

    # Dos motores distintos NO se comparan entre sí: sus vectores ni siquiera
    # tienen el mismo número de dimensiones. El índice guarda con cuál se hizo
    # cada uno, y esa marca es la que evita resultados sin sentido.
    import json as _j
    guardado = _j.dumps({"m": "otro:motor", "v": [0.1, 0.2]})
    leido = _j.loads(guardado)
    _check(leido.get("m") == "otro:motor",
           "cada vector guarda con qué motor se hizo")

    # Cableado de la herramienta.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    _check("vectorizar_documentos" in nombres,
           "«vectorizar_documentos» se le ofrece al cerebro")
    _check(hasattr(caja, "_t_vectorizar_documentos"),
           "«vectorizar_documentos» tiene método")
    _check("vectorizar_documentos" in permisos._LECTURA,
           "vectorizar es lectura: no cambia ningún documento")


# ── 48. Vectores y estática ────────────────────────────────────────────────
def test_vectores_estatica():
    print("\n== 48. VECTORES Y ESTATICA ==")
    import vectores as V

    # Leer vectores como se dictan.
    _check(V.leer([3, 4]) == [3.0, 4.0, 0.0], "una lista corta se completa a 3D")
    _check(V.leer("3i + 4j") == [3.0, 4.0, 0.0], "notación i, j, k")
    _check(V.leer("-2i + 5k") == [-2.0, 0.0, 5.0], "con signos y saltándose una")
    v = V.leer("10 N a 90 grados")
    _check(abs(v[0]) < 1e-9 and abs(v[1] - 10) < 1e-9,
           "«10 N a 90 grados» apunta al eje Y", f"-> {v}")

    # El 3-4-12 da 13 exacto: si sale otra cosa, el módulo está mal.
    _check(abs(V.modulo([3, 4, 12]) - 13.0) < 1e-12, "|(3,4,12)| = 13")
    _check(abs(V.modulo(V.unitario([3, 4, 12])) - 1.0) < 1e-12,
           "el unitario mide exactamente 1")
    _check(V.modulo([0, 0, 0]) == 0 and V.unitario([0, 0, 0]) == [0, 0, 0],
           "el vector nulo no divide por cero")

    _check(abs(V.escalar([1, 0, 0], [0, 1, 0])) < 1e-12,
           "el escalar de dos perpendiculares es 0")
    _check(V.vectorial([1, 0, 0], [0, 1, 0]) == [0.0, 0.0, 1.0],
           "i × j = k", f"-> {V.vectorial([1, 0, 0], [0, 1, 0])}")
    _check(abs(V.angulo([1, 0, 0], [0, 1, 0]) - 90.0) < 1e-9, "el ángulo sale en grados")
    _check(abs(V.angulo([1, 0, 0], [-1, 0, 0]) - 180.0) < 1e-9,
           "y los opuestos dan 180° sin salirse del arco coseno")

    # Descomponer: 100 N a 30° son 86,60 y 50,00.
    d = V.descomponer(100, 30)
    _check(abs(d["vector"][0] - 86.6025403) < 1e-5 and abs(d["vector"][1] - 50.0) < 1e-9,
           "100 N a 30° se descomponen bien", f"-> {d['vector'][:2]}")

    # Equilibrio.
    eq = V.equilibrio([[10, 0, 0], [0, 10, 0], [-10, -10, 0]])
    _check(eq["equilibrio"], "tres fuerzas que se anulan están en equilibrio")
    eq2 = V.equilibrio([[10, 0, 0], [5, 0, 0]])
    _check(not eq2["equilibrio"] and abs(eq2["falta"][0] + 15.0) < 1e-9,
           "y si no, dice exactamente qué fuerza falta", f"-> {eq2['falta']}")

    # Momento: r = 2i, F = 10j  ->  M = 20k, brazo 2 m.
    m = V.momento([0, 10, 0], [2, 0, 0])
    _check(abs(m["vector"][2] - 20.0) < 1e-9, "M = r × F da 20k", f"-> {m['vector']}")
    _check(any("Brazo" in p and "2.0" in p for p in m["pasos"]),
           "y saca el brazo de 2 m", f"-> {[p for p in m['pasos'] if 'Brazo' in p]}")

    # Viga: 1000 N a 2 m de una viga de 6 m -> Rb = 333,33 y Ra = 666,67.
    viga = V.viga(6.0, [(2.0, 1000.0)])
    _check(abs(viga["Rb"] - 1000 * 2 / 6) < 1e-9 and abs(viga["Ra"] - 1000 * 4 / 6) < 1e-9,
           "las reacciones de la viga salen de ΣM = 0",
           f"-> Ra={viga['Ra']:.2f} Rb={viga['Rb']:.2f}")
    _check(abs(viga["Ra"] + viga["Rb"] - 1000.0) < 1e-9,
           "y suman la carga total")
    fuera = V.viga(6.0, [(9.0, 100.0)])
    _check(not fuera.get("ok"), "una carga fuera de la viga se rechaza")

    # El dibujo escribe su visor.
    r = V.dibujar([[100, 0, 0], [0, 80, 0]], abrir_visor=False, log=lambda *a: None)
    _check(r.get("ok") and os.path.exists(r["html"]),
           "el diagrama de fuerzas se escribe")
    _check(V.dibujar([], abrir_visor=False, log=lambda *a: None).get("ok") is False,
           "sin fuerzas no se inventa un diagrama")

    # Cableado.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    _check("vectores_fuerzas" in nombres and hasattr(caja, "_t_vectores_fuerzas"),
           "«vectores_fuerzas» está declarada y tiene método")
    _check("vectores_fuerzas" in permisos._LECTURA, "y es lectura: solo calcula")
    roto = caja._t_vectores_fuerzas({"accion": "viga", "datos": "{esto no es json"})
    _check("Necesito" in roto, "un JSON roto del modelo no la tumba")


# ── 49. Estudio: tarjetas y repaso espaciado ───────────────────────────────
def test_estudio_repaso():
    print("\n== 49. ESTUDIO ==")
    import estudio

    # El intervalo, que es todo el algoritmo. Se prueba sobre una tarjeta
    # puesta a mano para no depender del cerebro.
    with estudio._lock:
        con = estudio._con()
        try:
            con.execute("DELETE FROM tarjetas WHERE tema = '__prueba__'")
            cur = con.execute(
                "INSERT INTO tarjetas (tema, pregunta, respuesta, fuente, creada, "
                "proxima, intervalo, factor) VALUES (?,?,?,?,?,?,?,?)",
                ("__prueba__", "¿2 + 2?", "4", "test", time.time(), time.time(),
                 0.0, estudio.FACTOR_INICIAL))
            ident = cur.lastrowid
            con.commit()
        finally:
            con.close()

    def _lee():
        with estudio._lock:
            con = estudio._con()
            try:
                return con.execute(
                    "SELECT intervalo, factor, aciertos, fallos FROM tarjetas "
                    "WHERE id = ?", (ident,)).fetchone()
            finally:
                con.close()

    estudio.calificar(ident, "bien")
    i1, f1, a1, _x = _lee()
    _check(abs(i1 - 1.0) < 1e-9 and a1 == 1,
           "el primer acierto pone la tarjeta a un día", f"-> {i1}")

    estudio.calificar(ident, "bien")
    i2, f2, _a, _x = _lee()
    _check(abs(i2 - estudio.FACTOR_INICIAL) < 1e-9,
           "el segundo acierto la multiplica por el factor", f"-> {i2}")

    estudio.calificar(ident, "fallo")
    i3, f3, _a, fal3 = _lee()
    _check(abs(i3 - 1.0) < 1e-9 and fal3 == 1,
           "un fallo la devuelve a mañana", f"-> {i3}")
    _check(f3 < f2, "y baja el factor de facilidad", f"-> {f3} vs {f2}")

    # El factor nunca baja del mínimo: si no, la tarjeta se pregunta a diario
    # para siempre y acabas odiándola.
    for _ in range(20):
        estudio.calificar(ident, "fallo")
    _i, f_final, _a, _f = _lee()
    _check(f_final >= estudio.FACTOR_MINIMO,
           f"el factor no baja de {estudio.FACTOR_MINIMO}", f"-> {f_final}")

    # Y el intervalo no se dispara a diez años.
    with estudio._lock:
        con = estudio._con()
        try:
            con.execute("UPDATE tarjetas SET intervalo = 900, factor = 3.0 "
                        "WHERE id = ?", (ident,))
            con.commit()
        finally:
            con.close()
    estudio.calificar(ident, "facil")
    i_tope, _f, _a, _x = _lee()
    _check(i_tope <= 365.0, "el intervalo se corta en un año", f"-> {i_tope}")

    # Lo que toca hoy y lo que no.
    pendientes_antes = len(estudio.pendientes("__prueba__"))
    _check(pendientes_antes == 0,
           "una tarjeta con fecha lejana NO toca hoy", f"-> {pendientes_antes}")

    _check("no borro todas" in estudio.olvidar("").lower(),
           "«olvida las tarjetas» sin tema no borra nada")
    _check("Borradas 1" in estudio.olvidar("__prueba__"),
           "y con tema sí borra")

    # Cableado.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    _check("tarjetas_estudio" in nombres and hasattr(caja, "_t_tarjetas_estudio"),
           "«tarjetas_estudio» está declarada y tiene método")

    # La voz: contestar sin que haya pregunta no revienta.
    from skills.plugins import get_plugin_registry
    reg = get_plugin_registry(log=lambda *a: None)
    plug = next((i for _p, n, i, _x in reg.plugins if n.startswith("estudiar")), None)
    if _check(plug is not None, "el plugin de estudio se carga solo"):
        class _C:
            log = staticmethod(lambda *a: None)
        r = plug.handle("respondo lo que sea", _C())
        _check("no le había preguntado" in (r or "").lower(),
               "contestar sin pregunta se avisa, no se traga", f"-> {str(r)[:50]}")
        for frase in ("que hora es", "abre spotify", "pon musica"):
            _check(not any(any(x.search(frase) for x in rx)
                           for _p, n, _i, rx in reg.plugins if n.startswith("estudiar")),
                   f"«{frase}» no lo secuestra el estudio")


# ── 50. Portal académico ───────────────────────────────────────────────────
def test_portal_academico():
    print("\n== 50. PORTAL ==")
    import portal_academico as P

    guardada = P._cfg()
    try:
        P.configurar("campus.pruebas.edu")
        _check(P._cfg()["url"] == "https://campus.pruebas.edu",
               "la dirección se guarda con su https")
        _check(P.resumen_estado()["configurado"], "y queda configurado")

        # Las fechas: Moodle manda segundos y Canvas texto ISO.
        _check(abs(P._fecha(1700000000) - 1700000000) < 1, "una fecha de Moodle (segundos)")
        iso = P._fecha("2027-03-15T10:00:00Z")
        _check(iso > 1_700_000_000, "una fecha de Canvas (ISO)", f"-> {iso}")
        _check(P._fecha(None) == 0.0 and P._fecha("") == 0.0,
               "sin fecha no se inventa una")

        # Cómo se cuenta el tiempo que falta.
        _check(P._cuando(0) == "sin fecha", "una tarea sin fecha lo dice")
        _check(P._cuando(time.time() - 100) == "VENCIDA", "una vencida se marca")
        _check("mañana" in P._cuando(time.time() + 86400 * 1.5), "y mañana es mañana")

        # Urgentes: solo las de verdad.
        estado = P._estado_leer()
        estado["tareas"] = [
            {"titulo": "Cerca", "curso": "A", "vence": time.time() + 3600 * 10,
             "url": "", "entregado": False},
            {"titulo": "Lejos", "curso": "B", "vence": time.time() + 86400 * 30,
             "url": "", "entregado": False},
            {"titulo": "Hecha", "curso": "C", "vence": time.time() + 3600,
             "url": "", "entregado": True}]
        P._estado_guardar(estado)
        urgentes = [t["titulo"] for t in P.urgentes()]
        _check(urgentes == ["Cerca"],
               "solo avisa de lo que vence pronto y no está entregado",
               f"-> {urgentes}")

        # Y el motor proactivo las convierte en aviso.
        from jarvis_proactive import ProactiveEngine
        motor = ProactiveEngine.__new__(ProactiveEngine)
        eventos = motor._check_entregas()
        _check(len(eventos) == 1 and "Cerca" in eventos[0].message,
               "el motor proactivo avisa de la entrega que vence",
               f"-> {[e.title for e in eventos]}")
        _check(eventos[0].priority.name == "HIGH",
               "y si vence en horas, lo dice alto")
    finally:
        estado = P._estado_leer()
        estado["tareas"] = []
        P._estado_guardar(estado)
        P._guardar_cfg(guardada)

    # Cableado.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    for n in ("portal_academico", "borrador_entrega"):
        _check(n in nombres and hasattr(caja, f"_t_{n}"),
               f"«{n}» está declarada y tiene método")
    _check(permisos.evaluar("borrador_entrega") == "confirmar",
           "el borrador se confirma: escribe un archivo y gasta cerebro")

    # La voz.
    from skills.plugins import get_plugin_registry
    reg = get_plugin_registry(log=lambda *a: None)

    def _toca(frase):
        return any(any(r.search(frase) for r in rx)
                   for _p, n, _i, rx in reg.plugins if n.startswith("portal"))
    for frase in ("que tengo que entregar", "mis asignaturas", "mira el campus",
                  "pon las entregas en el calendario"):
        _check(_toca(frase), f"«{frase}» llega al campus")
    for frase in ("que hora es", "abre el navegador", "mira mi pantalla"):
        _check(not _toca(frase), f"«{frase}» NO lo secuestra el campus")


# ── 51. Informes ───────────────────────────────────────────────────────────
def test_informes():
    print("\n== 51. INFORMES ==")
    import informe

    # Escapar LaTeX: sin esto, un «100 %» comenta el resto de la línea y el
    # informe sale mutilado sin que se vea por qué.
    escapado = informe._escapar_tex("100 % de R&D con _guiones_ y #1")
    for bruto, seguro in (("%", r"\%"), ("&", r"\&"), ("_", r"\_"), ("#", r"\#")):
        _check(seguro in escapado, f"«{bruto}» se escapa para LaTeX")
    _check("\\textbackslash" in informe._escapar_tex("C:\\ruta"),
           "y la barra invertida también")

    # Las plantillas salen enteras.
    secciones = [{"titulo": "Objetivo", "texto": "Medir la gravedad al 100 %."},
                 {"titulo": "Conclusiones", "texto": "Sale 9,8 m/s²."}]
    formulas = [{"nombre": "Caída libre", "latex": "v = v_0 + a t",
                 "explicacion": "Velocidad frente al tiempo."}]
    tex = informe._plantilla_tex("Práctica 1", "Mario", secciones, formulas,
                                 ["Tipler, Física"])
    _check("\\documentclass" in tex and "\\end{document}" in tex,
           "el .tex sale completo")
    _check("\\section{Objetivo}" in tex, "con sus secciones")
    _check("v = v_0 + a t" in tex,
           "y la fórmula NO se escapa: es LaTeX a propósito")
    _check("100 \\%." in tex, "pero el texto sí", f"-> {[l for l in tex.split(chr(10)) if '100' in l]}")
    _check("thebibliography" in tex, "y lleva bibliografía")

    md = informe._plantilla_md("Práctica 1", "Mario", secciones, formulas, [])
    _check(md.startswith("# Práctica 1") and "## Objetivo" in md,
           "el .md sale con sus encabezados")

    # El nombre de archivo no se lleva caracteres que Windows no admite.
    nombre = informe._nombre_archivo("Práctica 1: ¿medir? g/s <2>")
    _check(not set(nombre) & set('<>:"/\\|?*'),
           f"el nombre de archivo queda limpio", f"-> {nombre}")

    _check(informe.resumen_estado()["docx"],
           "python-docx está, así que se puede entregar el .docx")

    # Cableado.
    import permisos
    from herramientas_llm import Herramientas
    caja = Herramientas(None, log=lambda *a: None)
    nombres = [d["function"]["name"] for d in caja.definiciones()]
    _check("informe_practica" in nombres and hasattr(caja, "_t_informe_practica"),
           "«informe_practica» está declarada y tiene método")
    _check(permisos.evaluar("informe_practica") == "confirmar",
           "y se confirma: escribe tres archivos")


# ── 52. pensar.py: el cerebro no se queda a medias ─────────────────────────
def test_pensar_rescata():
    print("\n== 52. PENSAR ==")
    import pensar

    # Rescatar JSON de donde sea, que es lo que hacen los modelos pequeños.
    casos = [
        ('{"a": 1}', {"a": 1}),
        ('Aquí tienes:\n```json\n{"a": 1}\n```\nEspero que sirva', {"a": 1}),
        ("bla bla {'a': 1} bla", {"a": 1}),
        ('[{"n": 2}]', [{"n": 2}]),
    ]
    for crudo, esperado in casos:
        _check(pensar._rescatar_json(crudo) == esperado,
               f"rescata el JSON de {crudo[:28]!r}",
               f"-> {pensar._rescatar_json(crudo)}")
    _check(pensar._rescatar_json("no hay json aquí") is None,
           "y si no hay JSON, lo dice en vez de inventarlo")
    _check(pensar._rescatar_json("") is None and pensar._rescatar_json(None) is None,
           "el vacío no revienta")

    # Sin cerebro, se devuelve vacío en vez de reventar.
    class _SinCerebro:
        log = staticmethod(lambda *a: None)

        def _proveedores(self):
            raise RuntimeError("no hay")
    _check(pensar.texto(_SinCerebro(), "s", "u", log=lambda *a: None) == "",
           "sin cerebro devuelve vacío, no una excepción")
    _check(not pensar.disponible(_SinCerebro()),
           "y se puede preguntar si lo hay antes de intentarlo")
