#!/usr/bin/env python3
"""
mision.py - Objetivos grandes que se trabajan solos durante horas
=================================================================
El turno de noche (modo_nocturno.py) ejecuta una lista fija. Esto es distinto:
se le da un OBJETIVO y el se hace el plan.

    «prepara el entorno del proyecto X»
    «organiza y limpia todo el disco»
    «hazme el informe mensual con los gastos del año»

Como funciona
-------------
  1. PLANIFICA   el modelo parte el objetivo en pasos concretos y ejecutables.
  2. VERIFICA    cada paso pasa por verificador.py antes de tocar nada.
  3. EJECUTA     por los caminos de siempre: habilidades, herramientas o el
                 analista (que escribe codigo cuando hace falta calcular).
  4. REPLANTEA   si un paso falla, pide una alternativa UNA vez y sigue.
  5. INFORMA     deja un parte con lo hecho, lo fallido y lo que quedo.

Los tres frenos que lo hacen aceptable
--------------------------------------
* PRESUPUESTO de minutos y de pasos: al agotarse, para y lo dice. Una mision no
  puede comerse la tarde.
* PUNTOS DE CONTROL: cada paso queda anotado y lo reversible pasa por el diario
  de deshacer, asi que se puede volver atras.
* NADA IRREVERSIBLE A SOLAS: si el verificador marca un paso como grave, la
  mision se detiene ahi y pregunta en vez de decidir por su cuenta.
"""
import json
import os
import threading
import time
from datetime import datetime

CARPETA = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Misiones")
MAX_PASOS = int(os.getenv("JARVIS_MISION_PASOS", "12"))
MAX_MINUTOS = int(os.getenv("JARVIS_MISION_MINUTOS", "30"))

INSTRUCCIONES = """Eres el planificador de un asistente que controla un PC con Windows.

Divide el objetivo en pasos CONCRETOS, cada uno una orden que el asistente
pueda ejecutar tal cual, en español y en una línea. Nada de «analizar la
situación» ni «preparar el entorno»: cada paso debe ser algo que se hace.

Reglas:
- Entre 2 y {max_pasos} pasos. Menos es mejor si basta.
- Un paso por línea, empezando por un verbo. Sin numerar, sin viñetas.
- El asistente sabe: abrir y cerrar programas, mover y organizar archivos,
  buscar en internet, leer y escribir documentos, consultar la agenda, mirar el
  estado del equipo, hacer copias, y escribir programas para calcular cosas.
- Si un paso necesita cálculo o cruzar datos, escríbelo como
  «analiza ...» para que use su intérprete de código.
- No incluyas pasos que borren o formateen nada salvo que el objetivo lo pida.

Responde SOLO con los pasos, uno por línea."""


class Mision:
    """Un objetivo con su plan, su presupuesto y su bitácora."""

    def __init__(self, objetivo: str, pasos=None, minutos: int = MAX_MINUTOS):
        self.objetivo = objetivo
        self.pasos = pasos or []
        self.minutos = minutos
        self.estado = "planificada"
        self.bitacora = []          # [{paso, resultado, ok, segundos}]
        self.inicio = 0.0
        self.fin = 0.0
        self.detenida_por = ""

    def como_dict(self) -> dict:
        return {"objetivo": self.objetivo, "pasos": self.pasos, "estado": self.estado,
                "bitacora": self.bitacora, "minutos": self.minutos,
                "detenida_por": self.detenida_por,
                "duracion_min": round(((self.fin or time.time()) - self.inicio)/60, 1)
                if self.inicio else 0}


def planificar(core, objetivo: str, log=print, max_pasos: int = MAX_PASOS) -> list:
    """Convierte un objetivo en pasos ejecutables."""
    try:
        from openai import OpenAI
        _n, url, modelo, clave = core._proveedores()[0]
        cliente = (core._cliente_llm(url, clave) if hasattr(core, "_cliente_llm")
                   else OpenAI(base_url=url, api_key=clave))
        resp = cliente.chat.completions.create(
            model=modelo, temperature=0.3, max_tokens=400,
            messages=[{"role": "system",
                       "content": INSTRUCCIONES.replace("{max_pasos}", str(max_pasos))},
                      {"role": "user", "content": f"Objetivo: {objetivo}"}])
        texto = (resp.choices[0].message.content or "")
    except Exception as e:
        log(f"[MISION] No pude planificar: {e}")
        return []

    if "</think>" in texto:
        texto = texto.split("</think>", 1)[1]
    pasos = []
    for linea in texto.splitlines():
        limpia = linea.strip().lstrip("-•*0123456789. ").strip()
        if len(limpia) > 6 and not limpia.endswith(":"):
            pasos.append(limpia)
    return pasos[:max_pasos]


class Piloto:
    """Ejecuta una misión paso a paso, con presupuesto y frenos."""

    def __init__(self, core, log=print):
        self.core = core
        self.log = log
        self.actual = None
        self._hilo = None
        self._parar = threading.Event()

    # ── ejecución de un paso ────────────────────────────────────────────────
    def _ejecutar_paso(self, paso: str) -> dict:
        """Un paso por los caminos de siempre. Devuelve {ok, resultado}."""
        import verificador
        veredicto = verificador.verificar(self.core, paso, con_modelo=False, log=self.log)
        if verificador.hay_que_parar(veredicto):
            return {"ok": False, "resultado": f"detenido por revisión: {veredicto['motivo']}",
                    "frenado": True}

        # 1. Habilidades de siempre.
        for despachador in (getattr(self.core, "skills", None),
                            getattr(self.core, "pc", None),
                            getattr(self.core, "conectores", None)):
            if despachador is None:
                continue
            try:
                r = despachador.handle(paso)
            except Exception as e:
                self.log(f"[MISION] {type(despachador).__name__}: {e}")
                continue
            if r:
                return {"ok": True, "resultado": str(r)[:300]}

        # 2. Analista, si el paso pide cálculo.
        try:
            import analista
            if analista.parece_analisis(paso) or paso.lower().startswith("analiza"):
                r = analista.resolver(self.core, paso, log=self.log)
                return {"ok": r["ok"], "resultado": analista.frase(r)[:300]}
        except Exception as e:
            self.log(f"[MISION] analista: {e}")

        # 3. El cerebro con herramientas.
        try:
            from herramientas_llm import pensar_con_herramientas
            salida = pensar_con_herramientas(self.core, paso, self.core.history,
                                             log=self.log)
            if salida:
                texto, usadas = salida
                return {"ok": True, "resultado": (texto or ", ".join(usadas))[:300]}
        except Exception as e:
            self.log(f"[MISION] herramientas: {e}")

        return {"ok": False, "resultado": "nadie supo hacer este paso"}

    def _replantear(self, paso: str, error: str) -> str:
        """Una alternativa cuando un paso falla. Solo se pide una vez."""
        try:
            from openai import OpenAI
            _n, url, modelo, clave = self.core._proveedores()[0]
            cliente = (self.core._cliente_llm(url, clave)
                       if hasattr(self.core, "_cliente_llm")
                       else OpenAI(base_url=url, api_key=clave))
            resp = cliente.chat.completions.create(
                model=modelo, temperature=0.4, max_tokens=90,
                messages=[{"role": "system", "content":
                           "Reescribe la orden para que el asistente pueda cumplirla. "
                           "Responde SOLO con la orden nueva, en una línea, en español."},
                          {"role": "user", "content":
                           f"Orden que falló: {paso}\nMotivo: {error}"}])
            alternativa = (resp.choices[0].message.content or "").strip().splitlines()
            return alternativa[0][:200] if alternativa else ""
        except Exception:
            return ""

    # ── misión completa ─────────────────────────────────────────────────────
    def ejecutar(self, mision: Mision) -> Mision:
        self.actual = mision
        mision.estado = "en curso"
        mision.inicio = time.time()
        limite = mision.minutos * 60
        self.log(f"[MISION] «{mision.objetivo}» — {len(mision.pasos)} pasos, "
                 f"{mision.minutos} minutos de presupuesto")

        for indice, paso in enumerate(mision.pasos, 1):
            if self._parar.is_set():
                mision.detenida_por = "el señor la detuvo"
                break
            if time.time() - mision.inicio > limite:
                mision.detenida_por = "se agotó el presupuesto de tiempo"
                break

            t0 = time.time()
            resultado = self._ejecutar_paso(paso)
            if not resultado["ok"] and not resultado.get("frenado"):
                alternativa = self._replantear(paso, resultado["resultado"])
                if alternativa and alternativa.lower() != paso.lower():
                    self.log(f"[MISION] Replanteo: «{alternativa}»")
                    resultado = self._ejecutar_paso(alternativa)
                    paso = f"{paso} -> {alternativa}"

            mision.bitacora.append({
                "paso": paso, "ok": resultado["ok"],
                "resultado": resultado["resultado"],
                "segundos": round(time.time() - t0, 1)})
            # Sin símbolos fuera de ASCII: la consola de Windows va en cp1252
            # y un tic reventaba la misión entera al escribir el log.
            self.log(f"[MISION] {indice}/{len(mision.pasos)} "
                     f"[{'ok' if resultado['ok'] else '--'}] {paso[:60]}")

            if resultado.get("frenado"):
                mision.detenida_por = "un paso necesita su permiso: " + resultado["resultado"]
                break

        mision.fin = time.time()
        hechos = sum(1 for b in mision.bitacora if b["ok"])
        if mision.detenida_por:
            mision.estado = "detenida"
        elif hechos == len(mision.pasos):
            mision.estado = "completada"
        else:
            mision.estado = "parcial"
        self._guardar(mision)
        return mision

    def lanzar(self, mision: Mision):
        """Arranca la misión en segundo plano y devuelve al instante."""
        self._parar.clear()
        self._hilo = threading.Thread(target=self.ejecutar, args=(mision,), daemon=True)
        self._hilo.start()

    def detener(self) -> str:
        self._parar.set()
        return "Misión detenida, señor. Le dejo el parte de lo hecho hasta ahora."

    def en_curso(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    # ── parte ───────────────────────────────────────────────────────────────
    def _guardar(self, mision: Mision):
        try:
            os.makedirs(CARPETA, exist_ok=True)
            nombre = datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
            with open(os.path.join(CARPETA, nombre), "w", encoding="utf-8") as f:
                json.dump(mision.como_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"[MISION] No pude guardar el parte: {e}")
        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                "mision", mision.objetivo[:90],
                f"{mision.estado}: {sum(1 for b in mision.bitacora if b['ok'])}"
                f"/{len(mision.pasos)} pasos",
                gravedad="info", agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass


def parte(mision: Mision) -> str:
    """El resumen hablado de una misión."""
    if not mision.bitacora:
        return f"No llegué a hacer nada de «{mision.objetivo}», señor."
    hechos = [b for b in mision.bitacora if b["ok"]]
    fallidos = [b for b in mision.bitacora if not b["ok"]]
    partes = [f"Misión «{mision.objetivo[:60]}»: {mision.estado}, "
              f"{len(hechos)} de {len(mision.pasos)} pasos en "
              f"{mision.como_dict()['duracion_min']} minutos."]
    if hechos:
        partes.append("Hecho: " + "; ".join(b["paso"][:50] for b in hechos[:4]) + ".")
    if fallidos:
        partes.append("Sin poder hacer: "
                      + "; ".join(f"{b['paso'][:40]} ({b['resultado'][:40]})"
                                  for b in fallidos[:3]) + ".")
    if mision.detenida_por:
        partes.append("Me detuve porque " + mision.detenida_por + ".")
    return " ".join(partes)


def historial(limite: int = 5) -> str:
    if not os.path.isdir(CARPETA):
        return "No he hecho ninguna misión todavía, señor."
    archivos = sorted(os.listdir(CARPETA), reverse=True)[:limite]
    if not archivos:
        return "No he hecho ninguna misión todavía, señor."
    filas = []
    for a in archivos:
        try:
            with open(os.path.join(CARPETA, a), encoding="utf-8") as f:
                d = json.load(f)
            hechos = sum(1 for b in d.get("bitacora", []) if b.get("ok"))
            filas.append(f"{a[:13]} «{d.get('objetivo','')[:40]}» {d.get('estado')} "
                         f"({hechos}/{len(d.get('pasos', []))})")
        except Exception:
            continue
    return "Últimas misiones, señor: " + " | ".join(filas)
