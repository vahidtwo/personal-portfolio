// Page HTML carries no amounts: each one is an empty [data-amt] placeholder (or a [data-amt-attr] /
// [data-amt-json] slot). The values come from /api/amounts (no-store, same-origin, signed-in) only
// while amounts are shown, or when the eye is tapped; they live in the DOM and are never stored.
(function () {
  var W = window;
  var loaded = null; // page path the DOM was last filled for
  var pending = null;

  function shown() {
    return document.documentElement.dataset.showPortfolio === "1";
  }
  function hasSlots(root) {
    return !!(root || document).querySelector("[data-amt],[data-amt-attr],[data-amt-json]");
  }
  function pagePath(url) {
    var u = new URL(url || location.href, location.href);
    return u.pathname + u.search;
  }

  function fill(values, root) {
    root = root || document;
    root.querySelectorAll("[data-amt]").forEach(function (el) {
      var v = values[el.getAttribute("data-amt")];
      el.textContent = typeof v === "string" ? v : "—";
    });
    root.querySelectorAll("[data-amt-attr]").forEach(function (el) {
      el.getAttribute("data-amt-attr").split(" ").forEach(function (pair) {
        var i = pair.indexOf("=");
        if (i < 1) return;
        var v = values[pair.slice(i + 1)];
        if (v === undefined) return;
        el.setAttribute(pair.slice(0, i), typeof v === "string" ? v : JSON.stringify(v));
      });
    });
    root.querySelectorAll("[data-amt-json]").forEach(function (el) {
      var v = values[el.getAttribute("data-amt-json")];
      if (v !== undefined) el.textContent = JSON.stringify(v);
      el.setAttribute("data-amt-filled", "1");
    });
    document.dispatchEvent(new CustomEvent("amounts:filled"));
  }

  function load(url, force) {
    var path = pagePath(url);
    if (!force && loaded === path) return Promise.resolve(true);
    if (!hasSlots()) return Promise.resolve(false);
    if (pending && !force) return pending;
    pending = fetch("/api/amounts?path=" + encodeURIComponent(path), {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (r.status === 401) { location.reload(); throw new Error("login"); }
        if (!r.ok) throw new Error("amounts " + r.status);
        return r.json();
      })
      .then(function (data) {
        fill(data.v || {});
        loaded = path;
        return true;
      })
      .catch(function () { return false; })
      .then(function (ok) { pending = null; return ok; });
    return pending;
  }

  W.Amounts = {
    // Re-read after a part of the page was swapped in from url (defaults to this page).
    refresh: function (url) { loaded = null; return shown() ? load(url, true) : Promise.resolve(false); },
    // Load now even if masked (a view such as a chart or an edit form needs the numbers).
    need: function (url) { return load(url, false); },
    shown: shown,
  };

  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest('[data-privacy-toggle="portfolio"]');
    if (!t) return;
    setTimeout(function () { if (shown()) load(); }, 0);
  });
  W.addEventListener("pageshow", function (e) {
    if (e.persisted && shown()) load(null, true);
  });
  if (shown()) load();
})();
