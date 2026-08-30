# jarvis-definitivo — contexto del proyecto

Asistente de voz omnimodal tipo "Jarvis" (control de PC, memoria persistente,
generación multimedia, control remoto Android) con un segundo agente hermano
"Ultron" (`UltronCore(JarvisCore)`) añadido encima del mismo núcleo. Todo el
backend es Python plano en la raíz del repo (sin `src/`), con 3 frontends web
independientes y componentes nativos (C++/Java) para hotkeys y control ADB.

## Stack

- **Backend:** Python 3.10+ (probado en CI local con 3.12), sin `pyproject.toml`
  ni lockfile — solo `requirements.txt` (pins mínimos `>=`) y
  `requirements-min.txt` (subset ligero sin pipecat/aiortc).
- **Frontend activo:** `web-hud/` — Vite + React + TypeScript + R3F + Zustand +
  BFF propio en `web-hud/server/` (Express/WS). Arrancado por
  `jarvis_web_start.bat`. Es el único conectado a un script de arranque.
  - `jarvis-fui/` (Vite+TS+Three.js vanilla) y `liquid-glass-jarvis/`
    (Vite+React+JSX sin TS) son prototipos previos, sin conexión a ningún
    flujo de arranque actual. No borrar sin decisión explícita del usuario.
- **Nativo:** `jarvis_hotkey.cpp` (hotkey global Win32), `JarvisAdbBridge.java`
  (puente ADB para control de Android).

## Núcleo backend (raíz, plano)

- `jarvis_core.py` — `JarvisCore`: STT, LLM (Qwen vía Ollama/vLLM u OpenAI),
  TTS (ElevenLabs/Piper), memoria SQLite (`jarvis_memory.db`), listener UDP.
- `jarvis_skills.py` — **monolito**, 7300+ líneas, clase `SkillsManager` con
  ~260 métodos: despachador central de TODAS las habilidades (abrir/cerrar
  apps, volumen, tareas programadas, procesos, desinstalar programas, etc.).
  Se consulta antes del LLM.
- `pc_control.py` — módulo de "poder total" del sistema (apagado programado,
  ventanas, ratón/teclado, archivos, registro, tareas planificadas). Se
  consulta DESPUÉS de `jarvis_skills` y ANTES del LLM.
- `ultron_core.py` / `ultron_skills.py` — extensión aditiva sobre
  `JarvisCore`/despachador de Jarvis (herencia real, no duplicación).
- `jarvis_redact.py` — redacción de secretos (emails, tarjetas, API keys,
  JWT, `Authorization:` headers) antes de persistir texto de usuario. Ver
  "Convenciones de seguridad" abajo — **hay que llamarlo explícitamente en
  cada punto nuevo que persista texto de usuario**, no es automático.
- `jarvis_mcp_server.py` — servidor MCP (stdio estándar + modo HTTP ligero en
  `127.0.0.1:5001` para pruebas con curl/JS). El modo HTTP requiere ahora
  cabecera `X-Auth-Token` (ver abajo).
- `web_interface/app.py`, `ultron_interface/app.py` — backends Flask +
  SocketIO, cada uno con su propio PIN de pareo de 6 dígitos para móvil.
- `mcp_servers/` — servidores MCP externos: `android_server.py`,
  `calendar_server.py`, `ha_server.py` (Home Assistant). Nota:
  `skills/plugins/home_assistant.py` también integra HA — revisar solape si
  se toca esa área.
- `cognition/` — `CognitionHub` (fachada en `cognition/__init__.py`) sobre
  `ml_engine.py` (clasificación de intención, sklearn), `cluster_engine.py`
  (temas dominantes, KMeans), `decision_engine.py` (riesgo de comandos) y
  `shell_ops.py` (shell auditado). Persiste en `storage.py` (raíz,
  `Storage`, tabla `audit_log`+`interacciones` en `jarvis_cognition.db`,
  con redacción de secretos). Wireado en `jarvis_core.py` como
  `self.cognition`; usado solo desde `_registrar_cognicion()`.
- `android_healing/` — `SelfHealingEngine`/`execute_android_action`: auto-
  reparación de selectores Android cuando una app actualiza su UI (dump +
  heurísticas + candidatos LLM opcionales). Enganchado en
  `mcp_servers/android_server.py`'s `android_find_tap`.
- `ultron_arsenal.py` — arsenal de seguridad de Ultron acotado a los
  propios sistemas del usuario: `SurfaceAuditor` (puertos propios en
  escucha), `NetworkSweeper` (barrido activo TCP de la LAN local, más
  profundo que la caché ARP pasiva de `jarvis_skills.py:_quien_red`), y
  `CredentialVault` (vault cifrado Fernet+PBKDF2, clave maestra nunca
  persistida). Enganchado en `ultron_skills.py:_seguridad_propia`.

## Convenciones de seguridad (aplicadas en la auditoría de 2026-08-30)

- **`SECRET_KEY` de Flask ≠ PIN de pareo.** Cada backend web tiene DOS
  secretos separados: `AUTH_TOKEN` (PIN de 6 dígitos, se muestra al usuario
  para emparejar el móvil — `.jarvis_auth`/`.ultron_auth`) y un
  `SECRET_KEY` de 256 bits que NUNCA se muestra
  (`.jarvis_secret_key`/`.ultron_secret_key`, `secrets.token_hex(32)`). No
  volver a unificarlos.
- **Servidor MCP HTTP requiere auth.** `jarvis_mcp_server.py --http` valida
  `X-Auth-Token` contra un token en `JARVIS_MCP_TOKEN` o `.jarvis_mcp_auth`
  (`secrets.compare_digest`). Solo `/health` y `/tools` (GET) quedan sin auth.
- **Nunca `shell=True` con texto libre de usuario interpolado.** Usar listas
  de argumentos (`subprocess.Popen(["cmd", "/c", "start", "", app], ...)`,
  `["taskkill", "/IM", exe, "/F"]`, etc.) cuando la variable interpolada
  proviene de voz/texto del usuario. `shell=True` con una **lista** de args
  (patrón `Popen(["start", "", url], shell=True)`) es más seguro porque
  Python cita cada argumento vía `list2cmdline` — pero interpolación en un
  **string/f-string** con `shell=True` es el patrón peligroso a evitar.
  Antes de tocar más `shell=True` en `jarvis_skills.py` (quedan ~30, la
  mayoría con valores de diccionarios fijos como `APP_MAP`/`CLOSE_MAP` o
  slugs `md5`-hasheados, por tanto seguros), trazar el origen de la variable
  interpolada hasta confirmar si es texto de usuario sin restringir.
- **`jarvis_redact.redact()`/`scrub_secrets()`** debe aplicarse a todo texto
  de usuario que se persista de forma duradera (memoria, recordatorios,
  historial de medios). Ya cubierto: `save_to_memory`, `save_media_history`,
  `add_reminder` (en `jarvis_core.py`, heredado por `ultron_core.py`), y
  `guardar_memoria` en `jarvis_mcp_server.py`. Deliberadamente NO cubierto:
  `guardar_archivo` (genera documentos que el usuario pidió explícitamente).
- Todos los `subprocess` en Windows deben conservar
  `creationflags=0x08000000` (`CREATE_NO_WINDOW`) donde ya estaba presente.
- **`.gitignore` NO debe llevar un patrón `_*` suelto.** Lo tuvo (bajo "Temp
  files") y silenciaba TODOS los `__init__.py` del repo (y cualquier otro
  archivo con nombre `_algo`) sin ningún aviso — así es como `skills/`,
  `skills/plugins/` y `cognition/` llevaban meses sin `__init__.py`
  trackeado. Los directorios `_lhm/`, `_external/`, `_vision/`, etc. ya
  tienen sus propias líneas explícitas más abajo en el archivo; no hace
  falta el comodín.

## Bugs corregidos (auditoría + pasada masiva de 2026-08-30)

Todo lo siguiente está arreglado y verificado (compilación + smoke tests
end-to-end); no hace falta re-auditarlo en la próxima sesión:

- `UltronCore._procesar` no aceptaba `skip_skills` → `TypeError` en toda
  consulta compuesta ("X y Y") que pasara por Ultron. Corregido; además
  ahora respeta `skip_skills` para el despacho de `ultron_skills`.
- El filtro "Ultron nunca dice señor" (`_sanitizar`) solo corría dentro de
  `chat()`, no en `_procesar()` (donde de verdad se encola el TTS) — la
  mayoría de respuestas de Ultron (heredadas de `jarvis_skills.py` vía
  fallback) decían "Señor" en voz alta. Corregido: se sanitiza en los tres
  puntos de retorno de `_procesar`. Mismo leak corregido en 3 strings de
  `ultron_guardian.py` (`FacialGuardian`) y 2 de `ultron_skills.py`.
- `pc_control.py`: el planificador de tareas ejecutaba las diarias/semanales
  **una sola vez para siempre** (`WHERE ultima_ejec IS NULL`). Corregido a
  "no ejecutada hoy todavía" (`substr(ultima_ejec,1,10) != hoy`), y de paso
  se arregló el parseo de tareas "el DD de MES a las HH:MM" (nunca fijaba
  `fecha`, y mapeaba el nombre del mes contra un diccionario de días de la
  semana — siempre daba `None`).
- `mcp_servers/calendar_server.py`: los 7 métodos de `GoogleCalendarMCP`
  eran síncronos pero `handle_mcp` hacía `await` sobre ellos → `TypeError`
  en toda llamada de calendario, enmascarado por el `except` genérico.
  Ahora son `async def` que despachan el trabajo bloqueante vía
  `asyncio.to_thread`.
- `mcp_servers/ha_server.py`: `notify(target=None)` pisaba el valor por
  defecto y crasheaba con `None.split(".")`. Corregido con coalescencia
  dentro de la función.
- `jarvis_skills.py`: faltaba `import socket` a nivel de módulo → las dos
  skills de red (`_vigilante_red`/`_quien_red`) nunca resolvían hostnames,
  `NameError` silencioso. También: 3 pares de métodos duplicados donde el
  segundo pisaba al primero (`_portapapeles`, `_ocr`, `_noticias` —
  eliminadas las versiones muertas, incluida `_RSS_FUENTES` huérfana y
  `_ocr_ejecutar`, conservando `_OCR_SCRIPT` que sí usa `_escanear_doc`),
  entradas duplicadas en el tuple del dispatcher, y 3 `return None`
  inalcanzables tras un `try/except` donde ambas ramas ya retornaban.
- `jarvis_generator.py` usaba un modelo hardcodeado (`llama3.2:1b` vía su
  propia URL de Ollama) que probablemente nunca estuvo instalado — ahora
  usa `jarvis_config.OLLAMA_URL`/`OLLAMA_MODEL` (mismo Qwen que el resto
  del stack).
- `skills/plugins/` — el paquete no existía (`skills/__init__.py`,
  `skills/plugins/__init__.py`, `SkillPlugin`, `get_plugin_registry` no
  estaban escritos en ningún sitio) — el plugin de Home Assistant nunca
  cargó. Construido el scaffolding real; verificado que descubre y
  despacha `home_assistant.py` correctamente.
- `cognition/CognitionHub` y `storage.Storage` no existían — `self.cognition`
  era siempre `None` en `jarvis_core.py`, así que `ml_engine`/
  `cluster_engine`/`decision_engine`/`shell_ops` (completos pero huérfanos)
  nunca se ejecutaban. Construidos ambos; falta `scikit-learn` en
  `requirements.txt` para que la clasificación/clustering funcionen de
  verdad (ya añadido).
- `ultron_skills/self_healing.py` (paquete) colisionaba de nombre con
  `ultron_skills.py` (módulo) → inalcanzable por import. Movido a
  `android_healing/` y enganchado en `android_find_tap`. De paso apareció
  un `SyntaxError` real (llaves desbalanceadas en un f-string) que quedaba
  invisible mientras el archivo era dead code — corregido.

## Debilidades conocidas pendientes (fuera de alcance de esta pasada)

No tocar estas salvo que el usuario lo pida explícitamente — son cambios de
mayor alcance/riesgo, documentados pero no ejecutados:

- **Sin logging estructurado**: 0 usos de `logging` en todo el repo, ~150
  `print()` sueltos. Sustituto pendiente.
- **Manejo de excepciones muy permisivo**: ~550 `except Exception` en total,
  ~60 `except Exception: pass` solo en `jarvis_skills.py` (errores
  silenciados sin rastro). 3 `except:` desnudos en `jarvis_core.py`
  (378, 1498) y `jarvis_generator.py` (211).
- **Sin CI/tests reales**: no hay `.github/workflows/`. `run_tests.py` y
  `test_core2.py` son scripts manuales sin aserciones (requieren servidor
  corriendo a mano), no `pytest`/`unittest`. Cero tests en los 3 frontends.
- **Sin linters/formatters**: ni ESLint/Prettier en los frontends ni
  ruff/flake8/mypy en Python.
- **Monolitos**: `jarvis_skills.py` (7300+ líneas/~260 métodos),
  `jarvis_core.py` (1500+ líneas/55 métodos), `web_interface/app.py` (1500+
  líneas) mezclan HTML inline, lógica de negocio y control de sistema.
- **3 frontends paralelos**: solo `web-hud/` está activo (ver arriba);
  decisión de si eliminar `jarvis-fui/`/`liquid-glass-jarvis/` pendiente del
  usuario, no técnica.
- **Historial git**: el repo partió de un único commit gigante
  (`91dcf26`, +40 805 líneas) — sin trazabilidad incremental previa a esta
  sesión.

## Notas de entorno

- El proyecto está pensado para Windows (rutas `C:\`, `subprocess` con
  `shutdown`/`taskkill`/`schtasks`/PowerShell, `creationflags=0x08000000`).
  En un sandbox Linux, partes del código fallarán en tiempo de ejecución
  (p. ej. `psutil.disk_usage("C:\\")`) — eso es esperado, no un bug.
- `pc_control.py` usa una construcción f-string con backslash dentro de la
  expresión (línea ~556, preexistente) que requiere **Python 3.12+** para
  parsear (PEP 701). `python3.11` falla con `SyntaxError` al hacer
  `ast.parse` de ese archivo; usar `python3.12`/`python3.13` para
  verificaciones de sintaxis.
- Variables de entorno vía `.env` (`python-dotenv` + un parser manual
  duplicado en `web_interface/app.py`); solo `jarvis_core.py` llama
  `load_dotenv()` de forma centralizada.
