/* ===== Service Worker — Ajorpareh Mini App Offline Cache ===== */
const CACHE_NAME = 'ajorpareh-v6-audit-perf';
const STATIC_ASSETS = [
  '/app/',
  '/app/index.html',
  '/app/app.js',
  '/app/app.js?v=20260813-audit-perf',
  '/app/styles.css',
  '/app/site.webmanifest',
  '/app/hokm.css',
  '/app/hokm.js?v=2-lazy',
  '/app/boardgames.js?v=2-lazy',
  '/app/ajorchin.css',
  '/app/ajorchin.js?v=2-lazy',
  '/app/snake.css',
  '/app/snake.js?v=2-lazy',
  '/app/landing.css',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // فقط GET و فقط فایل‌های استاتیک
  if (event.request.method !== 'GET') return;
  // API calls: network-first
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }
  // Static assets: cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response.ok && url.origin === self.location.origin) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => {
        // fallback: صفحه اصلی
        if (url.pathname.startsWith('/app/')) {
          return caches.match('/app/');
        }
      });
    })
  );
});
