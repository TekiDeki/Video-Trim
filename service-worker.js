// Video Trimmer - offline shell.
// Pagina nu cere nimic din retea dupa prima incarcare: fisierul video al utilizatorului
// nu trece niciodata prin aici (e un blob local), deci cache-ul tine doar pagina si iconitele.
const CACHE_PREFIX = 'video-trimmer-v';
const CACHE_NAME = CACHE_PREFIX + '1';
const ASSETS = [
  './',
  './index.html',
  './LICENSE',
  './manifest.json',
  './favicon.ico',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png',
  './apple-touch-icon.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(CACHE_NAME).then(function (cache) { return cache.addAll(ASSETS); }));
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil((async function () {
    const keys = await caches.keys();
    const obsolete = keys.filter(function (k) { return k.indexOf(CACHE_PREFIX) === 0 && k !== CACHE_NAME; });
    await Promise.all(obsolete.map(function (k) { return caches.delete(k); }));
  })());
  self.clients.claim();
});

// Network-first pentru pagina (ca sa vada imediat o versiune noua), cache pentru restul.
self.addEventListener('fetch', function (event) {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  if (req.mode === 'navigate' || url.pathname.endsWith('index.html') || url.pathname.endsWith('/')) {
    event.respondWith((async function () {
      try {
        const fresh = await fetch(req);
        const cache = await caches.open(CACHE_NAME);
        cache.put(req, fresh.clone());
        return fresh;
      } catch (e) {
        const cached = await caches.match(req);
        return cached || caches.match('./index.html');
      }
    })());
    return;
  }

  event.respondWith((async function () {
    const cached = await caches.match(req);
    if (cached) return cached;
    try {
      const fresh = await fetch(req);
      if (fresh && fresh.ok) {
        const cache = await caches.open(CACHE_NAME);
        cache.put(req, fresh.clone());
      }
      return fresh;
    } catch (e) {
      return new Response('', { status: 504, statusText: 'offline' });
    }
  })());
});
