const VERSION = "inventory-v__STATIC_ASSET_VERSION__";
const STATIC_CACHE = VERSION + "-static";
const PAGE_CACHE = VERSION + "-pages-v2"; // v2: offline copy needs the signed-in marker (batch 1)
// The offline copy of the dashboard is private data: it must not outlive the session cookie.
// Each stored copy carries the time it was stored (CACHED_AT_HEADER); older than this = deleted, not served.
const SESSION_MAX_AGE_MS = Number("__SESSION_MAX_AGE_MS__") || 30 * 24 * 60 * 60 * 1000;
const CACHED_AT_HEADER = "x-inventory-cached-at";
// Readable marker the server keeps next to the HttpOnly session cookie (app/session_marker.py): same
// lifetime, removed on logout/expiry. No marker (or no way to read it) = no valid session = no offline copy.
const SESSION_MARKER_COOKIE = "inventory_signed_in";

async function hasSessionMarker() {
  try {
    if (!self.cookieStore || typeof self.cookieStore.get !== "function") return false;
    const c = await self.cookieStore.get(SESSION_MARKER_COOKIE);
    return Boolean(c && c.value === "1");
  } catch (e) {
    return false;
  }
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
      .then(() => self.clients.claim())
  );
});

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

function clearPrivatePages() {
  return caches.delete(PAGE_CACHE);
}

// The session is over (or never was): 401/403, or the server sent us to the login page.
function isSessionEnd(response) {
  if (!response) return false;
  if (response.status === 401 || response.status === 403) return true;
  if (response.redirected) {
    try {
      if (new URL(response.url).pathname === "/login") return true;
    } catch (e) {}
  }
  return false;
}

function isLoginUrl(url) {
  return url.origin === self.location.origin && url.pathname === "/login";
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

async function networkFirstDashboard(request) {
  const cache = await caches.open(PAGE_CACHE);
  let response;
  try {
    response = await fetch(request);
  } catch (err) {
    if (!(await hasSessionMarker())) {
      // Offline and no valid session: the private copy is deleted, never shown.
      await clearPrivatePages();
      const offline = await caches.match("/offline.html");
      if (offline) return offline;
      throw err;
    }
    const now = Date.now();
    const page =
      (await freshCachedPage(cache, request, now)) ||
      (await freshCachedPage(cache, "/dashboard", now)) ||
      (await freshCachedPage(cache, "/dashboard?tab=daily", now));
    if (page) return page;
    const offline = await caches.match("/offline.html");
    if (offline) return offline;
    throw err;
  }
  // /dashboard only redirects when there is no valid session (to /login). A navigation fetch does not
  // follow redirects ("opaqueredirect"), so any redirect here also ends the offline copy.
  if (isSessionEnd(response) || response.type === "opaqueredirect" || (response.status >= 300 && response.status < 400)) {
    await clearPrivatePages();
    return response;
  }
  const type = response.headers.get("content-type") || "";
  if (response.ok && type.includes("text/html") && (await hasSessionMarker())) {
    await cache.put(request, await withCachedAt(response, Date.now()));
  }
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
    event.respondWith(clearPrivatePages().then(() => fetch(request)).catch(async () => {
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
    event.respondWith(networkFirstDashboard(request));
    return;
  }

  if (request.mode === "navigate" || url.pathname === "/offline.html") {
    event.respondWith(
      fetch(request)
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
