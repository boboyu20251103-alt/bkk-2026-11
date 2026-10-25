// 離線：導覽請求 network-first（有網路一律拿最新版），斷線才回快取。版本 202610251004
const C = 'bkk-202610251004';
self.addEventListener('install', e => { self.skipWaiting(); e.waitUntil(caches.open(C).then(c => c.add('./')).catch(() => {})); });
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k)))).then(() => self.clients.claim())
));
self.addEventListener('fetch', e => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(
    fetch(e.request, { cache: 'no-store' })
      .then(r => { if (r.ok) { const cp = r.clone(); caches.open(C).then(c => c.put('./', cp)); } return r; })
      .catch(() => caches.match('./').then(r => r || new Response('離線中，且沒有快取的版本。', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } })))
  );
});
