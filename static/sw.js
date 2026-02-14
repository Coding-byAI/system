// Media Streaming Lab - Offline-first PWA
const CACHE_VERSION = 'media-streaming-lab-offline-v2';
const STATIC_CACHE = CACHE_VERSION + '-static';
const PAGES_CACHE = CACHE_VERSION + '-pages';
const MEDIA_CACHE = CACHE_VERSION + '-media';

// Precache these so the app shell works offline immediately
const PRECACHE_URLS = ['/manifest.json', '/icon.png', '/login'];

self.addEventListener('install', function (event) {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE).then(function (cache) {
      return cache.addAll(PRECACHE_URLS).catch(function () {
        // Ignore if some URLs fail (e.g. / requires auth redirect)
        return Promise.resolve();
      });
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.map(function (key) {
          if (key.startsWith('media-streaming-lab') && key !== STATIC_CACHE && key !== PAGES_CACHE && key !== MEDIA_CACHE) {
            return caches.delete(key);
          }
        })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

function isSameOrigin(url) {
  try {
    return new URL(url).origin === self.location.origin;
  } catch (e) {
    return false;
  }
}

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET' || !isSameOrigin(request.url)) {
    return;
  }
  var url = new URL(request.url);
  var path = url.pathname;

  // Static assets: cache-first (manifest, icon, sw.js)
  if (path === '/manifest.json' || path === '/icon.png' || path === '/sw.js') {
    event.respondWith(
      caches.open(STATIC_CACHE).then(function (cache) {
        return cache.match(request).then(function (cached) {
          return cached || fetch(request).then(function (response) {
            if (response.ok) cache.put(request, response.clone());
            return response;
          });
        });
      })
    );
    return;
  }

  // Video files: network-first, then cache (so played videos work offline)
  if (path.startsWith('/video/')) {
    event.respondWith(
      fetch(request).then(function (response) {
        if (response.ok) {
          var clone = response.clone();
          caches.open(MEDIA_CACHE).then(function (cache) { return cache.put(request, clone); });
        }
        return response;
      }).catch(function () {
        return caches.match(request).then(function (cached) {
          return cached || new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
        });
      })
    );
    return;
  }

  // HTML pages (/, /login, /signup, /playlist/*): network-first, cache fallback for offline
  if (request.mode === 'navigate' || (request.headers.get('accept') || '').indexOf('text/html') !== -1) {
    event.respondWith(
      fetch(request).then(function (response) {
        var clone = response.clone();
        if (response.ok && response.type === 'basic') {
          caches.open(PAGES_CACHE).then(function (cache) { return cache.put(request, clone); });
        }
        return response;
      }).catch(function () {
        return caches.match(request).then(function (cached) {
          if (cached) return cached;
          // Offline fallback: return a minimal "you're offline" page if nothing cached
          return caches.match('/login').then(function (loginPage) {
            return loginPage || new Response(
              '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title><style>body{font-family:sans-serif;background:#0f0f0f;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center;padding:20px;} a{color:#00e5ff;}</style></head><body><div><h1>You\'re offline</h1><p>This app works offline for pages you\'ve already opened.</p><p>Open the app again when you have internet to sync.</p><a href="/">Try again</a></div></body></html>',
              { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
            );
          });
        });
      })
    );
    return;
  }

  // Other same-origin GET: network-first with cache fallback
  event.respondWith(
    fetch(request).then(function (response) {
      if (response.ok && response.type === 'basic') {
        var clone = response.clone();
        caches.open(PAGES_CACHE).then(function (cache) { return cache.put(request, clone); });
      }
      return response;
    }).catch(function () {
      return caches.match(request);
    })
  );
});
