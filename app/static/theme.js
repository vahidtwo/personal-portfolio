/* Theme per device (localStorage "inventory-theme": "dark" | "light"; no key = «خودکار», follow the OS).
   No server state. window.inventoryTheme lets the settings page read/set the choice. */
(function () {
  const STORAGE_KEY = "inventory-theme";
  const NAME = { dark: "تیره", light: "روشن" };
  const root = document.documentElement;
  const meta = document.getElementById("meta-theme-color");
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  const listeners = [];

  function stored() {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      return v === "dark" || v === "light" ? v : null;
    } catch (e) { return null; }
  }
  function system() { return media && media.matches ? "light" : "dark"; }
  function choice() { return stored() || "auto"; }
  function effective() { return stored() || system(); }

  function labelToggle() {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    const now = effective();
    const next = now === "dark" ? "light" : "dark";
    btn.setAttribute("aria-label", "پوسته: " + NAME[now] + ". تغییر به " + NAME[next]);
  }

  function apply() {
    const theme = effective();
    root.setAttribute("data-theme", theme);
    if (meta) meta.setAttribute("content", theme === "light" ? "#eef1f8" : "#050608");
    labelToggle();
    listeners.forEach(function (fn) { try { fn(choice(), theme); } catch (e) {} });
  }

  function set(value) {
    try {
      if (value === "auto") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, value === "light" ? "light" : "dark");
    } catch (e) {}
    apply();
  }

  // «خودکار»: follow an OS theme change without a reload.
  if (media) {
    const onChange = function () { if (!stored()) apply(); };
    if (media.addEventListener) media.addEventListener("change", onChange);
    else if (media.addListener) media.addListener(onChange);
  }
  window.inventoryTheme = { NAME: NAME, choice: choice, effective: effective, set: set,
    onChange: function (fn) { listeners.push(fn); } };
  apply();

  document.addEventListener("DOMContentLoaded", function () {
    labelToggle();
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      set(effective() === "dark" ? "light" : "dark");
    });
  });
})();
