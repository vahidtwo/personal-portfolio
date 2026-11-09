// Loads a served /sw.js in a sandbox with a fake Firebase SDK (or a blocked one) and runs push scenarios.
// argv: swPath, JSON {origin, sdk: true|false, steps: [...]}. Prints JSON results.
"use strict";
const fs = require("fs");
const vm = require("vm");

const [, , swPath, scenarioJson] = process.argv;
const scenario = JSON.parse(scenarioJson);
const listeners = {};
const shown = [];
const opened = [];
let backgroundHandler = null;
let windows = (scenario.windows || []).map((w) => ({ ...w }));

const clients = {
  claim() {},
  async get() { return null; },
  async matchAll() {
    return windows.map((w) => ({
      url: w.url,
      async focus() { opened.push({ how: "focus", url: w.url }); return this; },
      async navigate(target) {
        if (!w.controlled) return null;
        opened.push({ how: "navigate", url: target });
        w.url = target;
        return this;
      },
    }));
  },
  async openWindow(target) { opened.push({ how: "open", url: target }); return {}; },
};

const sandbox = {
  self: {
    location: { origin: scenario.origin, href: scenario.origin + "/sw.js" },
    addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
    skipWaiting() {},
    clients,
    registration: {
      navigationPreload: { async enable() {}, async disable() {} },
      async showNotification(title, options) { shown.push({ title, body: options.body, data: options.data }); },
    },
  },
  importScripts() {
    if (!scenario.sdk) throw new Error("blocked");
  },
  firebase: {
    initializeApp() {},
    messaging() {
      sandbox.self.addEventListener("notificationclick", (event) => {
        if (event.notification.data && event.notification.data.FCM_MSG) opened.push({ how: "sdk-click" });
      });
      return { onBackgroundMessage(fn) { backgroundHandler = fn; } };
    },
  },
  caches: { async open() { return { async match() {}, async put() {}, async delete() {} }; }, async keys() { return []; }, async delete() {}, async match() {} },
  fetch: async () => { throw new TypeError("offline"); },
  Response, Headers, Request, URL, console, Number, Promise, String, Date, JSON, setTimeout,
};
sandbox.self.self = sandbox.self;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(swPath, "utf8"), sandbox);

function dispatch(type, event) {
  for (const fn of listeners[type] || []) {
    if (event._stopped) break;
    fn(event);
  }
}

(async () => {
  const results = [];
  for (const step of scenario.steps) {
    shown.length = 0;
    opened.length = 0;
    windows = (step.windows || []).map((w) => ({ ...w }));
    const waits = [];
    if (step.kind === "background") {
      if (backgroundHandler) await backgroundHandler(step.payload);
    } else if (step.kind === "push") {
      const event = { data: { json: () => step.payload }, waitUntil: (p) => waits.push(p) };
      dispatch("push", event);
    } else if (step.kind === "click") {
      const event = {
        notification: { data: step.data, close() {} },
        waitUntil: (p) => waits.push(p),
        stopImmediatePropagation() { this._stopped = true; },
      };
      dispatch("notificationclick", event);
    }
    await Promise.all(waits);
    results.push({ waited: waits.length, shown: shown.map((x) => ({ ...x })), opened: opened.map((x) => ({ ...x })) });
  }
  console.log(JSON.stringify({ listeners: Object.fromEntries(Object.entries(listeners).map(([k, v]) => [k, v.length])), hasBackground: !!backgroundHandler, results }));
})().catch((e) => { console.error(e); process.exit(1); });
