/* Service worker: aplikácia sa načíta aj pri slabom signáli. Dáta (API) sa NIKDY neukladajú do cache. */
const CACHE = "bid-dochadzka-v1";
const ASSETS = ["/", "/static/style.css", "/static/app.js", "/static/manifest.webmanifest", "/static/icons/icon-192.png", "/kiosk", "/static/kiosk.js", "/static/kiosk.css"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/") || e.request.method !== "GET") return; // API vždy zo siete
  e.respondWith(fetch(e.request).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request)));
});
