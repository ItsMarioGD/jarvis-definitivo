#!/usr/bin/env python3
"""
modo_nocturno.py - El turno de noche
====================================
Un asistente que solo trabaja cuando le hablas desaprovecha ocho horas de
maquina al dia. Mientras el señor duerme, el equipo esta encendido y ocioso:
esta es la rutina que lo aprovecha.

Lo que hace de noche (todo dentro de una lista blanca, nada improvisado):

  * ordena la carpeta de descargas,
  * borra temporales y vacia la papelera si esta muy llena,
  * copia de seguridad del cerebro (memoria, grafo, preferencias),
  * poda la memoria antigua,
  * revisa actualizaciones pendientes (sin instalarlas salvo que se pida),
  * prepara el dia siguiente: agenda, avisos, informe.

Tres reglas que la hacen segura:

  1. PRESUPUESTO. La rutina tiene un limite de minutos; al agotarse, para y lo
     dice, en vez de seguir hasta que el señor se despierte.
  2. LISTA BLANCA. Solo ejecuta tareas declaradas aqui. El cerebro no decide de
     noche que se le ocurre hacer.
  3. RASTRO Y VUELTA ATRAS. Cada tarea queda registrada y, cuando toca
     archivos, anotada en el diario de deshacer.
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta

CARPETA_INFORMES = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Informes")
PRESUPUESTO_MIN = int(os.getenv("JARVIS_NOCTURNO_MINUTOS", "45"))


class Tarea:
    def __init__(self, clave, descripcion, funcion, riesgo="bajo"):
        self.clave = clave
        self.descripcion = descripcion
        self.funcion = funcion
        self.riesgo = riesgo


class ModoNocturno:
    """Rutina autónoma con presupuesto, lista blanca y parte de resultados."""

    def __init__(self, core, log=print):
        self.core = core
        self.log = log
        self._timer = None
        self.ultimo_informe = ""

    # ── lista blanca ────────────────────────────────────────────────────────
    def tareas(self) -> list:
        return [
            Tarea("descargas", "ordenar la carpeta de descargas",
                  lambda: self._orden("organiza la carpeta de descargas")),
            Tarea("temporales", "borrar archivos temporales",
                  lambda: self._orden("limpia los temporales")),
            Tarea("memoria", "podar la memoria antigua",
                  lambda: self.core.mantenimiento_memoria()),
            Tarea("copia", "copia de seguridad del cerebro", self._copia),
            Tarea("actualizaciones", "revisar actualizaciones pendientes",
                  lambda: self._orden("hay actualizaciones pendientes"), "medio"),
            Tarea("agenda", "preparar la agenda de mañana",
                  lambda: self._orden("que tengo mañana")),
            Tarea("estado", "revisar el estado del equipo",
                  lambda: self._orden("como esta el pc")),
        ]

    def _orden(self, frase: str) -> str:
        """Ejecuta una orden por los despachadores normales."""
        for despachador in (getattr(self.core, "skills", None),
                            getattr(self.core, "pc", None),
                            getattr(self.core, "conectores", None)):
            if despachador is None:
                continue
            try:
                r = despachador.handle(frase)
            except Exception as e:
                return f"falló: {e}"
            if r:
                return str(r)[:200]
        return "ninguna habilidad la atendió"

    def _copia(self) -> str:
        import cerebro_backup
        return f"copia en {os.path.basename(cerebro_backup.exportar(log=self.log))}"

    # ── ejecución ───────────────────────────────────────────────────────────
    def ejecutar(self, claves=None, presupuesto_min: int = PRESUPUESTO_MIN,
                 seco: bool = False) -> str:
        """Corre la rutina. Devuelve el informe para leerlo por la mañana."""
        inicio = time.time()
        limite = presupuesto_min * 60
        elegidas = [t for t in self.tareas()
                    if claves is None or t.clave in claves]
        lineas, hechas, saltadas = [], 0, 0

        self.log(f"[NOCTURNO] Turno de noche: {len(elegidas)} tareas, "
                 f"{presupuesto_min} minutos de presupuesto")

        for tarea in elegidas:
            transcurrido = time.time() - inicio
            if transcurrido > limite:
                saltadas += 1
                lineas.append(f"- {tarea.descripcion}: sin tiempo (presupuesto agotado)")
                continue
            if seco:
                lineas.append(f"- {tarea.descripcion}: (ensayo, no ejecutado)")
                continue
            try:
                resultado = tarea.funcion()
                hechas += 1
                lineas.append(f"- {tarea.descripcion}: {str(resultado)[:160]}")
            except Exception as e:
                lineas.append(f"- {tarea.descripcion}: falló ({str(e)[:80]})")
            self._registrar(tarea, lineas[-1])

        minutos = (time.time() - inicio) / 60
        cabecera = (f"Turno de noche del {datetime.now():%d/%m/%Y %H:%M} — "
                    f"{hechas} tareas en {minutos:.1f} minutos"
                    + (f", {saltadas} sin tiempo" if saltadas else ""))
        informe = cabecera + "\n" + "\n".join(lineas)
        self.ultimo_informe = informe
        self._guardar_informe(informe)
        self.log(f"[NOCTURNO] {cabecera}")
        return informe

    def _registrar(self, tarea, linea):
        try:
            from storage import get_storage
            get_storage(log=self.log).registrar_evento(
                "nocturno", tarea.descripcion, linea[:300], gravedad="info",
                agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass

    def _guardar_informe(self, informe: str):
        try:
            os.makedirs(CARPETA_INFORMES, exist_ok=True)
            ruta = os.path.join(CARPETA_INFORMES,
                                f"noche_{datetime.now():%Y%m%d}.txt")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(informe)
        except Exception as e:
            self.log(f"[NOCTURNO] No pude guardar el informe: {e}")

    # ── programación ────────────────────────────────────────────────────────
    def programar(self, hora: str = "03:30") -> str:
        """Deja la rutina lista para esta noche a la hora indicada."""
        try:
            hh, mm = [int(x) for x in hora.split(":")]
        except Exception:
            return "No entendí la hora, señor. Dígamela como 03:30."
        ahora = datetime.now()
        objetivo = ahora.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if objetivo <= ahora:
            objetivo += timedelta(days=1)
        espera = (objetivo - ahora).total_seconds()

        if self._timer is not None:
            self._timer.cancel()

        def _disparar():
            try:
                informe = self.ejecutar()
                # El informe no se dice en voz alta de madrugada: espera a que
                # el señor pregunte, o al saludo de la mañana.
                self.log("[NOCTURNO] Informe listo para la mañana.")
                _ = informe
            except Exception as e:
                self.log(f"[NOCTURNO] La rutina falló: {e}")
            finally:
                self.programar(hora)     # se reprograma para el día siguiente

        self._timer = threading.Timer(espera, _disparar)
        self._timer.daemon = True
        self._timer.start()
        try:
            self.core.set_pref("modo_nocturno_hora", hora)
        except Exception:
            pass
        return (f"Turno de noche programado a las {hh:02d}:{mm:02d}, señor. "
                f"Empezaré dentro de {espera / 3600:.1f} horas y le dejaré el parte.")

    def cancelar(self) -> str:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        try:
            self.core.set_pref("modo_nocturno_hora", "")
        except Exception:
            pass
        return "Turno de noche cancelado, señor."

    def informe_ultimo(self) -> str:
        if self.ultimo_informe:
            return self.ultimo_informe
        try:
            ruta = os.path.join(CARPETA_INFORMES,
                                f"noche_{datetime.now():%Y%m%d}.txt")
            if os.path.exists(ruta):
                with open(ruta, encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass
        return "Todavía no he hecho ningún turno de noche, señor."

    def estado(self) -> dict:
        return {
            "programado": self._timer is not None and self._timer.is_alive(),
            "hora": (self.core.get_pref("modo_nocturno_hora") or "")
            if hasattr(self.core, "get_pref") else "",
            "tareas": [t.clave for t in self.tareas()],
            "presupuesto_min": PRESUPUESTO_MIN,
        }
