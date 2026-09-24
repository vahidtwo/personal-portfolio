(function () {
  if (!("serviceWorker" in navigator)) return;

  navigator.serviceWorker.register("/sw.js").catch(function () {});

  const installBtn = document.getElementById("pwa-install");
  const iosHint = document.getElementById("pwa-ios");
  const offlineBanner = document.getElementById("pwa-offline");
  const standalone =
    window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;

  let deferredPrompt = null;

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    if (standalone) return;
    deferredPrompt = event;
    if (installBtn) installBtn.hidden = false;
  });

  if (installBtn) {
    installBtn.addEventListener("click", function () {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        deferredPrompt = null;
        installBtn.hidden = true;
      });
    });
  }

  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    if (installBtn) installBtn.hidden = true;
    if (iosHint) iosHint.hidden = true;
  });

  const ios =
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (ios && !standalone && iosHint && localStorage.getItem("pwa-ios-hint") !== "1") {
    iosHint.hidden = false;
    const dismiss = iosHint.querySelector("[data-pwa-ios-dismiss]");
    if (dismiss) {
      dismiss.addEventListener("click", function () {
        iosHint.hidden = true;
        try {
          localStorage.setItem("pwa-ios-hint", "1");
        } catch (e) {}
      });
    }
  }

  function syncOffline() {
    const offline = !navigator.onLine;
    if (offlineBanner) offlineBanner.hidden = !offline;
  }

  window.addEventListener("online", syncOffline);
  window.addEventListener("offline", syncOffline);
  syncOffline();

  document.addEventListener(
    "submit",
    function (event) {
      if (navigator.onLine) return;
      event.preventDefault();
      syncOffline();
    },
    true
  );
})();
