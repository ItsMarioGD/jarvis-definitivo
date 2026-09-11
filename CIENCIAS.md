# Ciencias: matemáticas, física y química para JARVIS y ULTRON

Todo en local. No hay API de pago ni internet: sympy resuelve, numpy muestrea,
matplotlib dibuja la lámina y un visor web propio (three.js) hace la versión
girable. Lo que sale se guarda en `~/Descargas/JARVIS/Ciencia/<problema>-<fecha>/`.

## Instalar

Ya está en `requirements.txt`. Si falta algo:

```bash
pip install sympy scipy pint
```

O dígaselo en voz alta: **«instala las librerías de ciencias»**.

`numpy` y `matplotlib` ya venían con el proyecto. `scipy` y `pint` son
opcionales: sin ellos el módulo funciona igual.

## Cómo se usa

Se le habla como a un profesor. No hay sintaxis que aprender: el módulo
traduce el dictado («equis al cuadrado», «raíz cuadrada de», «dos mil
trescientos cuarenta y cinco») a notación antes de resolver.

| Lo que se dice | Lo que hace |
|---|---|
| «resuélveme equis al cuadrado menos cinco equis más seis igual a cero» | raíces, discriminante, factorización y la gráfica con las raíces marcadas |
| «derívame equis al cubo por seno de equis y grafícalo» | derivada, puntos críticos, y función + derivada superpuestas |
| «integra equis al cuadrado de cero a tres» | primitiva, regla de Barrow y el área sombreada |
| «cuál es el límite de seno de equis entre equis cuando equis tiende a cero» | sustitución, indeterminación y valor |
| «resuelve el sistema x + y = 10; x - y = 2» | matriz de coeficientes, determinante y solución |
| «grafícame en tres dimensiones seno de equis por coseno de ye» | superficie + mapa de nivel + **malla .obj/.stl** + visor girable |
| «una pelota se lanza a 25 metros por segundo con 40 grados, dibújamelo en 3D» | alcance, altura, tiempos, y la trayectoria como tubo 3D imprimible |
| «periodo de un péndulo de 1 metro» | despeja la ley del formulario y enseña el desarrollo |
| «masa molar del H2SO4» | desglose por elemento y composición centesimal |
| «balancea KMnO4 + HCl -> KCl + MnCl2 + H2O + Cl2» | ajuste por álgebra lineal, con el sistema y la comprobación |
| «hazme el modelo 3D de la molécula de amoniaco» | geometría RPECV, polaridad y el modelo de bolas y varillas girable |
| «enséñame la tabla periódica» | los 118 elementos dibujados |
| un enunciado de examen entero, con su lista de requisitos y LaTeX | saca la ecuación de dentro de la prosa, la resuelve exacta y el cerebro redacta la clase encima |
| «entrena tus ciencias» | pasa el examen interno y aprende de los fallos |

Para ver el dibujo basta añadir **«grafícalo»**; para que sea volumen,
**«en 3D»** o **«superficie»**. Con **«holograma»** la malla pasa al visor
holográfico de `modelado3d.py`.

## Qué sale de cada problema

```
~/Descargas/JARVIS/Ciencia/superficie-20260911-094512/
    lamina.png     render de matplotlib a 190–200 ppp
    visor.html     visor interactivo (se abre solo en el navegador)
    malla.obj      la gráfica como modelo 3D — se abre en Blender
    malla.stl      lista para imprimir en 3D
```

Los datos van **embebidos dentro del HTML** a propósito: abierto con doble clic
(`file://`) el navegador bloquea cualquier lectura de un archivo de al lado, así
que un visor que cargara los datos aparte no funcionaría.

## Los módulos

| Archivo | Qué es |
|---|---|
| `ciencias.py` | la puerta: entiende el enunciado y reparte. Con el cerebro si hay; con reglas si no hay internet |
| `matematica.py` | el motor: dictado → notación, sympy, muestreo robusto, láminas 2D/3D, mallas y visor |
| `fisica.py` | banco de 74 leyes con símbolos y unidades (elige y despeja sola) + análisis con gráfica |
| `quimica.py` | tabla periódica de 118 elementos, masas molares, balanceo, pH, cinética, RPECV en 3D |
| `entrenar_ciencias.py` | el examen de 50 problemas y la memoria de frases aprendidas |

## Tipos de gráfica

**2D** — funciones (marca raíces, máximos, mínimos, inflexiones y asíntotas
verticales y horizontales), área bajo la curva, paramétricas con el sentido del
recorrido en color, polares, campos de direcciones con curvas integrales,
histogramas, cajas y nubes de puntos con recta o parábola de ajuste y su R².

**3D** — superficie `z = f(x,y)` con mapa de color y curvas de nivel
proyectadas, superficies paramétricas `(u,v)`, curvas en el espacio exportadas
como tubo sólido, campos vectoriales con divergencia y rotacional, y
superficies **implícitas** `F(x,y,z)=0` reconstruidas por *surface nets* (una
esfera sale con radio exacto a menos de 0,3 % con malla de 24³).

## El entrenamiento

`entrenar_ciencias.py` no es una demo: es el examen con el que se comprueba que
los módulos aciertan, y el mecanismo por el que lo aprendido se queda.

```bash
python entrenar_ciencias.py                    # examen + aprendizaje
python entrenar_ciencias.py --solo-examen
python entrenar_ciencias.py --materia quimica
```

1. Pasa los 50 problemas del banco (muchos escritos como se **dictan**, y
   otros envueltos en prosa de examen).
2. Compara con la respuesta correcta: por número con tolerancia, por texto que
   debe aparecer, o comprobando que el archivo `.png`/`.obj` se generó de verdad.
3. De cada fallo de **enrutado** guarda la huella de la frase con la acción
   correcta en `~/Descargas/JARVIS/Prefs/ciencias_aprendido.json`. `ciencias.py`
   consulta ese fichero antes de decidir, así que esa forma de hablar ya no se
   vuelve a fallar. Solo aprende de los fallos de enrutado: si eligió bien y aun
   así erró, el problema está en el cálculo y memorizarlo no arreglaría nada.
4. Deja el informe (`informe.json` + gráfica del progreso) en
   `~/Descargas/JARVIS/Ciencia/entrenamiento/`, y apunta en la memoria
   permanente y en la unificada qué sabe hacer ahora.

También se le puede enseñar a mano:

```python
import entrenar_ciencias
entrenar_ciencias.ensenar("sácame la pendiente de", "derivar")
```

o por voz: «cuando te diga sácame la pendiente de, haz derivar».

**Nota actual: 10,0 sobre 10 — 50 de 50 problemas** (22 matemáticas,
15 física, 13 química).

## Encargos largos y modo tutor

Un enunciado real no viene solo. Llega así:

> «Actúa como un tutor experto en matemáticas. Resuelve paso a paso la
> siguiente ecuación cuadrática: 3x² − 5x − 2 = 0. Requisitos de respuesta:
> 1. Identifica los coeficientes (a, b, c). 2. Aplica la fórmula general
> mostrando cada paso explícito en LaTeX. 3. Encuentra y simplifica los dos
> valores posibles para x. 4. Explica brevemente el significado del
> discriminante.»

Quitar verbos no sirve con eso, así que el módulo va a **buscar** el trozo que
es matemática dentro del texto (`ciencias._extraer_matematica`) y lo resuelve
exacto con sympy. Después, como el encargo pide además que se EXPLIQUE, el
cerebro redacta la clase **encima del cálculo ya verificado**: recibe los
resultados de sympy con la orden de no recalcular nada. Así la explicación es
didáctica y la aritmética no se inventa, que es justo lo que hacen mal los
modelos de lenguaje por su cuenta.

Se activa solo, cuando el encargo trae marcas de instrucción: «actúa como»,
«paso a paso», «explica», «justifica», «requisitos», una lista numerada, o más
de 35 palabras. Si además se pide LaTeX, las fórmulas salen en `$$…$$`.

Sin cerebro disponible, queda el desarrollo determinista, que ya cubre los
cuatro puntos del ejemplo (coeficientes, fórmula general, raíces exactas y
decimales, discriminante con su interpretación, y de propina Cardano-Vieta y
el vértice de la parábola).

**Cuando NO hay nada que calcular** («explícame qué es una derivada y para qué
sirve»), el módulo se aparta: devuelve vacío y la frase sigue su camino normal
hasta el cerebro. Un callejón sin salida es peor que una respuesta conversada.

## La física elige la ley sola

Nadie dice «usa la fórmula de la velocidad». Se dan los datos y ya:

> «Un móvil parte del reposo con aceleración de 2 m/s². ¿Qué velocidad tiene a
> los 5 s?»

`fisica.elegir_ley()` prueba las 74 leyes del banco y se queda con la que más
datos del enunciado consume dejando exactamente una incógnita. Además:

- lee los **sobreentendidos** («parte del reposo» → v₀ = 0; «hasta detenerse»
  → v = 0; «se deja caer» → v₀ = 0; «horizontalmente» → θ = 0);
- pesa **cómo se pregunta** («¿cuánto tarda?» busca un tiempo, «¿qué
  aceleración?» una aceleración), que distingue mejor que las palabras sueltas;
- distingue el símbolo de la constante que se llama igual: la `h` de la caída
  libre es una ALTURA, no la constante de Planck. Rellenarla con 6,6·10⁻³⁴
  arruinaba el problema en silencio.

Y cuando una cuadrática da dos raíces, se queda con la de sentido físico (un
tiempo de vuelo negativo es la solución de antes de soltar la piedra), pero
enseña las dos.

## Herramientas que ve el modelo

`resolver_ciencia`, `graficar`, `formula_fisica` y `quimica`. Las cuatro están
marcadas como lectura en `permisos.py`: solo calculan y dejan la lámina en su
carpeta, así que no piden confirmación ni en modo lectura.

## Panel AEON

Tarjeta **«Ciencias»** en el rail: estado del motor, cuántas leyes y elementos
sabe, la última nota del entrenamiento, un campo para dictar el problema y
botones de Resolver / Graficar 2D / Superficie 3D / Tabla periódica / Entrenar.
Hay que **reiniciar el servidor Flask** (`arrancar_ambos.py --reiniciar`) para
que cargue la ruta nueva `/api/ciencias/estado`.
