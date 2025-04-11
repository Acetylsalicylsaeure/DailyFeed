/**
 * Service Worker for basic offline support
 */
const CACHE_NAME = 'rss-aggregator-v1';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/styles/main.css',
    '/js/app.js',
    '/js/api.js',
    '/js/feed.js',
    '/js/settings.js'
];

// Install event - cache static assets
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.filter(cacheName => {
                    return cacheName !== CACHE_NAME;
                }).map(cacheName => {
                    return caches.delete(cacheName);
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch event - serve from cache if available, otherwise fetch from network
self.addEventListener('fetch', event => {
    // Only cache GET requests
    if (event.request.method !== 'GET') return;
    
    // Skip caching API requests
    if (event.request.url.includes('/api/')) {
        return;
    }
    
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Return cached response if found
                if (response) {
                    return response;
                }
                
                // Clone the request - request can only be used once
                const fetchRequest = event.request.clone();
                
                // Make network request
                return fetch(fetchRequest).then(response => {
                    // Check if valid response
                    if (!response || response.status !== 200 || response.type !== 'basic') {
                        return response;
                    }
                    
                    // Clone the response - response can only be used once
                    const responseToCache = response.clone();
                    
                    // Cache the fetched response
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseToCache);
                    });
                    
                    return response;
                });
            })
            .catch(error => {
                // For navigation requests, return the offline page
                if (event.request.mode === 'navigate') {
                    return caches.match('/index.html');
                }
                
                // Otherwise just propagate the error
                throw error;
            })
    );
});
