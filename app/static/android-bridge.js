(function () {
  if (!window.AndroidBridge || typeof AndroidBridge.isAndroidApp !== "function") return;
  document.documentElement.classList.add("in-android-app");
  const install = document.getElementById("pwa-install");
  if (install) install.hidden = true;
  // Do NOT call the setServerUrl bridge method from web pages. In the app,
  // setServerUrl navigates to /dashboard, so calling it on every page load
  // causes a reload loop (landing -> /dashboard -> landing ...). The app
  // already saves the server address itself in onPageFinished.
})();
