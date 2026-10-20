(function () {
  var keys = { portfolio: "privacy-portfolio" };
  var showAttr = { portfolio: "showPortfolio" };

  function isHidden(kind) {
    try {
      return localStorage.getItem(keys[kind]) === "1";
    } catch (e) {
      return false;
    }
  }

  function paint(kind) {
    var hidden = isHidden(kind);
    if (hidden) delete document.documentElement.dataset[showAttr[kind]];
    else document.documentElement.dataset[showAttr[kind]] = "1";
    document.querySelectorAll('[data-privacy-toggle="' + kind + '"]').forEach(function (button) {
      button.setAttribute("aria-pressed", hidden ? "true" : "false");
    });
  }

  document.querySelectorAll("[data-privacy-toggle]").forEach(function (button) {
    var kind = button.getAttribute("data-privacy-toggle");
    paint(kind);
    button.addEventListener("click", function () {
      try {
        localStorage.setItem(keys[kind], isHidden(kind) ? "0" : "1");
      } catch (e) {}
      paint(kind);
    });
  });
})();

// Monthly salary (and the مانده derived from it) is never in the page HTML.
// The eye button fetches it from /api/salary and keeps it only in the DOM; nothing is stored,
// so every reload or navigation shows the mask again.
(function () {
  var MASK = "••••••";
  var buttons = document.querySelectorAll("[data-salary-reveal]");
  if (!buttons.length) return;
  var shown = false;

  function fields() {
    return document.querySelectorAll("[data-salary-field]");
  }

  function setButtons(hidden, busy) {
    buttons.forEach(function (b) {
      b.setAttribute("aria-pressed", hidden ? "true" : "false");
      b.setAttribute("aria-label", hidden ? "نمایش مبلغ" : "پنهان کردن");
      if (busy) b.setAttribute("aria-busy", "true");
      else b.removeAttribute("aria-busy");
    });
  }

  function hide() {
    fields().forEach(function (el) { el.textContent = MASK; });
    shown = false;
    setButtons(true, false);
  }

  function show() {
    setButtons(true, true);
    fetch("/api/salary", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("salary " + r.status);
        return r.json();
      })
      .then(function (data) {
        fields().forEach(function (el) {
          var v = data[el.getAttribute("data-salary-field")];
          el.textContent = typeof v === "string" ? v : MASK;
        });
        shown = true;
        setButtons(false, false);
      })
      .catch(function () { hide(); });
  }

  buttons.forEach(function (b) {
    b.addEventListener("click", function () { if (shown) hide(); else show(); });
  });
  // Back/forward cache restores the old DOM: mask again.
  window.addEventListener("pageshow", function (e) { if (e.persisted) hide(); });
  window.addEventListener("pagehide", hide);
  hide();
})();
