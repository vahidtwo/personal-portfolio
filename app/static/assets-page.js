/* Assets page (Phase 1): live values, «افزودن دارایی» chips, unsaved-changes bar and leave warning.
   Display only: the form still submits the raw inputs to POST /profile, parsed by app/number_input.py.
   Numbers are read with NumberFa.normalize (same rules as the server); nothing typed is ever rounded. */
(function () {
  var form = document.querySelector("[data-assets-form]");
  if (!form || !window.NumberFa) return;
  var NF = window.NumberFa;
  var root = document.documentElement;
  var bar = form.querySelector("[data-save-bar]");
  var countEl = form.querySelector("[data-dirty-count]");
  var totalEl = form.querySelector("[data-assets-total]");
  var inputs = Array.prototype.slice.call(form.querySelectorAll("[data-asset-input]"));
  var extras = Array.prototype.slice.call(form.querySelectorAll("[data-assets-extra]"));
  var revealed = [];
  var submitting = false;
  var mobile = window.matchMedia("(max-width: 899px)");

  // Canonical text for comparing values: "" and "0" are the same, "1.50" equals "1.5"; null = invalid.
  function canon(text) {
    var t = NF.normalize(text);
    if (t === null) return null;
    if (t === "") return "0";
    var neg = t.charAt(0) === "-";
    t = t.replace(/^[+-]/, "");
    var parts = t.split(".");
    var ip = (parts[0] || "0").replace(/^0+(?=\d)/, "") || "0";
    var fp = (parts[1] || "").replace(/0+$/, "");
    var out = fp ? ip + "." + fp : ip;
    if (neg && out !== "0") return null; // negative: invalid, worth shows «—», totals untouched
    return out;
  }

  function isChanged(input) {
    var now = canon(input.value);
    return now === null || now !== canon(input.defaultValue);
  }

  function rowOf(input) { return input.closest("[data-asset-row]"); }

  function rowValue(row, input) {
    var base = Number(row.dataset.base || "0");
    if (!isChanged(input)) return { value: base, ok: true };
    var price = row.dataset.price;
    if (!price) return { value: 0, ok: true }; // no price today: counts as 0, same as the server
    var q = canon(input.value);
    if (q === null) return { value: base, ok: false };
    return { value: Math.round(Number(q) * Number(price)), ok: true };
  }

  function fmt(v) { return NF.format(v, 0) || "۰"; }

  function refreshValues() {
    var total = Number(totalEl.dataset.base || "0");
    form.querySelectorAll("[data-asset-group]").forEach(function (group) {
      var gTotalEl = group.querySelector("[data-group-total]");
      if (!gTotalEl) return;
      var gTotal = Number(gTotalEl.dataset.base || "0");
      group.querySelectorAll("[data-asset-row]").forEach(function (row) {
        var input = row.querySelector("[data-asset-input]");
        var r = rowValue(row, input);
        var delta = r.value - Number(row.dataset.base || "0");
        gTotal += delta;
        total += delta;
        var out = row.querySelector("[data-row-value]");
        if (out) out.textContent = r.ok ? fmt(r.value) : "—";
        row.classList.toggle("is-changed", isChanged(input));
        input.setAttribute("aria-invalid", r.ok ? "false" : "true");
      });
      gTotalEl.textContent = fmt(gTotal);
    });
    totalEl.textContent = fmt(total);
  }

  function dirtyCount() {
    var n = inputs.filter(isChanged).length;
    extras.forEach(function (el) {
      if (el.type === "checkbox" ? el.checked : el.value.trim() !== "") n += 1;
    });
    return n;
  }

  function setExtraBottom() {
    var h = !bar.hidden && mobile.matches ? Math.ceil(bar.getBoundingClientRect().height) : 0;
    root.style.setProperty("--page-extra-bottom", h + "px");
  }

  function refresh() {
    refreshValues();
    var n = dirtyCount();
    var removed = form.querySelectorAll(".arow.v2-removed").length;
    bar.hidden = n === 0;
    // assets v2: name the kind of change when every pending change is a delete
    countEl.textContent = removed && removed === n ? NF.format(n, 0) + " حذف ذخیره نشده" : NF.format(n, 0) + " تغییر ذخیره نشده";
    setExtraBottom();
  }

  function updateMore(group) {
    var more = group.querySelector("[data-asset-more]");
    if (!more) return;
    var visible = more.querySelectorAll("[data-add-asset]:not([hidden])").length;
    more.hidden = visible === 0;
  }

  form.querySelectorAll("[data-add-asset]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var row = form.querySelector('[data-asset-row="' + chip.dataset.addAsset + '"]');
      if (!row) return;
      row.hidden = false;
      chip.hidden = true;
      revealed.push({ row: row, chip: chip });
      updateMore(chip.closest("[data-asset-group]"));
      var input = row.querySelector("[data-asset-input]");
      input.focus();
      row.scrollIntoView({ block: "nearest" });
    });
  });

  form.querySelector("[data-assets-cancel]").addEventListener("click", function () {
    form.reset(); // back to the values that were loaded
    form.dispatchEvent(new Event("assets:reset"));
    inputs.forEach(function (input) { input.dispatchEvent(new Event("blur")); });
    revealed.forEach(function (item) {
      item.row.hidden = true;
      item.chip.hidden = false;
      updateMore(item.chip.closest("[data-asset-group]"));
    });
    revealed = [];
    setTimeout(refresh, 0);
  });

  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);
  form.addEventListener("submit", function () { submitting = true; });
  form.addEventListener("assets:refresh", refresh);
  form.addEventListener("assets:saved", function () { submitting = true; });
  window.addEventListener("beforeunload", function (event) {
    if (submitting || dirtyCount() === 0) return;
    event.preventDefault();
    event.returnValue = "";
  });
  if (mobile.addEventListener) mobile.addEventListener("change", setExtraBottom);
  window.addEventListener("resize", setExtraBottom);

  // Back/forward: the browser may put typed-but-unsaved values back into the fields after this script
  // ran. Show the rows those values belong to (a new asset's row starts hidden) and the save bar again.
  function restoreTyped() {
    inputs.forEach(function (input) {
      var row = rowOf(input);
      if (!row || !row.hidden || !isChanged(input)) return;
      var chip = form.querySelector('[data-add-asset="' + row.dataset.assetRow + '"]');
      row.hidden = false;
      if (chip) {
        chip.hidden = true;
        revealed.push({ row: row, chip: chip });
        updateMore(chip.closest("[data-asset-group]"));
      }
    });
    refresh();
  }
  window.addEventListener("pageshow", restoreTyped);
  window.addEventListener("load", restoreTyped);
  refresh();
})();
