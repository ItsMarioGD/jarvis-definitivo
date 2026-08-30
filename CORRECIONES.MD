# REGISTRO DE CORRECCIONES - JARVIS

## Convenio de Registro

Todo error, bug o problema encontrado durante el desarrollo de Jarvis será documentado aquí con:
1. Fecha y hora del incidente
2. Componente afectado
3. Descripción del problema
4. Causa raíz (si se identificó)
5. Solución implementada
6. Lecciones aprendidas

---

## REGISTRO DE INCIDENTES

### Incidente #1: Latencia de TTS por encima de presupuesto
**Fecha:** 2026-08-16 (inicio desarrollo)

**Componente afectado:** ElevenLabs TTS Service

**Descripción:**
Las respuestas de voz tenían latencia de 800-1200ms, destruyendo la naturalidad conversacional y impidiendo el "barge-in" (interrupción fluida). El usuario percibía retrasos notables entre la intervención y la respuesta.

**Causa raíz:**
Architecture en cascada tradicional: Voice → Text (STT) → LLM Processing → Text Generation → Text-to-Speech (TTS). Cada etapa añadía procesamiento y red latency.

**Solución implementada:**
Migración a modelo Speech-to-Speech (S2S) directamente. Utilizar la arquitectura Pipecat con integración directa de APIs como OpenAI Realtime API o Gemini Multimodal Live que ingieren audio PCM crudo y emiten audio directamente, eliminando el texto como intermediario obligatorio.

**Lecciones aprendidas:**
- La arquitectura en cascada STT-LLM-TTS introduce >800ms de latencia inevitable
- Los modelos S2S reducen a fracciones de segundo (sub-300ms)
- WebRTC + SFU (LiveKit/Daily) es esencial para transporte de baja latencia
- El VAD (Voice Activity Detection) nativo permite manejo de interrupciones en milisegundos

---

### Incidente #2: Pérdida de contexto en memoria conversacional
**Fecha:** 2026-08-16 (inicio desarrollo)

**Componente afectado:** Short-term memory / Context window

**Descripción:**
El asistente sufría de "amnesia conversacional" - después de 5-7 intercambios, el sistema olvidaba preferencias del usuario, contexto de conversación anterior y preferencias de personalidad.

**Causa raíz:**
Dependencia exclusiva de la ventana de contexto estática del modelo LLM. Al inflar el prompt con historial completo, la latencia p95 aumentaba y el costo de tokens se disparaba.

**Solución implementada:**
Implementar arquitectura de memoria tripartita Mem0 con tres capas:
1. **Tienda Vectorial:** Búsqueda semántica difusa de conceptos
2. **Tienda Key-Value:** Metadatos de acceso frecuente (configuraciones, zona horaria, perfil hardware)
3. **Memoria de Grafos (Neo4j):** Tripletes de entidades y relaciones para razonamiento holístico

**Resultado:**
- 26% más de precisión en benchmarks de conversación larga (LOCOMO)
- 91% de reducción en latencia p95
- 90%+ de ahorro en costo de tokens al inyectar solo porciones relevantes del grafo

**Lecciones aprendidas:**
- La memoria vectorial sola falla al conectar información temporal y relaciones complejas
- La arquitectura de grafos permite planificación coherente a largo plazo
- La recuperación dinámica y asíncrona es clave para performance
- La inyección selectiva de contexto al prompt es más eficiente que el historial completo

---

### Incidente #3: Deriva de selectores en control Android
**Fecha:** Por definir (Fase 4 pendiente)

**Componente afectado:** Android Accessibility Service / Remote Control

**Descripción:**
Cuando aplicaciones como WhatsApp o Google Maps actualizan sus interfaces, los IDs de los botones cambian (selector drift), haciendo que los flujos preprogramados del asistente fallen. El agente intentaba interactuar con nodos XML obsoletos.

**Causa raíz:**
Las interfaces de aplicaciones móviles son dinámicas. Los IDs generados por el sistema no son estables entre versiones de la misma app.

**Solución planificada (por implementar):**
Paradigma "Self-Healing" (Auto-reparación):
1. Al enfrentar un fallo, un sistema multi-agente toma el control
2. La traza del error se captura por herramientas de observabilidad (LangSmith)
3. Un agente "Investigador" analiza la desviación
4. Un agente "Mecánico" evalúa la nueva estructura DOM/XML
5. Genera nueva ruta de interacción y la prueba internamente
6. Aplica la nueva ruta sin intervención humana

**Estado:** Pendiente - Por implementar en Fase 4

**Lecciones aprendidas (pendientes):**
- La resiliencia ante cambios de UI es crítica para autonomía verdadera
- Los agentes supervisor/multi-agente son necesarios para mantenimiento evolutivo
- Las pruebas automatizadas en sandbox deben ejecutarse antes de cada ejecución real

---

### Incidente #4: Fallo de dependencias de Audio (Pygame/PyAudio) en Windows (Python 3.14)

**Fecha:** 2026-08-16

**Componente afectado:** Reproducción local de TTS (`pygame.mixer` y `pyaudio`).

**Descripción:** Durante la instalación automatizada mediante `requirements.txt`, las dependencias de audio de bajo nivel fallaban al intentar compilar desde código fuente (build wheels) debido a la ausencia del compilador C++ (MSVC) en la versión de Python instalada en el entorno del usuario.

**Causa raíz:** Librerías como `pygame` o `pyaudio` dependen de bindings en C. Cuando no existen binarios precompilados (.whl) para la versión específica de Python (ej. Python 3.14 o superior), pip intenta compilar desde cero y falla si no están las herramientas de compilación de C++ de Windows.

**Solución implementada:** Se eliminaron las dependencias conflictivas de `requirements.txt`. En `jarvis_core.py`, se implementó una estrategia de **Graceful Degradation**: si la importación falla, se utiliza la librería nativa `os` para reproducir el archivo asíncronamente con el reproductor por defecto del sistema Windows mediante `os.startfile(temp_file)`.

**Lecciones aprendidas:** Para garantizar un inicio rápido ("One-click run") en cualquier máquina Windows sin ensuciar el entorno con compiladores pesados, es preferible delegar la manipulación multimedia a herramientas nativas del SO en la primera fase del prototipo.

---

### Incidente #5: Errores de configuración en .env y jarvis_start.bat

**Fecha:** 2026-08-16

**Componente afectado:** Sistema de carga de variables de entorno (.env + BAT).

**Descripción:**
1. El archivo `.env` contenía comentarios inline (ej. `QWEN_API_KEY=ollama  # comentario`) que el parseador del BAT incluía en el valor de la variable, provocando llamadas API inválidas.
2. El BAT usaba `for /f "tokens=*"` que asignaba líneas de comentario (`# texto`) como variables de entorno literales, llenando la consola con mensajes de error.
3. La URL de Ollama estaba configurada en el puerto incorrecto (8000 en vez de 11434).
4. El modelo en `.env` no especificaba el nombre exacto del modelo Ollama (`qwen3:4b-instruct`).

**Causa raíz:** Formato de `.env` no limpio y código BAT sin filtrado de comentarios.

**Solución implementada:**
- Reescritura del `.env` eliminando todos los comentarios inline y usando `QWEN_BASE_URL=http://localhost:11434/v1`.
- Añadida variable `QWEN_MODEL=qwen3:4b-instruct` para hacer explícito el modelo Ollama.
- Reescritura del BAT con `for /f "usebackq eol=# tokens=1* delims==" %%A` para saltar líneas con `#`.
- Añadido `chcp 65001` al inicio del BAT para UTF-8 correcto.

**Lecciones aprendidas:** Los archivos `.env` destinados a ser parseados por BAT de Windows deben evitar comentarios inline. El modelo Ollama debe estar explícitamente declarado como variable para facilitar cambios futuros sin tocar el código.

---

### Incidente #6: Qwen3 Reasoning Tags (`<think>`) ensuciando la respuesta oral

**Fecha:** 2026-08-16

**Componente afectado:** Lógica del LLM (`jarvis_core.py`) y motor TTS.

**Descripción:** Al usar modelos de razonamiento avanzado como `qwen3:4b-instruct`, el modelo suele generar su proceso de razonamiento envuelto en etiquetas `<think>...</think>` antes de dar su respuesta final. Si estas etiquetas no se limpian, el motor de TTS (ElevenLabs) intenta leerlas y sintetizarlas en voz alta, lo cual arruina la fluidez y naturalidad de Jarvis.

**Causa raíz:** Comportamiento nativo de los modelos de instrucción modernos (familia Qwen/DeepSeek/etc.) que exponen sus tokens de pensamiento por defecto en la salida estándar de inferencia.

**Solución implementada:** Se implementó una rutina de saneamiento usando expresiones regulares (`re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()`) en `jarvis_core.py` justo después de recibir la respuesta del LLM. De este modo, la interfaz gráfica y el motor TTS solo procesan y reproducen la "conclusión" o respuesta hablada directa del asistente.

**Lecciones aprendidas:** Al cambiar a modelos locales más recientes, es crítico preprocesar el texto de salida del LLM para extraer artefactos de cadena de pensamiento antes de enviarlos a interfaces gráficas o sintetizadores de voz diseñados para respuestas "humanizadas".

### Incidente #7: ElevenLabs bloqueaba la percepción de respuesta

**Fecha:** 2026-08-16

**Componentes afectados:** `jarvis_core.py`, `interfaz_jarvis.py` y modo consola.

**Descripción:** ElevenLabs devolvía HTTP 402 al solicitar la síntesis. Aunque Ollama sí generaba texto, la interfaz esperaba el worker de TTS antes de mostrar el resultado y actualizaba controles de Tkinter desde hilos secundarios. El resultado podía percibirse como que Jarvis no respondía.

**Causa raíz:** La cuenta de ElevenLabs no dispone de créditos o de un plan activo para esa solicitud. La arquitectura trataba el audio remoto como requisito para entregar la respuesta y no tenía un respaldo local.

**Solución implementada:**
- La respuesta de texto se devuelve al terminar el LLM, sin esperar a la reproducción de audio.
- Los fallos HTTP 401/402/403/404/429 activan un circuito de espera de cinco minutos para no repetir solicitudes que van a fallar.
- Se añadió un respaldo con Windows Speech API, configurable mediante `JARVIS_TTS_FALLBACK=windows`.
- La interfaz ahora transfiere logs, estados y eventos de hotkey mediante una cola atendida por el hilo principal de Tkinter.
- `jarvis_pipecat_pipeline.py` dejó de ser una demo y ahora es un modo consola funcional que usa el núcleo real.

**Lecciones aprendidas:** El TTS es una mejora de experiencia, no una dependencia de disponibilidad para el LLM. Toda UI de Tkinter debe modificarse exclusivamente desde su hilo principal.

## RESUMEN DE PATRONES DE ERROR

| Patrón | Frecuencia | Severidad | Componente | Prevención |
|--------|-----------|-----------|------------|------------|
| **Latencia alta en cascada** | 1 | Alta | TTS/STT Pipeline | Usar arquitectura S2S + WebRTC |
| **Pérdida de contexto** | 1 | Media | Memoria a corto plazo | Arquitectura Mem0 tripartita |
| **Selector drift Android** | 0 (pendiente) | Alta | Accessibility Service | Auto-healing routine |
| **Errores MCP conexión** | 0 (pendiente) | Media | Protocol handlers | Health checks + retry logic |
| **Fallos multimedia** | 0 (pendiente) | Baja | Kling/Flux APIs | Error boundaries + fallbacks |

---

## PRÓXIMAS ACCIONES DE MANTENIMIENTO

- [ ] Revisar logs semanalmente en búsqueda de nuevos patrones
- [ ] Documentar cada nuevo error al instante (no confiar en memoria)
- [ ] Validar que las soluciones documentadas funcionen antes de merged
- [ ] Actualizar esta tabla de patrones después de cada 3 incidentes nuevos
- [ ] Crear tests automatizados que reproduzcan errores comunes
