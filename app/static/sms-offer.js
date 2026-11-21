// v7 spending page: one-time offer to record spends from SMS (Android app only, v6 spec state 2).
// One-line banner, shown only when the app reports the feature is off; ✕ hides it for good (stored on this device).
(function () {
  "use strict";
  var KEY = "inventory-sms-offer-dismissed";
  var card = document.getElementById("sms-offer");
  if (!card) return;
  var bridge = window.AndroidBridge;
  if (!bridge || typeof bridge.getSmsAutoState !== "function" || typeof bridge.openSmsSettings !== "function") return;
  try {
    if (localStorage.getItem(KEY) === "1") return;
    if (bridge.getSmsAutoState() !== "off") return;
  } catch (e) {
    return;
  }
  function dismiss() {
    try { localStorage.setItem(KEY, "1"); } catch (e) {}
    card.hidden = true;
  }
  card.hidden = false;
  card.querySelector("[data-sms-offer-enable]").addEventListener("click", function () {
    try { bridge.openSmsSettings(); } catch (e) {}
  });
  card.querySelectorAll("[data-sms-offer-dismiss]").forEach(function (btn) {
    btn.addEventListener("click", dismiss);
  });
})();
