const VERSION = "inventory-v__STATIC_ASSET_VERSION__";
const STATIC_CACHE = VERSION + "-static";
// v3 (v11): one page cache per signed-in user, named by the marker's per-user id (never shared).
const PAGE_CACHE_PREFIX = VERSION + "-pages-v3-";
const PAGES_MARK = "-pages-";
// The offline copy of the dashboard is private data: it must not outlive the session cookie.
// Each stored copy carries the time it was stored (CACHED_AT_HEADER); older than this = deleted, not served.
const SESSION_MAX_AGE_MS = Number("__SESSION_MAX_AGE_MS__") || 30 * 24 * 60 * 60 * 1000;
const CACHED_AT_HEADER = "x-inventory-cached-at";
// Readable marker the server keeps next to the HttpOnly session cookie (app/session_marker.py): same
// lifetime, removed on logout/expiry. It stays "1" (the Android SMS sender needs that); v11 adds
// inventory_page_key, a non-secret per-user id ("u" + signed hash of the user id), so a cached page is
// only ever served to the account that stored it. Both must be present to use any cached page.
// No marker (or no way to read it) = no valid session = no cached private page.
const SESSION_MARKER_COOKIE = "inventory_signed_in";
const PAGE_KEY_COOKIE = "inventory_page_key";
const MARKER_ID_RE = /^u[A-Za-z0-9_-]{8,64}$/;
// A cached dashboard is shown first (fast start) while a fresh copy is fetched in the background.
// Older than this = too stale to show first: wait for the network (still used as the offline copy).
const SHOW_FIRST_MAX_AGE_MS = 12 * 60 * 60 * 1000;

async function sessionId() {
  try {
    if (!self.cookieStore || typeof self.cookieStore.get !== "function") return null;
    const m = await self.cookieStore.get(SESSION_MARKER_COOKIE);
    if (!m || m.value !== "1") return null;
    const c = await self.cookieStore.get(PAGE_KEY_COOKIE);
    const v = c && c.value;
    return typeof v === "string" && MARKER_ID_RE.test(v) ? v : null;
  } catch (e) {
    return null;
  }
}

async function hasSessionMarker() {
  return Boolean(await sessionId());
}

function pageCacheName(id) {
  return PAGE_CACHE_PREFIX + id;
}

const PRECACHE = [
  "/offline.html",
  "/static/style.css",
  "/static/theme.js",
  "/static/privacy.js",
  "/static/number-format.js",
  "/static/dashboard.js",
  "/static/amount-input.js",
  "/static/leave-guard.js",
  "/static/table-sort.js",
  "/static/pwa.js",
  "/static/logo.svg",
  "/static/favicon.ico",
  "/static/icons/favicon-16.png",
  "/static/icons/favicon-32.png",
  "/static/brand/daraiito-symbol-dark.svg",
  "/static/brand/daraiito-symbol-light.svg",
  "/static/icons/apple-touch-icon.png",
  "/static/vendor/chart.umd.min.js",
  "/static/vendor/hammer.min.js",
  "/static/vendor/chartjs-plugin-zoom.min.js",
  "/static/fonts/vazirmatn-arabic.woff2",
  "/static/fonts/vazirmatn-latin.woff2",
  "/static/fonts/vazirmatn-latin-ext.woff2",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-512.png",
  "/static/logos/section-report.svg",
  "/static/logos/section-income.svg",
  "/static/logos/section-expense.svg",
  "/static/logos/section-debts.svg",
  "/static/logos/section-assets.svg",
  "/static/logos/car.svg",
  "/static/logos/cash.svg",
  "/static/logos/usd.svg",
  "/static/logos/coin_gram.svg",
  "/static/logos/coin_quarter.svg",
  "/static/logos/coin_half.svg",
  "/static/logos/coin_bahar.svg",
  "/static/logos/coin_emami.svg",
  "/static/logos/silver.svg",
  "/static/logos/gold.svg",
  "/static/logos/matic.svg",
  "/static/logos/doge.svg",
  "/static/logos/ada.svg",
  "/static/logos/sol.svg",
  "/static/logos/eth.svg",
  "/static/logos/btc.svg",
  "/static/onboarding/chart.svg",
  "/static/onboarding/dashboard.svg",
];

function bypassServiceWorker(url) {
  if (url.pathname === "/download/my-inventory.apk") return true;
  if (url.pathname.endsWith(".apk")) return true;
  // Private salary figure: never cached, never served offline.
  if (url.pathname === "/api/salary") return true;
  return false;
}

function isMutableStatic(pathname) {
  return pathname.endsWith(".js") || pathname.endsWith(".css");
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then(async (cache) => {
        await Promise.all(
          PRECACHE.map(async (path) => {
            try {
              await cache.add(path);
            } catch (err) {
              console.warn("precache skip", path, err);
            }
          })
        );
      })
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => !key.startsWith(VERSION)).map((key) => caches.delete(key)))
      )
      .then(() => enableNavigationPreload())
      .then(() => self.clients.claim())
  );
});

// Navigation preload: the /dashboard request starts while this worker is still booting (v11 startup).
async function enableNavigationPreload() {
  try {
    if (self.registration && self.registration.navigationPreload) await self.registration.navigationPreload.enable();
  } catch (e) {}
}

// The preloaded response if the browser made one, else a normal fetch.
async function navigationResponse(event) {
  try {
    const pre = await event.preloadResponse;
    if (pre) return pre;
  } catch (e) {}
  return fetch(event.request);
}

function isDashboard(url) {
  if (url.origin !== self.location.origin || url.pathname !== "/dashboard") return false;
  const tab = url.searchParams.get("tab");
  return tab === null || tab === "portfolio" || tab === "daily";
}

async function cacheFirstStatic(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function networkFirstStatic(request) {
  const cache = await caches.open(STATIC_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw err;
  }
}

// Every user's cached private pages (logout, 401/403, redirect to login, no session).
async function clearPrivatePages() {
  const keys = await caches.keys();
  await Promise.all(keys.filter((k) => k.includes(PAGES_MARK)).map((k) => caches.delete(k)));
}

// Account switch: only the signed-in user's page cache may exist.
async function dropOtherUsersPages(id) {
  const keep = pageCacheName(id);
  const keys = await caches.keys();
  await Promise.all(keys.filter((k) => k.includes(PAGES_MARK) && k !== keep).map((k) => caches.delete(k)));
}

async function tellClient(clientId, message) {
  try {
    const client = clientId && (await self.clients.get(clientId));
    if (client) client.postMessage(message);
  } catch (e) {}
}

// The session is over (or never was): 401/403, or the server sent us to the login page.
function isSessionEnd(response) {
  if (!response) return false;
  if (response.status === 401 || response.status === 403) return true;
  if (response.redirected) {
    try {
      if (["/login", "/auth"].includes(new URL(response.url).pathname)) return true;
    } catch (e) {}
  }
  return false;
}

function isLoginUrl(url) {
  return url.origin === self.location.origin && (url.pathname === "/login" || url.pathname === "/auth");
}

async function withCachedAt(response, now) {
  const headers = new Headers(response.headers);
  headers.set(CACHED_AT_HEADER, String(now));
  const body = await response.clone().arrayBuffer();
  return new Response(body, { status: response.status, statusText: response.statusText, headers });
}

function isFresh(response, now) {
  const stamp = Number(response.headers.get(CACHED_AT_HEADER));
  if (!stamp || !Number.isFinite(stamp)) return false; // a copy without a timestamp is never trusted
  return now - stamp >= 0 && now - stamp < SESSION_MAX_AGE_MS;
}

// A cached private page that is still within the session lifetime, or null (an expired one is deleted).
async function freshCachedPage(cache, key, now) {
  const cached = await cache.match(key);
  if (!cached) return null;
  if (isFresh(cached, now)) return cached;
  await cache.delete(key);
  return null;
}

function cachedAt(response) {
  return Number(response.headers.get(CACHED_AT_HEADER)) || 0;
}

// Stores a good signed-in dashboard response for this user; ends every private copy when the session is over.
// Returns "stored" | "ended" | "skip".
async function storeDashboard(request, response, id) {
  if (isSessionEnd(response) || response.type === "opaqueredirect" || (response.status >= 300 && response.status < 400)) {
    await clearPrivatePages();
    return "ended";
  }
  const type = response.headers.get("content-type") || "";
  // The account may have changed while the request was in flight: store only under the current id.
  if (response.ok && type.includes("text/html") && id && (await sessionId()) === id) {
    const cache = await caches.open(pageCacheName(id));
    await cache.put(request, await withCachedAt(response, Date.now()));
    return "stored";
  }
  return "skip";
}

// v11: stale-while-revalidate for the signed-in dashboard. A fresh-enough copy of THIS user's page is shown at
// once; the network copy (navigation preload) replaces it in the cache, and the page is told so it can refresh
// quietly (pwa.js) or show it on the next open. No marker = no cache at all (network only, copies deleted).
async function dashboardNavigation(event) {
  const request = event.request;
  const id = await sessionId();
  if (!id) {
    await clearPrivatePages();
    try {
      return await navigationResponse(event);
    } catch (err) {
      const offline = await caches.match("/offline.html");
      if (offline) return offline;
      throw err;
    }
  }
  await dropOtherUsersPages(id);
  const cache = await caches.open(pageCacheName(id));
  const now = Date.now();
  const network = navigationResponse(event);
  const cached = await freshCachedPage(cache, request, now);
  if (cached && now - cachedAt(cached) < SHOW_FIRST_MAX_AGE_MS) {
    const clientId = event.resultingClientId || event.clientId;
    event.waitUntil(
      network
        .then(async (response) => {
          const r = await storeDashboard(request, response, id);
          if (r === "ended") await tellClient(clientId, { type: "inventory-session-ended" });
          else if (r === "stored") await tellClient(clientId, { type: "inventory-dashboard-refreshed", age: now - cachedAt(cached) });
        })
        .catch(() => {})
    );
    return cached;
  }
  let response;
  try {
    response = await network;
  } catch (err) {
    const page =
      cached ||
      (await freshCachedPage(cache, "/dashboard", now)) ||
      (await freshCachedPage(cache, "/dashboard?tab=daily", now));
    if (page) return page;
    const offline = await caches.match("/offline.html");
    if (offline) return offline;
    throw err;
  }
  await storeDashboard(request, response, id);
  return response;
}

// Any other same-origin request: pass through, but a 401/403 or a redirect to /login ends the offline copy.
async function watchSession(request) {
  const response = await fetch(request);
  if (isSessionEnd(response)) await clearPrivatePages();
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method === "POST" && url.origin === self.location.origin && url.pathname === "/logout") {
    event.respondWith(
      fetch(request, { redirect: "manual" }).then(async (response) => {
        if (response.status === 302 || response.status === 303 || response.type === "opaqueredirect") {
          await clearPrivatePages();
        }
        return response;
      })
    );
    return;
  }

  if (url.origin !== self.location.origin) return;

  if (request.method !== "GET") {
    // Form POSTs are left to the browser (an expired session redirects them to /login, handled below).
    if (url.pathname.startsWith("/api/")) event.respondWith(watchSession(request));
    return;
  }

  if (bypassServiceWorker(url)) return;

  // Reaching the login page means there is no session (logged out, expired or never logged in).
  if (request.mode === "navigate" && isLoginUrl(url)) {
    event.respondWith(clearPrivatePages().then(() => navigationResponse(event)).catch(async () => {
      const offline = await caches.match("/offline.html");
      return offline || Response.error();
    }));
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    if (isMutableStatic(url.pathname)) {
      event.respondWith(networkFirstStatic(request));
    } else {
      event.respondWith(cacheFirstStatic(request));
    }
    return;
  }

  if (request.mode === "navigate" && isDashboard(url)) {
    event.respondWith(dashboardNavigation(event));
    return;
  }

  if (request.mode === "navigate" || url.pathname === "/offline.html") {
    event.respondWith(
      (request.mode === "navigate" ? navigationResponse(event) : fetch(request))
        .then(async (response) => {
          if (isSessionEnd(response)) await clearPrivatePages();
          return response;
        })
        .catch(async () => {
          const offline = await caches.match("/offline.html");
          if (offline) return offline;
          return Response.error();
        })
    );
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(watchSession(request));
  }
});
