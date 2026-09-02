#!/usr/bin/env python3
"""
test_conectores.py - Prueba los conectores contra un Google Calendar falso.

Ejecuta:  python test_conectores.py

Levanta un servidor MCP de mentira en el puerto del calendario, le pide a
JARVIS cosas en espanol y comprueba que llama a la herramienta correcta,
con los argumentos correctos, y que SIEMPRE avisa de lo que se le pidio.
No toca tu Google Calendar real.
"""
import json
import os
import sys
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

PUERTO = 8399          # puerto de pruebas, no el real
llamadas = []          # lo que el conector pidio al servidor
agenda = []            # "eventos" del calendario falso


class CalendarioFalso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _responder(self, payload, code=200):
        cuerpo = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path == "/health":
            return self._responder({"status": "ok"})
        self._responder({"error": "no"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        peticion = json.loads(self.rfile.read(n) or "{}")
        herramienta = peticion.get("tool")
        args = peticion.get("arguments", {})
        llamadas.append((herramienta, args))

        if herramienta == "cal_create_event":
            ev = {"id": f"ev{len(agenda)}", "summary": args["summary"],
                  "start": args["start"], "end": args["end"],
                  "htmlLink": "https://calendar.google.com/evento"}
            agenda.append(ev)
            return self._responder({"result": ev})
        if herramienta == "cal_list_events":
            return self._responder({"result": list(agenda)})
        if herramienta == "cal_delete_event":
            agenda[:] = [e for e in agenda if e["id"] != args["event_id"]]
            return self._responder({"result": True})
        self._responder({"error": f"herramienta desconocida: {herramienta}"})


fallos = []


def comprobar(nombre, fn):
    try:
        fn()
        print(f"  [OK]  {nombre}")
    except AssertionError as e:
        fallos.append(f"{nombre}: {e}")
        print(f"  [MAL] {nombre}: {e}")
    except Exception as e:
        fallos.append(f"{nombre}: {type(e).__name__}: {e}")
        print(f"  [MAL] {nombre}: {type(e).__name__}: {e}")


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), CalendarioFalso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    import conectores
    avisos = []
    c = conectores.Conectores(
        log=lambda m: None,
        notify=avisos.append,
        servidores={"calendar": PUERTO},
    )

    print("=== DISPONIBILIDAD ===")
    comprobar("el conector ve el servidor vivo",
              lambda: (_ for _ in ()).throw(AssertionError("no responde"))
              if not c.estado().get("Google Calendar") else None)

    print("\n=== AGENDAR ===")

    def agendar_manana():
        llamadas.clear(); avisos.clear()
        r = c.handle("Jarvis, agenda una reunion con Marta manana a las 17:00")
        assert r, "no respondio"
        assert llamadas, "no llamo al calendario"
        tool, args = llamadas[0]
        assert tool == "cal_create_event", f"llamo a {tool}"
        inicio = datetime.fromisoformat(args["start"])
        manana = (datetime.now() + timedelta(days=1)).date()
        assert inicio.date() == manana, f"fecha {inicio.date()}, esperaba {manana}"
        assert inicio.hour == 17, f"hora {inicio.hour}, esperaba 17"
        assert "marta" in args["summary"].lower(), f"asunto: {args['summary']}"
    comprobar("«agenda una reunion con Marta manana a las 17:00»", agendar_manana)

    def notifica_siempre():
        llamadas.clear(); avisos.clear()
        c.handle("apunta en el calendario dentista el jueves a las 10")
        assert avisos, "no notifico nada"
        aviso = avisos[0]
        assert "pidió" in aviso, f"el aviso no repite la orden: {aviso}"
        assert "dentista" in aviso.lower(), f"el aviso no dice que se agendo: {aviso}"
    comprobar("notifica SIEMPRE y repite lo que se le pidio", notifica_siempre)

    def duracion_una_hora():
        llamadas.clear()
        c.handle("agenda en el calendario comida manana a las 14")
        _, args = llamadas[0]
        ini = datetime.fromisoformat(args["start"])
        fin = datetime.fromisoformat(args["end"])
        assert fin - ini == timedelta(hours=1), f"dura {fin - ini}"
    comprobar("el evento dura una hora por defecto", duracion_una_hora)

    def sin_fecha_pregunta():
        llamadas.clear()
        r = c.handle("agenda en el calendario una cita con el gestor")
        assert not llamadas, "creo el evento sin saber cuando"
        assert "cuándo" in r or "cuando" in r, f"no pregunta por la fecha: {r}"
    comprobar("sin fecha, pregunta en vez de inventarse una", sin_fecha_pregunta)

    print("\n=== CONSULTAR ===")

    def consultar():
        llamadas.clear()
        r = c.handle("que citas tengo manana")
        assert llamadas and llamadas[0][0] == "cal_list_events", f"{llamadas}"
        assert "señor" in r.lower(), r
    comprobar("«que citas tengo manana» consulta Google Calendar", consultar)

    def consultar_en_calendario():
        llamadas.clear()
        c.handle("que tengo esta semana en el calendario")
        assert llamadas and llamadas[0][0] == "cal_list_events", f"{llamadas}"
    comprobar("«que tengo esta semana en el calendario»", consultar_en_calendario)

    def respeta_agenda_local():
        # Sin nombrar calendario/cita/reunion la orden es de la agenda LOCAL
        # que ya trae jarvis_skills: el conector no debe robarsela.
        llamadas.clear()
        assert c.handle("que tengo manana") is None, "secuestro la agenda local"
        assert c.handle("recuerdame comprar pan manana") is None, "secuestro un recordatorio"
        assert not llamadas, f"llamo a Google sin que se lo pidieran: {llamadas}"
    comprobar("no le roba ordenes a la agenda local", respeta_agenda_local)

    print("\n=== CANCELAR ===")

    def cancelar():
        agenda.clear(); llamadas.clear(); avisos.clear()
        c.handle("agenda en el calendario dentista manana a las 9")
        llamadas.clear(); avisos.clear()
        r = c.handle("cancela la cita del dentista")
        borrados = [x for x in llamadas if x[0] == "cal_delete_event"]
        assert borrados, f"no borro nada: {llamadas}"
        assert avisos, "no notifico la cancelacion"
        assert "cancelada" in r.lower(), r
    comprobar("«cancela la cita del dentista»", cancelar)

    print("\n=== NO SECUESTRA OTRAS ORDENES ===")
    for frase in ("que hora es", "pon musica", "abre el bloc de notas",
                  "cuentame un chiste", "apaga el ordenador"):
        comprobar(f"ignora «{frase}»",
                  lambda f=frase: (_ for _ in ()).throw(
                      AssertionError(f"la intercepto: {c.handle(f)}"))
                  if c.handle(f) else None)

    print("\n=== SERVICIO CAIDO ===")

    def servicio_caido():
        roto = conectores.Conectores(log=lambda m: None, notify=avisos.append,
                                     servidores={"calendar": 9})  # puerto muerto
        r = roto.handle("agenda en el calendario prueba manana a las 12")
        assert r and "no pude" in r.lower(), f"no explica el fallo: {r}"
    comprobar("con el servidor caido responde y explica por que", servicio_caido)

    print("\n=== FECHA Y HORA EN ESPANOL ===")

    def fechas():
        from datetime import datetime
        C = conectores.ConectorCalendar
        ahora = datetime.now()
        man = (ahora + timedelta(days=1)).date()
        casos = [
            # (frase, dia esperado, hora, minuto)
            ("cita con mi novia manana a las 6 de la tarde", man, 18, 0),
            ("cita manana a las seis de la tarde", man, 18, 0),
            ("cita manana a las 8 y media de la noche", man, 20, 30),
            ("cita manana a las 10 y cuarto", man, 10, 15),
            ("cita manana a las 9 menos cuarto", man, 8, 45),
            ("reunion hoy a las 11 de la manana", ahora.date(), 11, 0),
            ("cita esta noche a las 9", ahora.date(), 21, 0),
            ("cita manana a las 17:30", man, 17, 30),
            ("cita pasado manana al mediodia",
             (ahora + timedelta(days=2)).date(), 12, 0),
        ]
        for frase, dia, h, mi in casos:
            d = C._cuando(conectores._norm(frase))
            assert d is not None, f"«{frase}» no se entendio"
            assert d.date() == dia, f"«{frase}» -> dia {d.date()}, esperaba {dia}"
            assert (d.hour, d.minute) == (h, mi), \
                f"«{frase}» -> {d.hour}:{d.minute:02d}, esperaba {h}:{mi:02d}"
    comprobar("fechas y horas escritas de todas las formas", fechas)

    def sin_confundir_manana():
        # "de la manana" contiene "manana": no debe mover el evento un dia.
        from datetime import datetime
        C = conectores.ConectorCalendar
        d = C._cuando(conectores._norm("reunion hoy a las 11 de la manana"))
        assert d.date() == datetime.now().date(), f"se fue a {d.date()}"
    comprobar("«hoy ... de la manana» no salta al dia siguiente", sin_confundir_manana)

    def hora_llega_a_google():
        llamadas.clear()
        c.handle("agenda en el calendario cena con mi novia manana a las 6 de la tarde")
        assert llamadas, "no llamo al calendario"
        _, args = llamadas[0]
        ini = datetime.fromisoformat(args["start"])
        assert ini.hour == 18, f"mando las {ini.hour}:00 a Google, esperaba las 18:00"
        assert ini.date() == (datetime.now() + timedelta(days=1)).date()
        assert "novia" in args["summary"].lower(), f"titulo: {args['summary']}"
    comprobar("la hora correcta llega hasta Google", hora_llega_a_google)

    print("\n=== RESPUESTAS RARAS DEL SERVIDOR ===")

    def respuesta_malformada():
        # Un servidor que devuelve un dict donde tocaba una lista no debe
        # tumbar el conector ni mandar la orden al LLM sin decir nada.
        cal = c.conectores[0]
        original = cal.llamar
        for basura in ({"no": "es una lista"}, None, "texto", 42):
            cal.llamar = lambda *a, _b=basura, **k: _b
            r = c.handle("que citas tengo manana")
            assert isinstance(r, str) and r.strip(), f"se rompio con {basura!r}"
        cal.llamar = original
    comprobar("tolera respuestas con forma inesperada", respuesta_malformada)

    def titulos_limpios():
        casos = [("Jarvis, agenda una reunion con Marta manana a las 17:00", "reunion con Marta"),
                 ("apunta en el calendario Dentista el jueves a las 10", "Dentista"),
                 ("agenda en mi calendario Comida con papá mañana a las 14:30", "Comida con papá")]
        cal = c.conectores[0]
        for frase, esperado in casos:
            _, asunto = cal._cuando_y_asunto(conectores._norm(frase), frase)
            assert asunto == esperado, f"«{frase[:40]}» dio «{asunto}», esperaba «{esperado}»"
    comprobar("el titulo del evento sale limpio y con tildes", titulos_limpios)

    srv.shutdown()
    print("\n=== RESUMEN ===")
    if fallos:
        for f in fallos:
            print("  - " + f)
        return 1
    print("  Conectores operativos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
