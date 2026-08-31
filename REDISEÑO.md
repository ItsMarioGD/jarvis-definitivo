# AETHER — rediseño de JARVIS y ULTRON

Rediseño completo de las dos interfaces web y del sistema de voz. Un solo
lenguaje visual, dos identidades, y voz masculina garantizada en ambos.

---

## 1. Qué ha cambiado

### Interfaz

Ambos agentes comparten ahora un sistema de diseño, `hud_assets/`, tematizado
por el atributo `data-agent` del `<html>`. Un solo CSS, un solo motor de orbe,
un solo motor de voz, un solo shell de aplicación:

```
hud_assets/
  core.css   Tokens de diseño, cristal, bento, chat, paleta, responsive
  orb.js     Núcleo de energía reactivo (WebGL + fallback Canvas2D)
  voice.js   Motor de voz masculina + escucha (STT)
  hud.js     Shell: transporte, conversación, telemetría, paleta, ajustes
```

| | JARVIS | ULTRON |
|---|---|---|
| Fondo | azul noche `#03070F` | obsidiana `#070204` |
| Acento | cian arco reactor `#4FD8FF` | carmesí `#FF3B4E` |
| Secundario | ámbar `#F0B45E` | violeta `#C46BFF` |
| Orbe | plasma orgánico, anillos suaves | plasma facetado, filo angular |
| Tono | «a su servicio, señor» | «esperando un motivo» |

Lo que trae el HUD nuevo:

- **Orbe de energía en WebGL** que reacciona en tiempo real al nivel de audio
  (micrófono al escuchar, voz sintetizada al responder) con cinco estados:
  reposo, escucha, proceso, respuesta y alerta. Si no hay WebGL, cae a un
  fallback en Canvas2D.
- **Rejilla bento de telemetría** con CPU, RAM, disco, batería, modelo,
  latencia y tiempo activo, refrescada cada 5 s.
- **Paleta de comandos** (`Ctrl+K`) con 11 órdenes en JARVIS y 14 en ULTRON,
  navegable con teclado.
- **Conversación con markdown** renderizado de forma segura (se escapa el HTML
  antes de formatear, así que una respuesta del modelo no puede inyectar
  marcado), con copiar y repetir en voz alta por mensaje.
- **Transporte doble**: Socket.IO cuando está disponible, y si no, HTTP con
  reintento. La píldora de estado dice en cuál está.
- **Ajustes de voz** en un cajón lateral: elegir voz, velocidad, gravedad del
  timbre, motor (servidor o navegador) y locución automática.
- **Atajos**: `Ctrl+K` paleta · `Ctrl+J` micrófono · `Ctrl+,` ajustes · `/`
  enfocar entrada · `Esc` cancelar y callar.
- **Responsive real**, verificado a 414 px sin desplazamiento horizontal:
  los raíles pasan a hojas deslizantes y el dock queda fijo abajo.
- Respeta `prefers-reduced-motion`.

### Rutas nuevas

| Ruta | Qué sirve |
|---|---|
| `/` | HUD AETHER |
| `/mobile` | el mismo HUD (es responsive y lee `?token=` del QR) |
| `/assets/<archivo>` | el sistema de diseño compartido |
| `/classic` | la interfaz anterior, intacta |
| `/mobile/classic` | la vista móvil anterior |
| `/api/local_token` | (nuevo en ULTRON) token de voz sólo desde localhost |

Nada se ha borrado: las interfaces anteriores siguen accesibles en `/classic`.

---

## 2. Voz masculina

### El fallo que había

`jarvis_core.py` tomaba la voz de ElevenLabs así:

```python
self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
```

`21m00Tcm4TlvDq8ikWAM` es **Rachel**, una voz femenina del catálogo de
ElevenLabs. Sin `ELEVENLABS_VOICE_ID` en el entorno —el caso de cualquier
instalación recién clonada— ambos agentes hablaban en femenino. Además,
`/api/speak` devolvía `502 no_voice` si la variable estaba vacía, de modo que
el HUD del navegador se quedaba directamente mudo.

### Cómo queda

Un módulo nuevo, `jarvis_voice.py`, concentra la decisión en un solo sitio y
la aplica a las cuatro capas de síntesis:

| Capa | JARVIS | ULTRON |
|---|---|---|
| ElevenLabs | Daniel `onwK4e9ZLuTAKqWW03F9` (británico, autoritario) | Callum `N2lVS1w4EtoT3dr4eOWO` (transatlántico, intenso) |
| Piper (offline) | `es_ES-davefx-medium` | `es_ES-sharvard-medium` |
| Windows SAPI | voz masculina es-\*, velocidad 0 | voz masculina es-\*, velocidad −2 |
| Navegador | mejor voz masculina, pitch 0.80 | mejor voz masculina, pitch 0.58 |
| Ritmo | 0.99× | 0.86×, con pausas largas entre frases |

- **`jarvis_voice.py`** define los perfiles y expone `perfil()`,
  `voz_elevenlabs()`, `voz_piper()`, `cadena_piper()` y `ajustes_elevenlabs()`.
  Si el usuario configura a mano una voz femenina conocida, se respeta su
  decisión pero se registra un aviso: puede ser deliberado.
- **`jarvis_piper.py`** amplía el catálogo a cinco voces españolas, todas
  masculinas. La única femenina del repositorio rhasspy en español
  (`es_AR-daniela-high`) queda deliberadamente fuera, para que ninguna ruta
  de respaldo acabe dando una voz femenina. `hablar_como(agente, texto)`
  recorre la cadena de modelos del perfil: si el preferido no está descargado
  y la descarga falla, prueba el siguiente en vez de quedarse mudo.
- **`hud_assets/voice.js`** puntúa las voces del navegador: descalifica las
  femeninas conocidas (−500), premia las masculinas confirmadas (+120), el
  español (+100), la calidad neuronal (+40) y el orden de preferencia del
  perfil. Como las APIs de voz no exponen el género de forma fiable, se deduce
  del nombre del hablante, con listas que cubren Windows, macOS/iOS, Android
  y Chrome.

Comprobado con un catálogo de voces simulado: con Helena, Mónica, Álvaro,
Pablo, Jorge y Google español disponibles, ambos agentes eligen
«Microsoft Alvaro Online (Natural)» y las femeninas quedan al final de la lista.

### Configuración

Variables nuevas en `.env.example`, todas opcionales. Vacías, cada agente usa
la voz masculina de su perfil:

```
ELEVENLABS_VOICE_ID=   # voz global de respaldo
JARVIS_VOICE_ID=       # sólo JARVIS, tiene prioridad
ULTRON_VOICE_ID=       # sólo ULTRON, tiene prioridad
PIPER_VOICE=           # fuerza un modelo Piper concreto
```

---

## 3. Referencias y decisiones de diseño

La investigación previa y en qué se tradujo:

- **FUI/HUD de cine** (Iron Man, Minority Report) como referencia estética,
  con la advertencia recurrente en la bibliografía de UX: el reto no es que
  parezca futurista, sino que además funcione. De ahí que el orbe no sea
  decorativo —comunica cinco estados y el nivel de audio real— y que la
  telemetría muestre datos vivos, no barras de adorno.
- **Glassmorphism 2.0 (2026)**: superficies oscuras con paneles translúcidos
  encima, pero sin desenfoque pesado en todo. Aquí el cristal se aplica a
  paneles y superposiciones, con contraste alto en el texto.
- **Rejillas bento** para la telemetría, que permiten leer seis métricas de un
  vistazo sin jerarquía forzada.
- **Orbe reactivo por voz** con Web Audio API + shader GLSL, el patrón que se
  ha vuelto estándar en interfaces de agentes de voz. El nivel se calcula
  sobre la banda de voz (~85 Hz–3 kHz) con ataque rápido y caída lenta, para
  que acompañe al habla en vez de temblar.
- **Modo oscuro por defecto** con paleta completa en tokens.
- **Piper frente a Kokoro** para la voz local: Piper es el más rápido con
  diferencia (~0.03 de factor de tiempo real, primer audio en ~40 ms) y el que
  mejor encaja en un flujo sobre CPU; Kokoro suena más natural pero pesa más.
  Para un asistente que responde en voz, la latencia manda, así que Piper se
  queda como motor offline. Kokoro es un candidato razonable si algún día se
  prioriza la calidad sobre la latencia.

Fuentes consultadas:

- [Designing a *functional* futuristic user interface — Domo UX](https://medium.com/domo-ux/designing-a-functional-futuristic-user-interface-c27d617ce8cc)
- [Sci-fi interfaces — HUD](https://scifiinterfaces.com/tag/hud/)
- [UI Design Trends 2026: Glassmorphism Evolution, AI Interfaces, Dark Mode](https://lucky.graphics/learn/ui-design-trends-2026/)
- [12 UI/UX Design Trends for AI Apps (2026)](https://www.groovyweb.co/blog/ui-ux-design-trends-ai-apps-2026)
- [Coding a 3D Audio Visualizer with Three.js, GSAP & Web Audio API — Codrops](https://tympanus.net/codrops/2025/06/18/coding-a-3d-audio-visualizer-with-three-js-gsap-web-audio-api/)
- [Orb — ElevenLabs UI](https://ui.elevenlabs.io/docs/components/orb)
- [piper/VOICES.md — rhasspy](https://github.com/rhasspy/piper/blob/master/VOICES.md)
- [Every Piper Voice, Ranked](https://quick-tts.com/blog/piper-voices-ranked.html)
- [Kokoro vs Piper vs XTTS v2 — Contra Collective](https://contracollective.com/blog/kokoro-vs-piper-vs-xtts-local-text-to-speech-m5-max-2026)
- [Best Local TTS Models 2026](https://localaimaster.com/blog/best-local-tts-models)

---

## 4. Qué añadir después

Ideas viables que salieron de la investigación y que **no** están implementadas.
Ordenadas por relación entre esfuerzo y lo que aportan.

### Alto impacto, esfuerzo contenido

1. **Streaming token a token.** Hoy la respuesta llega entera y luego se
   locuta. Con Server-Sent Events desde `/process_text` el texto aparecería
   mientras se genera, y la voz podría arrancar en la primera frase completa
   en vez de esperar al final. Es la mejora que más reduce la latencia
   *percibida*.
2. **Barge-in.** Poder interrumpir al agente hablando encima. Hoy hay que
   pulsar `Esc`. Requiere mantener el micrófono abierto durante la locución y
   cancelar el TTS al detectar voz, con cancelación de eco para no
   autointerrumpirse.
3. **Palabra de activación offline** (openWakeWord o Porcupine) para no
   depender del atajo de teclado.
4. **Kokoro TTS como motor opcional** junto a Piper, elegible desde el cajón
   de ajustes: más calidad cuando la latencia no apremia.
5. **Historial buscable.** La memoria ya está en SQLite; falta una búsqueda
   sobre las conversaciones desde la paleta de comandos.

### Más ambicioso

6. **Pipeline de voz en tiempo real** (estilo Pipecat, que el proyecto ya tiene
   esbozado en `jarvis_pipecat_pipeline.py`): STT, LLM y TTS encadenados en
   streaming, en lugar de por turnos.
7. **Visor multimedia en el escenario**, tal como describe `DISEÑO.MD`: cuando
   el agente genera una imagen o un vídeo, el orbe se retira a una esquina y el
   contenido ocupa el centro.
8. **Vista del grafo de memoria.** `jarvis_grafo.py` ya construye el grafo;
   falta representarlo y poder navegarlo.
9. **Telemetría histórica**: sparklines de CPU y memoria en las teselas, con
   una ventana de unos minutos, en vez de sólo el valor instantáneo.
10. **PWA con soporte offline real** para la vista móvil, y notificaciones
    push desde el `/notify` que ya existe.

---

## 5. Cómo verificarlo

Con el servidor de JARVIS o de ULTRON en marcha, abrir `/` y comprobar:

- La secuencia de arranque termina y el orbe queda girando en reposo.
- La telemetría se rellena (CPU, RAM, disco, batería) en unos segundos.
- `Ctrl+K` abre la paleta; las flechas y `Enter` la recorren.
- El cajón de ajustes muestra la voz activa, y «Probar voz» suena **masculina**
  en ambos agentes, con ULTRON claramente más grave y lento que JARVIS.
- `Ctrl+J` activa el micrófono: el orbe reacciona al hablar.
- A 414 px de ancho no hay desplazamiento horizontal.

Este rediseño se ha probado renderizando ambas interfaces en Chromium a
1600×950 y a 414×896: WebGL activo, cero errores de consola, telemetría en
vivo, paleta operativa, envío de mensajes correcto y sin desbordamiento
horizontal.
