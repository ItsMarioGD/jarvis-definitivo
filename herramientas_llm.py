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
_TOPE_CONVERSACION = int(os.getenv("JARVIS_TOOLS_TOPE_CHARS", "24000"))


def podar_conversacion(conversacion: list, tope: int = _TOPE_CONVERSACION) -> list:
    """Si el hilo de tool-calling se hace largo, resume los resultados de
    herramienta más viejos: se conservan el system, el primer user y los dos
    últimos intercambios enteros; lo de en medio se recorta a una línea."""
    total = sum(len(str(m.get("content") or "")) for m in conversacion)
    if total <= tope or len(conversacion) <= 6:
        return conversacion
    cabeza = conversacion[:2]        # system + primer user (o los dos primeros)
    cola = conversacion[-4:]         # últimos dos pares
    medio = conversacion[2:-4]
    for m in medio:
        if m.get("role") == "tool":
            c = str(m.get("content") or "")
            if len(c) > 200:
                m["content"] = c.splitlines()[0][:200] + " …[recortado]"
        elif m.get("role") == "assistant" and m.get("content"):
            m["content"] = str(m["content"])[:200]
    return cabeza + medio + cola


class Herramientas:
    """Puente entre las tool-calls del modelo y las habilidades reales."""

    def __init__(self, core, log=print, confirmado=None):
        self.core = core
        self.log = log
        self.usadas = []          # historial de la conversación actual
        self.pendiente = None     # {nombre, argumentos} a la espera de «confirma»
        self._confirmado = set(confirmado or ())  # herramientas ya autorizadas

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
            h("ensayar_orden_movil", "Pre-vuelo de una acción en el móvil: mira "
                                     "el árbol de la pantalla y estima la confianza "
                                     "de acertar antes de tocar el teléfono.",
              {"objetivo": texto, "texto": {"type": "string", "description": "texto del elemento a tocar"},
               "resource_id": texto,
               "accion": {"type": "string", "description": "tap, swipe o text_input"}},
              ["objetivo"]),
            h("pilotar_pantalla", "Usa ratón y teclado para lograr un objetivo en "
                                  "pantalla cuando ninguna otra herramienta sirve. "
                                  "Es lento: úsala solo como último recurso.",
              {"objetivo": texto}, ["objetivo"]),
            h("buscar_en_documentos", "Busca dentro del contenido de los documentos "
                                       "del señor y responde citando el archivo.",
              {"pregunta": texto}, ["pregunta"]),
            h("recados_pendientes", "Resume los mensajes y recados sin leer.", {}),
            h("revisar_correo", "Resume los correos sin leer de Gmail "
                                "(remitente y asunto). Solo lectura.",
              {"solo_importantes": {"type": "boolean",
                                    "description": "true = solo los que parecen urgentes"}}),
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
            h("git_estado", "Estado de un repositorio git: rama, archivos sin "
                            "guardar, commits sin subir.",
              {"repo": {"type": "string", "description": "ruta del repo (. por defecto)"}}),
            h("git_diff", "Muestra el diff de un repositorio git.",
              {"repo": texto, "ruta": {"type": "string", "description": "archivo concreto (opcional)"}}),
            h("correr_tests", "Ejecuta la batería de tests del repo (pytest, npm "
                              "test o go test) y reporta si pasan.",
              {"repo": texto}),
            h("git_crear_rama", "Crea y activa una rama nueva en el repo.",
              {"repo": texto, "nombre": texto}, ["nombre"]),
            h("git_commit", "Hace stage de todo y un commit local (NO sube nada). "
                            "No permite commit directo en main/master.",
              {"repo": texto, "mensaje": texto}, ["mensaje"]),
            h("revisar_pr", "Trae el diff de un Pull Request de GitHub (URL "
                            "completa o número) y lo revisa. Solo lectura.",
              {"objetivo": texto}, ["objetivo"]),
            h("deshacer_ultimo", "Revierte la última acción reversible.", {}),
            h("analizar_imagen", "Mira una imagen del disco y responde una "
                                 "pregunta sobre ella (errores, gráficos, fotos).",
              {"ruta": texto, "pregunta": texto}, ["ruta"]),
            h("analizar_documento", "Lee un PDF (o texto) y responde una pregunta "
                                    "o lo resume.",
              {"ruta": texto, "pregunta": texto}, ["ruta"]),
            h("modelar_3d", "Modela en 3D EN LOCAL con Blender + reconstructores "
                            "locales (TripoSR/Hunyuan3D/ComfyUI/Meshroom). Entrada: "
                            "foto, vídeo, descripción de texto, o un archivo de "
                            "modelado (.blend/.obj/.fbx/.stl/.ply...). Devuelve "
                            ".glb/.obj/.stl, render de giro y visor holográfico, y "
                            "abre el visor.",
              {"entrada": {"type": "string",
                           "description": "ruta a imagen/vídeo/archivo 3D, o la descripción"},
               "t_pose": {"type": "boolean",
                          "description": "para personajes: poner la armadura en T-pose"}},
              ["entrada"]),
            h("holograma", "Muestra como holograma (visor web three.js + cruz para "
                           "pirámide de acrílico) el último modelo o cualquier "
                           "archivo 3D (.blend/.obj/.fbx/.glb/.stl...). Lo abre.",
              {"entrada": {"type": "string", "description": "ruta a un archivo 3D (opcional)"},
               "modo": {"type": "string", "description": "completo o t-pose"}}),
            h("resolver_ciencia", "Resuelve un problema de MATEMÁTICAS, FÍSICA o "
                                  "QUÍMICA dictado en lenguaje normal y, si se "
                                  "pide, lo GRAFICA (2D, superficie 3D girable y "
                                  "malla .obj/.stl). Entiende ecuaciones, "
                                  "derivadas, integrales, límites, series, "
                                  "matrices, EDOs, estadística, cinemática, "
                                  "dinámica, energía, ondas, circuitos, óptica, "
                                  "relatividad, masas molares, balanceo, "
                                  "estequiometría, pH, cinética y geometría "
                                  "molecular. Úsala siempre que haya que calcular "
                                  "o dibujar algo de ciencias.",
              {"enunciado": {"type": "string",
                             "description": "el problema tal cual lo dijo el señor"}},
              ["enunciado"]),
            h("graficar", "Dibuja una función o un conjunto de funciones. En 2D "
                          "marca raíces, máximos, mínimos y asíntotas; en 3D "
                          "levanta la superficie z=f(x,y), la exporta a .obj/.stl "
                          "y abre un visor girable.",
              {"expresion": {"type": "string",
                             "description": "f(x) o f(x,y), con ** para potencias"},
               "dim": {"type": "integer", "description": "2 o 3"},
               "desde": {"type": "number"}, "hasta": {"type": "number"},
               "tipo": {"type": "string",
                        "description": "funcion, superficie, implicita, parametrica, "
                                       "curva3d, polar o campo"}},
              ["expresion"]),
            h("formula_fisica", "Despeja una ley física del formulario con los "
                                "datos que haya (cinemática, dinámica, energía, "
                                "gravitación, fluidos, ondas, termodinámica, "
                                "electricidad, magnetismo, óptica y moderna) y "
                                "explica el desarrollo.",
              {"ley": {"type": "string",
                       "description": "nombre de la ley, p. ej. energia_cinetica u ohm"},
               "datos": {"type": "object",
                         "description": "{\"m\": 2, \"v\": 10} en unidades del SI"},
               "incognita": {"type": "string", "description": "símbolo a despejar"}},
              ["ley"]),
            h("quimica", "Consulta química directa: masa molar, balanceo de una "
                         "reacción, ficha de un elemento, configuración "
                         "electrónica, geometría molecular con MODELO 3D, o la "
                         "tabla periódica dibujada entera.",
              {"operacion": {"type": "string",
                             "description": "masa_molar, balancear, elemento, "
                                            "configuracion, molecula o tabla_periodica"},
               "valor": {"type": "string",
                         "description": "fórmula, ecuación o nombre del elemento"}},
              ["operacion"]),
            h("procesar_reunion", "Transcribe un audio de reunión y saca resumen, "
                                  "acuerdos y tareas; mete las tareas como "
                                  "recordatorios.",
              {"ruta_audio": texto}, ["ruta_audio"]),
            h("buscar_en_memoria", "Busca en la memoria unificada del señor: "
                                   "hechos, preferencias, eventos y episodios. "
                                   "Acepta «qué hice el martes».",
              {"consulta": texto}, ["consulta"]),
            h("recordar_hecho", "Guarda un hecho en la memoria unificada (con "
                                "fecha). Para lo que conviene recordar pero no es "
                                "una convención permanente.",
              {"texto": texto,
               "tipo": {"type": "string", "description": "nota, evento, preferencia..."}},
              ["texto"]),
            h("recordar_permanente", "Apunta un hecho o convención en la memoria "
                                     "permanente (JARVIS.md), que se carga en "
                                     "cada conversación. Solo para lo que SIEMPRE "
                                     "debe recordarse.",
              {"nota": texto,
               "seccion": {"type": "string",
                           "description": "Preferencias fijas, Convenciones, Proyectos en curso o Notas"}},
              ["nota"]),
            h("automejorar", "JARVIS edita su PROPIO código en una rama nueva, "
                             "corre los tests y deja el resultado para que el "
                             "señor lo revise y mergee. Nunca toca main ni "
                             "mergea. Requiere JARVIS_AUTOMEJORA=1.",
              {"objetivo": texto,
               "abrir_pr": {"type": "boolean", "description": "abrir Pull Request (necesita gh)"}},
              ["objetivo"]),
            h("delegar_subtarea", "Lanza un sub-agente aparte que resuelve una "
                                  "subtarea con sus propias herramientas y te "
                                  "avisa al terminar. Úsala para trabajo que "
                                  "puede correr mientras sigues con el señor.",
              {"tarea": texto,
               "en_segundo_plano": {"type": "boolean",
                                    "description": "true (def) = no esperar; false = esperar el resumen"}},
              ["tarea"]),
            h("mision_larga", "Lanza una misión de HORAS: parte el objetivo en "
                              "fases, replanifica entre fases, vigila el gasto y "
                              "rinde cuentas al acabar cada fase. Para objetivos "
                              "grandes que no caben en una tanda.",
              {"objetivo": texto}, ["objetivo"]),
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
        import time as _t
        # ── Filtro de permisos ──────────────────────────────────────────────
        try:
            import permisos
            politica = permisos.evaluar(nombre)
        except Exception:
            politica = "directo"
        if politica == "prohibido":
            self._auditar(nombre, argumentos, "prohibido", ok=False)
            return (f"Señor, no puedo ejecutar «{nombre}»: está prohibida en el "
                    f"modo «{__import__('permisos').modo()}».")
        if politica == "confirmar" and nombre not in self._confirmado:
            self.pendiente = {"nombre": nombre, "argumentos": argumentos or {}}
            resumen = ", ".join(f"{k}={str(v)[:40]}" for k, v in (argumentos or {}).items())
            self._auditar(nombre, argumentos, "pendiente de confirmación", ok=False)
            return (f"CONFIRMACIÓN REQUERIDA: iba a ejecutar {nombre}({resumen}). "
                    "No lo he hecho. Dígame «confirma» para proceder.")

        _inicio = _t.time()
        try:
            if nombre.startswith("mcp__"):
                import mcp_generico
                resultado = mcp_generico.llamar(nombre, argumentos or {}, log=self.log)
            else:
                metodo = getattr(self, f"_t_{nombre}", None)
                if metodo is None:
                    return f"No tengo ninguna herramienta llamada {nombre}."
                resultado = metodo(argumentos or {})
            self.usadas.append(nombre)
            self.log(f"[HERRAMIENTA] {nombre}({argumentos}) -> {str(resultado)[:80]}")
            self._auditar(nombre, argumentos, str(resultado)[:400], ok=True,
                          ms=int((_t.time() - _inicio) * 1000))
            return str(resultado or "hecho")
        except Exception as e:
            self.log(f"[HERRAMIENTA] {nombre} falló: {e}")
            self._auditar(nombre, argumentos, f"EXC {type(e).__name__}: {e}", ok=False,
                          ms=int((_t.time() - _inicio) * 1000))
            return f"La herramienta {nombre} falló: {e}"

    def _auditar(self, nombre, argumentos, detalle, ok=True, ms=0):
        """Deja constancia de cada tool-call en storage.acciones."""
        try:
            import json as _j
            from storage import get_storage
            args = _j.dumps(argumentos or {}, ensure_ascii=False)[:400]
            get_storage(log=self.log).registrar_accion(
                "herramienta_llm", nombre, args, ok, detalle, ms,
                agente=getattr(self.core, "nombre_agente", "JARVIS"))
        except Exception:
            pass

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

    def _t_ensayar_orden_movil(self, a):
        import sandbox_android
        return sandbox_android.informe(a.get("objetivo", ""), a.get("texto", ""),
                                       a.get("resource_id", ""),
                                       a.get("accion", "tap"), log=self.log)

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

    def _t_revisar_correo(self, a):
        import correo_gmail
        return correo_gmail.resumen(log=self.log) if not a.get("solo_importantes") \
            else "\n".join(
                f"{c['de']} — {c['asunto']}"
                for c in correo_gmail.no_leidos(15, solo_importantes=True, log=self.log)
            ) or "Sin correos importantes sin leer, señor."

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

    def _t_git_estado(self, a):
        import git_tools
        return git_tools.git_estado(a.get("repo", "."), log=self.log)

    def _t_git_diff(self, a):
        import git_tools
        return git_tools.git_diff(a.get("repo", "."), a.get("ruta", ""), log=self.log)

    def _t_correr_tests(self, a):
        import git_tools
        return git_tools.correr_tests(a.get("repo", "."), log=self.log)

    def _t_git_crear_rama(self, a):
        import git_tools
        return git_tools.crear_rama(a.get("repo", "."), a.get("nombre", ""), log=self.log)

    def _t_git_commit(self, a):
        import git_tools
        return git_tools.commit(a.get("repo", "."), a.get("mensaje", ""), log=self.log)

    def _t_revisar_pr(self, a):
        import git_tools
        return git_tools.revisar_pr(a.get("objetivo", ""), core=self.core, log=self.log)

    def _t_deshacer_ultimo(self, a):
        import deshacer
        return deshacer.deshacer_ultimo(1, log=self.log,
                                        set_pref=getattr(self.core, "set_pref", None))

    def _t_analizar_imagen(self, a):
        import multimodal
        return multimodal.analizar_imagen(self.core, a.get("ruta", ""),
                                          a.get("pregunta", ""), log=self.log)

    def _t_analizar_documento(self, a):
        import multimodal
        return multimodal.analizar_documento(self.core, a.get("ruta", ""),
                                             a.get("pregunta", ""), log=self.log)

    def _t_modelar_3d(self, a):
        import modelado3d
        return modelado3d.modelar(self.core, a.get("entrada", ""),
                                  t_pose=bool(a.get("t_pose")), log=self.log)

    def _t_holograma(self, a):
        import modelado3d
        modo = "t-pose" if str(a.get("modo", "")).lower().startswith("t") else "completo"
        return modelado3d.holograma(self.core, a.get("entrada", ""), modo=modo,
                                    log=self.log)

    def _t_resolver_ciencia(self, a):
        import ciencias
        r = ciencias.resolver(self.core, a.get("enunciado", ""), log=self.log)
        # Vacío = el motor no supo con ese enunciado. Se dice, para que el
        # modelo conteste por su cuenta en vez de quedarse callado.
        return r or ("No he podido convertir ese enunciado en un cálculo. "
                     "Respóndele tú razonándolo, y avísale de que no está "
                     "verificado con sympy.")

    def _t_graficar(self, a):
        import ciencias
        tipo = (a.get("tipo") or "").lower()
        dim = int(a.get("dim") or (3 if tipo in ("superficie", "implicita",
                                                 "curva3d", "parametrica3d") else 2))
        accion = {"superficie": "superficie3d", "implicita": "implicita3d",
                  "curva3d": "curva3d", "parametrica": "parametrica2d",
                  "polar": "polar", "campo": "campo2d"}.get(
                      tipo, "superficie3d" if dim == 3 else "grafica2d")
        expr = a.get("expresion", "")
        p = {"accion": accion, "expresion": expr,
             "expresiones": [s.strip() for s in expr.split(";") if s.strip()],
             "graficar": True, "dim": dim,
             "rango": [a.get("desde", -10), a.get("hasta", 10)]}
        r = ciencias.ejecutar(self.core, p, log=self.log)
        for ruta in (r.get("html"), r.get("png")):
            if ruta:
                import matematica
                matematica.abrir(ruta, log=self.log)
                break
        return (r.get("titular", "") + "\n" + "\n".join(r.get("pasos", [])[:12])
                + f"\nArchivos en {r.get('carpeta', '')}")

    def _t_formula_fisica(self, a):
        import fisica
        r = fisica.resolver_formula(a.get("ley", ""), a.get("datos") or {},
                                    a.get("incognita", ""), log=self.log)
        return "\n".join(r.get("pasos", [])) or "No pude con esa ley."

    def _t_quimica(self, a):
        import ciencias
        op = (a.get("operacion") or "masa_molar").lower()
        p = {"accion": op if op in ("masa_molar", "balancear", "elemento",
                                    "configuracion", "molecula", "tabla_periodica")
             else "masa_molar",
             "expresion": a.get("valor", "")}
        r = ciencias.ejecutar(self.core, p, log=self.log)
        for ruta in (r.get("html"), r.get("png")):
            if ruta:
                import matematica
                matematica.abrir(ruta, log=self.log)
                break
        return (r.get("titular", "") + "\n" + "\n".join(r.get("pasos", [])[:18])).strip()

    def _t_procesar_reunion(self, a):
        import reunion
        return reunion.procesar(self.core, a.get("ruta_audio", ""), log=self.log)

    def _t_buscar_en_memoria(self, a):
        import memoria_grafo, re as _re
        q = a.get("consulta", "")
        if _re.search(r"\b(ayer|anteayer|el (lunes|martes|mi[eé]rcoles|jueves|"
                      r"viernes|s[aá]bado|domingo)|semana pasada|hace \d+ d[ií]as)\b",
                      q.lower()):
            hs = memoria_grafo.episodico(q, log=self.log)
        else:
            hs = memoria_grafo.recall(q, log=self.log)
        if not hs:
            return "No tengo nada en memoria sobre eso, señor."
        return "\n".join(f"- {h['texto'][:160]}" for h in hs)

    def _t_recordar_hecho(self, a):
        import memoria_grafo
        n = memoria_grafo.recordar(a.get("texto", ""), tipo=a.get("tipo", "nota"),
                                   fuente="agente", log=self.log)
        return "Anotado en memoria, señor." if n else "No pude anotarlo."

    def _t_recordar_permanente(self, a):
        import memoria_proyecto
        return memoria_proyecto.anadir(a.get("nota", ""),
                                       a.get("seccion", "Notas"), log=self.log)

    def _t_automejorar(self, a):
        import auto_mejora
        return auto_mejora.proponer(self.core, a.get("objetivo", ""),
                                    bool(a.get("abrir_pr")), log=self.log)

    def _t_delegar_subtarea(self, a):
        import subagente
        return subagente.delegar(self.core, a.get("tarea", ""),
                                 a.get("en_segundo_plano", True), log=self.log)

    def _t_mision_larga(self, a):
        import mision
        return mision.mision_larga(self.core, a.get("objetivo", ""), log=self.log)

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
        conversacion = podar_conversacion(conversacion)
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
            # Una herramienta que necesita confirmación paró el bucle: se guarda
            # la acción pendiente en el core y se le dice al señor. La ejecuta
            # el siguiente turno si responde «confirma».
            if caja.pendiente:
                try:
                    core._tool_pendiente = dict(caja.pendiente)
                except Exception:
                    pass
                return (f"Señor, {resultado}", caja.usadas)

    # Se agotaron las rondas: contamos lo hecho en vez de callar.
    if caja.usadas:
        return ("He hecho lo que pude: " + ", ".join(caja.usadas) + ".", caja.usadas)
    return None


def ejecutar_pendiente(core, log=print):
    """Ejecuta la herramienta que quedó a la espera de «confirma». Devuelve
    texto o None si no había nada pendiente."""
    pend = getattr(core, "_tool_pendiente", None)
    if not pend:
        return None
    try:
        core._tool_pendiente = None
    except Exception:
        pass
    caja = Herramientas(core, log=log, confirmado=[pend["nombre"]])
    r = caja.ejecutar(pend["nombre"], pend.get("argumentos") or {})
    return f"Confirmado, señor. {r}"
