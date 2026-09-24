#!/usr/bin/env python3
"""
arrancar_ambos.py - JARVIS y ULTRON a la vez, con sus dos webs abiertas
=======================================================================
Levanta los dos asistentes en paralelo y abre ORIGEN, la interfaz de JARVIS
(los modulos de ULTRON y el Consejo estan dentro), sin teclear ningun PIN.

    JARVIS  http://localhost:5000         ORIGEN
    ULTRON  http://localhost:8766         su propia web (--clasico)

Lo que hace, en orden:

  1. comprueba que Ollama responde, y lo levanta si no,
  2. mira si alguno de los dos ya estaba corriendo (no lo mata: lo reutiliza),
  3. arranca los que falten, con sus registros en jarvis_log/ para poder ver
     por que ha fallado alguno si falla,
  4. espera a que cada uno conteste de verdad (no basta con que el proceso
     exista: hay que ver el puerto contestando),
  5. lee el PIN de cada interfaz y abre las pestañas con el token puesto,
  6. imprime tambien las direcciones de la red local, para el movil,
  7. se queda vigilando: si uno se cae lo dice, y con Ctrl+C los para a los dos.

Uso:
    python arrancar_ambos.py                 arranca todo y abre las webs
    python arrancar_ambos.py --sin-navegador arranca sin abrir pestañas
    python arrancar_ambos.py --solo-jarvis   solo JARVIS
    python arrancar_ambos.py --clasico       abre tambien la web de ULTRON
    python arrancar_ambos.py --solo-ultron   solo ULTRON
    python arrancar_ambos.py --reiniciar     mata lo que hubiera y arranca limpio

En Windows, `arrancar_ambos.bat` hace lo mismo con doble clic.

A diferencia de reiniciar_todo.py, este NO mata todos los pythonw del equipo
salvo que se lo pidas con --reiniciar: si ya tenias JARVIS abierto, se
aprovecha en vez de tirarlo.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

try:
    import consola_utf8  # noqa: F401   (salida legible en consolas cp1252)
except Exception:
    pass

from interprete import python_del_proyecto, explicar_si_falta, aviso_si_cambia

LOGS = os.path.join(RAIZ, "jarvis_log")

# (clave, nombre, carpeta, script, puerto, fichero del PIN, rutas a abrir)
AGENTES = {
    "jarvis": {
        "nombre": "JARVIS",
        "cwd": os.path.join(RAIZ, "web_interface"),
        "script": "app.py",
        "puerto": int(os.getenv("JARVIS_PORT", "5000")),
        "pin": os.path.join(RAIZ, "web_interface", ".jarvis_auth"),
        # ORIGEN es la única interfaz de JARVIS.
        "rutas": ["/"],
        "rutas_clasicas": ["/"],
        "entorno": {},
    },
    "ultron": {
        "nombre": "ULTRON",
        "cwd": os.path.join(RAIZ, "ultron_interface"),
        "script": "app.py",
        "puerto": int(os.getenv("ULTRON_PORT", "8766")),
        "pin": os.path.join(RAIZ, "ultron_interface", ".ultron_auth"),
        "rutas": [],                       # ULTRON se maneja desde el NEXUS
        "rutas_clasicas": ["/"],
        "entorno": {"ULTRON_MODE": "1"},
    },
}


# ── utilidades ──────────────────────────────────────────────────────────────
def puerto_ocupado(puerto: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex((host, puerto)) == 0


def ip_local() -> str:
    """IP de la red real (la que sirve para el móvil), no la de loopback."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        if ip and not ip.startswith(("127.", "169.254")):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def leer_pin(ruta: str) -> str:
    """PIN de una interfaz. Admite el formato nuevo (JSON) y el viejo (texto)."""
    try:
        with open(ruta, encoding="utf-8") as f:
            bruto = f.read().strip()
        if bruto.startswith("{"):
            return str(json.loads(bruto).get("token", ""))
        return bruto
    except Exception:
        return ""


def esperar(puerto: int, nombre: str, segundos: int = 60) -> bool:
    """Espera a que el puerto conteste de verdad, no solo a que exista el proceso."""
    inicio = time.time()
    punto = 0
    while time.time() - inicio < segundos:
        if puerto_ocupado(puerto):
            print(f"\r  [OK]  {nombre} responde en el puerto {puerto}"
                  f" ({time.time() - inicio:.0f}s)      ")
            return True
        punto = (punto + 1) % 4
        print(f"\r  ...   esperando a {nombre}{'.' * punto}{' ' * (3 - punto)}",
              end="", flush=True)
        time.sleep(1.0)
    print(f"\r  [ERR] {nombre} no respondió en {segundos}s.            ")
    return False


# ── Ollama ──────────────────────────────────────────────────────────────────
def asegurar_ollama() -> bool:
    """Sin cerebro los dos arrancan igual, pero solo ejecutan habilidades."""
    base = os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1").replace("/v1", "")
    try:
        urllib.request.urlopen(f"{base}/api/tags", timeout=4)
        print("  [OK]  Ollama ya estaba en marcha")
        return True
    except Exception:
        pass

    print("  ...   Ollama no responde: lo levanto")
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags)
    except FileNotFoundError:
        print("  [!]   Ollama no está instalado: ambos funcionarán sin cerebro.")
        return False
    except Exception as e:
        print(f"  [!]   No pude lanzar Ollama: {e}")
        return False

    for _ in range(20):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{base}/api/tags", timeout=3)
            print("  [OK]  Ollama en marcha")
            return True
        except Exception:
            continue
    print("  [!]   Ollama tarda demasiado; sigo sin esperarlo más.")
    return False


# ── arranque ────────────────────────────────────────────────────────────────
def arrancar(clave: str, cfg: dict, ventanas: bool = False):
    """Lanza un agente. Devuelve el proceso, o None si ya estaba corriendo."""
    if puerto_ocupado(cfg["puerto"]):
        print(f"  [=]   {cfg['nombre']} ya estaba corriendo en {cfg['puerto']}: "
              "lo aprovecho")
        return None

    os.makedirs(LOGS, exist_ok=True)
    registro = os.path.join(LOGS, f"web_{clave}.log")
    salida = open(registro, "a", encoding="utf-8", errors="ignore")
    salida.write(f"\n===== arranque {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    salida.flush()

    entorno = os.environ.copy()
    entorno.update(cfg["entorno"])
    # Evita la cascada de bots: el hijo no debe relanzar otro Telegram.
    entorno.setdefault("JARVIS_TELEGRAM_CHILD", "1")

    flags = 0
    if os.name == "nt" and not ventanas:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # No se lanza con `sys.executable` a ciegas: si el PATH cambia de orden
    # (basta con instalar otro Python) ese seria uno vacio y el hijo moriria
    # con un ModuleNotFoundError. Se usa el que tiene las dependencias.
    exe = python_del_proyecto() or sys.executable
    proceso = subprocess.Popen(
        [exe, cfg["script"]],
        cwd=cfg["cwd"], env=entorno,
        stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        creationflags=flags)
    print(f"  [>]   {cfg['nombre']} lanzado (PID {proceso.pid}, "
          f"registro en jarvis_log/web_{clave}.log)")
    return proceso


def abrir_navegador(cfg: dict, pausa: float = 1.2, clasico: bool = False):
    """Abre las pestañas de un agente con su PIN ya puesto."""
    rutas = cfg["rutas_clasicas"] if clasico else cfg["rutas"]
    if not rutas:
        return
    pin = leer_pin(cfg["pin"])
    if not pin:
        print(f"  [!]   No encontré el PIN de {cfg['nombre']}: abro sin token "
              "(tendrá que escribirlo).")
    for ruta in rutas:
        url = f"http://localhost:{cfg['puerto']}{ruta}"
        if pin:
            url += f"?token={pin}"
        webbrowser.open_new_tab(url)
        time.sleep(pausa)


def matar_previos():
    """Solo con --reiniciar: tira lo que hubiera escuchando en esos puertos."""
    if os.name != "nt":
        subprocess.run(["pkill", "-9", "-f", "web_interface/app.py"], check=False)
        subprocess.run(["pkill", "-9", "-f", "ultron_interface/app.py"], check=False)
        return
    for cfg in AGENTES.values():
        try:
            salida = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                    capture_output=True, text=True, timeout=20).stdout
        except Exception:
            return
        for linea in salida.splitlines():
            if f":{cfg['puerto']} " in linea and "LISTENING" in linea:
                pid = linea.split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               capture_output=True, check=False)
                print(f"  [x]   Cerrado el proceso {pid} que ocupaba "
                      f"el puerto {cfg['puerto']}")


# ── principal ───────────────────────────────────────────────────────────────
def main(argv) -> int:
    sin_navegador = "--sin-navegador" in argv
    con_ventanas = "--ventanas" in argv
    solo = None
    if "--solo-jarvis" in argv:
        solo = "jarvis"
    elif "--solo-ultron" in argv:
        solo = "ultron"

    elegidos = {k: v for k, v in AGENTES.items() if solo is None or k == solo}

    print("=" * 62)
    print("  JARVIS + ULTRON — arranque conjunto")
    print("=" * 62)

    if "--reiniciar" in argv:
        print("\n[1/5] Cerrando lo que hubiera abierto...")
        matar_previos()
        time.sleep(1.5)
    else:
        print("\n[1/5] Reutilizando lo que ya esté corriendo")

    print("\n[2/5] Cerebro local")
    asegurar_ollama()

    print("\n[3/5] Arrancando asistentes")
    # Antes de lanzar nada: comprobar que hay un Python con las dependencias.
    # Sin esto, el fallo aparecia 60 segundos despues y escondido en un log.
    exe = python_del_proyecto()
    if not exe:
        print("  [ERR] " + explicar_si_falta().replace("\n", "\n        "))
        return 3
    aviso = aviso_si_cambia(exe)
    if aviso:
        print(aviso)
    procesos = {}
    for clave, cfg in elegidos.items():
        try:
            procesos[clave] = arrancar(clave, cfg, ventanas=con_ventanas)
        except Exception as e:
            print(f"  [ERR] {cfg['nombre']} no arrancó: {e}")

    print("\n[4/5] Esperando a que respondan")
    vivos = {}
    for clave, cfg in elegidos.items():
        if esperar(cfg["puerto"], cfg["nombre"]):
            vivos[clave] = cfg
        else:
            registro = os.path.join(LOGS, f"web_{clave}.log")
            print(f"        Mire {registro} para ver por qué.")

    if not vivos:
        print("\nNo ha arrancado ninguno. Revise los registros de jarvis_log/.")
        return 1

    print("\n[5/5] Abriendo las interfaces")
    clasico = "--clasico" in argv
    if sin_navegador:
        print("  [=]   --sin-navegador: no abro pestañas")
    elif clasico:
        for cfg in vivos.values():
            abrir_navegador(cfg, clasico=True)
    else:
        # Una sola pestaña: ORIGEN (sus módulos hablan también con ULTRON).
        abrir_navegador(vivos.get("jarvis") or list(vivos.values())[0])

    ip = ip_local()
    print("\n" + "=" * 62)
    for clave, cfg in vivos.items():
        pin = leer_pin(cfg["pin"]) or "sin PIN"
        print(f"  {cfg['nombre']:<7} http://localhost:{cfg['puerto']}"
              f"      PIN {pin}")
        print(f"          desde el móvil: http://{ip}:{cfg['puerto']}/mobile")
    print("=" * 62)
    print("  Ctrl+C para parar los que haya arrancado este lanzador.\n")

    # Vigilancia: si uno se cae, se dice; no se reinicia solo porque de eso ya
    # se encarga el vigilante interno de cada núcleo.
    try:
        while True:
            time.sleep(5)
            for clave, proceso in list(procesos.items()):
                if proceso is not None and proceso.poll() is not None:
                    print(f"  [!]   {AGENTES[clave]['nombre']} se ha cerrado "
                          f"(código {proceso.returncode}). "
                          f"Registro: jarvis_log/web_{clave}.log")
                    procesos.pop(clave)
            if procesos and not any(p is not None for p in procesos.values()):
                # Todos los que arrancamos aquí eran reutilizados: nada que vigilar.
                break
    except KeyboardInterrupt:
        print("\n  Parando lo que arranqué...")
        for clave, proceso in procesos.items():
            if proceso is None:
                continue
            try:
                proceso.terminate()
                proceso.wait(timeout=8)
                print(f"  [x]   {AGENTES[clave]['nombre']} detenido")
            except Exception:
                try:
                    proceso.kill()
                except Exception:
                    pass
        print("  Hasta luego, señor.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
