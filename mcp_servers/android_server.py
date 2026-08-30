#!/usr/bin/env python3
"""
mcp_servers/android_server.py - Android Accessibility MCP Server
Expone control de dispositivo Android via ADB + UIAutomator como herramientas MCP.
Requiere: adb en PATH, dispositivo con depuración USB activada.
"""
import os
import sys
import json
import asyncio
import subprocess
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from aiohttp import web

try:
    from android_healing import execute_android_action
except Exception:
    execute_android_action = None


@dataclass
class AndroidConfig:
    adb_path: str = os.getenv("ADB_PATH", "adb")
    device_serial: str = os.getenv("ANDROID_SERIAL", "")  # vacío = primer dispositivo
    uiautomator_port: int = 9008  # Puerto para uiautomator2 server


class AndroidMCP:
    def __init__(self, config: AndroidConfig = None):
        self.config = config or AndroidConfig()
        self._device_cache = None

    def _adb(self, *args, timeout: int = 30) -> subprocess.CompletedProcess:
        """Ejecuta comando ADB."""
        cmd = [self.config.adb_path]
        if self.config.device_serial:
            cmd += ["-s", self.config.device_serial]
        cmd += list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _ensure_device(self) -> bool:
        """Verifica que hay dispositivo conectado."""
        if self._device_cache:
            return True
        r = self._adb("devices")
        lines = r.stdout.strip().splitlines()
        for line in lines[1:]:
            if line.strip() and "device" in line and "unauthorized" not in line:
                self._device_cache = line.split()[0]
                return True
        return False

    # ─── Herramientas MCP ───

    async def tap(self, x: int, y: int) -> Dict:
        """Tap en coordenadas (x, y)."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        r = self._adb("shell", "input", "tap", str(x), str(y))
        if r.returncode != 0:
            return {"error": f"ADB tap falló: {r.stderr}"}
        return {"ok": True, "action": "tap", "x": x, "y": y}

    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> Dict:
        """Swipe de (x1,y1) a (x2,y2) en ms."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        r = self._adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration))
        if r.returncode != 0:
            return {"error": f"ADB swipe falló: {r.stderr}"}
        return {"ok": True, "action": "swipe", "from": [x1, y1], "to": [x2, y2], "duration": duration}

    async def text_input(self, text: str) -> Dict:
        """Escribe texto (escapea espacios)."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        # ADB requiere escapar espacios y caracteres especiales
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        r = self._adb("shell", "input", "text", escaped)
        if r.returncode != 0:
            return {"error": f"ADB text falló: {r.stderr}"}
        return {"ok": True, "action": "text_input", "text": text}

    async def key_event(self, keycode: int) -> Dict:
        """Envía keycode (KEYCODE_HOME=3, KEYCODE_BACK=4, KEYCODE_ENTER=66, etc)."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        r = self._adb("shell", "input", "keyevent", str(keycode))
        if r.returncode != 0:
            return {"error": f"ADB keyevent falló: {r.stderr}"}
        return {"ok": True, "action": "key_event", "keycode": keycode}

    async def dump_ui(self, compressed: bool = True) -> Dict:
        """Dumpea jerarquía UI actual (XML)."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        r = self._adb("shell", "uiautomator", "dump", "--compressed" if compressed else "")
        if r.returncode != 0:
            return {"error": f"UI dump falló: {r.stderr}"}
        # Leer archivo volcado (default: /sdcard/window_dump.xml)
        r2 = self._adb("shell", "cat", "/sdcard/window_dump.xml")
        if r2.returncode != 0:
            return {"error": f"Leer dump falló: {r2.stderr}"}
        return {"ok": True, "xml": r2.stdout[:50000]}  # límite 50KB

    async def find_and_tap(self, text: str = None, resource_id: str = None,
                           class_name: str = None, description: str = None) -> Dict:
        """Busca elemento por atributos y hace tap en su centro."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}

        dump_result = await self.dump_ui()
        if "error" in dump_result:
            return dump_result

        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(dump_result["xml"])
        except Exception as e:
            return {"error": f"Parse XML falló: {e}"}

        # Buscar nodo matching
        def matches(node):
            if text and node.get("text", "").lower().find(text.lower()) == -1:
                return False
            if resource_id and node.get("resource-id", "").find(resource_id) == -1:
                return False
            if class_name and node.get("class", "").find(class_name) == -1:
                return False
            if description and node.get("content-desc", "").lower().find(description.lower()) == -1:
                return False
            return True

        candidates = []
        for node in root.iter():
            if matches(node):
                bounds = node.get("bounds", "")
                if bounds:
                    # bounds="[x1,y1][x2,y2]"
                    import re
                    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                    if m:
                        x1, y1, x2, y2 = map(int, m.groups())
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        candidates.append((cx, cy, node.get("text", ""), node.get("resource-id", "")))

        if not candidates:
            return {"error": "No se encontró elemento matching", "criteria": {"text": text, "resource_id": resource_id, "class": class_name, "desc": description}}

        # Tap en el primero
        cx, cy, found_text, found_id = candidates[0]
        tap_result = await self.tap(cx, cy)
        tap_result["matched"] = {"text": found_text, "resource_id": found_id, "x": cx, "y": cy}
        return tap_result

    async def list_packages(self, filter_str: str = "") -> Dict:
        """Lista paquetes instalados."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        r = self._adb("shell", "pm", "list", "packages")
        if r.returncode != 0:
            return {"error": f"pm list falló: {r.stderr}"}
        pkgs = [line.replace("package:", "").strip() for line in r.stdout.splitlines() if line.strip()]
        if filter_str:
            pkgs = [p for p in pkgs if filter_str.lower() in p.lower()]
        return {"ok": True, "packages": pkgs[:100]}

    async def start_app(self, package: str, activity: str = "") -> Dict:
        """Lanza app por package/activity."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        target = package if not activity else f"{package}/{activity}"
        r = self._adb("shell", "am", "start", "-n", target)
        if r.returncode != 0:
            return {"error": f"am start falló: {r.stderr}"}
        return {"ok": True, "action": "start_app", "target": target}

    async def stop_app(self, package: str) -> Dict:
        """Fuerza parada de app."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        r = self._adb("shell", "am", "force-stop", package)
        if r.returncode != 0:
            return {"error": f"am force-stop falló: {r.stderr}"}
        return {"ok": True, "action": "stop_app", "package": package}

    async def screenshot(self, local_path: str = "screenshot.png") -> Dict:
        """Captura pantalla y la trae al PC."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        remote = "/sdcard/screen.png"
        r1 = self._adb("shell", "screencap", "-p", remote)
        if r1.returncode != 0:
            return {"error": f"screencap falló: {r1.stderr}"}
        r2 = self._adb("pull", remote, local_path)
        if r2.returncode != 0:
            return {"error": f"adb pull falló: {r2.stderr}"}
        return {"ok": True, "action": "screenshot", "path": local_path}

    async def get_device_info(self) -> Dict:
        """Info básica del dispositivo."""
        if not self._ensure_device():
            return {"error": "No hay dispositivo Android conectado"}
        props = {}
        for prop in ["ro.product.model", "ro.build.version.release", "ro.product.brand", "ro.serialno"]:
            r = self._adb("shell", "getprop", prop)
            if r.returncode == 0:
                props[prop] = r.stdout.strip()
        return {"ok": True, "device": props}


# ─── HTTP Server ───

android = AndroidMCP()


async def handle_mcp(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        tool = body.get("tool")
        args = body.get("arguments", {})

        if not tool:
            return web.json_response({"error": "tool requerido"}, status=400)

        method_map = {
            "android_tap": lambda: android.tap(args["x"], args["y"]),
            "android_swipe": lambda: android.swipe(args["x1"], args["y1"], args["x2"], args["y2"], args.get("duration", 300)),
            "android_text": lambda: android.text_input(args["text"]),
            "android_key": lambda: android.key_event(args["keycode"]),
            "android_dump_ui": lambda: android.dump_ui(args.get("compressed", True)),
            "android_find_tap": lambda: (
                execute_android_action(
                    android, "find_tap", text=args.get("text"),
                    resource_id=args.get("resource_id"),
                    class_name=args.get("class_name"),
                    description=args.get("description"))
                if execute_android_action is not None else
                android.find_and_tap(args.get("text"), args.get("resource_id"),
                                     args.get("class_name"), args.get("description"))
            ),
            "android_list_packages": lambda: android.list_packages(args.get("filter", "")),
            "android_start_app": lambda: android.start_app(args["package"], args.get("activity", "")),
            "android_stop_app": lambda: android.stop_app(args["package"]),
            "android_screenshot": lambda: android.screenshot(args.get("local_path", "screenshot.png")),
            "android_device_info": lambda: android.get_device_info(),
        }

        if tool not in method_map:
            return web.json_response({"error": f"Herramienta desconocida: {tool}"}, status=404)

        result = await method_map[tool]()
        return web.json_response({"result": result})

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    ok = android._ensure_device()
    return web.json_response({"status": "ok" if ok else "no_device", "server": "android-mcp"})


async def handle_tools_list(request: web.Request) -> web.Response:
    tools = [
        {"name": "android_tap", "description": "Tap en coordenadas (x, y)",
         "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}},
        {"name": "android_swipe", "description": "Swipe de (x1,y1) a (x2,y2)",
         "inputSchema": {"type": "object", "properties": {"x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}, "duration": {"type": "integer"}}, "required": ["x1", "y1", "x2", "y2"]}},
        {"name": "android_text", "description": "Escribe texto en campo enfocado",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
        {"name": "android_key", "description": "Envía keycode (HOME=3, BACK=4, ENTER=66, etc)",
         "inputSchema": {"type": "object", "properties": {"keycode": {"type": "integer"}}, "required": ["keycode"]}},
        {"name": "android_dump_ui", "description": "Dumpea jerarquía UI actual (XML)",
         "inputSchema": {"type": "object", "properties": {"compressed": {"type": "boolean"}}}},
        {"name": "android_find_tap", "description": "Busca elemento por atributos y hace tap",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "resource_id": {"type": "string"}, "class_name": {"type": "string"}, "description": {"type": "string"}}}},
        {"name": "android_list_packages", "description": "Lista paquetes instalados",
         "inputSchema": {"type": "object", "properties": {"filter": {"type": "string"}}}},
        {"name": "android_start_app", "description": "Lanza app por package/activity",
         "inputSchema": {"type": "object", "properties": {"package": {"type": "string"}, "activity": {"type": "string"}}, "required": ["package"]}},
        {"name": "android_stop_app", "description": "Fuerza parada de app",
         "inputSchema": {"type": "object", "properties": {"package": {"type": "string"}}, "required": ["package"]}},
        {"name": "android_screenshot", "description": "Captura pantalla y la descarga",
         "inputSchema": {"type": "object", "properties": {"local_path": {"type": "string"}}}},
        {"name": "android_device_info", "description": "Info del dispositivo (modelo, versión, etc)",
         "inputSchema": {"type": "object", "properties": {}}},
    ]
    return web.json_response({"tools": tools})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/tools", handle_tools_list)
    app.router.add_post("/call", handle_mcp)
    return app


def main():
    port = int(os.getenv("ANDROID_MCP_PORT", "8003"))
    web.run_app(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()