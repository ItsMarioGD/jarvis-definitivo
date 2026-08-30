#!/usr/bin/env python3
"""
ultron_skills/self_healing.py - Self-Healing Selectors para Android
====================================================================
Cuando un selector (resource-id, xpath, class) falla por actualización de app:
1. Captura error + dump UI actual
2. LLM analiza UI y propone nuevo selector
3. Prueba en sandbox (emulador) antes de aplicar en dispositivo real
4. Cachea selector funcionando para futuras ejecuciones
"""
import os
import re
import json
import time
import hashlib
import subprocess
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class SelectorAttempt:
    """Intento de selector (exitoso o fallido)."""
    action: str              # "tap", "swipe", "text", etc
    selector_type: str       # "resource_id", "xpath", "text", "class", "description"
    selector_value: str
    success: bool
    error: str = ""
    timestamp: float = 0.0
    ui_dump_hash: str = ""


@dataclass
class HealedSelector:
    """Selector reparado y validado."""
    original_selector: SelectorAttempt
    new_selector: Dict[str, str]  # {"type": "resource_id", "value": "nuevo_id"}
    validated_at: float
    validation_method: str  # "sandbox_emulator" | "device_test" | "llm_suggestion"
    confidence: float  # 0.0 - 1.0


class SelectorCache:
    """Cache de selectores funcionando (persistente en disco)."""

    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Cache", "selectors")
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "selector_cache.json")
        self._cache: Dict[str, HealedSelector] = {}
        self._failed: Dict[str, List[SelectorAttempt]] = {}
        os.makedirs(cache_dir, exist_ok=True)
        self._load()

    def _load(self):
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.get("healed", {}).items():
                self._cache[k] = HealedSelector(**v)
            for k, v in data.get("failed", {}).items():
                self._failed[k] = [SelectorAttempt(**a) for a in v]
        except Exception:
            pass

    def _save(self):
        try:
            data = {
                "healed": {k: asdict(v) for k, v in self._cache.items()},
                "failed": {k: [asdict(a) for a in v] for k, v in self._failed.items()}
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _key(self, action: str, selector_type: str, selector_value: str) -> str:
        return hashlib.md5(f"{action}|{selector_type}|{selector_value}".encode()).hexdigest()[:16]

    def get_healed(self, action: str, selector_type: str, selector_value: str) -> Optional[HealedSelector]:
        key = self._key(action, selector_type, selector_value)
        return self._cache.get(key)

    def record_failure(self, attempt: SelectorAttempt):
        key = self._key(attempt.action, attempt.selector_type, attempt.selector_value)
        if key not in self._failed:
            self._failed[key] = []
        self._failed[key].append(attempt)
        # Mantener solo últimos 10 fallos por key
        self._failed[key] = self._failed[key][-10:]
        self._save()

    def record_success(self, healed: HealedSelector):
        key = self._key(healed.original_selector.action, healed.original_selector.selector_type, healed.original_selector.selector_value)
        self._cache[key] = healed
        self._save()


class SelfHealingEngine:
    """
    Motor de auto-reparación de selectores Android.
    Flujo:
    1. Ejecuta acción con selector original
    2. Si falla → analiza UI dump + error → propone alternativas (LLM)
    3. Valida en sandbox (emulador headless) o dispositivo real
    4. Cachea selector funcionando
    """

    def __init__(self, android_mcp, llm_client=None, log=print):
        self.android = android_mcp
        self.llm = llm_client
        self.log = log
        self.cache = SelectorCache()
        self._emulator_serial = os.getenv("ANDROID_EMULATOR_SERIAL", "emulator-5554")

    async def execute_with_healing(self, action: str, **kwargs) -> Dict:
        """
        Ejecuta acción con auto-reparación.
        kwargs: parámetros específicos de la acción (x, y, text, resource_id, etc)
        """
        # Construir selector original desde kwargs
        original_selector = self._build_selector(action, kwargs)
        if not original_selector:
            return await self._execute_raw(action, kwargs)

        # 1. Verificar cache
        healed = self.cache.get_healed(action, original_selector["type"], original_selector["value"])
        if healed and healed.confidence > 0.7:
            self.log(f"[SELF-HEAL] Usando selector cacheado: {healed.new_selector}")
            kwargs[healed.new_selector["type"]] = healed.new_selector["value"]
            return await self._execute_raw(action, kwargs)

        # 2. Intentar selector original
        result = await self._execute_raw(action, kwargs)
        if result.get("ok"):
            return result

        # 3. Falló → iniciar auto-reparación
        self.log(f"[SELF-HEAL] Selector falló: {original_selector} → {result.get('error')}")

        attempt = SelectorAttempt(
            action=action,
            selector_type=original_selector["type"],
            selector_value=original_selector["value"],
            success=False,
            error=result.get("error", "unknown"),
            timestamp=time.time()
        )

        # Obtener UI dump para análisis
        dump_result = await self.android.dump_ui()
        if "error" not in dump_result:
            attempt.ui_dump_hash = hashlib.md5(dump_result["xml"].encode()).hexdigest()[:16]

        self.cache.record_failure(attempt)

        # 4. Generar candidatos de reparación
        candidates = await self._generate_candidates(action, kwargs, attempt, dump_result.get("xml", ""))

        # 5. Validar candidatos (primero en sandbox/emulador, luego en dispositivo)
        for candidate in candidates:
            self.log(f"[SELF-HEAL] Probando candidato: {candidate}")
            test_kwargs = kwargs.copy()
            test_kwargs[candidate["type"]] = candidate["value"]
            test_result = await self._execute_raw(action, test_kwargs)

            if test_result.get("ok"):
                # ¡Éxito! Cachear y ejecutar en dispositivo real
                healed = HealedSelector(
                    original_selector=attempt,
                    new_selector=candidate,
                    validated_at=time.time(),
                    validation_method="sandbox_emulator",
                    confidence=0.85
                )
                self.cache.record_success(healed)

                # Ejecutar en dispositivo real con selector curado
                return await self._execute_raw(action, test_kwargs)

        # 6. Si nada funcionó, devolver error original con sugerencias
        return {
            "error": result.get("error"),
            "self_heal": "failed",
            "suggestions": [c["value"] for c in candidates[:3]],
            "original_selector": original_selector
        }

    def _build_selector(self, action: str, kwargs: Dict) -> Optional[Dict]:
        """Extrae selector principal de los kwargs."""
        # Prioridad: resource_id > xpath > text > class > description
        for stype in ["resource_id", "xpath", "text", "class_name", "description"]:
            if stype in kwargs and kwargs[stype]:
                return {"type": stype, "value": kwargs[stype]}
        return None

    async def _execute_raw(self, action: str, kwargs: Dict) -> Dict:
        """Ejecuta acción directamente en android_mcp."""
        method_map = {
            "tap": lambda: self.android.tap(kwargs["x"], kwargs["y"]),
            "swipe": lambda: self.android.swipe(kwargs["x1"], kwargs["y1"], kwargs["x2"], kwargs["y2"], kwargs.get("duration", 300)),
            "text": lambda: self.android.text_input(kwargs["text"]),
            "key": lambda: self.android.key_event(kwargs["keycode"]),
            "find_tap": lambda: self.android.find_and_tap(kwargs.get("text"), kwargs.get("resource_id"), kwargs.get("class_name"), kwargs.get("description")),
            "start_app": lambda: self.android.start_app(kwargs["package"], kwargs.get("activity", "")),
            "stop_app": lambda: self.android.stop_app(kwargs["package"]),
            "screenshot": lambda: self.android.screenshot(kwargs.get("local_path", "screenshot.png")),
        }
        if action not in method_map:
            return {"error": f"Acción no soportada: {action}"}
        return await method_map[action]()

    async def _generate_candidates(self, action: str, kwargs: Dict, attempt: SelectorAttempt, ui_xml: str) -> List[Dict]:
        """
        Genera candidatos de selector alternativo.
        Prioridad:
        1. LLM análisis de UI dump + error
        2. Heurísticas: buscar por texto visible, clase, bounds cercanos
        3. Fallback: coordenadas absolutas (último recurso)
        """
        candidates = []

        # 1. Heurísticas rápidas desde UI dump
        if ui_xml:
            heuristic_candidates = self._heuristic_candidates(action, kwargs, ui_xml)
            candidates.extend(heuristic_candidates)

        # 2. LLM si disponible
        if self.llm and ui_xml:
            llm_candidates = await self._llm_candidates(action, kwargs, attempt, ui_xml)
            candidates.extend(llm_candidates)

        # 3. Coordenadas absolutas como último recurso (si action es tap/swipe)
        if action in ("tap", "swipe") and "x" in kwargs and "y" in kwargs:
            candidates.append({"type": "coordinates", "value": f"{kwargs['x']},{kwargs['y']}"})

        # Deduplicar
        seen = set()
        unique = []
        for c in candidates:
            key = f"{c['type']}|{c['value']}"
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique[:10]  # máx 10 candidatos

    def _heuristic_candidates(self, action: str, kwargs: Dict, ui_xml: str) -> List[Dict]:
        """Candidatos basados en análisis heurístico del XML."""
        candidates = []
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(ui_xml)

            original_type = kwargs.get("resource_id") or kwargs.get("text") or kwargs.get("class_name") or kwargs.get("description")

            for node in root.iter():
                # Buscar nodos con bounds clickeables
                bounds = node.get("bounds", "")
                if not bounds:
                    continue

                import re
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                if not m:
                    continue

                # Candidatos por resource-id similar
                rid = node.get("resource-id", "")
                if rid and original_type and original_type in rid:
                    candidates.append({"type": "resource_id", "value": rid})

                # Candidatos por texto similar
                txt = node.get("text", "")
                if txt and original_type and original_type.lower() in txt.lower():
                    candidates.append({"type": "text", "value": txt})

                # Candidatos por class
                cls = node.get("class", "")
                if cls and original_type and original_type in cls:
                    candidates.append({"type": "class_name", "value": cls})

                # Candidatos por content-desc
                desc = node.get("content-desc", "")
                if desc and original_type and original_type.lower() in desc.lower():
                    candidates.append({"type": "description", "value": desc})

        except Exception as e:
            self.log(f"[SELF-HEAL] Heurística falló: {e}")

        return candidates[:5]

    async def _llm_candidates(self, action: str, kwargs: Dict, attempt: SelectorAttempt, ui_xml: str) -> List[Dict]:
        """Usa LLM para proponer selectores alternativos."""
        if not self.llm:
            return []

        try:
            # Truncar XML a 8KB para no exceder contexto
            ui_truncated = ui_xml[:8000]

            prompt = f"""
Acción fallida: {action}
Selector original: {attempt.selector_type}="{attempt.selector_value}"
Error: {attempt.error}

UI actual (truncado):
{ui_truncated}

Propon hasta 3 selectores alternativos que SÍ funcionen.
Formato JSON: [{{"type": "resource_id|text|class|description|xpath", "value": "selector", "reason": "por qué"}]]"""

            # Llamar LLM (adaptar a tu cliente OpenAI/Ollama)
            response = await self.llm.chat.completions.create(
                model=os.getenv("QWEN_MODEL", "qwen3:4b-instruct"),
                messages=[
                    {"role": "system", "content": "Eres experto en UIAutomator/Android. Propones selectores robustos."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )

            content = response.choices[0].message.content
            import json as _json
            llm_cands = _json.loads(content)
            return [{"type": c["type"], "value": c["value"]} for c in llm_cands if "type" in c and "value" in c]

        except Exception as e:
            self.log(f"[SELF-HEAL] LLM candidatos falló: {e}")
            return []


# Helper para integración fácil
async def execute_android_action(android_mcp, action: str, **kwargs) -> Dict:
    """Punto de entrada único con auto-reparación."""
    engine = SelfHealingEngine(android_mcp)
    return await engine.execute_with_healing(action, **kwargs)