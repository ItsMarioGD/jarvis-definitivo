# JARVIS en la universidad

Los módulos pensados para una carrera de ingeniería, del primer día al último.
Todos se apoyan en lo que ya había: el navegador, el índice de documentos, el
calendario y el motor proactivo.

| Módulo | Qué resuelve |
|---|---|
| `fisica_general.py` | despeja **cualquier** ecuación, con unidades y análisis dimensional |
| `vectores.py` | vectores, fuerzas, momentos y vigas, dibujados en 3D |
| `simulacion.py` | los sistemas **en movimiento**: órbitas, péndulos, ondas, lo que dicte |
| `embeddings.py` | buscar en los apuntes por **significado**, no por palabras |
| `estudio.py` | tarjetas y repaso espaciado sacados de **sus** apuntes |
| `portal_academico.py` | el campus: cursos, entregas, fechas y material |
| `informe.py` | memorias de prácticas en `.tex`, `.docx` y `.md` |
| `pensar.py` | el ayudante común para hablar con el cerebro sin quedarse a medias |

## Resolver y entender

### Cualquier ecuación, no un formulario

El banco de 74 leyes de `fisica.py` se acaba en semanas. `fisica_general.py` no
tiene catálogo:

```
despejar("1/f = 1/s + 1/i", {"f": "10 cm", "s": "15 cm"})
  →  Despejado: i = f·s/(-f + s)
     Resultado: i = 0.3 m
```

Tres cosas que un despeje a pelo no da:

* **La fórmula primero**, que es lo que puntúa en un examen.
* **Unidades de verdad** con `pint`: «2 km» y «2000 m» son el mismo dato.
* **Análisis dimensional**, que caza el error sin resolver nada:
  `E = m*v` → *no cuadra: [masa·longitud²/tiempo²] ≠ [masa·longitud/tiempo]*.

> **Cuidado con las mayúsculas.** En física `P` es potencia y `p` cantidad de
> movimiento. Y `E`, `I`, `N`, `O`, `S` y `Q` son constantes de sympy: sin
> forzarlas a ser símbolos, «E = m·c²» se convertía en «e = c²·m» con la
> energía valiendo 2,718… El módulo lo fuerza; las pruebas lo vigilan.

### Vectores y estática

| Se dice | Hace |
|---|---|
| «descompón 100 newtons a 30 grados» | componentes, con la comprobación |
| «viga de 6 metros con 1000 newtons a 2 metros» | reacciones por ΣM = 0 y ΣF = 0 |
| «dibuja las fuerzas (100,0,0) y (0,80,0)» | el diagrama en 3D, girable, con su resultante |
| «equilibrio de las fuerzas …» | si no lo está, **qué fuerza falta** |

También módulo, unitario, ángulos directores, producto escalar y vectorial,
proyección y momento con su brazo.

### Simulaciones

Ver [CIENCIAS.md](CIENCIAS.md). Diez sistemas montados y, la que quita el
techo, **las ecuaciones que usted dicte** integradas con Runge-Kutta 4.

## Apuntes y estudio

### Buscar por significado

Con la clave de Pollinations (o `ollama pull nomic-embed-text`), la búsqueda
deja de ser por palabras:

```
«busca en mis apuntes qué es una derivada»
  →  encuentra el apunte que dice «tasa de variación instantánea»
     y nunca escribe la palabra «derivada»
```

Es **híbrida**: FTS5 para lo literal (un número de expediente lo clava) y
vectores para lo que se recuerda de otra forma.

* «indexa mis documentos» — lee y vectoriza
* «vectoriza» — completa lo indexado **antes** de activar el motor

### Que te pregunte él a ti

Releer da sensación de saber y es de las peores formas de estudiar. Lo que
funciona es lo contrario:

```
«hazme tarjetas de derivadas»   →  8 tarjetas sacadas de SUS apuntes
«pregúntame»                    →  una pregunta, la que toque hoy
«respondo es la pendiente…»     →  corrige y calcula cuándo vuelve
«cómo voy»                      →  el parte
```

El intervalo va por un SM-2 recortado: fallo → mañana; bien → intervalo por el
factor de facilidad; fácil → más aún. El factor no baja de 1,3 (si no, la
tarjeta se pregunta a diario para siempre) y el intervalo se corta en un año.

Las preguntas salen **solo** de sus apuntes. Si no hay apuntes del tema, se
dice: inventar preguntas de un temario que no se ha visto es la forma más
rápida de estudiar lo que no entra.

## La carrera

### El campus

```
«configura mi portal en campus.universidad.es»
«mira el campus»                    →  entra y lista las entregas con su fecha
«mis asignaturas»
«bájame el material de cálculo»     →  lo descarga Y lo indexa
«pon las entregas en el calendario»
```

Reconoce Moodle, Canvas y Blackboard, y lee **el JSON que la web pide por
detrás** en vez de rascar el texto: el dato sale exacto y no se rompe con el
rediseño. Si no reconoce la plataforma, mira la página como la miraría usted.

Las entregas que vencen entran en el motor proactivo, así que **avisa solo**
antes de que se pasen.

> **Dos límites que no se negocian.** JARVIS **no teclea su contraseña**: entra
> usted una vez en su ventana y la sesión queda guardada. Y **no pulsa
> «entregar»**: prepara el borrador y el botón lo pulsa usted. Una entrega no
> se deshace, y el que responde es usted. Mire además qué dice su universidad
> sobre el uso de IA en las entregas: varían mucho.

### Informes y memorias

```
«hazme el informe de la práctica de caída libre»
```

Sale en `.tex` (Overleaf), `.docx` (para el campus) y `.md` (para corregirlo),
con la estructura de siempre: objetivo, fundamento, método, datos, resultados,
discusión, conclusiones y referencias.

* Los **cálculos se verifican** con sympy antes de escribirse, no se recuerdan.
* Se apoya en **sus apuntes** y cita el archivo.
* Lo que no puede saber lo deja **entre corchetes**: `[medición pendiente]`.
  Un informe con datos inventados es peor que uno sin terminar.

No hay LaTeX instalado en este equipo, así que el PDF no se compila; el `.tex`
sale listo para Overleaf.

## Una nota sobre el cerebro

Todos estos módulos hablan con el modelo a través de `pensar.py`, y hay un
motivo concreto: **los modelos que razonan gastan del mismo presupuesto de
tokens**. Con `max_tokens=2500` y un encargo largo, el modelo se gastaba los
2500 pensando y devolvía `finish_reason: length` con el contenido **vacío**. No
es un error —la llamada tiene éxito y no trae nada— y desde arriba solo se veía
«el cerebro no devolvió nada».

`pensar.py` baja el esfuerzo de razonamiento en lo estructurado (7,2 s → 4,3 s
medidos), reintenta con el doble de presupuesto si vuelve vacío, y rescata el
JSON aunque venga envuelto en explicaciones o en ```.
