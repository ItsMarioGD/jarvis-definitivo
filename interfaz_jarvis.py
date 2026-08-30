#!/usr/bin/env python3
"""
interfaz_jarvis.py — J.A.R.V.I.S. COSMIC HUD
Black hole fullscreen + floating glass panels.
"""
import customtkinter as ctk
import tkinter as tk
import queue
import threading
import time
import math
import datetime
import socket
import sys
import re
import random
from jarvis_core import JarvisCore

# ── Palette ────────────────────────────────────────────────────────────────
C = {
    "bg":          "#010208",
    "glass":       "#080C16",
    "glass2":      "#0A0F1C",
    "border":      "#1A1E30",
    "border_hi":   "#2A2E48",
    "sep":         "#141828",
    "accent":      "#E8C8A0",
    "accent2":     "#FFC896",
    "violet":      "#A78BFA",
    "emerald":     "#10B981",
    "red":         "#FF6B6B",
    "text":        "#E8ECF4",
    "text2":       "#8892A8",
    "text3":       "#4A5068",
}

F_M  = ("Consolas", 10)
F_MS = ("Consolas", 8)
F_S  = ("Segoe UI", 10)
F_SS = ("Segoe UI", 9)
F_XS = ("Segoe UI", 7)


# ═══════════════════════════════════════════════════════════════════════════
#  BLACK HOLE CANVAS — fullscreen background
# ═══════════════════════════════════════════════════════════════════════════
class BlackHoleCanvas(tk.Canvas):
    STATE_COLORS = {
        "idle":       ("#E8C8A0", 0.15),
        "listening":  ("#FFC896", 0.8),
        "processing": ("#A78BFA", 1.8),
        "speaking":   ("#D4A574", 0.6),
        "error":      ("#FF6B6B", 1.2),
    }

    def __init__(self, parent, **kw):
        super().__init__(parent, bg="#010208", highlightthickness=0, **kw)
        self._state = "idle"
        self._t = 0.0
        self._disk = 0.0
        self._alive = True
        self._W = 800
        self._H = 600
        self._cx = 400
        self._cy = 300
        self._stars = []
        self._dust = []
        self._rebuild_particles()
        self.bind("<Configure>", self._on_resize)
        self._draw()

    def _on_resize(self, e):
        self._W = e.width
        self._H = e.height
        self._cx = self._W // 2
        self._cy = self._H // 2
        self._rebuild_particles()

    def _rebuild_particles(self):
        s = min(self._W, self._H)
        self._stars = [
            (random.randint(0, self._W), random.randint(0, self._H),
             random.uniform(0.2, 1.0),
             random.choice(["#1A2040", "#2A3060", "#3A4080", "#8892A8", "#E8ECF4"]))
            for _ in range(200)
        ]
        self._dust = [
            {"a": random.uniform(0, 360),
             "r": s * random.uniform(0.22, 0.42),
             "s": random.uniform(0.08, 0.35) * random.choice([1, -1]),
             "sz": random.uniform(0.6, 1.8),
             "col": random.choice(["#2A2040", "#3A2848", "#4A3858"])}
            for _ in range(60)
        ]

    def set_state(self, st):
        self._state = st if st in self.STATE_COLORS else "idle"

    def destroy_loop(self):
        self._alive = False

    def _draw(self):
        if not self._alive:
            return
        self.delete("all")
        col, speed = self.STATE_COLORS.get(self._state, ("#E8C8A0", 0.15))
        cx, cy = self._cx, self._cy
        s = min(self._W, self._H)

        self._t = (self._t + 0.04) % (2 * math.pi)
        self._disk = (self._disk + speed * 0.3) % 360

        # ── stars ──
        for x, y, br, sc in self._stars:
            tw = 0.5 + 0.5 * math.sin(self._t * 0.7 + x * 0.02 + y * 0.015)
            a = br * tw
            if a < 0.25:
                continue
            sz = 0.5 + a * 0.7
            self.create_oval(x - sz, y - sz, x + sz, y + sz, fill=sc, outline="")

        # ── outer diffuse glow ──
        for i in range(8):
            r = int(s * (0.38 + i * 0.012))
            fade = max(0, 0.06 - i * 0.007)
            g = f"#{int(232*fade):02x}{int(200*fade):02x}{int(160*fade):02x}"
            self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=g, width=2)

        # ── accretion disk (dual Fire & Ice vortex) ──
        disk_r = int(s * 0.34)
        # base ring
        self.create_oval(cx - disk_r, cy - disk_r, cx + disk_r, cy + disk_r,
                         outline="#081020", width=max(4, int(s * 0.035)))
        # rotating segments with dual fire (top/right) & ice (bottom/left)
        n_seg = 36
        for i in range(n_seg):
            seg = (i * (360 / n_seg) + self._disk) % 360
            is_fire = (seg > 30 and seg < 210) # Top & Right arc
            phase = math.sin(math.radians(seg + self._disk * 0.5))
            b = 0.3 + 0.7 * max(0, phase)
            if is_fire:
                rv = int(220 + 35 * b)
                gv = int(90 + 90 * b)
                bv = int(10 + 40 * b)
            else:
                rv = int(10 + 40 * b)
                gv = int(160 + 80 * b)
                bv = int(220 + 35 * b)
            sc = f"#{min(255,rv):02x}{min(255,gv):02x}{min(255,bv):02x}"
            w = max(2, int(s * 0.009 * (0.5 + b * 0.8)))
            self._arc(disk_r, seg, 360 / n_seg - 1, sc, width=w)

        # bright accent arcs matching reference hotspots
        # Top-right solar flare hotspot
        self._arc(disk_r, (self._disk + 60) % 360, 45, "#FFAA20", width=max(3, int(s * 0.006)))
        self._arc(disk_r, (self._disk + 80) % 360, 20, "#FFFFFF", width=max(2, int(s * 0.004)))
        # Bottom-left cyan wave
        self._arc(disk_r, (self._disk + 240) % 360, 45, "#00E5FF", width=max(3, int(s * 0.005)))
        self._arc(disk_r, (self._disk + 260) % 360, 20, "#C0FFFF", width=max(2, int(s * 0.003)))

        # ── inner ring ──
        ir = int(s * 0.28)
        self.create_oval(cx - ir, cy - ir, cx + ir, cy + ir, outline="#050814", width=max(2, int(s * 0.015)))
        self._arc(ir, (self._disk * 1.2) % 360, 60, "#FF8800", width=max(2, int(s * 0.003)))
        self._arc(ir, (self._disk * 1.2 + 180) % 360, 60, "#00D4FF", width=max(2, int(s * 0.003)))

        # ── event horizon (absolute black void) ──
        for r_mul, fc in [(0.22, "#01040a"), (0.20, "#010206"), (0.18, "#000102"), (0.16, "#000000")]:
            rv = int(s * r_mul)
            self.create_oval(cx - rv, cy - rv, cx + rv, cy + rv, fill=fc, outline="")

        # ── photon ring ──
        ph_r = int(s * 0.19) + int(math.sin(self._t * 0.5) * 2)
        self.create_oval(cx - ph_r, cy - ph_r, cx + ph_r, cy + ph_r, outline="#003366", width=1)
        self._arc(ph_r, (self._t * 15) % 360, 40, "#00F0FF", width=max(2, int(s * 0.003)))
        self._arc(ph_r, (self._t * 15 + 180) % 360, 35, "#FFB800", width=max(2, int(s * 0.003)))
        self._arc(ph_r, (self._t * 15 + 90) % 360, 20, "#FFFFFF", width=max(1, int(s * 0.002)))

        # ── dust ──
        for d in self._dust:
            d["a"] = (d["a"] + d["s"]) % 360
            ang = math.radians(d["a"])
            px = cx + d["r"] * math.cos(ang)
            py = cy + d["r"] * math.sin(ang)
            dist = abs((d["a"] - self._disk) % 360)
            br = 1.0 if dist < 25 else (0.45 if dist < 70 else 0.15)
            sz = d["sz"] * (0.5 + br * 0.8)
            self.create_oval(px - sz, py - sz, px + sz, py + sz, fill=d["col"], outline="")

        # ── singularity ──
        cr = max(1.0, s * 0.003) + math.sin(self._t * 1.5) * 0.5
        self.create_oval(cx - cr, cy - cr, cx + cr, cy + cr, fill="#FFFFFF", outline="")
        for i in range(3):
            gr = cr + 2 + i * 2
            ga = max(0, 0.25 - i * 0.08)
            gc = f"#{int(232*ga):02x}{int(200*ga):02x}{int(160*ga):02x}"
            self.create_oval(cx - gr, cy - gr, cx + gr, cy + gr, outline=gc, width=1)

        # ── state effects ──
        if self._state == "speaking":
            for i in range(5):
                wr = int(s * 0.2) + i * int(s * 0.035) + int(math.sin(self._t * 2 + i) * 4)
                wa = max(0, 0.12 - i * 0.02)
                wc = f"#{int(232*wa):02x}{int(200*wa):02x}{int(160*wa):02x}"
                self.create_oval(cx - wr, cy - wr, cx + wr, cy + wr, outline=wc, width=1)
        elif self._state == "listening":
            for i in range(3):
                pr = int(s * 0.195) + i * int(s * 0.025) + int(math.sin(self._t * 1.5 + i * 2) * 3)
                pa = max(0, 0.18 - i * 0.05)
                pc = f"#{int(255*pa):02x}{int(200*pa):02x}{int(100*pa):02x}"
                self.create_oval(cx - pr, cy - pr, cx + pr, cy + pr, outline=pc, width=1)
        elif self._state == "processing":
            for i in range(4):
                a0 = (self._disk * 2 + i * 90) % 360
                self._arc(int(s * 0.21), a0, 30, col, width=1)
        elif self._state == "error":
            er = int(s * 0.20) + int(math.sin(self._t * 3) * 5)
            self.create_oval(cx - er, cy - er, cx + er, cy + er, outline="#FF4040", width=1)

        self.after(33, self._draw)

    def _arc(self, r, start, extent, color, width=1):
        cx, cy = self._cx, self._cy
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=start, extent=extent, outline=color, width=width, style=tk.ARC)


# ═══════════════════════════════════════════════════════════════════════════
#  GLASS PANEL — base for floating panels
# ═══════════════════════════════════════════════════════════════════════════
class GlassPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        kw.setdefault("fg_color", "#080C16")
        kw.setdefault("border_color", "#1A1E30")
        kw.setdefault("border_width", 1)
        kw.setdefault("corner_radius", 14)
        super().__init__(parent, **kw)


# ═══════════════════════════════════════════════════════════════════════════
#  LOG PANEL — floating right
# ═══════════════════════════════════════════════════════════════════════════
class LogPanel(GlassPanel):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(hdr, text="REGISTRO", font=F_XS, text_color=C["text3"]).pack(side="left")
        self._live = ctk.CTkLabel(hdr, text="●  EN VIVO", font=F_XS, text_color=C["emerald"])
        self._live.pack(side="right")
        ctk.CTkFrame(self, height=1, fg_color=C["sep"]).pack(fill="x", padx=10)
        self._box = ctk.CTkTextbox(self, fg_color="#010208", text_color=C["text"], font=F_MS,
                                   wrap="word", border_width=0, corner_radius=8,
                                   scrollbar_button_color=C["border"], scrollbar_button_hover_color=C["border_hi"])
        self._box.pack(fill="both", expand=True, padx=6, pady=(4, 6))
        self._box.configure(state="disabled")
        self._tags = False

    def _ensure_tags(self):
        if self._tags:
            return
        try:
            tb = self._box._textbox
            tb.tag_config("ts", foreground="#3A3050")
            tb.tag_config("user", foreground="#7DD3FC")
            tb.tag_config("jarvis", foreground="#C4B5FD")
            tb.tag_config("sys", foreground="#6B7280")
            self._tags = True
        except Exception:
            pass

    def log(self, msg):
        self._ensure_tags()
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        kind = "sys"
        if msg.startswith("USUARIO"):
            kind = "user"
        elif msg.startswith("JARVIS"):
            kind = "jarvis"
        self._box.configure(state="normal")
        try:
            tb = self._box._textbox
            tb.insert("end", f"[{ts}] ", "ts")
            tb.insert("end", msg + "\n", kind)
        except Exception:
            self._box.insert("end", f"[{ts}] {msg}\n")
        self._box.see("end")
        self._box.configure(state="disabled")


# ═══════════════════════════════════════════════════════════════════════════
#  TELEMETRY PANEL — floating left, real-time system metrics
# ═══════════════════════════════════════════════════════════════════════════
class TelemetryPanel(GlassPanel):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(hdr, text="TELEMETRÍA", font=F_XS, text_color=C["text3"]).pack(side="left")
        self._live = ctk.CTkLabel(hdr, text="●  LIVE", font=F_XS, text_color=C["emerald"])
        self._live.pack(side="right")
        ctk.CTkFrame(self, height=1, fg_color=C["sep"]).pack(fill="x", padx=10)

        self._metrics = {}

        # CPU
        self._add_metric_row("CPU", "--%", "cpu")
        self._add_core_bars("cpu_cores")

        # RAM
        self._add_metric_row("RAM", "--%", "ram")

        # Disk
        self._add_metric_row("DISCO", "-- GB", "disk")

        # Network
        self._add_metric_row("RED ↑", "-- MB/s", "net_up")
        self._add_metric_row("RED ↓", "-- MB/s", "net_down")

        # Temperature
        self._add_metric_row("TEMP", "--°C", "temp")

        # Battery
        self._add_metric_row("BAT", "--%", "battery")

        # MCP Status
        ctk.CTkFrame(self, height=1, fg_color=C["sep"]).pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(self, text="MCP SERVERS", font=F_XS, text_color=C["accent"]).pack(anchor="w", padx=10)
        self._mcp_labels = {}
        for name in ("ha", "calendar", "android"):
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(row, text=name.upper(), font=F_SS, text_color=C["text2"], width=60).pack(side="left")
            lbl = ctk.CTkLabel(row, text="●", font=F_SS, text_color=C["text3"], width=10)
            lbl.pack(side="left", padx=4)
            ctk.CTkLabel(row, text="desconocido", font=F_SS, text_color=C["text3"]).pack(side="left")
            self._mcp_labels[name] = lbl

    def _add_metric_row(self, label: str, value: str, key: str):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(row, text=label, font=F_SS, text_color=C["text2"], width=55).pack(side="left")
        val = ctk.CTkLabel(row, text=value, font=("Consolas", 9, "bold"), text_color=C["text"])
        val.pack(side="right")
        self._metrics[key] = val

    def _add_core_bars(self, key: str):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 4))
        self._metrics[key] = row
        self._core_bars = []
        for i in range(8):  # max 8 cores shown
            bar = ctk.CTkProgressBar(row, width=22, height=4, progress_color=C["accent"],
                                     fg_color=C["border"], corner_radius=2)
            bar.set(0)
            bar.pack(side="left", padx=1)
            self._core_bars.append(bar)

    def update_metrics(self, stats: dict):
        """Actualiza con dict de jarvis_core.get_system_stats()"""
        try:
            # CPU
            cpu = stats.get("cpu", "--")
            self._metrics["cpu"].configure(text=f"{cpu}")
            # Cores
            cores = stats.get("cpu_cores", [])
            for i, bar in enumerate(self._core_bars):
                if i < len(cores):
                    bar.set(float(cores[i]) / 100.0)
                else:
                    bar.set(0)

            # RAM
            ram_pct = stats.get("ram_pct", "--")
            ram_used = stats.get("ram_used", "--")
            self._metrics["ram"].configure(text=f"{ram_pct} ({ram_used})")

            # Disk
            disk_free = stats.get("disk_free", "--")
            self._metrics["disk"].configure(text=f"{disk_free} GB libre")

            # Network
            self._metrics["net_up"].configure(text=f"{stats.get('net_sent', '--')} MB/s")
            self._metrics["net_down"].configure(text=f"{stats.get('net_recv', '--')} MB/s")

            # Temp
            self._metrics["temp"].configure(text=stats.get("temp", "--"))

            # Battery
            bat = stats.get("battery")
            if bat:
                pct = bat.get("percent", "--")
                plugged = "🔌" if bat.get("plugged") else "🔋"
                self._metrics["battery"].configure(text=f"{pct}% {plugged}")
            else:
                self._metrics["battery"].configure(text="N/A")

        except Exception:
            pass

    def update_mcp_status(self, name: str, online: bool):
        if name in self._mcp_labels:
            self._mcp_labels[name].configure(
                text_color=C["emerald"] if online else C["red"]
            )


# ═══════════════════════════════════════════════════════════════════════════
#  COMMANDS PANEL — floating left, collapsible
# ═══════════════════════════════════════════════════════════════════════════
class CmdPanel(GlassPanel):
    CATALOGO = [
        ("VIDEO Y CAPTURAS", [
            ("Descargar video", "descarga este video {p}", True, "URL del video"),
            ("Descargar música", "descarga la musica {p}", True, "Nombre o artista"),
            ("Resumir video", "resume {p}", True, "URL del video"),
            ("Captura de pantalla", "captura la pantalla", False, None),
            ("OCR de pantalla", "lee el texto de la pantalla", False, None),
        ]),
        ("MÚSICA", [
            ("Reproducir música", "pon musica {p}", True, "Ej: rock, los 80"),
            ("Parar música", "para la musica", False, None),
            ("Abrir Spotify", "abre spotify", False, None),
            ("Radio", "pon la radio", False, None),
            ("Subir volumen", "sube el volumen", False, None),
            ("Bajar volumen", "baja el volumen", False, None),
        ]),
        ("TIEMPO Y OCIO", [
            ("Clima", "dame el clima de hoy", False, None),
            ("Noticias", "dame las noticias", False, None),
            ("Hora", "que hora es", False, None),
        ]),
        ("ORGANIZACIÓN", [
            ("Recordatorio", "recuerdame {p}", True, "Qué recordar"),
            ("Alarma", "pon una alarma a las {p}", True, "Hora"),
            ("Temporizador", "pon un temporizador de {p} min", True, "Minutos"),
            ("Nota", "anota {p}", True, "Texto"),
            ("Lista de tareas", "lista mis tareas", False, None),
            ("Agenda", "agenda {p}", True, "Evento"),
        ]),
        ("BUSCAR Y CREAR", [
            ("Buscar", "busca en internet {p}", True, "Términos"),
            ("Investigar", "investiga {p}", True, "Tema"),
            ("Traducir", "traduce al ingles {p}", True, "Texto"),
            ("Resumir", "resume {p}", True, "Texto o URL"),
            ("QR", "genera un codigo qr para {p}", True, "Texto o URL"),
            ("Calculadora", "cuanto es {p}", True, "Ej: 15*7"),
        ]),
        ("PC Y SISTEMA", [
            ("Estado del PC", "dame el estado del pc", False, None),
            ("Procesos", "que procesos pesan mas", False, None),
            ("Batería", "dame el estado de la bateria", False, None),
            ("Red", "dame el estado de la red", False, None),
        ]),
        ("CEREBRO", [
            ("Probar cerebro", "prueba tu cerebro", False, None),
            ("Limpiar memoria", "limpia tu memoria", False, None),
            ("Historial", "que hicimos hoy", False, None),
        ]),
        ("EXTRAS", [
            ("Chiste", "cuentame un chiste", False, None),
            ("Quiz", "hazme una pregunta", False, None),
            ("Curiosidad", "dame una curiosidad", False, None),
        ]),
        ("REFRIGERACIÓN", [
            ("Refrigerar PC", "refrigeracion", False, None),
            ("Parar refrigeración", "para la refrigeracion", False, None),
            ("Estado temperaturas", "dame la temperatura", False, None),
        ]),
    ]

    def __init__(self, parent, on_command=None, **kw):
        super().__init__(parent, **kw)
        self._cmd = on_command
        self._visible = True
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(hdr, text="ACCIONES", font=F_XS, text_color=C["text3"]).pack(side="left")
        self._toggle_btn = ctk.CTkButton(hdr, text="◀", width=20, height=20, corner_radius=4,
                                         fg_color="transparent", hover_color=C["glass2"],
                                         text_color=C["text3"], font=F_XS, command=self.toggle)
        self._toggle_btn.pack(side="right")
        ctk.CTkFrame(self, height=1, fg_color=C["sep"]).pack(fill="x", padx=10)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                              scrollbar_button_color=C["border"],
                                              scrollbar_button_hover_color=C["border_hi"])
        self._scroll.pack(fill="both", expand=True, padx=4, pady=4)

        row = 0
        for header, items in self.CATALOGO:
            ctk.CTkLabel(self._scroll, text=header, font=F_XS, text_color=C["accent"],
                         anchor="w").grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 2))
            row += 1
            ctk.CTkFrame(self._scroll, height=1, fg_color=C["sep"]).grid(
                row=row, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 3))
            row += 1
            col = 0
            for label, cmd, needs, prompt in items:
                prefix = "› " if needs else ""
                btn = ctk.CTkButton(
                    self._scroll, text=prefix + label, font=F_SS,
                    fg_color=C["glass2"], hover_color="#141828",
                    text_color=C["text"], border_width=1, border_color=C["border"],
                    corner_radius=6, height=26,
                    command=lambda c=cmd, n=needs, p=prompt: self._run(c, n, p))
                btn.grid(row=row, column=col, sticky="ew", padx=2, pady=2)
                col ^= 1
                if col == 0:
                    row += 1
            if col:
                row += 1
        self._scroll.grid_columnconfigure(0, weight=1)
        self._scroll.grid_columnconfigure(1, weight=1)

    def toggle(self):
        if self._visible:
            self.pack_forget()
            self._visible = False
        else:
            self.pack(side="left", fill="y", padx=(0, 6))
            self._visible = True

    def _run(self, cmd, needs, prompt):
        if needs:
            dlg = ctk.CTkInputDialog(text=prompt or "Dato:", title="J.A.R.V.I.S.",
                                     button_text="Enviar", fg_color=C["glass"],
                                     button_fg_color=C["border"], button_hover_color=C["border_hi"],
                                     entry_fg_color="#010208", entry_border_color=C["border"],
                                     entry_text_color=C["text"])
            val = dlg.get_input()
            if not val or not val.strip():
                return
            val = val.strip()
            if "{p2}" in cmd:
                m = re.search(r"^(.*?)\s+(\d+(?:[.,]\d+)?)\s*$", val)
                if m:
                    cmd = cmd.replace("{p}", m.group(1).strip()).replace("{p2}", m.group(2).replace(",", "."))
                else:
                    return
            else:
                cmd = cmd.replace("{p}", val)
        if self._cmd:
            self._cmd(cmd)


# ═══════════════════════════════════════════════════════════════════════════
#  INPUT BAR — floating bottom center
# ═══════════════════════════════════════════════════════════════════════════
class InputBar(GlassPanel):
    def __init__(self, parent, on_text, on_voice, **kw):
        kw.setdefault("height", 56)
        super().__init__(parent, **kw)
        self.pack_propagate(False)
        self._on_text = on_text
        self._on_voice = on_voice
        self._build()

    def _build(self):
        self.btn_voice = ctk.CTkButton(
            self, text="◉", width=38, height=38, corner_radius=19,
            font=("Segoe UI", 14), fg_color=C["accent"], hover_color="#D4A574",
            text_color="#010208", command=self._on_voice)
        self.btn_voice.pack(side="left", padx=(10, 6), pady=9)

        self.entry = ctk.CTkEntry(
            self, placeholder_text="Habla con Jarvis…",
            fg_color="#010208", border_color=C["border"], text_color=C["text"],
            placeholder_text_color=C["text3"], font=F_S, corner_radius=20, height=38)
        self.entry.pack(side="left", fill="x", expand=True, padx=4, pady=9)
        self.entry.bind("<Return>", lambda e: self._on_text())

        self.btn_send = ctk.CTkButton(
            self, text="→", width=38, height=38, corner_radius=19,
            font=("Segoe UI", 14, "bold"), fg_color=C["glass2"], hover_color=C["border_hi"],
            text_color=C["accent"], border_width=1, border_color=C["border"],
            command=self._on_text)
        self.btn_send.pack(side="right", padx=(6, 10), pady=9)

    def set_busy(self, busy):
        st = "disabled" if busy else "normal"
        self.btn_voice.configure(state=st)
        self.btn_send.configure(state=st)
        self.entry.configure(state=st)


# ═══════════════════════════════════════════════════════════════════════════
#  MINI STATUS — floating top center
# ═══════════════════════════════════════════════════════════════════════════
class MiniStatus(GlassPanel):
    def __init__(self, parent, **kw):
        kw.setdefault("height", 36)
        super().__init__(parent, **kw)
        self.pack_propagate(False)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="J.A.R.V.I.S.", font=("Segoe UI", 10, "bold"),
                     text_color=C["text"]).pack(side="left", padx=(10, 4))
        self._dot = ctk.CTkLabel(self, text="●", font=F_XS, text_color=C["emerald"])
        self._dot.pack(side="left", padx=2)
        self._pulse(True)
        ctk.CTkLabel(self, text="  ·  COSMIC  v3", font=F_XS, text_color=C["text3"]).pack(side="left")
        self._time = ctk.CTkLabel(self, text="", font=F_M, text_color=C["text2"])
        self._time.pack(side="right", padx=10)
        host = socket.gethostname()[:12]
        ctk.CTkLabel(self, text=host, font=F_MS, text_color=C["text3"]).pack(side="right")
        self._tick()

    def _pulse(self, on):
        try:
            self._dot.configure(text_color=C["emerald"] if on else "#0B3A2A")
        except Exception:
            pass
        self.after(900, lambda: self._pulse(not on))

    def _tick(self):
        self._time.configure(text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._tick)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════
class JarvisUI:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self._events = queue.Queue()
        self._active = False
        self._closing = False

        root.title("J.A.R.V.I.S. — COSMIC")
        root.geometry("1280x800")
        root.minsize(900, 600)
        root.configure(fg_color="#010208")
        ctk.set_appearance_mode("Dark")

        # Black hole fills entire window
        self.canvas = BlackHoleCanvas(root)
        self.canvas.pack(fill="both", expand=True)

        # Floating panels are placed ON TOP of the canvas
        self._build_panels()

        # Core
        self.core = JarvisCore(
            log_callback=lambda m: self._post("log", m),
            hotkey_callback=lambda: self._post("voice"))
        self._log("COSMIC iniciado. Núcleo Qwen3 · Piper · Red activos.")
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._drain()

    def _build_panels(self):
        # Status bar — top center, floating
        self.status = MiniStatus(self.canvas)
        self.canvas.create_window(self.canvas._cx, 22, window=self.status, anchor="center")

        # Telemetry — left side, floating (below commands area)
        self.telemetry = TelemetryPanel(self.canvas, width=260)
        self.telemetry.place(relx=0.0, rely=0.55, x=14, y=0, anchor="nw")

        # Log — right side, floating
        self.log_panel = LogPanel(self.canvas, width=280)
        self.log_panel.place(relx=1.0, rely=0.08, x=-14, y=0, anchor="ne")

        # Commands — left side, floating
        self.cmd_panel = CmdPanel(self.canvas, width=260, on_command=self._run_cmd)
        self.cmd_panel.place(relx=0.0, rely=0.08, x=14, y=0, anchor="nw")

        # Input — bottom center, floating
        self.input_bar = InputBar(self.canvas, on_text=self._on_send, on_voice=self._on_voice)
        self.input_bar.place(relx=0.5, rely=1.0, y=-14, anchor="s")

        # Re-anchor on resize
        self.canvas.bind("<Configure>", self._reanchor, add="+")

        # Start telemetry loop
        self._telemetry_loop()

    def _reanchor(self, e=None):
        cx = self.canvas._cx
        cy = self.canvas._cy
        try:
            self.canvas.coords(self.canvas._winfo_children()[0], cx, 22)
        except Exception:
            pass

    def _post(self, action, payload=None):
        if not self._closing:
            self._events.put((action, payload))

    def _log(self, msg):
        self._post("log", msg)

    def _drain(self):
        while True:
            try:
                act, pay = self._events.get_nowait()
            except queue.Empty:
                break
            if act == "log":
                self.log_panel.log(str(pay))
            elif act == "state":
                self.canvas.set_state(str(pay))
            elif act == "voice":
                self._on_voice()
            elif act == "finish":
                self.canvas.set_state("idle")
                self.input_bar.set_busy(False)
                self._active = False
            elif act == "telemetry":
                self.telemetry.update_metrics(pay)
        if not self._closing:
            self.root.after(50, self._drain)

    def _telemetry_loop(self):
        """Actualiza telemetría cada 2 segundos"""
        def _loop():
            if self._closing:
                return
            try:
                stats = self.core.get_system_stats()
                self._post("telemetry", stats)
            except Exception:
                pass
            if not self._closing:
                self.root.after(2000, _loop)
        self.root.after(2000, _loop)

    def _on_send(self):
        if self._active:
            return
        text = self.input_bar.entry.get().strip()
        if not text:
            return
        self._active = True
        self.input_bar.entry.delete(0, "end")
        self._log(f"USUARIO: {text}")
        self.input_bar.set_busy(True)
        threading.Thread(target=self._pipeline, args=(text,), daemon=True).start()

    def _on_voice(self):
        if self._active:
            return
        self._active = True
        self._log("Activando micrófono…")
        self.input_bar.set_busy(True)
        threading.Thread(target=self._voice_pipeline, daemon=True).start()

    def _run_cmd(self, text):
        if self._active:
            return
        text = text.strip()
        if not text:
            return
        self._active = True
        self._log(f"USUARIO [COMANDO]: {text}")
        threading.Thread(target=self._pipeline, args=(text,), daemon=True).start()

    def _voice_pipeline(self):
        self._set_state("listening")
        text = self.core.listen()
        if text:
            self._log(f"USUARIO [VOZ]: {text}")
            if self.core.dictado_activo():
                if self.core.dictar(text):
                    self._log(f"DICTADO: {text}")
                else:
                    self._log("No pude escribir el dictado.")
                self._post("finish")
                return
            self._pipeline(text)
        else:
            self._log("No se detectó voz.")
            self._post("finish")

    def _pipeline(self, text):
        self._set_state("processing")
        try:
            reply = self.core.process_text_stream(text, state_callback=self._set_state)
            self._log(f"JARVIS: {reply}")
        except Exception as e:
            self._log(f"Error: {e}")
            self._set_state("error")
        finally:
            self._post("finish")

    def _set_state(self, st):
        self._post("state", st)

    def _on_close(self):
        self._closing = True
        self.core.shutdown()
        self.canvas.destroy_loop()
        self.root.quit()
        self.root.destroy()


def main():
    root = ctk.CTk()
    JarvisUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
