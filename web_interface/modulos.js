/* ═══════════════════════════════════════════════════════════════════════════
   MÓDULOS — todo lo que sabían hacer las dos interfaces antiguas.
   Compartido por /, /nexus y /aeon: una sola copia, tres pieles distintas.
   Espera encontrar ya definidos: API, esc, caja, barra, tabla, duracion,
   brindis y token, y los nodos mod-titulo / mod-contenido / rail.
   ═══════════════════════════════════════════════════════════════════════════ */
/* ═════════════════════════ MÓDULOS ════════════════════════════════════════
   Todo lo que sabían hacer las dos interfaces antiguas. Cada módulo declara su
   icono, su título y una función que devuelve HTML; las acciones se enganchan
   por delegación. Lo de ULTRON va por /api/nexus/u/<ruta>.                    */
const MODULOS = {
  sistema:{
    titulo:'Sistema', icono:'<path d="M4 5h16v11H4zM9 20h6M12 16v4"/><path d="M8 9h8M8 12h5"/>',
    async cargar(){
      const [s, p] = await Promise.all([
        API.get('/stats').catch(()=>({})),
        API.get('/api/system/processes?limit=12').catch(()=>({processes:[]}))
      ]);
      // Las claves son las que devuelve /stats de verdad: se comprobó contra
      // el servidor, no se adivinaron.
      const b = s.battery || s.bateria;
      const bat = b ? `${b.percent}%${b.plugged ? ' (cargando)' : ''}` : '—';
      const usado = (s.disco_total_gb && s.disco_libre_gb)
        ? Math.round((1 - s.disco_libre_gb / s.disco_total_gb) * 100) : null;
      // El proceso inactivo del sistema siempre encabeza la lista con un uso
      // absurdo (suma de todos los núcleos) y no aporta nada: fuera.
      const proc = (p.processes || [])
        .filter(x => !/idle process/i.test(x.name || x.nombre || ''))
        .map(x => [
        esc(x.name || x.nombre || '?'),
        Math.round(x.cpu ?? x.cpu_percent ?? 0) + '%',
        (x.mem_mb != null ? Math.round(x.mem_mb) + ' MB'
                          : ((x.mem_pct ?? x.mem ?? 0) + '%')),
        `<button class="mbtn peligro" data-accion="matar" data-valor="${esc(x.name||x.nombre||'')}"
           data-pid="${x.pid ?? ''}">matar</button>`
      ]);
      return `<div class="mrejilla">
        ${caja('Procesador', `<div class="grande">${s.cpu ?? '—'}%</div>${barra(s.cpu||0)}
          <div class="pista">${Array.isArray(s.cpu_cores) ? s.cpu_cores.length + ' núcleos'
            : (s.cpu_cores ? s.cpu_cores + ' núcleos' : '')}
            ${s.temp ? ' · ' + s.temp + ' °C' : ''}</div>`)}
        ${caja('Memoria', `<div class="grande">${s.ram_pct ?? '—'}%</div>${barra(s.ram_pct||0)}
          <div class="pista">${s.ram_used_gb ?? '?'} de ${s.ram_total_gb ?? '?'} GB</div>`)}
        ${caja('Disco', `<div class="grande">${usado != null ? usado + '%' : '—'}</div>
          ${barra(usado||0)}<div class="pista">${s.disco_libre_gb ?? '?'} GB libres de
          ${s.disco_total_gb ?? '?'}</div>`)}
        ${caja('Batería', `<div class="grande">${bat}</div>
          <div class="pista">encendido ${duracion(s.uptime)}
            · red ${esc(s.net_mb ?? '—')} MB</div>`)}
      </div>
      <div class="mfila" style="margin-top:14px">
        <button class="mbtn" data-accion="limpiar-ram">Liberar memoria</button>
        <button class="mbtn" data-accion="radar">Radar de red</button>
        <button class="mbtn peligro" data-accion="lockdown">Bloqueo total</button>
      </div>
      <div id="mod-extra"></div>
      <h4 style="margin:16px 0 8px;color:var(--p1);font-size:10.5px;letter-spacing:.18em">PROCESOS</h4>
      ${proc.length ? tabla(['Proceso','CPU','Memoria',''], proc)
                    : '<p class="pista">Sin datos de procesos (requiere pc_tactical).</p>'}`;
    }
  },

  camara:{
    titulo:'Cámara', icono:'<path d="M3 7h4l2-2h6l2 2h4v12H3z"/><circle cx="12" cy="13" r="3.4"/>',
    async cargar(){
      return `<img class="espejo" src="${API.medios('/camera_feed')}" alt="cámara">
        <p class="pista">Emisión en vivo de la cámara del equipo. Si no aparece nada,
        es que no hay cámara disponible o está en uso por otra aplicación.</p>`;
    }
  },

  pantalla:{
    titulo:'Pantalla y control', icono:'<rect x="3" y="4" width="18" height="13" rx="1.6"/><path d="M9 20h6"/>',
    async cargar(){
      return `<img class="espejo" id="espejo-pantalla" src="${API.medios('/screen_feed')}" alt="pantalla">
        <p class="pista">Arrastre sobre la imagen para mover el ratón, toque para hacer clic,
        y use la rueda para desplazarse. Lo que escriba abajo se teclea en el equipo.</p>
        <div class="mfila" style="margin-top:10px">
          <input class="mcampo" id="mod-teclear" placeholder="Texto para escribir en el equipo…" style="flex:1">
          <button class="mbtn" data-accion="teclear">Escribir</button>
          <button class="mbtn" data-accion="clic-derecho">Clic derecho</button>
        </div>`;
    }
  },

  archivos:{
    titulo:'Archivos', icono:'<path d="M4 6h6l2 2h8v11H4z"/><path d="M12 12v5M9.5 14.5L12 12l2.5 2.5"/>',
    async cargar(){
      const g = await API.get('/generated_files').catch(()=>({files:[]}));
      const filas = (g.files||[]).map(f => [
        esc(f.name), f.type || '', Math.round((f.size||0)/1024) + ' KB',
        `<a class="mbtn" href="${API.medios('/download/' + encodeURI(f.path))}" download>bajar</a>`
      ]);
      return `<div class="mfila">
          <input type="file" id="mod-subir" class="mcampo" style="flex:1">
          <button class="mbtn" data-accion="subir">Subir al equipo</button>
        </div>
        <p class="pista">Lo que suba aparece en Descargas/JARVIS. Abajo, lo que JARVIS ha generado.</p>
        ${filas.length ? tabla(['Archivo','Tipo','Tamaño',''], filas)
                       : '<p class="pista">Todavía no hay archivos generados.</p>'}`;
    }
  },

  generador:{
    titulo:'Generar', icono:'<path d="M12 3v18M3 12h18M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    async cargar(){
      return `<div class="mfila">
          <input class="mcampo" id="mod-prompt" style="flex:1"
                 placeholder="Ej.: una imagen de un reactor arc · un Excel de gastos · un PDF con el informe">
          <button class="mbtn" data-accion="generar">Generar</button>
        </div>
        <p class="pista">Imágenes, Word, Excel, PowerPoint, PDF, diagramas y código:
        el generador elige el formato según lo que pida.</p>
        <div id="mod-salida"></div>`;
    }
  },

  agenda:{
    titulo:'Agenda', icono:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    async cargar(){
      const hoy = await API.get('/api/calendar/today').catch(()=>({events:[]}));
      const ev = hoy.events || hoy.eventos || [];
      const filas = ev.map(e => [
        esc(e.start || e.inicio || e.hora || ''), esc(e.summary || e.titulo || e.title || ''),
        `<button class="mbtn peligro" data-accion="borrar-evento" data-valor="${esc(e.id||'')}">borrar</button>`
      ]);
      return `<div class="mfila">
          <input class="mcampo" id="mod-evento" style="flex:1"
                 placeholder="Ej.: reunión con Marta mañana a las 17:00">
          <button class="mbtn" data-accion="crear-evento">Agendar</button>
        </div>
        ${filas.length ? tabla(['Hora','Evento',''], filas)
                       : '<p class="pista">Nada en la agenda de hoy.</p>'}`;
    }
  },

  seguridad:{
    titulo:'Guardián', icono:'<path d="M12 3l8 3v6c0 4.4-3.2 7.9-8 9-4.8-1.1-8-4.6-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    async cargar(){
      const [u, radar] = await Promise.all([
        API.u('/status').catch(()=>({})),
        API.get('/api/system/network_radar').catch(()=>({}))
      ]);
      const disp = (radar.devices || radar.dispositivos || []).map(d =>
        [esc(d.ip || d.direccion || ''), esc(d.mac || ''), esc(d.name || d.nombre || '—'),
         `<button class="mbtn peligro" data-accion="bloquear-ip" data-valor="${esc(d.ip||'')}">bloquear</button>`]);
      return `<div class="mrejilla">
          ${caja('ULTRON', `<div class="pista">modo <b style="color:var(--p1)">${esc(u.modo || u.mode || '—')}</b><br>
            núcleo ${u.core_loaded === false ? 'no cargado' : 'cargado'}</div>
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn" data-accion="modo-ofensiva">OFENSIVA</button>
              <button class="mbtn" data-accion="modo-normal">NORMAL</button>
            </div>`)}
          ${caja('Guardián facial', `<div class="pista">Pregunte por voz «estado del guardián»
            o actívelo desde aquí.</div>
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn" data-accion="guardian-on">Activar</button>
              <button class="mbtn" data-accion="guardian-off">Desactivar</button>
            </div>`)}
          ${caja('Emergencia', `<div class="mfila">
              <button class="mbtn peligro" data-accion="lockdown">Bloqueo total</button>
              <button class="mbtn" data-accion="restaurar-red">Restaurar red</button>
            </div>`)}
        </div>
        <h4 style="margin:16px 0 8px;color:var(--p1);font-size:10.5px;letter-spacing:.18em">RADAR DE RED</h4>
        ${disp.length ? tabla(['IP','MAC','Nombre',''], disp)
                      : '<p class="pista">Sin dispositivos detectados todavía. Pulse actualizar.</p>'}`;
    }
  },

  voz:{
    titulo:'Voz', icono:'<path d="M4 12a8 8 0 0 1 16 0"/><rect x="4" y="12" width="4" height="7" rx="1.5"/><rect x="16" y="12" width="4" height="7" rx="1.5"/>',
    async cargar(){
      const v = await API.get('/voz_windows').catch(()=>({}));
      const P = await API.get('/api/panel').catch(()=>({}));
      return `<div class="mfila">
          <input class="mcampo" id="mod-decir" style="flex:1" placeholder="Texto para que lo diga en voz alta…">
          <button class="mbtn" data-accion="decir">Decir</button>
          <button class="mbtn peligro" data-accion="callar">Callar</button>
        </div>
        <div class="mrejilla" style="margin-top:12px">
          ${caja('Voz de Windows', `<div class="pista">Estado: ${v.silenciada ? 'silenciada' : 'activa'}</div>
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn" data-accion="voz-on">Activar</button>
              <button class="mbtn" data-accion="voz-off">Silenciar</button>
            </div>`)}
          ${caja('Rituales', `<div class="mfila">
              <button class="mbtn" data-accion="saludo">Saludo</button>
              <button class="mbtn" data-accion="despedida">Despedida</button>
              <button class="mbtn" data-accion="probar-ia">Probar cerebro</button>
            </div>`)}
          ${caja('Voz neuronal local', (() => {
            const vp = (P.voz_propia || {});
            const puestas = vp.voces_instaladas || [];
            const catalogo = Object.entries(vp.catalogo || {});
            return `<div class="pista">Instaladas: ${puestas.length ? puestas.map(esc).join(', ') : 'ninguna'}
                · JARVIS: <b>${esc(vp.voz_jarvis || '—')}</b> · ULTRON: <b>${esc(vp.voz_ultron || '—')}</b></div>
              <div class="mfila" style="margin-top:8px">
                <select class="mcampo" id="mod-voz" style="flex:1">${
                  catalogo.map(([k,d]) => `<option value="${esc(k)}">${esc(k)} — ${esc(d)}</option>`).join('')
                }</select>
              </div>
              <div class="mfila" style="margin-top:8px">
                <button class="mbtn" data-accion="voz-instalar">Descargar</button>
                <button class="mbtn" data-accion="voz-jarvis">Dársela a JARVIS</button>
                <button class="mbtn" data-accion="voz-ultron">Dársela a ULTRON</button>
              </div>
              <p class="pista">Son unos 60 MB por voz, se quedan en el equipo y no cuestan nada.</p>`;
          })())}
        </div>
        <div id="mod-salida"></div>`;
    }
  },

  movil:{
    titulo:'Teléfono', icono:'<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M10.5 5.5h3"/><circle cx="12" cy="18" r="1"/>',
    async cargar(){
      const P = await API.get('/api/panel').catch(()=>({}));
      const m = P.movil || {}, puente = P.puente_movil || {};
      if (!m.conectado){
        return `${caja('Sin teléfono', `<p class="pista">${esc(m.motivo || 'no hay ningún teléfono conectado')}.</p>
          <ol class="pista" style="margin:8px 0 0 16px;line-height:1.7">
            <li>Ajustes › Información del teléfono › siete toques en «Número de compilación».</li>
            <li>Opciones de desarrollador › Depuración USB.</li>
            <li>Conecte el cable y acepte la huella de este PC.</li>
          </ol>
          <div class="mfila" style="margin-top:10px">
            <input class="mcampo" id="mod-movil-ip" style="flex:1" placeholder="IP del teléfono (opcional, para WiFi)">
            <button class="mbtn" data-accion="movil-wifi">Emparejar por WiFi</button>
          </div>`)}
          <div id="mod-salida"></div>`;
      }
      const b = m.bateria || {};
      return `<div class="mrejilla">
          ${caja('Estado', `<div class="pista">${esc(m.dispositivo || '')}</div>
            ${barra(b.nivel || 0)}
            <div class="pista">Batería ${b.nivel ?? '—'}%${b.cargando ? ' · cargando' : ''}${
              b.temperatura ? ' · ' + b.temperatura + '°' : ''} · ${m.notificaciones ?? 0} notificaciones</div>
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn" data-accion="movil-sonar">Hacerlo sonar</button>
              <button class="mbtn" data-accion="movil-notis">Ver notificaciones</button>
            </div>`)}
          ${caja('Avisos que me pidió', `<div class="pista">${
              (puente.reglas || []).length
                ? (puente.reglas || []).map(r => esc(r.filtro)).join(', ')
                : 'ninguno todavía'}</div>
            <div class="mfila" style="margin-top:8px">
              <input class="mcampo" id="mod-movil-regla" style="flex:1" placeholder="avísame cuando me escriba…">
              <button class="mbtn" data-accion="movil-regla">Añadir</button>
            </div>
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn" data-accion="movil-vigilar">${puente.activo ? 'Vigilando' : 'Vigilar'}</button>
              <button class="mbtn peligro" data-accion="movil-parar">Parar</button>
            </div>`)}
          ${caja('Abrir una app', `<div class="mfila">
              <input class="mcampo" id="mod-movil-app" style="flex:1" placeholder="spotify, whatsapp, maps…">
              <button class="mbtn" data-accion="movil-app">Abrir</button>
            </div>`)}
          ${caja('WhatsApp', `<div class="mfila">
              <input class="mcampo" id="mod-wa-quien" placeholder="nombre o +34…">
            </div>
            <div class="mfila" style="margin-top:8px">
              <input class="mcampo" id="mod-wa-texto" style="flex:1" placeholder="mensaje">
              <button class="mbtn" data-accion="wa-preparar">Preparar</button>
            </div>
            <p class="pista">Se escribe en el teléfono y se enseña antes de enviar. Nada sale solo.</p>`)}
        </div>
        <div id="mod-salida"></div>`;
    }
  },

  ojos:{
    titulo:'Ojos', icono:'<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.6"/>',
    async cargar(){
      const P = await API.get('/api/panel').catch(()=>({}));
      const o = P.observador || {}, v = P.vision || {};
      return `<div class="mrejilla">
          ${caja('Vigilancia de pantalla', `<div class="pista">
              ${o.activo ? 'Pendiente de su pantalla' : 'No está mirando'} ·
              ${o.miradas ?? 0} revisiones · ${o.ofrecimientos ?? 0} avisos</div>
            ${o.ventana_actual ? `<div class="pista">Ahora: ${esc(o.ventana_actual)}</div>` : ''}
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn" data-accion="ojos-on">Vigilar</button>
              <button class="mbtn peligro" data-accion="ojos-off">Dejar de mirar</button>
              <button class="mbtn" data-accion="ojos-mirar">Mirar ahora</button>
            </div>
            <p class="pista">Solo gasta una captura cuando lleva cuatro minutos con la misma
              ventana. En perfil de juego o modo privado, ni mira.</p>`)}
          ${caja('Modelo de visión', `<div class="pista">${
              v.modelo ? esc(v.modelo) : 'sin modelo instalado'}${
              v.disponible === false && v.motivo ? ' · ' + esc(v.motivo) : ''}</div>
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn" data-accion="ver-pantalla">Describir la pantalla</button>
            </div>`)}
        </div>
        <div id="mod-salida"></div>`;
    }
  },

  aprender:{
    titulo:'Aprendizaje', icono:'<path d="M12 3 3 7.5 12 12l9-4.5L12 3z"/><path d="M6 10v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/>',
    async cargar(){
      const P = await API.get('/api/panel').catch(()=>({}));
      const r = (P.rutinas || {}).rutinas || [], a = P.afinado || {}, m = P.mision || {};
      const equipo = (a.equipo || {}).recomendacion || '';
      return `<div class="mrejilla">
          ${caja('Rutinas que sé repetir', r.length
            ? tabla(['rutina','pasos',''], r.map(x => [esc(x.nombre), x.pasos,
                `<button class="mbtn" data-accion="repetir-rutina" data-valor="${esc(x.nombre)}">repetir</button>`]))
            : `<p class="pista">Ninguna todavía. Dígame «aprende esto», haga la tarea y
                 diga «ya está».</p>`)}
          ${caja('Misión en curso', m.en_curso
            ? `<div class="pista">${esc(m.objetivo || '')}</div>
               ${barra(m.hechos || 0, Math.max(1, m.pasos || 1))}
               <div class="pista">${m.hechos ?? 0} de ${m.pasos ?? 0} pasos</div>
               <div class="mfila" style="margin-top:8px">
                 <button class="mbtn peligro" data-accion="mision-parar">Detener</button>
               </div>`
            : `<div class="mfila">
                 <input class="mcampo" id="mod-mision" style="flex:1" placeholder="Encárgate de…">
                 <button class="mbtn" data-accion="mision-lanzar">Lanzar</button>
               </div>
               <p class="pista">Lo parte en pasos, los ejecuta uno a uno y replanifica lo que falle.</p>`)}
          ${caja('Analista', `<div class="mfila">
              <input class="mcampo" id="mod-analisis" style="flex:1" placeholder="Analiza mis gastos del mes…">
              <button class="mbtn" data-accion="analizar">Analizar</button>
            </div>
            <p class="pista">Escribe un programa, lo ejecuta en su propia carpeta y corrige
              los fallos hasta que sale.</p>`)}
          ${caja('Afinado del modelo', `<div class="pista">
              ${a.conversaciones ?? 0} conversaciones · ${a.bien_valoradas ?? 0} bien y
              ${a.mal_valoradas ?? 0} mal valoradas${a.suficiente ? '' : ' · aún son pocas'}</div>
            ${barra(a.conversaciones || 0, a.minimo || 200)}
            <div class="pista">${esc(equipo)}</div>
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn" data-accion="afinar-exportar">Preparar dataset y guion</button>
            </div>`)}
        </div>
        <div id="mod-salida"></div>`;
    }
  },

  agentes:{
    titulo:'Especialistas', icono:'<circle cx="9" cy="8" r="3"/><circle cx="17" cy="10" r="2.4"/><path d="M4 19c0-3 2.5-5 5-5s5 2 5 5M14.5 19c.2-2 1.3-3.4 2.5-3.4 1.3 0 2.4 1.4 2.6 3.4"/>',
    async cargar(){
      const [a, par] = await Promise.all([
        API.get('/api/agentes').catch(()=>({divisiones:[],total:0})),
        API.get('/api/agent/peer_status').catch(()=>({}))
      ]);
      const divs = (a.divisiones || []).map(d =>
        caja(esc(d.nombre || d.name || 'división'),
             `<div class="pista">${(d.agentes || d.agents || []).slice(0,8).map(esc).join(', ') || '—'}</div>`));
      return `<div class="mfila">
          <input class="mcampo" id="mod-agente" style="flex:1" placeholder="Activar especialista: ej. Frontend Developer">
          <button class="mbtn" data-accion="activar-agente">Activar</button>
          <button class="mbtn" data-accion="desactivar-agente">Volver a la identidad base</button>
        </div>
        <div class="mfila">
          <input class="mcampo" id="mod-delegar" style="flex:1" placeholder="Delegar orden al otro agente…">
          <button class="mbtn" data-accion="delegar">Delegar</button>
        </div>
        <p class="pista">Enlace entre agentes: ${par.online ? 'ONLINE' : 'sin contacto'} ·
          catálogo de ${a.total ?? 0} especialistas.</p>
        <div class="mrejilla">${divs.join('') || '<p class="pista">Catálogo no disponible.</p>'}</div>`;
    }
  },

  datos:{
    titulo:'Datos y web', icono:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 3 2.6 15 0 18M12 3c-2.6 3-2.6 15 0 18"/>',
    async cargar(){
      return `<div class="mrejilla">
          ${caja('Bolsa', `<div class="mfila"><input class="mcampo" id="mod-ticker" placeholder="AAPL">
            <button class="mbtn" data-accion="bolsa">Consultar</button></div>`)}
          ${caja('Noticias', `<div class="mfila"><input class="mcampo" id="mod-noticias" placeholder="tema">
            <button class="mbtn" data-accion="noticias">Buscar</button></div>`)}
          ${caja('Leer una web', `<div class="mfila"><input class="mcampo" id="mod-url" placeholder="https://…">
            <button class="mbtn" data-accion="scrape">Extraer</button></div>`)}
          ${caja('YouTube', `<div class="mfila"><input class="mcampo" id="mod-yt" placeholder="enlace o búsqueda">
            <button class="mbtn" data-accion="yt">Descargar</button></div>`)}
        </div>
        <div id="mod-salida"></div>`;
    }
  },

  historial:{
    titulo:'Historial', icono:'<path d="M4 5h16M4 12h16M4 19h10"/>',
    async cargar(){
      const [j, u] = await Promise.all([
        API.get('/api/history').catch(()=>({messages:[]})),
        API.u('/history').catch(()=>({messages:[]}))
      ]);
      const pinta = (lista, quien) => (lista||[]).slice(-14).map(m =>
        `<div style="padding:6px 0;border-bottom:1px dashed rgba(255,255,255,.06)">
           <b style="color:var(--p1);font-size:10.5px;letter-spacing:.14em">
             ${quien} · ${esc(m.role || m.rol || '')}</b><br>${esc(m.text || m.content || '')}</div>`).join('');
      return `<div class="mrejilla" style="grid-template-columns:1fr 1fr">
          ${caja('JARVIS', pinta(j.messages || j.mensajes, 'J') || '<span class="pista">sin historial</span>')}
          ${caja('ULTRON', pinta(u.messages || u.mensajes || u.history, 'U') || '<span class="pista">sin historial</span>')}
        </div>
        <div class="mfila" style="margin-top:12px">
          <button class="mbtn peligro" data-accion="purgar-ultron">Purgar memoria de ULTRON</button>
        </div>`;
    }
  },

  enlace:{
    titulo:'Emparejar', icono:'<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><path d="M14 14h3v3h-3zM19 19h2v2h-2z"/>',
    async cargar(){
      const [info, est] = await Promise.all([
        API.get('/pair_info').catch(()=>({})),
        API.get('/pair_status').catch(()=>({emparejados:[]}))
      ]);
      const filas = (est.emparejados||[]).map(e =>
        [esc(e.ip), e.dias_restantes == null ? 'sin caducidad' : e.dias_restantes + ' días']);
      const motivos = info.diagnostico || [];
      const otras = (info.urls || []).slice(1);
      return `<div class="mrejilla">
          ${caja('QR del móvil', `<img src="${API.medios('/qr')}&v=${Date.now()}"
              style="width:100%;max-width:230px;border-radius:10px;background:#fff">
            <div class="pista">PIN ${esc(info.pin || '—')} · ya va dentro del QR</div>
            <div class="pista">${esc(info.url || '')}</div>`)}
          ${caja('Aparatos emparejados', filas.length ? tabla(['IP','Caduca en'], filas)
                 : '<span class="pista">Ninguno todavía. Escanee el QR con el teléfono.</span>')}
          ${caja('Desde fuera de casa', (() => {
            const r = info.remoto || {};
            if (!r.instalado)
              return `<p class="pista">Este equipo solo es alcanzable desde su propia red.
                Con <b>Tailscale</b> en el PC y en el teléfono (misma cuenta, gratis para uso
                personal) podría entrar desde cualquier sitio sin abrir nada en el router.</p>`;
            const red = r.red || {}, pub = r.publicado || {};
            const segura = (r.urls || []).find(u => u.segura);
            const aparatos = (red.aparatos || []).map(a =>
              `${esc(a.nombre)}${a.conectado ? '' : ' (apagado)'}`).join(', ') || 'ninguno más';
            return `<div class="pista">Nombre en la red privada: <b>${esc(red.nombre || '—')}</b></div>
              ${segura
                ? `<div class="pista">Entre desde cualquier red por
                     <b>${esc(segura.url)}/mobile</b></div>
                   <img src="${API.medios('/qr')}&url=${encodeURIComponent(segura.url + '/mobile')}"
                     style="width:150px;border-radius:10px;background:#fff;margin-top:8px">`
                : `<div class="pista">Todavía sin publicar: solo se llega por IP y sin HTTPS,
                     así que el micrófono del teléfono no funcionaría.</div>`}
              <div class="pista" style="margin-top:8px">Sus aparatos: ${aparatos}</div>
              ${pub.funnel ? '<div class="pista" style="color:#ffd479">Además está abierto a Internet.</div>' : ''}
              <div class="mfila" style="margin-top:8px">
                <button class="mbtn" data-accion="remoto-on">${segura ? 'Volver a publicar' : 'Activar acceso remoto'}</button>
                <button class="mbtn peligro" data-accion="remoto-off">Quitarlo</button>
              </div>`;
          })())}
          ${caja('Si el teléfono no carga', (motivos.length
              ? motivos.map(m => `<p class="pista"><b>${esc(m.que)}</b><br>${esc(m.hacer)}</p>`).join('')
              : '<p class="pista">Nada raro por aquí. Compruebe que el teléfono está en el mismo WiFi.</p>')
            + ((info.firewall && info.firewall.hace_falta)
              ? '<div class="mfila" style="margin-top:8px"><button class="mbtn" data-accion="abrir-puerto">Abrir el puerto</button></div>'
              : ''))}
          ${otras.length ? caja('Otras direcciones', otras.map(u =>
              `<div class="pista" style="margin-bottom:8px">${esc(u.ip)} · ${esc(u.via)}<br>
               <img src="${API.medios('/qr')}&url=${encodeURIComponent(u.url)}"
                 style="width:120px;border-radius:8px;background:#fff;margin-top:4px"></div>`).join('')) : ''}
          ${caja('Seguridad', `<div class="pista">El PIN caduca a los ${est.pin_dias ?? '?'} días
            y los emparejamientos a los ${est.pair_dias ?? '?'}.</div>
            <div class="mfila" style="margin-top:8px">
              <button class="mbtn peligro" data-accion="rotar-pin">Cambiar el PIN ahora</button>
            </div>`)}
        </div>`;
    }
  },

  modelado3d:{
    titulo:'Modelado 3D', icono:'<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M12 2v20M3 7l9 5 9-5"/>',
    async cargar(){
      const e = await API.get('/api/modelado3d/estado').catch(()=>({}));
      const bk = (e.backends||[]);
      return `<div class="mrejilla">
        ${caja('Motor', `<div class="pista">Blender: <b>${e.blender ? 'sí' : 'no'}</b></div>
          <div class="pista" style="word-break:break-all">${esc(e.blender_exe||'—')}</div>
          <div class="pista">Reconstructores locales: <b>${bk.length ? esc(bk.join(', ')) : 'ninguno (uso la «imaginación» del cerebro)'}</b></div>`)}
        ${caja('Notas', `<div class="pista">${esc(e.resumen||'')}</div>
          <div class="pista">Configura rutas en Prefs/modelado3d.json (ver setup_modelado3d.md).</div>`)}
      </div>
      <h4 style="margin:16px 0 8px;color:var(--p1);font-size:10.5px;letter-spacing:.18em">MODELAR</h4>
      <div class="mfila">
        <input id="m3d-entrada" class="mcampo" style="flex:1"
          placeholder="descripción, o ruta a foto / vídeo / .blend / .obj / .fbx …">
      </div>
      <div class="mfila" style="margin-top:8px">
        <label class="pista"><input type="checkbox" id="m3d-tpose"> T-pose (personajes)</label>
      </div>
      <div class="mfila" style="margin-top:8px">
        <button class="mbtn" data-accion="m3d-modelar">Modelar</button>
        <button class="mbtn" data-accion="m3d-holograma">Holograma del último</button>
        <button class="mbtn" data-accion="m3d-abrir">Abrir carpeta de modelos</button>
      </div>
      <div id="mod-salida"></div>
      <p class="pista" style="margin-top:10px">Tarda 1–3 min. Al acabar te abre el visor
        holográfico. Para pirámide de acrílico: «holograma pirámide».</p>`;
    }
  },

  ciencias:{
    titulo:'Ciencias', icono:'<path d="M9 3h6M10 3v6l-5 9a3 3 0 0 0 3 4h8a3 3 0 0 0 3-4l-5-9V3"/><path d="M7.5 15h9"/>',
    async cargar(){
      const e = await API.get('/api/ciencias/estado').catch(()=>({}));
      const ent = e.entrenamiento || {}, u = e.ultimo || {};
      const falta = ['sympy','numpy','matplotlib','scipy','pint'].filter(k => !e[k]);
      return `<div class="mrejilla">
        ${caja('Motor', `<div class="pista">sympy <b>${e.sympy?'sí':'no'}</b> ·
          numpy <b>${e.numpy?'sí':'no'}</b> · matplotlib <b>${e.matplotlib?'sí':'no'}</b></div>
          <div class="pista">scipy ${e.scipy?'sí':'no'} · pint ${e.pint?'sí':'no'}</div>
          ${falta.length ? `<div class="pista" style="color:#ff8080">falta: ${esc(falta.join(', '))}</div>` : ''}`)}
        ${caja('Saber', `<div class="grande">${e.formulas_fisica ?? '—'}</div>
          <div class="pista">leyes de física · ${e.elementos ?? 0} elementos ·
            ${e.constantes ?? 0} constantes</div>`)}
        ${caja('Entrenamiento', `<div class="grande">${ent.ultima_nota != null ? Number(ent.ultima_nota).toFixed(1) : '—'}</div>
          <div class="pista">${ent.casos_banco ?? 0} problemas de examen ·
            ${ent.frases_aprendidas ?? 0} frases aprendidas</div>
          <div class="pista">${esc(ent.ultimo_informe || 'sin entrenar todavía')}</div>`)}
      </div>
      <h4 style="margin:16px 0 8px;color:var(--p1);font-size:10.5px;letter-spacing:.18em">RESOLVER Y GRAFICAR</h4>
      <div class="mfila">
        <input id="cie-q" class="mcampo" style="flex:1"
          placeholder="dicta el problema: «deriva x**3 por seno de x y grafícalo en 3D»">
      </div>
      <div class="mfila" style="margin-top:8px">
        <button class="mbtn" data-accion="cie-resolver">Resolver</button>
        <button class="mbtn" data-accion="cie-graficar-2d">Graficar 2D</button>
        <button class="mbtn" data-accion="cie-graficar-3d">Superficie 3D</button>
        <button class="mbtn" data-accion="cie-tabla">Tabla periódica</button>
        <button class="mbtn" data-accion="cie-entrenar">Entrenar</button>
        <button class="mbtn" data-accion="cie-abrir">Abrir carpeta</button>
      </div>
      <div id="mod-salida"></div>
      <p class="pista" style="margin-top:10px">El visor 3D se abre en el navegador y
        se gira con el ratón. Las mallas .obj/.stl valen para Blender y para imprimir.
        ${u.carpeta ? 'Último: ' + esc(u.accion || '') + ' → ' + esc(u.carpeta) : ''}</p>`;
    }
  },

  cerebro:{
    titulo:'Cerebro', icono:'<path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-1 5.8A3 3 0 0 0 8 17a3 3 0 0 0 4 2 3 3 0 0 0 4-2 3 3 0 0 0 3-5.2A3 3 0 0 0 18 6a3 3 0 0 0-3-3 3 3 0 0 0-3 1.5A3 3 0 0 0 9 3z"/>',
    async cargar(){
      const e = await API.get('/api/cerebro/estado').catch(()=>({}));
      const mem = e.memoria||{}, pre = e.presupuesto||{}, sal = e.salud_proveedores||{},
            rt = e.router||{}, am = e.automejora||{};
      const filasSalud = Object.entries(sal).map(([k,v]) =>
        [esc(k), (v.fallos||0)+' fallos', (v.cuarentena_s||0)+' s']);
      return `<div class="mrejilla">
        ${caja('Memoria unificada', `<div class="grande">${mem.hechos ?? '—'}</div>
          <div class="pista">${mem.entidades ?? 0} entidades · FTS ${mem.fts ? 'sí' : 'no'}</div>`)}
        ${caja('Gasto del día', `<div class="grande">${pre.usd != null ? '$'+Number(pre.usd).toFixed(3) : '—'}</div>
          <div class="pista">tope $${pre.tope_usd ?? '?'} · ${pre.tokens ?? 0} tokens
            ${pre.excedido ? '· <b style="color:#ff8080">TOPE</b>' : ''}</div>`)}
        ${caja('Router por modelo', `<div class="grande">${rt.activo ? 'ON' : 'off'}</div>
          <div class="pista">${rt.en_cache ?? 0} frases en caché</div>`)}
        ${caja('Auto-mejora', `<div class="grande">${am.activo ? 'ON' : 'off'}</div>
          <div class="pista">modo agente: ${esc(e.agente_modo||'normal')}</div>`)}
      </div>
      <h4 style="margin:16px 0 8px;color:var(--p1);font-size:10.5px;letter-spacing:.18em">PROVEEDORES</h4>
      ${filasSalud.length ? tabla(['Proveedor','Fallos','Cuarentena'], filasSalud)
                          : '<p class="pista">Todos sanos.</p>'}
      <div class="mfila" style="margin-top:12px">
        <input id="cbr-q" class="mcampo" style="flex:1" placeholder="buscar en la memoria (o «qué hice el martes»)">
        <button class="mbtn" data-accion="cbr-buscar">Buscar</button>
      </div>
      <div id="mod-salida"></div>`;
    }
  },

  correo:{
    titulo:'Correo', icono:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    async cargar(){
      const r = await API.get('/api/correo/inbox?limite=12').catch(e => ({ok:false, error:e.message}));
      const ms = r.mensajes || [];
      const filas = ms.map(m => [
        (m.vip ? '<b style="color:var(--p1)">★</b> ' : '') + esc(m.from || '?'),
        esc(m.subject || '(sin asunto)'),
        `<button class="mbtn" data-accion="correo-leer" data-valor="${esc(m.id || '')}">leer</button>`]);
      return `<div class="mfila">
          <button class="mbtn" data-accion="correo-resumir">Resúmeme lo nuevo</button>
        </div>
        ${r.error ? `<p class="pista" style="color:#ff8080">${esc(r.error)}
          · para dar acceso: <b>python autorizar_google.py</b></p>` : ''}
        ${filas.length ? tabla(['De','Asunto',''], filas)
                       : '<p class="pista">Bandeja vacía o sin acceso a Gmail.</p>'}
        <div id="mod-salida"></div>
        <h4 style="margin:16px 0 8px;color:var(--p1);font-size:10.5px;letter-spacing:.18em">ESCRIBIR</h4>
        <div class="mfila">
          <input id="correo-para" class="mcampo" style="flex:1" placeholder="para (correo)">
          <input id="correo-asunto" class="mcampo" style="flex:1" placeholder="asunto">
        </div>
        <div class="mfila" style="margin-top:8px">
          <textarea id="correo-cuerpo" class="mcampo" rows="4" style="flex:1" placeholder="mensaje"></textarea>
        </div>
        <div class="mfila" style="margin-top:8px">
          <button class="mbtn" data-accion="correo-enviar">Enviar</button>
        </div>`;
    }
  },

  demos:{
    titulo:'Demos web', icono:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M6.5 6.5h.01M9.5 6.5h.01M8 13l-2 2 2 2M16 13l2 2-2 2"/>',
    async cargar(){
      const r = await API.get('/api/webdemo/lista').catch(()=>({}));
      const filas = (r.demos || []).map(d => [
        esc(d.nombre || '—'),
        d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener" style="color:var(--p1)">${esc(d.url)}</a>` : '—',
        esc(String(d.ts || '').slice(0, 16))]);
      return `<p class="pista">JARVIS diseña la web de un negocio y la publica en Vercel
          (necesita VERCEL_TOKEN en el .env).</p>
        <div class="mfila" style="margin-top:8px">
          <input id="demo-nombre" class="mcampo" style="flex:1" placeholder="nombre del negocio">
          <select id="demo-industria" class="mcampo">
            ${['general','restaurante','tecnologia','salud','legal','construccion','inmobiliaria',
               'educacion','moda','viajes'].map(i => `<option>${i}</option>`).join('')}
          </select>
        </div>
        <div class="mfila" style="margin-top:8px">
          <textarea id="demo-desc" class="mcampo" rows="3" style="flex:1"
            placeholder="qué hacen, qué quieren destacar…"></textarea>
        </div>
        <div class="mfila" style="margin-top:8px">
          <button class="mbtn" data-accion="demo-crear">Crear y publicar</button>
        </div>
        <div id="mod-salida"></div>
        <h4 style="margin:16px 0 8px;color:var(--p1);font-size:10.5px;letter-spacing:.18em">PUBLICADAS</h4>
        ${filas.length ? tabla(['Negocio','Dirección','Fecha'], filas)
                       : '<p class="pista">Todavía no hay demos.</p>'}`;
    }
  },

  llamadas:{
    titulo:'Llamadas', icono:'<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>',
    async cargar(){
      const e = await API.get('/api/llamar/estado').catch(()=>({}));
      return `<div class="mrejilla">
        ${caja('Twilio', `<div class="grande">${e.disponible ? 'listo' : 'no'}</div>
          <div class="pista">${esc(e.numero || '')}${e.motivo ? ' · ' + esc(e.motivo) : ''}</div>`)}
        ${caja('En espera', `<div class="pista">llamada ${e.cooldown_llamada ?? 0} s
          · SMS ${e.cooldown_sms ?? 0} s</div>`)}
      </div>
      <div class="mfila" style="margin-top:12px">
        <input id="llamar-msg" class="mcampo" style="flex:1"
          placeholder="qué quieres que te diga (por defecto: «JARVIS requiere su atención»)">
      </div>
      <div class="mfila" style="margin-top:8px">
        <button class="mbtn" data-accion="llamar" data-valor="llamada">Llámame</button>
        <button class="mbtn" data-accion="llamar" data-valor="sms">SMS</button>
        <button class="mbtn" data-accion="llamar" data-valor="whatsapp">WhatsApp</button>
      </div>
      <p class="pista" style="margin-top:10px">JARVIS también te llama solo cuando necesita
        que confirmes algo.</p>`;
    }
  },

  consejo:{
    titulo:'Consejo', icono:'<circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><path d="M3 20a5 5 0 0 1 10 0M11 20a5 5 0 0 1 10 0"/>',
    async cargar(){
      return `<p class="pista">JARVIS y ULTRON piensan el asunto por separado y después se
          sintetiza una decisión.</p>
        <div class="mfila" style="margin-top:8px">
          <input id="consejo-q" class="mcampo" style="flex:1" placeholder="¿sobre qué quieres que deliberen?">
          <button class="mbtn" data-accion="consejo">Deliberar</button>
        </div>
        <div id="mod-salida"></div>`;
    }
  }
};

let moduloActivo = null;
function pintarRail(){
  const rail = document.getElementById('rail'); rail.innerHTML = '';
  for (const [clave, m] of Object.entries(MODULOS)){
    const b = document.createElement('div');
    b.className = 'mod'; b.dataset.mod = clave;
    b.innerHTML = `<svg viewBox="0 0 24 24">${m.icono}</svg><span class="globo">${m.titulo}</span>`;
    b.onclick = () => abrirModulo(clave);
    rail.appendChild(b);
  }
}
async function abrirModulo(clave){
  const m = MODULOS[clave];
  if (!m) return;
  const lienzo = document.getElementById('lienzo-mod');
  if (moduloActivo === clave && lienzo.classList.contains('abierto')){ cerrarModulo(); return; }
  moduloActivo = clave;
  document.querySelectorAll('.rail .mod').forEach(b =>
    b.classList.toggle('activo', b.dataset.mod === clave));
  document.getElementById('mod-titulo').textContent = m.titulo;
  lienzo.classList.add('abierto');
  const cuerpo = document.getElementById('mod-contenido');
  cuerpo.innerHTML = '<p class="pista">Cargando…</p>';
  try{
    cuerpo.innerHTML = await m.cargar();
    if (clave === 'pantalla') engancharPantalla();
  }catch(e){ cuerpo.innerHTML = `<p class="pista">No pude cargar el módulo: ${esc(e.message||e)}</p>`; }
}
function cerrarModulo(){
  moduloActivo = null;
  document.getElementById('lienzo-mod').classList.remove('abierto');
  document.querySelectorAll('.rail .mod').forEach(b => b.classList.remove('activo'));
}
document.getElementById('mod-cerrar').onclick = cerrarModulo;
document.getElementById('mod-refrescar').onclick = () => moduloActivo && abrirModulo(moduloActivo);

const val = id => (document.getElementById(id)?.value || '').trim();
const salida = html => {
  const s = document.getElementById('mod-salida') || document.getElementById('mod-extra');
  if (s) s.innerHTML = `<div class="mcaja" style="margin-top:12px">${html}</div>`;
};
document.getElementById('mod-contenido').addEventListener('click', async e => {
  const b = e.target.closest('[data-accion]');
  if (!b) return;
  const a = b.dataset.accion, v = b.dataset.valor || '';
  b.disabled = true;
  try{
    switch(a){
      case 'matar': {
        const pid = b.dataset.pid;
        const r = await API.post('/api/system/kill',
          pid ? {pid: Number(pid), name: v, nombre: v} : {name: v, nombre: v});
        brindis(r.mensaje || r.message || (r.ok ? 'Proceso terminado.' : JSON.stringify(r).slice(0,140)));
        abrirModulo('sistema'); break;
      }
      case 'limpiar-ram':
        brindis(JSON.stringify(await API.post('/api/system/clean_ram', {})).slice(0,180)); break;
      case 'radar':
        salida('<pre style="white-space:pre-wrap;font-size:12px">'
          + esc(JSON.stringify(await API.get('/api/system/network_radar'), null, 1)).slice(0,1500) + '</pre>');
        break;
      case 'lockdown':
        if (confirm('¿Bloqueo total del equipo?'))
          brindis(JSON.stringify(await API.post('/api/system/lockdown', {})).slice(0,180));
        break;
      case 'teclear':
        await API.post('/cmd', {texto:'escribe ' + val('mod-teclear')});
        brindis('Texto enviado al equipo.'); break;
      case 'clic-derecho':
        await API.post('/mouse', {action:'right_click'}); brindis('Clic derecho.'); break;
      case 'subir': {
        const f = document.getElementById('mod-subir').files[0];
        if (!f){ brindis('Elija un archivo primero.'); break; }
        const fd = new FormData(); fd.append('file', f);
        const r = await fetch('/upload', {method:'POST', headers:{'X-Token':token}, body:fd});
        brindis(r.ok ? `«${f.name}» subido al equipo.` : 'No se pudo subir.');
        abrirModulo('archivos'); break;
      }
      case 'generar': {
        salida('<p class="pista">Generando… esto puede tardar.</p>');
        const r = await API.post('/generate', {prompt: val('mod-prompt')});
        salida(r.error ? `Error: ${esc(r.error)}`
          : `Listo: <b>${esc(r.filename || r.type || 'archivo')}</b>
             ${r.path ? `<a class="mbtn" style="margin-left:8px"
               href="${API.medios('/download/' + encodeURI(r.filename||''))}" download>bajar</a>` : ''}`);
        break;
      }
      case 'crear-evento':
        await API.post('/cmd', {texto:'agenda ' + val('mod-evento')});
        brindis('Evento enviado a la agenda.'); abrirModulo('agenda'); break;
      case 'borrar-evento':
        await API.del('/api/calendar/events/' + encodeURIComponent(v));
        brindis('Evento borrado.'); abrirModulo('agenda'); break;
      case 'modo-ofensiva': brindis(JSON.stringify(await API.up('/mode/ofensiva', {})).slice(0,150)); break;
      case 'modo-normal':   brindis(JSON.stringify(await API.up('/mode/normal', {})).slice(0,150)); break;
      case 'guardian-on':
        brindis((await API.post('/api/nexus/cmd', {agente:'ultron', texto:'activa el guardian'})).respuesta || 'hecho'); break;
      case 'guardian-off':
        brindis((await API.post('/api/nexus/cmd', {agente:'ultron', texto:'desactiva el guardian'})).respuesta || 'hecho'); break;
      case 'bloquear-ip':
        brindis(JSON.stringify(await API.up('/api/system/block_ip', {ip:v})).slice(0,150)); break;
      case 'restaurar-red':
        brindis((await API.post('/api/panel/accion', {accion:'restaurar_red'})).texto || 'hecho'); break;
      case 'decir':
        await API.post('/tts', {text: val('mod-decir')}); brindis('Hablando…'); break;
      case 'callar': await API.post('/tts_stop', {}); brindis('Voz detenida.'); break;
      case 'voz-instalar':
        brindis('Descargando la voz… tarda un poco.');
        brindis((await API.post('/api/panel/accion',
          {accion:'instalar_voz', valor: val('mod-voz')})).texto || 'hecho');
        abrirModulo('voz'); break;
      case 'voz-jarvis':
        brindis((await API.post('/api/panel/accion',
          {accion:'elegir_voz_jarvis', valor: val('mod-voz')})).texto || 'hecho');
        abrirModulo('voz'); break;
      case 'voz-ultron':
        brindis((await API.post('/api/panel/accion',
          {accion:'elegir_voz_ultron', valor: val('mod-voz')})).texto || 'hecho');
        abrirModulo('voz'); break;
      case 'ojos-on':
        brindis((await API.post('/api/panel/accion', {accion:'observador_on'})).texto || 'hecho');
        abrirModulo('ojos'); break;
      case 'ojos-off':
        brindis((await API.post('/api/panel/accion', {accion:'observador_off'})).texto || 'hecho');
        abrirModulo('ojos'); break;
      case 'ojos-mirar':
        salida('<p class="pista">Mirando la pantalla…</p>');
        salida(esc((await API.post('/api/panel/accion', {accion:'mirar_pantalla'})).texto || '')); break;
      case 'ver-pantalla':
        salida('<p class="pista">Describiendo…</p>');
        salida(esc((await API.post('/cmd', {texto:'mira mi pantalla'})).respuesta || '')); break;
      case 'movil-sonar':
        brindis((await API.post('/api/panel/accion', {accion:'movil_sonar'})).texto || 'hecho'); break;
      case 'movil-wifi':
        brindis((await API.post('/api/panel/accion',
          {accion:'movil_wifi', valor: val('mod-movil-ip')})).texto || 'hecho'); break;
      case 'movil-vigilar':
        brindis((await API.post('/api/panel/accion', {accion:'movil_vigilar'})).texto || 'hecho');
        abrirModulo('movil'); break;
      case 'movil-parar':
        brindis((await API.post('/api/panel/accion', {accion:'movil_parar'})).texto || 'hecho');
        abrirModulo('movil'); break;
      case 'movil-notis':
        salida(esc((await API.post('/cmd', {texto:'que notificaciones tengo'})).respuesta || '')); break;
      case 'movil-regla':
        brindis((await API.post('/cmd',
          {texto:'avisame cuando me escriba ' + val('mod-movil-regla')})).respuesta || 'hecho');
        abrirModulo('movil'); break;
      case 'movil-app':
        brindis((await API.post('/cmd',
          {texto:'abre ' + val('mod-movil-app') + ' en el movil'})).respuesta || 'hecho'); break;
      case 'wa-preparar':
        salida(esc((await API.post('/cmd', {texto:'mandale un whatsapp a '
          + val('mod-wa-quien') + ': ' + val('mod-wa-texto')})).respuesta || ''));
        break;
      case 'repetir-rutina':
        brindis('Repitiendo «' + v + '»…');
        brindis((await API.post('/api/panel/accion',
          {accion:'repetir_rutina', valor: v})).texto || 'hecho'); break;
      case 'mision-lanzar':
        brindis((await API.post('/cmd',
          {texto:'encargate de ' + val('mod-mision')})).respuesta || 'en marcha');
        abrirModulo('aprender'); break;
      case 'mision-parar':
        brindis((await API.post('/api/panel/accion', {accion:'mision_parar'})).texto || 'hecho');
        abrirModulo('aprender'); break;
      case 'analizar':
        salida('<p class="pista">Escribiendo el programa y ejecutándolo…</p>');
        salida(esc((await API.post('/cmd', {texto:'analiza ' + val('mod-analisis')})).respuesta || ''));
        break;
      case 'remoto-on':
        brindis('Publicando en la red privada…');
        brindis((await API.post('/remoto', {accion:'activar'})).texto || 'hecho');
        abrirModulo('enlace'); break;
      case 'remoto-off':
        brindis((await API.post('/remoto', {accion:'desactivar'})).texto || 'hecho');
        abrirModulo('enlace'); break;
      case 'abrir-puerto':
        brindis('Pidiendo permiso a Windows…');
        brindis((await API.post('/abrir_puerto', {})).texto || 'hecho');
        abrirModulo('enlace'); break;
      case 'afinar-exportar':
        brindis((await API.post('/api/panel/accion', {accion:'afinar_exportar'})).texto || 'hecho');
        abrirModulo('aprender'); break;
      case 'voz-on':  await API.post('/voz_windows', {silenciar:false}); brindis('Voz de Windows activa.'); break;
      case 'voz-off': await API.post('/voz_windows', {silenciar:true}); brindis('Voz de Windows silenciada.'); break;
      case 'saludo':    brindis((await API.get('/greet')).response || ''); break;
      case 'despedida': brindis((await API.get('/farewell')).response || ''); break;
      case 'probar-ia':
        salida('<pre style="white-space:pre-wrap;font-size:12px">'
          + esc(JSON.stringify(await API.post('/probar_ia', {}), null, 1)).slice(0,1200) + '</pre>'); break;
      case 'activar-agente':
        brindis((await API.post('/cmd', {texto:'activa agente ' + val('mod-agente')})).respuesta || 'hecho'); break;
      case 'desactivar-agente':
        brindis((await API.post('/cmd', {texto:'desactiva agente'})).respuesta || 'hecho'); break;
      case 'delegar':
        brindis(JSON.stringify(await API.post('/api/agent/delegate',
          {mensaje: val('mod-delegar'), message: val('mod-delegar')})).slice(0,200)); break;
      case 'bolsa':
        salida(esc(JSON.stringify(await API.post('/api/stock', {ticker: val('mod-ticker')}))).slice(0,900)); break;
      case 'noticias':
        salida(esc(JSON.stringify(await API.post('/api/news', {tema: val('mod-noticias'),
          query: val('mod-noticias')}))).slice(0,900)); break;
      case 'scrape':
        salida(esc(JSON.stringify(await API.post('/api/scrape', {url: val('mod-url')}))).slice(0,900)); break;
      case 'yt':
        salida(esc(JSON.stringify(await API.post('/api/yt/download', {url: val('mod-yt'),
          query: val('mod-yt')}))).slice(0,600)); break;
      case 'purgar-ultron':
        if (confirm('¿Borrar la memoria de conversaciones de ULTRON?')){
          await API.up('/purge', {}); brindis('Memoria de ULTRON purgada.'); abrirModulo('historial');
        }
        break;
      case 'rotar-pin': {
        if (!confirm('El PIN actual dejará de valer y habrá que reemparejar. ¿Seguir?')) break;
        const r = await API.post('/rotate_token', {});
        if (r.pin){ localStorage.setItem('jarvis_pin', r.pin);
          brindis('PIN nuevo: ' + r.pin + '. Recargue con el QR nuevo.'); }
        else brindis(r.error || 'No se pudo cambiar.');
        break;
      }
      case 'm3d-modelar': {
        let ent = val('m3d-entrada');
        if (!ent){ brindis('Escribe una descripción o una ruta.'); break; }
        const tp = document.getElementById('m3d-tpose')?.checked;
        // No duplicar el verbo si el usuario ya lo escribió.
        ent = ent.replace(/^\s*(mod[eé]la\w*|escan\w*|haz(me)?\s+un\s+modelo\s*(3\s*-?\s*d)?\s*(de)?)\s*:?\s*/i, '').trim();
        ent = ent.replace(/^\s*(en\s+)?3\s*-?\s*d\s*:?\s*/i, '').trim();
        salida('<p class="pista">Modelando en 3D… 1–3 min. Te abriré el visor al acabar.</p>');
        const r = await API.post('/cmd', {texto:
          (tp ? 'modélame en 3D en T-pose: ' : 'modélame en 3D: ') + ent});
        salida('<pre style="white-space:pre-wrap;font-size:12px">'
          + esc(r.respuesta || JSON.stringify(r).slice(0,600)) + '</pre>');
        break;
      }
      case 'm3d-holograma': {
        salida('<p class="pista">Renderizando holograma…</p>');
        const r = await API.post('/cmd', {texto:'muéstrame el holograma de eso'});
        salida('<pre style="white-space:pre-wrap;font-size:12px">'
          + esc(r.respuesta || '') + '</pre>');
        break;
      }
      case 'm3d-abrir':
        await API.post('/cmd', {texto:'abre la carpeta Descargas/JARVIS/Modelos3D'});
        brindis('Abriendo la carpeta de modelos.'); break;
      case 'cie-resolver': case 'cie-graficar-2d': case 'cie-graficar-3d': {
        const q = val('cie-q');
        if (!q){ brindis('Dicta el problema primero.'); break; }
        const sufijo = a === 'cie-graficar-3d' ? ' y grafícalo en 3D'
                     : a === 'cie-graficar-2d' ? ' y grafícalo' : '';
        salida('<p class="pista">Calculando… el visor se abrirá al acabar.</p>');
        const r = await API.post('/cmd', {texto: q + sufijo});
        salida('<pre style="white-space:pre-wrap;font-size:12px">'
          + esc(r.respuesta || JSON.stringify(r).slice(0,600)) + '</pre>');
        break;
      }
      case 'cie-tabla': {
        salida('<p class="pista">Dibujando los 118 elementos…</p>');
        const r = await API.post('/cmd', {texto:'enséñame la tabla periódica'});
        salida('<pre style="white-space:pre-wrap;font-size:12px">'
          + esc(r.respuesta || '') + '</pre>');
        break;
      }
      case 'cie-entrenar': {
        salida('<p class="pista">Examen de ciencias en marcha… medio minuto.</p>');
        const r = await API.post('/cmd', {texto:'entrena tus ciencias'});
        salida('<pre style="white-space:pre-wrap;font-size:12px">'
          + esc(r.respuesta || '') + '</pre>');
        break;
      }
      case 'cie-abrir':
        await API.post('/cmd', {texto:'abre la carpeta Descargas/JARVIS/Ciencia'});
        brindis('Abriendo la carpeta de ciencias.'); break;
      case 'cbr-buscar': {
        const q = val('cbr-q');
        if (!q){ brindis('Escribe qué buscar.'); break; }
        const r = await API.post('/cmd', {texto:'busca en tu memoria ' + q});
        salida('<pre style="white-space:pre-wrap;font-size:12px">'
          + esc(r.respuesta || '') + '</pre>');
        break;
      }
      case 'correo-leer': {
        salida('<p class="pista">Abriendo…</p>');
        const r = await API.get('/api/correo/leer?id=' + encodeURIComponent(v));
        const m = r.mensaje || {};
        if (!r.ok || m.ok === false){ salida(esc(r.error || m.error || 'No pude abrirlo.')); break; }
        salida(`<b>${esc(m.subject || '(sin asunto)')}</b><div class="pista">${esc(m.from || '')}</div>
          <pre style="white-space:pre-wrap;font-size:12px">${esc(m.body || '')}</pre>`);
        const dir = (String(m.from || '').match(/<([^>]+)>/) || [])[1] || m.from || '';
        const para = document.getElementById('correo-para'), asu = document.getElementById('correo-asunto');
        if (para) para.value = dir;
        if (asu) asu.value = /^re:/i.test(m.subject || '') ? m.subject : 'Re: ' + (m.subject || '');
        break;
      }
      case 'correo-resumir': {
        salida('<p class="pista">Leyendo la bandeja…</p>');
        const r = await API.get('/api/correo/resumir');
        salida(esc(r.resumen || r.error || 'Sin respuesta.'));
        break;
      }
      case 'correo-enviar': {
        const para = val('correo-para'), cuerpo = val('correo-cuerpo');
        if (!para || !cuerpo){ brindis('Falta el destinatario o el mensaje.'); break; }
        if (!confirm('¿Enviar el correo a ' + para + '?')) break;
        const r = await API.post('/api/correo/responder',
          {destino: para, asunto: val('correo-asunto'), cuerpo});
        brindis(r.mensaje || r.error || (r.ok ? 'Enviado.' : 'No se pudo enviar.'));
        break;
      }
      case 'demo-crear': {
        const nombre = val('demo-nombre');
        if (!nombre){ brindis('Escribe el nombre del negocio.'); break; }
        salida('<p class="pista">Diseñando y publicando… 1–2 min.</p>');
        const r = await API.post('/api/webdemo/crear',
          {nombre, industria: val('demo-industria') || 'general', descripcion: val('demo-desc')});
        salida(r.ok && r.url
          ? `Publicada: <a href="${esc(r.url)}" target="_blank" rel="noopener" style="color:var(--p1)">${esc(r.url)}</a>`
          : 'No se pudo: ' + esc(r.error || 'error desconocido'));
        break;
      }
      case 'llamar': {
        const etiqueta = {llamada:'la llamada', sms:'el SMS', whatsapp:'el WhatsApp'}[v] || 'el aviso';
        if (!confirm('¿Enviar ' + etiqueta + ' a tu móvil?')) break;
        const r = await API.post('/api/llamar', {canal: v, mensaje: val('llamar-msg') || undefined});
        brindis(r.mensaje || r.error || (r.ok ? 'Hecho.' : 'No se pudo.'));
        abrirModulo('llamadas');
        break;
      }
      case 'consejo': {
        const q = val('consejo-q');
        if (!q){ brindis('Escribe el asunto.'); break; }
        salida('<p class="pista">Deliberando… puede tardar un minuto.</p>');
        const r = await API.post('/api/nexus/cmd', {agente:'consejo', texto:q});
        if (!r.ok){ salida(esc(r.error || 'El consejo no respondió.')); break; }
        salida(`${r.desacuerdo ? '<div class="pista" style="color:#ffb86b">No están de acuerdo.</div>' : ''}
          <h4 style="margin:8px 0 4px;color:var(--p1);font-size:10px;letter-spacing:.18em">JARVIS</h4>
          <pre style="white-space:pre-wrap;font-size:12px">${esc(r.jarvis || '')}</pre>
          <h4 style="margin:8px 0 4px;color:var(--p1);font-size:10px;letter-spacing:.18em">ULTRON</h4>
          <pre style="white-space:pre-wrap;font-size:12px">${esc(r.ultron || '')}</pre>
          <h4 style="margin:8px 0 4px;color:var(--p1);font-size:10px;letter-spacing:.18em">SÍNTESIS</h4>
          <pre style="white-space:pre-wrap;font-size:12px">${esc(r.sintesis || '')}</pre>`);
        break;
      }
      default: brindis('Acción desconocida: ' + a);
    }
  }catch(err){ brindis('Error: ' + (err.message || err)); }
  finally{ b.disabled = false; }
});

/* ── ratón remoto sobre la imagen de la pantalla ── */
function engancharPantalla(){
  const img = document.getElementById('espejo-pantalla');
  if (!img) return;
  let ultimo = null;
  const rel = e => { const r = img.getBoundingClientRect();
    return {x:(e.clientX-r.left)/r.width, y:(e.clientY-r.top)/r.height}; };
  img.addEventListener('pointerdown', e => { ultimo = rel(e); img.setPointerCapture(e.pointerId); });
  img.addEventListener('pointermove', e => {
    if (!ultimo) return;
    const p = rel(e), dx = (p.x-ultimo.x)*1400, dy = (p.y-ultimo.y)*900;
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1){
      API.post('/mouse', {action:'move', dx:Math.round(dx), dy:Math.round(dy)}); ultimo = p;
    }
  });
  img.addEventListener('pointerup', e => {
    const p = rel(e);
    if (ultimo && Math.abs(p.x-ultimo.x) < .004 && Math.abs(p.y-ultimo.y) < .004)
      API.post('/mouse', {action:'click'});
    ultimo = null;
  });
  img.addEventListener('wheel', e => {
    e.preventDefault(); API.post('/mouse', {action:'scroll', amount: e.deltaY > 0 ? -3 : 3});
  }, {passive:false});
}

