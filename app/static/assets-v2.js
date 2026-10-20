/* Assets v2 (mockups/app-v2/assets): inline validation in words, error summary, «⋯» menu with
   edit/delete (confirm + pending row + undo), the «افزودن دارایی» sheet, quick-adds, collapse,
   and a busy/failed state for save. The form contract (POST /profile) is unchanged; with JS the save
   goes through fetch(Accept: application/json) so a network failure keeps every typed value. */
(function () {
  var form = document.querySelector("[data-assets-form]");
  if (!form || !window.NumberFa) return;
  var NF = window.NumberFa;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var MSG = {
    decimal_point: "فقط یک ممیز (٫) بگذارید؛ مثلاً ۱٫۲۵",
    not_number: "فقط عدد وارد کنید",
    negative: "مقدار نمی‌تواند منفی باشد",
    too_many_decimals: "حداکثر {n} رقم اعشار",
  };
  var SHORT = { decimal_point: "عدد نامعتبر", not_number: "عدد نامعتبر", negative: "منفی است", too_many_decimals: "رقم اعشار زیاد" };
  var fa = function (s) { return String(s).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; }); };
  var money = function (n) { return NF.format(Math.round(n), 0) || "۰"; };
  var maxDec = function (input) { return Number(input.dataset.maxDecimals || NF.QTY_DECIMALS || 8); };
  var isLatin = function (u) { return /^[A-Z]/.test(u || ""); };

  // Same rules as app/number_input.quantity_error.
  function reason(raw, max) {
    var lead = String(raw || "").trim().replace(/\u2212/g, "-").charAt(0) === "-";
    var t = NF.normalize(raw);
    if (t === null) {
      var latin = String(raw).replace(/[۰-۹٠-٩]/g, "0").replace(/\u066B/g, ".");
      if (latin.split(".").length > 2 || /\.[^.]*[,\u066C\u060C]/.test(latin)) return "decimal_point";
      return lead ? "negative" : "not_number";
    }
    if (t === "") return null;
    if (t.charAt(0) === "-" && /[1-9]/.test(t)) return "negative";
    if (t.indexOf(".") !== -1 && t.split(".")[1].length > max) return "too_many_decimals";
    return null;
  }
  function message(r, max) { return MSG[r].replace("{n}", fa(max)); }
  function rowOf(el) { return el.closest("[data-asset-row]"); }
  function refresh() { form.dispatchEvent(new Event("assets:refresh")); }

  function setError(input, msg) {
    var row = rowOf(input), field = input.closest(".v2-field"), id = "err-" + input.id;
    var el = document.getElementById(id);
    var described = (input.getAttribute("aria-describedby") || "").split(" ").filter(function (x) { return x && x !== id; });
    if (msg) {
      if (!el) { el = document.createElement("span"); el.className = "v2-err"; el.id = id; field.appendChild(el); }
      el.textContent = msg;
      described.unshift(id);
      row.classList.add("v2-invalid");
      input.setAttribute("aria-invalid", "true");
    } else {
      if (el) el.remove();
      row.classList.remove("v2-invalid");
      input.setAttribute("aria-invalid", "false");
    }
    input.setAttribute("aria-describedby", described.join(" "));
  }
  function check(input) {
    var r = reason(input.value, maxDec(input));
    setError(input, r ? message(r, maxDec(input)) : null);
    return r;
  }
  var inputs = $$("[data-asset-input]", form);
  inputs.forEach(function (input) {
    // validate on blur and on submit, never per keystroke; clear as soon as the value is valid again
    input.addEventListener("blur", function () { check(input); });
    input.addEventListener("input", function () {
      if (rowOf(input).classList.contains("v2-invalid") && !reason(input.value, maxDec(input))) setError(input, null);
    });
  });

  var banners = $("[data-v2-banners]", form);
  function summary(errors) {
    var old = $("[data-v2-summary]", form); if (old) old.remove();
    if (!errors.length) return;
    var b = document.createElement("div");
    b.className = "v2-banner err"; b.setAttribute("role", "alert"); b.tabIndex = -1; b.id = "v2-summary"; b.setAttribute("data-v2-summary", "");
    var items = errors.map(function (e) {
      return '<li><a href="#' + e.input.id + '">' + rowOf(e.input).dataset.name + ": " + e.short + "</a></li>";
    }).join("");
    b.innerHTML = "<div><strong>" + fa(errors.length) + " مقدار نیاز به اصلاح دارد</strong><ul>" + items + "</ul></div>";
    banners.prepend(b);
    b.focus();
  }
  form.addEventListener("click", function (e) {
    var a = e.target.closest("[data-v2-summary] a");
    if (!a) return;
    e.preventDefault();
    var t = document.getElementById(a.getAttribute("href").slice(1));
    if (t) { openGroup(t.closest(".asset-group")); t.focus(); t.scrollIntoView({ block: "center" }); }
  });
  var serverSummary = $("[data-v2-summary]", form);
  if (serverSummary) serverSummary.focus();

  // ---- save: validate, then fetch; busy state; a failure banner keeps the values ----
  var submitBtn = $("[data-assets-submit]", form), cancelBtn = $("[data-assets-cancel]", form);
  var busy = false;
  function setBusy(on) {
    busy = on;
    submitBtn.setAttribute("aria-disabled", on ? "true" : "false");
    cancelBtn.setAttribute("aria-disabled", on ? "true" : "false");
    cancelBtn.disabled = on;
    submitBtn.innerHTML = on ? '<span class="v2-spin" aria-hidden="true"></span> ذخیره…' : "ذخیرهٔ تغییرات";
  }
  function saveFailed() {
    var old = $("[data-v2-save-error]", form); if (old) old.remove();
    var b = document.createElement("div");
    b.className = "v2-banner err"; b.setAttribute("role", "alert"); b.setAttribute("data-v2-save-error", "");
    b.innerHTML = '<div><strong>ذخیره نشد</strong>اتصال برقرار نشد. مقدارهایی که وارد کردید سر جایشان مانده‌اند.</div><button type="button" class="btn">دوباره</button>';
    b.querySelector("button").addEventListener("click", function () { submit(); });
    banners.prepend(b);
  }
  function submit(e) {
    if (e) e.preventDefault();
    if (busy) return; // a double submit is ignored
    var errors = [];
    inputs.forEach(function (input) {
      var r = check(input);
      if (r) errors.push({ input: input, short: SHORT[r] });
    });
    if (errors.length) { summary(errors); return; }
    summary([]);
    var old = $("[data-v2-save-error]", form); if (old) old.remove();
    if (!window.fetch || !window.FormData) { form.dispatchEvent(new Event("assets:saved")); form.submit(); return; }
    setBusy(true);
    fetch(form.action, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (res) {
        return res.json().catch(function () { return null; }).then(function (data) { return { res: res, data: data }; });
      })
      .then(function (r) {
        if (r.data && r.data.ok) { form.dispatchEvent(new Event("assets:saved")); window.location.assign(r.data.redirect || "/assets"); return; }
        setBusy(false);
        if (r.res.status === 422 && r.data && r.data.fields) {
          var errs = [];
          Object.keys(r.data.fields).forEach(function (name) {
            var input = form.querySelector('[name="' + name + '"]');
            if (!input) return;
            setError(input, r.data.fields[name]);
            errs.push({ input: input, short: SHORT[r.data.reasons && r.data.reasons[name]] || r.data.fields[name] });
          });
          summary(errs);
          return;
        }
        saveFailed();
      })
      .catch(function () { setBusy(false); saveFailed(); });
  }
  form.addEventListener("submit", submit);

  // ---- dialogs (sheet / alertdialog): focus trap, Esc, return focus ----
  var dlg = null;
  function closeDialog() {
    if (!dlg) return;
    dlg.el.remove(); dlg.scrim.remove();
    document.removeEventListener("keydown", dlg.key, true);
    var back = dlg.back; dlg = null;
    if (back && document.contains(back)) back.focus();
  }
  function openDialog(html, opts) {
    var back = opts.back || (dlg ? dlg.back : document.activeElement);
    closeDialog();
    var scrim = document.createElement("div"); scrim.className = "v2-scrim";
    var el = document.createElement("div");
    el.className = "v2-sheet"; el.setAttribute("role", opts.role || "dialog"); el.setAttribute("aria-modal", "true"); el.setAttribute("aria-labelledby", "v2-st");
    el.innerHTML = '<div class="v2-grab"></div>' + html;
    document.body.appendChild(scrim); document.body.appendChild(el);
    var key = function (e) {
      if (e.key === "Escape") { e.preventDefault(); closeDialog(); return; }
      if (e.key !== "Tab") return;
      var f = $$("button:not([disabled]),input,a[href]", el).filter(function (x) { return x.offsetParent !== null; });
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    };
    document.addEventListener("keydown", key, true);
    scrim.addEventListener("click", closeDialog);
    dlg = { el: el, scrim: scrim, key: key, back: back };
    $$("[data-v2-close]", el).forEach(function (b) { b.addEventListener("click", closeDialog); });
    var first = opts.focus ? $(opts.focus, el) : $("input,button", el);
    if (first) first.focus();
    return el;
  }
  var X = '<button type="button" class="v2-x" aria-label="بستن" data-v2-close>✕</button>';

  // ---- add sheet: step 1 pick, step 2 quantity ----
  function hintFor(key) {
    var both = "ارقام فارسی یا انگلیسی هر دو پذیرفته می‌شوند.";
    if (/^coin_/.test(key)) return "تعداد سکهٔ کامل. " + both;
    if (key === "gold" || key === "silver") return "به گرم. " + both;
    if (key === "cash") return "بدون تبدیل، به تومان. " + both;
    return both;
  }
  function pickSheet(back) {
    var groups = $$("[data-asset-group]", form).filter(function (g) { return g.dataset.assetGroup !== "car"; });
    var list = groups.map(function (g) {
      var rows = $$("[data-asset-row]", g).filter(function (r) { return r.hidden; });
      if (!rows.length) return "";
      return "<h3>" + g.dataset.groupTitle + "</h3><ul>" + rows.map(function (r) {
        return '<li data-q="' + r.dataset.name + '"><button type="button" data-v2-pick="' + r.dataset.assetRow + '"><img src="/static/logos/' +
          r.dataset.assetRow + '.svg" alt="">' + r.dataset.name + '<span class="s"' + (isLatin(r.dataset.unit) ? ' dir="ltr"' : "") + ">" + r.dataset.unit + "</span></button></li>";
      }).join("") + "</ul>";
    }).join("");
    var el = openDialog('<div class="v2-shead"><h2 id="v2-st">افزودن دارایی</h2>' + X + "</div>" +
      '<label class="lbl" for="v2-s">جست‌وجو</label><input class="v2-search" id="v2-s" type="search" placeholder="مثلاً سکه یا دلار" autocomplete="off">' +
      '<div class="v2-pick">' + (list || '<p class="hint">همهٔ دارایی‌ها اضافه شده‌اند.</p>') + "</div>", { back: back, focus: "#v2-s" });
    $("#v2-s", el).addEventListener("input", function () {
      var q = this.value.trim();
      $$(".v2-pick li", el).forEach(function (li) { li.hidden = q !== "" && li.dataset.q.indexOf(q) === -1; });
      $$(".v2-pick h3", el).forEach(function (h) {
        var ul = h.nextElementSibling;
        h.hidden = !!ul && !$$("li", ul).some(function (li) { return !li.hidden; });
      });
    });
    $$("[data-v2-pick]", el).forEach(function (b) { b.addEventListener("click", function () { qtySheet(b.dataset.v2Pick, back, true); }); });
  }
  function qtySheet(key, back, fromPick) {
    var row = form.querySelector('[data-asset-row="' + key + '"]');
    if (!row) return;
    var price = row.dataset.price ? Number(row.dataset.price) : null;
    var g = row.closest("[data-asset-group]");
    var showWorth = price && key !== "cash";
    var el = openDialog('<div class="v2-shead"><h2 id="v2-st">افزودن دارایی</h2>' + X + "</div>" +
      '<div class="v2-picked"><img src="/static/logos/' + key + '.svg" alt=""><div class="t">' + row.dataset.name + "<small>" + g.dataset.groupTitle +
      (showWorth ? "، قیمت روز: " + money(price) + " تومان" : "") + "</small></div>" + (fromPick ? '<button type="button" data-v2-change>تغییر</button>' : "") + "</div>" +
      '<label class="lbl" for="v2-q">مقدار</label>' +
      '<div class="v2-qty"><input id="v2-q" inputmode="decimal" dir="ltr" autocomplete="off" aria-describedby="v2-qh v2-qw"><span class="u"' +
      (isLatin(row.dataset.unit) ? ' dir="ltr"' : "") + ">" + row.dataset.unit + "</span></div>" +
      '<p class="hint" id="v2-qh">' + hintFor(key) + "</p>" +
      '<div class="v2-worth" id="v2-qw" aria-live="polite"' + (showWorth ? "" : " hidden") + ">ارزش تقریبی: <b>۰</b> تومان</div>" +
      '<div class="v2-actions"><button type="button" class="btn btn-primary" data-v2-confirm-add>افزودن</button><button type="button" class="btn btn-ghost" data-v2-close>انصراف</button></div>',
      { back: back, focus: "#v2-q" });
    var q = $("#v2-q", el), worth = $("#v2-qw b", el), max = maxDec(row.querySelector("[data-asset-input]"));
    function showErr(r) {
      var e = document.getElementById("v2-qe");
      if (!r) { if (e) e.remove(); q.removeAttribute("aria-invalid"); q.setAttribute("aria-describedby", "v2-qh v2-qw"); return; }
      if (!e) { e = document.createElement("p"); e.className = "v2-err"; e.id = "v2-qe"; $(".v2-qty", el).after(e); }
      q.setAttribute("aria-describedby", "v2-qe v2-qh v2-qw");
      e.textContent = message(r, max); q.setAttribute("aria-invalid", "true");
    }
    q.addEventListener("input", function () {
      var t = NF.normalize(q.value);
      if (t !== null && price) worth.textContent = money(Number(t || 0) * price);
      if (document.getElementById("v2-qe") && !reason(q.value, max)) showErr(null);
    });
    q.addEventListener("blur", function (e) {
      if (e.relatedTarget && e.relatedTarget.hasAttribute("data-v2-close")) return;
      showErr(reason(q.value, max));
    });
    var change = $("[data-v2-change]", el); if (change) change.addEventListener("click", function () { pickSheet(back); });
    $("[data-v2-confirm-add]", el).addEventListener("click", function () {
      var r = reason(q.value, max) || (NF.normalize(q.value) === "" ? "not_number" : null);
      if (r) { showErr(r); q.focus(); return; }
      reveal(row);
      var input = row.querySelector("[data-asset-input]");
      input.value = q.value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      dlg.back = input;
      closeDialog();
      row.scrollIntoView({ block: "nearest" });
    });
  }
  function reveal(row) {
    leaveEmpty();
    var chip = form.querySelector('[data-add-asset="' + row.dataset.assetRow + '"]');
    if (row.hidden && chip) chip.click(); else row.hidden = false;
    var g = row.closest(".asset-group"); openGroup(g); updateCount(g);
  }
  function leaveEmpty() {
    var w = $("[data-v2-welcome]", form);
    if (!w) return;
    w.remove();
    $$(".asset-group.v2-hide, .assets-total.v2-hide, .v2-add.v2-hide", form).forEach(function (el) { el.classList.remove("v2-hide"); });
  }
  $$("[data-v2-add-open]", form).forEach(function (b) { b.addEventListener("click", function () { pickSheet(b); }); });
  $$("[data-v2-quick]", form).forEach(function (b) { b.addEventListener("click", function () { qtySheet(b.dataset.v2Quick, b, false); }); });
  $$("[data-add-asset]", form).forEach(function (chip) { chip.addEventListener("click", function () { updateCount(chip.closest(".asset-group")); }); });

  // ---- group count + collapse ----
  function updateCount(g) {
    var c = g && $("[data-v2-count]", g); if (!c) return;
    var n = $$("[data-asset-row]", g).filter(function (r) { return !r.hidden; }).length;
    c.hidden = n === 0; c.textContent = fa(n) + " دارایی";
  }
  function openGroup(g) {
    if (!g || !g.classList.contains("v2-closed")) return;
    g.classList.remove("v2-closed");
    var t = $(".v2-collapse", g); if (t) t.setAttribute("aria-expanded", "true");
  }
  $$("[data-asset-group]", form).forEach(function (g) {
    if (g.dataset.assetGroup === "car") return;
    var t = document.createElement("button");
    t.type = "button"; t.className = "v2-collapse"; t.setAttribute("aria-expanded", "true");
    t.setAttribute("aria-label", "بستن یا باز کردن گروه " + g.dataset.groupTitle);
    t.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M6 15l6-6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
    t.addEventListener("click", function () {
      var closed = g.classList.toggle("v2-closed");
      t.setAttribute("aria-expanded", closed ? "false" : "true");
    });
    $(".asset-group-head", g).appendChild(t);
  });

  // ---- «⋯» menu, delete confirm, pending row + undo ----
  var menu = null;
  function closeMenu(focusBack) {
    if (!menu) return;
    menu.el.remove(); menu.btn.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", menu.outside, true);
    if (focusBack) menu.btn.focus();
    menu = null;
  }
  $$("[data-v2-more]", form).forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (menu && menu.btn === btn) { closeMenu(true); return; }
      closeMenu(false);
      var row = rowOf(btn);
      var el = document.createElement("div");
      el.className = "v2-menu"; el.setAttribute("role", "menu"); el.setAttribute("aria-label", btn.getAttribute("aria-label"));
      el.innerHTML = '<button type="button" role="menuitem" data-act="edit">ویرایش</button><button type="button" role="menuitem" class="danger" data-act="del">حذف</button>';
      el.style.insetInlineEnd = "0"; el.style.top = btn.offsetTop + btn.offsetHeight + "px";
      row.appendChild(el);
      btn.setAttribute("aria-expanded", "true");
      var outside = function (e) { if (!el.contains(e.target) && !btn.contains(e.target)) closeMenu(false); };
      document.addEventListener("click", outside, true);
      menu = { el: el, btn: btn, outside: outside };
      el.addEventListener("keydown", function (e) {
        var items = $$("button", el), i = items.indexOf(document.activeElement);
        if (e.key === "Escape") { e.preventDefault(); closeMenu(true); }
        if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
        if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
      });
      $("[data-act=edit]", el).addEventListener("click", function () { closeMenu(false); var i = row.querySelector("[data-asset-input]"); i.focus(); i.select(); });
      $("[data-act=del]", el).addEventListener("click", function () { closeMenu(false); confirmDelete(row, btn); });
      $("button", el).focus();
    });
  });
  function confirmDelete(row, back) {
    var input = row.querySelector("[data-asset-input]");
    var qty = NF.format(NF.normalize(input.value) || "0", 8) || "۰";
    var worthEl = row.querySelector("[data-row-value]");
    var worth = worthEl ? " با ارزش حدود " + worthEl.textContent + " تومان" : "";
    var el = openDialog('<h2 id="v2-st">' + row.dataset.name + " حذف شود؟</h2>" +
      '<p class="hint" style="font-size:14.5px" id="v2-sd"><bdi' + (isLatin(row.dataset.unit) ? ' dir="ltr"' : "") + ">" + qty + " " + row.dataset.unit + "</bdi>" + worth +
      " از دارایی‌هایتان برداشته می‌شود. تا «ذخیرهٔ تغییرات» را نزنید، می‌توانید برش گردانید.</p>" +
      '<div class="v2-actions"><button type="button" class="btn btn-danger" data-v2-del>حذف</button><button type="button" class="btn btn-ghost" data-v2-close>انصراف</button></div>',
      { role: "alertdialog", back: back, focus: "[data-v2-close]" });
    el.setAttribute("aria-describedby", "v2-sd");
    $("[data-v2-del]", el).addEventListener("click", function () { dlg.back = null; closeDialog(); markRemoved(row); });
  }
  function markRemoved(row) {
    var input = row.querySelector("[data-asset-input]"), more = row.querySelector("[data-v2-more]");
    row.dataset.v2Orig = input.value;
    setError(input, null);
    input.value = ""; // a cleared field is removed on save, exactly as before
    row.classList.add("v2-removed");
    var w = row.querySelector(".arow-worth"); row.dataset.v2Worth = w.innerHTML; w.textContent = "حذف می‌شود";
    more.hidden = true;
    var u = document.createElement("button");
    u.type = "button"; u.className = "v2-undo"; u.textContent = "برگردان"; u.setAttribute("aria-label", "برگرداندن " + row.dataset.name);
    u.addEventListener("click", function () { undoRemoved(row); more.focus(); });
    more.after(u);
    refresh();
    u.focus();
  }
  function undoRemoved(row) {
    if (!row.classList.contains("v2-removed")) return;
    var input = row.querySelector("[data-asset-input]");
    input.value = row.dataset.v2Orig || "";
    row.classList.remove("v2-removed");
    row.querySelector(".arow-worth").innerHTML = row.dataset.v2Worth || "";
    var u = row.querySelector(".v2-undo"); if (u) u.remove();
    row.querySelector("[data-v2-more]").hidden = false;
    refresh();
  }
  form.addEventListener("assets:reset", function () {
    setTimeout(function () {
      $$(".arow.v2-removed", form).forEach(undoRemoved);
      inputs.forEach(function (i) { setError(i, null); });
      summary([]);
      $$("[data-asset-group]", form).forEach(updateCount);
    }, 0);
  });
})();
