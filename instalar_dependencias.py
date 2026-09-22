#!/usr/bin/env python3
"""
instalar_dependencias.py - Instala lo que JARVIS necesita, sin rendirse a la primera.

Por que existe este fichero en vez de un `pip install -r requirements.txt` a secas:
pip resuelve el fichero ENTERO antes de instalar nada, asi que una unica linea
mala (una ruta que no existe, un paquete sin rueda para tu version de Python)
deja el sistema sin NINGUNA dependencia. Eso es justo lo que pasaba aqui, y por
eso faltaban qrcode, Pillow y media docena mas.

Aqui se instala en dos pasadas:
  1. El fichero de golpe, que es lo rapido cuando todo va bien.
  2. Si eso falla, paquete a paquete, para que lo que si se pueda instalar se
     instale y al final se diga exactamente que ha quedado fuera y para que
     servia.

Uso:
    python instalar_dependencias.py              # lo imprescindible
    python instalar_dependencias.py --extras     # tambien los opcionales
    python instalar_dependencias.py --comprobar  # no instala, solo informa
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consola_utf8  # noqa: F401  (salida a prueba de cp1252)

RAIZ = os.path.dirname(os.path.abspath(__file__))

# Que se rompe si falta cada cosa. Se usa para el informe final: un nombre de
# paquete no le dice nada a nadie, «el QR de emparejamiento» si.
PARA_QUE_SIRVE = {
    "openai": "hablar con el modelo de IA (imprescindible)",
    "flask": "el servidor web y la interfaz movil (imprescindible)",
    "flask_socketio": "el chat en tiempo real con el movil (imprescindible)",
    "qrcode": "el QR de emparejar el telefono (hay respaldo propio en jarvis_qr.py)",
    "PIL": "capturas de pantalla, ver el escritorio desde el movil y el QR en PNG",
    "pyautogui": "control del raton y el teclado del PC",
    "pynput": "atajos de teclado globales",
    "pyperclip": "copiar y pegar entre el movil y el PC",
    "speech_recognition": "escuchar por el microfono del PC",
    "pyttsx3": "la voz de Windows cuando ElevenLabs no responde",
    "customtkinter": "la ventana HUD de escritorio",
    "googleapiclient": "Google Calendar",
    "google_auth_oauthlib": "autorizar la cuenta de Google",
    "bs4": "leer paginas web",
    "numpy": "calculos de las habilidades",
    "yt_dlp": "descargar videos de YouTube",
    "ddgs": "buscar en internet",
    "cv2": "la camara",
    "openpyxl": "generar hojas de Excel",
    "docx": "generar documentos Word",
    "pptx": "generar presentaciones PowerPoint",
    "reportlab": "generar PDFs",
    "matplotlib": "generar graficas",
    "psutil": "telemetria del sistema (CPU, RAM, disco)",
    "dotenv": "leer el fichero .env",
    "requests": "peticiones HTTP (imprescindible)",
    # Opcionales
    "faster_whisper": "transcribir la voz que llega DESDE el movil y dictado local sin nube",
    "pygame": "reproducir la voz sin abrir el reproductor de Windows",
    "mem0": "memoria semantica avanzada",
    "pyaudio": "microfono del PC (escucha continua y palabra de activacion)",
    "sklearn": "clasificador de intenciones que aprende de tus ordenes",
}

# modulo que se importa -> paquete que hay que instalar (no siempre coinciden)
MODULO_A_PAQUETE = {
    "PIL": "Pillow",
    "flask_socketio": "flask-socketio",
    "speech_recognition": "SpeechRecognition",
    "googleapiclient": "google-api-python-client",
    "google_auth_oauthlib": "google-auth-oauthlib",
    "bs4": "beautifulsoup4",
    "yt_dlp": "yt-dlp",
    "cv2": "opencv-python",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "dotenv": "python-dotenv",
    "faster_whisper": "faster-whisper",
    "mem0": "mem0ai",
    "sklearn": "scikit-learn",
    "pyaudio": "pyaudio",
}

IMPRESCINDIBLES = ["openai", "flask", "flask_socketio", "requests", "psutil", "dotenv"]


def falta(modulo):
    import importlib.util
    try:
        return importlib.util.find_spec(modulo) is None
    except (ImportError, ValueError):
        return True


def pip(*args, silencioso=True):
    orden = [sys.executable, "-m", "pip", "install", *args]
    if silencioso:
        orden.append("--quiet")
    try:
        return subprocess.run(orden, timeout=1800).returncode == 0
    except Exception:
        return False


def paquetes_de(fichero):
    """Nombres de paquete de un requirements, sin comentarios ni vacios."""
    ruta = os.path.join(RAIZ, fichero)
    if not os.path.isfile(ruta):
        return []
    salida = []
    for linea in open(ruta, encoding="utf-8"):
        linea = linea.split("#")[0].strip()
        if linea:
            salida.append(linea)
    return salida


def instalar(fichero, titulo):
    """Instala un requirements. Devuelve la lista de paquetes que fallaron."""
    print(f"\n  {titulo}")
    print(f"  {'-' * len(titulo)}")
    if pip("-r", os.path.join(RAIZ, fichero)):
        print("  Todo instalado de una pasada.")
        return []
    # La pasada conjunta ha fallado: vamos uno por uno para salvar el resto.
    print("  La instalacion conjunta ha fallado. Voy paquete a paquete...")
    fallidos = []
    for paquete in paquetes_de(fichero):
        nombre = paquete.split(">")[0].split("=")[0].split("[")[0].strip()
        if pip(paquete):
            print(f"    [OK]    {nombre}")
        else:
            print(f"    [FALLO] {nombre}")
            fallidos.append(nombre)
    return fallidos


def informe():
    """Que falta ahora mismo y para que servia."""
    ausentes = [(m, PARA_QUE_SIRVE[m]) for m in PARA_QUE_SIRVE if falta(m)]
    criticos = [m for m in IMPRESCINDIBLES if falta(m)]

    print("\n" + "=" * 64)
    if not ausentes:
        print("  TODO LISTO. No falta ninguna dependencia.")
        print("=" * 64)
        return 0

    if criticos:
        print("  FALTAN DEPENDENCIAS IMPRESCINDIBLES")
        print("=" * 64)
        for m in criticos:
            print(f"    {MODULO_A_PAQUETE.get(m, m)}  ->  {PARA_QUE_SIRVE[m]}")
        print("\n  JARVIS no va a arrancar asi. Instalalas con:")
        print(f'    "{sys.executable}" -m pip install '
              + " ".join(MODULO_A_PAQUETE.get(m, m) for m in criticos))
        print("=" * 64)
        return 1

    print("  JARVIS funciona, pero estas cosas quedaran desactivadas:")
    print("=" * 64)
    for m, para in ausentes:
        print(f"    {MODULO_A_PAQUETE.get(m, m):26s} {para}")
    print("\n  Para intentar instalarlas:")
    print(f'    "{sys.executable}" -m pip install '
          + " ".join(MODULO_A_PAQUETE.get(m, m) for m, _ in ausentes))
    print("=" * 64)
    return 0


def main():
    print("=" * 64)
    print("  DEPENDENCIAS DE JARVIS")
    print(f"  Python {sys.version.split()[0]} en {sys.executable}")
    print("=" * 64)

    if "--comprobar" in sys.argv:
        return informe()

    pip("--upgrade", "pip")
    fallidos = instalar("requirements.txt", "Dependencias necesarias")

    if "--extras" in sys.argv:
        instalar("requirements-extra.txt", "Dependencias opcionales (pueden fallar)")

    if fallidos:
        print(f"\n  No pude instalar: {', '.join(fallidos)}")
    return informe()


if __name__ == "__main__":
    sys.exit(main())
