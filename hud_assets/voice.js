/* ============================================================================
   AETHER VOICE — motor de voz MASCULINA para JARVIS y ULTRON
   ---------------------------------------------------------------------------
   - Selección de voz por puntuación: descarta voces femeninas conocidas y
     prioriza voces masculinas neuronales en español.
   - Perfiles por agente: JARVIS = mayordomo británico sereno y grave.
                          ULTRON = barítono profundo, lento, amenazante.
   - Cadena de síntesis: /api/speak (ElevenLabs) -> /tts (servidor) -> navegador.
   - Análisis de nivel de audio en vivo (para alimentar el orbe).
   - Reconocimiento de voz: SpeechRecognition -> MediaRecorder + POST /voice.
   ========================================================================= */
(function (global) {
  'use strict';

  /* ── Léxico de género de voces en español ──────────────────────────────
     Las APIs de voz no exponen el género de forma fiable, así que lo
     deducimos del nombre del hablante. Estas listas cubren las voces de
     Windows (SAPI/Neural), macOS/iOS, Android y Chrome. */
  var MALE = [
    // Microsoft (SAPI + Neural)
    'pablo', 'raul', 'raúl', 'alvaro', 'álvaro', 'jorge', 'enrique', 'elias', 'elías',
    'liberto', 'nil', 'saul', 'saúl', 'teo', 'yago', 'lorenzo', 'cecilio', 'gerardo',
    'luciano', 'dario', 'darío', 'tomas', 'tomás', 'gonzalo', 'sebastian', 'sebastián',
    'rodrigo', 'javier', 'mateo', 'santiago', 'andres', 'andrés',
    // Apple
    'diego', 'juan', 'carlos', 'francisca_no', 'miguel', 'marcos',
    // Piper / open source
    'davefx', 'carlfm', 'sharvard', 'claude', 'ald',
    // Genéricos en inglés (último recurso si no hay español)
    'david', 'mark', 'george', 'daniel', 'alex', 'fred', 'guy', 'ryan', 'thomas',
    'james', 'aaron', 'arthur', 'oliver', 'reed', 'rishi', 'eric', 'brandon'
  ];
  var FEMALE = [
    'helena', 'laura', 'sabina', 'monica', 'mónica', 'paulina', 'angelina', 'marisol',
    'esperanza', 'larissa', 'ximena', 'dalia', 'renata', 'triana', 'estrella', 'irene',
    'lia', 'lía', 'vera', 'abril', 'camila', 'catalina', 'isidora', 'lorena', 'maria',
    'maría', 'sofia', 'sofía', 'valentina', 'daniela', 'salome', 'salomé', 'carmen',
    'penelope', 'penélope', 'lucia', 'lucía', 'nuria', 'elvira', 'paloma', 'yolanda',
    'zira', 'hazel', 'susan', 'linda', 'heather', 'samantha', 'karen', 'moira', 'tessa',
    'fiona', 'victoria', 'allison', 'ava', 'nicky', 'serena', 'emma', 'amelie', 'sonia',
    'libby', 'jenny', 'aria', 'michelle', 'ana', 'paulina'
  ];

  /* Perfiles: definen carácter vocal. La voz es masculina en ambos casos;
     lo que cambia es el registro, el ritmo y la cadencia. */
  var PROFILES = {
    jarvis: {
      name: 'JARVIS',
      lang: 'es-ES',
      rate: 0.99,      // pausado pero eficiente
      pitch: 0.80,     // grave: registro de mayordomo
      volume: 1.0,
      piper: 'es_ES-davefx-medium',
      // Voces preferidas por nombre, en orden
      prefer: ['alvaro', 'álvaro', 'pablo', 'jorge', 'enrique', 'diego', 'juan', 'davefx'],
      // Micro-pausas tras signos: da cadencia de conversación, no de lectura
      cadence: 1.0
    },
    ultron: {
      name: 'ULTRON',
      lang: 'es-ES',
      rate: 0.86,      // lento: cada palabra pesa
      pitch: 0.58,     // muy grave: barítono metálico
      volume: 1.0,
      piper: 'es_ES-sharvard-medium',
      prefer: ['sharvard', 'jorge', 'raul', 'raúl', 'alvaro', 'álvaro', 'pablo', 'enrique'],
      cadence: 1.35
    }
  };

  /* Normaliza para comparar: minusculas y sin acentos. */
  function norm(s) {
    var t = String(s == null ? '' : s).toLowerCase();
    try { t = t.normalize('NFD').replace(/[\u0300-\u036f]/g, ''); } catch (e) {}
    return t;
  }
  /* Devuelve la entrada de `list` contenida en `hay`, o null. */
  function hits(hay, list) {
    var n = norm(hay);
    for (var i = 0; i < list.length; i++) {
      var k = norm(list[i]);
      if (k && n.indexOf(k) !== -1) return k;
    }
    return null;
  }

  /* ── Puntuación de una voz del navegador ─────────────────────────────────
     Mayor puntuación = mejor candidata. Una voz femenina detectada queda
     descalificada salvo que no exista ninguna alternativa. */
  function scoreVoice(v, profile) {
    var name = v.name || '';
    var lang = (v.lang || '').toLowerCase();
    var s = 0;

    if (lang.indexOf('es') === 0) s += 100;          // español
    else if (lang.indexOf('es') !== -1) s += 60;
    else s -= 40;                                     // otro idioma: mal último recurso

    if (lang === norm(profile.lang)) s += 25;         // variante exacta (es-ES)
    else if (lang.indexOf('es-mx') === 0 || lang.indexOf('es-us') === 0) s += 14;
    else if (lang.indexOf('es-ar') === 0 || lang.indexOf('es-419') === 0) s += 8;

    var f = hits(name, FEMALE);
    var m = hits(name, MALE);
    if (f && !m) s -= 500;                            // descalificada
    if (m) s += 120;                                  // masculina confirmada

    var prefer = profile._prefN || (profile._prefN = profile.prefer.map(norm));
    var p = m ? prefer.indexOf(m) : -1;
    if (m && p !== -1) s += 60 - p * 6;               // orden de preferencia

    var n = norm(name);
    if (n.indexOf('neural') !== -1) s += 40;          // calidad
    if (n.indexOf('natural') !== -1) s += 35;
    if (n.indexOf('online') !== -1) s += 12;
    if (n.indexOf('premium') !== -1 || n.indexOf('enhanced') !== -1) s += 30;
    if (n.indexOf('compact') !== -1 || n.indexOf('x_low') !== -1) s -= 25;
    if (v.localService) s += 8;                       // baja latencia
    if (v.default) s += 4;
    return s;
  }

  /* ── Motor ──────────────────────────────────────────────────────────── */
  function AetherVoice(opts) {
    opts = opts || {};
    this.agent = (opts.agent || 'jarvis').toLowerCase();
    this.profile = Object.assign({}, PROFILES[this.agent] || PROFILES.jarvis, opts.profile || {});
    this.base = opts.base || '';
    this.token = opts.token || '';
    this.enabled = opts.enabled !== false;
    this.preferServer = opts.preferServer !== false;   // ElevenLabs primero
    this.onLevel = opts.onLevel || function () {};
    this.onState = opts.onState || function () {};
    this.onLog = opts.onLog || function () {};

    this.voice = null;
    this.voiceOverride = null;    // voiceURI elegido a mano en ajustes
    this.speaking = false;
    this._audio = null;
    this._ac = null;
    this._analyser = null;
    this._levelRaf = 0;
    this._queue = [];
    this._voicesReady = false;

    this._loadVoices();
  }

  AetherVoice.PROFILES = PROFILES;

  /* Las voces llegan de forma asíncrona en Chrome: hay que esperar el evento. */
  AetherVoice.prototype._loadVoices = function () {
    var self = this;
    if (!('speechSynthesis' in global)) return;
    function pick() {
      var list = global.speechSynthesis.getVoices() || [];
      if (!list.length) return false;
      self.voices = list;
      self._voicesReady = true;
      self.selectBestVoice();
      return true;
    }
    if (!pick()) {
      global.speechSynthesis.onvoiceschanged = function () { pick(); };
      // Chrome a veces no dispara el evento: reintento acotado
      var n = 0;
      var iv = setInterval(function () {
        if (pick() || ++n > 20) clearInterval(iv);
      }, 250);
    }
  };

  /** Elige la mejor voz masculina disponible para el perfil actual. */
  AetherVoice.prototype.selectBestVoice = function () {
    if (!this.voices || !this.voices.length) return null;
    var self = this;

    if (this.voiceOverride) {
      var forced = this.voices.filter(function (v) { return v.voiceURI === self.voiceOverride; })[0];
      if (forced) { this.voice = forced; return forced; }
    }

    var ranked = this.voices
      .map(function (v) { return { v: v, s: scoreVoice(v, self.profile) }; })
      .sort(function (a, b) { return b.s - a.s; });

    this.voice = ranked[0] ? ranked[0].v : null;
    this.ranked = ranked;
    if (this.voice) {
      var masc = hits(this.voice.name, MALE) ? 'masculina' : 'sin género confirmado';
      this.onLog('Voz seleccionada: ' + this.voice.name + ' (' + this.voice.lang + ', ' + masc + ')');
    }
    return this.voice;
  };

  /** Voces ordenadas para poblar el selector de ajustes. */
  AetherVoice.prototype.listVoices = function () {
    var self = this;
    if (!this.voices) return [];
    return this.voices
      .map(function (v) {
        var m = hits(v.name, MALE), f = hits(v.name, FEMALE);
        return {
          uri: v.voiceURI, name: v.name, lang: v.lang,
          gender: m && !f ? 'M' : (f ? 'F' : '?'),
          score: scoreVoice(v, self.profile)
        };
      })
      .sort(function (a, b) { return b.score - a.score; });
  };

  AetherVoice.prototype.setAgent = function (agent) {
    this.agent = agent;
    this.profile = Object.assign({}, PROFILES[agent] || PROFILES.jarvis);
    this.selectBestVoice();
  };

  AetherVoice.prototype.setVoiceURI = function (uri) {
    this.voiceOverride = uri || null;
    this.selectBestVoice();
  };

  /* ── Cadencia: puntuación explícita para que la prosodia respire ────────
     Sin esto, el TTS lee de corrido y suena a lector de PDF. */
  AetherVoice.prototype._shape = function (text) {
    var t = String(text || '')
      .replace(/```[\s\S]*?```/g, ' bloque de código omitido. ')  // no leer código
      .replace(/`([^`]+)`/g, '$1')
      .replace(/[*_#>|]/g, ' ')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')                    // markdown links
      .replace(/https?:\/\/\S+/g, ' un enlace ')
      .replace(/\s+/g, ' ')
      .trim();
    if (this.profile.cadence > 1.15) {
      // ULTRON: pausas largas tras cada frase; el silencio es parte del tono.
      t = t.replace(/([.!?])\s+/g, '$1 ... ');
    }
    return t.slice(0, 1200);
  };

  /* ── Nivel de audio en vivo desde un <audio> ──────────────────────────── */
  AetherVoice.prototype._attachAnalyser = function (el) {
    try {
      var AC = global.AudioContext || global.webkitAudioContext;
      if (!AC) return;
      this._ac = this._ac || new AC();
      if (this._ac.state === 'suspended') this._ac.resume();
      var src = this._ac.createMediaElementSource(el);
      var an = this._ac.createAnalyser();
      an.fftSize = 512;
      an.smoothingTimeConstant = 0.72;
      src.connect(an);
      an.connect(this._ac.destination);
      this._analyser = an;
      this._pumpLevel();
    } catch (e) { /* el navegador puede bloquearlo; el orbe usará envolvente falsa */ }
  };

  AetherVoice.prototype._pumpLevel = function () {
    var self = this;
    if (!this._analyser) return;
    var buf = new Uint8Array(this._analyser.frequencyBinCount);
    (function loop() {
      if (!self.speaking || !self._analyser) { self.onLevel(0); return; }
      self._levelRaf = requestAnimationFrame(loop);
      self._analyser.getByteFrequencyData(buf);
      var sum = 0;
      // Sólo la banda de voz (~85 Hz–3 kHz) para que el nivel siga al habla.
      var top = Math.max(8, Math.floor(buf.length * 0.28));
      for (var i = 2; i < top; i++) sum += buf[i] * buf[i];
      var rms = Math.sqrt(sum / (top - 2)) / 255;
      self.onLevel(Math.min(1, rms * 2.6));
    })();
  };

  /* Envolvente sintética: cuando no hay acceso al audio (speechSynthesis),
     generamos un nivel plausible para que el orbe no se quede plano. */
  AetherVoice.prototype._fakeEnvelope = function () {
    var self = this, t0 = performance.now();
    (function loop() {
      if (!self.speaking) { self.onLevel(0); return; }
      self._levelRaf = requestAnimationFrame(loop);
      var t = (performance.now() - t0) / 1000;
      var v = 0.34
        + 0.24 * Math.sin(t * 11.3)
        + 0.16 * Math.sin(t * 5.1 + 1.2)
        + 0.10 * Math.sin(t * 23.7 + 0.4);
      self.onLevel(Math.max(0.06, Math.min(1, v)));
    })();
  };

  /** Habla. Devuelve una promesa que resuelve al terminar. */
  AetherVoice.prototype.speak = function (text) {
    var self = this;
    var t = this._shape(text);
    if (!this.enabled || !t) return Promise.resolve(false);
    this.stop();

    return new Promise(function (resolve) {
      function done(ok) {
        self.speaking = false;
        if (self._levelRaf) cancelAnimationFrame(self._levelRaf);
        self.onLevel(0);
        self.onState('idle');
        resolve(ok);
      }
      self.speaking = true;
      self.onState('speak');

      if (self.preferServer) {
        self._speakServer(t).then(function (ok) {
          if (ok) { done(true); return; }
          self._speakBrowser(t).then(done);
        });
      } else {
        self._speakBrowser(t).then(done);
      }
    });
  };

  /* Servidor: ElevenLabs vía /api/speak. Devuelve MP3 reproducible aquí,
     lo que permite analizar el audio real y sincronizar el orbe. */
  AetherVoice.prototype._speakServer = function (text) {
    var self = this;
    return new Promise(function (resolve) {
      var ctrl = new AbortController();
      var to = setTimeout(function () { ctrl.abort(); }, 12000);
      fetch(self.base + '/api/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Auth-Token': self.token || '' },
        body: JSON.stringify({ text: text, token: self.token || '' }),
        signal: ctrl.signal
      }).then(function (r) {
        clearTimeout(to);
        if (!r.ok) { resolve(false); return; }
        return r.blob();
      }).then(function (blob) {
        if (!blob || !blob.size) { resolve(false); return; }
        var url = URL.createObjectURL(blob);
        var a = new Audio(url);
        a.crossOrigin = 'anonymous';
        a.volume = self.profile.volume;
        // El servidor ya entrega la voz correcta; sólo afinamos el ritmo.
        try { a.playbackRate = Math.max(0.75, Math.min(1.2, self.profile.rate)); } catch (e) {}
        self._audio = a;
        self._attachAnalyser(a);
        if (!self._analyser) self._fakeEnvelope();
        a.onended = function () { URL.revokeObjectURL(url); resolve(true); };
        a.onerror = function () { URL.revokeObjectURL(url); resolve(false); };
        a.play().catch(function () { URL.revokeObjectURL(url); resolve(false); });
      }).catch(function () { clearTimeout(to); resolve(false); });
    });
  };

  /* Navegador: speechSynthesis con la voz masculina puntuada más alta. */
  AetherVoice.prototype._speakBrowser = function (text) {
    var self = this;
    return new Promise(function (resolve) {
      if (!('speechSynthesis' in global)) { resolve(false); return; }
      if (!self.voice) self.selectBestVoice();

      // Chrome corta enunciados largos: los troceamos por frases.
      var chunks = text.match(/[^.!?…]+[.!?…]*/g) || [text];
      var merged = [], cur = '';
      chunks.forEach(function (c) {
        if ((cur + c).length > 180) { if (cur) merged.push(cur); cur = c; }
        else cur += c;
      });
      if (cur) merged.push(cur);

      var i = 0;
      self._fakeEnvelope();
      function next() {
        if (!self.speaking || i >= merged.length) { resolve(true); return; }
        var u = new SpeechSynthesisUtterance(merged[i++].trim());
        if (self.voice) { u.voice = self.voice; u.lang = self.voice.lang; }
        else u.lang = self.profile.lang;
        u.rate = self.profile.rate;
        u.pitch = self.profile.pitch;   // <- el registro grave masculino
        u.volume = self.profile.volume;
        u.onend = next;
        u.onerror = function () { resolve(false); };
        try { global.speechSynthesis.speak(u); }
        catch (e) { resolve(false); }
      }
      // Chrome se "duerme" si hay una cola previa colgada.
      try { global.speechSynthesis.cancel(); } catch (e) {}
      setTimeout(next, 40);
    });
  };

  AetherVoice.prototype.stop = function () {
    this.speaking = false;
    if (this._levelRaf) cancelAnimationFrame(this._levelRaf);
    this.onLevel(0);
    try { if (global.speechSynthesis) global.speechSynthesis.cancel(); } catch (e) {}
    if (this._audio) {
      try { this._audio.pause(); this._audio.currentTime = 0; } catch (e) {}
      this._audio = null;
    }
    this._analyser = null;
  };

  /* ── Escucha ───────────────────────────────────────────────────────────
     SpeechRecognition cuando existe (resultados parciales instantáneos);
     si no, grabamos y lo transcribe Whisper en el servidor vía POST /voice. */
  function AetherEars(opts) {
    opts = opts || {};
    this.base = opts.base || '';
    this.token = opts.token || '';
    this.lang = opts.lang || 'es-ES';
    this.onPartial = opts.onPartial || function () {};
    this.onFinal = opts.onFinal || function () {};
    this.onLevel = opts.onLevel || function () {};
    this.onState = opts.onState || function () {};
    this.onError = opts.onError || function () {};
    this.listening = false;
    this._rec = null;
    this._mr = null;
    this._stream = null;
    this._raf = 0;
  }

  AetherEars.prototype.supported = function () {
    return !!(global.SpeechRecognition || global.webkitSpeechRecognition ||
              (global.navigator && navigator.mediaDevices));
  };

  AetherEars.prototype.toggle = function () {
    return this.listening ? this.stop() : this.start();
  };

  AetherEars.prototype.start = function () {
    var self = this;
    if (this.listening) return Promise.resolve();
    this.listening = true;
    this.onState('listen');
    var SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    // El medidor de nivel se monta siempre: alimenta el orbe mientras hablas.
    this._meter();
    if (SR) {
      var r = new SR();
      r.lang = this.lang;
      r.continuous = false;
      r.interimResults = true;
      r.maxAlternatives = 1;
      r.onresult = function (e) {
        var fin = '', part = '';
        for (var i = e.resultIndex; i < e.results.length; i++) {
          var tx = e.results[i][0].transcript;
          if (e.results[i].isFinal) fin += tx; else part += tx;
        }
        if (part) self.onPartial(part);
        if (fin) { self.onPartial(fin); self.onFinal(fin.trim()); }
      };
      r.onerror = function (e) {
        self.onError(e.error || 'reconocimiento');
        self.stop();
      };
      r.onend = function () { if (self.listening) self.stop(); };
      this._rec = r;
      try { r.start(); } catch (e) { this.onError('no pude abrir el micrófono'); this.stop(); }
      return Promise.resolve();
    }
    return this._recordFallback();
  };

  /* Fallback universal: graba webm y lo manda a /voice (Whisper del servidor). */
  AetherEars.prototype._recordFallback = function () {
    var self = this;
    if (!navigator.mediaDevices || !global.MediaRecorder) {
      this.onError('este navegador no permite grabar audio');
      this.stop();
      return Promise.resolve();
    }
    return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (st) {
      self._stream = st;
      var mr = new MediaRecorder(st);
      var parts = [];
      mr.ondataavailable = function (e) { if (e.data && e.data.size) parts.push(e.data); };
      mr.onstop = function () {
        var blob = new Blob(parts, { type: 'audio/webm' });
        if (!blob.size) return;
        self.onState('think');
        var fd = new FormData();
        fd.append('audio', blob, 'v.webm');
        fetch(self.base + '/voice?token=' + encodeURIComponent(self.token || ''), {
          method: 'POST', body: fd
        }).then(function (r) { return r.json(); })
          .then(function (j) {
            if (j && j.texto) { self.onPartial(j.texto); self.onFinal(j.texto, j.respuesta || ''); }
            else self.onError('no detecté voz');
          })
          .catch(function () { self.onError('fallo al transcribir'); });
      };
      self._mr = mr;
      mr.start();
      return null;
    }).catch(function () {
      self.onError('permiso de micrófono denegado');
      self.stop();
    });
  };

  /* Nivel del micrófono → orbe. Independiente del motor de reconocimiento. */
  AetherEars.prototype._meter = function () {
    var self = this;
    if (!navigator.mediaDevices) return;
    var AC = global.AudioContext || global.webkitAudioContext;
    if (!AC) return;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (st) {
      if (!self.listening) { st.getTracks().forEach(function (t) { t.stop(); }); return; }
      self._meterStream = st;
      var ac = new AC();
      var src = ac.createMediaStreamSource(st);
      var an = ac.createAnalyser();
      an.fftSize = 512; an.smoothingTimeConstant = 0.7;
      src.connect(an);
      var buf = new Uint8Array(an.frequencyBinCount);
      (function loop() {
        if (!self.listening) {
          self.onLevel(0);
          try { ac.close(); } catch (e) {}
          st.getTracks().forEach(function (t) { t.stop(); });
          return;
        }
        self._raf = requestAnimationFrame(loop);
        an.getByteFrequencyData(buf);
        var sum = 0, top = Math.max(8, Math.floor(buf.length * 0.3));
        for (var i = 2; i < top; i++) sum += buf[i] * buf[i];
        self.onLevel(Math.min(1, (Math.sqrt(sum / (top - 2)) / 255) * 3.0));
      })();
    }).catch(function () {});
  };

  AetherEars.prototype.stop = function () {
    this.listening = false;
    if (this._raf) cancelAnimationFrame(this._raf);
    this.onLevel(0);
    this.onState('idle');
    if (this._rec) { try { this._rec.stop(); } catch (e) {} this._rec = null; }
    if (this._mr && this._mr.state !== 'inactive') { try { this._mr.stop(); } catch (e) {} }
    this._mr = null;
    [this._stream, this._meterStream].forEach(function (s) {
      if (s) try { s.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
    });
    this._stream = this._meterStream = null;
    return Promise.resolve();
  };

  global.AetherVoice = AetherVoice;
  global.AetherEars = AetherEars;
})(window);
