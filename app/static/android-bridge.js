(function () {
  if (!window.AndroidBridge || typeof AndroidBridge.isAndroidApp !== "function") return;
  document.documentElement.classList.add("in-android-app");
  document.querySelectorAll("#pwa-install, #pwa-install-landing").forEach(function (el) {
    el.hidden = true;
  });
  try {
    var origin = window.location.origin;
    if (origin && origin.startsWith("https://") && typeof AndroidBridge.setServerUrl === "function") {
      AndroidBridge.setServerUrl(origin);
    }
  } catch (e) {}
})();
