(function () {
  const STORAGE_KEY = "inventory-theme";
  const root = document.documentElement;
  const meta = document.getElementById("meta-theme-color");

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    if (meta) {
      meta.setAttribute("content", theme === "light" ? "#eef1f8" : "#050608");
    }
  }

  const saved = localStorage.getItem(STORAGE_KEY);
  const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
  apply(saved || (prefersLight ? "light" : "dark"));

  document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      apply(next);
    });
  });
})();
