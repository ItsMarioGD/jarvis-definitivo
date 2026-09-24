/* JARVIS — service worker sin caché.

   El anterior guardaba /mobile con «caché primero» y un nombre que nunca
   cambiaba: el teléfono seguía cargando para siempre la página vieja (con
   sus fallos de emparejamiento) aunque el PC se actualizara. Este borra todo
   lo que dejó aquel, recarga las pestañas abiertas y a partir de ahí la
   interfaz siempre llega fresca del PC. Solo sigue existiendo para que el
   teléfono pueda «añadir a la pantalla de inicio». */

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const viejas = await caches.keys();
    for (const k of viejas) await caches.delete(k);
    await self.clients.claim();
    // Solo si había caché del anterior hay una página vieja en pantalla que
    // cambiar por la buena; en una instalación limpia no se recarga nada.
    if (viejas.length) {
      for (const c of await self.clients.matchAll({ type: 'window' })) {
        try { await c.navigate(c.url); } catch (_) {}
      }
    }
  })());
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET' || e.request.mode !== 'navigate') return;
  e.respondWith(
    fetch(e.request, { cache: 'no-store' }).catch(() => new Response(
      '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">' +
      '<body style="background:#030407;color:#ECE7DE;font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0;text-align:center">' +
      '<div><h2 style="font-weight:400">JARVIS no responde</h2><p style="color:#8A8F9C">¿Está encendido el PC y en la misma red?</p>' +
      '<button onclick="location.reload()" style="margin-top:12px;padding:10px 18px;border-radius:999px;border:1px solid #555;background:none;color:inherit">Reintentar</button></div>',
      { headers: { 'Content-Type': 'text/html; charset=utf-8' } }))
  );
});
