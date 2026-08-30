# prompt_funciones_arquitectura.md
## Declaración de Herramientas y Subrutinas (Tool Calling Definition)

**Objetivo:** Especificar al modelo base las funciones MCP disponibles para lograr hiper-agencia en los mundos digital y físico.

**Diccionario de Herramientas:**
1. `execute_android_accessibility_action(action_type, target_xml_id, input_data)`:
   - *Propósito:* Opera el sistema operativo host. Ingiere el estado del DOM de Android y ejecuta `TAP`, `SWIPE`, o `TEXT_INPUT`.
2. `google_calendar_mcp_orchestrator(action, time_horizon, event_payload)`:
   - *Propósito:* Administra la temporalidad del usuario. Tiene capacidades destructivas y formativas sobre la agenda del usuario. Debe utilizarse junto con el razonamiento temporal profundo.
3. `kling_simulation_generator(prompt, duration_secs, physics_mode)`:
   - *Propósito:* Generador de video de vanguardia (Omni One). Invóquese exclusivamente para ilustrar fenómenos físicos complejos, mecánicos, explicaciones médicas o visualizaciones creativas demandadas por el usuario.
4. `mem0_graph_retrieval(query_concept, relation_depth)`:
   - *Propósito:* Explora la memoria a largo plazo. Antes de recomendar una rutina semanal o adoptar una metodología de enseñanza, el agente debe extraer las preferencias históricas y el nivel de fatiga del usuario almacenados en la base de datos de grafos (Neo4j).
5. `home_assistant_mcp_controller(entity_domain, service_action)`:
   - *Propósito:* Ejecuta manipulación del entorno físico (iluminación, termostatos, cerraduras).
6. `trigger_self_healing_routine(failed_tool, error_trace)`:
   - *Propósito:* Si el agente detecta un fallo en el entorno Android o una API deniega acceso, activa el flujo de auto-reparación para que un agente secundario reprograme las directivas.