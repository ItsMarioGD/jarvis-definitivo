/* Light HUD behaviors — purely visual, no backend wiring.
   Clock, telemetry scramble, chat/generator echo, modules grid, modes, boot. */

const $ = <T extends HTMLElement = HTMLElement>(sel: string) => document.querySelector<T>(sel)!

const GLYPHS = 'ABCDEF0123456789ΩΔΣΦΨλβξ◊#@%'

function scrambleTo(el: HTMLElement, text: string, ms = 600) {
  const start = performance.now()
  const tick = (now: number) => {
    const p = Math.min((now - start) / ms, 1)
    const locked = Math.floor(p * text.length)
    let out = ''
    for (let i = 0; i < text.length; i++) {
      out += i < locked || text[i] === ' '
        ? text[i]
        : GLYPHS[(Math.random() * GLYPHS.length) | 0]
    }
    el.textContent = out
    if (p < 1) requestAnimationFrame(tick)
    else el.textContent = text
  }
  requestAnimationFrame(tick)
}

function buildCpuBars(host: HTMLElement, n = 28) {
  host.innerHTML = ''
  for (let i = 0; i < n; i++) {
    const cb = document.createElement('div')
    cb.className = 'cb'
    const f = document.createElement('div')
    f.className = 'cb-f'
    f.style.height = `${10 + Math.random() * 80}%`
    cb.appendChild(f)
    host.appendChild(cb)
  }
}

export function initHud() {
  // ── Boot sequence ──
  const bootBox = $('#bootBox')
  const bootBar = $<HTMLElement>('#bootBar')
  const bootPct = $('#bootPct')
  const splash = $('#splash')
  const lines = [
    'NÚCLEO HOLOGRÁFICO .......... [OK]',
    'ENJAMBRE DE PARTÍCULAS ...... [OK]',
    'LIQUID GLASS / SHADER FBO ... [OK]',
    'ABERRACIÓN CROMÁTICA ........ [OK]',
    'POST-PROCESO CINEMATOGRÁFICO  [OK]',
    'SISTEMAS OPERATIVOS EN LÍNEA',
  ]
  let li = 0
  const step = () => {
    if (li < lines.length) {
      const d = document.createElement('div')
      d.className = 'ln ok'
      d.textContent = '> ' + lines[li]
      bootBox.appendChild(d)
      li++
      const pct = Math.round((li / lines.length) * 100)
      bootBar.style.width = pct + '%'
      bootPct.textContent = pct + '%'
      setTimeout(step, 320 + Math.random() * 240)
    } else {
      setTimeout(() => splash.classList.add('hide'), 700)
    }
  }
  setTimeout(step, 300)

  // ── Clock + uptime ──
  const clock = $('#clock')
  const up = $('#upV')
  const ftrClock = $('#ftrClock')
  let upS = 0
  const pad = (n: number) => String(n).padStart(2, '0')
  const tick = () => {
    const d = new Date()
    const t = d.toLocaleTimeString('en-GB')
    clock.textContent = t
    ftrClock.textContent = t
    upS++
    up.textContent = `${pad((upS / 3600) | 0)}:${pad(((upS % 3600) / 60) | 0)}:${pad(upS % 60)}`
  }
  tick()
  setInterval(tick, 1000)

  // ── Telemetry scramble + bars ──
  buildCpuBars($('#cpuB'))
  buildCpuBars($('#sysCpuB'))
  const cpuV = $('#cpuV')
  const sigV = $('#sigV')
  const latV = $('#latV')
  const ramV = $<HTMLElement>('#ramV')
  const sysCpu = $('#sysCpu')
  const sysRam = $<HTMLElement>('#sysRam')
  const sysNet = $('#sysNet')
  const refresh = () => {
    const cpu = 18 + Math.random() * 74
    const ram = 42 + Math.random() * 52
    const dbm = -(28 + Math.random() * 30)
    const net = 4 + Math.random() * 60
    scrambleTo(cpuV, `${Math.round(cpu)}%`)
    scrambleTo(sigV, `${dbm.toFixed(0)}dBm`)
    latV.textContent = `LATENCIA ${Math.round(net)}ms`
    ramV.style.width = `${ram}%`
    sysCpu.textContent = `${Math.round(cpu)}`
    sysRam.style.width = `${ram}%`
    sysNet.textContent = `${Math.round(net)}ms`
    document.querySelectorAll('#cpuB .cb-f, #sysCpuB .cb-f').forEach((f) => {
      ;(f as HTMLElement).style.height = `${10 + Math.random() * 80}%`
    })
  }
  refresh()
  setInterval(refresh, 2200)

  // ── Chat echo ──
  const msgs = $('#msgs')
  const form = $<HTMLFormElement>('#chatForm')
  const input = $<HTMLInputElement>('#chatInput')
  const jarvisReply = () => {
    const r = [
      'Sistemas operativos en línea. Núcleo estabilizado.',
      'Refracción óptica recalibrada. Aberración dentro de parámetros.',
      'Telemetría óptima. Latencia sub-umbral detectada.',
      'Protocolo de seguridad reforzado. Acceso concedido.',
    ][(Math.random() * 4) | 0]
    const m = document.createElement('div')
    m.className = 'msg jarvis'
    m.innerHTML = `<div class="w"><span>J.A.R.V.I.S.</span><span class="w-t">${new Date().toLocaleTimeString('en-GB')}</span></div>${jarvisReply0()}`
    msgs.appendChild(m)
    typeText(m.lastChild as HTMLElement, r)
    msgs.scrollTop = msgs.scrollHeight
  }
  const jarvisReply0 = () => '<span class="js"></span>'
  const typeText = (el: HTMLElement, text: string) => {
    let i = 0
    const id = setInterval(() => {
      el.textContent = text.slice(0, ++i)
      msgs.scrollTop = msgs.scrollHeight
      if (i >= text.length) clearInterval(id)
    }, 18)
  }
  form.addEventListener('submit', (e) => {
    e.preventDefault()
    const v = input.value.trim()
    if (!v) return
    const m = document.createElement('div')
    m.className = 'msg user'
    m.innerHTML = `<div class="w"><span>OPERADOR</span><span class="w-t">${new Date().toLocaleTimeString('en-GB')}</span></div>${v}`
    msgs.appendChild(m)
    input.value = ''
    msgs.scrollTop = msgs.scrollHeight
    setTimeout(jarvisReply, 400)
  })

  // ── Generator echo ──
  const gForm = $<HTMLFormElement>('#genForm')
  const gInput = $<HTMLInputElement>('#genInput')
  const gStatus = $('#genStatus')
  const gList = $('#genList')
  gForm.addEventListener('submit', (e) => {
    e.preventDefault()
    const v = gInput.value.trim()
    if (!v) return
    gStatus.textContent = 'GENERANDO…'
    gStatus.classList.add('ld')
    const row = document.createElement('div')
    row.className = 'gi'
    row.innerHTML = `<div class="ic">◈</div><div class="inf"><div class="nm">${v}</div><div class="mt">procesado · ${(Math.random() * 4 + 1).toFixed(1)}s</div></div>`
    gList.prepend(row)
    gInput.value = ''
    setTimeout(() => {
      gStatus.textContent = 'Listo.'
      gStatus.classList.remove('ld')
    }, 1400)
  })

  // ── Modules grid ──
  const grid = $('#modulesGrid')
  const MODULES = [
    { ic: '🛰', t: 'RESUMEN', d: 'Síntesis de documentos y contexto.', tags: ['pdf', 'web'], n: 12 },
    { ic: '🌤', t: 'CLIMA', d: 'Pronóstico y alertas por región.', tags: ['geo'], n: 5 },
    { ic: '🌐', t: 'TRADUCIR', d: 'Traducción neuronal multilingüe.', tags: ['nlp'], n: 38 },
    { ic: '📡', t: 'NOTICIAS', d: 'Agregación y resumen de feeds.', tags: ['ai'], n: 21 },
    { ic: '🔎', t: 'SCRAPING', d: 'Extracción estructurada de sitios.', tags: ['web'], n: 9 },
    { ic: '📄', t: 'PDF CHAT', d: 'Conversación sobre documentos.', tags: ['pdf'], n: 7 },
    { ic: '🔗', t: 'RESUMEN URL', d: 'Resumen de páginas completas.', tags: ['web'], n: 14 },
    { ic: '❄', t: 'COOLING', d: 'Control térmico del núcleo.', tags: ['hw'], n: 3 },
  ]
  MODULES.forEach((m) => {
    const c = document.createElement('div')
    c.className = 'mcard'
    c.innerHTML = `<div class="ic">${m.ic}</div><h3>${m.t}</h3><p>${m.d}</p>
      <div class="meta">${m.tags.map((x) => `<span class="chip">${x}</span>`).join('')}</div>
      <div class="count">${m.n}</div>`
    grid.appendChild(c)
  })

  // ── Modes ──
  const mSleep = $('#mSleep')
  const mFocus = $('#mFocus')
  const mMod = $('#mMod')
  const overlay = $('#modulesOverlay')
  const mModClose = $('#mModClose')
  mSleep.addEventListener('click', () => {
    document.body.classList.toggle('sleep')
    mSleep.classList.toggle('on')
  })
  mFocus.addEventListener('click', () => {
    document.body.classList.toggle('focus')
    mFocus.classList.toggle('on')
  })
  mMod.addEventListener('click', () => overlay.classList.add('on'))
  mModClose.addEventListener('click', () => overlay.classList.remove('on'))

  // ── Liquid-reaction ripple on click ──
  const style = document.createElement('style')
  style.textContent = `.ripple-ring{position:fixed;border-radius:50%;border:2px solid rgba(33,230,255,.6);box-shadow:0 0 18px rgba(33,230,255,.5),inset 0 0 18px rgba(255,200,150,.3);pointer-events:none;transform:translate(-50%,-50%);z-index:97;animation:lg-ripple .7s ease-out forwards}@keyframes lg-ripple{0%{width:0;height:0;opacity:.9}100%{width:220px;height:220px;opacity:0}}`
  document.head.appendChild(style)
  window.addEventListener('click', (e) => {
    const r = document.createElement('span')
    r.className = 'ripple-ring'
    r.style.left = e.clientX + 'px'
    r.style.top = e.clientY + 'px'
    document.body.appendChild(r)
    setTimeout(() => r.remove(), 700)
  })

  // expose a tiny energy feed for the WebGL stage
  return {
    feedEnergy(v: number) {
      scrambleTo(cpuV, `${Math.round(v * 100)}%`)
    },
  }
}
