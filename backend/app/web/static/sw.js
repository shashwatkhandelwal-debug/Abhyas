

const BUILD_VERSION = '__BUILD_VERSION__';
const STATIC_CACHE_PREFIX = 'abhyas-static-';
const CACHE_NAME_STATIC = STATIC_CACHE_PREFIX + BUILD_VERSION;
const CACHE_NAME_AUDIO = 'abhyas-audio-v1';
const MAX_AUDIO_CACHE_ITEMS = 30;

const STATIC_ASSETS = [
  '/static/app.css?v=' + BUILD_VERSION,
  '/static/chat.js?v=' + BUILD_VERSION,
  '/static/recorder.js?v=' + BUILD_VERSION,
  '/static/ack.js',
  '/static/manifest.json',
  '/offline.html',
  '/waking',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME_STATIC).then((cache) => {
      
      return cache.addAll(STATIC_ASSETS.map((url) => new Request(url, { cache: 'reload' })));
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          const staleStatic = key.startsWith(STATIC_CACHE_PREFIX) && key !== CACHE_NAME_STATIC;
          if (staleStatic || (key !== CACHE_NAME_AUDIO && key !== CACHE_NAME_STATIC)) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

async function trimCache(cacheName, maxItems) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length > maxItems) {
    await cache.delete(keys[0]);
    await trimCache(cacheName, maxItems);
  }
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  
  if (url.pathname.startsWith('/api/audio/')) {
    event.respondWith(
      caches.open(CACHE_NAME_AUDIO).then(async (cache) => {
        const cachedResponse = await cache.match(event.request);
        if (cachedResponse) {
          return cachedResponse;
        }
        try {
          const networkResponse = await fetch(event.request);
          if (networkResponse.status === 200) {
            cache.put(event.request, networkResponse.clone());
            trimCache(CACHE_NAME_AUDIO, MAX_AUDIO_CACHE_ITEMS);
          }
          return networkResponse;
        } catch (err) {
          return new Response(null, { status: 504, statusText: 'Gateway Timeout' });
        }
      })
    );
    return;
  }

  
  if (event.request.mode === 'navigate' || event.request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(event.request).then(async (response) => {
        
        
        if ([502, 503, 504].includes(response.status)) {
          const cache = await caches.open(CACHE_NAME_STATIC);
          const waking = await cache.match('/waking');
          if (waking) return waking;
        }
        return response;
      }).catch(async () => {
        const cache = await caches.open(CACHE_NAME_STATIC);
        const cachedOffline = await cache.match('/offline.html');
        return cachedOffline || new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
      })
    );
    return;
  }

  
  if (url.pathname.startsWith('/static/') && /\.(js|css)$/.test(url.pathname)) {
    event.respondWith(
      caches.open(CACHE_NAME_STATIC).then(async (cache) => {
        const cached = await cache.match(event.request);
        const refresh = fetch(event.request).then((networkResponse) => {
          if (networkResponse.status === 200) {
            cache.put(event.request, networkResponse.clone());
          }
          return networkResponse;
        });
        if (cached) {
          refresh.catch(() => {});
          return cached;
        }
        return refresh;
      })
    );
    return;
  }

  
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).then((networkResponse) => {
          if (networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME_STATIC).then((cache) => cache.put(event.request, responseClone));
          }
          return networkResponse;
        });
      })
    );
    return;
  }

  
  event.respondWith(fetch(event.request));
});
