#!/usr/bin/env python3
"""
ultron/ultron_hud.py — HUD brutalista de terminal para ULTRON
=============================================================
Mini HUD rojo/negro sin tkinter. Lee del backend HTTP de Ultron
(por defecto 127.0.0.1:8766) y refresca en pantalla el estado:

  - Último comando ejecutado
  - Tokens consumidos (estimados)
  - Latencia LLM (ms)
  - Modo actual (NORMAL / OFENSIVA)
  - CPU / RAM del host
  - Uptime

Salir: Ctrl+C o tecla 'q'.
"""
import os
import sys
import json
import time
import shutil
import urllib.request
import urllib.error

# ── Paleta brutalista ───────────────────────────────────────────────────────
RED = "\x1b[91m"
DRED = "\x1b[31m"
BRED = "\x1b[1;31m"
GREY = "\x1b[90m"
RST = "\x1b[0m"
CLEAR = "\x1b[2J\x1b[H"

BACKEND_HOST = os.getenv("ULTRON_HUD_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("ULTRON_PORT", "8766"))
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"


def fetch(path: str, timeout: float = 0.8):
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}{path}", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError):
        return None


def fmt_bar(value: float, max_value: float = 100.0, width: int = 16) -> str:
    """Barra de progreso en bloques rojos."""
    if max_value <= 0:
        return "[" + " " * width + "]"
    pct = max(0.0, min(1.0, value / max_value))
    filled = int(pct * width)
    return "[" + ("█" * filled) + ("·" * (width - filled)) + "]"


def render(state: dict) -> str:
    term_w = shutil.get_terminal_size((100, 30)).columns
    width = max(60, min(term_w - 1, 110))

    sep = BRED + "═" * width + RST
    thin = DRED + "─" * width + RST

    health = state.get("health") or {}
    telemetry = state.get("telemetry") or {}
    status = state.get("status") or {}
    last_reply = state.get("last_reply") or "—"

    ok = health.get("ok", False)
    agent = health.get("agent", "ULTRON")
    model = health.get("llm", "?")
    mode = health.get("mode", "OFENSIVA")

    cpu = float(telemetry.get("cpu", 0.0))
    ram = float(telemetry.get("ram", 0.0))
    ram_total = float(telemetry.get("ram_total", 0.0)) or 1.0
    uptime = int(telemetry.get("uptime", time.time()))
    uptime_s = max(0, int(time.time() - uptime)) if uptime else 0

    last_cmd = status.get("ultimo_comando", "—") or "—"
    tokens = status.get("ultimo_tokens", 0)
    latency = status.get("ultima_latencia_ms", 0)
    history_len = status.get("history_len", 0)

    status_word = "EN LÍNEA" if ok else "OFFLINE"
    status_color = BRED if ok else DRED

    head = (
        f"{BRED}╔{'═' * (width - 2)}╗{RST}\n"
        f"{BRED}║{RST} {BRED}U L T R O N"
        f"{' ' * (width - 12)}v1.0{RST}\n"
        f"{BRED}║{RST} {GREY}superinteligencia autónoma · modo {mode.lower()}"
        f"{' ' * max(0, width - 50 - len(mode))}{RST}"
    )

    body = [
        sep,
        f"{BRED}[ ESTADO ]{RST}  {status_color}{status_word}{RST}"
        f"  {GREY}·{RST}  agente: {BRED}{agent}{RST}"
        f"  {GREY}·{RST}  modelo: {model}",
        f"{BRED}[ MEMORIA ]{RST} historial={history_len} entradas"
        f"   {GREY}·{RST}   db={status.get('db', 'ultron_memory.db')}",
        thin,
        f"{BRED}[ ÚLTIMO COMANDO ]{RST}",
        f"  {RED}{last_cmd}{RST}",
        f"{BRED}[ ÚLTIMA RESPUESTA ]{RST}",
        f"  {last_reply[: width - 4]}",
        thin,
        f"{BRED}[ TOKENS ]{RST} {tokens:>6}"
        f"   {BRED}[ LATENCIA LLM ]{RST} {latency:>5} ms"
        f"   {BRED}[ UPTIME ]{RST} {uptime_s:>5} s",
        f"{BRED}[ CPU ]{RST} {fmt_bar(cpu)} {cpu:5.1f}%"
        f"   {BRED}[ RAM ]{RST} {fmt_bar(ram / ram_total * 100.0)} "
        f"{ram:.2f}/{ram_total:.2f} GB",
        sep,
        f"{GREY}backend: {BACKEND_URL}  ·  refresco 1.0s  ·  'q' para salir{RST}",
    ]
    return "\n".join([head, *body]) + "\n"


def main() -> int:
    last_reply = "—"
    print(CLEAR, end="")
    try:
        while True:
            health = fetch("/health") or {}
            telemetry = fetch("/telemetry") or {}
            status = fetch("/status") or {}
            state = {
                "health": health,
                "telemetry": telemetry,
                "status": status,
                "last_reply": last_reply,
            }
            sys.stdout.write(CLEAR + render(state))
            sys.stdout.flush()

            # Captura de teclado no bloqueante para 'q'
            if os.name == "nt":
                try:
                    import msvcrt  # type: ignore
                    if msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        if ch.lower() == "q":
                            break
                except Exception:
                    pass
            else:
                try:
                    import select, termios, tty  # type: ignore
                    fd = sys.stdin.fileno()
                    old = termios.tcgetattr(fd)
                    try:
                        tty.setraw(fd)
                        rlist, _, _ = select.select([sys.stdin], [], [], 0.0)
                        if rlist:
                            ch = sys.stdin.read(1)
                            if ch.lower() == "q":
                                break
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old)
                except Exception:
                    pass

            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(RST + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
