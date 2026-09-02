#!/usr/bin/env python3
"""
conectores.py - Conectores de JARVIS y ULTRON a servicios externos.
=====================================================================
Permite pedir por voz o texto cosas como:

  "Jarvis, agenda una reunion con Marta manana a las 5"
  "apunta en el calendario dentista el jueves a las 10 y media"
  "que tengo manana"  /  "que tengo esta semana"
  "cancela la cita del dentista"

Como funciona
-------------
Los servicios viven en servidores MCP que el proyecto ya tiene
(mcp_servers/), cada uno en su puerto. Este modulo es la capa que
entiende el espanol, decide a que conector llamar y AVISA SIEMPRE de lo
que se le pidio y de lo que se hizo.

  usuario -> Conectores.handle() -> MCPClient -> servidor MCP -> servicio

Anadir un conector nuevo
------------------------
1. Un servidor MCP en mcp_servers/ que exponga /call, /health y /tools.
2. Registrarlo en SERVIDORES (nombre -> puerto).
3. Una subclase de Conector con su handle(); anadirla en Conectores._cargar.

La notificacion no es opcional: toda accion que cambie algo fuera del PC
se confirma por todos los canales disponibles (voz, HUD/movil y Telegram).
"""
import json
import os
import re
import unicodedata
import urllib.request
from datetime import datetime, timedelta

# Puerto de cada servidor MCP (los mismos que arranca start_jarvis.bat).
SERVIDORES = {
    "ha": int(os.getenv("HA_MCP_PORT", "8001")),
    "calendar": int(os.getenv("CAL_MCP_PORT", "8002")),
    "android": int(os.getenv("ANDROID_MCP_PORT", "8003")),
}

ZONA = os.getenv("JARVIS_TIMEZONE", "Europe/Madrid")


def _norm(s: str) -> str:
    """Minusculas sin tildes, como hace el resto del proyecto."""
    n = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in n if unicodedata.category(c) != "Mn")


# ── NOTIFICACION ─────────────────────────────────────────────────────────────
class Notificador:
    """Avisa por todos los canales a la vez; ninguno es obligatorio.

    notify: callback del nucleo (acaba en la cola de voz).
    El push al HUD/movil va por /notify del servidor Flask, y el aviso de
    Telegram por el chat guardado del dueno.
    """

    def __init__(self, notify=None, log=print, safe=False):
        self.notify = notify
        self.log = log
        self.safe = safe

    def avisar(self, pedido: str, resultado: str, detalle: str = ""):
        """Notifica QUE se pidio y QUE se hizo. Devuelve el texto del aviso."""
        texto = f"{resultado}"
        if detalle:
            texto += f" {detalle}"
        completo = f"{texto} (me pidió: «{(pedido or '').strip()[:120]}»)"
        self.log(f"[CONECTORES] {completo}")
        if self.safe:
            return texto
        for canal in (self._voz, self._hud, self._telegram):
            try:
                canal(completo)
            except Exception as e:
                self.log(f"[CONECTORES] Aviso por {canal.__name__} fallo: {e}")
        return texto

    def _voz(self, texto: str):
        if self.notify:
            self.notify(texto)

    def _hud(self, texto: str):
        import jarvis_config
        req = urllib.request.Request(
            jarvis_config.url_flask("/notify"),
            data=json.dumps({"text": texto}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2.0)

    def _telegram(self, texto: str):
        import jarvis_config
        cfg = json.load(open(jarvis_config.TELEGRAM_JSON, encoding="utf-8-sig"))
        token, chat = cfg.get("token"), cfg.get("chat_id")
        if not token or not chat:
            return
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": texto}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5.0)


# ── BASE ─────────────────────────────────────────────────────────────────────
class Conector:
    """Un servicio externo detras de un servidor MCP."""

    nombre = "base"
    servicio = "servicio"

    def __init__(self, cliente, notificador, log=print):
        self.cliente = cliente
        self.avisos = notificador
        self.log = log

    def disponible(self) -> bool:
        try:
            return self.cliente.health_check(self.nombre)
        except Exception:
            return False

    def llamar(self, herramienta: str, argumentos: dict):
        r = self.cliente.call(self.nombre, herramienta, argumentos)
        # Los servidores del proyecto devuelven {"result": ...} o el valor suelto.
        if isinstance(r, dict) and "result" in r:
            return r["result"]
        return r

    def lista(self, herramienta: str, argumentos: dict) -> list:
        """Como llamar(), pero garantiza una lista.

        Un servidor que responda con otra forma (un dict, None, un error) no
        debe reventar el conector y mandar la orden al LLM sin avisar.
        """
        r = self.llamar(herramienta, argumentos)
        if isinstance(r, list):
            return r
        if isinstance(r, dict):
            for clave in ("items", "events", "eventos"):
                if isinstance(r.get(clave), list):
                    return r[clave]
            return [r] if r.get("id") else []
        if r is None:
            return []
        self.log(f"[CONECTORES] {herramienta} devolvio {type(r).__name__}, esperaba una lista")
        return []

    def handle(self, t: str, orig: str):
        raise NotImplementedError


# ── GOOGLE CALENDAR ──────────────────────────────────────────────────────────
class ConectorCalendar(Conector):
    nombre = "calendar"
    servicio = "Google Calendar"

    # "agenda / apunta / ponme / mete / reserva ... [asunto] ... [cuando]"
    CREAR = re.compile(
        r"\b(?:agenda(?:me)?|agendar|apunta(?:me)?|apuntar|anota(?:me)?|"
        r"pon(?:me|ga)?|mete(?:me)?|meter|reserva(?:me)?|crea(?:me)?|"
        r"programa(?:me)?|add)\b")
    # Palabras que atan la orden a Google Calendar y no a la agenda LOCAL que
    # ya trae jarvis_skills. Deliberadamente NO incluye el verbo "agenda":
    # "agendame algo" a secas sigue yendo a la agenda local de siempre, y solo
    # se va a Google cuando el senor nombra el calendario, una cita, una
    # reunion o un evento. Asi el conector no le roba ordenes a lo que ya
    # funcionaba.
    CALENDARIO = re.compile(
        r"\b(?:calendario|google\s+calendar|cita|citas|reunion|reuniones|"
        r"evento|eventos)\b")
    # El sustantivo puede ir en medio: "que CITAS tengo manana".
    CONSULTAR = re.compile(
        r"\b(?:que\s+(?:\w+\s+){0,2}tengo|que\s+hay|que\s+me\s+toca|tengo\s+algo|"
        r"cuantas?\s+(?:\w+\s+){0,2}tengo|"
        r"cuales\s+son\s+mis|dime\s+(?:mi|mis|que)|mira\s+mi|consulta\s+mi|ver\s+mi)\b")
    BORRAR = re.compile(r"\b(?:cancela(?:me)?|cancelar|borra(?:me)?|borrar|"
                        r"elimina(?:me)?|eliminar|quita(?:me)?|anula)\b")

    def handle(self, t: str, orig: str):
        if not self.CALENDARIO.search(t):
            return None
        if self.CONSULTAR.search(t):
            return self._consultar(t, orig)
        if self.BORRAR.search(t):
            return self._borrar(t, orig)
        if self.CREAR.search(t):
            return self._crear(t, orig)
        return None

    # ── crear ────────────────────────────────────────────────────────────────
    def _crear(self, t: str, orig: str):
        cuando, asunto = self._cuando_y_asunto(t, orig)
        if not asunto:
            return ("Señor, ¿qué debo agendar exactamente? Dígame por ejemplo "
                    "«agenda dentista mañana a las 10».")
        if cuando is None:
            return (f"Señor, ¿para cuándo agendo «{asunto}»? Dígame el día y la hora, "
                    "por ejemplo «mañana a las 5».")
        fin = cuando + timedelta(hours=1)
        try:
            ev = self.llamar("cal_create_event", {
                "summary": asunto,
                "start": cuando.strftime("%Y-%m-%dT%H:%M:%S"),
                "end": fin.strftime("%Y-%m-%dT%H:%M:%S"),
                "description": f"Creado por JARVIS desde: «{orig.strip()[:200]}»",
            })
        except Exception as e:
            self.log(f"[CONECTORES] cal_create_event fallo: {e}")
            return self._sin_servicio(e)
        enlace = (ev or {}).get("htmlLink", "") if isinstance(ev, dict) else ""
        return self.avisos.avisar(
            orig,
            f"Agendado, señor: «{asunto}» el {self._bonita(cuando)}.",
            f"Está en su {self.servicio}." + (f" {enlace}" if enlace else ""))

    # Trozos que hay que sacar del titulo: el verbo, las muletillas de
    # calendario y la parte temporal. Con tildes opcionales porque el titulo
    # se recorta del texto ORIGINAL, para no perder mayusculas ni acentos
    # ("Reunión con Marta", no "reunion con marta").
    _RUIDO = [
        r"\bjarvis\b", r"\bultron\b",
        r"\b(?:agenda|agéndame|agendame|agendar|apunta|apúntame|apuntame|apuntar|"
        r"anota|anótame|anotame|pon|ponme|ponga|mete|méteme|meteme|meter|reserva|"
        r"resérvame|reservame|crea|créame|creame|programa|prográmame|programame)\b",
        r"\ben\s+(?:el|mi|la)?\s*(?:google\s+)?calendario?\b",
        r"\bgoogle\s+calendar\b",
        r"\bpasado\s+ma[nñ]ana\b", r"\bma[nñ]ana\b", r"\bhoy\b",
        r"\besta\s+(?:noche|tarde|ma[nñ]ana)\b",
        r"\b(?:el\s+)?(?:pr[oó]ximo|siguiente)\s+\w+\b",
        r"\b(?:el\s+)?(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)"
        r"(?:\s+que\s+viene)?\b",
        r"\bel\s+\d{1,2}\s+de\s+[a-zá-úñ]+\b",
        r"\ba\s+las?\s+[\wá-ú]{1,9}(?:[:.]\d{2})?"
        r"(?:\s+y\s+(?:media|cuarto))?(?:\s+menos\s+cuarto)?"
        r"(?:\s*(?:horas?|hs?|am|pm))?"
        r"(?:\s+de\s+la\s+(?:ma[nñ]ana|tarde|noche|madrugada))?"
        r"(?:\s+del\s+mediod[ií]a)?\b",
        r"\b(?:al\s+)?mediod[ií]a\b",
        r"\b(?:dentro\s+de|en)\s+\d{1,3}\s*(?:minutos?|horas?|d[ií]as?|semanas?)\b",
        r"\bpara\b",
    ]

    # ── fecha y hora en espanol ──────────────────────────────────────────────
    # Parser propio. El de jarvis_skills (_fecha_agenda) no entiende "de la
    # tarde", ni las horas escritas con letras, ni "y media": "a las 6 de la
    # tarde" le salia 06:00, "a las seis" caia al valor por defecto de las
    # 09:00 y "8 y media de la noche" se quedaba en 08:00.
    _PALABRA_HORA = {
        "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
        "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    }
    _DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes",
                    "sabado", "domingo"]
    _MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
              "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

    @classmethod
    def _hora_de(cls, t: str):
        """(hora, minuto) en formato 24h, o None si no se menciona ninguna."""
        # "a las 17:30", "a las 17.30"
        m = re.search(r"a\s+las?\s+(\d{1,2})[:.](\d{2})", t)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if h > 23 or mi > 59:
                return None
            return cls._ajustar_franja(h, mi, t, explicito=True)
        # "a las 6", "a las seis", "a las 6 y media", "a las 8 menos cuarto"
        m = re.search(r"a\s+las?\s+(\d{1,2}|" + "|".join(cls._PALABRA_HORA) + r")\b", t)
        if not m:
            if re.search(r"\b(?:al\s+)?mediodia\b", t):
                return (14, 0) if re.search(r"tarde", t) else (12, 0)
            return None
        crudo = m.group(1)
        h = int(crudo) if crudo.isdigit() else cls._PALABRA_HORA[crudo]
        if h > 23:
            return None
        mi = 0
        cola = t[m.end():m.end() + 30]
        if re.search(r"^\s+y\s+media", cola):
            mi = 30
        elif re.search(r"^\s+y\s+cuarto", cola):
            mi = 15
        elif re.search(r"^\s+menos\s+cuarto", cola):
            h, mi = (h - 1) % 24, 45
        return cls._ajustar_franja(h, mi, t, explicito=False)

    @staticmethod
    def _ajustar_franja(h: int, mi: int, t: str, explicito: bool):
        """Convierte a 24h segun «de la tarde/noche/manana/madrugada» o am/pm."""
        # "esta noche"/"esta tarde" tambien fijan la franja, no solo
        # "de la tarde": "esta noche a las 9" son las 21:00.
        tarde = bool(re.search(r"de\s+la\s+(?:tarde|noche)|\bpm\b|"
                               r"esta\s+(?:tarde|noche)|\bal\s+atardecer\b", t))
        manana = bool(re.search(r"de\s+la\s+(?:manana|madrugada)|\bam\b|"
                                r"esta\s+manana", t))
        if tarde and h < 12:
            h += 12
        elif manana and h == 12:
            h = 0
        return h % 24, mi

    @classmethod
    def _dia_de(cls, t: str, ahora):
        """Fecha (sin hora) mencionada en el texto, o None."""
        # Quitar la franja horaria primero: "hoy a las 11 DE LA MANANA" contiene
        # la palabra "manana" y se agendaba para el dia siguiente.
        t = re.sub(r"de\s+la\s+(?:manana|tarde|noche|madrugada)", " ", t)
        if re.search(r"pasado\s+manana", t):
            return (ahora + timedelta(days=2)).date()
        if re.search(r"\bmanana\b", t):
            return (ahora + timedelta(days=1)).date()
        if re.search(r"\bhoy\b|\besta\s+(?:noche|tarde)\b", t):
            return ahora.date()
        m = re.search(r"(?:el\s+|este\s+|proximo\s+|el\s+proximo\s+)?("
                      + "|".join(cls._DIAS_SEMANA) + r")(\s+que\s+viene)?", t)
        if m:
            idx = cls._DIAS_SEMANA.index(m.group(1))
            delta = (idx - ahora.weekday()) % 7
            # "el jueves" dicho un jueves = el que viene, no hoy.
            if delta == 0 or m.group(2) or "proximo" in t:
                delta = delta or 7
                if m.group(2) or re.search(r"proximo", t):
                    delta = delta if delta else 7
            return (ahora + timedelta(days=delta)).date()
        m = re.search(r"(?:el\s+)?(\d{1,2})\s+de\s+([a-z]+)", t)
        if m and m.group(2) in cls._MESES:
            dia, mes = int(m.group(1)), cls._MESES.index(m.group(2)) + 1
            try:
                f = ahora.replace(month=mes, day=dia).date()
            except ValueError:
                return None
            return f.replace(year=f.year + 1) if f < ahora.date() else f
        m = re.search(r"\bel\s+(\d{1,2})\b", t)
        if m and 1 <= int(m.group(1)) <= 31:
            dia = int(m.group(1))
            try:
                f = ahora.replace(day=dia).date()
            except ValueError:
                return None
            if f < ahora.date():
                siguiente = (ahora.replace(day=1) + timedelta(days=32)).replace(day=1)
                try:
                    f = siguiente.replace(day=dia).date()
                except ValueError:
                    return None
            return f
        return None

    @staticmethod
    def _fecha_simple(t: str):
        """«dentro de N horas/dias/semanas» y «en N minutos»."""
        m = re.search(r"dentro\s+de\s+(\d{1,3})\s*(minuto|hora|dia|semana)", t)
        if not m:
            m = re.search(r"\ben\s+(\d{1,3})\s*(minuto|hora|dia|semana)", t)
        if not m:
            return None
        n, unidad = int(m.group(1)), m.group(2)
        delta = {"minuto": timedelta(minutes=n), "hora": timedelta(hours=n),
                 "dia": timedelta(days=n), "semana": timedelta(weeks=n)}[unidad]
        return datetime.now() + delta

    @classmethod
    def _cuando(cls, t: str):
        """Fecha y hora completas, o None si no hay nada temporal."""
        ahora = datetime.now()
        relativo = cls._fecha_simple(t)
        if relativo is not None:
            return relativo.replace(second=0, microsecond=0)
        dia = cls._dia_de(t, ahora)
        hora = cls._hora_de(t)
        if dia is None and hora is None:
            return None
        if hora is None:
            hora = (9, 0)          # un dia sin hora: por la manana
        if dia is None:
            # Solo hora: hoy si aun no ha pasado, si no manana.
            cand = ahora.replace(hour=hora[0], minute=hora[1], second=0, microsecond=0)
            return cand if cand > ahora else cand + timedelta(days=1)
        return datetime(dia.year, dia.month, dia.day, hora[0], hora[1])

    def _cuando_y_asunto(self, t: str, orig: str):
        """Separa la fecha del asunto.

        El titulo se recorta del texto ORIGINAL para conservar mayusculas y
        tildes; la fecha sale del parser de arriba.
        """
        cuando = self._cuando(t)
        asunto = orig
        for patron in self._RUIDO:
            asunto = re.sub(patron, " ", asunto, flags=re.IGNORECASE)
        asunto = re.sub(r"\s{2,}", " ", asunto).strip(" ,.;:-¿?¡!")
        asunto = re.sub(r"^(?:un|una|unos|unas|el|la|los|las|de|del|que|a|con)\s+",
                        "", asunto, flags=re.IGNORECASE).strip(" ,.;:-")
        return cuando, asunto[:120]

    # ── consultar ────────────────────────────────────────────────────────────
    def _consultar(self, t: str, orig: str):
        desde = datetime.now()
        if re.search(r"\bmanana\b", t):
            desde = (desde + timedelta(days=1)).replace(hour=0, minute=0, second=0)
            hasta, cuando = desde + timedelta(days=1), "mañana"
        elif re.search(r"semana", t):
            hasta, cuando = desde + timedelta(days=7), "esta semana"
        elif re.search(r"\bmes\b", t):
            hasta, cuando = desde + timedelta(days=30), "este mes"
        else:
            hasta = desde.replace(hour=23, minute=59, second=59)
            cuando = "hoy"
        try:
            eventos = self.lista("cal_list_events", {
                "time_min": desde.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "time_max": hasta.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "max_results": 10,
            })
        except Exception as e:
            self.log(f"[CONECTORES] cal_list_events fallo: {e}")
            return self._sin_servicio(e)
        if not eventos:
            return f"Señor, no tiene nada agendado {cuando}."
        lineas = []
        for ev in eventos[:10]:
            hora = self._hora_iso(ev.get("start", ""))
            lineas.append(f"{hora} {ev.get('summary', '(sin título)')}".strip())
        return (f"Señor, {cuando} tiene {len(eventos)} "
                f"{'cita' if len(eventos) == 1 else 'citas'}: " + "; ".join(lineas) + ".")

    @staticmethod
    def _hora_iso(iso: str) -> str:
        """Hora legible de una fecha ISO devuelta por Google."""
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%H:%M")
        except Exception:
            return ""

    # ── borrar ───────────────────────────────────────────────────────────────
    def _borrar(self, t: str, orig: str):
        pista = self.BORRAR.sub(" ", t)
        pista = self.CALENDARIO.sub(" ", pista)
        pista = re.sub(r"\b(?:la|el|de|del|mi|en|para|cita|evento)\b", " ", pista)
        pista = re.sub(r"\s{2,}", " ", pista).strip(" ,.;:")
        if not pista:
            return "Señor, ¿qué cita cancelo? Dígame parte del título."
        ahora = datetime.now()
        try:
            eventos = self.lista("cal_list_events", {
                "time_min": ahora.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "time_max": (ahora + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "max_results": 50,
            })
        except Exception as e:
            return self._sin_servicio(e)
        candidatos = [e for e in eventos
                      if isinstance(e, dict) and e.get("id")
                      and pista in _norm(e.get("summary", ""))]
        if not candidatos:
            return f"Señor, no encuentro ninguna cita que contenga «{pista}»."
        if len(candidatos) > 1:
            titulos = "; ".join(c.get("summary", "") for c in candidatos[:5])
            return (f"Señor, tengo {len(candidatos)} citas que encajan ({titulos}). "
                    "Concréteme cuál cancelo.")
        ev = candidatos[0]
        try:
            self.llamar("cal_delete_event", {"event_id": ev["id"]})
        except Exception as e:
            self.log(f"[CONECTORES] cal_delete_event fallo: {e}")
            return self._sin_servicio(e)
        return self.avisos.avisar(
            orig,
            f"Cancelada, señor: «{ev.get('summary', '')}» "
            f"del {self._bonita(self._dt(ev.get('start', '')))}.",
            f"La he quitado de su {self.servicio}.")

    @staticmethod
    def _dt(iso: str):
        try:
            return datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
        except Exception:
            return None

    # ── comunes ──────────────────────────────────────────────────────────────
    DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

    @classmethod
    def _bonita(cls, dt) -> str:
        if dt is None:
            return "fecha desconocida"
        hoy = datetime.now().date()
        dia = dt.date()
        if dia == hoy:
            prefijo = "hoy"
        elif dia == hoy + timedelta(days=1):
            prefijo = "mañana"
        else:
            prefijo = (f"{cls.DIAS[dt.weekday()]} {dt.day} de "
                       f"{cls.MESES[dt.month - 1]}")
        return f"{prefijo} a las {dt.strftime('%H:%M')}"

    def _sin_servicio(self, e) -> str:
        return (f"Señor, no pude hablar con {self.servicio}: {str(e)[:120]}. "
                f"Compruebe que el servidor de calendario está en marcha "
                f"(puerto {SERVIDORES['calendar']}) y autorizado.")


# ── DESPACHADOR ──────────────────────────────────────────────────────────────
class Conectores:
    """Despachador de conectores. handle(text) -> str | None

    Mismo contrato que SkillsManager, PCControl y Mensajeria, para que el
    nucleo lo consulte igual que a los demas.
    """

    def __init__(self, log=print, notify=None, safe=False, servidores=None):
        self.log = log
        self.safe = safe
        self.servidores = servidores or SERVIDORES
        self.avisos = Notificador(notify=notify, log=log, safe=safe)
        self._cliente = None
        self.conectores = []
        self._cargar()

    def _cliente_mcp(self):
        if self._cliente is None:
            from mcp_client import MCPClient
            self._cliente = MCPClient(
                {n: f"http://127.0.0.1:{p}" for n, p in self.servidores.items()},
                default_timeout=15.0)
        return self._cliente

    def _cargar(self):
        try:
            cliente = self._cliente_mcp()
        except Exception as e:
            self.log(f"[CONECTORES] Cliente MCP no disponible: {e}")
            return
        for clase in (ConectorCalendar,):
            try:
                self.conectores.append(clase(cliente, self.avisos, self.log))
            except Exception as e:
                self.log(f"[CONECTORES] No pude cargar {clase.nombre}: {e}")

    def estado(self) -> dict:
        """Que conectores responden ahora mismo (para el diagnostico)."""
        return {c.servicio: c.disponible() for c in self.conectores}

    def handle(self, text: str):
        t = _norm(text)
        if not t:
            return None
        for c in self.conectores:
            try:
                r = c.handle(t, text)
            except Exception as e:
                self.log(f"[CONECTORES] {c.servicio} fallo con «{text[:60]}»: {e}")
                continue
            if r:
                return r
        return None
