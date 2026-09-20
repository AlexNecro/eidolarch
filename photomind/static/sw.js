const CACHE='eidolarch-shell-v228';
const SHELL=['/','/assets/app.css?v=2.2.14','/assets/app.js?v=2.2.14','/assets/viewer.js?v=2.2.14','/assets/settings.js?v=2.2.14','/manifest.json?v=2.2.14','/assets/icons/app-mark.svg?v=2.2.14'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('eidolarch-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;const u=new URL(e.request.url);if(u.pathname.startsWith('/api/'))return;e.respondWith(fetch(e.request).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));return r}).catch(()=>caches.match(e.request)))});
