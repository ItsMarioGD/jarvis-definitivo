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

## 📱 Que el teléfono llegue al PC (Tailscale)

El servidor escucha en `0.0.0.0`, pero eso no basta: el móvil solo llega si está
en el mismo Wi-Fi **y** el Firewall de Windows deja pasar el puerto. Tailscale
resuelve las dos cosas creando una red privada entre el PC y el teléfono.

```bat
:: en el PC, botón derecho → Ejecutar como administrador
instalar_tailscale.bat
```

Ese script:

1. Instala Tailscale (winget y, si falla, el MSI oficial).
2. Levanta la VPN y abre el enlace de login.
3. Abre en el Firewall los puertos **5000** (web), **8765** (JARVIS) y **8766**
   (ULTRON) para la red local y para el rango de Tailscale.
4. Imprime la dirección exacta que hay que abrir en el móvil.

En el teléfono: instale la app **Tailscale**, entre con **la misma cuenta**,
déjela conectada y abra la dirección que imprimió el script. El PIN de
emparejamiento sale en `http://localhost:5000/pair`.

Para ver en cualquier momento cómo está la conexión:

```bash
python tailscale_setup.py --estado     # diagnóstico en JSON
python tailscale_setup.py --firewall   # solo abrir los puertos
```

También está en la interfaz: botón **◎ Red** en el PC, pestaña **Conexión** en
el móvil. Y por voz: «*estado de la red*».

## ⌘ Comandos de voz

Una frase suya, una acción inmediata: los comandos se despachan **antes** que
cualquier habilidad de fábrica y sin pasar por el modelo, así que responden al
instante.

**Vienen puestos** (editables o borrables): `modo enfoque`, `modo estudio`,
`modo reunión`, `modo desarrollo`, `bloquea el equipo`, `estado de la red`,
`quiero recortar la pantalla` e `informe de guardia` (solo ULTRON).

**Para inventar los suyos**, tres caminos:

| Dónde | Cómo |
|-------|------|
| PC | Botón **⌘ Comandos** → *Nuevo comando* (varios pasos por comando) |
| Móvil | Botón **⌘** de la cabecera → pestaña *Crear* |
| Hablando | «*crea un comando: cuando diga radio, abre open.spotify.com*» |

Cada comando tiene una o varias frases (se ignoran tildes, mayúsculas y
muletillas: «oye Jarvis, activa el **modo cine**» dispara «modo cine») y una
lista de pasos:

| Tipo | Qué hace |
|------|----------|
| `decir` | Solo responde una frase |
| `abrir` | Abre una web, un archivo o una carpeta |
| `programa` | Ejecuta un programa |
| `shell` | Ejecuta un comando del sistema |
| `teclas` | Pulsa una combinación (`win+shift+s`) |
| `escribir` | Escribe texto donde esté el cursor |
| `agente` | Le pide algo al propio agente en lenguaje natural |
| `esperar` | Pausa N segundos entre pasos |

Otras frases útiles: «*qué comandos tienes*», «*olvida el comando radio*».

Se guardan en `<Descargas>/JARVIS/Prefs/comandos_voz.json`, compartidos por
JARVIS y ULTRON (o asignados a uno solo, si lo prefiere).

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
