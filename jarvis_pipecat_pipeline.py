#!/usr/bin/env python3
"""Jarvis - modo consola funcional con Ollama y TTS opcional."""

import sys
from pathlib import Path

# Configuracion automatica de rutas
PROJECT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))

print("=" * 60)
print("JARVIS - Asistente Omnimodal Autonomo")
print("=" * 60)
print("Directorio del proyecto: " + str(PROJECT_DIR))
print()

print("Modo consola: usa el mismo núcleo que la interfaz gráfica.")
print("=" * 60)
print()

def run_console():
    """Modo de respaldo funcional: cada texto se envía al núcleo real."""
    try:
        from jarvis_core import JarvisCore
    except ImportError as exc:
        print(f"No se pudo cargar el núcleo de Jarvis: {exc}")
        return 1

    core = JarvisCore()
    print("  Modo consola funcional iniciado.")
    print("  Escribe una pregunta para Jarvis. Usa 'salir' para cerrar.")
    print()
    try:
        while True:
            try:
                linea = input(">>> ").strip()
            except EOFError:
                break
            if not linea:
                continue
            if linea.lower() in {"salir", "exit", "quit"}:
                break

            respuesta = core.process_text_stream(linea)
            print(f"JARVIS: {respuesta}")
    except KeyboardInterrupt:
        print()
    finally:
        core.shutdown()

    print("JARVIS: Sesión finalizada. Mantén la calma y la lógica.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_console())
