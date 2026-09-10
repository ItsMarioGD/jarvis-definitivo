#!/usr/bin/env python3
"""
jarvis.py - Puerta unica de entrada a JARVIS y ULTRON
=====================================================
En la raiz del proyecto habia mas de diez lanzadores (.bat y .ps1) sin ninguna
indicacion de cual era el bueno: start.bat, jarvis_start.bat, start_jarvis.bat,
jarvis_web_start.bat, start_flask.bat, start_server.bat, tester.bat... Elegir el
equivocado hace perder media hora depurando un fantasma. Los antiguos siguen
donde estaban (por si algun acceso directo apunta a ellos), pero a partir de
ahora solo hace falta recordar este:

    python jarvis.py                 HUD de escritorio de JARVIS
    python jarvis.py ultron          HUD de escritorio de ULTRON
    python jarvis.py web             interfaz web de JARVIS (movil incluido)
    python jarvis.py ultron-web      interfaz web de ULTRON
    python jarvis.py movil           QR de emparejamiento del telefono
    python jarvis.py estado          diagnostico: que hay listo y que falta
    python jarvis.py test            pruebas de regresion
    python jarvis.py instalar        instala las dependencias que falten

En Windows, `jarvis.bat <modo>` hace lo mismo desde el explorador.
"""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

MODOS = {
    "jarvis":      ("interfaz_jarvis.py",       "HUD de escritorio de JARVIS"),
    "ultron":      ("ultron_core.py",           "Núcleo/HUD de ULTRON"),
    "ambos":       ("arrancar_ambos.py",        "JARVIS y ULTRON a la vez, con sus dos webs"),
    "web":         ("web_interface/app.py",     "Interfaz web de JARVIS (y móvil)"),
    "ultron-web":  ("ultron_interface/app.py",  "Interfaz web de ULTRON"),
    "movil":       ("jarvis_qr.py",             "Código QR para emparejar el teléfono"),
    "test":        ("test_regresion.py",        "Pruebas de regresión"),
    "revisar":     ("revisar.py",               "Revisión del entorno"),
    "instalar":    ("instalar_dependencias.py", "Instalar dependencias que falten"),
    "copia":       ("cerebro_backup.py",        "Exportar/importar todo lo aprendido"),
    "colisiones":  ("colisiones.py",            "Ver qué habilidades se pisan"),
    "afinar":      ("afinar.py",                "Preparar el ajuste fino del modelo"),
    "actualizar":  ("actualizar.py",            "Actualizar con vuelta atrás si falla"),
    "servicio":    ("servicio.py",              "Arrancar solo con Windows"),
}

# Paquetes opcionales y para que sirve cada uno (se muestran en «estado»).
OPCIONALES = {
    "openai":           "hablar con el modelo (Ollama expone API compatible)",
    "speech_recognition": "escuchar por el micrófono del PC",
    "pyaudio":          "acceso al micrófono (lo necesita speech_recognition)",
    "faster_whisper":   "dictado local sin enviar la voz a la nube",
    "sklearn":          "clasificador de intenciones que aprende de sus órdenes",
    "psutil":           "telemetría y motor proactivo (CPU, batería, disco)",
    "flask":            "interfaz web y móvil",
    "pygame":           "reproducir la voz sin bloquear",
    "cv2":              "guardián facial de ULTRON",
    "requests":         "conectores y servicios externos",
}


def _python() -> str:
    """El Python que tiene las dependencias, no el primero del PATH."""
    try:
        from interprete import python_del_proyecto
        return python_del_proyecto() or sys.executable or "python"
    except Exception:
        return sys.executable or "python"


def lanzar(modo: str, extra) -> int:
    destino, _ = MODOS[modo]
    ruta = os.path.join(RAIZ, destino.replace("/", os.sep))
    if not os.path.exists(ruta):
        print(f"No encuentro {destino}. ¿Se movió el archivo?")
        return 2
    carpeta = os.path.dirname(ruta) or RAIZ
    print(f"→ {modo}: {destino}")
    return subprocess.call([_python(), os.path.basename(ruta), *extra], cwd=carpeta)


def estado() -> int:
    """Diagnóstico honesto: qué está listo, qué falta y para qué sirve."""
    print("JARVIS / ULTRON — estado del entorno\n" + "=" * 46)
    print(f"Python      : {sys.version.split()[0]}  ({sys.executable})")
    print(f"Proyecto    : {RAIZ}\n")

    import importlib.util
    faltan = []
    print("Dependencias:")
    for paquete, para_que in OPCIONALES.items():
        try:
            hay = importlib.util.find_spec(paquete) is not None
        except Exception:
            hay = False
        print(f"  [{'ok' if hay else '--'}] {paquete:<20} {para_que}")
        if not hay:
            faltan.append(paquete)

    print("\nMódulos del proyecto:")
    for modulo, para_que in (
            ("energia", "apagado/reinicio que obedece siempre"),
            ("ejecutor", "comandos con resultado verificado"),
            ("storage", "registro de acciones y eventos"),
            ("cognition", "motores cognitivos (riesgo, shell, ML)"),
            ("jarvis_escucha", "escucha continua con palabra de activación"),
            ("jarvis_proactive", "avisos proactivos"),
            ("self_healing", "auto-reparación de interfaces Android"),
            ("deshacer", "revertir acciones («deshaz eso»)"),
            ("vigilante", "supervisión del propio asistente"),
            ("privacidad", "modo privado verificable"),
            ("cerebro_backup", "exportar e importar la memoria"),
            ("herramientas_llm", "el cerebro ejecuta herramientas de verdad"),
            ("vision", "mirar la pantalla y entenderla"),
            ("piloto", "usar ratón y teclado como un humano"),
            ("sandbox", "ensayar una orden antes de ejecutarla"),
            ("canarios", "señuelos anti-ransomware"),
            ("modo_nocturno", "turno de noche autónomo"),
            ("prediccion", "hábitos y anticipación"),
            ("consejo", "deliberación JARVIS contra ULTRON"),
            ("enjambre", "agentes especialistas con presupuesto"),
            ("indice_documentos", "buscar dentro de sus documentos"),
            ("voz_identidad", "reconocer quién habla"),
            ("rebobinar", "memoria episódica de la pantalla"),
            ("autoskills", "escribirse habilidades a sí mismo"),
            ("colisiones", "detectar habilidades que se pisan"),
            ("recados", "filtrar mensajes y tomar recado"),
            ("relevo", "protocolo de inactividad"),
            ("cluster", "varios equipos, un asistente"),
            ("afinar", "ajuste fino del modelo (LoRA)"),
            ("arrepentimiento", "ventana para decir «no» tras actuar"),
            ("perfiles", "perfiles de contexto (trabajo, juego, noche)"),
            ("feedback", "valoraciones del señor"),
            ("metricas", "latencia y gasto"),
            ("audio_dispositivos", "elegir micrófono y altavoz"),
            ("orquestador", "parte del día y preparación anticipada"),
            ("actualizar", "actualización con vuelta atrás"),
            ("servicio", "arranque automático robusto")):
        try:
            __import__(modulo)
            print(f"  [ok] {modulo}: {para_que}")
        except Exception as e:
            print(f"  [--] {modulo}: {str(e)[:60]}")

    # Cerebro local
    try:
        import urllib.request
        base = os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1")
        urllib.request.urlopen(base.replace("/v1", "/api/tags"), timeout=3)
        print(f"\nOllama      : responde en {base}")
    except Exception:
        print("\nOllama      : no responde (arranque `ollama serve`)")

    try:
        from storage import get_storage
        r = get_storage().resumen(24)
        print(f"Actividad   : {r['acciones']} órdenes en 24 h, {r['fallos']} con error, "
              f"{r['eventos']} eventos")
    except Exception:
        pass

    if faltan:
        print("\nPara completar el equipo:")
        print(f"  {_python()} jarvis.py instalar")
        print("  (o: pip install " + " ".join(
            {"sklearn": "scikit-learn", "cv2": "opencv-python",
             "speech_recognition": "SpeechRecognition",
             "faster_whisper": "faster-whisper"}.get(p, p) for p in faltan) + ")")
    return 0


def ayuda() -> int:
    print(__doc__.strip())
    print("\nModos disponibles:")
    for modo, (destino, desc) in MODOS.items():
        print(f"  {modo:<12} {desc}")
    print(f"  {'estado':<12} Diagnóstico del entorno")
    print("\nAtajos útiles:")
    print("  python jarvis.py copia exportar            copia de seguridad del cerebro")
    print("  python jarvis.py copia importar <zip>      restaurarla en otro equipo")
    print("  python jarvis.py ambos                     los dos asistentes + sus webs")
    print("  python jarvis.py test                      pruebas de regresión")
    print("  python jarvis.py actualizar --probar       ¿hay versión nueva?")
    print("  python jarvis.py servicio instalar         arrancar con Windows")
    print("\nPanel de control: arranque la web y abra /panel?token=<PIN>")
    return 0


def main() -> int:
    args = sys.argv[1:]
    modo = (args[0].lower() if args else "jarvis")
    extra = args[1:]
    if modo in ("-h", "--help", "help", "ayuda"):
        return ayuda()
    if modo == "estado":
        return estado()
    if modo not in MODOS:
        print(f"Modo desconocido: {modo}\n")
        return ayuda()
    return lanzar(modo, extra)


if __name__ == "__main__":
    sys.exit(main())
