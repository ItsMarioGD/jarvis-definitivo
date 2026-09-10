#!/usr/bin/env python3
"""
herramientas_llm.py - Que el cerebro pueda ACTUAR, no solo hablar
=================================================================
Hasta ahora el flujo era: regex -> si ninguna habilidad reconoce la frase, el
LLM contesta con palabras. El modelo no podia ejecutar nada. Por eso una orden
como «organiza la carpeta de descargas y avisame por Telegram cuando acabes»
recibia una respuesta amable y ni un solo archivo movido: ninguna regex la
cubria, y el cerebro no tenia manos.

Aqui estan las manos. Qwen (via Ollama) admite `tools` con el formato de
OpenAI, asi que se le ofrece un juego de herramientas y se ejecuta lo que pida:

    usuario  -> «organiza las descargas y avisame por Telegram»
    modelo   -> mover_archivos(...) + enviar_telegram(...)
    JARVIS   -> ejecuta las dos, con registro y con deshacer, y responde

Decisiones de diseño
--------------------
* Cada herramienta traduce sus parametros a la **frase canonica** que ya
  entienden los despachadores de siempre (jarvis_skills, pc_control...). No se
  duplica logica: se reutiliza la que ya esta probada, con su auditoria y su
  diario de deshacer.
* Las regex siguen siendo la via rapida (latencia cero, sin tokens). Esto solo
  entra cuando ninguna reconoce la orden.
* Numero de rondas acotado: un modelo pequeño puede encadenar llamadas para
  siempre si se le deja.
* Si el modelo no admite herramientas, se devuelve None y el nucleo sigue por
  el camino de siempre. Nunca se queda mudo por esto.
"""
import json
import os

MAX_RONDAS = int(os.getenv("JARVIS_TOOLS_RONDAS", "4"))


class Herramientas:
    """Puente entre las tool-calls del modelo y las habilidades reales."""

    def __init__(self, core, log=print):
        self.core = core
        self.log = log
        self.usadas = []          # historial de la conversación actual

    # ── catálogo ────────────────────────────────────────────────────────────
    def definiciones(self) -> list:
        """Esquema de herramientas en el formato que espera la API."""
        def h(nombre, descripcion, propiedades, obligatorios=()):
            return {"type": "function", "function": {
                "name": nombre, "description": descripcion,
                "parameters": {"type": "object", "properties": propiedades,
                               "required": list(obligatorios)}}}

        texto = {"type": "string"}
        entero = {"type": "integer"}

        return [
            h("abrir_app", "Abre una aplicación o web en el PC del señor.",
              {"nombre": {"type": "string", "description": "spotify, chrome, word, calculadora..."}},
              ["nombre"]),
            h("cerrar_app", "Cierra una aplicación que esté abierta.",
              {"nombre": texto}, ["nombre"]),
            h("apagar_equipo", "Programa el apagado del PC.",
              {"minutos": {"type": "integer", "description": "0 = en 30 segundos"}}),
            h("reiniciar_equipo", "Programa el reinicio del PC.", {"minutos": entero}),
            h("cancelar_apagado", "Anula un apagado o reinicio programado.", {}),
            h("bloquear_equipo", "Bloquea la sesión de Windows.", {}),
            h("ajustar_volumen", "Pone el volumen del sistema en un porcentaje.",
              {"nivel": {"type": "integer", "description": "0 a 100"}}, ["nivel"]),
            h("captura_pantalla", "Hace una captura de pantalla y la guarda.", {}),
            h("estado_pc", "Estado del equipo: CPU, memoria, disco, batería.", {}),
            h("listar_procesos", "Procesos que más recursos consumen ahora.", {}),
            h("cerrar_proceso", "Termina un proceso por nombre.", {"nombre": texto}, ["nombre"]),
            h("buscar_web", "Busca algo en internet y abre los resultados.",
              {"consulta": texto}, ["consulta"]),
            h("clima", "Tiempo actual en una ciudad.", {"ciudad": texto}),
            h("crear_nota", "Guarda una nota de texto.", {"texto": texto}, ["texto"]),
            h("leer_notas", "Lee las notas guardadas.", {}),
            h("temporizador", "Pone un temporizador en minutos.",
              {"minutos": entero, "etiqueta": texto}, ["minutos"]),
            h("recordatorio", "Crea un recordatorio para una hora concreta.",
              {"texto": texto, "hora": {"type": "string", "description": "HH:MM"}},
              ["texto"]),
            h("agenda_dia", "Qué hay en la agenda hoy, mañana o esta semana.",
              {"cuando": {"type": "string", "description": "hoy, mañana o esta semana"}}),
            h("mover_archivos", "Mueve en lote los archivos de una extensión entre carpetas.",
              {"extension": {"type": "string", "description": "pdf, jpg, zip..."},
               "origen": {"type": "string", "description": "descargas, documentos, escritorio o ruta"},
               "destino": texto}, ["extension", "origen", "destino"]),
            h("organizar_descargas", "Ordena la carpeta de descargas por tipo de archivo.", {}),
            h("buscar_archivos", "Busca archivos por nombre en el equipo.",
              {"nombre": texto}, ["nombre"]),
            h("reproducir_musica", "Reproduce música o una canción concreta.",
              {"consulta": texto}, ["consulta"]),
            h("enviar_telegram", "Envía un mensaje al Telegram del señor.",
              {"texto": texto}, ["texto"]),
            h("mirar_pantalla", "Mira la pantalla del señor y responde a una pregunta "
                                "sobre lo que se ve (errores, ventanas, documentos).",
              {"pregunta": texto}),
            h("ensayar_orden", "Comprueba qué haría una orden ANTES de ejecutarla "
                                "(cuántos archivos toca, qué cambiaría).",
              {"orden": texto}, ["orden"]),
            h("pilotar_pantalla", "Usa ratón y teclado para lograr un objetivo en "
                                  "pantalla cuando ninguna otra herramienta sirve. "
                                  "Es lento: úsala solo como último recurso.",
              {"objetivo": texto}, ["objetivo"]),
            h("buscar_en_documentos", "Busca dentro del contenido de los documentos "
                                       "del señor y responde citando el archivo.",
              {"pregunta": texto}, ["pregunta"]),
            h("recados_pendientes", "Resume los mensajes y recados sin leer.", {}),
            h("analizar_con_codigo",
              "Resuelve una tarea de datos escribiendo y ejecutando un programa: "
              "cruzar hojas de cálculo, calcular estadísticas, generar gráficas, "
              "convertir formatos, renombrar en lote por criterios. Úsala cuando "
              "ninguna herramienta simple sirva y haga falta cálculo real.",
              {"tarea": texto}, ["tarea"]),
            h("leer_archivo", "Lee un archivo de texto del señor (código, notas, "
                              "config). Devuelve las líneas numeradas.",
              {"ruta": texto,
               "desde": {"type": "integer", "description": "primera línea (1 por defecto)"},
               "hasta": {"type": "integer", "description": "última línea (0 = hasta el final)"}},
              ["ruta"]),
            h("escribir_archivo", "Crea o reescribe por completo un archivo de "
                                  "texto. Reversible con «deshaz eso».",
              {"ruta": texto, "contenido": texto}, ["ruta", "contenido"]),
            h("editar_archivo", "Cambia UN fragmento exacto de un archivo por otro. "
                                "El fragmento a buscar debe aparecer una sola vez. "
                                "Reversible con «deshaz eso».",
              {"ruta": texto, "buscar": texto, "reemplazar": texto},
              ["ruta", "buscar", "reemplazar"]),
            h("listar_dir", "Lista el contenido de una carpeta.",
              {"ruta": texto}),
            h("buscar_en_archivos", "Busca un patrón (regex) dentro de los archivos "
                                    "de una carpeta. Devuelve ruta:línea: coincidencia.",
              {"patron": texto, "ruta": texto,
               "glob": {"type": "string", "description": "filtro de nombre, p. ej. *.py"}},
              ["patron"]),
            h("deshacer_ultimo", "Revierte la última acción reversible.", {}),
            h("orden_libre", "Ejecuta cualquier otra orden en el lenguaje de siempre. "
                             "Úsala solo si ninguna herramienta encaja.",
              {"orden": texto}, ["orden"]),
        ] + self._definiciones_mcp()

    def _definiciones_mcp(self) -> list:
        """Herramientas de los servidores MCP configurados (Prefs/mcp.json)."""
        if os.getenv("JARVIS_MCP", "1") == "0":
            return []
        try:
            import mcp_generico
            return mcp_generico.definiciones_openai(log=self.log)
        except Exception as e:
            self.log(f"[HERRAMIENTAS] MCP no disponible: {e}")
            return []

    # ── ejecución ───────────────────────────────────────────────────────────
    def ejecutar(self, nombre: str, argumentos: dict) -> str:
        """Ejecuta una herramienta y devuelve el texto del resultado."""
        try:
            if nombre.startswith("mcp__"):
                import mcp_generico
                resultado = mcp_generico.llamar(nombre, argumentos or {}, log=self.log)
                self.usadas.append(nombre)
                self.log(f"[HERRAMIENTA] {nombre}({argumentos}) -> {str(resultado)[:80]}")
                return str(resultado or "hecho")
            metodo = getattr(self, f"_t_{nombre}", None)
            if metodo is None:
                return f"No tengo ninguna herramienta llamada {nombre}."
            resultado = metodo(argumentos or {})
            self.usadas.append(nombre)
            self.log(f"[HERRAMIENTA] {nombre}({argumentos}) -> {str(resultado)[:80]}")
            return str(resultado or "hecho")
        except Exception as e:
            self.log(f"[HERRAMIENTA] {nombre} falló: {e}")
            return f"La herramienta {nombre} falló: {e}"

    def _frase(self, texto: str) -> str:
        """Manda una frase por los despachadores de siempre."""
        for despachador in (self.core.skills, getattr(self.core, "pc", None),
                            getattr(self.core, "msg", None),
                            getattr(self.core, "conectores", None)):
            if despachador is None:
                continue
            try:
                r = despachador.handle(texto)
            except Exception as e:
                self.log(f"[HERRAMIENTA] despachador falló con «{texto[:40]}»: {e}")
                continue
            if r:
                return r
        return f"Nadie supo atender «{texto}»."

    # ── herramientas concretas ──────────────────────────────────────────────
    def _t_abrir_app(self, a):        return self._frase(f"abre {a.get('nombre', '')}")
    def _t_cerrar_app(self, a):       return self._frase(f"cierra {a.get('nombre', '')}")
    def _t_bloquear_equipo(self, a):  return self._frase("bloquea el pc")
    def _t_captura_pantalla(self, a): return self._frase("haz una captura de pantalla")
    def _t_estado_pc(self, a):        return self._frase("como esta el pc")
    def _t_listar_procesos(self, a):  return self._frase("que procesos pesan mas")
    def _t_leer_notas(self, a):       return self._frase("muestra mis notas")
    def _t_organizar_descargas(self, a): return self._frase("organiza la carpeta de descargas")

    def _t_apagar_equipo(self, a):
        minutos = int(a.get("minutos") or 0)
        return self._frase(f"apaga el pc en {minutos} minutos" if minutos else "apaga el pc")

    def _t_reiniciar_equipo(self, a):
        minutos = int(a.get("minutos") or 0)
        return self._frase(f"reinicia el pc en {minutos} minutos" if minutos else "reinicia el pc")

    def _t_cancelar_apagado(self, a):
        return self._frase("cancela el apagado")

    def _t_ajustar_volumen(self, a):
        nivel = max(0, min(int(a.get("nivel", 50)), 100))
        return self._frase(f"volumen al {nivel}%")

    def _t_cerrar_proceso(self, a):
        return self._frase(f"mata el proceso {a.get('nombre', '')}")

    def _t_buscar_web(self, a):
        return self._frase(f"busca {a.get('consulta', '')}")

    def _t_clima(self, a):
        ciudad = a.get("ciudad") or ""
        return self._frase(f"clima en {ciudad}" if ciudad else "que tiempo hace")

    def _t_crear_nota(self, a):
        return self._frase(f"anota {a.get('texto', '')}")

    def _t_temporizador(self, a):
        minutos = int(a.get("minutos", 5))
        etiqueta = a.get("etiqueta") or ""
        return self._frase(f"temporizador de {minutos} minutos {etiqueta}".strip())

    def _t_recordatorio(self, a):
        hora = a.get("hora") or ""
        texto = a.get("texto", "")
        return self._frase(f"recuerdame que {texto}" + (f" a las {hora}" if hora else ""))

    def _t_agenda_dia(self, a):
        cuando = a.get("cuando") or "hoy"
        return self._frase(f"que tengo {cuando}")

    def _t_mover_archivos(self, a):
        return self._frase(f"mueve todos los {a.get('extension', '')} de "
                           f"{a.get('origen', '')} a {a.get('destino', '')}")

    def _t_buscar_archivos(self, a):
        return self._frase(f"busca archivos {a.get('nombre', '')}")

    def _t_reproducir_musica(self, a):
        return self._frase(f"reproduce {a.get('consulta', '')}")

    def _t_enviar_telegram(self, a):
        texto = a.get("texto", "")
        try:
            from conectores import Notificador
            Notificador(notify=None, log=self.log).avisar("aviso por Telegram", texto)
            return "Mensaje enviado por Telegram."
        except Exception as e:
            return f"No pude enviar el mensaje: {e}"

    def _t_mirar_pantalla(self, a):
        import vision
        return vision.mirar_pantalla(a.get("pregunta", ""), log=self.log)

    def _t_ensayar_orden(self, a):
        import sandbox
        return sandbox.informe_impacto(a.get("orden", ""), log=self.log)

    def _t_pilotar_pantalla(self, a):
        from piloto import Piloto
        piloto = getattr(self.core, "piloto", None)
        if piloto is None:
            piloto = Piloto(self.core, log=self.log)
            try:
                self.core.piloto = piloto
            except Exception:
                pass
        # Desde una herramienta siempre en seco: mover el ratón de verdad exige
        # que el señor lo pida a la cara, no que lo decida el modelo.
        return piloto.ejecutar(a.get("objetivo", ""), seco=True)

    def _t_buscar_en_documentos(self, a):
        import indice_documentos
        return indice_documentos.responder(self.core, a.get("pregunta", ""), log=self.log)

    def _t_recados_pendientes(self, a):
        import recados
        return recados.resumen()

    def _t_analizar_con_codigo(self, a):
        import analista
        r = analista.resolver(self.core, a.get("tarea", ""), log=self.log)
        return analista.frase(r)

    def _t_leer_archivo(self, a):
        import herramientas_fs
        return herramientas_fs.leer_archivo(a.get("ruta", ""), a.get("desde", 1),
                                            a.get("hasta", 0), log=self.log)

    def _t_escribir_archivo(self, a):
        import herramientas_fs
        return herramientas_fs.escribir_archivo(a.get("ruta", ""),
                                                a.get("contenido", ""), log=self.log)

    def _t_editar_archivo(self, a):
        import herramientas_fs
        return herramientas_fs.editar_archivo(a.get("ruta", ""), a.get("buscar", ""),
                                              a.get("reemplazar", ""), log=self.log)

    def _t_listar_dir(self, a):
        import herramientas_fs
        return herramientas_fs.listar_dir(a.get("ruta", "."), log=self.log)

    def _t_buscar_en_archivos(self, a):
        import herramientas_fs
        return herramientas_fs.buscar_en_archivos(a.get("patron", ""), a.get("ruta", "."),
                                                  a.get("glob", "*"), log=self.log)

    def _t_deshacer_ultimo(self, a):
        import deshacer
        return deshacer.deshacer_ultimo(1, log=self.log,
                                        set_pref=getattr(self.core, "set_pref", None))

    def _t_orden_libre(self, a):
        return self._frase(a.get("orden", ""))


# ── bucle de razonamiento con herramientas ──────────────────────────────────
def pensar_con_herramientas(core, texto: str, mensajes: list, log=print):
    """Deja que el modelo use herramientas. Devuelve (respuesta, usadas) o None.

    Devuelve None cuando el proveedor no admite `tools`: quien llama debe
    seguir por el camino normal (streaming) como si esto no existiera.
    """
    try:
        from openai import OpenAI
    except Exception:
        return None

    try:
        nombre, url, modelo, clave = core._proveedores()[0]
        _local = ("localhost" in url) or ("127.0.0.1" in url)
        if not _local:
            try:
                import presupuesto
                if not presupuesto.permite_nube():
                    log("[HERRAMIENTAS] tope de gasto alcanzado; sin herramientas hoy")
                    return None
            except Exception:
                pass
        cliente = OpenAI(base_url=url, api_key=clave)
    except Exception as e:
        log(f"[HERRAMIENTAS] Sin proveedor utilizable: {e}")
        return None

    caja = Herramientas(core, log=log)
    conversacion = list(mensajes) + [{"role": "user", "content": texto}]
    definiciones = caja.definiciones()

    for ronda in range(MAX_RONDAS):
        try:
            resp = cliente.chat.completions.create(
                model=modelo, messages=conversacion, tools=definiciones,
                tool_choice="auto", temperature=0.3, max_tokens=400)
        except Exception as e:
            # El modelo no admite herramientas (o el servidor no las expone).
            log(f"[HERRAMIENTAS] {nombre} no las admite ({str(e)[:80]}); sigo sin ellas.")
            return None

        try:
            import presupuesto
            _uso = getattr(resp, "usage", None)
            if _uso:
                presupuesto.registrar_uso(nombre, modelo,
                                          getattr(_uso, "prompt_tokens", 0) or 0,
                                          getattr(_uso, "completion_tokens", 0) or 0,
                                          log=log)
        except Exception:
            pass

        mensaje = resp.choices[0].message
        llamadas = getattr(mensaje, "tool_calls", None) or []
        if not llamadas:
            contenido = (mensaje.content or "").strip()
            if "</think>" in contenido:
                contenido = contenido.split("</think>", 1)[1].strip()
            if caja.usadas:
                return contenido, caja.usadas
            # El modelo ha contestado sin usar herramientas. Antes se descartaba
            # esta respuesta y se volvía a preguntar por el camino con streaming:
            # dos llamadas al modelo para una sola frase del señor. Si la
            # respuesta ya sirve, se usa; si vino vacía, entonces sí se cae al
            # camino normal.
            if len(contenido) > 15:
                return contenido, []
            return None

        conversacion.append({
            "role": "assistant", "content": mensaje.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name,
                                         "arguments": c.function.arguments}}
                           for c in llamadas]})

        for llamada in llamadas:
            try:
                argumentos = json.loads(llamada.function.arguments or "{}")
            except Exception:
                argumentos = {}
            resultado = caja.ejecutar(llamada.function.name, argumentos)
            conversacion.append({"role": "tool", "tool_call_id": llamada.id,
                                 "content": str(resultado)[:1500]})

    # Se agotaron las rondas: contamos lo hecho en vez de callar.
    if caja.usadas:
        return ("He hecho lo que pude: " + ", ".join(caja.usadas) + ".", caja.usadas)
    return None
