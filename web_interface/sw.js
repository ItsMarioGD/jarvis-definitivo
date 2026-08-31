/* Service worker del HUD AETHER.
 *
 * El anterior era cache-first para todo GET y con un nombre de cache fijo
 * ('jarvis-mobile-v1'): servia lo cacheado y solo iba a red si no habia nada,
 * sin revalidar nunca. Como la clave no cambiaba, el handler de 'activate'
 * tampoco llegaba a borrar nada. Resultado: quien tuviera /mobile cacheado
 * seguia viendo la interfaz antigua indefinidamente, aun despues de
 * actualizar el servidor.
 *
 * Ahora:
 *   - Nombre de cache versionado, para que 'activate' purgue lo viejo.
 *   - Navegaciones (el HTML): red primero, cache solo como respaldo offline.
 *   - Estaticos: cache primero, pero refrescando la copia en segundo plano.
 */
const CACHE = 'jarvis-aether-v2';

// Solo estaticos estables. El HTML se sirve siempre desde red cuando la hay.
const SHELL = [
  '/manifest.webmanifest',
  '/icon-192.png',
  '/icon-512.png',
  '/assets/core.css',
  '/assets/orb.js',
  '/assets/voice.js',
  '/assets/hud.js',
  '/assets/socket.io.min.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      // addAll falla entero si un recurso falla; los pedimos sueltos.
      .then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;      // CDN, fuentes, etc.
  if (url.pathname.startsWith('/socket.io')) return;    // tiempo real
  if (url.pathname.startsWith('/api/')) return;         // datos vivos
  if (url.pathname === '/stats') return;

  // El documento siempre desde red: es lo que cambia al actualizar el HUD.
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match('/')))
    );
    return;
  }

  // Estaticos: responde ya desde cache, pero actualiza la copia por detras.
  e.respondWith(
    caches.match(req).then((hit) => {
      const red = fetch(req).then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => hit);
      return hit || red;
    })
  );
});
