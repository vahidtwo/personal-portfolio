// Runs static/push.js against a fake page, browser and Firebase SDK, clicks "enable" and prints the outcome.
// argv: pushJsPath, JSON scenario. Prints JSON {status, code, error, requests, tokenOptions}.
"use strict";
const fs = require("fs");
const vm = require("vm");

const [, , pushPath, scenarioJson] = process.argv;
const sc = JSON.parse(scenarioJson);
const requests = [];
let tokenOptions = null;

function makeEl(tag) {
  const el = {
    tagName: tag, _text: "", children: [], hidden: true, className: "", dir: "", listeners: {},
    classList: {
      set: new Set(),
      toggle(name, on) { if (on) this.set.add(name); else this.set.delete(name); },
      contains(name) { return this.set.has(name); },
    },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); },
    set textContent(v) { this._text = String(v); this.children = []; },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
  };
  return el;
}

const els = {
  "firebase-config": Object.assign(makeEl("script"), { _text: sc.configText !== undefined ? sc.configText : '{"apiKey":"AIzaFake","projectId":"fake-project","messagingSenderId":"1","appId":"1:1:web:1"}' }),
  "push-enable": makeEl("button"),
  "push-status": makeEl("p"),
  "push-settings": makeEl("section"),
};

const fakeMessaging = {
  onMessage() {},
  async getToken(options) {
    tokenOptions = { hasRegistration: !!options.serviceWorkerRegistration, vapidKey: options.vapidKey || null };
    const t = sc.token === undefined ? "ok" : sc.token;
    if (t === "ok") return "fake-web-token";
    if (t === "empty") return "";
    const e = new Error(t.message || "failed");
    if (t.code) e.code = t.code;
    if (t.name) e.name = t.name;
    throw e;
  },
};

const win = {};
const sdk = sc.sdk || "ok";
const doc = {
  getElementById: (id) => els[id] || null,
  querySelector: () => null,
  createElement: (tag) => makeEl(tag),
  createTextNode: (t) => ({ textContent: String(t) }),
  head: {
    appendChild(script) {
      setTimeout(() => {
        if (sdk === "fail") { script.onerror(); return; }
        if (sdk === "ok") win.firebase = { apps: [], initializeApp() { this.apps.push({}); }, messaging: () => fakeMessaging };
        script.onload();
      }, 0);
    },
  },
};

function response(status, body, json = true) {
  return {
    ok: status >= 200 && status < 300, status,
    async json() { if (!json) throw new SyntaxError("Unexpected token <"); return body; },
  };
}

async function fakeFetch(url, opts = {}) {
  requests.push({ url, method: opts.method || "GET", credentials: opts.credentials || null,
    contentType: (opts.headers || {})["Content-Type"] || null, body: opts.body ? JSON.parse(opts.body) : null });
  if (url === "/api/push/status") return response(200, { ok: true, server: true, devices: {} });
  if (url === "/api/push/config") {
    const c = sc.configFetch || "ok";
    if (c === "network") throw new TypeError("Failed to fetch");
    if (c === "http500") return response(500, {}, false);
    return response(200, { enabled: c !== "disabled", vapidKey: sc.noVapid ? null : "BFakeVapidKey" });
  }
  if (url === "/api/push/register") {
    const r = sc.register || { status: 200, body: { ok: true } };
    if (r === "network") throw new TypeError("Failed to fetch");
    if (r === "html500") return response(500, null, false);
    return response(r.status, r.body);
  }
  return response(404, {}, false);
}

let permission = sc.initialPermission || "default";
const Notification = function () {};
Notification.requestPermission = () => {
  if (sc.permission === "throw") throw new Error("not allowed");
  permission = sc.permission || "granted";
  return Promise.resolve(permission);
};
Object.defineProperty(Notification, "permission", { get: () => permission });

const registration = { scope: "https://daraiito.ir/" };
const navigatorObj = {};
if (!sc.noServiceWorker) {
  navigatorObj.serviceWorker = {
    register: async (url, opts) => {
      requests.push({ url: "sw:" + url, method: "REGISTER", updateViaCache: opts && opts.updateViaCache });
      if (sc.swRegister === "fail") { const e = new Error("The script has an unsupported MIME type ('text/html')."); e.name = "SecurityError"; throw e; }
      return registration;
    },
    ready: sc.swReady === "hang" ? new Promise(() => {}) : Promise.resolve(registration),
  };
}

Object.assign(win, {
  Notification, isSecureContext: !sc.insecure, location: { origin: "https://daraiito.ir" },
  console: { error() {}, warn() {}, log() {} },
});
if (!sc.noPushManager) win.PushManager = function () {};
const sandbox = Object.assign(win, {
  window: win, document: doc, navigator: navigatorObj, fetch: fakeFetch,
  setTimeout: (f, ms) => setTimeout(f, Math.min(ms || 0, 5)), clearTimeout, setInterval, clearInterval,
  Promise, JSON, String, Error, TypeError, URL,
});
win.window = win;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(pushPath, "utf8"), sandbox);

(async () => {
  await new Promise((r) => setTimeout(r, 10));
  for (const f of els["push-enable"].listeners.click || []) f({});
  const st = els["push-status"];
  for (let i = 0; i < 200 && st._text === "در حال فعال‌سازی…"; i++) await new Promise((r) => setTimeout(r, 5));
  await new Promise((r) => setTimeout(r, 20));
  const small = st.children.find((c) => c.tagName === "small");
  process.stdout.write(JSON.stringify({
    status: st._text, code: small ? small.textContent : null, codeDir: small ? small.dir : null,
    error: st.classList.contains("toast-warn"), hidden: st.hidden, clickBound: (els["push-enable"].listeners.click || []).length,
    requests, tokenOptions,
  }));
})();
