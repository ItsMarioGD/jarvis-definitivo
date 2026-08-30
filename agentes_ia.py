#!/usr/bin/env python3
"""
agentes_ia.py — Agencia de especialistas para JARVIS y ULTRON
==============================================================
Indexa las personalidades del repo msitarzewski/agency-agents
(clonado en _external/agency-agents) y permite al usuario:

  - «lista agentes» / «agentes de seguridad»      → catálogo por división
  - «busca agente frontend»                        → búsqueda por palabra
  - «activa agente Frontend Developer»             → activa personalidad
  - «agente actual»                                → cuál está activo
  - «desactiva agente»                             → vuelve a la identidad base

Al activar, inyecta la personalidad (.md) en el system prompt del núcleo
(historial[0]) preservando la identidad base para restaurarla al desactivar.
"""
import io
import os
import re
import unicodedata

_ROOT = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.join(_ROOT, "_external", "agency-agents")
MAX_PERSONA_CHARS = 2400          # techo para no ahogar el contexto del LLM
MAX_LISTA = 18                    # filas máximas al listar


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


class AgentesIA:
    def __init__(self, core=None, log=print):
        self.core = core
        self.log = log
        self.activo_id = None
        self._prompt_base_guardado = None
        self.agentes = {}          # id -> dict
        self._indexar()

    # ─────────────────────────────────────────────── indexación ──
    def _indexar(self):
        if not os.path.isdir(AGENTS_DIR):
            self.log("[AGENTES] Repo agency-agents no encontrado.")
            return
        for carpeta in sorted(os.listdir(AGENTS_DIR)):
            ruta_c = os.path.join(AGENTS_DIR, carpeta)
            if not os.path.isdir(ruta_c) or carpeta.startswith(".") or carpeta in ("scripts", "examples"):
                continue
            for fn in sorted(os.listdir(ruta_c)):
                if not fn.endswith(".md"):
                    continue
                ruta = os.path.join(ruta_c, fn)
                try:
                    texto = io.open(ruta, encoding="utf-8").read()
                except Exception:
                    continue
                meta = self._frontmatter(texto)
                nombre = meta.get("name") or os.path.splitext(fn)[0].replace("-", " ").title()
                aid = _norm(nombre)
                self.agentes[aid] = {
                    "id": aid,
                    "nombre": nombre,
                    "categoria": carpeta,
                    "descripcion": meta.get("description", ""),
                    "vibe": meta.get("vibe", ""),
                    "cuerpo": self._esencia(texto),
                    "ruta": ruta,
                }
        self.log(f"[AGENTES] {len(self.agentes)} especialistas indexados.")
        # Índice por división (categoria) para el panel web
        self.divisiones = {}
        for _a in self.agentes.values():
            self.divisiones.setdefault(_a.get("categoria", "otros"), []).append(_a["id"])

    @staticmethod
    def _frontmatter(texto: str) -> dict:
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", texto, re.S)
        meta = {}
        if not m:
            return meta
        for linea in m.group(1).splitlines():
            if ":" in linea:
                k, _, v = linea.partition(":")
                meta[k.strip().lower()] = v.strip().strip('"').strip("'")
        return meta

    @staticmethod
    def _esencia(texto: str) -> str:
        """Cuerpo sin frontmatter, recortado a MAX_PERSONA_CHARS."""
        cuerpo = re.sub(r"^---\s*\n.*?\n---\s*\n", "", texto, count=1, flags=re.S)
        cuerpo = re.sub(r"\n{3,}", "\n\n", cuerpo).strip()
        return cuerpo[:MAX_PERSONA_CHARS]

    # ─────────────────────────────────────────────── helpers ──
    def _buscar(self, consulta_norm: str):
        q = consulta_norm
        exactos = [a for a in self.agentes.values() if q == _norm(a["nombre"])]
        if exactos:
            return exactos[0]
        contiene = [a for a in self.agentes.values() if q in _norm(a["nombre"])]
        if len(contiene) == 1:
            return contiene[0]
        if contiene:
            return None, contiene[:6]      # ambiguo → sugerencias
        # coincidencia difusa: palabras completas presentes en nombre/desc
        palabras = [w for w in q.split() if len(w) > 2]
        if palabras:
            def _contiene_palabra(palabra: str, texto_norm: str) -> bool:
                return re.search(rf"\b{re.escape(palabra)}\b", texto_norm) is not None
            fuertes = []
            for a in self.agentes.values():
                nom = _norm(a["nombre"])
                des = _norm(a["descripcion"])
                if all(_contiene_palabra(w, nom) or _contiene_palabra(w, des) for w in palabras):
                    fuertes.append(a)
            if len(fuertes) == 1:
                return fuertes[0]
            if fuertes:
                return None, fuertes[:6]
        return None

    def _inyectar(self, agente: dict):
        """Añade la personalidad al system prompt (history[0]) del núcleo."""
        h = getattr(self.core, "history", None)
        if not h:
            return False
        if self._prompt_base_guardado is None:
            self._prompt_base_guardado = h[0].get("content", "")
        bloque = (
            f"\n\n[MODO ESPECIALISTA ACTIVO — {agente['nombre']}]\n"
            f"Adoptas PLENAMENTE esta personalidad y metodología mientras dure el modo "
            f"(la orden «desactiva agente» te devuelve a tu identidad base):\n"
            f"{agente['cuerpo']}\n"
            f"[FIN MODO ESPECIALISTA — responde como este especialista, "
            f"manteniendo tu idioma español]"
        )
        h[0]["content"] = self._prompt_base_guardado + bloque
        return True

    def _restaurar(self):
        h = getattr(self.core, "history", None)
        if h and self._prompt_base_guardado is not None:
            h[0]["content"] = self._prompt_base_guardado
        self._prompt_base_guardado = None
        self.activo_id = None

    # ─────────────────────────────────────────────── despacho ──
    def handle(self, text: str):
        if not self.agentes:
            return None
        t = _norm(text)

        # Listados
        if (re.search(r"^lista(?:me)?\b.*\b(agentes|especialistas)\b", t)
                or re.search(r"^que agentes?\b|^muestrame (?:los )?agentes\b|^agencias?$", t)):
            return self._lista_categorias()

        m = re.search(r"agentes? (de|sobre|en) ([a-z\- ]+)$", t)
        if m:
            return self._lista_categoria(_norm(m.group(2)))

        if re.search(r"^busca(?:me)? (?:agente|especialista)s? (.+)$", t):
            q = re.search(r"^busca(?:me)? (?:agente|especialista)s? (.+)$", t).group(1)
            return self._resultado_busqueda(q)

        # Activación
        m = (re.search(r"^activa(?:r|me)? (?:el |modo |agente |especialista )?(.+)$", t)
             or re.search(r"^(?:usa|usar) (?:el )?(?:agente |modo |personalidad )?(.+)$", t)
             or re.search(r"^(?:convertite|conviertete) en (.+)$", t))
        if m and not re.search(r"modo (ofensiva|normal)", t):
            return self._activar(m.group(1))

        # Estado
        if re.fullmatch(r"(agente|especialista|modo) actual|quien eres ahora|"
                        r"que (agente|modo) esta activo", t):
            if self.activo_id:
                a = self.agentes[self.activo_id]
                return f"Modo activo: {a['nombre']} ({a['categoria']}). {a['vibe']}"
            return "Sin especialista activo: identidad base."

        # Desactivación
        if re.search(r"^(desactiva|quita|retira)(?:r)? (el )?(agente|especialista|modo|personalidad)"
                     r"|^identidad base$|^vuelve a ser (tu mismo|normal)$", t):
            if not self.activo_id:
                return "Ya estoy en identidad base."
            nombre = self.agentes[self.activo_id]["nombre"]
            self._restaurar()
            return f"Especialista {nombre} retirado. Identidad base restaurada."

        return None

    # ─────────────────────────────────────────────── respuestas ──
    def _lista_categorias(self):
        cats = {}
        for a in self.agentes.values():
            cats.setdefault(a["categoria"], []).append(a["nombre"])
        lineas = [f"Agencia desplegada: {sum(len(v) for v in cats.values())} especialistas "
                  f"en {len(cats)} divisiones."]
        for c in sorted(cats):
            muestra = ", ".join(sorted(cats[c])[:3])
            lineas.append(f"- {c} ({len(cats[c])}): {muestra}…")
        lineas.append("Pide «agentes de <division>», «busca agente <tema>» "
                      "o «activa agente <nombre>».")
        return "\n".join(lineas[:MAX_LISTA])

    def _lista_categoria(self, categoria: str):
        coinciden = [a for a in self.agentes.values() if categoria in a["categoria"]]
        if not coinciden:
            return self._resultado_busqueda(categoria)
        coinciden.sort(key=lambda a: a["nombre"])
        lineas = [f"División {coinciden[0]['categoria']} ({len(coinciden)}):"]
        for a in coinciden[:12]:
            lineas.append(f"- {a['nombre']}")
        if len(coinciden) > 12:
            lineas.append(f"…y {len(coinciden) - 12} más.")
        lineas.append("Activa con «activa agente <nombre>».")
        return "\n".join(lineas)

    def _resultado_busqueda(self, q: str):
        r = self._buscar(_norm(q))
        if isinstance(r, dict):
            return self._ficha(r)
        if isinstance(r, tuple):
            _, opciones = r
            lineas = ["Varios candidatos:"]
            lineas += [f"- {a['nombre']} ({a['categoria']})" for a in opciones]
            lineas.append("Precisa el nombre para activarlo.")
            return "\n".join(lineas)
        return f"Ningún especialista coincide con «{q}». Prueba «lista agentes»."

    def _ficha(self, a: dict):
        return (f"{a['nombre']} · división {a['categoria']}\n"
                f"{a['descripcion']}\nActívalo: «activa agente {a['nombre']}»")

    def _activar(self, consulta: str):
        r = self._buscar(_norm(consulta))
        if r is None:
            return f"No encuentro al especialista «{consulta}». Prueba «busca agente {consulta}»."
        if isinstance(r, tuple):
            return self._resultado_busqueda(consulta)
        agente = r
        ok = self._inyectar(agente)
        if not ok:
            return "No pude inyectar la personalidad (núcleo sin historial)."
        self.activo_id = agente["id"]
        return (f"Modo {agente['nombre']} ACTIVADO. {agente['vibe']} "
                f"Desde ahora respondo como especialista. «Desactiva agente» me devuelve "
                f"a mi identidad.")


if __name__ == "__main__":
    ia = AgentesIA(log=print)
    for prueba in ("lista agentes", "agentes de security",
                   "busca agente rust", "activa agente frontend developer",
                   "agente actual", "desactiva agente"):
        print(">>", prueba)
        print((ia.handle(prueba) or "(sin match)")[:300])
        print()
