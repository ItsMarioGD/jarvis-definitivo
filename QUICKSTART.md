# JARVIS — Guía rápida

## Uso diario

Arranca todo (JARVIS, ULTRON y los servidores MCP) con un solo comando:

```bash
python reiniciar_todo.py
```

**ÆON: la interfaz de gala.** Con la web arrancada,
`http://TU-IP:5000/aeon?token=<PIN>`. Es la que se abre sola al arrancar, y las
tres personalidades no comparten solo el color: cada una trae su propia
retícula (las columnas se recolocan de verdad), su tipografía, su forma de
panel y su física de partículas.

* **JARVIS** — sala simétrica, cristal y aire, tipografía fina y ancha. El
  núcleo es una esfera de casco despiezado con tres anillos giroscópicos.
* **ULTRON** — la sala se da la vuelta: la conversación pasa a la izquierda,
  todo se vuelve monoespaciado en mayúsculas, las esquinas se cortan a bisel y
  el núcleo es un octaedro al que unas cajas giratorias le arrancan trozos, con
  las grietas al rojo vivo.
* **CONSEJO** — retícula simétrica con las dos columnas enfrentadas y la
  deliberación abajo a lo ancho; titulares en serif. El núcleo se desdobla en
  dos tetraedros que orbitan, uno de cada color, con una costura blanca en medio.

El núcleo es un *raymarch* de campos de distancia en WebGL2 escrito a mano: no
hay librería, ni CDN, ni un solo archivo de imagen; los tres cuerpos son tres
SDF que se mezclan, y por eso la esfera **se rompe** en el octaedro en lugar de
cambiar de dibujo. Lleva oclusión ambiental, sombra propia suave y un rebote de
reflejo, y encima un **revelado de cine en cuatro pasadas**: las luces altas se
separan, se difuminan en dos direcciones, se estiran en un destello anamórfico
y se componen con curva ACES, aberración cromática, grano y viñeta. Cada
personalidad se expone distinto —JARVIS es luz limpia, ULTRON una masa oscura
con la lumbre dentro—, y al cambiar de una a otra la cámara entra, el cuerpo se
desgarra y las barras de formato panorámico enmarcan el plano. Si la tarjeta no da WebGL2, el mismo núcleo se dibuja con
trazos en 2D y no se pierde nada más. La calidad se ajusta sola mirando los
cuadros por segundo (y si aun así no llega, apaga sombra y reflejo antes que
perder fluidez) y respeta «reducir movimiento» del sistema.

**Suena.** No son pitidos: hay una sala de verdad (reverberación por
convolución con un impulso generado a mano) y un ambiente propio por
personalidad que se cruza al mutar —un acorde cristalino en JARVIS, un zumbido
grave y sucio en ULTRON, dos voces en quinta en el CONSEJO—. La mutación entra
con un *riser* de ruido que sube, golpe de sub-graves y soplo; escribir, enviar,
recibir, abrir un módulo o el panel tienen su propio sonido. Todo sintetizado
al vuelo, sin un solo archivo de audio, y todo cuelga de un compresor para que
nada reviente el altavoz. Se apaga con el botón del altavoz de la cabecera y la
elección se recuerda. `Tab` cambia de personalidad, `Ctrl+K` abre la paleta de órdenes
(módulos, personalidades y frases) y el engranaje despliega el panel.

**NEXUS: la interfaz anterior, intacta.** Con la web arrancada,
`http://TU-IP:5000/nexus?token=<PIN>`. Un único lienzo donde JARVIS, ULTRON y el
CONSEJO conviven: al cambiar de personalidad el núcleo se transforma en directo
(el círculo de JARVIS se rompe en el hexágono de ULTRON, o en el triángulo doble
del consejo) mientras el color de toda la interfaz se interpola. `Tab` alterna
personalidad; el engranaje despliega el panel de control sin salir de la página.

En modo CONSEJO, una pregunta con consecuencias hace que las dos voces
argumenten en lados opuestos y se muestre la síntesis debajo, marcando si el
desacuerdo es real.

Alrededor del núcleo hay HUD de verdad, no adorno: a la izquierda, telemetría
viva con gráficas de tendencia (procesador, memoria, red, disco, batería,
temperatura, tiempo encendido), y a la derecha el estado de los subsistemas, la
actividad de las últimas 24 horas y el hilo de sucesos —ahí aparecen solos los
hallazgos del enjambre, las caídas que detecta el vigilante y las alertas—. Todo
se repinta con el color de la personalidad activa.

El raíl de la izquierda trae **todo lo que hacían las dos interfaces antiguas**,
cada cosa en su módulo:

| Módulo | Qué trae |
|---|---|
| Sistema | CPU, memoria, disco, batería, red, procesos (y matarlos), liberar RAM, radar, bloqueo total |
| Cámara | Emisión en vivo de la cámara del equipo |
| Pantalla y control | Escritorio en vivo + ratón (arrastrar, clic, rueda) y teclado remotos |
| Archivos | Subir al equipo y descargar lo que JARVIS ha generado |
| Generar | Imágenes, Word, Excel, PowerPoint, PDF, diagramas y código |
| Agenda | Lo de hoy, crear eventos y borrarlos (Google Calendar) |
| Guardián | Modo de ULTRON, guardián facial, radar de red, bloquear IPs, restaurar red |
| Voz | Hacer que hable, callarlo, voz de Windows, saludo, despedida, probar el cerebro |
| Especialistas | Catálogo de agentes, activar personalidad, delegar en el otro agente |
| Datos y web | Bolsa, noticias, extraer una web, descargar de YouTube |
| Historial | Las conversaciones de los dos, y purgar la memoria de ULTRON |
| Emparejar | QR, PIN, aparatos emparejados y cambio de PIN al instante |

Lo que ULTRON expone pasa por una pasarela (`/api/nexus/u/…`) desde el mismo
origen, así que no hay CORS ni un segundo PIN que teclear.

**Los dos a la vez.** Un solo comando levanta JARVIS y ULTRON y abre sus dos
interfaces ya autenticadas (sin teclear ningún PIN):

```bash
python jarvis.py ambos
```

En Windows también vale doble clic en `arrancar_ambos.bat`. Si alguno ya estaba
corriendo lo reutiliza en vez de tirarlo; con `--reiniciar` cierra lo anterior y
arranca limpio, y con `--sin-navegador` no abre pestañas. Ctrl+C para los dos.

**Panel de control.** Con la web arrancada, abre `http://TU-IP:5000/panel?token=<PIN>`
y tienes en una pantalla: qué se puede deshacer, qué órdenes fallaron, el estado
del vigilante y del enjambre, el perfil activo, la memoria indexada, la
seguridad, las habilidades pendientes de aprobar y el rendimiento. Con botones,
sin tener que recordar ninguna frase.

¿Solo quieres una parte? Todo pasa por un único lanzador (`jarvis.bat` hace lo
mismo desde el explorador de Windows):

| Comando | Qué abre |
|---|---|
| `python jarvis.py ambos` | **JARVIS y ULTRON a la vez, abriendo sus dos webs** |
| `python jarvis.py` | HUD de escritorio de JARVIS |
| `python jarvis.py ultron` | Núcleo/HUD de ULTRON |
| `python jarvis.py web` | Interfaz web (y móvil) de JARVIS |
| `python jarvis.py ultron-web` | Interfaz web de ULTRON |
| `python jarvis.py movil` | QR de emparejamiento del teléfono |
| `python jarvis.py estado` | Diagnóstico: qué está listo y qué falta |
| `python jarvis.py test` | Pruebas de regresión |

Los `.bat` antiguos siguen donde estaban por si algún acceso directo apunta a
ellos, pero solo hace falta recordar este.

Al terminar te dice la dirección para emparejar el teléfono. Ya puedes darle
órdenes: por el HUD del PC, por el navegador o desde el móvil.

¿Algo no responde? Este comando revisa todo y dice qué falta y cómo arreglarlo:

```bash
python revisar.py
```

---

## El cerebro

JARVIS puede pensar con tres cerebros, y los usa en el orden que usted mande:

| Cerebro | Velocidad | Coste | Sin internet |
|---|---|---|---|
| **Pollinations** (nube abierta) | ~2 s | gratis | no |
| **Qwen en casa** (Ollama) | ~30 s | gratis | **sí** |
| **Claude** (Anthropic) | rápido | de pago | no |

### Pollinations: poner la clave

Habla el mismo idioma que OpenAI, así que JARVIS le entiende sin traductor.

**Sin clave** funciona, pero con **un** solo modelo y una petición cada 15
segundos — y el bucle de herramientas encadena hasta cuatro, así que se hace
eterno. **Con clave** son **241 modelos** (139 saben usar herramientas, 95 ven
imágenes), contextos de hasta 1,3 millones de tokens y sin espera impuesta.

> **Ojo con el endpoint.** Las claves `sk_` son del portal nuevo
> (`gen.pollinations.ai`). El antiguo (`text.pollinations.ai`) las **ignora en
> silencio**: sigue contestando «anonymous» y enseñando un solo modelo, como si
> no hubiera clave. JARVIS elige el correcto solo según la tenga o no.

1. Consiga la clave en <https://enter.pollinations.ai> (empieza por `sk_`)
2. Ábrala el archivo `.env` de esta carpeta y pegue la clave en la línea que ya
   está esperándola:

   ```
   POLLINATIONS_API_KEY=
   ```
3. Reinicie JARVIS y compruebe con:

   ```bash
   python proveedor_pollinations.py
   ```

La clave solo se lee del `.env`. No se copia a `Prefs/cerebro.json` (ahí va por
referencia, `${POLLINATIONS_API_KEY}`) ni se manda a nadie que no sea
Pollinations.

### Quién manda

Con `JARVIS_CEREBRO` en el `.env`: `pollinations`, `local` o `claude`.
**Si lo deja vacío, JARVIS elige solo**: Pollinations cuando hay clave, y el de
casa cuando no. El de casa **nunca** se cae de la lista, así que si se va
internet o se acaba el saldo sigue habiendo asistente — que es exactamente lo
que falló con Anthropic.

De viva voz: «¿qué cerebro estás usando?», «cámbiate a pollinations», «usa el
cerebro de casa», «prueba pollinations», «¿dónde pongo la clave?».

### Buscar en tus apuntes por SIGNIFICADO

Con la clave de Pollinations puesta, JARVIS busca en tus documentos por lo que
**quieren decir**, no solo por las palabras que traen. Si el apunte dice «tasa
de variación instantánea» y preguntas «qué es una derivada», lo encuentra:

```
«busca en mis apuntes qué es una derivada»
```

La búsqueda es híbrida: FTS5 para lo literal (un nombre, un número de
expediente) y vectores para lo que recuerdas con otras palabras.

* «indexa mis documentos» — lee y vectoriza las carpetas habituales
* «vectoriza» — completa lo que se indexó **antes** de activar el motor
* Sin clave funciona igual, pero solo por palabras. También vale un motor
  local: `ollama pull nomic-embed-text`

### Qwen en casa

Servido por Ollama. No pasa factura, no se queda sin saldo, funciona sin
internet y las conversaciones no salen de casa.

| Modelo | Para qué | Tamaño |
|---|---|---|
| `qwen3:8b` | el de trabajo: razona y conversa | ~5 GB |
| `qwen3:4b-instruct` | el rápido, para lo corto | ~2,5 GB |
| `qwen2.5vl:3b` | el que **ve**: pantalla, fotos y escáner 3D | ~3 GB |

Instalación: descargue Ollama de <https://ollama.com/download> y luego

```bash
ollama pull qwen3:8b
```

```bash
ollama pull qwen2.5vl:3b
```

`arrancar_ambos.py` levanta Ollama solo si estaba apagado, comprueba que el
modelo conteste y lo precarga para que la primera frase no tarde.

Qwen3 razona antes de contestar, y eso trae dos cosas: acierta las cuentas y
las decisiones, pero tarda más si piensa en todo. Por eso el núcleo **decide
por pregunta**: lo cotidiano se responde directo (1-2 s) y lo que huele a
cálculo, comparación, diagnóstico o código se piensa (10-20 s). Se manda con
`JARVIS_RAZONAR` en `.env`: `auto` (por defecto), `siempre` o `nunca`. El
pensamiento del modelo (`<think>…</think>`) nunca se lee en voz alta: se filtra
antes de hablar.

Si el modelo principal falla, el núcleo baja solo: `qwen3:8b` →
`qwen3:4b-instruct` → Claude (si hay clave con saldo).

| Variable | Para qué |
|---|---|
| `JARVIS_CEREBRO` | `local` (por defecto) o `claude` para forzar la nube |
| `QWEN_MODEL` | Qué modelo local usa (`qwen3:8b`; `qwen3:4b-instruct` si va justo de VRAM) |
| `QWEN_VISION_MODEL` | El que mira imágenes (`qwen2.5vl:3b`) |
| `QWEN_BASE_URL` | Dónde escucha Ollama (`http://localhost:11434/v1`) |
| `JARVIS_MODELO` | Modelo activo; manda sobre lo anterior |
| `OLLAMA_CONTEXT_LENGTH` | Ventana de contexto al levantar Ollama (16384). Con los 4096 de fábrica no caben las fotos del escáner |
| `ANTHROPIC_API_KEY` | Solo para la reserva en la nube. Sin ella no pasa nada |
| `JARVIS_PRESUPUESTO_USD` | Tope de gasto al día de la nube (1.0). Lo local no cuenta: es gratis |

Para ir más ligero basta con cambiar `QWEN_MODEL` a `qwen3:4b-instruct` y
reiniciar. Para volver a la nube, `JARVIS_CEREBRO=claude`.

## Instalación desde cero

```bash
instalar.bat
```

Deja el equipo listo: Python, dependencias, el SDK de Anthropic, los accesos
directos y (si quieres) el arranque automático. La clave de la API la pones
tú en el `.env`.

Si prefieres hacerlo a mano:

```bash
python instalar_dependencias.py
```

Instala lo necesario y al final dice, en castellano, qué ha quedado fuera y
qué función se pierde con ello. Para los extras opcionales (voz por el móvil,
memoria semántica):

```bash
python instalar_dependencias.py --extras
```

> **Sobre `requirements.txt`:** contiene solo lo que se instala limpio y hace
> falta de verdad. Lo pesado y opcional está en `requirements-extra.txt`, y es
> a propósito: `pip` resuelve un requirements entero antes de instalar nada,
> así que una sola línea rota deja el sistema **sin ninguna** dependencia.

---

## Conectar el teléfono

1. En el PC, abre la dirección que imprime `reiniciar_todo.py`:
   `http://TU-IP:5000/pair`
2. Escanea el QR con la cámara del móvil. Entra solo, sin teclear nada.
   (Si prefieres, en esa página también sale un PIN de 6 dígitos.)
3. El teléfono tiene que estar en la **misma Wi-Fi** que el PC.

Desde el móvil puedes escribir, hablar, ver el escritorio en vivo, usar el
teléfono como touchpad y teclado, y mandar cualquier orden al PC.

La página de emparejamiento se cuida sola:

- **El QR nunca caduca en pantalla**: se rehace solo si el router te da una IP
  nueva, que es lo que dejaba al teléfono cargando contra una dirección muerta.
- **El PIN va dentro del QR**: escaneas y entras. No hay que teclearlo ni pulsar.
- **El teléfono se da de alta solo** la primera vez, y la página lo confirma con
  un «Teléfono emparejado ✓».
- **El PIN se renueva cada 30 días sin que te enteres**: un teléfono ya
  emparejado recoge el nuevo del PC en vez de mandarte a escanear otra vez.

### Si el teléfono no conecta

La propia página `/pair` lo diagnostica: te dice qué está fallando, con el
botón para arreglarlo cuando se puede, y ofrece los QR de las otras direcciones
del equipo (Wi-Fi, Ethernet, Tailscale) por si la principal no es la buena.

También puedes preguntárselo de viva voz: «¿por qué no conecta mi móvil?».

Causas por orden de frecuencia:

1. **El PC cambió de IP.** Ya no pasa: la página lo detecta y rehace el QR.
   Si tenías el QR abierto de ayer, refresca y listo.
2. **El firewall de Windows.** Si hace falta, la página saca el botón «abrir el
   puerto» y Windows te pide permiso una vez. A mano:
   `herramientas\abrir_firewall.ps1` → **Ejecutar como administrador**.
3. **La Wi-Fi está marcada como pública.** Configuración › Red › Wi-Fi › perfil
   **Red privada**.
4. **Un repetidor con aislamiento de clientes.** Muchos extensores no dejan que
   dos aparatos se vean entre sí aunque estén en la misma red. Conecta el
   teléfono al router principal, o usa Tailscale.

### Fuera de casa: el PC como servidor

El PC hace de servidor y tú te conectas desde donde estés — el teléfono con
datos móviles, el portátil en otro sitio — sin abrir un solo puerto del router.

1. Instala [Tailscale](https://tailscale.com/) en el PC y en cada aparato
   desde el que quieras entrar, todos con la **misma cuenta**. Es gratis para
   uso personal.
2. En el PC, dile a JARVIS: **«actívate en remoto»** (o el botón *Activar
   acceso remoto* del módulo Emparejar).
3. Desde cualquier sitio, abre la dirección que te da:
   `https://TU-EQUIPO.tu-tailnet.ts.net/mobile`

Esa dirección es la que sale en el QR mientras el acceso remoto esté activo,
así que **el mismo QR sirve en casa y fuera**.

Por qué HTTPS y no la IP de Tailscale a pelo: con `http://100.x.x.x:5000` el
navegador del teléfono considera la página insegura y **apaga el micrófono**,
así que el dictado por voz deja de funcionar sin decir por qué. Con
`tailscale serve` la dirección tiene certificado de verdad y funciona todo:
voz, cámara, pantalla en vivo y notificaciones.

Órdenes relacionadas:

- «¿puedo entrar desde fuera?» — estado, nombre del equipo y qué aparatos tuyos
  están conectados a la red privada
- «quita el acceso remoto» — deja de publicarlo
- «publícalo en internet» — Funnel: la URL queda abierta al mundo. Avisa y
  **exige confirmación expresa**; con un PIN de seis cifras no es buena idea

### Que el servidor esté siempre encendido

Para que el PC responda aunque no hayas abierto nada a mano:

```bash
python servicio.py instalar
```

Deja JARVIS arrancando con Windows y reponiéndose si se cae. «Instálate como
servicio» hace lo mismo de viva voz. `tailscale serve` ya es persistente: una
vez activado el acceso remoto, sigue puesto tras reiniciar.

### Seguridad al estar accesible desde fuera

- El PIN sigue siendo de 6 cifras, pero ahora hay **freno de fuerza bruta**:
  6 intentos fallidos desde una misma IP y esa IP queda castigada 15 minutos
  (ajustables con `JARVIS_PIN_INTENTOS` y `JARVIS_PIN_CASTIGO`). El propio PC
  nunca se castiga a sí mismo.
- Con Tailscale, para llegar siquiera a la pantalla del PIN hay que estar
  dentro de tu red privada: nadie de Internet ve el servidor.
- Si alguna vez usas Funnel, cambia el PIN por uno largo y quítalo en cuanto
  no lo necesites.

---

## Conectar Google Calendar

```bash
python autorizar_google.py
```

Te guía paso a paso. Hay que crear una credencial en la consola de Google una
sola vez (Google no permite hacerlo automáticamente); el script te dice
exactamente qué botón pulsar en cada pantalla.

Cuando termine, JARVIS entiende «¿qué tengo mañana?», «apúntame una reunión el
martes a las 5» o «bórrame la cita del jueves».

Opciones útiles:

| Comando | Para qué |
|---|---|
| `python autorizar_google.py --buscar` | Ver dónde busca las credenciales y cuáles encuentra |
| `python autorizar_google.py --revocar` | Desconectar la cuenta |
| `python autorizar_google.py --puerto 8080` | Usar otro puerto si ya tienes un redirect registrado |

---

## Qué le puedes pedir

Funciona igual desde el PC o desde el móvil:

- **«Jarvis, papá llegó»** — el interruptor general. Saluda según la hora y
  **enciende todo lo que estuviera apagado**: la escucha continua, el motor
  proactivo, los ojos en la pantalla, el vigilante y las luces. Lo que ya
  estaba en marcha se informa y no se reinicia; lo que no se puede encender se
  dice y por qué, en vez de fingir que todo fue bien. Valen también «ya
  llegué», «ya estoy en casa», «he llegado» y «estoy de vuelta».
- **La universidad** — «mira el campus», «qué tengo que entregar», «hazme
  tarjetas de derivadas», «pregúntame», «descompón 100 newtons a 30 grados»,
  «hazme el informe de la práctica 3». Ver [CARRERA.md](CARRERA.md).
- **Simulaciones en 3D** — «simula el péndulo doble», «anima la órbita de la
  Tierra y la Luna», «quiero ver el efecto mariposa», «simula x'' = -9.8».
  Ver [CIENCIAS.md](CIENCIAS.md).
- **Abrir y cerrar programas** — «abre el bloc de notas», «cierra Chrome»
- **Sonido** — «sube el volumen», «silencia»
- **Estado del equipo** — «cuánta RAM estoy usando», «cuánta batería queda»
- **Apagar / bloquear** — «bloquea el pc en 30 minutos», «apaga el equipo dentro de 2 horas», «cancela el apagado»
- **Capturas** — «haz una captura de pantalla» (se guardan en `Descargas/JARVIS/Capturas/`)
- **Portapapeles** — «copia 1234 al portapapeles»
- **Buscar** — «busca recetas de paella», «busca X en YouTube del canal Y»
- **Generar** — imágenes, documentos, Excel, PowerPoint, PDFs, diagramas, código
- **Calendario** — una vez conectado Google
- **Varias cosas a la vez** — «sube el volumen y dime cuánta RAM estoy usando»

### Órdenes sobre el propio JARVIS

Ahora puede preguntarle por lo que ha hecho, y comprobarlo:

- «¿qué has ejecutado hoy?» — las últimas órdenes con su resultado real
- «¿qué te ha fallado?» — solo las que Windows rechazó, con el motivo
- «¿qué ha pasado?» — eventos: intrusos, avisos, alertas del sistema
- «¿qué avisos tienes?» — lo que ha detectado el motor proactivo
- «silencia los avisos» / «activa los avisos»
- «activa la escucha continua» / «desactiva la escucha»
- «dicta en local» / «dicta en la nube» — dónde se transcribe su voz
- «entrena tu clasificador» — aprende de sus propias órdenes
- «haz limpieza de memoria» — poda lo que lleva meses sin usarse
- «¿cuánta memoria tienes?» — tamaño del grafo y actividad reciente
- «¿cómo me notas?» — qué ha leído en su voz (tensión, fatiga)

### Escucha continua (manos libres)

Con `python jarvis.py estado` verá si tiene PyAudio instalado. Si lo tiene:

```
«activa la escucha continua»
```

A partir de ahí basta con llamarle por su nombre: «Jarvis, apaga el pc». Tras
responder queda una ventana de 15 segundos en la que ya no hace falta repetir
el nombre. Y puede **interrumpirle hablando**: en cuanto usted dice algo, la
voz se corta.

ULTRON responde a «Ultron» además de a «Jarvis».

### Autonomía y control

- «deshaz eso» — revierte la última acción (mover archivos, cerrar apps, apagados)
- «¿qué puedes deshacer?» — lo que sigue siendo reversible
- «¿cómo estás de salud?» — parte del vigilante interno
- «turno de noche a las 03:30» — rutina nocturna autónoma; «¿qué hiciste anoche?»
- «activa el enjambre» — especialistas vigilando en segundo plano con presupuesto
- «¿qué dicen los especialistas?» — lo que vieron sin llegar a interrumpirle
- «ensaya `<orden>`» — qué pasaría, sin que pase
- «pilota y `<objetivo>`» — usar ratón y teclado como un humano (pide confirmación)
- «consulta al consejo sobre `<decisión>`» — JARVIS y ULTRON debaten y sintetizan
- «¿qué suelo hacer?» — sus hábitos, aprendidos del registro

### Ojos, oídos y memoria

- «mira mi pantalla» / «¿qué error me da esto?» — lo ve Claude (con el modo privado, solo OCR local)
- «busca en mis documentos lo de `<tema>`» — busca **dentro** del contenido
- «indexa mis documentos» — construye el índice (funciona ya, sin descargar nada)
- «empieza a grabar mi pantalla» — memoria episódica; «¿qué estaba haciendo `<X>`?»
- «borra la última hora» — el botón de arrepentimiento de la grabación
- «¿reconoces mi voz?» / «solo obedéceme a mí» — identidad por voz

### Escanear objetos y holograma vivo

- «escanea este objeto» — con la webcam del PC: sale una ventana, ponga el
  objeto dentro del marco y gírelo despacio mientras dispara solo
- «escanéalo con el móvil» — enseña un QR; el teléfono abre el escáner y usted
  da la vuelta al objeto
- El resultado es un modelo 3D **con las piezas separadas** y el holograma se
  abre solo. Con el holograma delante: «desármalo», «aísla la tapa»,
  «córtalo por la mitad», «ponle rayos X», «mídelo», «modo pirámide»
- «mide 12 cm de alto» — a partir de ahí las medidas salen en centímetros
- «hazme un prototipo plegable de esto» — diseña un modelo NUEVO a partir del
  escaneado y lo pone al lado para comparar
- «exporta esto» / «ábrelo en Blender» — `.glb`, `.obj`, `.stl` y `.blend`
- Todo en `~/Descargas/JARVIS/Escaneos/`. Detalles en `ESCANER3D.md`

### Ojos permanentes (sin pedirlo)

- «vigila mi pantalla» — mira la ventana activa cada minuto y, si lleva cuatro
  minutos atascado en el mismo error, se ofrece. Una captura solo cuando hay
  atasco; en modo juego, invitado o privado ni mira
- «¿qué ves ahora?» — una mirada puntual, sin dejar la vigilancia puesta
- «¿estás vigilando?» / «deja de vigilar mi pantalla»

### Voz propia (local, sin factura)

- «instala tu voz» — descarga una voz neuronal de Piper (unos 60 MB, se queda
  en el equipo). Necesita `pip install piper-tts`
- «usa la voz `<nombre>`» / «usa la voz de ULTRON `<nombre>`» — JARVIS habla con
  `es_ES-davefx-medium` y ULTRON con `es_MX-ald-medium`: no suenan igual
- «¿qué voces tienes?» — catálogo, cuáles están puestas y quién usa cada una
- «clona mi voz `<grabacion.wav>`» — con coqui-TTS instalado (opcional, 2 GB)

### El teléfono como una extensión más

Por ADB, con el cable y la depuración USB: nada de cuentas ni servidores.
«¿cómo conecto mi móvil?» explica los tres pasos.

- «¿cómo está mi móvil?» — batería, temperatura y notificaciones sin verlas
- «¿qué notificaciones tengo?» — las del teléfono, no las del PC
- «¿dónde está mi móvil?» — lo hace sonar aunque esté en silencio, y da la
  última posición conocida
- «abre spotify en el móvil» — lanza cualquier app instalada
- «mándale un whatsapp a Ana: llego tarde» — lo **escribe** y lo enseña; solo
  sale cuando usted dice «envíalo»
- «avísame cuando me escriba el banco» — el móvil despierta al PC
- «conecta el móvil por wifi» — empareja y ya puede quitar el cable

### Aprender de usted

- «aprende esto» → haga la tarea → «ya está» → «llámala informe del lunes»
  Aprende viéndole una vez y luego «haz el informe del lunes» lo repite,
  comprobando antes de cada paso que la ventana es la que tocaba
- «¿qué rutinas sabes?» — lo que ha aprendido mirando
- «analiza `<lo que sea>`» — escribe un programa, lo ejecuta en su propia
  carpeta y corrige sus fallos hasta que sale (tres intentos)
- «encárgate de `<objetivo>`» — lo parte en pasos, los ejecuta uno a uno y
  replanifica lo que falle; «¿cómo va la misión?» / «para la misión»
- «¿cuánto has aprendido de mí?» — conversaciones, valoraciones y si el equipo
  puede afinar el modelo
- «afínate» / «aprende de mí» — prepara el dataset (sin credenciales y sin lo
  que usted valoró mal) y el guion de entrenamiento LoRA, listo para cuando haya GPU

### Seguridad y continuidad

- «despliega los señuelos» — trampas anti-ransomware; corta la red y bloquea si saltan
- «restaura la red» — deshace ese corte
- «activa el modo privado» — nada sale del equipo; «¿qué sale de mi PC?» lo audita
- «haz una copia de tu cerebro» — memoria, grafo y preferencias en un .zip
- «activa el protocolo de relevo» — ausencia prolongada: cifra y avisa, **nunca borra**
- «¿qué equipos tienes?» — enlace y relevo entre varios PCs

### Que se programe solo

- «escríbete una habilidad para `<lo que sea>`» — la escribe, la valida, pasa toda
  la batería de pruebas y la deja en cuarentena
- «¿qué habilidades pendientes?» / «muéstrame la habilidad `<nombre>`» / «aprueba `<nombre>`»
- «¿qué habilidades se pisan?» — mapa de colisiones entre las 360 existentes
- «entrena tu clasificador» — aprende de sus propias órdenes

### Día a día

- «parte del día» / «ponme al día» — anoche, hoy, fallos, recados y qué sueles pedir
- «prepárate para» — lo que sueles abrir antes de lo que viene en la agenda
- «modo trabajo» / «modo juego» / «modo noche» / «modo invitado» / «modo normal»
- «no» (justo después de una acción grande) — ventana de 15 s para revertirla
- «eso estuvo mal, quería X» / «así sí» — te valora y aprende
- «¿cómo lo estoy haciendo?» — su porcentaje de acierto según usted
- «¿qué me dijiste sobre X?» — busca en las conversaciones pasadas
- «¿qué micrófonos tienes?» / «usa el micrófono 2» / «prueba el micrófono»
- «¿por qué tardas?» — dónde se van los milisegundos; «¿cuánto has gastado?» la voz
- «actualízate» — se actualiza y vuelve atrás solo si algo se rompe
- «instálate como servicio» — arranque automático que sobrevive al cierre de sesión

### Solo para ULTRON

- «ejecuta el comando `<lo que sea>`» — shell libre, sin confirmaciones, con
  registro de todo lo ejecutado
- «abre la calculadora y luego dime la hora» — cadenas de órdenes reales
- «¿quién entró?» / «historial del guardián» — línea temporal de la vigilancia
- «estado de auto-reparación» — selectores Android curados automáticamente

---

## Dónde está cada cosa

| Fichero | Qué hace |
|---|---|
| `reiniciar_todo.py` | Arranca (o reinicia) todo el sistema |
| `revisar.py` | Diagnóstico: qué funciona, qué no y cómo arreglarlo |
| `observador.py` | Mira la pantalla y se ofrece cuando le ve atascado |
| `voz_propia.py` | Voz neuronal local, distinta para JARVIS y para ULTRON |
| `movil.py` | El teléfono Android como periférico: avisos, apps, WhatsApp |
| `demostracion.py` | Aprende una rutina viéndole hacerla una vez |
| `escaner3d.py` | Escanea objetos con la cámara y los despieza en 3D |
| `holo_puente.py` | El servidor del holograma y el puente con el navegador |
| `holo_web/` | El escáner del móvil y el visor holográfico (three.js) |
| `analista.py` | Escribe programas, los ejecuta y corrige sus propios fallos |
| `mision.py` | Objetivos largos: planifica, ejecuta y replanifica |
| `verificador.py` | Segundo par de ojos antes de lo que no tiene vuelta atrás |
| `afinar.py` | Dataset y guion LoRA con su forma de hablar |
| `instalar_dependencias.py` | Instala dependencias sin rendirse a la primera |
| `autorizar_google.py` | Conecta Google Calendar |
| `herramientas\abrir_firewall.ps1` | Abre el puerto del móvil (como administrador) |
| `jarvis.py` / `jarvis.bat` | Lanzador único (todos los modos) |
| `jarvis_core.py` | Núcleo: LLM, voz, memoria |
| `jarvis_skills.py` | Las habilidades (lo que sabe hacer) |
| `energia.py` | Apagado/reinicio que obedece siempre (anula lo pendiente) |
| `ejecutor.py` | Todo comando del sistema pasa por aquí y se comprueba |
| `storage.py` | Registro de acciones, auditoría y eventos (`jarvis_audit.db`) |
| `cognition/` | Motores: riesgo, shell auditado, intenciones, señales |
| `jarvis_escucha.py` | Escucha continua, palabra de activación e interrupción |
| `jarvis_proactive.py` | Avisos proactivos (batería, disco, temperatura...) |
| `self_healing.py` | Auto-reparación de selectores Android (ULTRON) |
| `test_regresion.py` | Pruebas: 25 grupos, 100+ comprobaciones |
| `deshacer.py` | Diario reversible: «deshaz eso» |
| `vigilante.py` | Vigila que el propio JARVIS siga vivo |
| `herramientas_llm.py` | 30 herramientas que el cerebro puede ejecutar |
| `vision.py` | Mirar la pantalla y entenderla (modelo local) |
| `piloto.py` | Ratón y teclado: usar el PC como un humano |
| `sandbox.py` | Ensayar órdenes antes de ejecutarlas |
| `canarios.py` | Señuelos anti-ransomware |
| `modo_nocturno.py` | Turno de noche con presupuesto y parte |
| `enjambre.py` | Especialistas con presupuesto de interrupción |
| `consejo.py` | Deliberación JARVIS contra ULTRON |
| `prediccion.py` | Hábitos: anticiparse en vez de reaccionar |
| `indice_documentos.py` | Buscar dentro de sus documentos |
| `voz_identidad.py` | Reconocer quién está hablando |
| `rebobinar.py` | Memoria episódica de la pantalla (opt-in) |
| `autoskills.py` | JARVIS se escribe habilidades a sí mismo |
| `colisiones.py` | Qué habilidades se pisan entre sí |
| `privacidad.py` | Modo privado verificable |
| `cerebro_backup.py` | Exportar/importar todo lo aprendido |
| `recados.py` | Filtrar mensajes y tomar recado |
| `relevo.py` | Protocolo de inactividad (cifra y avisa, nunca borra) |
| `cluster.py` | Varios equipos, un solo asistente |
| `afinar.py` | Ajuste fino del modelo con su forma de hablar |
| `arrepentimiento.py` | Ventana de 15 s para decir «no» tras una acción |
| `perfiles.py` | Perfiles de contexto (trabajo, juego, noche, invitado) |
| `feedback.py` | Valoraciones del señor y su porcentaje de acierto |
| `metricas.py` | Latencia por etapa y gasto de voz |
| `audio_dispositivos.py` | Elegir y probar micrófono |
| `orquestador.py` | Parte del día: agenda + hábitos + turno de noche |
| `actualizar.py` | Actualización con pruebas y vuelta atrás automática |
| `servicio.py` | Arranque automático (tarea programada o servicio) |
| `web_interface/aeon.html` | **ÆON: la interfaz de gala, un diseño distinto por personalidad** |
| `web_interface/modulos.js` | Los módulos que comparten ÆON y el NEXUS |
| `web_interface/nexus.html` | Interfaz unificada anterior: JARVIS, ULTRON y el consejo |
| `web_interface/panel.html` | Panel de control de todos los subsistemas |
| `web_interface/panel_api.py` | Estado y mandos del panel |
| `web_interface/app.py` | Servidor web y móvil |
| `jarvis_qr.py` | Genera el QR de emparejamiento |
| `red_movil.py` | Por qué direcciones te encuentra el teléfono y qué falla si no |
| `remoto.py` | El PC como servidor: acceso desde fuera por la red privada |
| `mcp_servers/` | Calendario, Home Assistant y Android |

---

## Problemas conocidos

- **`pygame` no se instala en Python 3.14.** Todavía no publican una versión
  compatible. JARVIS lo detecta y reproduce la voz con el reproductor de
  Windows: funciona igual, solo que abre una ventana. Con Python 3.12 se
  instala sin problema.
- **La primera orden de voz desde el móvil tarda.** Se está descargando el
  modelo de transcripción (~145 MB). Solo pasa la primera vez.
- **ElevenLabs responde 402.** Se ha agotado el crédito de la cuenta. JARVIS
  sigue hablando con la voz de Windows.
- **Sin PyAudio no hay micrófono en el PC.** La escucha continua y el `listen()`
  del núcleo lo necesitan (`pip install pyaudio`). Sin él, la voz sigue
  funcionando desde el navegador y desde Telegram.
- **Sin scikit-learn no hay clasificador de intenciones.** JARVIS funciona
  igual; solo pierde la pista que da al cerebro cuando ninguna habilidad
  reconoce una orden (`pip install scikit-learn`).

---

## Velocidad

Si algo va lento, pregúntele: **«¿por qué tardas?»** — mide de verdad cada etapa
(dictado, cerebro, generación, voz, habilidades) y dice dónde se va el tiempo.

Lo que ya está optimizado, con lo medido en este equipo:

| Etapa | Antes | Ahora | Cómo |
|---|---|---|---|
| Freno entre respuestas | hasta 2 s | 0 s | Los topes de cuota vienen apagados: sin reserva local, cortar dejaría a JARVIS mudo |
| Dictado por frase | 7,9 s | 0,1–1 s | Todos los núcleos, búsqueda greedy y filtro de voz que descarta los silencios |
| Primera frase dictada | 6,3 s | 0 s | El modelo de dictado se precarga al arrancar |
| Empezar a hablar | 1,9 s | 3 ms | La voz de Windows va en proceso (SAPI), no arrancando un PowerShell por frase |
| Primera pregunta tras una pausa | +2,2 s | 0 s | Claude está siempre caliente: ya no hay modelo local que recargar |
| Respuesta del cerebro | 350 tokens | 200 | A 61 tokens/s medidos, cada 100 tokens de más son 1,6 s |
| Reglas proactivas caras | cada 2 min | 10 min a 6 h | winget y WMI tardan casi un segundo cada uno |

Resultado en conversación normal: de **2,7 s a 0,34 s** una respuesta corta, y de
3,2 s a 1,2 s una explicación. Las habilidades (hora, batería, apagar…) van en
**0,01 s** porque ni tocan el modelo.

Variables para afinar más: `JARVIS_MAX_TOKENS` (200), `JARVIS_WHISPER_MODELO`
(`tiny` es tres veces más rápido que `base`), `JARVIS_WHISPER_HILOS`,
`JARVIS_CALIENTE_MINUTOS` (0 lo desactiva).

## Ajustes finos (variables de entorno)

| Variable | Por defecto | Para qué |
|---|---|---|
| `JARVIS_ESCUCHA` | `0` | `1` arranca ya escuchando, sin pedirlo por voz |
| `JARVIS_PALABRA_ACTIVACION` | `jarvis` | Nombre(s) por los que responde, separados por comas |
| `JARVIS_WHISPER_MODELO` | `base` | Modelo de dictado local (`small` es más preciso y más lento) |
| `JARVIS_PROACTIVO` | `1` | `0` apaga los avisos proactivos |
| `JARVIS_PROACTIVO_INTERVALO` | `120` | Segundos entre rondas de vigilancia |
| `JARVIS_OLVIDO_DIAS` | `45` | Tiempo sin usarse tras el que un concepto se debilita |
| `JARVIS_AUDITORIA_DIAS` | `90` | Cuánto se conserva el registro de acciones |
| `JARVIS_HISTORIAL_MAX` | `5000` | Interacciones que se conservan en la memoria |
| `JARVIS_PIN_DIAS` | `30` | Caducidad del PIN de la web (`0` = nunca) |
| `JARVIS_PAIR_DIAS` | `30` | Caducidad del emparejamiento de un teléfono (`0` = nunca) |
| `JARVIS_TOOLS` | `1` | `0` desactiva que el cerebro ejecute herramientas |
| `JARVIS_VISION_MODELO` | auto | Modelo de visión a usar (si no, se busca el instalado) |
| `JARVIS_PILOTO_PASOS` | `12` | Pasos máximos por objetivo del piloto |
| `JARVIS_VIGILANTE` | `1` | `0` apaga el perro guardián interno |
| `JARVIS_NOCTURNO_MINUTOS` | `45` | Presupuesto del turno de noche |
| `JARVIS_ENJAMBRE_UMBRAL` | `0.7` | Importancia mínima para interrumpirle |
| `JARVIS_REBOBINAR_DIAS` | `7` | Días que se conserva la grabación de pantalla |
| `JARVIS_RELEVO_DIAS` | `30` | Días de silencio antes del primer aviso de relevo |
| `JARVIS_CANARIOS_UMBRAL` | `2` | Señuelos tocados que disparan la alarma |

## Seguridad de la interfaz web

- El PIN de 6 dígitos **caduca a los 30 días** y se genera uno nuevo al
  arrancar. Para cambiarlo en el acto (QR filtrado, captura compartida):
  `POST /rotate_token` con el PIN actual.
- Los teléfonos emparejados caducan también a los 30 días: una IP que vuelve al
  pool DHCP ya no hereda el permiso para siempre.
- `POST /allow_my_ip` **exige el PIN**. Antes cualquiera en la misma red podía
  darse de alta a sí mismo llamando a ese endpoint.
- `GET /pair_status` dice qué aparatos están emparejados y cuánto les queda.
