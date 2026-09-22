#!/usr/bin/env python3
"""
herramientas_llm.py - Que el cerebro pueda ACTUAR, no solo hablar
=================================================================
Hasta ahora el flujo era: regex -> si ninguna habilidad reconoce la frase, el
LLM contesta con palabras. El modelo no podia ejecutar nada. Por eso una orden
como «organiza la carpeta de descargas y avisame por Telegram cuando acabes»
recibia una respuesta amable y ni un solo archivo movido: ninguna regex la
cubria, y el cerebro no tenia manos.

Aqui estan las manos. Claude admite herramientas, y el traductor las
convierte del formato de OpenAI, asi que se le ofrece un juego y se ejecuta:

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

# Tope de salida de cada ronda. Estaba en 400 y con los modelos que RAZONAN
# —los de Pollinations y los de Anthropic— eso se queda corto: el razonamiento
# sale del mismo presupuesto, así que el modelo pensaba, se le acababa el turno
# y devolvía una respuesta VACÍA. Las tool-calls sí llegaban con 400; lo que se
# perdía era la respuesta hablada, que es peor porque JARVIS se quedaba mudo.
MAX_TOKENS = int(os.getenv("JARVIS_TOOLS_MAX_TOKENS", "2048"))


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
            h("navegador_tarea", "Hace una TAREA COMPLETA en la web: navega, pulsa, "
                                 "rellena formularios y lee el resultado, mirando la "
                                 "página de verdad. Para cualquier cosa que exija "
                                 "moverse por un sitio (consultar un pedido, sacar un "
                                 "dato de una web, rellenar un formulario). NO escribe "
                                 "contraseñas ni datos de tarjeta, y NO pulsa botones "
                                 "de pago: esos pasos los deja al señor.",
              {"objetivo": {"type": "string",
                            "description": "el encargo entero, en una frase"},
               "url": {"type": "string", "description": "dirección de partida, si la hay"}},
              ["objetivo"]),
            h("navegador_ensayo", "Ensayo general de una tarea web: dice paso a paso "
                                  "qué HARÍA sin pulsar nada. Úsala antes de "
                                  "navegador_tarea cuando la tarea toque una cuenta "
                                  "del señor o algo con consecuencias.",
              {"objetivo": texto, "url": texto}, ["objetivo"]),
            h("navegador_mirar", "Qué hay ahora mismo en la pestaña del navegador de "
                                 "JARVIS: dirección, texto visible y qué se puede "
                                 "pulsar. Solo lectura.", {}),
            h("navegador_datos", "Lee el JSON que la página pide por detrás, en vez "
                                 "de rascar el texto. Para tablas, listados, "
                                 "precios, horarios o saldos: el dato sale exacto "
                                 "y no se rompe con el rediseño. Úsala DESPUÉS de "
                                 "abrir la página. Sin patrón, lista lo que ha "
                                 "pedido.",
              {"patron": {"type": "string",
                          "description": "trozo de la URL de la API, p. ej. "
                                         "«/api/pedidos» o «precios»"},
               "indice": {"type": "integer",
                          "description": "0 = la respuesta más grande (por defecto)"}}),
            h("navegador_diagnostico", "Abre o recarga una web y dice QUÉ ESTÁ ROTO: "
                                       "errores de JavaScript, excepciones y "
                                       "peticiones fallidas o con 4xx/5xx. Para "
                                       "depurar la web del señor o entender por qué "
                                       "otra no funciona.",
              {"url": {"type": "string",
                       "description": "dirección; vacío = recarga la pestaña actual"}}),
            h("navegador_abrir", "Abre una dirección en el navegador de JARVIS y "
                                 "devuelve el título de la página.",
              {"url": texto}, ["url"]),
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
            h("escanear_objeto", "ESCANEA un objeto real con la cámara (la del PC "
                                 "o la del teléfono) y lo convierte en un modelo 3D "
                                 "con las piezas separadas, que se abre como "
                                 "holograma interactivo. Úsala cuando el señor "
                                 "quiera digitalizar algo que tiene delante.",
              {"origen": {"type": "string", "description": "pc (webcam) o telefono (QR)"},
               "nombre": {"type": "string", "description": "qué es el objeto, si se sabe"}}),
            h("holograma_vivo", "Abre el visor holográfico interactivo con un "
                                "escaneo (el último si no se dice cuál). Ahí se le "
                                "puede hablar y se le puede mandar acciones.",
              {"id": {"type": "string", "description": "id del escaneo (opcional)"}}),
            h("holo_accion", "Ejecuta UNA acción en el holograma abierto: desarmar, "
                             "armar, aislar, mostrar_todo, ocultar, resaltar, girar, "
                             "vista, zoom, rayos_x, alambre, solido, seccion, medir, "
                             "etiquetas, color, animar, piramide, comparar, cargar, "
                             "quitar_modelo, reset, capturar, listar, decir.",
              {"nombre": {"type": "string", "description": "nombre exacto de la acción"},
               "argumentos": {"type": "string",
                              "description": "JSON con los argumentos, p. ej. "
                                             "{\"pieza\": \"tapa\"}"}},
              ["nombre"]),
            h("prototipo_3d", "Diseña un modelo NUEVO derivado del objeto escaneado "
                              "(una variante, una mejora, otra cosa hecha con sus "
                              "piezas) y lo pone al lado en el holograma.",
              {"idea": {"type": "string", "description": "qué prototipo quiere el señor"},
               "base": {"type": "string", "description": "id del escaneo de partida (opcional)"}},
              ["idea"]),
            h("ojo_global", "Maneja God's Eye View: globo 3D fotorrealista con datos "
                            "públicos EN VIVO (aviones, militares, barcos, satélites, "
                            "lanzamientos, terremotos, incendios, tráfico, cámaras de "
                            "calle, radio, cables submarinos, centros de datos). "
                            "Úsala para abrirlo, cerrarlo, ver su estado, instalarlo o "
                            "actualizarlo, o pedir el catálogo de funciones.",
              {"accion": {"type": "string",
                          "description": "abrir, cerrar, estado, catalogo, instalar o actualizar"}}),
            h("ojo_global_accion",
              "Ejecuta UNA función de God's Eye View. Las hay todas: "
              "fly_to_location, select_nearest_aircraft, adjust_camera_zoom, "
              "zoom_to_globe, set_layer_visibility, show_data_layers_menu, "
              "set_panel_open, set_context_mode, control_cockpit, set_visual_style, "
              "get_entity_context, get_current_view_state, set_hud, set_detection, "
              "set_map_stack, set_post_processing, control_scene, control_cctv, "
              "control_radio, track_entity, stop_tracking, frame_overhead, "
              "annotate_map, clear_annotations, move_camera, fly_route, "
              "analyst_query, next_iss_pass. Si el ojo global no está abierto, lo "
              "abre. Pide antes «ojo_global» con accion=catalogo si dudas de los "
              "argumentos. Para sitios de fuera de EE. UU. conviene pasar latitude "
              "y longitude: sin clave de Google la búsqueda por texto tira de un "
              "geocodificador sesgado por la vista actual.",
              {"nombre": {"type": "string", "description": "nombre exacto de la función"},
               "argumentos": {"type": "string",
                              "description": "JSON con los argumentos, p. ej. "
                                             "{\"query\": \"Kiev\", \"viewMode\": \"close\"}"}},
              ["nombre"]),
            h("ojo_global_js", "Escotilla del ojo global: ejecuta JavaScript dentro de "
                               "la página con `gev` = window.__godsEyeView (viewer de "
                               "Cesium, dataManager, sceneDirector, anotaciones, "
                               "mapStackController). Solo para lo que las funciones "
                               "del catálogo no cubran. Devuelve lo que retorne.",
              {"codigo": {"type": "string",
                          "description": "cuerpo de una función async; use return"}},
              ["codigo"]),
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
            h("simular_ciencia", "SIMULACIÓN ANIMADA en 3D: no una foto, sino el "
                                 "sistema moviéndose, con play, barra de tiempo y "
                                 "las magnitudes vivas. Sistemas: tiro (proyectil "
                                 "con rozamiento), orbita (N cuerpos), pendulo "
                                 "(simple y doble), muelle (resonancia), carga "
                                 "(campo electromagnético), lorenz (caos), cuerda, "
                                 "membrana, molecula (vibrando) y ecuaciones (las "
                                 "que dicte el señor, integradas con Runge-Kutta). "
                                 "Úsala cuando pida ver algo MOVERSE o evolucionar "
                                 "en el tiempo; para un dibujo quieto, "
                                 "resolver_ciencia.",
              {"sistema": {"type": "string",
                           "description": "tiro, orbita, pendulo, muelle, carga, "
                                          "lorenz, cuerda, membrana, molecula o "
                                          "ecuaciones"},
               "parametros": {"type": "string",
                              "description": "JSON con los parámetros del sistema, "
                                             "p. ej. {\"l1\": 1, \"l2\": 0.8} o "
                                             "{\"ecuaciones\": [\"x'' = -9.8\"]}"}},
              ["sistema"]),
            h("despejar_ecuacion", "Despeja CUALQUIER ecuación de física o "
                                   "ingeniería, con unidades y comprobación "
                                   "dimensional. No está limitada a un "
                                   "formulario: vale la ley que sea, la del "
                                   "libro o la que dictó el profesor. Da la "
                                   "fórmula despejada y, si hay datos para "
                                   "todo lo demás, el número con su unidad.",
              {"ecuacion": {"type": "string",
                            "description": "con un igual, p. ej. «v = v0 + a*t» "
                                           "o «E = m*c**2». Respeta mayúsculas: "
                                           "P y p son cosas distintas"},
               "datos": {"type": "string",
                         "description": "JSON con los conocidos y su unidad, "
                                        "p. ej. {\"a\": \"9.8 m/s^2\", \"t\": \"3 s\"}"},
               "incognita": {"type": "string",
                             "description": "qué despejar; vacío si solo falta una"}},
              ["ecuacion"]),
            h("vectorizar_documentos", "Completa la búsqueda POR SIGNIFICADO de "
                                       "los documentos ya indexados que aún no "
                                       "tienen vector. Úsala si el señor dice "
                                       "que no encuentra algo que sabe que está "
                                       "en sus apuntes.", {}),
            h("convertir_unidades", "Pasa una cantidad de una unidad a otra: "
                                    "«120 km/h» a «m/s», «3 atm» a «Pa».",
              {"cantidad": {"type": "string", "description": "p. ej. «120 km/h»"},
               "a": {"type": "string", "description": "la unidad de destino"}},
              ["cantidad", "a"]),
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

    def _t_vectorizar_documentos(self, a):
        import indice_documentos
        return indice_documentos.vectorizar_pendientes(log=self.log)

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

    def _t_escanear_objeto(self, a):
        import escaner3d
        return escaner3d.escanear(self.core, a.get("origen") or "pc",
                                  nombre=a.get("nombre", ""), log=self.log)

    def _t_holograma_vivo(self, a):
        import escaner3d
        ident = a.get("id", "")
        url = escaner3d.abrir_holograma(ident, log=self.log)
        if not url:
            return ("Señor, no tengo ningún escaneo. Dígame «escanea este objeto» "
                    "y se lo monto.")
        u = escaner3d.ultima()
        return f"Holograma abierto, señor: «{u.get('nombre', '')}». {url}"

    def _t_holo_accion(self, a):
        import escaner3d
        args = a.get("argumentos") or {}
        if isinstance(args, str):
            try:
                args = __import__("json").loads(args or "{}")
            except Exception:
                args = {}
        return escaner3d.ejecutar([{"nombre": a.get("nombre", ""), "args": args}],
                                  log=self.log) or "Hecho, señor."

    def _t_prototipo_3d(self, a):
        import escaner3d
        return escaner3d.prototipo(self.core, a.get("idea", ""), a.get("base", ""),
                                   log=self.log)

    # ── navegador ───────────────────────────────────────────────────────────
    def _t_navegador_tarea(self, a):
        import navegador
        return navegador.navegar(a.get("objetivo", ""), core=self.core,
                                 url_inicial=a.get("url", ""), log=self.log)

    def _t_navegador_ensayo(self, a):
        import navegador
        return navegador.navegar(a.get("objetivo", ""), core=self.core, seco=True,
                                 url_inicial=a.get("url", ""), log=self.log)

    def _t_navegador_mirar(self, a):
        import navegador
        return navegador.mirar(log=self.log)

    def _t_navegador_abrir(self, a):
        import navegador
        return navegador.abrir(a.get("url", ""), log=self.log)

    def _t_navegador_datos(self, a):
        import navegador
        return navegador.datos(a.get("patron", ""), int(a.get("indice") or 0),
                               log=self.log)

    def _t_navegador_diagnostico(self, a):
        import navegador
        return navegador.diagnosticar(a.get("url", ""), log=self.log)

    def _t_ojo_global(self, a):
        import ojo_global
        accion = str(a.get("accion") or "abrir").strip().lower()
        if accion.startswith("cerr") or accion.startswith("apag"):
            return ojo_global.cerrar(log=self.log)
        if accion.startswith("estad"):
            return ojo_global.estado(log=self.log)
        if accion.startswith("catal") or accion.startswith("func"):
            return ojo_global.catalogo(log=self.log)
        if accion.startswith("actualiz"):
            return ojo_global.instalar(log=self.log, actualizar=True)
        if accion.startswith("instal"):
            return ojo_global.instalar(log=self.log)
        return ojo_global.abrir(self.core, log=self.log)

    def _t_ojo_global_accion(self, a):
        import ojo_global
        return ojo_global.accion(a.get("nombre", ""), a.get("argumentos"),
                                 log=self.log)

    def _t_ojo_global_js(self, a):
        import ojo_global
        return ojo_global.js(a.get("codigo", ""), log=self.log)

    def _t_resolver_ciencia(self, a):
        import ciencias
        r = ciencias.resolver(self.core, a.get("enunciado", ""), log=self.log)
        # Vacío = el motor no supo con ese enunciado. Se dice, para que el
        # modelo conteste por su cuenta en vez de quedarse callado.
        return r or ("No he podido convertir ese enunciado en un cálculo. "
                     "Respóndele tú razonándolo, y avísale de que no está "
                     "verificado con sympy.")

    def _t_simular_ciencia(self, a):
        import simulacion
        parametros = a.get("parametros") or {}
        if isinstance(parametros, str):
            # El modelo manda el JSON como texto más veces de las que lo manda
            # como objeto. Si viene roto, se sigue con los valores por defecto
            # en vez de tumbar la simulación entera.
            try:
                parametros = json.loads(parametros) if parametros.strip() else {}
            except Exception:
                self.log(f"[SIM] Parámetros ilegibles: {str(parametros)[:80]}")
                parametros = {}
        r = simulacion.simular(a.get("sistema", ""), parametros, log=self.log)
        if not r.get("ok"):
            return " ".join(r.get("pasos") or ["No pude montar esa simulación."])
        return (f"Simulación abierta en el navegador: "
                f"{r['datos'].get('titulo', '')}.\n" + "\n".join(r.get("notas") or []))

    def _t_despejar_ecuacion(self, a):
        import fisica_general as FG
        datos = a.get("datos") or {}
        if isinstance(datos, str):
            try:
                datos = json.loads(datos) if datos.strip() else {}
            except Exception:
                self.log(f"[FISICA] Datos ilegibles: {str(datos)[:80]}")
                datos = {}
        r = FG.despejar(a.get("ecuacion", ""), datos, a.get("incognita", ""),
                        log=self.log)
        return "\n".join(r.get("pasos") or ["No pude despejar eso."])

    def _t_convertir_unidades(self, a):
        import fisica_general as FG
        r = FG.convertir(a.get("cantidad", ""), a.get("a", ""))
        return "\n".join(r.get("pasos") or ["No pude convertir eso."])

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
        from proveedor_claude import cliente as OpenAI
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
                tool_choice="auto", temperature=0.3, max_tokens=MAX_TOKENS)
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
