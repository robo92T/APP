// App shell only: NEVER cache authentication tokens, API responses, or employee records.
const STATIC_CACHE='skdochadzka-shell-v7';
const ASSETS=['/assets/style.css','/assets/mobile.css','/assets/app.js','/assets/mobile-ui.js','/assets/employee-calendar.js','/assets/icon.svg','/manifest.webmanifest'];
self.addEventListener('install',event=>event.waitUntil(caches.open(STATIC_CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==STATIC_CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET'||new URL(request.url).origin!==self.location.origin)return;
  const path=new URL(request.url).pathname;
  if(path.startsWith('/api/')||path==='/docs'||path==='/openapi.json')return;
  if(path==='/'){event.respondWith(fetch(request).catch(()=>new Response('<!doctype html><html lang="sk"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title><body style="font:16px system-ui;padding:35px"><h1>Dochádzka</h1><p>Si offline. Pre zobrazenie dochádzky a odosielanie žiadostí sa pripoj k internetu.</p></body></html>',{headers:{'Content-Type':'text/html;charset=utf-8'}})));return;}
  if(ASSETS.includes(path)){event.respondWith(fetch(request).then(resp=>{if(resp.ok){const clone=resp.clone();caches.open(STATIC_CACHE).then(c=>c.put(request,clone));}return resp}).catch(()=>caches.match(request))); }
});