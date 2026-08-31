/* ============================================================================
   Pruebas de concurrencia del motor de voz (hud_assets/voice.js)
   ---------------------------------------------------------------------------
   Cubren tres carreras reales que se colaron en la primera version del HUD
   AETHER y que detecto la revision automatica de la PR #1:

     1. Una locucion antigua que resolvia tarde apagaba a la que ya estaba
        hablando: su done() ponia speaking=false y el estado en 'idle'.
     2. Un stop() durante un getUserMedia pendiente no impedia que despues se
        arrancara la grabacion. El microfono quedaba abierto indefinidamente,
        porque cuando stop() paso, _mr todavia era null y no habia nada que
        parar.
     3. Un stop() seguido de un start() rapido dejaba que el stream de la
        sesion anterior se enganchara a la nueva, con dos bucles de medicion
        peleandose por el mismo orbe.

     4. stop() no cerraba la promesa devuelta por speak(): _speakServer solo
        resolvia en 'ended', y pause() no lo dispara, asi que quien esperara
        esa promesa se quedaba colgado para siempre.
     5. Los callbacks de SpeechRecognition no llevaban guardia de generacion:
        el onend del reconocedor anterior veia listening=true (ya de la
        sesion nueva) y la mataba, y su onresult colaba una transcripcion
        vieja como mensaje de la nueva.

   Todas se corrigen con un contador de generacion en AetherVoice y en
   AetherEars, mas un cierre explicito de la promesa en stop().

   Ejecutar:  node hud_assets/tests/test_voice_races.js
   Sin dependencias: usa el modulo vm de Node con dobles de navegador.
   ========================================================================= */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const RUTA_VOICE = path.join(__dirname, '..', 'voice.js');

let fallos = 0;
function ok(cond, msg) {
  console.log((cond ? '  [OK]   ' : '  [FALLO]') + ' ' + msg);
  if (!cond) fallos++;
}

/* Monta voice.js en un contexto aislado con los dobles que se le pasen. */
function cargar(extra) {
  const sandbox = {
    console,
    performance: { now: () => Date.now() },
    setTimeout, clearTimeout, setInterval, clearInterval,
    requestAnimationFrame: (fn) => setTimeout(fn, 8),
    cancelAnimationFrame: (id) => clearTimeout(id),
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} },
    navigator: {},
    fetch: () => Promise.reject(new Error('sin servidor')),
    AbortController: function () { this.signal = {}; this.abort = () => {}; },
  };
  Object.assign(sandbox, extra || {});
  sandbox.window = sandbox;
  sandbox.global = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(RUTA_VOICE, 'utf8'), sandbox);
  return sandbox;
}

(async () => {
  // ── 1. Locucion vieja que resuelve tarde no debe apagar a la nueva ───────
  console.log('\n1. Locucion obsoleta pisando a una mas reciente');
  {
    const sb = cargar({
      speechSynthesis: {
        cancel() {},
        getVoices: () => [
          { name: 'Microsoft Pablo', lang: 'es-ES', voiceURI: 'p', localService: true },
        ],
        speak(u) { setTimeout(() => u.onend && u.onend(), 120); },
      },
      SpeechSynthesisUtterance: function (t) { this.text = t; },
    });
    const estados = [];
    const v = new sb.AetherVoice({
      agent: 'jarvis', preferServer: false,
      onState: (s) => estados.push(s),
    });
    v.voices = sb.speechSynthesis.getVoices();
    v.selectBestVoice();

    const p1 = v.speak('Primera frase.');
    await new Promise((r) => setTimeout(r, 30));
    const p2 = v.speak('Segunda frase.');          // pisa a la primera
    await Promise.all([p1, p2]);
    await new Promise((r) => setTimeout(r, 60));

    // Tras la segunda locucion debe haber exactamente un 'idle': el suyo.
    // Con el fallo, la primera colaba un 'idle' extra y la dejaba muda.
    const iSpeak2 = estados.lastIndexOf('speak');
    const idleTrasSegunda = estados.slice(iSpeak2).filter((s) => s === 'idle').length;
    ok(idleTrasSegunda === 1,
       'la segunda locucion recibe exactamente un idle final (recibio ' + idleTrasSegunda + ')');
    ok(v._gen >= 2, 'el contador de generacion avanzo (' + v._gen + ')');
    ok(v.speaking === false, 'speaking queda en false al terminar');
  }

  // ── 2. stop() antes de que getUserMedia resuelva no debe dejar el micro ──
  console.log('\n2. MediaRecorder arrancado tras un stop()');
  {
    let resolverGUM;
    const pista = { parada: false, stop() { this.parada = true; } };
    const stream = { getTracks: () => [pista] };
    let arrancado = false;

    const sb = cargar({
      navigator: {
        mediaDevices: {
          getUserMedia: () => new Promise((res) => { resolverGUM = () => res(stream); }),
        },
      },
      MediaRecorder: function () {
        this.state = 'inactive';
        this.start = () => { arrancado = true; this.state = 'recording'; };
        this.stop = () => { this.state = 'inactive'; };
      },
    });
    // Sin SpeechRecognition en el sandbox, start() cae al camino de grabacion.
    const e = new sb.AetherEars({});
    e.start();
    await new Promise((r) => setTimeout(r, 10));
    e.stop();                       // paramos ANTES de que el permiso resuelva
    resolverGUM();
    await new Promise((r) => setTimeout(r, 40));

    ok(arrancado === false, 'no se arranca la grabacion tras el stop()');
    ok(pista.parada === true, 'se libera la pista del microfono');
  }

  // ── 3. Medidor de una sesion vieja no debe engancharse a la nueva ────────
  console.log('\n3. Medidor obsoleto tras stop() + start() rapidos');
  {
    const streams = [];
    const resolvers = [];
    let n = 0;
    const sb = cargar({
      navigator: {
        mediaDevices: {
          getUserMedia: () => new Promise((res) => {
            const id = n++;
            const pista = { id, parada: false, stop() { this.parada = true; } };
            const st = { id, getTracks: () => [pista], pista };
            streams.push(st);
            resolvers.push(() => res(st));
          }),
        },
      },
      MediaRecorder: function () {
        this.state = 'inactive'; this.start = () => {}; this.stop = () => {};
      },
      AudioContext: function () {
        this.close = () => {};
        this.createMediaStreamSource = () => ({ connect: () => {} });
        this.createAnalyser = () => ({
          fftSize: 0, smoothingTimeConstant: 0, frequencyBinCount: 64,
          connect: () => {}, getByteFrequencyData: (b) => b.fill(0),
        });
      },
    });
    const e = new sb.AetherEars({});
    e.start();                       // sesion 1: pide medidor y grabacion
    await new Promise((r) => setTimeout(r, 10));
    e.stop();
    e.start();                       // sesion 2
    await new Promise((r) => setTimeout(r, 10));
    resolvers.forEach((f) => f());   // resuelven TODOS, los de la sesion 1 incluidos
    await new Promise((r) => setTimeout(r, 60));

    const viejosVivos = streams.slice(0, 2).filter((s) => !s.pista.parada).length;
    ok(viejosVivos === 0,
       'los streams de la sesion anterior quedan liberados (' + viejosVivos + ' vivos)');
    ok(e._gen >= 2, 'la generacion de escucha avanzo (' + e._gen + ')');
    e.stop();
  }

  // ── 4. stop() debe cerrar la promesa de speak(), no dejarla colgada ──────
  console.log('\n4. speak() interrumpido por stop()');
  {
    const sb = cargar({
      speechSynthesis: {
        cancel() {},
        getVoices: () => [{ name: 'Microsoft Pablo', lang: 'es-ES', voiceURI: 'p' }],
        // Nunca dispara onend: simula una locucion que se corta a medias.
        speak() {},
      },
      SpeechSynthesisUtterance: function (t) { this.text = t; },
    });
    const v = new sb.AetherVoice({ agent: 'jarvis', preferServer: false });
    v.voices = sb.speechSynthesis.getVoices();
    v.selectBestVoice();

    let resuelta = false;
    v.speak('Una frase larga que se va a interrumpir.').then(() => { resuelta = true; });
    await new Promise((r) => setTimeout(r, 40));
    v.stop();                       // corta en seco
    await new Promise((r) => setTimeout(r, 60));

    ok(resuelta === true, 'la promesa de speak() se asienta tras stop()');
  }

  // ── 5. Callbacks de un reconocedor viejo no deben tocar la sesion nueva ──
  console.log('\n5. SpeechRecognition obsoleto tras stop() + start()');
  {
    const recs = [];
    const sb = cargar({
      navigator: { mediaDevices: { getUserMedia: () => new Promise(() => {}) } },
      SpeechRecognition: function () {
        const r = this;
        r.start = () => {}; r.stop = () => {};
        recs.push(r);
      },
    });
    let finales = 0;
    const e = new sb.AetherEars({ onFinal: () => { finales++; } });
    e.start();                       // sesion 1 -> recs[0]
    e.stop();
    e.start();                       // sesion 2 -> recs[1]

    // El reconocedor de la sesion 1 emite tarde, como haria de verdad.
    recs[0].onresult({
      resultIndex: 0,
      results: [Object.assign([{ transcript: 'texto viejo' }], { 0: [{ transcript: 'texto viejo' }], isFinal: true, length: 1 })],
    });
    recs[0].onend();

    ok(finales === 0, 'la transcripcion vieja no se envia (' + finales + ' enviadas)');
    ok(e.listening === true, 'la sesion nueva sigue viva tras el onend del viejo');
    e.stop();
  }

  console.log('\n' + (fallos === 0 ? 'TODAS LAS PRUEBAS PASAN' : fallos + ' FALLO(S)'));
  process.exit(fallos === 0 ? 0 : 1);
})();
