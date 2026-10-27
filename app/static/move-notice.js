// One-time notice on the OLD host (portfolio.vahidtwo.ir) about the move to daraiito.ir.
// Only rendered for signed-in users on the old host (server check); this file checks the host again.
// Never shown inside the Android app: installed apps can't navigate to the new host (v9 moves them itself).
// Dismissal is per device (localStorage "move-notice-seen"). "privacy-portfolio" is only READ, never renamed or written here.
(function () {
  var OLD_HOST = "portfolio.vahidtwo.ir";
  var SEEN_KEY = "move-notice-seen";
  var box = document.getElementById("move-notice");
  if (!box) return;
  if (location.hostname !== OLD_HOST) return;
  if (window.AndroidBridge || document.documentElement.classList.contains("in-android-app")) return;
  try {
    if (localStorage.getItem(SEEN_KEY) === "1") return;
  } catch (e) {
    return; // can't remember a dismissal, so don't nag on every page
  }
  var base = (box.getAttribute("data-new-url") || "https://daraiito.ir").replace(/\/+$/, "");
  var hidden = false;
  try {
    hidden = localStorage.getItem("privacy-portfolio") === "1";
  } catch (e) {}
  var go = document.getElementById("move-notice-go");
  if (go) go.setAttribute("href", base + "/" + (hidden ? "#hide=1" : ""));
  var dismiss = box.querySelector("[data-move-notice-dismiss]");
  if (dismiss) {
    dismiss.addEventListener("click", function () {
      try {
        localStorage.setItem(SEEN_KEY, "1");
      } catch (e) {}
      box.hidden = true;
    });
  }
  box.hidden = false;
})();
