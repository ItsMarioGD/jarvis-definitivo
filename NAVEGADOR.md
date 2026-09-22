# Navegador — JARVIS con las manos dentro de la web

JARVIS navega de verdad: entra en una web, pulsa, rellena, lee el resultado y
contesta. No es «abrir el buscador y dejarte ahí»: es hacer la gestión.

## Cómo funciona

```
JARVIS (python)                         navegador (Edge / Chrome / Brave)
navegador.navegar("...")
    │  WebSocket al puerto 9222 (127.0.0.1)
    │                                        │
    │     Page.navigate · Input.dispatchMouseEvent · Runtime.evaluate
    └───────────────── resultado JSON ───────┘
```

Se habla **Chrome DevTools Protocol**, que todo navegador Chromium trae de
fábrica. El cliente de WebSocket son ochenta líneas de `socket`: **no hace
falta instalar nada**. Ni Playwright (300 MB de navegadores y rueda dudosa en
Python 3.14) ni Selenium ni un solo paquete nuevo en `requirements.txt`.

## Por qué el DOM y no los píxeles

`piloto.py` mira capturas y adivina coordenadas con el modelo de visión, porque
en el escritorio no hay otra. En una web sí la hay: aquí el cerebro recibe la
**lista numerada de lo que se puede tocar**.

```
[3] boton   «Aceptar todo»
[7] campo   «Buscar» (vacío)
[12] enlace «Mis facturas»
```

El modelo elige un número, no un píxel. Sale más barato (texto, no imágenes),
va más rápido y acierta mucho más.

## Leer la API, no el HTML

La mayoría de las webs modernas no traen los datos en el HTML: los piden por
detrás en un JSON y los pintan con JavaScript. JARVIS escucha esas peticiones
(`Network.*`) y puede leer **el mismo JSON que consume la página**.

```
«los datos de esta página»  →  GET .../rest.php/v1/search/title?q=Alan+Turing
                               (200, application/json, 1306 bytes)
                               {"pages": [{"title": "Alan Turing", …}]}
```

Por qué importa: el dato sale **exacto**, no cuesta ni un token de modelo y no
se rompe cuando el sitio cambia de diseño. Rascar el texto renderizado es
adivinar; esto es leer.

Se filtra el ruido (imágenes, fuentes, estilos y scripts) y de las candidatas
se sirve primero la más grande, que casi siempre es la que trae la información.
Si la página no pide nada por detrás, lo dice en lugar de inventárselo.

**Aviso:** el cuerpo hay que pedirlo mientras el navegador aún lo guarda. Tras
cambiar de página se pierde: primero se abre, luego se lee.

## Qué está roto en una web

`navegador_diagnostico` abre o **recarga** la página (los errores ocurren al
cargar: engancharse a una ya cargada la haría parecer sana) y reúne en un solo
informe lo que uno miraría a mano en las herramientas de desarrollo:

* errores y avisos de la consola,
* excepciones sin capturar, con su línea,
* peticiones caídas (`ERR_NAME_NOT_RESOLVED`, ficheros que no están),
* respuestas 4xx y 5xx,
* y lo que sólo ve el navegador: CORS, contenido mixto, CSP.

Si no hay nada, lo dice: «Limpia, señor». Sirve para depurar la web del señor
—y se cruza con `auto_mejora.py`: ve el error, propone el parche, abre la rama—
y para entender por qué una web ajena no hace lo que debería.

## Guardarraíles

| Regla | Por qué |
| --- | --- |
| **Perfil propio** en `~/Descargas/JARVIS/Navegador/Perfil` | No se toca el perfil diario del señor. Sus sesiones de banca y correo no quedan expuestas a un modelo. Lo que quiera que JARVIS maneje, lo inicia una vez en esa ventana. |
| **Nunca escribe contraseñas ni tarjetas** | `escribir()` se niega ante `type=password` o cualquier campo de tarjeta, IBAN o CVV. Eso lo teclea el señor. |
| **Nunca paga** | «Pagar», «Comprar ahora», «Realizar pedido», «Confirmar pago»: se ven, se informan, no se pulsan. |
| **Modo ensayo** | Dice paso a paso qué haría sin tocar nada. Es la idea 2 del IDEAS.MD aplicada a la web, y sale gratis. |
| **Tope de pasos** (14) | Un modelo perdido hace clic para siempre. |
| **Confirmación previa** | `navegador_tarea` está en la lista de `permisos.py` que se para y pregunta: un clic en una web no tiene diario de deshacer. |
| **Todo al diario** | Cada paso va a `storage.py` con la dirección y el resultado. |

Los CAPTCHA no se resuelven: si aparece uno, JARVIS lo dice y se detiene.

## Órdenes de voz

| Se dice | Hace |
| --- | --- |
| «abre el navegador» | lo levanta con su perfil propio |
| «cierra el navegador» | lo cierra |
| «estado del navegador» | binario, puerto, pestaña y carpeta de descargas |
| «qué hay en la pestaña» | dirección, texto visible y qué se puede pulsar |
| «entra en example.com» | abre esa dirección |
| «en la web, <encargo>» | hace la tarea entera |
| «ensaya en la web, <encargo>» | narra qué haría, sin tocar nada |
| «los datos de esta página» | el JSON que la web pide por detrás |
| «qué está roto en la web» / «revisa mi web» | informe de errores |

## Herramientas del modelo

| Herramienta | Para qué | Permiso |
| --- | --- | --- |
| `navegador_tarea` | la tarea completa: navega, pulsa, rellena y lee | confirmar |
| `navegador_ensayo` | ensayo general, sin tocar nada | lectura |
| `navegador_mirar` | qué hay ahora en la pestaña | lectura |
| `navegador_datos` | el JSON que la página pide por detrás | lectura |
| `navegador_diagnostico` | qué está roto en la web | lectura |
| `navegador_abrir` | abre una dirección | directo |

## Configuración

`~/Descargas/JARVIS/Prefs/navegador.json` (se siembra sola):

```json
{"binario": "", "puerto": 9222, "perfil": "", "visible": true,
 "descargas": "", "espera_red": 2.0}
```

* `binario` vacío: busca Chrome, luego Edge, luego Brave.
* `visible: false` lo corre sin ventana.
* Las descargas van a `~/Descargas/JARVIS/Navegador/Descargas`, no a las del
  señor, para que no se mezclen con las suyas.

Variables de entorno: `JARVIS_NAVEGADOR_PUERTO`, `JARVIS_NAVEGADOR_PASOS`.

## Requisitos

Un navegador Chromium (Chrome, Edge o Brave) y el cerebro en marcha. Nada más.

## Lo que falta

Está escrito para que la siguiente pieza encaje sin rehacer nada: **aprender
por demostración**. El señor hace la gestión una vez, JARVIS graba la traza y
sintetiza la rutina reutilizable; cuando el sitio cambie de diseño, el mismo
motor de `self_healing.py` que ya cura la deriva de selectores en Android
servirá para curarla en la web.
