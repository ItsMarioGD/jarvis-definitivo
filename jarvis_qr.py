"""
jarvis_qr.py - Generacion del QR de emparejamiento, sin depender de nada.

El QR es el unico camino comodo para conectar el telefono, asi que no puede
quedarse en blanco porque falte una libreria. Este modulo tiene dos caminos:

  1. Si la libreria `qrcode` esta instalada, se usa (PNG de toda la vida).
  2. Si no lo esta, se genera el QR aqui mismo, en Python puro, y se devuelve
     como SVG. Los navegadores lo pintan igual y las camaras lo leen igual.

Uso:
    from jarvis_qr import qr_response_data
    datos, mimetype = qr_response_data("http://192.168.1.5:5000/mobile?token=123456")

Implementa codificacion en modo byte con correccion de errores nivel M, que
cubre de sobra las URLs de emparejamiento (hasta ~150 caracteres).
"""

# ── Aritmetica en GF(256), el campo del que salen los codigos Reed-Solomon ──
_EXP = [0] * 512
_LOG = [0] * 256


def _init_tablas():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:          # polinomio generador del estandar QR
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_tablas()


def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _poly_generador(grado):
    """Polinomio generador para `grado` bytes de correccion."""
    g = [1]
    for i in range(grado):
        nuevo = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nuevo[j] ^= c
            nuevo[j + 1] ^= _mul(c, _EXP[i])
        g = nuevo
    return g


def _reed_solomon(datos, n_ec):
    """Bytes de correccion de errores para un bloque de datos."""
    gen = _poly_generador(n_ec)
    resto = list(datos) + [0] * n_ec
    for i in range(len(datos)):
        coef = resto[i]
        if coef == 0:
            continue
        for j, g in enumerate(gen):
            resto[i + j] ^= _mul(g, coef)
    return resto[len(datos):]


# ── Tablas del estandar, nivel de correccion M ─────────────────────────────
# version: (bytes de datos totales, bytes EC por bloque, bloques grupo1,
#           bytes datos por bloque grupo1, bloques grupo2, bytes datos grupo2)
#
# Se llega solo hasta la version 6 A PROPOSITO. A partir de la 7 el estandar
# obliga a incluir un bloque de «informacion de version» (18 bits junto a dos
# de los finder) que aqui no esta implementado: un QR de version 7 sin el se
# genera sin dar error pero ninguna camara lo lee. La version 6 admite 106
# caracteres, y la URL de emparejamiento mas larga (la de Tailscale, con
# token) ronda los 60, asi que sobra sitio. Si algun dia hiciera falta mas,
# hay que implementar la informacion de version antes de ampliar esta tabla.
_VERSIONES_M = {
    1:  (16,   10, 1, 16,  0, 0),
    2:  (28,   16, 1, 28,  0, 0),
    3:  (44,   26, 1, 44,  0, 0),
    4:  (64,   18, 2, 32,  0, 0),
    5:  (86,   24, 2, 43,  0, 0),
    6:  (108,  16, 4, 27,  0, 0),
}

# Centros de los patrones de alineacion por version.
_ALINEACION = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
}

# Informacion de formato ya calculada (nivel M + cada una de las 8 mascaras).
_FORMATO_M = [
    0x5412, 0x5125, 0x5E7C, 0x5B4B, 0x45F9, 0x40CE, 0x4F97, 0x4AA0,
]


def _elegir_version(n_bytes):
    """Version mas pequena que admite `n_bytes` de contenido."""
    for v in sorted(_VERSIONES_M):
        capacidad = _VERSIONES_M[v][0]
        # 4 bits de modo + 8 bits de longitud = 12 bits, o sea 2 bytes largos
        if n_bytes + 2 <= capacidad:
            return v
    raise ValueError(
        f"El texto ocupa {n_bytes} bytes y aqui el maximo son "
        f"{_VERSIONES_M[max(_VERSIONES_M)][0] - 2}. Instala la libreria "
        f"`qrcode` (pip install qrcode Pillow) para codigos mas grandes.")


def _bits_de_datos(texto, version):
    """Codifica el texto en modo byte y anade relleno hasta llenar la version."""
    datos = texto.encode("utf-8")
    capacidad = _VERSIONES_M[version][0]
    bits = []

    def mete(valor, n):
        for i in range(n - 1, -1, -1):
            bits.append((valor >> i) & 1)

    mete(0b0100, 4)                 # modo byte
    mete(len(datos), 8)             # longitud (8 bits para versiones 1-9)
    for b in datos:
        mete(b, 8)

    # Terminador: hasta 4 ceros, sin pasarse de la capacidad.
    for _ in range(min(4, capacidad * 8 - len(bits))):
        bits.append(0)
    # Cuadrar a byte completo.
    while len(bits) % 8:
        bits.append(0)

    palabras = [int("".join(str(b) for b in bits[i:i + 8]), 2)
                for i in range(0, len(bits), 8)]
    # Relleno estandar, alternando estos dos bytes.
    relleno = (0xEC, 0x11)
    i = 0
    while len(palabras) < capacidad:
        palabras.append(relleno[i % 2])
        i += 1
    return palabras


def _intercalar(palabras, version):
    """Reparte los datos en bloques, calcula su EC y los entrelaza."""
    _, n_ec, g1, d1, g2, d2 = _VERSIONES_M[version]
    bloques, i = [], 0
    for _ in range(g1):
        bloques.append(palabras[i:i + d1])
        i += d1
    for _ in range(g2):
        bloques.append(palabras[i:i + d2])
        i += d2

    ecs = [_reed_solomon(b, n_ec) for b in bloques]

    salida = []
    for col in range(max(len(b) for b in bloques)):
        for b in bloques:
            if col < len(b):
                salida.append(b[col])
    for col in range(n_ec):
        for e in ecs:
            salida.append(e[col])
    return salida


def _matriz_base(version):
    """Rejilla con los patrones fijos puestos. None = hueco para datos."""
    n = version * 4 + 17
    m = [[None] * n for _ in range(n)]

    def finder(fila, col):
        for dy in range(-1, 8):
            for dx in range(-1, 8):
                y, x = fila + dy, col + dx
                if not (0 <= y < n and 0 <= x < n):
                    continue
                borde = dy in (-1, 7) or dx in (-1, 7)
                if borde:
                    m[y][x] = 0
                else:
                    anillo = dy in (0, 6) or dx in (0, 6)
                    centro = 2 <= dy <= 4 and 2 <= dx <= 4
                    m[y][x] = 1 if (anillo or centro) else 0

    finder(0, 0)
    finder(0, n - 7)
    finder(n - 7, 0)

    # Patrones de tiempo.
    for i in range(8, n - 8):
        m[6][i] = 1 - (i % 2)
        m[i][6] = 1 - (i % 2)

    # Patrones de alineacion (nunca encima de los finder).
    centros = _ALINEACION[version]
    for cy in centros:
        for cx in centros:
            if (cy, cx) in ((6, 6), (6, n - 7), (n - 7, 6)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    borde = max(abs(dy), abs(dx))
                    m[cy + dy][cx + dx] = 1 if borde != 1 else 0

    # Modulo oscuro obligatorio.
    m[n - 8][8] = 1

    # Reservar los huecos de la informacion de formato.
    for i in range(9):
        if m[8][i] is None:
            m[8][i] = 0
        if m[i][8] is None:
            m[i][8] = 0
    for i in range(n - 8, n):
        m[8][i] = 0
        m[i][8] = 0
    return m


def _huecos_datos(version):
    """Rejilla booleana: True donde van los bits de datos."""
    n = version * 4 + 17
    base = _matriz_base(version)
    return [[base[y][x] is None for x in range(n)] for y in range(n)]


def _colocar_datos(m, libre, bits):
    """Recorrido en zigzag de derecha a izquierda, dos columnas cada vez."""
    n = len(m)
    idx = 0
    col = n - 1
    hacia_arriba = True
    while col > 0:
        if col == 6:            # la columna de tiempo no cuenta
            col -= 1
        filas = range(n - 1, -1, -1) if hacia_arriba else range(n)
        for fila in filas:
            for dx in (0, 1):
                x = col - dx
                if not libre[fila][x]:
                    continue
                m[fila][x] = bits[idx] if idx < len(bits) else 0
                idx += 1
        col -= 2
        hacia_arriba = not hacia_arriba


def _mascara(patron, fila, col):
    if patron == 0:
        return (fila + col) % 2 == 0
    if patron == 1:
        return fila % 2 == 0
    if patron == 2:
        return col % 3 == 0
    if patron == 3:
        return (fila + col) % 3 == 0
    if patron == 4:
        return (fila // 2 + col // 3) % 2 == 0
    if patron == 5:
        return (fila * col) % 2 + (fila * col) % 3 == 0
    if patron == 6:
        return ((fila * col) % 2 + (fila * col) % 3) % 2 == 0
    return ((fila + col) % 2 + (fila * col) % 3) % 2 == 0


def _penalizacion(m):
    """Puntuacion del estandar: cuanto mas baja, mejor lee la camara."""
    n = len(m)
    total = 0

    # Regla 1: rachas de 5 o mas del mismo color.
    for linea in list(m) + [[m[y][x] for y in range(n)] for x in range(n)]:
        racha, anterior = 1, linea[0]
        for v in linea[1:]:
            if v == anterior:
                racha += 1
            else:
                if racha >= 5:
                    total += 3 + (racha - 5)
                racha, anterior = 1, v
        if racha >= 5:
            total += 3 + (racha - 5)

    # Regla 2: bloques de 2x2 del mismo color.
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                total += 3

    # Regla 3: patrones que se confunden con un finder.
    aguja = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    for linea in list(m) + [[m[y][x] for y in range(n)] for x in range(n)]:
        for i in range(n - 10):
            trozo = linea[i:i + 11]
            if trozo == aguja or trozo == aguja[::-1]:
                total += 40

    # Regla 4: desequilibrio entre claro y oscuro.
    oscuros = sum(sum(f) for f in m)
    porcentaje = oscuros * 100 // (n * n)
    total += 10 * (abs(porcentaje - 50) // 5)
    return total


def _poner_formato(m, patron):
    """Escribe los 15 bits de formato en sus dos ubicaciones."""
    n = len(m)
    bits = [(_FORMATO_M[patron] >> i) & 1 for i in range(14, -1, -1)]
    # Copia junto al finder superior izquierdo.
    coords = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
              (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    for bit, (y, x) in zip(bits, coords):
        m[y][x] = bit
    # Copia repartida entre los otros dos finder.
    for i in range(7):
        m[n - 1 - i][8] = bits[i]
    for i in range(8):
        m[8][n - 8 + i] = bits[7 + i]
    m[n - 8][8] = 1


def matriz_qr(texto):
    """Matriz de 0 y 1 del QR que codifica `texto`."""
    datos = texto.encode("utf-8")
    version = _elegir_version(len(datos))
    palabras = _intercalar(_bits_de_datos(texto, version), version)

    bits = []
    for p in palabras:
        for i in range(7, -1, -1):
            bits.append((p >> i) & 1)

    libre = _huecos_datos(version)
    mejor, mejor_puntos = None, None
    for patron in range(8):
        m = _matriz_base(version)
        _colocar_datos(m, libre, bits)
        for y in range(len(m)):
            for x in range(len(m)):
                if libre[y][x] and _mascara(patron, y, x):
                    m[y][x] ^= 1
        _poner_formato(m, patron)
        puntos = _penalizacion(m)
        if mejor_puntos is None or puntos < mejor_puntos:
            mejor, mejor_puntos = m, puntos
    return mejor


def qr_svg(texto, escala=8, margen=4):
    """QR como SVG. Sin dependencias: siempre funciona."""
    m = matriz_qr(texto)
    n = len(m)
    lado = (n + margen * 2) * escala
    piezas = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{lado}" height="{lado}" '
        f'viewBox="0 0 {lado} {lado}" shape-rendering="crispEdges">',
        f'<rect width="{lado}" height="{lado}" fill="#ffffff"/>',
    ]
    for y in range(n):
        for x in range(n):
            if m[y][x]:
                px = (x + margen) * escala
                py = (y + margen) * escala
                piezas.append(f'<rect x="{px}" y="{py}" width="{escala}" '
                              f'height="{escala}" fill="#000000"/>')
    piezas.append("</svg>")
    return "".join(piezas)


def qr_response_data(texto, escala=8):
    """(bytes, mimetype) listos para devolver desde Flask.

    Prefiere PNG con la libreria `qrcode` si esta disponible; si no, cae al
    SVG propio. La pagina de emparejamiento acepta cualquiera de los dos.
    """
    try:
        import qrcode
        from io import BytesIO
        img = qrcode.make(texto)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"
    except Exception:
        pass
    return qr_svg(texto, escala=escala).encode("utf-8"), "image/svg+xml"


if __name__ == "__main__":
    import sys
    texto = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.1.117:5000/mobile?token=123456"
    m = matriz_qr(texto)
    # Vista rapida en la terminal: dos espacios por modulo para que salga cuadrado.
    print()
    for fila in [[0] * len(m)] * 2 + m + [[0] * len(m)] * 2:
        print("  " + "".join("  " if not v else "██" for v in fila))
    print(f"\n  {len(m)}x{len(m)} modulos para {len(texto)} caracteres")
