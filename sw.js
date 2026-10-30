// Lore Ledger service worker: app shell cached for offline use, data fetched network-first.
const CACHE = 'lore-ledger-v1';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png',
  'https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.hostname === 'api.justtcg.com' || url.hostname.endsWith('tcgplayer.com')) return;
  if (url.pathname.endsWith('/data.json')) {            // network first, fall back to cache
    e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request)));
    return;
  }
  if (url.pathname.includes('/img/') || url.hostname === 'fonts.gstatic.com') {   // cache first (immutable)
    e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; })));
    return;
  }
  // shell: stale-while-revalidate
  e.respondWith(caches.match(e.request).then(hit => { const net = fetch(e.request).then(r => { if (r && r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); } return r; }).catch(() => hit); return hit || net; }));
});
