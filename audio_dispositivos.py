#!/usr/bin/env python3
"""
audio_dispositivos.py - Elegir microfono y altavoz
==================================================
Con la escucha continua encendida, el fallo mas frustrante posible es este: el
asistente esta funcionando perfectamente, escuchando por el microfono de una
webcam apagada que nadie recuerda que existe. No hay error, no hay aviso: solo
un JARVIS que «no oye».

Este modulo lista lo que hay, deja elegir y recuerda la eleccion:

    «que microfonos tienes»          -> lista numerada
    «usa el microfono 2»             -> lo fija y lo recuerda
    «prueba el microfono»            -> graba dos segundos y dice cuanto oyo

La preferencia `microfono_indice` la lee jarvis_escucha al abrir el microfono.
Sin PyAudio no hay nada que listar, y se dice claramente en lugar de fallar.
"""
import os


def disponible() -> tuple:
    try:
        import pyaudio  # noqa: F401
    except Exception:
        return False, "falta PyAudio (pip install pyaudio)"
    return True, ""


def listar_microfonos(log=print) -> list:
    """[(indice, nombre, canales, frecuencia), ...] de entradas reales."""
    ok, _motivo = disponible()
    if not ok:
        return []
    import pyaudio
    pa = pyaudio.PyAudio()
    salida = []
    try:
        for i in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_index(i)
            except Exception:
                continue
            if int(info.get("maxInputChannels", 0)) > 0:
                salida.append((i, str(info.get("name", "?"))[:60],
                               int(info["maxInputChannels"]),
                               int(info.get("defaultSampleRate", 0))))
    finally:
        pa.terminate()
    return salida


def listar_altavoces(log=print) -> list:
    ok, _motivo = disponible()
    if not ok:
        return []
    import pyaudio
    pa = pyaudio.PyAudio()
    salida = []
    try:
        for i in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_index(i)
            except Exception:
                continue
            if int(info.get("maxOutputChannels", 0)) > 0:
                salida.append((i, str(info.get("name", "?"))[:60],
                               int(info["maxOutputChannels"]),
                               int(info.get("defaultSampleRate", 0))))
    finally:
        pa.terminate()
    return salida


def frase_microfonos(core=None, log=print) -> str:
    ok, motivo = disponible()
    if not ok:
        return f"No puedo ver los micrófonos, señor: {motivo}."
    micros = listar_microfonos(log=log)
    if not micros:
        return "No encuentro ningún micrófono conectado, señor."
    elegido = indice_elegido(core)
    partes = []
    for indice, nombre, _canales, _hz in micros[:8]:
        marca = " ←(en uso)" if indice == elegido else ""
        partes.append(f"{indice}: {nombre}{marca}")
    return ("Micrófonos disponibles, señor — " + "; ".join(partes)
            + ". Dígame «usa el micrófono N» para cambiar.")


def indice_elegido(core=None):
    """Índice guardado, o None para que el sistema elija el predeterminado."""
    if core is None:
        valor = os.getenv("JARVIS_MICROFONO", "")
    else:
        try:
            valor = core.get_pref("microfono_indice") or ""
        except Exception:
            valor = ""
    try:
        return int(valor)
    except Exception:
        return None


def elegir(core, indice: int, log=print) -> str:
    micros = {i for i, _n, _c, _hz in listar_microfonos(log=log)}
    if micros and indice not in micros:
        return (f"No tengo ningún micrófono con el número {indice}, señor. "
                "Dígame «qué micrófonos tienes» para ver la lista.")
    try:
        core.set_pref("microfono_indice", str(indice))
    except Exception as e:
        return f"No pude guardar la elección: {e}"
    nombre = next((n for i, n, _c, _hz in listar_microfonos(log=log) if i == indice), "?")
    return (f"Usaré el micrófono {indice} ({nombre}), señor. "
            "Si la escucha continua estaba activa, reiníciela para que lo tome.")


def probar(core=None, segundos: float = 2.0, log=print) -> str:
    """Graba unos segundos y dice cuánto sonido ha entrado de verdad."""
    ok, motivo = disponible()
    if not ok:
        return f"No puedo probar el micrófono, señor: {motivo}."
    try:
        import audioop
        import pyaudio
    except Exception:
        audioop = None
        import pyaudio

    indice = indice_elegido(core)
    pa = pyaudio.PyAudio()
    try:
        flujo = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True,
                        input_device_index=indice, frames_per_buffer=1024)
        picos = []
        for _ in range(int(16000 / 1024 * segundos)):
            datos = flujo.read(1024, exception_on_overflow=False)
            if audioop is not None:
                picos.append(audioop.rms(datos, 2))
            else:
                picos.append(max(datos) if datos else 0)
        flujo.stop_stream()
        flujo.close()
    except Exception as e:
        return f"El micrófono no se pudo abrir, señor: {str(e)[:100]}"
    finally:
        pa.terminate()

    pico = max(picos) if picos else 0
    if pico < 60:
        return (f"He grabado {segundos:.0f} segundos y prácticamente no ha entrado "
                "sonido, señor. Puede que sea el micrófono equivocado o esté "
                "silenciado.")
    if pico < 500:
        return f"Le oigo, señor, pero bajito (pico {pico}). Acérquese o suba la ganancia."
    return f"Le oigo perfectamente, señor (pico {pico})."


def estado(core=None) -> dict:
    ok, motivo = disponible()
    return {
        "disponible": ok, "motivo": motivo,
        "microfono_elegido": indice_elegido(core),
        "microfonos": [{"indice": i, "nombre": n} for i, n, _c, _hz in listar_microfonos()],
        "altavoces": [{"indice": i, "nombre": n} for i, n, _c, _hz in listar_altavoces()],
    }
