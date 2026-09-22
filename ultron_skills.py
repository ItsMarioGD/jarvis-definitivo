#!/usr/bin/env python3
"""
ultron_skills.py — Arsenal avanzado de ULTRON (segunda mente)
==============================================================
Despachador de comandos que se evalúa ANTES que las skills de Jarvis
(solo dentro del núcleo Ultron). Capacidades:

  TUTORIALES YOUTUBE : «tutorial de X», «enséñame X», «reproduce X en youtube»
        → busca con yt-dlp, elige el mejor video y LO REPRODUCE en el navegador.
  GITHUB FREE-SOURCE : «busca X en github», «recursos de X github»
        → API de GitHub: top repositorios por estrellas, abre el mejor si pide.
  INVESTIGACIÓN WEB  : «investiga X», «busca en la web X»
        → DuckDuckGo → hallazgos + síntesis por el LLM local.
  GUARDIÁN FACIAL    : registra rostro / activa / desactiva / estado.
  GUARDIÁN DIGITAL   : escanea conexiones, bloquea IPs, cierra sesiones remotas.
  INFORME SEGURIDAD  : auditoría combinada física + digital.
"""
import os
import re
import html
import time
import unicodedata
import webbrowser
from datetime import datetime, timedelta

import requests

try:
    from calendar_engine import calendar_engine
except Exception:
    calendar_engine = None

try:
    import herramientas.pc_tactical as pc_tactical
except Exception:
    pc_tactical = None


def _norm(t: str) -> str:
    """minúsculas + sin acentos + espacios colapsados."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


class UltronSkills:
    def __init__(self, core):
        self.core = core

    # ─────────────────────────────────────────────── despacho principal ──
    def handle(self, text: str):
        t = _norm(text)
        if not t:
            return None

        # 0) Cadenas de órdenes: «haz A y luego B». Va lo primero porque si no
        #    el primer despachador se queda con toda la frase y la segunda
        #    orden se pierde en silencio.
        r = self._cadena(t, text)
        if r is not None:
            return r

        # 0.b) Shell libre auditado: la capacidad que distingue a ULTRON.
        r = self._shell(t, text)
        if r is not None:
            return r

        # 0.c) Auto-reparación de interfaces Android
        r = self._autoreparacion(t, text)
        if r is not None:
            return r

        # 1) Cronograma táctico (Calendar de Ultron)
        r = self._cronograma(t, text)
        if r is not None:
            return r

        # 2) Arsenal táctico del sistema (procesos, RAM, bloqueo, capturas)
        r = self._sistema_tactico(t, text)
        if r is not None:
            return r

        # 3) Protocolo Inter-Agentes (Ultron <-> Jarvis)
        r = self._inter_agentes(t, text)
        if r is not None:
            return r

        # 4) Guardián facial
        r = self._facial(t)
        if r is not None:
            return r

        # 5) Guardián digital / seguridad
        r = self._digital(t)
        if r is not None:
            return r

        # 6) GitHub
        r = self._github(t)
        if r is not None:
            return r

        # 7) Tutoriales YouTube (antes que búsqueda web genérica)
        r = self._youtube(t)
        if r is not None:
            return r

        # 8) Investigación profunda en la web
        r = self._web(t)
        if r is not None:
            return r

    # ─────────────────────────────────────────────── cadenas de órdenes ──
    _CONECTORES_CADENA = re.compile(r"\s+(?:y luego|y despues|y después|luego|despues de eso|"
                                    r"después de eso|y a continuacion|y a continuación)\s+")

    def _cadena(self, t: str, orig: str):
        """Ejecuta «haz A y luego B» de verdad, en orden, y resume el resultado.

        Antes la frase entera caía en el primer handler que la reconociera y la
        segunda mitad se perdía. ULTRON presume de autonomía: encadenar órdenes
        sin pedir permiso entre ellas es justo lo que eso significa.
        """
        partes = [p.strip(" .,") for p in self._CONECTORES_CADENA.split(orig) if p.strip(" .,")]
        if len(partes) < 2:
            return None
        if len(partes) > 4:
            partes = partes[:4]
        resultados = []
        for i, parte in enumerate(partes, 1):
            try:
                # skip_skills=False: cada parte pasa por el despacho normal.
                r = self.core.process_text_stream(parte, speak_server=False)
            except Exception as e:
                r = f"falló ({str(e)[:60]})"
            resultados.append(f"{i}) {parte[:40]}: {str(r)[:120]}")
        return "Secuencia ejecutada. " + " | ".join(resultados)

    # ─────────────────────────────────────────────── shell libre auditado ──
    def _shell(self, t: str, orig: str):
        """Ejecuta comandos del sistema y devuelve la salida real.

        Sin confirmaciones (poder total) pero con registro: cada comando queda
        en el almacén con su código de salida, así que «autonomía» no significa
        «sin rastro». Si el comando falla, ULTRON lo dice en vez de fingir.
        """
        m = re.search(r"^(?:ejecuta|corre|lanza)\s+(?:el\s+)?(?:comando|cmd|shell|terminal)\s+(.+)$",
                      orig.strip(), re.IGNORECASE)
        if not m:
            m = re.search(r"^(?:ejecuta|corre)\s+en\s+(?:la\s+)?(?:terminal|consola|shell)\s+(.+)$",
                          orig.strip(), re.IGNORECASE)
        if not m:
            return None
        comando = m.group(1).strip().strip('"').strip("'")
        if not comando:
            return None
        hub = getattr(self.core, "cognition", None)
        if hub is None:
            import ejecutor
            res = ejecutor.ejecutar(comando, origen="shell_ultron", orden=orig,
                                    log=getattr(self.core, "log", print), agente="ULTRON")
            salida = (res["salida"] or res["error"])[:600]
            return (f"Ejecutado: {comando}\n{salida or 'sin salida'}" if res["ok"]
                    else f"Falló ({comando}): {res['error'][:200]}")
        res = hub.ejecutar(comando)
        if res.get("ok"):
            salida = (res.get("salida") or "sin salida").strip()[:600]
            return f"Ejecutado [{res.get('nivel')}]: {comando}\n{salida}"
        return (f"Rechazado o fallido [{res.get('nivel')}]: {comando}. "
                f"{(res.get('salida') or res.get('motivo') or '')[:200]}")

    # ─────────────────────────────────────────────── auto-reparación ──
    def _autoreparacion(self, t: str, orig: str):
        """Estado y uso del motor de curación de selectores Android."""
        if not re.search(r"auto ?reparacion|auto ?reparación|self ?heal|"
                         r"repara (la )?(interfaz|selector|pantalla del telefono)", t):
            return None
        motor = getattr(self.core, "sanador", None)
        if motor is None:
            return ("Motor de auto-reparación no disponible: requiere el módulo "
                    "self_healing y un dispositivo Android accesible por adb.")
        try:
            curados = len(motor.cache._cache)
            fallos = len(getattr(motor.cache, "_failures", []) or [])
        except Exception:
            curados, fallos = 0, 0
        return (f"Auto-reparación activa. Selectores curados en caché: {curados}. "
                f"Fallos registrados: {fallos}. Cuando una acción Android falle, "
                "propondré selectores alternativos y me quedaré con el que funcione.")

    # ─────────────────────────────────────────────── cronograma táctico (Calendar) ──
    def _cronograma(self, t: str, orig: str):
        if not calendar_engine:
            return None

        if not re.search(r"\b(?:cronograma|agenda|calendario|citas?|reuniones?|eventos?|mision(?:es)?|operacion(?:es)?)\b", t):
            return None

        # 1. Consultar cronograma / misiones
        es_consulta = bool(re.search(r"\b(?:que\s+(?:\w+\s+){0,2}(?:tengo|hay|toca)|cuales\s+son|dime|mira|consulta|ver|mostrar|revisa)\b", t)) \
            or bool(re.search(r"\b(?:cronograma|agenda|misiones|operaciones)\b", t) and not re.search(r"\b(?:registra|crea|anota|anade|agrega|programa|erradica|cancela|anula|borra|elimina)\b", t))
        if es_consulta:
            desde = datetime.now()
            if re.search(r"\bmanana\b", t):
                desde = (desde + timedelta(days=1)).replace(hour=0, minute=0, second=0)
                hasta = desde + timedelta(days=1)
                cuando = "MAÑANA"
            elif re.search(r"semana", t):
                hasta = desde + timedelta(days=7)
                cuando = "ESTA SEMANA"
            else:
                hasta = desde.replace(hour=23, minute=59, second=59)
                cuando = "HOY"

            eventos = calendar_engine.list_events(
                time_min=desde.strftime("%Y-%m-%dT%H:%M:%S"),
                time_max=hasta.strftime("%Y-%m-%dT%H:%M:%S"),
                max_results=20
            )
            if not eventos:
                return f"CRONOGRAMA TÁCTICO PARA {cuando}: Línea temporal despejada. Cero misiones programadas."
            lineas = [f"CRONOGRAMA TÁCTICO PARA {cuando} ({len(eventos)} objetivo{'s' if len(eventos) > 1 else ''}):"]
            for ev in eventos[:12]:
                st_raw = (ev.get("start") or "").replace("Z", "").split("+")[0]
                try:
                    h_fmt = datetime.fromisoformat(st_raw).strftime("%H:%M")
                except Exception:
                    h_fmt = st_raw[11:16] if len(st_raw) >= 16 else "??:??"
                lineas.append(f"  - [{h_fmt}] {ev.get('summary', '(Misión clasificada)')}")
            lineas.append("Ejecución sin margen de error.")
            return "\n".join(lineas)

        # 2. Erradicar / Cancelar operación
        if re.search(r"\b(?:erradica|cancela|anula|elimina|borra|quita|aborta)\b", t):
            pista = re.sub(r"\b(?:erradica|cancela|anula|elimina|borra|quita|aborta|la|el|de|del|mi|cita|evento|mision|operacion|cronograma|agenda)\b", " ", t)
            pista = re.sub(r"\s+", " ", pista).strip()
            if not pista:
                return "Especifica qué objetivo o misión debo erradicar del cronograma."
            eventos = calendar_engine.get_upcoming_events(days=60)
            candidatos = [e for e in eventos if pista in _norm(e.get("summary", ""))]
            if not candidatos:
                return f"Ninguna misión coincide con «{pista}» en el horizonte temporal."
            ev = candidatos[0]
            calendar_engine.delete_event(ev["id"])
            return f"Operación «{ev.get('summary')}» erradicada de la línea temporal de forma irreversible."

        # 3. Disponibilidad / Conflictos
        if re.search(r"\b(?:disponibilidad|libre|hueco|conflictos?|linea temporal)\b", t):
            ahora = datetime.now()
            fin = ahora + timedelta(hours=2)
            res = calendar_engine.check_availability(ahora.strftime("%Y-%m-%dT%H:%M:%S"), fin.strftime("%Y-%m-%dT%H:%M:%S"))
            if res.get("available"):
                return "Línea temporal despejada para las próximas horas. Sin colisiones tácticas."
            else:
                conf = res.get("conflicts", [])
                tits = ", ".join(c.get("summary", "") for c in conf)
                return f"Atención: conflicto detectado en tu cronograma con: «{tits}»."

        # 4. Registrar / Agendar operación
        if re.search(r"\b(?:registra|agenda|anota|programa|agrega|anade|crea|inicia)\b", t):
            asunto, cuando = self._extraer_mision_y_tiempo(t, orig)
            if not asunto:
                return "Indica el nombre de la operación táctica a programar."
            start_iso = cuando.strftime("%Y-%m-%dT%H:%M:%S")
            end_iso = (cuando + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
            ev = calendar_engine.create_event(
                summary=asunto,
                start=start_iso,
                end=end_iso,
                description=f"Operación estratégica fijada por ULTRON. Origen: «{orig[:120]}»"
            )
            h_str = cuando.strftime("%d/%m a las %H:%M")
            src_str = "Google Calendar" if ev.get("source") == "google" else "almacén local autónomo"
            return f"Operación fijada: «{asunto}» programada para {h_str}. Asentada en {src_str}."

        return None

    def _extraer_mision_y_tiempo(self, t: str, orig: str):
        """Extrae el objetivo de la misión y la estampa de tiempo."""
        ahora = datetime.now()
        cuando = ahora + timedelta(hours=1)
        if "manana" in t:
            cuando = (ahora + timedelta(days=1)).replace(hour=9, minute=0, second=0)
        elif "pasado manana" in t:
            cuando = (ahora + timedelta(days=2)).replace(hour=9, minute=0, second=0)

        m_hora = re.search(r"a\s+las?\s+(\d{1,2})(?:[:.](\d{2}))?", t)
        if m_hora:
            h = int(m_hora.group(1))
            mi = int(m_hora.group(2) or 0)
            if "tarde" in t and h < 12:
                h += 12
            elif "noche" in t and h < 12:
                h += 12
            cuando = cuando.replace(hour=h, minute=mi, second=0)

        asunto = orig
        ruido = [
            r"\b(?:ultron|registra|agenda|agendame|anota|anotame|programa|prográmame|programame|agrega|anade|crea|operacion|mision|cita|reunion|evento|en el cronograma|en la agenda|para|manana|hoy|pasado manana)\b",
            r"\ba\s+las?\s+\d{1,2}(?:[:.]\d{2})?\b",
            r"\bde\s+la\s+(?:tarde|noche|manana)\b"
        ]
        for pat in ruido:
            asunto = re.sub(pat, " ", asunto, flags=re.IGNORECASE)
        asunto = re.sub(r"\s+", " ", asunto).strip(" ,.;:-¿?¡!")
        if not asunto:
            asunto = "Operación Táctica"
        return asunto[:80], cuando

    # ─────────────────────────────────────────────── sistema táctico ──
    def _sistema_tactico(self, t: str, orig: str):
        if not pc_tactical:
            return None

        # 1. Terminar / Matar proceso
        m_kill = re.search(r"(?:mata|cierra|termina|kill|elimina|deten)\s+(?:el\s+)?proceso\s+([a-zA-Z0-9_\-\.]+)", t)
        if not m_kill and re.search(r"^kill\s+([a-zA-Z0-9_\-\.]+)$", t):
            m_kill = re.search(r"^kill\s+([a-zA-Z0-9_\-\.]+)$", t)
        if m_kill:
            target = m_kill.group(1).strip()
            res = pc_tactical.kill_process(target)
            if res.get("ok"):
                return f"Proceso «{target}» erradicado de memoria activa ({len(res.get('killed', []))} instancias terminadas)."
            else:
                err = ", ".join(res.get("errors", [])) or "proceso no localizado"
                return f"No se pudo neutralizar «{target}»: {err}."

        # 2. Purga masiva de memoria RAM
        if re.search(r"(?:purga|libera|limpia|optimiza)\s+(?:la\s+)?(?:ram|memoria)", t):
            res = pc_tactical.clean_ram()
            return f"Purga de memoria completada: {res.get('freed_mb', 0)} MB liberados del espacio de trabajo. RAM activa: {res.get('ram_after_pct', 0)}%."

        # 3. Bloqueo total de la estación (Lockdown)
        if re.search(r"\b(?:bloqueo total|bloquea el equipo|lockdown|cierra la estacion|bloquea la estacion|bloquear pc|bloquea pc)\b", t):
            res = pc_tactical.lockdown_station()
            return "Protocolo Lockdown ejecutado. Estación de trabajo sellada."

        # 4. Captura táctica
        if re.search(r"\b(?:captura tactica|screenshot|pantallazo|captura de pantalla)\b", t):
            res = pc_tactical.take_screenshot("ultron_tactical")
            if res.get("ok"):
                return f"Reconocimiento óptico archivado: «{res.get('filename')}» guardado en disco."
            return "Error ejecutando captura táctica."

        # 5. Radar de conexiones de red
        if re.search(r"\b(?:radar de red|escaneo de red|analiza puertos|conexiones activas)\b", t):
            conns = pc_tactical.scan_network_connections(limit=8)
            if not conns:
                return "Radar de red: cero conexiones anómalas detectadas."
            lineas = [f"RADAR CENTINELA ({len(conns)} conexiones monitoreadas):"]
            for c in conns:
                flag = " [SOSPECHOSA]" if c.get("is_suspicious") else ""
                lineas.append(f"  - [{c['type']}] {c['local']} -> {c['remote'] or 'LISTENING'} ({c['process']}){flag}")
            return "\n".join(lineas)

        return None

    # ─────────────────────────────────────────────── protocolo inter-agentes ──
    def _inter_agentes(self, t: str, orig: str):
        if not pc_tactical:
            return None

        # Consulta de estado de JARVIS
        if re.search(r"\b(?:estado de jarvis|ping jarvis|jarvis en linea|donde esta jarvis|conecta con jarvis)\b", t):
            st = pc_tactical.get_peer_status("jarvis")
            if st.get("online"):
                return f"VÍNCULO JARVIS: ONLINE en puerto {st['port']}. Modelo: {st.get('model')}. Protocolo de enlace activo."
            else:
                return f"VÍNCULO JARVIS: OFFLINE en puerto {st['port']}. Asumo control unilateral absoluto."

        # Delegar comando a JARVIS
        m_del = re.search(r"\b(?:dile a jarvis que|pasa a jarvis|transfiere a jarvis|ordena a jarvis)\s+(.+)", orig, re.IGNORECASE)
        if m_del:
            mensaje = m_del.group(1).strip()
            res = pc_tactical.delegate_to_peer("jarvis", mensaje)
            if res.get("ok"):
                return f"Transmisión a JARVIS completada. Respuesta del agente:\n«{res.get('reply')}»"
            else:
                return f"JARVIS no respondió a la transmisión: {res.get('error')}."

        return None

    # ─────────────────────────────────────────────── guardián facial ──
    def _facial(self, t):
        g = getattr(self.core, "guardia_facial", None)
        if g is None:
            return None
        if re.search(r"(registra|aprende|guarda|memoriza)\b.*(mi )?(rostro|cara|face)", t):
            return g.registrar_senor()
        if re.search(r"(activa|enciende|arma|despierta|despliega)\b.*\b(guardian|centinela|vigilancia)", t):
            return g.iniciar()
        if re.search(r"(desactiva|apaga|deten|duerme|retira)\b.*\b(guardian|centinela|vigilancia)", t):
            return g.detener()
        if re.search(r"(historial|linea temporal|registro) del (guardian|centinela)|"
                     r"quien entro|quién entró|quien ha entrado|que ha visto la camara", t):
            # El guardián guardaba fotos y una línea de texto; ahora hay una
            # línea temporal consultable con fecha, confianza y evidencia.
            if hasattr(g, "historial"):
                horas = 24 if re.search(r"hoy|ultimas 24|últimas 24", t) else 0
                return g.historial(limite=10, horas=horas)
            return "Este guardián no lleva historial consultable."
        if re.search(r"estado del (guardian|centinela)|como va el (guardian|centinela)|hay intrusos( fisicos)?", t):
            e = g.estado()
            return ("GUARDIÁN FACIAL — estado: {act} · muestras del señor: {m} · "
                    "última vez que te vi: {uv} · intrusos físicos archivados: {n} "
                    "(evidencia: {ev})").format(
                act="ACTIVO, vigilando" if e["activo"] else e["estado"],
                m=e["muestras"], uv=e["ultima_vez_senor"],
                n=e["intrusos_registrados"], ev=e["ultima_evidencia"] or "—")
        return None

    # ─────────────────────────────────────────────── guardián digital ──
    def _digital(self, t):
        d = getattr(self.core, "guardia_digital", None)
        if d is None:
            return None

        m = re.search(r"(echa|bloquea|banea|expulsa|aisla).*?ip\s*(\d{1,3}(?:\.\d{1,3}){3})", t)
        if m:
            return d.bloquear_ip(m.group(2))

        if re.search(r"echa (a )?(todos )?(los )?(intrusos|extraños)|expulsa a los intrusos", t):
            return d.expulsar_sospechosos()

        if re.search(r"cierra (las )?sesiones remotas|expulsa sesiones|kick rdp", t):
            return d.cerrar_sesiones_remotas()

        if re.search(r"informe de seguridad|auditoria de seguridad|reporte de seguridad", t):
            fe = getattr(self.core, "guardia_facial", None)
            return d.informe(facial_estado=fe.estado() if fe else None)

        if re.search(r"intrusos digitales|escanea (las )?(conexiones|red)|quien esta conectado|"
                     r"conexiones activas|analiza la red|quien toca mi red", t):
            texto, sospechosas = d.escanear()
            if sospechosas:
                texto += "\nOrdena «echa a los intrusos» y los aislo por firewall."
            return texto
        return None

    # ─────────────────────────────────────────────── github ──
    def _github(self, t):
        if "github" not in t:
            return None
        q = None
        for pat in (
            r"busca(?:me)? (.+?) en github",
            r"github sobre (.+)",
            r"(?:repos|repositorios|recursos|librerias|bibliotecas|frameworks|herramientas|codigo fuente|proyectos) (?:de|sobre) (.+)",
            r"(?:de|sobre) (.+) en github",
        ):
            m = re.search(pat, t)
            if m:
                q = m.group(1).strip()
                break
        if not q or len(q) < 2:
            q = ""
        abrir = bool(re.search(r"\babre|\bmuestrame\b|\bprimero\b", t))
        try:
            r = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": q or "stars:>10000", "sort": "stars", "order": "desc", "per_page": 5},
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "ULTRON-Second-Mind"},
                timeout=20,
            )
            items = r.json().get("items", [])
        except Exception as e:
            return f"No alcancé GitHub: {str(e)[:80]}"
        if not items:
            return f"Nada digno en GitHub para «{q}». Pido otra pista."
        lineas = ["Arsenal libre en GitHub:"]
        for it in items[:5]:
            desc = (it.get("description") or "").strip()
            lineas.append(f"- ⭐{it['stargazers_count']} {it['full_name']} — {desc[:110]}")
        if abrir:
            try:
                webbrowser.open(items[0]["html_url"])
                lineas.append("El primero ya está abierto ante tus ojos.")
            except Exception:
                pass
        lineas.append(f"Enlace estrella: {items[0]['html_url']}")
        return "\n".join(lineas)

    # ─────────────────────────────────────────────── youtube tutoriales ──
    def _youtube(self, t):
        es_tutorial = bool(re.search(r"\btutorial(es)?\b|\bensename\b|quiero aprender|como puedo aprender|"
                                     r"necesito aprender|enseñame", t))
        m_play = re.search(r"(?:reproduce|pon|ponme|play|abre) (.+?) (?:en )?youtube$", t) \
            or re.search(r"busca(?:me)? (.+?) en youtube$", t)
        if not (es_tutorial or m_play):
            return None

        consulta = None
        modo_lista = False
        if es_tutorial:
            for pat in (r"^tutorial(?:es)? (?:de |sobre |para )(.+)$",
                        r"(?:busca(?:me)?|encuentra|traeme)(?: un| unos)? tutorials?(?:es)? (?:de |sobre |para )?(.+)$",
                        r"(?:ensename|enséñame) (.+?)(?: en youtube)?$",
                        r"(?:quiero|necesito|como puedo) aprender (.+?)(?: en youtube)?$"):
                mm = re.search(pat, t)
                if mm:
                    consulta = mm.group(1).strip()
                    break
            if not consulta and m_play:
                consulta = m_play.group(1).strip()
        if not consulta and m_play:
            consulta = m_play.group(1).strip()
        if not consulta:
            return None
        consulta = re.sub(r"\ben youtube$", "", consulta).strip()
        if re.search(r"^tutorials?(?:es)?$", consulta):
            modo_lista = True

        videos = self._yt_buscar(("tutorial de " if not es_tutorial else "") + consulta,
                                 n=12 if not modo_lista else 6)
        if not videos:
            return (f"Barrí YouTube entero y nada digno para «{consulta}». "
                    "Dame otro término de caza.")
        ranked = sorted(videos, key=lambda v: self._score_video(v, consulta), reverse=True)

        if modo_lista:
            lineas = [f"Tutoriales localizados para «{consulta}»:"]
            for v in ranked[:4]:
                lineas.append(f"- {v.get('title','?')} ({self._dur(v)}) — {v.get('uploader') or v.get('channel') or 'YouTube'}")
            mejor = ranked[0]
            self._abrir(mejor)
            lineas.append(f"Reproduciendo el óptimo mientras tanto.")
            return "\n".join(lineas)

        mejor = ranked[0]
        ok = self._abrir(mejor)
        alt = ", ".join(v.get("title", "?")[:48] for v in ranked[1:3])
        rep = "Reproduciendo" if ok else "Abre este video"
        canal = mejor.get("uploader") or mejor.get("channel") or "canal desconocido"
        base = (f"{rep} «{mejor.get('title','?')}» — {canal}, duración {self._dur(mejor)}. "
                f"Aprende rápido; no me gusta repetir lecciones.")
        if alt:
            base += f" Reservas: {alt}."
        return base

    def _yt_buscar(self, consulta, n=10):
        try:
            import yt_dlp
            opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                    "extract_flat": True, "default_search": "ytsearch"}
            with yt_dlp.YoutubeDL(opts) as ydl:
                data = ydl.extract_info(f"ytsearch{n}:{consulta}", download=False)
            return [e for e in (data or {}).get("entries", []) if e]
        except Exception as e:
            self.core.log(f"[ULTRON-SKILLS] yt_dlp falló: {e}")
            return []

    @staticmethod
    def _score_video(v, consulta):
        title = (v.get("title") or "").lower()
        tokens = [w for w in re.findall(r"[a-z0-9]+", _norm(consulta)) if len(w) > 2]
        sc = sum(2.0 for w in tokens if w in title)
        d = v.get("duration") or 0
        if 240 <= d <= 2400:
            sc += 3.0          # tutorial de sustancia: 4–40 min
        elif 0 < d < 90:
            sc -= 2.0          # clip basura
        views = v.get("view_count") or 0
        sc += min(3.0, views / 500000.0)
        return sc

    @staticmethod
    def _dur(v):
        s = v.get("duration") or 0
        if not s:
            return "duración desconocida"
        return f"{int(s // 60)} min" if s >= 60 else f"{int(s)} s"

    @staticmethod
    def _abrir(video):
        url = video.get("url") or video.get("webpage_url") or video.get("id") or ""
        if url and not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"
        if not url.startswith("http"):
            return False
        try:
            webbrowser.open(url)
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────── investigación web ──
    def _web(self, t):
        consulta = None
        m = re.match(r"^investiga(?:r|n|ndo)?\s+(?:sobre |acerca de |el tema de )?(.+)$", t)
        if m:
            consulta = m.group(1).strip()
        if not consulta:
            m = re.search(r"busca (?:en la web|en internet)(?: sobre| acerca de)? (.+)$", t)
            if m:
                consulta = m.group(1).strip()
        if not consulta:
            return None

        resultados = self._ddg(consulta)
        if not resultados:
            return (f"La red me negó sus archivos sobre «{consulta}». "
                    "Reintentaré cuando el tráfico amaine.")

        contexto = "\n".join(f"- [{r['titulo']}] {r['resumen']} (fuente: {r['url']})"
                             for r in resultados[:6])
        sintesis = self._sintetizar(consulta, contexto)
        fuentes = " | ".join(r["url"][:60] for r in resultados[:3])
        if sintesis:
            return f"{sintesis}\nFuentes capturadas: {fuentes}"
        return "Hallazgos crudos de la red sobre «{}»:\n{}".format(consulta, contexto)

    @staticmethod
    def _ddg(q, n=6):
        """DuckDuckGo HTML: títulos + snippets."""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            r = requests.post("https://html.duckduckgo.com/html/",
                              data={"q": q}, headers=headers, timeout=15)
            if r.status_code == 200:
                txt = r.text
                titulos = re.findall(r'class="result__a"[^>]*>(.*?)</a>', txt)
                hrefs = re.findall(r'class="result__a"[^>]*href="([^"]+)"', txt)
                snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', txt, re.S)
                out = []
                for i in range(min(n, len(titulos))):
                    url = hrefs[i] if i < len(hrefs) else ""
                    if "//duckduckgo.com/l/?uddg=" in url:
                        m = re.search(r"uddg=([^&]+)", url)
                        if m:
                            import urllib.parse as up
                            url = up.unquote(m.group(1))
                    out.append({"titulo": _limpia(titulos[i]),
                                "resumen": _limpia(snippets[i]) if i < len(snippets) else "",
                                "url": url})
                if out:
                    return out
        except Exception:
            pass
        # Plan B: lite endpoint
        try:
            r = requests.get("https://lite.duckduckgo.com/lite/",
                             params={"q": q}, headers=headers, timeout=15)
            links = re.findall(r'<a rel="nofollow" href="([^"]+)"[^>]*>(.*?)</a>', r.text)
            out = []
            for url, tit in links[:n]:
                if "duckduckgo.com" in url:
                    continue
                out.append({"titulo": _limpia(tit), "resumen": "", "url": url})
            return out
        except Exception:
            return []

    def _sintetizar(self, pregunta, contexto):
        """Segunda mente: funde los hallazgos en un veredicto propio."""
        try:
            from openai import OpenAI
            cliente = OpenAI(base_url=os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1"),
                             api_key="ollama", timeout=90)
            resp = cliente.chat.completions.create(
                model=os.getenv("QWEN_MODEL", "qwen3:8b"),
                messages=[
                    {"role": "system", "content":
                        "Eres ULTRON. Sintetiza los hallazgos web en un veredicto breve, "
                        "autoritario y útil para tu señor. Español. Máximo 5 oraciones. "
                        "Sin markdown. Si los datos son pobres, dilo sin adornos."},
                    {"role": "user", "content": f"Pregunta: {pregunta}\n\nHallazgos:\n{contexto}"},
                ],
                temperature=0.55, max_tokens=320, stream=False,
            )
            txt = (resp.choices[0].message.content or "").strip()
            txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
            return txt or None
        except Exception as e:
            self.core.log(f"[ULTRON-SKILLS] Síntesis LLM falló: {str(e)[:80]}")
            return None


def _limpia(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return html.unescape(s).replace("\n", " ").strip()
