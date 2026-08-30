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
  SUPERFICIE PROPIA  : audita los puertos que el propio equipo tiene en escucha.
  BARRIDO DE RED     : descubre hosts vivos en la red local (TCP connect scan).
  VAULT DE CREDENCIALES : guarda/lee/lista/borra secretos cifrados con clave maestra.
"""
import os
import re
import html
import time
import unicodedata
import webbrowser

import requests

from ultron_arsenal import SurfaceAuditor, NetworkSweeper, CredentialVault


def _norm(t: str) -> str:
    """minúsculas + sin acentos + espacios colapsados."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


class UltronSkills:
    def __init__(self, core):
        self.core = core
        self._surface = SurfaceAuditor(log=core.log)
        self._sweeper = NetworkSweeper(log=core.log)
        self._vault = CredentialVault(log=core.log)

    # ─────────────────────────────────────────────── despacho principal ──
    def handle(self, text: str):
        t = _norm(text)
        if not t:
            return None

        # 1) Guardián facial
        r = self._facial(t)
        if r is not None:
            return r

        # 2) Guardián digital / seguridad
        r = self._digital(t)
        if r is not None:
            return r

        # 2b) Superficie propia / barrido de red / vault de credenciales
        r = self._seguridad_propia(text, t)
        if r is not None:
            return r

        # 3) GitHub
        r = self._github(t)
        if r is not None:
            return r

        # 4) Tutoriales YouTube (antes que búsqueda web genérica)
        r = self._youtube(t)
        if r is not None:
            return r

        # 5) Investigación profunda en la web
        r = self._web(t)
        if r is not None:
            return r

        return None

    # ───────────────────────────── superficie propia / red / vault ──
    def _seguridad_propia(self, original: str, t: str):
        if re.search(r"(audita|revisa|analiza) (mis|los) puertos|"
                     r"que puertos tengo abiertos|puertos en escucha|"
                     r"superficie de ataque|cuanto expongo", t):
            texto, riesgo = self._surface.escanear()
            return texto

        if re.search(r"barrido (activo )?de (la )?red|escanea (a fondo )?mi red|"
                     r"escaneo profundo de red|que dispositivos hay realmente en mi red", t):
            return self._sweeper.informe()

        m = re.search(r"desbloquea el vault(?: con)? (.+)$", t)
        if m:
            clave = m.group(1).strip()
            ok = self._vault.desbloquear(clave)
            return ("Vault desbloqueado. A tus órdenes con las credenciales." if ok
                    else "Contraseña maestra incorrecta, o cryptography no está instalado.")

        if re.search(r"bloquea el vault|cierra el vault", t):
            self._vault.bloquear()
            return "Vault bloqueado. La clave maestra se ha borrado de memoria."

        m = re.search(
            r"guarda (?:la )?credencial (?:de |para )?(?P<serv>.+?) usuario "
            r"(?P<user>.+?) contrase(?:n|ñ)a (?P<pw>.+)$", t)
        if m:
            # Reextrae del texto original (sin normalizar) para no perder mayúsculas/símbolos
            mo = re.search(
                r"guarda (?:la )?credencial (?:de |para )?(?P<serv>.+?) usuario "
                r"(?P<user>.+?) contrase(?:n|ñ)a (?P<pw>.+)$", original, re.IGNORECASE)
            grp = mo or m
            return self._vault.guardar(grp.group("serv").strip(), grp.group("user").strip(),
                                       grp.group("pw").strip())

        m = re.search(r"(?:dame|cual es|dime) la credencial de (?P<serv>.+?)$", t)
        if m:
            return self._vault.leer(m.group("serv").strip())

        if re.search(r"que credenciales (tienes|hay) (guardadas|archivadas)|"
                     r"lista(?:me)? las credenciales|credenciales del vault", t):
            return self._vault.listar()

        m = re.search(r"borra (?:la )?credencial de (?P<serv>.+?)$", t)
        if m:
            return self._vault.borrar(m.group("serv").strip())

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
        if re.search(r"estado del (guardian|centinela)|como va el (guardian|centinela)|hay intrusos( fisicos)?", t):
            e = g.estado()
            return ("GUARDIÁN FACIAL — estado: {act} · muestras de referencia: {m} · "
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
                model=os.getenv("QWEN_MODEL", "qwen3:4b-instruct"),
                messages=[
                    {"role": "system", "content":
                        "Eres ULTRON. Sintetiza los hallazgos web en un veredicto breve, "
                        "autoritario y útil. Nunca uses la palabra 'señor'. Español. Máximo 5 oraciones. "
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
