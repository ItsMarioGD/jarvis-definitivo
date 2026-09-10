#!/usr/bin/env python3
"""
piloto.py - Usar el PC como lo usaria un humano
===============================================
El techo del proyecto siempre ha sido el mismo: 360 habilidades escritas a mano
y una cola infinita de cosas que nadie previo. Este modulo quita ese techo. En
vez de necesitar una habilidad por tarea, el asistente:

    mira la pantalla -> decide la siguiente accion -> mueve raton y teclado
    -> vuelve a mirar para comprobar si funciono -> repite

Es el mismo bucle que ya hacia self_healing.py para Android (mirar el arbol de
la interfaz, probar un selector, verificar), llevado a Windows y con los ojos
del modelo de vision.

Guardarrailes, porque esto mueve el raton de verdad
---------------------------------------------------
* Numero maximo de pasos por objetivo (por defecto 12): sin tope, un modelo
  perdido hace clic para siempre.
* El señor confirma antes de empezar. Un clic no se puede deshacer, asi que la
  confirmacion sustituye al diario de deshacer.
* Cada paso queda registrado en storage.py con lo que vio y lo que hizo.
* Tecla de panico: mover el raton a la esquina superior izquierda aborta
  (es el fail-safe de pyautogui, y aqui esta activado a proposito).
* Si no hay modelo de vision instalado, no se mueve nada y se dice por que.
"""
import json
import os
import re
import time

MAX_PASOS = int(os.getenv("JARVIS_PILOTO_PASOS", "12"))
PAUSA_ENTRE_PASOS = float(os.getenv("JARVIS_PILOTO_PAUSA", "1.2"))

PROMPT = """Eres el piloto de un ordenador con Windows. Ves una captura de la
pantalla y tienes un objetivo. Responde SOLO con un JSON, sin explicaciones:

{"accion": "clic|doble_clic|escribir|tecla|scroll|esperar|listo|imposible",
 "x": <numero>, "y": <numero>, "texto": "<lo que hay que escribir o la tecla>",
 "razon": "<por que, en una frase corta>"}

Reglas:
- "x" e "y" son coordenadas en la imagen que te doy.
- Usa "listo" cuando el objetivo ya este cumplido en la pantalla.
- Usa "imposible" si el objetivo no se puede lograr desde aqui.
- Para atajos de teclado usa accion "tecla" y texto como "ctrl+s" o "enter".

Objetivo: {objetivo}
"""


class Piloto:
    """Bucle mirar-actuar-comprobar sobre la pantalla real."""

    def __init__(self, core=None, log=print):
        self.core = core
        self.log = log
        self.pasos = []

    # ── disponibilidad ──────────────────────────────────────────────────────
    def disponible(self) -> tuple:
        try:
            import pyautogui  # noqa: F401
        except Exception:
            return False, "falta pyautogui (pip install pyautogui)"
        try:
            import vision
        except Exception as e:
            return False, f"falta el módulo de visión ({e})"
        if not vision.modelo_vision(log=self.log):
            return False, ("no hay modelo de visión instalado: "
                           "ollama pull qwen2.5vl:3b")
        return True, ""

    # ── ciclo ───────────────────────────────────────────────────────────────
    def ejecutar(self, objetivo: str, max_pasos: int = MAX_PASOS,
                 seco: bool = False) -> str:
        """Persigue un objetivo en la pantalla. `seco=True` solo dice qué haría."""
        ok, motivo = self.disponible()
        if not ok:
            return f"No puedo pilotar el equipo, señor: {motivo}."

        import pyautogui
        import vision
        pyautogui.FAILSAFE = True     # esquina superior izquierda = abortar
        pyautogui.PAUSE = 0.2

        self.pasos = []
        ancho_real, alto_real = pyautogui.size()

        for paso in range(1, max_pasos + 1):
            captura = vision.capturar_pantalla(log=self.log)
            if not captura:
                return "No pude ver la pantalla, señor."

            crudo = vision.preguntar_a_imagen(
                captura, PROMPT.replace("{objetivo}", objetivo), log=self.log)
            accion = self._leer_json(crudo)
            if accion is None:
                self._anotar(paso, {"accion": "ilegible"}, crudo[:120])
                return (f"Me perdí en el paso {paso}, señor: el modelo no devolvió "
                        "una acción que pueda ejecutar.")

            tipo = (accion.get("accion") or "").lower()
            razon = accion.get("razon", "")
            self.log(f"[PILOTO] Paso {paso}: {tipo} ({razon})")

            if tipo == "listo":
                self._anotar(paso, accion, "objetivo cumplido")
                return f"Hecho, señor. {razon or 'El objetivo está cumplido.'}"
            if tipo == "imposible":
                self._anotar(paso, accion, "declarado imposible")
                return f"No puedo lograrlo desde aquí, señor: {razon}"

            if seco:
                self._anotar(paso, accion, "ensayo, sin ejecutar")
                return (f"En el ensayo, mi primer paso sería: {tipo} "
                        f"{accion.get('texto', '')} en ({accion.get('x')}, {accion.get('y')}). "
                        f"Motivo: {razon}")

            try:
                self._actuar(accion, pyautogui, captura, ancho_real, alto_real)
                self._anotar(paso, accion, "ejecutado")
            except pyautogui.FailSafeException:
                return ("Abortado por la esquina de pánico, señor. "
                        "No he tocado nada más.")
            except Exception as e:
                self._anotar(paso, accion, f"error: {e}")
                return f"El paso {paso} falló, señor: {e}"

            time.sleep(PAUSA_ENTRE_PASOS)

        return (f"He dado {max_pasos} pasos sin terminar, señor. Me detengo para "
                "no seguir a ciegas; dígame si sigo o lo hacemos de otra forma.")

    # ── acciones ────────────────────────────────────────────────────────────
    def _actuar(self, accion, pyautogui, captura, ancho_real, alto_real):
        tipo = (accion.get("accion") or "").lower()
        texto = accion.get("texto") or ""

        if tipo in ("clic", "doble_clic", "scroll"):
            x, y = self._escalar(accion, captura, ancho_real, alto_real)
            if tipo == "clic":
                pyautogui.click(x, y)
            elif tipo == "doble_clic":
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.scroll(-400 if "abajo" in texto.lower() else 400, x=x, y=y)
        elif tipo == "escribir":
            pyautogui.typewrite(texto, interval=0.02)
        elif tipo == "tecla":
            teclas = [t.strip() for t in re.split(r"[+\s]+", texto) if t.strip()]
            if len(teclas) > 1:
                pyautogui.hotkey(*teclas)
            elif teclas:
                pyautogui.press(teclas[0])
        elif tipo == "esperar":
            time.sleep(min(float(accion.get("x") or 2), 10))
        else:
            raise ValueError(f"acción desconocida: {tipo}")

    def _escalar(self, accion, captura, ancho_real, alto_real):
        """Del sistema de coordenadas de la imagen al de la pantalla real.

        La captura se reduce antes de mandarla al modelo, así que sus
        coordenadas no son las de la pantalla: sin esta conversión, el piloto
        haría clic siempre arriba a la izquierda.
        """
        x = float(accion.get("x") or 0)
        y = float(accion.get("y") or 0)
        try:
            from PIL import Image
            with Image.open(captura) as img:
                ancho_img, alto_img = img.size
            import vision
            if ancho_img > vision.ANCHO_MAX:
                factor = vision.ANCHO_MAX / ancho_img
                ancho_img, alto_img = ancho_img * factor, alto_img * factor
            x = x * ancho_real / max(ancho_img, 1)
            y = y * alto_real / max(alto_img, 1)
        except Exception as e:
            self.log(f"[PILOTO] No pude escalar coordenadas: {e}")
        return int(max(0, min(x, ancho_real - 1))), int(max(0, min(y, alto_real - 1)))

    # ── registro ────────────────────────────────────────────────────────────
    def _anotar(self, paso, accion, resultado):
        self.pasos.append({"paso": paso, "accion": accion, "resultado": resultado})
        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_accion(
                origen="piloto", orden=str(accion.get("razon", ""))[:120],
                comando=json.dumps(accion, ensure_ascii=False)[:300],
                ok=not str(resultado).startswith("error"), detalle=str(resultado)[:200],
                agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass

    @staticmethod
    def _leer_json(texto: str):
        """Saca el JSON aunque el modelo lo envuelva en explicaciones o ```."""
        if not texto:
            return None
        m = re.search(r"\{.*\}", texto, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            try:
                return json.loads(m.group(0).replace("'", '"'))
            except Exception:
                return None

    def informe(self) -> str:
        if not self.pasos:
            return "El piloto no ha dado ningún paso todavía, señor."
        return "Pasos: " + "; ".join(
            f"{p['paso']}) {p['accion'].get('accion')} → {p['resultado']}"
            for p in self.pasos)
