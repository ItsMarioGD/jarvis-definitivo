/* ============================================================================
   AETHER ORB — núcleo de energía reactivo (WebGL + fallback Canvas2D)
   Estados: idle · listen · think · speak · alert
   Reacciona en tiempo real al nivel de audio (voz del usuario o del agente).
   ========================================================================= */
(function (global) {
  'use strict';

  var VERT = [
    'attribute vec2 p;',
    'void main(){ gl_Position = vec4(p, 0.0, 1.0); }'
  ].join('\n');

  var FRAG = [
    'precision highp float;',
    'uniform vec2  uRes;',
    'uniform float uTime;',
    'uniform float uLevel;',   // 0..1 energia de audio
    'uniform float uState;     // 0 idle 1 listen 2 think 3 speak 4 alert',
    'uniform vec3  uA;         // color acento',
    'uniform vec3  uB;         // color secundario',
    'uniform float uAggr;      // 0 = jarvis (organico), 1 = ultron (afilado)',

    // --- ruido value-noise + fbm ---------------------------------------
    'float hash(vec3 q){ return fract(sin(dot(q, vec3(127.1, 311.7, 74.7))) * 43758.5453); }',
    'float noise(vec3 x){',
    '  vec3 i = floor(x), f = fract(x);',
    '  f = f * f * (3.0 - 2.0 * f);',
    '  float n000=hash(i), n100=hash(i+vec3(1,0,0)), n010=hash(i+vec3(0,1,0)), n110=hash(i+vec3(1,1,0));',
    '  float n001=hash(i+vec3(0,0,1)), n101=hash(i+vec3(1,0,1)), n011=hash(i+vec3(0,1,1)), n111=hash(i+vec3(1,1,1));',
    '  return mix(mix(mix(n000,n100,f.x), mix(n010,n110,f.x), f.y),',
    '             mix(mix(n001,n101,f.x), mix(n011,n111,f.x), f.y), f.z);',
    '}',
    'float fbm(vec3 x){',
    '  float v = 0.0, a = 0.5;',
    '  for(int i = 0; i < 5; i++){ v += a * noise(x); x *= 2.02; a *= 0.5; }',
    '  return v;',
    '}',

    // --- anillo suave ---------------------------------------------------
    // Los bordes van siempre de menor a mayor: smoothstep con edge0 >= edge1
    // es comportamiento indefinido segun la spec de GLSL ES, aunque en la
    // practica los drivers lo traten como una rampa descendente.
    'float ring(float r, float rad, float w){ return 1.0 - smoothstep(0.0, w, abs(r - rad)); }',

    'void main(){',
    '  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / min(uRes.x, uRes.y);',
    '  float r = length(uv);',
    '  float ang = atan(uv.y, uv.x);',
    '  float t = uTime;',
    '  float lvl = clamp(uLevel, 0.0, 1.0);',

    // Radio base: late con el audio y con un pulso propio (respiracion)
    '  float breath = 0.012 * sin(t * 1.1) + 0.010 * sin(t * 0.37 + 1.7);',
    '  float R = 0.255 + breath + lvl * 0.085;',

    // Velocidad y turbulencia segun el estado
    '  float spin = 0.22;',
    '  float turb = 1.0;',
    '  if(uState > 0.5 && uState < 1.5){ spin = 0.55; turb = 1.5; }',      // listen
    '  else if(uState > 1.5 && uState < 2.5){ spin = 1.25; turb = 2.6; }', // think
    '  else if(uState > 2.5 && uState < 3.5){ spin = 0.75; turb = 2.0; }', // speak
    '  else if(uState > 3.5){ spin = 1.9; turb = 3.4; }',                  // alert

    // --- nucleo de plasma -----------------------------------------------
    '  vec3 q = vec3(uv * (3.4 + uAggr * 1.4), t * 0.28 * turb);',
    '  float n = fbm(q + fbm(q * 1.8 + t * 0.14) * (0.7 + lvl * 0.9));',
    // Un anillo de plasma en vez de un disco relleno: el centro queda oscuro y
    // el borde concentra la energia, que es lo que hace legible el estado.
    '  float coreMask = 1.0 - smoothstep(R - 0.14, R + 0.10, r);',
    '  float shell = coreMask * smoothstep(R * 0.52, R * 0.97, r);',
    '  float plasma = shell * (0.22 + n * (1.05 + lvl * 0.95));',
    '  float inner = 1.0 - smoothstep(0.0, R * 0.60, r) * (0.05 + lvl * 0.22) * (0.30 + n * 0.70);',

    // Ultron: el plasma se rompe en facetas angulares en vez de fluir
    '  float facet = mix(1.0, smoothstep(0.36, 0.66, fract(n * 3.0 + ang * 0.95 / 3.14159)), uAggr);',
    '  plasma *= mix(1.0, 0.50 + 1.0 * facet, uAggr);',

    // --- borde luminoso ---------------------------------------------------
    '  float rim = ring(r, R, 0.016 + lvl * 0.012) * (2.2 + lvl * 1.8);',

    // --- anillos orbitales -------------------------------------------------
    '  float rings = 0.0;',
    '  for(int i = 0; i < 3; i++){',
    '    float fi = float(i);',
    '    float rad = R + 0.11 + fi * 0.095;',
    '    float wob = 0.006 * sin(ang * (3.0 + fi * 2.0) + t * spin * (1.0 + fi * 0.6));',
    '    float seg = 0.55 + 0.45 * sin(ang * (5.0 + fi * 3.0) - t * spin * (1.4 + fi));',
    '    rings += ring(r, rad + wob, 0.0032) * seg * (0.60 - fi * 0.13);',
    '  }',

    // --- barrido radar ------------------------------------------------------
    '  float sweepA = 0.5 + 0.5 * cos(ang - t * spin * 0.85);',
    '  float sweep = pow(sweepA, 9.0) * (1.0 - smoothstep(R + 0.06, R + 0.42, r))',
    '              * smoothstep(R - 0.02, R + 0.06, r) * 0.45;',

    // --- halo volumetrico ---------------------------------------------------
    '  float halo = exp(-max(r - R, 0.0) * (14.0 - lvl * 4.0)) * (0.26 + lvl * 0.40);',

    // --- composicion --------------------------------------------------------
    '  vec3 col = vec3(0.0);',
    '  col += uA * plasma * 1.30;',
    '  col += uA * inner * 0.55;',
    '  col += mix(uA, uB, 0.55) * halo;',
    '  col += mix(uA, vec3(1.0), 0.16) * rim;',
    '  col += uB * rings * 1.35;',
    '  col += uA * sweep;',
    // Solo una chispa blanca donde el plasma ya es intenso. Un nucleo blanco
    // amplio lavaba el color del agente hasta dejarlo rosa.
    '  col += vec3(1.0) * pow(max(plasma - 0.80, 0.0), 2.2) * (0.55 + lvl * 1.1);',
    '  float L = dot(col, vec3(0.2126, 0.7152, 0.0722));',
    '  col *= (L > 0.0001) ? ((L / (1.0 + L)) / L) : 0.0;',
    '  col = clamp(col, 0.0, 1.0);',
    '  col = pow(max(col, 0.0), vec3(0.4545));',     // a sRGB
    // Grano DESPUES de gamma y proporcional a lo ya iluminado: si se sumara
    // antes, la correccion gamma convertiria 0.02 en un gris del 19% y
    // pintaria un rectangulo visible sobre el panel de cristal.
    '  float lum = max(col.r, max(col.g, col.b));',
    '  col += (hash(vec3(gl_FragCoord.xy, floor(t * 24.0))) - 0.5) * 0.030 * lum;',
    // El lienzo se compone sobre el cristal: el alfa sigue a la luminancia
    // para que el fondo del orbe sea transparente, no un rectangulo negro.
    '  float a = clamp(lum * 1.6, 0.0, 1.0) * (1.0 - smoothstep(R + 0.10, R + 0.62, r));',
    '  a = max(a, clamp(lum * 1.6, 0.0, 1.0) * step(r, R + 0.12));',
    '  gl_FragColor = vec4(col, a);',
    '}'
  ].join('\n');

  var STATES = { idle: 0, listen: 1, think: 2, speak: 3, alert: 4 };

  function hexToRgb(hex) {
    var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(String(hex).trim());
    if (!m) return [0.31, 0.85, 1.0];
    return [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255];
  }

  function compile(gl, type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn('[orb] shader:', gl.getShaderInfoLog(s));
      gl.deleteShader(s);
      return null;
    }
    return s;
  }

  function Orb(canvas, opts) {
    opts = opts || {};
    this.canvas = canvas;
    this.colorA = hexToRgb(opts.colorA || '#4FD8FF');
    this.colorB = hexToRgb(opts.colorB || '#F0B45E');
    this.aggression = typeof opts.aggression === 'number' ? opts.aggression : 0;
    this.state = 'idle';
    this.level = 0;        // objetivo
    this._level = 0;       // suavizado
    this.running = false;
    this._t0 = performance.now();
    this._raf = 0;
    this._dpr = Math.min(global.devicePixelRatio || 1, 2);
    this._reduced = !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
    this._initGL() || this._initCanvas2D();
    this._bindResize();
  }

  Orb.prototype._initGL = function () {
    var gl;
    try {
      var attrs = { alpha: true, premultipliedAlpha: false, antialias: false,
                    powerPreference: 'low-power', depth: false };
      gl = this.canvas.getContext('webgl', attrs) || this.canvas.getContext('experimental-webgl', attrs);
    } catch (e) { gl = null; }
    if (!gl) return false;

    // A partir de aqui el lienzo ya esta ligado a WebGL: aunque fallemos, no
    // podra dar un contexto 2D. _initCanvas2D lo tiene en cuenta.
    this._glTainted = true;

    var vs = null, fs = null, pr = null;
    function limpiar() {                 // no dejar shaders ni programa colgando
      if (pr) { try { gl.deleteProgram(pr); } catch (e) {} }
      if (vs) { try { gl.deleteShader(vs); } catch (e) {} }
      if (fs) { try { gl.deleteShader(fs); } catch (e) {} }
    }

    vs = compile(gl, gl.VERTEX_SHADER, VERT);
    fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) { limpiar(); return false; }

    pr = gl.createProgram();
    gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) {
      console.warn('[orb] link:', gl.getProgramInfoLog(pr));
      limpiar();
      return false;
    }
    gl.useProgram(pr);
    // Ya enlazado: los shaders viven dentro del programa y pueden liberarse.
    gl.deleteShader(vs); gl.deleteShader(fs);
    vs = fs = null;

    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(pr, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    this.gl = gl;
    this.u = {
      res:   gl.getUniformLocation(pr, 'uRes'),
      time:  gl.getUniformLocation(pr, 'uTime'),
      level: gl.getUniformLocation(pr, 'uLevel'),
      state: gl.getUniformLocation(pr, 'uState'),
      a:     gl.getUniformLocation(pr, 'uA'),
      b:     gl.getUniformLocation(pr, 'uB'),
      aggr:  gl.getUniformLocation(pr, 'uAggr')
    };
    this.mode = 'webgl';
    this._resize();
    return true;
  };

  /* Fallback: anillos + núcleo en Canvas2D. Menos espectacular, igual de legible.
     Un lienzo queda ligado a su tipo de contexto de por vida: si _initGL llego
     a pedir 'webgl' y luego fallo al compilar, este mismo lienzo devuelve null
     para '2d' y el fallback dibujaria sobre nada. En ese caso lo sustituimos
     por uno limpio, conservando id, clases y estilos. */
  Orb.prototype._initCanvas2D = function () {
    var ctx = null;
    if (!this._glTainted) {
      try { ctx = this.canvas.getContext('2d'); } catch (e) { ctx = null; }
    }
    if (!ctx) {
      var viejo = this.canvas;
      var nuevo = document.createElement('canvas');
      nuevo.id = viejo.id;
      nuevo.className = viejo.className;
      if (viejo.getAttribute('style')) nuevo.setAttribute('style', viejo.getAttribute('style'));
      if (viejo.hasAttribute('aria-hidden')) nuevo.setAttribute('aria-hidden', viejo.getAttribute('aria-hidden'));
      if (viejo.parentNode) {
        viejo.parentNode.replaceChild(nuevo, viejo);
        this.canvas = nuevo;
        try { ctx = nuevo.getContext('2d'); } catch (e) { ctx = null; }
      }
    }
    if (!ctx) {                     // sin 2D tampoco: mejor no arrancar el bucle
      console.warn('[orb] sin contexto 2D disponible; el orbe queda inactivo.');
      this.mode = 'none';
      return false;
    }
    this.ctx = ctx;
    this.mode = '2d';
    this._resize();
    return true;
  };

  Orb.prototype._bindResize = function () {
    var self = this;
    this._onResize = function () { self._resize(); };
    global.addEventListener('resize', this._onResize, { passive: true });
    if (global.ResizeObserver) {
      this._ro = new ResizeObserver(this._onResize);
      this._ro.observe(this.canvas);
    }
  };

  Orb.prototype._resize = function () {
    var c = this.canvas;
    var r = c.getBoundingClientRect();
    var w = Math.max(1, Math.round((r.width || c.clientWidth || 320) * this._dpr));
    var h = Math.max(1, Math.round((r.height || c.clientHeight || 320) * this._dpr));
    if (c.width === w && c.height === h) return;
    c.width = w; c.height = h;
    if (this.gl) this.gl.viewport(0, 0, w, h);
  };

  Orb.prototype.setState = function (s) {
    if (STATES[s] === undefined) return;
    this.state = s;
  };

  /** level: 0..1 — normalmente RMS del micro o de la voz sintetizada. */
  Orb.prototype.setLevel = function (v) {
    this.level = Math.max(0, Math.min(1, v || 0));
  };

  Orb.prototype.setColors = function (a, b) {
    if (a) this.colorA = hexToRgb(a);
    if (b) this.colorB = hexToRgb(b);
  };

  Orb.prototype.start = function () {
    if (this.running || this.mode === 'none') return;
    this.running = true;
    var self = this;
    (function loop() {
      if (!self.running) return;
      self._raf = requestAnimationFrame(loop);
      self._frame();
    })();
  };

  Orb.prototype.stop = function () {
    this.running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
  };

  Orb.prototype.destroy = function () {
    this.stop();
    global.removeEventListener('resize', this._onResize);
    if (this._ro) this._ro.disconnect();
  };

  Orb.prototype._frame = function () {
    // Ataque rápido, caída lenta: así el orbe "acompaña" la voz sin temblar.
    var target = this.level;
    var k = target > this._level ? 0.35 : 0.07;
    this._level += (target - this._level) * k;

    var t = (performance.now() - this._t0) / 1000;
    if (this._reduced) t *= 0.25;

    if (this.mode === 'webgl') this._drawGL(t);
    else if (this.mode === '2d') this._draw2D(t);
  };

  Orb.prototype._drawGL = function (t) {
    var gl = this.gl;
    gl.uniform2f(this.u.res, this.canvas.width, this.canvas.height);
    gl.uniform1f(this.u.time, t);
    gl.uniform1f(this.u.level, this._level);
    gl.uniform1f(this.u.state, STATES[this.state] || 0);
    gl.uniform3fv(this.u.a, this.colorA);
    gl.uniform3fv(this.u.b, this.colorB);
    gl.uniform1f(this.u.aggr, this.aggression);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };

  Orb.prototype._draw2D = function (t) {
    var ctx = this.ctx, W = this.canvas.width, H = this.canvas.height;
    var cx = W / 2, cy = H / 2, S = Math.min(W, H);
    var lvl = this._level;
    var R = S * (0.26 + lvl * 0.07);
    var ca = 'rgb(' + this.colorA.map(function (v) { return Math.round(v * 255); }).join(',') + ')';
    var cb = 'rgb(' + this.colorB.map(function (v) { return Math.round(v * 255); }).join(',') + ')';
    var spin = this.state === 'think' ? 1.25 : this.state === 'listen' ? 0.55
             : this.state === 'speak' ? 0.75 : this.state === 'alert' ? 1.9 : 0.22;

    ctx.clearRect(0, 0, W, H);   // transparente: compone sobre el cristal

    var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 2.3);
    g.addColorStop(0, ca); g.addColorStop(0.22, ca);
    g.addColorStop(0.5, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.globalAlpha = 0.42 + lvl * 0.3;
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * 2.3, 0, 6.2832); ctx.fill();
    ctx.globalAlpha = 1;

    ctx.strokeStyle = ca; ctx.lineWidth = Math.max(1.5, S * 0.004);
    ctx.shadowBlur = S * 0.05; ctx.shadowColor = ca;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, 6.2832); ctx.stroke();

    ctx.strokeStyle = cb; ctx.lineWidth = Math.max(1, S * 0.0022);
    ctx.shadowColor = cb;
    for (var i = 0; i < 3; i++) {
      var rad = R * (1.32 + i * 0.30);
      var off = t * spin * (1 + i * 0.6);
      ctx.beginPath();
      ctx.arc(cx, cy, rad, off, off + 1.5 + i * 0.4);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, rad, off + 3.14, off + 3.14 + 1.0);
      ctx.stroke();
    }
    ctx.shadowBlur = 0;

    var cg = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.62);
    cg.addColorStop(0, 'rgba(255,255,255,' + (0.85 + lvl * 0.15) + ')');
    cg.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(cx, cy, R * 0.62, 0, 6.2832); ctx.fill();
  };

  Orb.STATES = STATES;
  global.AetherOrb = Orb;
})(window);
