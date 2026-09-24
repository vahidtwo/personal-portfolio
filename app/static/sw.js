const VERSION = "inventory-v1";
const STATIC_CACHE = VERSION + "-static";
const PAGE_CACHE = VERSION + "-pages";

const PRECACHE = [
  "/offline.html",
  "/static/style.css",
  "/static/theme.js",
  "/static/privacy.js",
  "/static/dashboard.js",
  "/static/amount-input.js",
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

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
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

async function networkFirstDashboard(request) {
  const cache = await caches.open(PAGE_CACHE);
  try {
    const response = await fetch(request);
    if (response.redirected) {
      const finalUrl = new URL(response.url);
      if (finalUrl.pathname === "/login") {
        await caches.delete(PAGE_CACHE);
        return response;
      }
    }
    const type = response.headers.get("content-type") || "";
    if (response.ok && type.includes("text/html")) {
      await cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    const portfolio = await cache.match("/dashboard");
    if (portfolio) return portfolio;
    const daily = await cache.match("/dashboard?tab=daily");
    if (daily) return daily;
    const offline = await caches.match("/offline.html");
    if (offline) return offline;
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method === "POST" && url.origin === self.location.origin && url.pathname === "/logout") {
    event.respondWith(
      fetch(request, { redirect: "manual" }).then(async (response) => {
        if (response.status === 302 || response.status === 303 || response.type === "opaqueredirect") {
          await caches.delete(PAGE_CACHE);
        }
        return response;
      })
    );
    return;
  }

  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(cacheFirstStatic(request));
    return;
  }

  if (request.mode === "navigate" && isDashboard(url)) {
    event.respondWith(networkFirstDashboard(request));
    return;
  }

  if (request.mode === "navigate" || url.pathname === "/offline.html") {
    event.respondWith(
      fetch(request).catch(async () => {
        const offline = await caches.match("/offline.html");
        if (offline) return offline;
        return Response.error();
      })
    );
  }
});
