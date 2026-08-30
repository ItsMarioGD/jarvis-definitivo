#!/usr/bin/env python3
"""
jarvis_mcp_server.py - Servidor MCP (Model Context Protocol) de Jarvis
Expone las capacidades de Jarvis como herramientas estándar MCP para
cualquier cliente compatible (Claude Desktop, agentes, etc.).

Uso:
    python jarvis_mcp_server.py            # modo stdio (MCP estándar)
    python jarvis_mcp_server.py --http 5001 # modo HTTP ligero para pruebas
"""
import sys, json, os, time, secrets
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis_skills import SkillsManager
import jarvis_redact


class JarvisMcpTools:
    """Herramientas expuestas por Jarvis vía MCP."""

    def __init__(self):
        self.skills = SkillsManager(log=self._silent)
        self._db_path = Path(__file__).resolve().parent / "jarvis_memory.db"

    @staticmethod
    def _silent(*a, **k):
        pass

    def _query(self, sql, params=()):
        import sqlite3
        conn = sqlite3.connect(str(self._db_path), timeout=5)
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    # ── Herramientas ────────────────────────────────────────────────────────
    def ejecutar_habilidad(self, texto: str) -> str:
        """Ejecuta una habilidad del sistema (abrir apps, volumen, clima,
        notas, temporizadores, captura, portapapeles, hora, batería, etc.).
        Devuelve la respuesta del mayordomo o aviso de que no es habilidad."""
        resp = self.skills.handle(texto)
        if resp:
            return resp
        return "No es una habilidad del sistema; sería conversación normal del LLM."

    def guardar_memoria(self, rol: str, contenido: str) -> str:
        """Guarda un mensaje en la memoria persistente de Jarvis."""
        rol = rol if rol in ("user", "assistant") else "user"
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        contenido = jarvis_redact.redact(contenido)
        self._query("INSERT INTO interactions (timestamp, role, content) VALUES (?, ?, ?)",
                    (ts, rol, contenido[:4000]))
        return f"Memoria guardada ({rol})."

    def leer_memoria(self, limite: int = 8) -> str:
        """Recupera las últimas interacciones guardadas en memoria."""
        rows = self._query(
            "SELECT role, content FROM interactions ORDER BY id DESC LIMIT ?",
            (min(max(limite, 1), 20),))
        if not rows:
            return "No hay memoria guardada."
        return "\n".join(f"[{r}]: {c[:200]}" for r, c in reversed(rows))

    def estadisticas_sistema(self) -> str:
        """Devuelve CPU, RAM, disco y red en tiempo real."""
        import psutil
        cpu = psutil.cpu_percent(interval=0.3)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        net = psutil.net_io_counters()
        return (f"CPU: {cpu:.0f}% | RAM: {ram.used/1e9:.1f}/{ram.total/1e9:.1f} GB "
                f"({ram.percent:.0f}%) | Disco libre: {disk.free/1e9:.0f} GB | "
                f"Red: subida {net.bytes_sent/1e6:.0f}MB bajada {net.bytes_recv/1e6:.0f}MB")

    def guardar_archivo(self, nombre: str, contenido: str) -> str:
        """Genera un archivo de texto en la carpeta Descargas/JARVIS/Generaciones/Documentos."""
        base = Path(os.path.expanduser("~")) / "Descargas" / "JARVIS" / "Generaciones" / "Documentos"
        fecha = time.strftime("%Y-%m-%d")
        d = base / fecha
        d.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in nombre if c.isalnum() or c in " ._-")[:60] or "archivo.txt"
        path = d / safe
        path.write_text(contenido, encoding="utf-8")
        return f"Archivo guardado: {path}"


def main_stdio():
    """Modo MCP estándar: JSON-RPC 2.0 por stdio."""
    tools = JarvisMcpTools()
    CATALOG = {
        "ejecutar_habilidad": {"description": "Ejecuta habilidades del sistema de Jarvis", "params": {"texto": "str"}},
        "guardar_memoria": {"description": "Guarda un mensaje en memoria persistente", "params": {"rol": "str", "contenido": "str"}},
        "leer_memoria": {"description": "Recupera últimas interacciones", "params": {"limite": "int"}},
        "estadisticas_sistema": {"description": "CPU/RAM/disco/red en tiempo real", "params": {}},
        "guardar_archivo": {"description": "Guarda un archivo de texto", "params": {"nombre": "str", "contenido": "str"}},
    }
    IMPL = {
        "ejecutar_habilidad": tools.ejecutar_habilidad,
        "guardar_memoria": tools.guardar_memoria,
        "leer_memoria": tools.leer_memoria,
        "estadisticas_sistema": tools.estadisticas_sistema,
        "guardar_archivo": tools.guardar_archivo,
    }
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg_id = msg.get("id")
        method = msg.get("method", "")
        if method == "initialize":
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"protocolVersion": "2025-03-26", "serverInfo": {"name": "jarvis-mcp", "version": "1.0.0"},
                           "capabilities": {"tools": {"listChanged": False}}},
            }) + "\n")
        elif method == "tools/list":
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": [
                    {"name": k, "description": v["description"],
                     "inputSchema": {"type": "object", "properties": {p: {"type": "string"} for p in v["params"]}}}
                    for k, v in CATALOG.items()]},
            }) + "\n")
        elif method == "tools/call":
            name = msg.get("params", {}).get("name", "")
            args = msg.get("params", {}).get("arguments", {})
            fn = IMPL.get(name)
            if not fn:
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id,
                                             "error": {"code": -32601, "message": f"Herramienta desconocida: {name}"}}) + "\n")
                continue
            try:
                result = fn(**args) if isinstance(args, dict) else fn()
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id,
                                             "result": {"content": [{"type": "text", "text": str(result)}]}}) + "\n")
            except Exception as e:
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id,
                                             "error": {"code": -32603, "message": str(e)}}) + "\n")
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id,
                                         "result": {}}) + "\n")
        sys.stdout.flush()


def _get_mcp_token() -> str:
    """Token compartido para autenticar POST /call. Prioriza la variable de
    entorno JARVIS_MCP_TOKEN; si no está definida, genera/persiste uno en
    .jarvis_mcp_auth junto a este archivo."""
    env_token = os.environ.get("JARVIS_MCP_TOKEN", "").strip()
    if env_token:
        return env_token
    token_file = Path(__file__).resolve().parent / ".jarvis_mcp_auth"
    try:
        t = token_file.read_text(encoding="utf-8").strip()
        if t:
            return t
    except Exception:
        pass
    t = secrets.token_hex(32)
    try:
        token_file.write_text(t, encoding="utf-8")
    except Exception:
        pass
    return t


def main_http(port=5001):
    """Modo HTTP ligero (para pruebas rápidas con curl/JS).
    Requiere autenticación: enviar la cabecera 'X-Auth-Token: <token>' en
    cada POST /call. El token se imprime en consola al arrancar, o puede
    fijarse de antemano con la variable de entorno JARVIS_MCP_TOKEN.
    Ejemplo:
        curl -X POST http://127.0.0.1:5001/call \\
             -H "X-Auth-Token: <token>" -H "Content-Type: application/json" \\
             -d '{"tool": "estadisticas_sistema", "arguments": {}}'
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    tools = JarvisMcpTools()
    token = _get_mcp_token()
    IMPL = {
        "ejecutar_habilidad": tools.ejecutar_habilidad,
        "guardar_memoria": tools.guardar_memoria,
        "leer_memoria": tools.leer_memoria,
        "estadisticas_sistema": tools.estadisticas_sistema,
        "guardar_archivo": tools.guardar_archivo,
    }

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send({"status": "ok", "server": "jarvis-mcp"})
            elif self.path.startswith("/tools"):
                self._send({"tools": list(IMPL.keys())})
            else:
                self._send({"error": "not found"}, 404)

        def do_POST(self):
            if self.path != "/call":
                self._send({"error": "not found"}, 404)
                return
            req_token = self.headers.get("X-Auth-Token", "")
            if not secrets.compare_digest(req_token, token):
                self._send({"error": "no autorizado"}, 401)
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            except json.JSONDecodeError:
                self._send({"error": "json invalido"}, 400)
                return
            name = body.get("tool")
            args = body.get("arguments", {})
            fn = IMPL.get(name)
            if not fn:
                self._send({"error": f"Herramienta desconocida: {name}"}, 404)
                return
            try:
                self._send({"result": fn(**args) if isinstance(args, dict) else fn()})
            except Exception as e:
                self._send({"error": str(e)}, 500)

    print(f"JARVIS MCP (HTTP) en http://127.0.0.1:{port}")
    print(f"  Token: {token}")
    HTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 5001
        main_http(port)
    else:
        main_stdio()