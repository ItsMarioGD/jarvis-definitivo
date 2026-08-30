# CONTEXTO DEL PROYECTO JARVIS

## Estado Actual: FASE 1 - OPERATIVA ✅

### Objetivo General
Desarrollar un asistente inteligente omnimodal y autónomo con capacidades de voz natural, control remoto de dispositivos móviles, memoria gráfica avanzada y generación multimedia hiperrealista. El asistente evoca la arquetípica personalidad de "Jarvis": proactivo, con carisma computacional y hiper-agencia sobre entornos digitales y físicos.

### Progreso Logrado (Fecha: 2026-08-16)

#### ✅ COMPLETADO:
1. **Arquitectura de Sistemas** - Documentada en el informe detallado con 9 fases y 7 secciones temáticas
2. **Prompt de Identidad** - `prompt_contexto_agente.md` - System prompt con tono "Jarvis", carisma computational y proactividad temporal
3. **Directrices UI/UX** - `prompt_diseño_ui_ux.md` - Interfaz híbrida voz/chat con Glassmorphism, esfera de estado y HUD de operación remota
4. **Diccionario de Herramientas** - `prompt_funciones_arquitectura.md` - 6 herramientas MCP definidas (Android accessibility, Calendar, Kling, Mem0, Home Assistant, Self-Healing)
5. **Vector de Desarrollo** - `prompt_ideas_por_implementar.md` - 3 ideas futuras (multi-agente, sandbox móvil, paralingüística)
6. **Núcleo Lógico** - `jarvis_core.py` - Motor principal (Python) con STT, LLM, TTS, memoria persistente (SQLite) y listener UDP.
7. **Interfaz HUD** - `interfaz_jarvis.py` - UI (Python) rediseñada a un estilo HUD futurista con telemetría en tiempo real.
8. **Módulo Hotkey (C++)** - `jarvis_hotkey.cpp` - Microservicio Win32 para despertar a Jarvis globalmente (Ctrl+Alt+J) vía UDP.
9. **Módulo ADB (Java)** - `JarvisAdbBridge.java` - Puente para controlar dispositivos Android (preparación Sprint 6).
10. **Variables de Entorno** - `.env` - Configuradas y limpias (sin comentarios inline)
9. **Guía Rápida** - `QUICKSTART.md` - Instrucciones de instalación y ejecución

#### 🟡 EN CURSO:
- Fase 2: Implementación estructura cognitiva (Mem0, bases de datos Neo4j/Qdrant/Redis)
- Fase 3: Ecosistema MCP (Google Calendar, herramientas externas)
- Fase 4: Integración profunda Android (accesibilidad, control remoto)
- Fase 5: Generación multimedia (Kling 3.0, Flux Pro) y auto-reparación

### Componentes Técnicos Principales

| Componente | Estado | Descripción |
|------------|--------|-------------|
| **Orquestador** | ✅ | Framework Pipecat Python |
| **STT** | ✅ | Google Speech Recognition vía SpeechRecognition lib |
| **TTS** | ✅ | ElevenLabs voz Spuds Oxley (eleven_multilingual_v2) |
| **LLM** | ✅ | Qwen3:4b-instruct ejecutando localmente vía Ollama (puerto 11434) |
| **Transporte** | ✅ | Llamadas directas REST (no WebRTC en Fase 1) |
| **Interfaz** | ✅ | HUD Futurista estilo Iron Man: Arc Reactor animado (Canvas), 90 tick-marks, anillos giratorios, telemetría real, log de sistema. **Módulo de generación de imágenes añadido** - guarda en Descargas/JARVIS/Imagenes/YYYY-MM-DD/ |
| **Núcleo Lógico** | ✅ | `jarvis_core.py` (Python): Limpieza `<think>`, Contexto Dinámico, SQLite DB para memoria local persistente, y Listener UDP. |
| **Hotkey Global** | ✅ | `jarvis_hotkey.cpp` (C++): Intercepta Ctrl+Alt+J a nivel SO y activa el micrófono de Jarvis remotamente. |
| **Android Bridge** | ✅ | `JarvisAdbBridge.java` (Java): Wrapper ADB para controlar emuladores/dispositivos físicos. |
| **Telemetría** | ✅ | HUD panel lateral actualizándose cada 2 segundos con `psutil`. |
| **Memoria** | ✅ | Integrado en base de datos SQLite (`jarvis_memory.db`). |
| **MCP** | 🟡 | Por desplegar (Calendar, Home Assistant, Android) |
| **Multimedia** | 🟡 | Por integrar (Kling 3.0 video, Flux imágenes) |

### Próximos Hitos

1. **Hito 1:** Interfaz gráfica y núcleo base funcionales ✅ (HUD Futurista con Canvas, integración real con Qwen y ElevenLabs) - `interfaz_jarvis.py` y `jarvis_core.py`.
2. **Hito 2:** Integración Mem0 para memoria persistente
3. **Hito 3:** Servidores MCP operativos (Calendar, Home Assistant)
4. **Hito 4:** Control de accesibilidad Android operativo
5. **Hito 5:** Generación multimedia en tiempo real
6. **Hito 6:** Auto-reparación de interfaces (deriva de selectores)

### Variables de Entorno Críticas

```
ELEVENLABS_API_KEY=<tu_key>
ELEVENLABS_VOICE_ID=NOpBlnGInO9m6vDvFkFC
QWEN_BASE_URL=http://localhost:11434/v1
QWEN_API_KEY=ollama
QWEN_MODEL=qwen3:4b-instruct
JARVIS_MODE=full
```

### Referencias del Informe Original

Este proyecto sigue la arquitectura detallada en el informe "Arquitectura de Sistemas y Flujo de Implementación para un Asistente Inteligente Omnimodal y Autónomo" con énfasis en:
- Estrato perceptivo voz-voz (Sección 2)
- Control remoto Android via Accessibility Services (Sección 3)
- Memoria tripartita Mem0 (Sección 4)
- Planificación proactiva y Google Calendar (Sección 5)
- Generación multimedia Kling 3.0 y Flux (Sección 6)
- Auto-reparación y multi-agente (Sección 7)
- Flujo CI/CD de 5 fases (Sección 8)