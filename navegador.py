#!/usr/bin/env python3
"""
navegador.py - JARVIS con las manos dentro del navegador
========================================================
`ojo_global.py` demostró que se puede mandar en una página sin instalar medio
mundo: un puente y la pestaña que ve el señor obedece. El problema es que aquel
puente sólo sirve para UNA aplicación, porque hay que inyectarle un `.js` al
repositorio.

Esto es lo mismo pero para CUALQUIER web, y sin inyectar nada: se habla el
protocolo que el propio navegador trae de fábrica, **Chrome DevTools Protocol**.
Se arranca Edge (o Chrome, o Brave) con el puerto de depuración abierto y desde
ahí se ve el DOM, se pulsa, se escribe y se lee.

    JARVIS (python)                     navegador (Edge/Chrome)
    ---------------                     -----------------------
    navegador.abrir("https://...")
        |  WebSocket al puerto 9222 (127.0.0.1)
        |                                   |
        |          Page.navigate / Input.dispatchMouseEvent / Runtime.evaluate
        +------------- resultado JSON ------+

Sin dependencias
----------------
Ni Playwright (300 MB de navegadores y rueda dudosa en Python 3.14) ni
Selenium. El cliente WebSocket son ochenta líneas de `socket` y el resto es
JSON. Lo único que hace falta ya está instalado: un navegador Chromium.

Por qué el DOM y no los píxeles
-------------------------------
`piloto.py` mira capturas y adivina coordenadas con el modelo de visión. En el
escritorio no hay más remedio; en una web sí lo hay. Aquí se le da al cerebro
la **lista de elementos con los que se puede interactuar**, numerada:

    [3] boton    "Aceptar todo"
    [7] campo    "Buscar"  (vacío)
    [12] enlace  "Mis facturas"

El modelo elige un número. No hay coordenadas que fallen, no hace falta modelo
de visión, cuesta una décima parte de tokens y acierta muchísimo más.

Guardarraíles, porque esto pulsa de verdad
------------------------------------------
* **Perfil propio** en `~/Descargas/JARVIS/Navegador/Perfil`. No se toca el
  perfil diario del señor: sus sesiones de banca y correo NO quedan expuestas a
  un modelo. Lo que quiera que JARVIS maneje, lo inicia una vez en esa ventana.
* **Nunca escribe contraseñas ni tarjetas.** `escribir()` se niega en seco ante
  `type=password` o cualquier campo de tarjeta. Eso lo teclea el señor.
* **Nunca paga.** Los botones de compra y pago están en una lista negra: se ven
  y se informan, no se pulsan.
* **Modo ensayo** (`seco=True`): dice paso a paso qué haría sin tocar nada. Es
  la idea 2 del IDEAS.MD aplicada a la web, y es gratis.
* Tope de pasos, y cada paso al diario de `storage.py`.

Configuración en `Prefs/navegador.json` (se siembra sola):
    {"binario": "", "puerto": 9222, "perfil": "", "visible": true,
     "descargas": "", "espera_red": 2.0}
"""
import base64
import json
import os
import random
import re
import select
import shutil
import socket
import subprocess
import time
from collections import deque

_BASE = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS")
_CFG = os.path.join(_BASE, "Prefs", "navegador.json")
_PERFIL = os.path.join(_BASE, "Navegador", "Perfil")
_DESCARGAS = os.path.join(_BASE, "Navegador", "Descargas")

MAX_PASOS = int(os.getenv("JARVIS_NAVEGADOR_PASOS", "14"))
PUERTO = int(os.getenv("JARVIS_NAVEGADOR_PUERTO", "9222"))

# Campos que JARVIS no rellena jamás. No es pudor: teclear una contraseña o un
# número de tarjeta desde un bucle automático es exactamente como se pierde una
# cuenta o un cobro.
_PROHIBIDO_ESCRIBIR = re.compile(
    r"password|contrase|tarjeta|\bcvv\b|\bcvc\b|cc-number|cc-csc|cc-exp|"
    r"card-?number|iban|\bpin\b|c[oó]digo\s+de\s+seguridad", re.I)

# Botones que no se pulsan solos. Se informa y se para.
_PROHIBIDO_PULSAR = re.compile(
    r"\bpagar\b|\bpay\b|\bcomprar\b|\bbuy now\b|realizar\s+(el\s+)?pedido|"
    r"place\s+order|confirmar\s+(el\s+)?pago|finalizar\s+(la\s+)?compra|"
    r"\btransferir\b|\bdonar\b|suscribirme|confirm\s+and\s+pay", re.I)


# ── configuración ───────────────────────────────────────────────────────────
def _cfg() -> dict:
    d = {"binario": "", "puerto": PUERTO, "perfil": "", "visible": True,
         "descargas": "", "espera_red": 2.0}
    try:
        with open(_CFG, encoding="utf-8") as f:
            d.update(json.load(f) or {})
    except Exception:
        pass
    return d


def _guardar_cfg(d: dict):
    try:
        os.makedirs(os.path.dirname(_CFG), exist_ok=True)
        with open(_CFG, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _binario() -> str:
    """Dónde está el navegador. Chrome si lo hay; si no, Edge; si no, Brave."""
    cfg = _cfg()
    if cfg.get("binario") and os.path.exists(cfg["binario"]):
        return cfg["binario"]

    local = os.environ.get("LOCALAPPDATA", "")
    candidatos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    for nombre in ("chrome", "msedge", "brave"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return ""


# ── cliente WebSocket mínimo (RFC 6455, sólo lo que hace falta) ─────────────
class _WS:
    """Lo justo para hablar CDP: texto, máscara de cliente y ping/pong.

    No se usa la librería `websockets` a propósito: esto va contra 127.0.0.1,
    sin TLS y con un único interlocutor. Ochenta líneas se leen mejor que una
    dependencia más en un proyecto que ya arrastra bastantes.
    """

    def __init__(self, url: str, timeout: float = 30.0):
        m = re.match(r"ws://([^:/]+):(\d+)(/.*)", url)
        if not m:
            raise ValueError(f"URL de WebSocket rara: {url}")
        host, puerto, camino = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, puerto), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""

        clave = base64.b64encode(bytes(random.getrandbits(8) for _ in range(16))).decode()
        peticion = (f"GET {camino} HTTP/1.1\r\n"
                    f"Host: {host}:{puerto}\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {clave}\r\n"
                    "Sec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(peticion.encode())

        cabecera = b""
        while b"\r\n\r\n" not in cabecera:
            trozo = self.sock.recv(4096)
            if not trozo:
                raise ConnectionError("el navegador cerró durante el saludo")
            cabecera += trozo
        if b"101" not in cabecera.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"saludo rechazado: {cabecera[:120]!r}")
        self._buf = cabecera.split(b"\r\n\r\n", 1)[1]

    # ── bajo nivel ──────────────────────────────────────────────────────────
    def _leer(self, n: int) -> bytes:
        while len(self._buf) < n:
            trozo = self.sock.recv(65536)
            if not trozo:
                raise ConnectionError("el navegador cerró la conexión")
            self._buf += trozo
        salida, self._buf = self._buf[:n], self._buf[n:]
        return salida

    def enviar(self, texto: str):
        datos = texto.encode()
        largo = len(datos)
        cabecera = bytearray([0x81])          # FIN + opcode texto
        mascara = bytes(random.getrandbits(8) for _ in range(4))
        if largo < 126:
            cabecera.append(0x80 | largo)
        elif largo < 65536:
            cabecera.append(0x80 | 126)
            cabecera += largo.to_bytes(2, "big")
        else:
            cabecera.append(0x80 | 127)
            cabecera += largo.to_bytes(8, "big")
        cabecera += mascara
        cuerpo = bytes(b ^ mascara[i % 4] for i, b in enumerate(datos))
        self.sock.sendall(bytes(cabecera) + cuerpo)

    def recibir(self) -> str:
        """Un mensaje de texto completo, juntando continuaciones."""
        partes = []
        while True:
            b1, b2 = self._leer(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            largo = b2 & 0x7F
            if largo == 126:
                largo = int.from_bytes(self._leer(2), "big")
            elif largo == 127:
                largo = int.from_bytes(self._leer(8), "big")
            carga = self._leer(largo) if largo else b""

            if opcode == 0x9:                  # ping -> pong
                self.sock.sendall(bytes([0x8A, 0x80]) + bytes(4))
                continue
            if opcode == 0x8:                  # close
                raise ConnectionError("el navegador cerró el canal")
            if opcode == 0xA:                  # pong suelto
                continue
            partes.append(carga)
            if fin:
                return b"".join(partes).decode("utf-8", "replace")

    def hay_datos(self, espera: float = 0.0) -> bool:
        """¿Hay algo esperando? Para vaciar eventos sin quedarse bloqueado."""
        if self._buf:
            return True
        try:
            listos, _, _ = select.select([self.sock], [], [], espera)
            return bool(listos)
        except Exception:
            return False

    def cerrar(self):
        try:
            self.sock.sendall(bytes([0x88, 0x80]) + bytes(4))
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ── el navegador ────────────────────────────────────────────────────────────
class Navegador:
    """Una pestaña gobernada por CDP."""

    def __init__(self, log=print):
        self.log = log
        self.cfg = _cfg()
        self.puerto = int(self.cfg.get("puerto") or PUERTO)
        self.perfil = self.cfg.get("perfil") or _PERFIL
        self.descargas = self.cfg.get("descargas") or _DESCARGAS
        self.proc = None
        self.ws = None
        self._id = 0
        # Lo que la página pide por detrás y lo que grita por la consola. Antes
        # esto se tiraba: los eventos de CDP llegaban por el mismo canal que las
        # respuestas y se descartaban. Aquí se guardan, y de ahí salen las dos
        # capacidades buenas: leer la API en vez del HTML, y diagnosticar una web.
        self._red = {}                       # requestId -> lo que sabemos de él
        self._consola = deque(maxlen=300)    # errores, avisos y excepciones

    # ── disponibilidad ──────────────────────────────────────────────────────
    def disponible(self) -> tuple:
        if not _binario():
            return False, ("no encuentro ningún navegador Chromium "
                           "(Chrome, Edge o Brave) en el equipo")
        return True, ""

    def _vivo(self) -> bool:
        try:
            self._http("/json/version")
            return True
        except Exception:
            return False

    # ── arranque y conexión ─────────────────────────────────────────────────
    def arrancar(self, visible: bool = None) -> tuple:
        """Levanta el navegador con el puerto de depuración. Si ya hay uno
        escuchando en ese puerto, se reaprovecha en vez de abrir otro."""
        ok, motivo = self.disponible()
        if not ok:
            return False, motivo
        if self._vivo():
            return True, "ya estaba abierto"

        binario = _binario()
        os.makedirs(self.perfil, exist_ok=True)
        os.makedirs(self.descargas, exist_ok=True)
        if visible is None:
            visible = bool(self.cfg.get("visible", True))

        args = [binario,
                f"--remote-debugging-port={self.puerto}",
                f"--user-data-dir={self.perfil}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate,MediaRouter",
                "--remote-allow-origins=*",
                "about:blank"]
        if not visible:
            args.insert(1, "--headless=new")

        try:
            self.proc = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == "nt" else 0)
        except Exception as e:
            return False, f"no pude arrancarlo: {e}"

        for _ in range(60):                    # hasta 12 s
            if self._vivo():
                self.cfg["binario"] = binario
                _guardar_cfg(self.cfg)
                return True, os.path.basename(binario)
            time.sleep(0.2)
        return False, "arrancó pero no abrió el puerto de depuración"

    def _http(self, camino: str) -> list:
        import urllib.request
        url = f"http://127.0.0.1:{self.puerto}{camino}"
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def conectar(self) -> tuple:
        """Se engancha a la pestaña visible (o abre una si no hay ninguna)."""
        if self.ws:
            return True, ""
        ok, motivo = self.arrancar()
        if not ok:
            return False, motivo
        try:
            objetivos = [t for t in self._http("/json/list")
                         if t.get("type") == "page" and
                         not (t.get("url") or "").startswith("devtools://")]
            if not objetivos:
                self._http("/json/new?about:blank")
                time.sleep(0.5)
                objetivos = [t for t in self._http("/json/list") if t.get("type") == "page"]
            if not objetivos:
                return False, "no hay ninguna pestaña a la que engancharme"
            self.ws = _WS(objetivos[0]["webSocketDebuggerUrl"])
        except Exception as e:
            return False, f"no pude conectar con la pestaña: {e}"

        # Log.enable es lo que trae los errores del navegador (CORS, mixed
        # content, CSP) que la consola de la página no ve.
        for dominio in ("Page.enable", "Runtime.enable", "DOM.enable",
                        "Network.enable", "Log.enable"):
            try:
                self.cmd(dominio)
            except Exception:
                pass
        # Las descargas van a una carpeta propia de JARVIS, no a las del señor.
        try:
            self.cmd("Browser.setDownloadBehavior",
                     {"behavior": "allow", "downloadPath": self.descargas})
        except Exception:
            pass
        return True, ""

    # ── protocolo ───────────────────────────────────────────────────────────
    def cmd(self, metodo: str, params: dict = None, timeout: float = 30.0) -> dict:
        """Manda un comando CDP y espera SU respuesta, apartando los eventos."""
        if not self.ws:
            ok, motivo = self.conectar()
            if not ok:
                raise ConnectionError(motivo)
        self._id += 1
        mio = self._id
        self.ws.enviar(json.dumps({"id": mio, "method": metodo,
                                   "params": params or {}}))
        limite = time.time() + timeout
        while time.time() < limite:
            mensaje = json.loads(self.ws.recibir())
            if mensaje.get("id") != mio:
                self._procesar(mensaje)
                continue
            if "error" in mensaje:
                raise RuntimeError(mensaje["error"].get("message", "error de CDP"))
            return mensaje.get("result") or {}
        raise TimeoutError(f"{metodo} no contestó")

    # ── eventos: lo que la página cuenta sin que se le pregunte ─────────────
    def _procesar(self, mensaje: dict):
        """Clasifica un evento de CDP. Todo lo demás se ignora en silencio."""
        metodo = mensaje.get("method") or ""
        p = mensaje.get("params") or {}

        if metodo == "Network.requestWillBeSent":
            pet = p.get("request") or {}
            self._red[p.get("requestId")] = {
                "url": pet.get("url", ""), "metodo": pet.get("method", "GET"),
                "tipo": p.get("type", ""), "estado": None, "mime": "",
                "tam": 0, "fallo": ""}
            if len(self._red) > 400:          # sólo interesa lo reciente
                for k in list(self._red)[:100]:
                    self._red.pop(k, None)
        elif metodo == "Network.responseReceived":
            r = p.get("response") or {}
            d = self._red.setdefault(p.get("requestId"), {"metodo": "GET", "tam": 0, "fallo": ""})
            d.update({"url": r.get("url", d.get("url", "")), "estado": r.get("status"),
                      "mime": r.get("mimeType", ""), "tipo": p.get("type", d.get("tipo", ""))})
        elif metodo == "Network.loadingFinished":
            d = self._red.get(p.get("requestId"))
            if d:
                d["tam"] = int(p.get("encodedDataLength") or 0)
        elif metodo == "Network.loadingFailed":
            d = self._red.setdefault(p.get("requestId"), {"metodo": "GET", "url": "", "tam": 0})
            d.update({"fallo": p.get("errorText", "falló"), "tipo": p.get("type", "")})

        elif metodo == "Runtime.consoleAPICalled":
            nivel = p.get("type", "log")
            if nivel in ("error", "warning", "assert"):
                trozos = [str(a.get("value", a.get("description", "")))[:200]
                          for a in (p.get("args") or [])]
                self._consola.append((nivel, " ".join(t for t in trozos if t)[:300]))
        elif metodo == "Runtime.exceptionThrown":
            d = (p.get("exceptionDetails") or {})
            texto = ((d.get("exception") or {}).get("description")
                     or d.get("text") or "excepción sin texto")
            self._consola.append(("excepcion", str(texto)[:300]))
        elif metodo == "Log.entryAdded":
            e = p.get("entry") or {}
            if e.get("level") in ("error", "warning"):
                self._consola.append((e.get("level"), str(e.get("text", ""))[:300]))

    def _bombear(self, segundos: float = 0.6):
        """Vacía los eventos que esperan en el canal, sin bloquearse.

        Los eventos y las respuestas viajan por el mismo WebSocket. Sin esto
        sólo se recogerían los que caen mientras hay un comando en vuelo, y la
        mitad de lo interesante llega justo después.
        """
        if not self.ws:
            return
        anterior = None
        try:
            anterior = self.ws.sock.gettimeout()
            self.ws.sock.settimeout(0.4)
            limite = time.time() + segundos
            while time.time() < limite and self.ws.hay_datos(0.05):
                try:
                    self._procesar(json.loads(self.ws.recibir()))
                except Exception:
                    break
        except Exception:
            pass
        finally:
            if anterior is not None:
                try:
                    self.ws.sock.settimeout(anterior)
                except Exception:
                    pass

    def js(self, codigo: str, timeout: float = 30.0):
        """Ejecuta JavaScript en la página y devuelve el valor."""
        r = self.cmd("Runtime.evaluate",
                     {"expression": codigo, "returnByValue": True,
                      "awaitPromise": True, "userGesture": True}, timeout)
        if r.get("exceptionDetails"):
            detalle = r["exceptionDetails"].get("text", "")
            excepcion = (r["exceptionDetails"].get("exception") or {}).get("description", "")
            raise RuntimeError(f"JavaScript falló: {excepcion or detalle}")
        return (r.get("result") or {}).get("value")

    # ── navegación ──────────────────────────────────────────────────────────
    def abrir(self, url: str, limpiar: bool = True) -> str:
        if not re.match(r"^[a-z]+://", url or "", re.I):
            url = "https://" + (url or "").strip()
        ok, motivo = self.conectar()
        if not ok:
            return f"No pude abrir el navegador, señor: {motivo}"
        if limpiar:
            # El registro de red y de consola pasa a ser el de ESTA página.
            self._red.clear()
            self._consola.clear()
        self.cmd("Page.navigate", {"url": url})
        self.esperar()
        return f"{self.titulo()} — {self.url()}"

    def esperar(self, segundos: float = None):
        """Espera a que la página se calme: documento listo y red en silencio."""
        segundos = segundos if segundos is not None else float(self.cfg.get("espera_red") or 2.0)
        limite = time.time() + max(segundos, 0.5) * 5
        estable = 0
        while time.time() < limite:
            try:
                listo = self.js("document.readyState")
            except Exception:
                listo = None
            if listo == "complete":
                estable += 1
                if estable >= 2:
                    break
            else:
                estable = 0
            time.sleep(0.25)
        time.sleep(min(segundos, 2.0))
        self._bombear()

    def url(self) -> str:
        try:
            return self.js("location.href") or ""
        except Exception:
            return ""

    def titulo(self) -> str:
        try:
            return self.js("document.title") or ""
        except Exception:
            return ""

    def atras(self) -> str:
        self.js("history.back()")
        self.esperar()
        return self.url()

    # ── lo que se ve ────────────────────────────────────────────────────────
    def texto(self, tope: int = 4000) -> str:
        """El texto visible de la página, sin menús ni scripts."""
        codigo = """(() => {
          const malos = new Set(['SCRIPT','STYLE','NOSCRIPT','SVG','HEAD']);
          const salida = [];
          const anda = (n) => {
            if (n.nodeType === 3) {
              const t = n.textContent.replace(/\\s+/g, ' ').trim();
              if (t) salida.push(t);
              return;
            }
            if (n.nodeType !== 1 || malos.has(n.tagName)) return;
            const e = getComputedStyle(n);
            if (e.display === 'none' || e.visibility === 'hidden') return;
            for (const h of n.childNodes) anda(h);
          };
          anda(document.body);
          return salida.join(' ').slice(0, %d);
        })()""" % (tope * 2)
        try:
            return (self.js(codigo) or "")[:tope]
        except Exception as e:
            return f"(no pude leer la página: {e})"

    def elementos(self, tope: int = 60) -> list:
        """Lo que se puede pulsar o rellenar, numerado.

        Esta es la pieza que hace que el modelo acierte: en vez de adivinar
        coordenadas sobre una captura, elige un número de esta lista.
        """
        codigo = """(() => {
          window.__jarvisRefs = [];
          const sel = 'a[href],button,input,select,textarea,summary,' +
                      '[role=button],[role=link],[role=tab],[role=checkbox],' +
                      '[role=menuitem],[onclick],[contenteditable=true]';
          const salida = [];
          for (const el of document.querySelectorAll(sel)) {
            const r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) continue;
            const e = getComputedStyle(el);
            if (e.visibility === 'hidden' || e.display === 'none' || e.opacity === '0') continue;
            if (el.disabled) continue;
            if (r.bottom < -200 || r.top > innerHeight + 2000) continue;
            const etiqueta = el.tagName.toLowerCase();
            const tipo = (el.type || '').toLowerCase();
            let clase = 'boton';
            if (etiqueta === 'a') clase = 'enlace';
            else if (etiqueta === 'select') clase = 'lista';
            else if (etiqueta === 'textarea') clase = 'campo';
            else if (etiqueta === 'input') {
              if (['checkbox','radio'].includes(tipo)) clase = 'casilla';
              else if (['submit','button','image','reset'].includes(tipo)) clase = 'boton';
              else clase = 'campo';
            } else if (el.isContentEditable) clase = 'campo';
            let nombre = (el.getAttribute('aria-label') || el.placeholder ||
                          el.title || el.innerText || el.value || el.name || '').trim();
            if (!nombre && el.labels && el.labels[0]) nombre = el.labels[0].innerText.trim();
            nombre = nombre.replace(/\\s+/g, ' ').slice(0, 80);
            if (!nombre && clase === 'enlace') nombre = (el.getAttribute('href') || '').slice(0, 60);
            if (!nombre) continue;
            const n = window.__jarvisRefs.length;
            window.__jarvisRefs.push(el);
            const item = {ref: n, clase: clase, nombre: nombre,
                          visible: r.top >= 0 && r.bottom <= innerHeight};
            if (clase === 'campo') {
              item.valor = (el.value || el.innerText || '').slice(0, 40);
              item.secreto = (tipo === 'password') ||
                             /pass|tarjeta|card|cvv|cvc|iban/i.test(
                               (el.name || '') + (el.id || '') + (el.autocomplete || ''));
            }
            if (clase === 'casilla') item.marcada = !!el.checked;
            salida.push(item);
            if (salida.length >= %d) break;
          }
          return salida;
        })()""" % tope
        try:
            return self.js(codigo) or []
        except Exception as e:
            self.log(f"[NAVEGADOR] No pude listar elementos: {e}")
            return []

    def mapa(self, tope: int = 60) -> str:
        """Los elementos en texto, que es como los lee el cerebro."""
        lineas = []
        for el in self.elementos(tope):
            extra = ""
            if el.get("clase") == "campo":
                if el.get("secreto"):
                    extra = " (secreto: no lo relleno yo)"
                elif el.get("valor"):
                    extra = f" (= «{el['valor']}»)"
                else:
                    extra = " (vacío)"
            elif el.get("clase") == "casilla":
                extra = " (marcada)" if el.get("marcada") else " (sin marcar)"
            lineas.append(f"[{el['ref']}] {el['clase']:7} «{el['nombre']}»{extra}")
        return "\n".join(lineas) or "(no hay nada con lo que interactuar)"

    # ── la API que hay detrás de la página ──────────────────────────────────
    def red(self, patron: str = "", solo_datos: bool = True) -> list:
        """Las peticiones que ha hecho la página.

        Con `solo_datos` se queda con lo que trae información (JSON y similares)
        y tira imágenes, fuentes, hojas de estilo y scripts, que es ruido.
        """
        self._bombear()
        rx = re.compile(patron, re.I) if patron else None
        salida = []
        for rid, d in self._red.items():
            url = d.get("url") or ""
            if not url or url.startswith("data:"):
                continue
            if rx and not rx.search(url):
                continue
            if solo_datos:
                mime = (d.get("mime") or "").lower()
                tipo = (d.get("tipo") or "").lower()
                # Los SVG son «image/svg+xml»: sin esta línea, un simple
                # «xml in mime» llenaba la lista de iconos.
                if (mime.startswith(("image/", "font/", "video/", "audio/", "text/css"))
                        or tipo in ("image", "font", "stylesheet", "media", "script")):
                    continue
                if not ("json" in mime or "xml" in mime or tipo in ("xhr", "fetch")):
                    continue
            salida.append(dict(d, id=rid))
        return salida

    def datos(self, patron: str = "", indice: int = 0, tope: int = 6000) -> str:
        """El CUERPO de una respuesta: el JSON que llena la página.

        Esto es lo que cambia el juego. La tabla de movimientos, el listado de
        pedidos o los horarios llegan casi siempre en un JSON limpio; leer ese
        JSON es exacto y gratis, mientras que rascar el texto renderizado es
        adivinar y se rompe con cada rediseño.
        """
        candidatos = self.red(patron, solo_datos=True)
        if not candidatos:
            sin_filtro = self.red("", solo_datos=True)
            if sin_filtro:
                urls = "\n".join(f"  · {c['url'][:110]}" for c in sin_filtro[:10])
                return (f"Ninguna petición encaja con «{patron}», señor. "
                        f"Esta página ha pedido esto:\n{urls}")
            return ("Esta página no pide datos por detrás, señor: lo trae todo "
                    "en el HTML. Ahí hay que leer el texto.")
        # Las grandes suelen ser las que traen la información de verdad.
        candidatos.sort(key=lambda c: c.get("tam") or 0, reverse=True)
        elegido = candidatos[min(indice, len(candidatos) - 1)]
        try:
            r = self.cmd("Network.getResponseBody", {"requestId": elegido["id"]})
        except Exception as e:
            return (f"No pude recuperar el cuerpo de {elegido['url'][:80]}, señor: {e}. "
                    "El navegador ya lo habrá soltado; recargue y lo pillo al vuelo.")
        cuerpo = r.get("body") or ""
        if r.get("base64Encoded"):
            try:
                cuerpo = base64.b64decode(cuerpo).decode("utf-8", "replace")
            except Exception:
                return "La respuesta es binaria, señor; no es un JSON que pueda leerle."
        cabecera = (f"{elegido.get('metodo', 'GET')} {elegido['url'][:120]}\n"
                    f"({elegido.get('estado')}, {elegido.get('mime', '')}, "
                    f"{elegido.get('tam', 0)} bytes"
                    + (f", {len(candidatos)} candidatas más" if len(candidatos) > 1 else "")
                    + ")\n\n")
        try:                                   # si es JSON, se sirve legible
            cuerpo = json.dumps(json.loads(cuerpo), ensure_ascii=False, indent=1)
        except Exception:
            pass
        return cabecera + cuerpo[:tope] + ("\n… (cortado)" if len(cuerpo) > tope else "")

    # ── qué está roto en esta web ───────────────────────────────────────────
    def consola(self) -> list:
        """Errores, avisos y excepciones que ha soltado la página."""
        self._bombear()
        return list(self._consola)

    def diagnostico(self, tope: int = 12) -> str:
        """Informe de salud de la página: consola, excepciones y red rota.

        Es lo que uno mira a mano en las herramientas de desarrollo, pero
        contado en una respuesta. Sirve para la web del señor y para entender
        por qué una web ajena no hace lo que debería.
        """
        self._bombear(1.0)
        lineas = []

        fallos = [d for d in self._red.values() if d.get("fallo")]
        rotas = [d for d in self._red.values()
                 if isinstance(d.get("estado"), int) and d["estado"] >= 400]

        consola = self.consola()
        errores = [c for c in consola if c[0] in ("error", "excepcion")]
        avisos = [c for c in consola if c[0] == "warning"]

        if errores:
            lineas.append(f"Errores de JavaScript ({len(errores)}):")
            for nivel, texto in errores[:tope]:
                lineas.append(f"  · [{nivel}] {texto}")
        if rotas:
            lineas.append(f"Peticiones con error ({len(rotas)}):")
            for d in rotas[:tope]:
                lineas.append(f"  · {d.get('estado')} {d.get('metodo', '')} {d.get('url', '')[:100]}")
        if fallos:
            lineas.append(f"Peticiones que no llegaron ({len(fallos)}):")
            for d in fallos[:tope]:
                lineas.append(f"  · {d.get('fallo')} — {d.get('url', '')[:100]}")
        if avisos and not (errores or rotas or fallos):
            lineas.append(f"Sólo avisos ({len(avisos)}):")
            for _n, texto in avisos[:tope]:
                lineas.append(f"  · {texto}")

        n = len(self._red)
        cuenta = "1 petición" if n == 1 else f"{n} peticiones"
        if not lineas:
            return (f"{self.titulo()} — {self.url()}\n"
                    f"Limpia, señor: {cuenta}, ni un error de consola ni una rota.")
        return (f"{self.titulo()} — {self.url()}\n"
                f"{cuenta}. Esto es lo que va mal:\n\n" + "\n".join(lineas))

    def _rect(self, ref: int):
        return self.js(f"""(() => {{
          const el = (window.__jarvisRefs || [])[{int(ref)}];
          if (!el) return null;
          el.scrollIntoView({{block:'center', inline:'center', behavior:'instant'}});
          const r = el.getBoundingClientRect();
          return {{x: r.left + r.width/2, y: r.top + r.height/2,
                   nombre: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0,80)}};
        }})()""")

    # ── actuar ──────────────────────────────────────────────────────────────
    def clic(self, ref: int, seco: bool = False) -> str:
        datos = self._rect(ref)
        if not datos:
            return f"No existe el elemento [{ref}], señor. La página habrá cambiado."
        nombre = datos.get("nombre") or f"[{ref}]"

        if _PROHIBIDO_PULSAR.search(nombre):
            return (f"Me detengo, señor: «{nombre}» es un botón de pago o compra. "
                    "Eso lo pulsa usted; yo no gasto su dinero.")
        if seco:
            return f"(ensayo) Pulsaría «{nombre}»."

        time.sleep(0.15)
        x, y = float(datos["x"]), float(datos["y"])
        for tipo in ("mousePressed", "mouseReleased"):
            self.cmd("Input.dispatchMouseEvent",
                     {"type": tipo, "x": x, "y": y, "button": "left",
                      "clickCount": 1, "buttons": 1 if tipo == "mousePressed" else 0})
        self.esperar(1.0)
        return f"Pulsado «{nombre}»."

    def escribir(self, ref: int, texto: str, enviar: bool = False,
                 seco: bool = False) -> str:
        info = self.js(f"""(() => {{
          const el = (window.__jarvisRefs || [])[{int(ref)}];
          if (!el) return null;
          const t = (el.type || '').toLowerCase();
          return {{secreto: t === 'password' ||
                    /pass|tarjeta|card|cvv|cvc|iban/i.test(
                      (el.name||'')+(el.id||'')+(el.autocomplete||'')+(el.placeholder||'')),
                   nombre: (el.getAttribute('aria-label')||el.placeholder||el.name||'').slice(0,80)}};
        }})()""")
        if not info:
            return f"No existe el campo [{ref}], señor."
        nombre = info.get("nombre") or f"[{ref}]"

        if info.get("secreto") or _PROHIBIDO_ESCRIBIR.search(nombre):
            return (f"No escribo en «{nombre}», señor: es una contraseña o un dato "
                    "bancario. Ese campo lo rellena usted; yo sigo desde el siguiente paso.")
        if seco:
            return f"(ensayo) Escribiría «{texto}» en «{nombre}»" + (" y pulsaría Intro." if enviar else ".")

        self.js(f"""(() => {{
          const el = window.__jarvisRefs[{int(ref)}];
          el.focus();
          if ('value' in el) {{ el.value = ''; }} else {{ el.textContent = ''; }}
        }})()""")
        self.cmd("Input.insertText", {"text": texto})
        self.js(f"""(() => {{
          const el = window.__jarvisRefs[{int(ref)}];
          el.dispatchEvent(new Event('input', {{bubbles: true}}));
          el.dispatchEvent(new Event('change', {{bubbles: true}}));
        }})()""")
        if enviar:
            self.pulsar("Enter")
        return f"Escrito «{texto}» en «{nombre}»" + (" y enviado." if enviar else ".")

    def pulsar(self, tecla: str) -> str:
        mapa = {"enter": ("Enter", 13), "intro": ("Enter", 13), "tab": ("Tab", 9),
                "escape": ("Escape", 27), "esc": ("Escape", 27),
                "abajo": ("ArrowDown", 40), "arriba": ("ArrowUp", 38),
                "backspace": ("Backspace", 8)}
        nombre, codigo = mapa.get((tecla or "").lower(), ("Enter", 13))
        for tipo in ("rawKeyDown", "keyUp"):
            self.cmd("Input.dispatchKeyEvent",
                     {"type": tipo, "key": nombre, "code": nombre,
                      "windowsVirtualKeyCode": codigo, "nativeVirtualKeyCode": codigo})
        self.esperar(1.0)
        return f"Pulsada la tecla {nombre}."

    def desplazar(self, hacia: str = "abajo", cantidad: int = 600) -> str:
        signo = -1 if (hacia or "").lower() in ("arriba", "up") else 1
        self.js(f"window.scrollBy({{top: {signo * int(cantidad)}, behavior: 'instant'}})")
        time.sleep(0.4)
        return f"Desplazado hacia {hacia}."

    def captura(self, nombre: str = "") -> str:
        """Guarda un PNG de la página. Para el informe, no para decidir."""
        try:
            r = self.cmd("Page.captureScreenshot", {"format": "png"})
            datos = base64.b64decode(r.get("data") or "")
        except Exception as e:
            return f"(no pude capturar: {e})"
        carpeta = os.path.join(_BASE, "Navegador", "Capturas",
                               time.strftime("%Y-%m-%d"))
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, (nombre or time.strftime("%H%M%S")) + ".png")
        with open(ruta, "wb") as f:
            f.write(datos)
        return ruta

    def cerrar(self):
        """Cierra el navegador de JARVIS entero.

        `terminate()` a secas no basta: Chromium reparte el trabajo en un
        montón de procesos hijos y matar al padre deja once vivos (medido).
        Por eso primero se le pide al propio navegador que se cierre —
        `Browser.close`, que arrastra a toda su prole— y sólo si no obedece se
        recurre a la fuerza, esta vez con el árbol entero.

        Sólo muere el navegador del puerto de depuración, que es el del perfil
        de JARVIS. El navegador diario del señor no lo tiene abierto y no se
        entera de nada.
        """
        try:
            if self.ws:
                self.cmd("Browser.close", timeout=5)
        except Exception:
            pass
        if self.ws:
            self.ws.cerrar()
            self.ws = None

        if self.proc:
            try:
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                                       capture_output=True,
                                       creationflags=0x08000000)
                    else:
                        self.proc.terminate()
                except Exception:
                    pass
            self.proc = None


# ── una sola instancia, como el resto de puentes de la casa ─────────────────
_NAVEGADOR = None


def obtener(log=print) -> Navegador:
    global _NAVEGADOR
    if _NAVEGADOR is None:
        _NAVEGADOR = Navegador(log=log)
    return _NAVEGADOR


# ── el bucle: mirar, decidir, actuar, comprobar ─────────────────────────────
PROMPT = """Manejas un navegador para cumplir un encargo. En cada turno ves la
dirección, el título, el texto visible y la LISTA NUMERADA de lo que se puede
pulsar o rellenar. Respondes SOLO con un JSON, sin explicaciones:

{"accion": "abrir|clic|escribir|tecla|desplazar|atras|esperar|listo|imposible",
 "ref": <número de la lista, para clic/escribir>,
 "url": "<sólo para abrir>",
 "texto": "<lo que se escribe, o la tecla>",
 "enviar": true|false,
 "razon": "<una frase corta>"}

Reglas:
- "ref" SIEMPRE sale de la lista de este turno. Los números cambian cada vez.
- Al escribir en un buscador pon "enviar": true, o la búsqueda no se lanza.
- Mira "Ya has hecho": NO repitas un paso que ya diste; si no surtió efecto,
  prueba otra cosa.
- "listo" cuando el encargo ya esté cumplido; pon en "razon" el resultado
  concreto que has encontrado (el dato, el número, la confirmación).
- "imposible" si hace falta contraseña, pago, o un dato que no tienes.
- Acepta los avisos de cookies eligiendo siempre la opción que RECHAZA lo no
  esencial si existe.
- No inventes: si el dato no está en el texto, sigue navegando o di imposible.

Encargo: {objetivo}
"""


def navegar(objetivo: str, core=None, max_pasos: int = MAX_PASOS,
            seco: bool = False, url_inicial: str = "", log=print) -> str:
    """Persigue un encargo en la web. `seco=True` narra sin tocar nada."""
    nav = obtener(log=log)
    ok, motivo = nav.disponible()
    if not ok:
        return f"No puedo manejar el navegador, señor: {motivo}."

    ok, motivo = nav.conectar()
    if not ok:
        return f"No pude enchufarme al navegador, señor: {motivo}."

    if url_inicial:
        nav.abrir(url_inicial)

    pasos = []
    ensayo = []
    perdidos = 0
    for paso in range(1, max_pasos + 1):
        # Sin memoria de lo ya hecho, el modelo repite el mismo clic en bucle.
        historial = ("\n".join(pasos[-3:]) or "(nada todavía)")
        vista = (f"Dirección: {nav.url()}\n"
                 f"Título: {nav.titulo()}\n\n"
                 f"Ya has hecho:\n{historial}\n\n"
                 f"Texto visible:\n{nav.texto(1800)}\n\n"
                 f"Elementos:\n{nav.mapa()}")

        crudo = _preguntar(core, PROMPT.replace("{objetivo}", objetivo), vista, log)
        accion = _leer_json(crudo)
        if accion is None:
            perdidos += 1
            if perdidos >= 3:
                return (f"Me perdí en el paso {paso}, señor: el cerebro no devolvió "
                        "una acción que pueda ejecutar, y van tres seguidas."
                        + (f"\nLo último que hice: {pasos[-1]}" if pasos else ""))
            log(f"[NAVEGADOR] Paso {paso}: sin acción legible, vuelvo a mirar.")
            nav.esperar(1.0)
            continue
        perdidos = 0

        tipo = (accion.get("accion") or "").lower()
        razon = accion.get("razon", "")
        log(f"[NAVEGADOR] Paso {paso}: {tipo} ({razon})")

        if tipo == "listo":
            _anotar(core, nav, paso, accion, "cumplido", log)
            cierre = f"Hecho, señor. {razon}" if razon else "Hecho, señor."
            return cierre + f"\n(Quedó en {nav.url()})"
        if tipo == "imposible":
            _anotar(core, nav, paso, accion, "imposible", log)
            return f"No puedo terminarlo, señor: {razon}"

        if seco:
            detalle = _ejecutar(nav, accion, seco=True)
            ensayo.append(f"{paso}. {detalle if detalle.startswith('(ensayo)') else tipo} "
                          f"— {razon}".replace("(ensayo) ", ""))
            # En ensayo sólo se ejecuta lo que no cambia nada: mirar y moverse.
            # Un clic no, y por eso el ensayo se para ahí: lo que venga después
            # depende de una página que todavía no existe, y prometerlo sería
            # inventar.
            if tipo in ("desplazar", "esperar", "abrir", "atras"):
                continue
            break

        resultado = _ejecutar(nav, accion, seco=False)
        pasos.append(f"{paso}. {resultado}")
        _anotar(core, nav, paso, accion, resultado, log)
        # Si un guardarraíl ha parado el paso, no tiene sentido seguir a ciegas.
        if resultado.startswith("Me detengo") or resultado.startswith("No escribo"):
            return resultado + "\n\nCuando lo haga usted, dígame «sigue» y retomo."

    if seco:
        return _cierre_ensayo(ensayo, nav)
    return (f"He dado {max_pasos} pasos sin cerrarlo, señor. Me detengo para no "
            f"seguir a ciegas.\n" + "\n".join(pasos[-4:]))


def _cierre_ensayo(ensayo: list, nav: Navegador) -> str:
    """El informe del ensayo, sin prometer más de lo que se puede saber.

    Un ensayo web honesto llega hasta la primera acción con consecuencias. Lo
    que venga después depende de una página que aún no existe, y enumerarla
    sería inventársela.
    """
    if not ensayo:
        return "En el ensayo no me hizo falta tocar nada, señor."
    cuerpo = "\n".join(ensayo)
    return ("Esto es lo que haría, señor:\n" + cuerpo +
            f"\n\nAhí me paro: estoy en {nav.url()} y de ese paso en adelante "
            "depende de lo que salga en pantalla. Si le parece bien, dígamelo y "
            "lo hago de verdad.")


def _ejecutar(nav: Navegador, accion: dict, seco: bool) -> str:
    tipo = (accion.get("accion") or "").lower()
    try:
        if tipo == "abrir":
            return nav.abrir(accion.get("url") or "")
        if tipo == "clic":
            return nav.clic(int(accion.get("ref", -1)), seco=seco)
        if tipo == "escribir":
            return nav.escribir(int(accion.get("ref", -1)), accion.get("texto") or "",
                                enviar=bool(accion.get("enviar")), seco=seco)
        if tipo == "tecla":
            return nav.pulsar(accion.get("texto") or "enter")
        if tipo == "desplazar":
            return nav.desplazar(accion.get("texto") or "abajo")
        if tipo == "atras":
            return f"Vuelto a {nav.atras()}"
        if tipo == "esperar":
            nav.esperar(2.0)
            return "Esperado."
        return f"No sé hacer «{tipo}»."
    except Exception as e:
        return f"error: {e}"


def _preguntar(core, sistema: str, vista: str, log) -> str:
    """Una vuelta del cerebro. Texto, no visión: es diez veces más barato.

    Qwen razona en voz alta entre <think>, y cuando el razonamiento se come los
    tokens la respuesta llega sin JSON. Por eso hay un segundo intento con la
    orden de contestar a bocajarro: es más barato que perder el paso entero.
    """
    from proveedor_claude import cliente as OpenAI, sin_pensamiento
    try:
        _n, url, modelo, clave = core._proveedores()[0]
        cliente = OpenAI(base_url=url, api_key=clave)
    except Exception as e:
        log(f"[NAVEGADOR] No hay cerebro al que preguntar: {e}")
        return ""

    for intento, (tope, empuje) in enumerate(
            ((700, ""), (400, "\n\nResponde SOLO con el JSON, sin razonar antes."))):
        try:
            r = cliente.chat.completions.create(
                model=modelo, temperature=0.1, max_tokens=tope,
                messages=[{"role": "system", "content": sistema + empuje},
                          {"role": "user", "content": vista}])
            texto = sin_pensamiento((r.choices[0].message.content or "")).strip()
            if _leer_json(texto) is not None:
                return texto
            log(f"[NAVEGADOR] Sin JSON en el intento {intento + 1}; reintento.")
        except Exception as e:
            log(f"[NAVEGADOR] El cerebro no contestó: {e}")
            return ""
    return ""


def _leer_json(texto: str):
    """Saca el JSON aunque el modelo lo envuelva en explicaciones o en ```."""
    if not texto:
        return None
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        try:
            return json.loads(m.group(0).replace("'", '"'))
        except Exception:
            return None


def _anotar(core, nav, paso, accion, resultado, log):
    try:
        from storage import get_storage
        get_storage(log=log).registrar_accion(
            origen="navegador", orden=str(accion.get("razon", ""))[:120],
            comando=json.dumps(accion, ensure_ascii=False)[:300],
            ok=not str(resultado).startswith("error"),
            detalle=f"{nav.url()[:120]} | {str(resultado)[:120]}",
            agente=getattr(core, "nombre_agente", "JARVIS"))
    except Exception:
        pass


# ── atajos para el resto del proyecto ───────────────────────────────────────
def abrir(url: str, log=print) -> str:
    return obtener(log=log).abrir(url)


def mirar(pregunta: str = "", log=print) -> str:
    """Qué hay ahora mismo en la pestaña. Lectura pura, sin tocar nada."""
    nav = obtener(log=log)
    ok, motivo = nav.conectar()
    if not ok:
        return f"No hay navegador al que mirar, señor: {motivo}"
    return (f"{nav.titulo()} — {nav.url()}\n\n{nav.texto(2000)}\n\n"
            f"Se puede pulsar:\n{nav.mapa(30)}")


def datos(patron: str = "", indice: int = 0, log=print) -> str:
    """El JSON que la página ha pedido por detrás, en vez del texto rascado."""
    nav = obtener(log=log)
    ok, motivo = nav.conectar()
    if not ok:
        return f"No hay navegador al que preguntar, señor: {motivo}"
    return nav.datos(patron, indice)


def diagnosticar(url: str = "", log=print) -> str:
    """Abre (o recarga) una web y cuenta qué está roto.

    La recarga no es un capricho: los errores de JavaScript y las peticiones
    rotas ocurren AL CARGAR. Si nos enganchamos a una página ya cargada, el
    registro está vacío y parecería sana estando enferma.
    """
    nav = obtener(log=log)
    ok, motivo = nav.conectar()
    if not ok:
        return f"No pude abrir el navegador, señor: {motivo}"
    if url:
        nav.abrir(url)
    else:
        nav._red.clear()
        nav._consola.clear()
        try:
            nav.cmd("Page.reload", {"ignoreCache": True})
        except Exception:
            pass
        nav.esperar()
    return nav.diagnostico()


def estado(log=print) -> str:
    nav = obtener(log=log)
    ok, motivo = nav.disponible()
    if not ok:
        return f"Navegador: no disponible ({motivo})."
    binario = os.path.basename(_binario())
    if not nav._vivo():
        return f"Navegador: {binario} listo, sin arrancar. Perfil propio en {nav.perfil}."
    return (f"Navegador: {binario} en marcha (puerto {nav.puerto}).\n"
            f"Pestaña: {nav.titulo()} — {nav.url()}\n"
            f"Descargas a {nav.descargas}")


if __name__ == "__main__":
    print(estado())
