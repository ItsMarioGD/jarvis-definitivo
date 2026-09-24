# DISEÑO UI/UX - JARVIS ASISTENTE OMNIMODAL

## Interfaz actual: ORIGEN (`web_interface/origen.html`, ruta `/`)

El reactor Arc se jubila y no hay figura. **En silencio, JARVIS es polvo de luz
disperso**: una galaxia fría de tres brazos que gira despacio. **Cuando le hablas,
y mientras piensa o te contesta, las partículas se reúnen y forman una mente de
oro**: un cerebro con dos hemisferios, circunvoluciones, cisura de Silvio, lóbulos
temporales, cerebelo y tronco, que pulsa, chispea (sinapsis) y late con su voz. Al
terminar se queda unos segundos y vuelve a disolverse. La idea es que JARVIS no
se sienta como un asistente que espera órdenes, sino como algo que está ahí.

| Estado | Qué hacen las partículas |
|--------|--------------------------|
| **Reposo** | Dispersas en la galaxia; alguna destella. |
| **Escribiendo** | Mientras tecleas, una tercera parte se agita y empieza a acercarse. |
| **Escucha** | El 85 % se reúne; tiemblan con el nivel del micrófono. |
| **Pensando** | La mente entera, que pulsa más rápido y chispea más; parte de ella orbita en dos anillos cruzados. |
| **Hablando** | La mente late y ondula con el volumen real de la voz (`AnalyserNode`). |
| **Descanso / Enfoque** | Dispersas y más tenues. |
| **Apagado** | Se disuelven y casi se apagan. «Silencio. Sigo pensando, aunque no me veas.» |

Cada partícula tiene su umbral, así que no llegan todas a la vez: el cerebro se va
formando. Reunirse tarda un segundo; disolverse, unos tres y tras una pausa.

**Arranque:** sin cinemática. Las partículas aparecen, JARVIS saluda (la mente se
forma mientras lo dice) y a trabajar. Si el navegador bloquea el audio hasta el
primer gesto, el saludo se repite en cuanto se toca algo. En la cabecera,
«despierto hace N min».

**Móvil:** la misma interfaz (`/mobile` sirve ORIGEN). El QR del PC trae el PIN;
sin él, ORIGEN pide el PIN. Todas las peticiones llevan el PIN en la cabecera, así
que un cambio de IP del teléfono no lo deja fuera. El PIN y el QR solo se ven
desde el PC.

**Módulos:** el botón de nodos abre un panel lateral con los módulos
(`/modulos.js`), con un índice de tarjetas y lo más nuevo delante: Ciencias, Modelado 3D, Cerebro, Correo, Demos web, Llamadas y Consejo,
y después Agenda, Sistema, Cámara, Pantalla, Archivos, etc.

**Motor (WebGL2 a mano, sin librerías ni imágenes):**
- Hasta **1.048.576 partículas** en texturas RGBA32F. Su física corre en la GPU con
  render-to-texture ping-pong y MRT (posición + velocidad): cada partícula tiene su
  sitio en la galaxia y su hueco en un cerebro paramétrico, y viaja entre los dos con
  muelles, flujo ABC sin divergencia y un cursor que las aparta. El cerebro se
  sombrea según hacia dónde mira cada partícula, para que se lea sólido.
- Acumulación HDR de 16 bits con estela (más larga mientras viajan), haz de luz,
  resplandor de la mente sobre la niebla, bloom *dual-filter* de 6 niveles, ACES, viñeta, aberración cromática y grano.
- **Regulador de calidad**: mide la GPU (`EXT_disjoint_timer_query_webgl2` si existe) y
  sube o baja entre 65 k y 1 M partículas; `?calidad=0..4` lo fija a mano.
- **Respaldo**: sin texturas float escribibles, la misma coreografía se calcula en
  forma cerrada en el vertex shader (`?motor=analitico` lo fuerza). Sin WebGL2 queda
  un pulso en CSS y todo lo demás funciona.

**Funciones:** chat (`/process_text`), voz (`/api/speak`, con respaldo en
`speechSynthesis`), micrófono (Web Speech o grabación a `/voice`), voz continua
(«Jarvis…» y ventana de 8 s tras cada respuesta), modos (`/set_mode`), historial,
emparejar el móvil, telemetría real (`/stats`) y del motor, y apagado ritual
(`/farewell`). Atajos: `/` escribir, `M` hablar, `Esc` callar/cerrar.

---

## Diseño anterior (HUD Arc Reactor, ya eliminado)

## Diseño de Interfaz Híbrida Voz/Chat

### Principios de Diseño

1. **Carisma Computacional Prioritario**: La interfaz debe reflejar la baja latencia y la fluidez conversacional del agente. Cada elemento visual debe reforzar la sensación de inteligencia en tiempo real.

2. **Voz como Modal Principal, Chat como Soporte**: La voz es el modo interactivo principal, pero el chat está disponible como alternativa sin interrumpir la experiencia vocal.

3. **Transparencia Operativa**: El usuario debe ser consciente cuándo Jarvis está procesando información, esperando o ejecutando acciones remotas.

### Componentes Visuales Principales

#### 1. Esfera de Visualización de Estado (Arc Reactor HUD Central)

**Estados y Animaciones (Renderizadas en Canvas):**

| Estado | Animación | Descripción |
|--------|-----------|-------------|
| **Escucha Activa** | Rotación acelerada naranja | Anillos cambian a color warning (#FFB800) y giran un 50% más rápido. |
| **Procesamiento/Cognición** | Rotación violeta profundo | Anillos cambian a morado (#FF00FF) y la velocidad se duplica. |
| **Respuesta Vocal** | Brillo verde | Anillos en verde (#00FF00) con pulsos síncronos simulando salida de audio. |
| **Modo Reposo/Idle** | Rotación azul neón regular | Azul Neón (#00F0FF) girando de forma constante. |
| **Pensando Profundamente** | Secuencia de pulsos en el núcleo central | El núcleo central palpita con variación radial continua. |

**Especificaciones Técnicas:**
- Radio: 80% del ancho de la pantalla
- FPS mínimo: 60
- Paleta: Blanco cálido para estados activos, gris neutro para reposo
- Color ámbar #B8860B para modo remoto/notificaciones

#### 2. Paneles de Datos HUD Laterales

**Estructura de Paneles:**

```
┌─────────────────────────────────────────────────────────────┐
│  PANEL IZQUIERDO: Métricas                 PANEL DERECHO:  │
│  - [CPU] 32%                               >_ SYSTEM LOGS  │
│  - [RAM] 4.2 GB                            [Historial de   │
│  - [NETWORK] ENCRYPTED                      acciones del   │
│  - [MCP] ONLINE                             núcleo]        │
└─────────────────────────────────────────────────────────────┘
```

#### 3. Módulo de Renderizado Multimedia

**Comportamiento al invocar contenido:**

1. **Simulaciones (Kling 3.0 / Video):**
   - El visor se expande fluidamente al centro (animación 300ms)
   - La esfera de estado se desplaza suavemente a una esquina (corner preferred: top-right)
   - Controles de reproducción minimalistas (play/pause, duración)
   - Al finalizar, el contenido se contrae y la esfera regresa a posición original

2. **Generación de Imágenes (Flux Pro / Flux Dev):**
   - Cuadro de imagen centrado se materializa desde el área de conversación
   - Texto descriptivo se desvanece mientras la imagen toma protagonismo
   - Botón "Guardar en Google Drive" o "Más información" aparece al hover

3. **Gráficos y Diagramas Educativos:**
   - Visualización interactiva que el usuario puede "explorar" con gestos
   - El agente narra puntos clave mientras el usuario explora visualmente

#### 4. HUD Perimetral de Transparencia Remota

**Ubicación:** Borde completo de la pantalla, normalmente oculto.

**Cuándo Activarse:**
- Cuando el agente está accediendo al árbol de accesibilidad de Android
- Cuando ejecuta acciones MCP (calendar, home assistant, etc.)
- Cuando la memoria de grafos está siendo consultada para decisiones proactivas

**Señales Visuales:**
- Borde ámbar #B8860B de 3px que parpadea en patrón rítmico
- Íconos miniatura en esquemas que indican tipo de acción:
  - 📅 = Calendar/MCP operation
  - 🏠 = Home Assistant/IoT control
  - 📱 = Android accessibility action
  - 🧠 = Memory graph retrieval
- Texto súper-minúsculo (tooltip) que aparece al mantener finger/hover: "Jarvis operando dispositivo remoto"

**Comportamiento de Auto-ocultamiento:**
- Desaparece 2 segundos después de que el agente termina la acción remota
- Reaparece inmediatamente si se detecta nueva acción en progreso
- Pueden desactivarse en configuración de privacidad

### Flujo de Interacción Usuario-Jarvis

```
┌──────────────────────────────────────────────────────────────┐
│  USUARIO dice: "Configura una alarma para las 6 AM"         │
│                                                              │
│  [Esfera se expande = ESCUCHA ACTIVA]                       │
│                                                              │
│  [Anillos giran = PROCESAMIENTO - consultando Calendar MCP] │
│                                                              │
│  [HUD perimetral ámbar ENCIENDE = OPERACIÓN REMOTE]         │
│  [Ícono 📅 parpadea en borde]                                │
│                                                              │
│  [Audio Jarvis]: "Consideralo hecho, procedo a operarlo"     │
│  [Acción]: Toque en app Reloj, configuración de alarma       │
│                                                              │
│  [HUD parpadea = FINALIZADO]                               │
│  [Esfera vuelve a estado reposo]                            │
│  [Audio Jarvis]: "Alarma configurada para las 6 AM. Buen    │
│    descanso!"                                                │
│                                                              │
│  [Usuario puede responder o iniciar nuevo input]            │
└──────────────────────────────────────────────────────────────┘
```

### Paleta de Colores HUD

| Uso | Color | HEX |
|-----|-------|-----|
| **Fondo Principal** | Deep Navy Black | #030811 |
| **Acento Primario** | Neon Cyan | #00F0FF |
| **Bordes/Sub Acento**| Neon Dark Blue | #005F88 |
| **Texto Primario** | Ice White | #E0FFFF |
| **Texto Secundario**| Cyan Grisáceo | #00A8CC |
| **Modo Escucha** | Warning Orange | #FFB800 |
| **Procesamiento** | Deep Purple | #FF00FF |
| **Habla/Éxito** | Neon Green | #00FF00 |
| **Error/Alerta** | Neon Pink/Red | #FF3366 |

### Tipografía

| Elemento | Fuente | Tamaño | Peso |
|----------|--------|--------|------|
| **Título Principal** | System Font (San Francisco / Roboto) | 24-32px | Semibold 600 |
| **Texto de Conversación** | System Font | 16-18px | Regular 400 |
| **Etiquetas/Metadatos** | System Font | 12-14px | Medium 500 |
| **Notificaciones HUD** | System Font | 10-12px | Regular 400 |
| **Counters/Indicators** | System Font | 11-13px | Medium 500 |

### Interacciones Especiales

#### 1. "Barge-In" Visual
- Cuando el usuario habla mientras Jarvis está hablando:
  - La esfera cambia a rojo pulsante rápido
  - La barra de progreso de TTS se congele visualmente
  - El usuario puede tocar para interrumpir y tomar el control
  - Después de la interrupción, la esfera retorna al estado anterior con animación de "shh"

#### 2. Modo "Ojos Cerrados" (Descanso)
- Cuando el usuario dice "descanso" o el sistema detecta inactividad prolongada:
  - La esfera secontra contra sí misma suavemente
  - El HUD perimetral se vuelve completamente transparente/oculto
  - Audio: "Entendido. Estaré atento a cualquier necesidad."
  - Después de 5 minutos sin actividad, la aplicación entra en modo de bajo consumo

#### 3. Modo "Enfoque Profundo"
- Cuando el usuario activa modo concentración:
  - La esfera y HUD se minimizan a un botón flotante pequeño
  - Solo responde a "Jarvis" wake word o entrada explícita
  - Bloquea notificaciones no prioritarias

### Responsividad Móvil

| Dispositivo | Adaptaciones |
|-------------|--------------|
| **Phone (320px-480px ancho)** | Esfera reduce a 60% width, HUD perimetral se comprime a indicadores táctiles |
| **Tablet (481px-768px ancho)** | Esfera 70% width, HUD mantiene funcionalidad completa |
| **Tablet Horizontal (769px-820px)** | Esfera full width, layout de doble panel (chat a la izquierda, esfera/derecha) |
| **Smallest screens** | Modo "esfera única" prioritario, voz como interfaz exclusiva temporal |

### Accesibilidad

- **Contraste mínimo:** 4.5:1 para todos los textos
- **Tamaños táctiles:** Mínimo 48dp para todos los elementos interactivos
- **Compatibilidad lectores de pantalla:** Todas las animaciones descritas vía ARIA labels
- **Modo alto contraste:** Alternativa en configuración que invierte la paleta pero mantiene funcionalidad de la esfera
- **Reducir movimiento:** Opción para reemplazar animaciones por estados estáticos con indicadores de texto

### Estado Actual del Diseño

| Componente | Avance | Comentarios |
|------------|--------|-------------|
| **Esfera Arc Reactor HUD** | ✅ 100% | Reemplazó al diseño anterior, usando `CTkCanvas` para dibujar anillos rotatorios. |
| **Paneles Laterales Datos** | ✅ 100% | Layout implementado, mostrando placeholders y logs. |
| **Logs del Sistema** | ✅ 100% | Implementado en el panel derecho para output de consola. |
| **Módulo Multimedia** | 🟡 70% | Comportamientos definidos, pending integración API Kling/Flux |
| **Flujo de Interacción** | ✅ 100% | Lógica asíncrona real conectada en `jarvis_core.py`. |
| **Paleta de Colores Neón** | ✅ 100% | Actualizada. |
| **Tipografía Tech** | ✅ 100% | Courier New / Consolas aplicadas. |
| **Accesibilidad** | 🟡 80% | Alto contraste neón listo, pendiente opciones de "reducir movimiento". |

**Próxima acción de diseño:** Conectar los placeholders del panel izquierdo a librerías reales de recolección de datos del sistema (como `psutil`) para mostrar CPU y RAM reales del ordenador anfitrión.