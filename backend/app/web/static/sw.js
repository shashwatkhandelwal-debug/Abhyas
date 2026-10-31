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
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME_AUDIO && key !== CACHE_NAME_STATIC).map((key) => caches.delete(key)))
    )
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
const WAKING_HINT_MS = 3000;
const NAV_BACKOFF_MS = [1000, 2000, 4000, 8000, 15000];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const cached = (url) => caches.open(CACHE_NAME_STATIC).then((cache) => cache.match(url));
const RETRY_PAGE = '<meta charset="utf-8"><p style="margin:2rem;font:1.1rem sans-serif">सर्वर नहीं मिला, पेज फिर खोलें।<br>Server not reachable, please reload.';
// Quiet retries (~30 s). A POST is replayed only if it got no answer at all.
async function fetchWithRetry(request) {
  const get = request.method === 'GET' || request.method === 'HEAD';
  let last = null;
  for (let i = 0; i <= NAV_BACKOFF_MS.length; i++) {
    if (i) await sleep(NAV_BACKOFF_MS[i - 1]);
    try {
      const response = await fetch(request.clone());
      if (!get || ![502, 503, 504].includes(response.status)) return response;
      last = response;
    } catch (err) {
      if (!self.navigator.onLine) throw err;
    }
  }
  return last || new Response(RETRY_PAGE, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}
// "Waking up" only on the very first load of the entry page, and only if the server is silent for 3 s.
async function handleNavigation(request, url) {
  const entry = !request.referrer && (url.pathname === '/login' || url.pathname === '/');
  try {
    const answer = fetchWithRetry(request);
    if (!entry) return await answer;
    return (await Promise.race([answer, sleep(WAKING_HINT_MS).then(() => null)])) || (await cached('/waking')) || (await answer);
  } catch (err) {
    return (await cached('/offline.html')) || new Response('Offline', { status: 503 });
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
    event.respondWith(handleNavigation(event.request, url));
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
