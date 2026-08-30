# Jarvis - Asistente Omnimodal Autónomo
# Guía rápida de inicio

## 📋 Requisitos previos

1. **Python 3.10+** recomendado
2. **API Key Eleven Labs** - Regístrate en https://elevenlabs.io/ y obtén tu key
3. **Servidor Qwen 3.4b** - Necesitas un endpoint OpenAI-compatible:
   - Opción A: Ollama local (`ollama serve` + `ollama pull qwen-plus`)
   - Opción B: vLLM o servidor propio en `http://localhost:8000/v1`
   - Opción C: API remota de Alibaba Cloud DashScope

## 🛠️ Instalación

```bash
# 1. Clona o asegúrate de estar en el directorio del proyecto
cd jarvis-definitivo

# 2. Crea y activa entorno virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Instala dependencias
pip install -r requirements.txt
# Nota: "headroom" (compresión de contexto) es una dependencia interna no
# publicada y viene comentada en requirements.txt — la instalación funciona
# sin ella (el import está protegido con try/except en jarvis_core.py).

# 4. Configura tus credenciales
cp .env.example .env
# Edita .env con tus claves reales
```

## ▶️ Ejecución

### Modo completo (recomendado):

```bash
# 1. Inicia Ollama (si usas modelo local)
ollama serve

# 2. (Opcional) Trae el modelo Qwen
ollama pull qwen-plus

# 3. Ejecuta la interfaz funcional de Jarvis
jarvis_start.bat
```

También puedes abrirla directamente:

```bash
python interfaz_jarvis.py
```

### Modo consola (respaldo):

```bash
python jarvis_pipecat_pipeline.py
```

Este modo acepta preguntas normales y utiliza el mismo núcleo de Ollama y TTS.

## 📁 Estructura de archivos

```
jarvis-definitivo/
├── interfaz_jarvis.py           # Interfaz HUD principal
├── jarvis_core.py               # Núcleo LLM, voz, memoria y telemetría
├── jarvis_pipecat_pipeline.py  # Modo consola de respaldo
├── requirements.txt              # Dependencias Python
├── .env.example                 # Variables de entorno ejemplo
├── prompt_diseño_ui_ux.md       # Directrices UI/UX
├── prompt_funciones_arquitectura.md  # Definición de herramientas MCP
├── prompt_contexto_agente.md    # System prompt de identidad
└── prompt_ideas_por_implementar.md   # Desarrollos futuros
```

## 🔧 Personalización

### Cambiar voz Eleven Labs:
Modifica `ELEVENLABS_VOICE_ID` en el pipeline o en `.env`.
Todas las voces disponibles: https://elevenlabs.io/voice-library
Usa una voz marcada como masculina. Si ElevenLabs no está disponible, Jarvis prioriza una voz masculina instalada en Windows.

### Ajustar Qwen 3.4b:
- Cambiar `QWEN_MODEL` en el pipeline (`qwen-plus`, `qwen-turbov2`, etc.)
- Modificar `system_instruction` para ajustar el tono de Jarvis
- Ajustar `temperature` y `max_tokens`

### Modo offline/online:
- **Online**: Usa tu API key de Qwen en la nube
- **Offline local**: Ejecuta Ollama y apunta `QWEN_BASE_URL` a `http://localhost:11434`

## 🖥️ Frontend web

El frontend activo y soportado es `web-hud/` (arrancado por `jarvis_web_start.bat`,
incluye su propio BFF en `web-hud/server/`). Los directorios `jarvis-fui/` y
`liquid-glass-jarvis/` son prototipos/UIs alternativas no conectadas a ningún
script de arranque actual — decisión pendiente de conservarlos o eliminarlos.

## 📱 Integración con la arquitectura completa

Este pipeline es la **Fase 1** de la arquitectura completa. Para escalar:

1. **Fase 2**: Agregar Mem0 (memoria en grafos vectoriales/key-value)
2. **Fase 3**: Integrar servidores MCP (Google Calendar, Home Assistant)
3. **Fase 4**: Implementar control de accesibilidad Android
4. **Fase 5**: Motores multimedia (Kling 3.0, Flux Pro)

## 🛡️ Problemas conocidos

- **Latencia >300ms**: Verifica tu conexión WebRTC y la distancia al servidor Qwen
- **Errores de API key**: Verifica que `ELEVENLABS_API_KEY` y `QWEN_API_KEY` sean válidos
- **Sin salida de audio**: Asegúrate de que tu dispositivo de salida esté configurado correctamente en el cliente WebRTC
- **ElevenLabs HTTP 402**: La API no tiene créditos o un plan activo para sintetizar. Jarvis seguirá respondiendo por texto y usará la voz integrada de Windows. Recarga o activa el plan de ElevenLabs para recuperar esa voz.

## 📞 Soporte

Para dudas sobre la integración Pipecat + ElevenLabs, consulta:
- Documentación oficial: https://docs.pipecat.ai
- Ejemplos GitHub: https://github.com/pipecat-ai/pipecat/tree/main/examples
