#!/usr/bin/env python3
"""
web_interface/panel_api.py - Estado y mandos de todos los subsistemas
=====================================================================
Los modulos nuevos (deshacer, vigilante, enjambre, turno de noche, recados,
perfiles, indice, metricas, canarios...) devuelven todos un `estado()` en dict,
pero solo se podian consultar hablando y recordando la frase exacta. Un
asistente con veinte funciones que solo se descubren de memoria es un asistente
con dos funciones.

Aqui se recoge todo ese estado en un unico JSON y se exponen los mandos mas
usados. La pagina /panel lo pinta; el movil usa el mismo endpoint.

Cada bloque va aislado: si un modulo falla o no esta instalado, aparece con su
motivo y el resto del panel sigue funcionando.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def _seguro(nombre, funcion):
    """Ejecuta un bloque del panel sin que un módulo roto tumbe los demás."""
    try:
        return funcion()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


# ── estado global ───────────────────────────────────────────────────────────
def panel(core=None) -> dict:
    """Foto completa: lo que está encendido, lo que vigila y lo que se puede deshacer."""
    datos = {}

    def _deshacer():
        import deshacer
        from storage import get_storage
        pendientes = get_storage().deshacer_pendientes(limite=8)
        return {"pendientes": [{"ts": p["ts"], "que": p["descripcion"],
                                "tipo": p["tipo"]} for p in pendientes],
                "hay": bool(pendientes), "_texto": deshacer.listar(limite=3,
                                                                   log=lambda *a: None)}

    def _registro():
        from storage import get_storage
        db = get_storage()
        resumen = db.resumen(24)
        return {
            "resumen_24h": resumen,
            "ultimas": [{"ts": a["ts"], "orden": a["orden"] or a["comando"],
                         "ok": bool(a["ok"]), "detalle": a["detalle"][:120]}
                        for a in db.acciones_recientes(12)],
            "fallos": [{"ts": a["ts"], "orden": a["orden"] or a["comando"],
                        "detalle": a["detalle"][:120]}
                       for a in db.acciones_recientes(6, solo_fallos=True)],
            "eventos": [{"ts": e["ts"], "tipo": e["tipo"], "titulo": e["titulo"],
                         "gravedad": e["gravedad"]}
                        for e in db.eventos_recientes(10)],
        }

    def _perfil():
        import perfiles
        return perfiles.estado()

    def _metricas():
        import metricas
        return metricas.resumen()

    def _indice():
        import indice_documentos
        return indice_documentos.estado(log=lambda *a: None)

    def _recados():
        import recados
        return recados.estado()

    def _feedback():
        import feedback
        filas = feedback.valoraciones(100, log=lambda *a: None)
        return {"positivas": len([f for f in filas if f.get("titulo") == "positiva"]),
                "negativas": len([f for f in filas if f.get("titulo") == "negativa"])}

    def _autoskills():
        import autoskills
        return {"pendientes": autoskills.pendientes(),
                "autogeneradas": autoskills.firmadas()}

    def _relevo():
        import relevo
        return relevo.estado()

    def _servicio():
        import servicio
        return servicio.estado(log=lambda *a: None)

    def _vision():
        import vision
        return vision.estado(log=lambda *a: None)

    def _audio():
        import audio_dispositivos
        return audio_dispositivos.estado(core)

    def _voz_propia():
        import voz_propia
        return voz_propia.estado(core)

    def _movil():
        import movil
        return movil.estado()

    def _afinado():
        import afinar
        return afinar.estado(log=lambda *a: None)

    def _rutinas():
        import demostracion
        return {"rutinas": demostracion.listar()}

    datos["deshacer"] = _seguro("deshacer", _deshacer)
    datos["registro"] = _seguro("registro", _registro)
    datos["perfil"] = _seguro("perfil", _perfil)
    datos["metricas"] = _seguro("metricas", _metricas)
    datos["indice"] = _seguro("indice", _indice)
    datos["recados"] = _seguro("recados", _recados)
    datos["valoraciones"] = _seguro("feedback", _feedback)
    datos["habilidades"] = _seguro("autoskills", _autoskills)
    datos["relevo"] = _seguro("relevo", _relevo)
    datos["servicio"] = _seguro("servicio", _servicio)
    datos["vision"] = _seguro("vision", _vision)
    datos["audio"] = _seguro("audio", _audio)
    datos["voz_propia"] = _seguro("voz_propia", _voz_propia)
    datos["movil"] = _seguro("movil", _movil)
    datos["afinado"] = _seguro("afinado", _afinado)
    datos["rutinas"] = _seguro("rutinas", _rutinas)

    # Lo que solo existe con el núcleo cargado.
    if core is not None:
        datos["vigilante"] = _seguro("vigilante", lambda: (
            core.vigilante.estado() if getattr(core, "vigilante", None) else
            {"vigilando": False}))
        datos["enjambre"] = _seguro("enjambre", lambda: (
            core.enjambre.estado() if getattr(core, "enjambre", None) else
            {"activo": False}))
        datos["nocturno"] = _seguro("nocturno", lambda: (
            core.nocturno.estado() if getattr(core, "nocturno", None) else
            {"programado": False}))
        datos["escucha"] = _seguro("escucha", lambda: (
            core.escucha.estado() if getattr(core, "escucha", None) else
            {"activa": False}))
        datos["animo"] = _seguro("animo", lambda: dict(
            getattr(core, "_estado_animo", {}) or {}))
        datos["rebobinar"] = _seguro("rebobinar", lambda: (
            core.rebobinador.estado() if getattr(core, "rebobinador", None) else
            {"grabando": False}))
        datos["observador"] = _seguro("observador", lambda: (
            core.observador.estado() if getattr(core, "observador", None) else
            {"activo": False}))
        datos["puente_movil"] = _seguro("puente_movil", lambda: (
            core.puente_movil.estado() if getattr(core, "puente_movil", None) else
            {"activo": False, "reglas": []}))
        datos["mision"] = _seguro("mision", lambda: (
            _resumen_mision(core)))
    return datos


def _resumen_mision(core) -> dict:
    """La misión en curso, si la hay, en cuatro datos."""
    m = getattr(core, "mision_actual", None)
    if m is None:
        return {"en_curso": False}
    pasos = getattr(m, "pasos", []) or []
    hechos = [p for p in pasos if getattr(p, "estado", "") in ("hecho", "ok")]
    return {"en_curso": bool(getattr(core, "mision_piloto", None)
                             and core.mision_piloto.en_curso()),
            "objetivo": getattr(m, "objetivo", "")[:120],
            "pasos": len(pasos), "hechos": len(hechos)}


# ── mandos ──────────────────────────────────────────────────────────────────
ACCIONES = {
    "deshacer", "perfil", "indexar", "indexar_conversaciones", "turno_noche",
    "enjambre_on", "enjambre_off", "escucha_on", "escucha_off", "privado_on",
    "privado_off", "copia", "mantenimiento", "canarios_on", "canarios_off",
    "restaurar_red", "aprobar_habilidad", "descartar_habilidad", "parte_manana",
    "metricas_reset", "colisiones",
    "instalar_voz", "elegir_voz_jarvis", "elegir_voz_ultron",
    "observador_on", "observador_off", "mirar_pantalla",
    "movil_vigilar", "movil_parar", "movil_sonar", "movil_wifi",
    "afinar_exportar", "repetir_rutina", "mision_parar",
}


def ejecutar(core, accion: str, valor: str = "", log=print) -> dict:
    """Ejecuta un mando del panel. Devuelve {ok, texto}."""
    if accion not in ACCIONES:
        return {"ok": False, "texto": f"Mando desconocido: {accion}"}
    try:
        if accion == "deshacer":
            import deshacer
            return {"ok": True, "texto": deshacer.deshacer_ultimo(
                1, log=log, set_pref=getattr(core, "set_pref", None))}

        if accion == "perfil":
            import perfiles
            if valor in ("normal", ""):
                return {"ok": True, "texto": perfiles.restaurar(core, log=log)}
            return {"ok": True, "texto": perfiles.activar(core, valor, log=log)}

        if accion == "indexar":
            import indice_documentos
            return {"ok": True, "texto": indice_documentos.indexar(log=log)}

        if accion == "indexar_conversaciones":
            import indice_documentos
            return {"ok": True, "texto": indice_documentos.indexar_conversaciones(log=log)}

        if accion == "turno_noche":
            if getattr(core, "nocturno", None) is None:
                return {"ok": False, "texto": "El turno de noche no está disponible."}
            if valor == "ahora":
                return {"ok": True, "texto": core.nocturno.ejecutar()}
            if valor == "cancelar":
                return {"ok": True, "texto": core.nocturno.cancelar()}
            return {"ok": True, "texto": core.nocturno.programar(valor or "03:30")}

        if accion in ("enjambre_on", "enjambre_off"):
            texto = core._ordenes_meta("activa el enjambre" if accion.endswith("on")
                                       else "desactiva el enjambre")
            return {"ok": True, "texto": texto or "hecho"}

        if accion in ("escucha_on", "escucha_off"):
            texto = core._ordenes_meta("activa la escucha continua" if accion.endswith("on")
                                       else "desactiva la escucha")
            return {"ok": True, "texto": texto or "hecho"}

        if accion in ("privado_on", "privado_off"):
            import privacidad
            return {"ok": True, "texto": (privacidad.activar(core) if accion.endswith("on")
                                          else privacidad.desactivar(core))}

        if accion == "instalar_voz":
            import voz_propia
            return {"ok": True, "texto": voz_propia.instalar(valor, log=log)}

        if accion in ("elegir_voz_jarvis", "elegir_voz_ultron"):
            import voz_propia
            quien = "ultron" if accion.endswith("ultron") else "jarvis"
            return {"ok": True, "texto": voz_propia.elegir(core, quien, valor, log=log)}

        if accion in ("observador_on", "observador_off", "mirar_pantalla"):
            import observador
            if getattr(core, "observador", None) is None:
                core.observador = observador.Observador(core, log=log)
            if accion == "observador_on":
                return {"ok": True, "texto": core.observador.start()}
            if accion == "observador_off":
                return {"ok": True, "texto": core.observador.stop()}
            aviso = core.observador.mirar()
            return {"ok": True, "texto": aviso or "No veo ningún error en pantalla."}

        if accion in ("movil_vigilar", "movil_parar"):
            import movil
            if getattr(core, "puente_movil", None) is None:
                core.puente_movil = movil.Puente(core, log=log)
            return {"ok": True, "texto": (core.puente_movil.start()
                                          if accion.endswith("vigilar")
                                          else core.puente_movil.stop())}

        if accion == "movil_sonar":
            import movil
            return {"ok": True, "texto": movil.encontrar()}

        if accion == "movil_wifi":
            import movil
            return {"ok": True, "texto": movil.emparejar_wifi(valor, log=log)}

        if accion == "afinar_exportar":
            import afinar
            ruta = afinar.exportar(log=log)
            guion = afinar.guion(ruta, log=log)
            import os as _os
            return {"ok": True, "texto": (f"Dataset {_os.path.basename(ruta)} y guion "
                                          f"{_os.path.basename(guion)} listos.")}

        if accion == "repetir_rutina":
            import demostracion
            return {"ok": True, "texto": demostracion.repetir(valor, log=log)}

        if accion == "mision_parar":
            if getattr(core, "mision_piloto", None) is None:
                return {"ok": False, "texto": "No hay ninguna misión en marcha."}
            return {"ok": True, "texto": core.mision_piloto.detener()}

        if accion == "copia":
            import cerebro_backup
            ruta = cerebro_backup.exportar(log=log)
            return {"ok": True, "texto": f"Copia creada en {os.path.basename(ruta)}"}

        if accion == "mantenimiento":
            return {"ok": True, "texto": core.mantenimiento_memoria()}

        if accion in ("canarios_on", "canarios_off"):
            import canarios
            if accion.endswith("on"):
                texto = canarios.desplegar(log=log)
                if getattr(core, "canarios", None) is None:
                    core.canarios = canarios.Canarios(core, log=log)
                return {"ok": True, "texto": texto + " " + core.canarios.start()}
            if getattr(core, "canarios", None) is not None:
                core.canarios.stop()
            return {"ok": True, "texto": canarios.retirar(log=log)}

        if accion == "restaurar_red":
            import canarios
            return {"ok": True, "texto": canarios.restaurar_red(log=log)}

        if accion in ("aprobar_habilidad", "descartar_habilidad"):
            import autoskills
            if not valor:
                return {"ok": False, "texto": "Falta el nombre de la habilidad."}
            texto = (autoskills.aprobar(valor, log=log) if accion.startswith("aprobar")
                     else autoskills.descartar(valor))
            return {"ok": True, "texto": texto}

        if accion == "parte_manana":
            import orquestador
            return {"ok": True, "texto": orquestador.parte_de_manana(core, log=log)}

        if accion == "metricas_reset":
            import metricas
            metricas.reiniciar()
            return {"ok": True, "texto": "Métricas reiniciadas."}

        if accion == "colisiones":
            import colisiones
            return {"ok": True, "texto": colisiones.informe(log=log)[:2000]}

    except Exception as e:
        return {"ok": False, "texto": f"{type(e).__name__}: {str(e)[:200]}"}
    return {"ok": False, "texto": "Mando no implementado"}
