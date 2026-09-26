(function () {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  const installBtn = document.getElementById("pwa-install");
  const installLanding = document.getElementById("pwa-install-landing");
  const iosHint = document.getElementById("pwa-ios");
  const offlineBanner = document.getElementById("pwa-offline");
  const retryBtn = document.getElementById("pwa-retry");
  const standalone =
    window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;

  let deferredPrompt = null;

  function showInstallButtons(show) {
    if (installBtn) installBtn.hidden = !show;
    if (installLanding) installLanding.hidden = !show;
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    if (standalone) return;
    deferredPrompt = event;
    showInstallButtons(true);
  });

  function promptInstall() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.finally(function () {
      deferredPrompt = null;
      showInstallButtons(false);
    });
  }

  if (installBtn) installBtn.addEventListener("click", promptInstall);
  if (installLanding) installLanding.addEventListener("click", promptInstall);

  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    showInstallButtons(false);
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

  function showOfflineToast() {
    let toast = document.getElementById("pwa-offline-toast");
    if (!toast) {
      toast = document.createElement("p");
      toast.id = "pwa-offline-toast";
      toast.className = "toast toast-warn pwa-offline-toast";
      toast.setAttribute("role", "alert");
      document.body.appendChild(toast);
    }
    toast.textContent = "ذخیره نشد — اتصال نیست.";
    toast.hidden = false;
    clearTimeout(showOfflineToast._t);
    showOfflineToast._t = setTimeout(function () {
      toast.hidden = true;
    }, 4000);
  }

  function syncOffline() {
    const offline = !navigator.onLine;
    if (offlineBanner) offlineBanner.hidden = !offline;
  }

  if (retryBtn) {
    retryBtn.addEventListener("click", function () {
      if (navigator.onLine) location.reload();
      else showOfflineToast();
    });
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
      showOfflineToast();
    },
    true
  );
})();
