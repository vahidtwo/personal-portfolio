// Minimal service-worker sandbox for tests: loads app/static/sw.js with fake caches/fetch and runs a
// scenario given as JSON on argv[2]. Prints a JSON result. Node >= 18 (global Response/Headers).
"use strict";
const fs = require("fs");
const vm = require("vm");

const [, , swPath, scenarioJson] = process.argv;
const scenario = JSON.parse(scenarioJson);
const MAX_AGE_MS = scenario.maxAgeMs || 1000;

function makeCaches() {
  const stores = new Map();
  const keyOf = (k) => (typeof k === "string" ? new URL(k, "https://app.test").href : k.url);
  function store(name) {
    if (!stores.has(name)) {
      const m = new Map();
      stores.set(name, {
        async match(k) { const r = m.get(keyOf(k)); return r ? r.clone() : undefined; },
        async put(k, r) { m.set(keyOf(k), r.clone()); },
        async delete(k) { return m.delete(keyOf(k)); },
        async add() {},
        _keys: () => [...m.keys()],
      });
    }
    return stores.get(name);
  }
  return {
    async open(name) { return store(name); },
    async delete(name) { return stores.delete(name); },
    async has(name) { return stores.has(name); },
    async keys() { return [...stores.keys()]; },
    async match(k) { for (const s of stores.values()) { const r = await s.match(k); if (r) return r; } return undefined; },
    _stores: stores,
  };
}

const listeners = {};
const messages = [];
let preloadEnabled = false;
const DEFAULT_ID = "uTESTUSERaaaa0001";
let clock = scenario.start || 1_000_000;
let network = null; // function(request) -> Response | throws
let preload = null; // navigation preload response factory (step.preload)
const caches = makeCaches();
const sandbox = {
  self: {
    location: { origin: "https://app.test" },
    addEventListener: (t, f) => (listeners[t] = f),
    skipWaiting() {},
    clients: { claim() {}, async get(id) { return { postMessage: (m) => messages.push({ to: id, ...m }) }; } },
    registration: { navigationPreload: { async enable() { preloadEnabled = true; } } },
  },
  caches,
  fetch: async (req) => { if (!network) throw new TypeError("offline"); return network(req); },
  Response, Headers, Request, URL, console, Number, Promise, String,
  Date: { now: () => clock },
};
sandbox.self.caches = caches;
// Fake cookieStore: the readable signed-in marker (scenario.marker / step.marker toggles it).
// marker: true = default user id, a string = that user id, false = signed out, "1" = old v10 marker.
let marker = scenario.marker === undefined ? true : scenario.marker;
const markerValue = () => (marker === true ? DEFAULT_ID : marker);
if (scenario.cookieStore !== false) {
  sandbox.self.cookieStore = { async get(name) { return name === "inventory_signed_in" && marker ? { name, value: markerValue() } : null; } };
}
let src = fs.readFileSync(swPath, "utf8")
  .replace(/__STATIC_ASSET_VERSION__/g, "test")
  .replace("__SESSION_MAX_AGE_MS__", String(MAX_AGE_MS));
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

function html(body, status = 200, extra = {}) {
  const r = new Response(body, { status, headers: { "content-type": "text/html; charset=utf-8" } });
  for (const [k, v] of Object.entries(extra)) Object.defineProperty(r, k, { value: v });
  return r;
}

async function dispatch(path, { method = "GET", mode = "navigate" } = {}) {
  const url = new URL(path, "https://app.test").href;
  const request = { url, method, mode, clone() { return this; } };
  let responded = null;
  const waits = [];
  const preloadResponse = Promise.resolve(preload ? preload(request) : undefined);
  listeners.fetch({ request, resultingClientId: "client-" + path, respondWith: (p) => (responded = p), waitUntil: (p) => waits.push(p), preloadResponse });
  if (!responded) return { handled: false };
  try {
    const res = await responded;
    await Promise.all(waits);
    return { handled: true, status: res.status, type: res.type, body: res.status === 0 ? "" : await res.clone().text() };
  } catch (e) {
    return { handled: true, error: String(e) };
  }
}

async function pageKeys() {
  const out = [];
  for (const [name, s] of caches._stores) if (name.includes("-pages-")) for (const k of s._keys()) out.push(k);
  return out;
}
const pageStores = () => [...caches._stores.keys()].filter((n) => n.includes("-pages-"));

(async () => {
  const out = [];
  for (const step of scenario.steps) {
    if (step.advance) clock += step.advance;
    if (step.marker !== undefined) marker = step.marker;
    if (step.online === false) network = null;
    if (step.online === "ok") network = () => html(step.body || "<p>dashboard private</p>");
    if (step.online === "status") network = () => html("nope", step.status);
    if (step.online === "redirect-login") network = () => html("<p>login</p>", 200, { redirected: true, url: "https://app.test/login" });
    if (step.online === "opaqueredirect") network = () => { const r = new Response(null, { status: 200 }); Object.defineProperty(r, "type", { value: "opaqueredirect" }); Object.defineProperty(r, "status", { value: 0 }); return r; };
    if (step.online === "login-page") network = () => html("<p>login</p>");
    if (step.preload !== undefined) preload = step.preload ? () => html(step.preload) : null;
    if (step.activate) { let ap; listeners.activate({ waitUntil: (p) => (ap = p) }); await ap; }
    if (step.offline_html) await (await caches.open("inventory-vtest-static")).put("/offline.html", html("<p>offline page</p>"));
    if (step.go) {
      const r = await dispatch(step.go, step.opts || {});
      out.push({ go: step.go, ...r, pages: await pageKeys(), stores: pageStores(), messages: messages.splice(0) });
    }
  }
  out.push({ preloadEnabled });
  console.log(JSON.stringify(out));
})();
