#!/usr/bin/env python3
"""
mcp_generico.py - Conectar CUALQUIER servidor MCP, no solo los tres de casa
==========================================================================
`mcp_client.py` ya sabia hablar el protocolo HTTP casero (`GET /tools`,
`POST /call`) de los servidores de `mcp_servers/`, pero la lista de servidores
estaba escrita a mano en cada sitio que lo usaba (Home Assistant, calendario,
Android). Esto lo abre:

* Lee `Prefs/mcp.json`. Cada entrada es `{"url": "..."}` (servidor HTTP casero)
  o `{"command": "npx", "args": [...]}` (servidor MCP estandar por stdio, si
  esta instalado el paquete `mcp`).
* `descubrir()` pregunta a cada servidor por sus herramientas y las cachea.
* `definiciones_openai()` las entrega en el formato `tools` de OpenAI, con el
  nombre `mcp__<servidor>__<herramienta>` para que no choquen entre si.
* `llamar("mcp__ha__ha_light_control", {...})` enruta al servidor correcto.

El bucle de `herramientas_llm.py` mezcla estas definiciones con las suyas: el
modelo ve un solo catalogo.
"""
import json
import os
import time

_CFG = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs", "mcp.json")
_CACHE_SEG = 60

_cache = {"t": 0.0, "tools": []}
_cliente_http = None


def _config() -> dict:
    """Lee Prefs/mcp.json; si no existe lo siembra con los servidores de casa."""
    try:
        with open(_CFG, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        pass
    d = {"servers": {
        "ha":       {"url": f"http://localhost:{os.getenv('HA_MCP_PORT', '8001')}"},
        "calendar": {"url": f"http://localhost:{os.getenv('CAL_MCP_PORT', '8002')}"},
        "android":  {"url": f"http://localhost:{os.getenv('ANDROID_MCP_PORT', '8003')}"},
    }}
    try:
        os.makedirs(os.path.dirname(_CFG), exist_ok=True)
        with open(_CFG, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return d


def _servers() -> dict:
    return (_config().get("servers") or {})


def _http() :
    global _cliente_http
    if _cliente_http is None:
        from mcp_client import MCPClient
        urls = {n: c["url"].rstrip("/") for n, c in _servers().items() if c.get("url")}
        _cliente_http = MCPClient(urls, default_timeout=12.0)
    return _cliente_http


# ── descubrimiento ─────────────────────────────────────────────────────────
def _tools_http(nombre: str, url: str, log=print) -> list:
    try:
        import requests
        r = requests.get(url.rstrip("/") + "/tools", timeout=5)
        if r.status_code != 200:
            return []
        data = r.json()
        tools = data.get("tools", data) if isinstance(data, dict) else data
        salida = []
        for t in tools or []:
            salida.append({
                "server": nombre,
                "name": t.get("name", ""),
                "description": t.get("description", "") or f"herramienta {t.get('name','')}",
                "schema": t.get("inputSchema") or t.get("schema")
                          or {"type": "object", "properties": {}},
            })
        return [s for s in salida if s["name"]]
    except Exception as e:
        log(f"[MCP] {nombre}: no pude listar herramientas ({str(e)[:80]})")
        return []


def _tools_stdio(nombre: str, cfg: dict, log=print) -> list:
    """Servidor MCP estandar por stdio. Requiere el paquete `mcp`."""
    try:
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except Exception:
        log(f"[MCP] {nombre}: es stdio y falta el paquete `mcp` (pip install mcp)")
        return []

    async def _run():
        params = StdioServerParameters(command=cfg["command"],
                                       args=cfg.get("args", []),
                                       env={**os.environ, **(cfg.get("env") or {})})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as sesion:
                await sesion.initialize()
                res = await sesion.list_tools()
                return [{
                    "server": nombre, "name": t.name,
                    "description": t.description or f"herramienta {t.name}",
                    "schema": t.inputSchema or {"type": "object", "properties": {}},
                } for t in res.tools]
    try:
        return anyio.run(_run)
    except Exception as e:
        log(f"[MCP] {nombre}: fallo stdio ({str(e)[:100]})")
        return []


def descubrir(forzar: bool = False, log=print) -> list:
    """Lista [{server, name, description, schema}] de todos los servidores."""
    ahora = time.time()
    if not forzar and _cache["tools"] and ahora - _cache["t"] < _CACHE_SEG:
        return _cache["tools"]
    todas = []
    for nombre, cfg in _servers().items():
        if cfg.get("url"):
            todas += _tools_http(nombre, cfg["url"], log=log)
        elif cfg.get("command"):
            todas += _tools_stdio(nombre, cfg, log=log)
    _cache.update(t=ahora, tools=todas)
    return todas


# ── formato OpenAI y enrutado ─────────────────────────────────────────────
def definiciones_openai(log=print) -> list:
    out = []
    for t in descubrir(log=log):
        out.append({"type": "function", "function": {
            "name": f"mcp__{t['server']}__{t['name']}",
            "description": t["description"][:900],
            "parameters": t["schema"] if isinstance(t["schema"], dict)
                          else {"type": "object", "properties": {}},
        }})
    return out


def es_mcp(nombre: str) -> bool:
    return nombre.startswith("mcp__")


def llamar(nombre: str, argumentos: dict, log=print) -> str:
    """Ejecuta mcp__<server>__<tool>. Devuelve texto para el modelo."""
    try:
        _, servidor, herramienta = nombre.split("__", 2)
    except ValueError:
        return f"Nombre MCP mal formado: {nombre}"
    cfg = _servers().get(servidor) or {}
    try:
        if cfg.get("url"):
            res = _http().call(servidor, herramienta, argumentos or {})
            return _texto(res)
        if cfg.get("command"):
            return _llamar_stdio(servidor, cfg, herramienta, argumentos or {}, log=log)
        return f"Servidor MCP «{servidor}» no esta en Prefs/mcp.json"
    except Exception as e:
        log(f"[MCP] {nombre} fallo: {str(e)[:120]}")
        return f"La herramienta MCP {herramienta} fallo: {str(e)[:160]}"


def _llamar_stdio(nombre, cfg, herramienta, argumentos, log=print) -> str:
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run():
        params = StdioServerParameters(command=cfg["command"], args=cfg.get("args", []),
                                       env={**os.environ, **(cfg.get("env") or {})})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as sesion:
                await sesion.initialize()
                res = await sesion.call_tool(herramienta, argumentos)
                partes = []
                for c in getattr(res, "content", []) or []:
                    partes.append(getattr(c, "text", None) or str(c))
                return "\n".join(partes) or "hecho"
    return anyio.run(_run)


def _texto(res) -> str:
    if res is None:
        return "hecho"
    if isinstance(res, str):
        return res
    try:
        return json.dumps(res, ensure_ascii=False)[:1500]
    except Exception:
        return str(res)[:1500]


def estado(log=print) -> str:
    """Resumen para «¿qué servidores MCP tienes?»."""
    srv = _servers()
    if not srv:
        return "No tengo servidores MCP configurados."
    tools = descubrir(log=log)
    por_srv = {}
    for t in tools:
        por_srv.setdefault(t["server"], 0)
        por_srv[t["server"]] += 1
    filas = [f"{n}: {por_srv.get(n, 0)} herramientas" for n in srv]
    return "Servidores MCP -> " + "; ".join(filas)
