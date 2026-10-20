/* Spending v2: chips <-> hidden selects, date shortcuts, sheet, row menu, in-app delete confirm,
   per-field validation (same rules as app/spend_validation.py), fetch save, and progressive list loading. */
(function () {
  "use strict";
  var W = typeof window !== "undefined" ? window : {};
  // number-format.js loads after this file (page scripts block), so look it up when used.
  var NF0 = W.NumberFa || (typeof require === "function" && typeof module !== "undefined" ? require("./number-format.js") : null);
  function N() { return W.NumberFa || NF0; }
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  function fa(n) { return String(n).replace(/\d/g, function (d) { return FA[Number(d)]; }); }
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  var MSG = {
    amountFormat: "مبلغ را بدون ممیز بنویسید؛ مثلاً ۱۲۰٬۰۰۰",
    amountPositive: "مبلغ باید بیشتر از صفر باشد",
    year: "سال را چهاررقمی بنویسید",
    month: "ماه بین ۱ تا ۱۲ است",
    day: function (n) { return "این ماه " + fa(n) + " روز دارد"; },
  };
  var SHORT = { amount_toman: "مبلغ", category_id: "زیردسته", year: "سال", month: "ماه", day: "روز" };
  var ORDER = ["amount_toman", "category_id", "year", "month", "day"];

  function intOf(raw) {
    var t = N().normalize(raw);
    return t && /^\d+$/.test(t) ? Number(t) : null;
  }
  function isLeap(y) { return [1, 5, 9, 13, 17, 22, 26, 30].indexOf(y % 33) !== -1; } // jdatetime's rule
  function monthLength(y, m) { return m <= 6 ? 31 : m <= 11 ? 30 : (isLeap(y) ? 30 : 29); }

  /* {field: message} for every bad field; mirrors spend_validation.validate_spend. */
  function validate(v) {
    var e = {};
    var t = N().normalize(v.amount);
    if (t === null) e.amount_toman = MSG.amountFormat;
    else if (/^-/.test(t) && /[1-9]/.test(t)) e.amount_toman = MSG.amountPositive;
    else if (t.indexOf(".") !== -1) e.amount_toman = MSG.amountFormat;
    else if (!(Number(t || "0") > 0)) e.amount_toman = MSG.amountPositive;
    var y = intOf(v.year), m = intOf(v.month), d = intOf(v.day);
    if (y === null || y < 1000 || y > 9999) e.year = MSG.year;
    if (m === null || m < 1 || m > 12) e.month = MSG.month;
    if (!e.year && !e.month) {
      var n = monthLength(y, m);
      if (d === null || d < 1 || d > n) e.day = MSG.day(n);
    } else if (d === null || d < 1 || d > 31) e.day = MSG.day(31);
    return e;
  }
  W.SpendValidate = { validate: validate, monthLength: monthLength };
  if (typeof module !== "undefined" && module.exports) module.exports = W.SpendValidate;
  if (typeof document === "undefined" || !document.querySelector) return;

  document.addEventListener("DOMContentLoaded", function () {
    var page = $("[data-sp-page]");
    if (!page) return;
    page.setAttribute("data-sp-js", "1");
    var card = $("[data-sp-form-card]"), form = $("[data-sp-form]");
    var ps = $("#spend-parent"), cs = $("#spend-child");
    var amt = form.elements.amount_toman;
    // amount words/suggestions were inserted inside the unit wrapper; move them under it.
    var wrap = amt.closest(".sp-amt");
    // Order under the field: error, words, suggestions. The error and the words line swap places
    // (one shows when the other hides), so blur validation doesn't shift the chips below mid-click.
    var amtErr = $("#err-amount_toman");
    $$(".amount-words, .amount-suggest", wrap).reverse().forEach(function (el) { amtErr.insertAdjacentElement("afterend", el); });

    /* ---------- chips ---------- */
    var pChips = $("[data-sp-pchips]"), cChips = $("[data-sp-cchips]");
    function drawKids() {
      cChips.innerHTML = "";
      var kids = $$("option", cs).filter(function (o) { return o.getAttribute("data-parent") === ps.value; });
      if (!kids.some(function (o) { return o.value === cs.value; }) && kids[0]) cs.value = kids[0].value;
      kids.forEach(function (o) {
        var b = document.createElement("button");
        b.type = "button"; b.textContent = o.textContent;
        b.setAttribute("aria-pressed", String(o.value === cs.value));
        b.addEventListener("click", function () { cs.value = o.value; drawKids(); });
        cChips.appendChild(b);
      });
    }
    function drawParents() {
      pChips.innerHTML = "";
      $$("option", ps).forEach(function (o) {
        if (o.getAttribute("data-slug") === "sms" && o.value !== ps.value) return; // auto-only category
        var b = document.createElement("button");
        b.type = "button";
        var sw = document.createElement("span"); sw.className = "sw"; sw.setAttribute("aria-hidden", "true");
        sw.style.background = o.getAttribute("data-color") || "#475569";
        b.appendChild(sw); b.appendChild(document.createTextNode(o.textContent.trim()));
        b.setAttribute("aria-pressed", String(o.value === ps.value));
        b.addEventListener("click", function () { ps.value = o.value; drawParents(); drawKids(); });
        pChips.appendChild(b);
      });
    }
    drawParents(); drawKids();

    /* ---------- date shortcuts ---------- */
    var dchips = $("[data-sp-dchips]"), custom = $("[data-sp-custom]");
    function parts(key) { return dchips.getAttribute(key).split("-"); }
    function setDate(p) { form.elements.year.value = fa(p[0]); form.elements.month.value = fa(p[1]); form.elements.day.value = fa(p[2]); }
    function current() { return [intOf(form.elements.year.value), intOf(form.elements.month.value), intOf(form.elements.day.value)].join("-"); }
    function pickDay(which, focus) {
      $$("button", dchips).forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-sp-day") === which)); });
      var other = which === "other";
      custom.classList.toggle("open", other);
      $("[data-sp-day=other]", dchips).setAttribute("aria-expanded", String(other));
      if (which === "today") setDate(parts("data-today"));
      if (which === "yesterday") setDate(parts("data-yesterday"));
      if (other && focus) form.elements.day.focus();
    }
    $$("button", dchips).forEach(function (b) { b.addEventListener("click", function () { pickDay(b.getAttribute("data-sp-day"), true); }); });
    var hasDateErr = !!$(".sp-custom .sp-invalid", form);
    var cur = current();
    pickDay(hasDateErr ? "other" : cur === parts("data-today").join("-") ? "today" : cur === parts("data-yesterday").join("-") ? "yesterday" : "other");
    // pickDay("today") rewrote nothing harmful: same values. Keep server values for "other".

    /* ---------- dialogs (sheet, confirm) ---------- */
    var mobile = window.matchMedia("(max-width: 899px)");
    var openDlg = null;
    function trap(dlg, e) {
      if (e.key === "Escape") { e.preventDefault(); closeDialog(); return; }
      if (e.key !== "Tab") return;
      var f = $$("a[href],button:not([disabled]),input,select,[tabindex='0']", dlg).filter(function (el) { return el.offsetParent !== null; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    function openDialog(dlg, opts) {
      closeDialog();
      var scrim = document.createElement("div"); scrim.className = "sp-scrim"; scrim.addEventListener("click", closeDialog);
      document.body.appendChild(scrim);
      var onKey = function (e) { trap(dlg, e); };
      document.addEventListener("keydown", onKey);
      openDlg = { dlg: dlg, scrim: scrim, onKey: onKey, back: opts.back || document.activeElement, onClose: opts.onClose };
      dlg.setAttribute("aria-modal", "true");
      document.body.classList.add("sp-locked");
      if (opts.focus) opts.focus.focus();
    }
    function closeDialog() {
      if (!openDlg) return;
      var o = openDlg; openDlg = null;
      o.scrim.remove(); document.removeEventListener("keydown", o.onKey);
      document.body.classList.remove("sp-locked");
      if (o.onClose) o.onClose();
      if (o.back && o.back.focus) o.back.focus();
    }
    function openForm(back) {
      if (!mobile.matches) { amt.focus(); return; }
      card.classList.add("open"); card.setAttribute("role", "dialog");
      openDialog(card, { back: back, focus: amt, onClose: function () { card.classList.remove("open"); card.removeAttribute("role"); card.removeAttribute("aria-modal"); } });
    }
    $("[data-sp-close]", card).addEventListener("click", closeDialog);
    function bindOpen(root) { $$("[data-sp-open-form]", root).forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.preventDefault();
        if (b.hasAttribute("data-sp-month-start")) {
          setDate([form.elements.jy.value, form.elements.jm.value, 1]); pickDay("other");
        }
        openForm(b);
      });
    }); }
    bindOpen(document);
    if (page.hasAttribute("data-sp-open")) {
      openForm(null);
      var sum0 = $("[data-sp-summary]"); if (sum0) sum0.focus();
    }

    /* ---------- category «n دستهٔ دیگر» ---------- */
    var rest = $("[data-sp-rest-toggle]");
    if (rest) rest.addEventListener("click", function () {
      var open = rest.getAttribute("aria-expanded") !== "true";
      $$("[data-sp-rest]").forEach(function (li) { li.hidden = !open; });
      rest.setAttribute("aria-expanded", String(open));
    });

    /* ---------- row menu + delete confirm ---------- */
    var menuOpen = null;
    function closeMenu(focusBack) {
      if (!menuOpen) return;
      menuOpen.menu.hidden = true; menuOpen.btn.setAttribute("aria-expanded", "false");
      if (focusBack) menuOpen.btn.focus();
      menuOpen = null;
    }
    function bindRows(root) {
      $$("[data-sp-dots]", root).forEach(function (btn) {
        var row = btn.closest("[data-sp-row]"), menu = $(".sp-menu", row);
        var items = $$("[role=menuitem]", menu);
        btn.addEventListener("click", function (e) {
          e.stopPropagation();
          var was = menuOpen && menuOpen.btn === btn;
          closeMenu(false);
          if (was) return;
          menu.hidden = false; btn.setAttribute("aria-expanded", "true");
          menuOpen = { btn: btn, menu: menu }; items[0].focus();
        });
        menu.addEventListener("keydown", function (e) {
          var i = items.indexOf(document.activeElement);
          if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
          if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
          if (e.key === "Escape") { e.preventDefault(); closeMenu(true); }
          if (e.key === "Tab") closeMenu(false);
        });
        $("[data-sp-del]", menu).addEventListener("click", function () { closeMenu(false); confirmDelete(row, btn); });
      });
    }
    document.addEventListener("click", function (e) { if (menuOpen && !menuOpen.menu.contains(e.target)) closeMenu(false); });
    function confirmDelete(row, back) {
      var d = document.createElement("div");
      d.className = "sp-sheet sp-confirm"; d.setAttribute("role", "alertdialog");
      d.setAttribute("aria-labelledby", "sp-ct"); d.setAttribute("aria-describedby", "sp-cd");
      var note = row.getAttribute("data-sp-note");
      var desc = row.getAttribute("data-sp-amount") + " تومان، " + row.getAttribute("data-sp-name") + (note ? "، " + note : "") + "، " + row.getAttribute("data-sp-rel") + ". حذف برگشت ندارد.";
      d.innerHTML = '<h2 id="sp-ct">این خرج حذف شود؟</h2><p class="sp-hint" id="sp-cd"></p><div class="sp-actions"><button type="button" class="btn btn-danger" data-sp-yes>حذف</button><button type="button" class="btn btn-ghost" data-sp-no>انصراف</button></div>';
      $("#sp-cd", d).textContent = desc;
      document.body.appendChild(d);
      $("[data-sp-no]", d).addEventListener("click", closeDialog);
      $("[data-sp-yes]", d).addEventListener("click", function () {
        var f = $("#sp-del-form"); f.action = "/profile/spends/" + row.getAttribute("data-sp-row") + "/delete"; f.submit();
      });
      openDialog(d, { back: back, focus: $("[data-sp-no]", d), onClose: function () { d.remove(); } });
    }
    bindRows(document);

    /* ---------- validation ---------- */
    var FIELDS = { amount_toman: amt, year: form.elements.year, month: form.elements.month, day: form.elements.day };
    function values() { return { amount: amt.value, year: FIELDS.year.value, month: FIELDS.month.value, day: FIELDS.day.value }; }
    function setErr(name, msg) {
      var input = FIELDS[name];
      var err = name === "category_id" ? $("#sp-category_id") : $("#err-" + name);
      if (err) err.textContent = msg || "";
      if (!input) return;
      input.closest("label").classList.toggle("sp-invalid", !!msg);
      if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
    }
    function summary(errs) {
      var old = $("[data-sp-summary]", card); if (old) old.remove();
      var keys = ORDER.filter(function (k) { return errs[k]; });
      if (!keys.length) return;
      var b = document.createElement("div");
      b.className = "v2-banner err sp-summary"; b.setAttribute("role", "alert"); b.tabIndex = -1; b.setAttribute("data-sp-summary", "");
      var inner = document.createElement("div");
      var s = document.createElement("strong"); s.textContent = fa(keys.length) + " مورد نیاز به اصلاح دارد"; inner.appendChild(s);
      keys.forEach(function (k, i) {
        var a = document.createElement("a"); a.href = k === "category_id" ? "#sp-category_id" : "#sp-" + k; a.textContent = SHORT[k];
        inner.appendChild(a); if (i < keys.length - 1) inner.appendChild(document.createTextNode("، "));
      });
      b.appendChild(inner); form.before(b); b.focus();
    }
    function showErrors(errs) {
      Object.keys(FIELDS).forEach(function (k) { setErr(k, errs[k]); });
      setErr("category_id", errs.category_id);
      if (errs.year || errs.month || errs.day) pickDay("other");
      summary(errs);
    }
    Object.keys(FIELDS).forEach(function (k) {
      FIELDS[k].addEventListener("blur", function () {
        if (!FIELDS[k].value.trim() && k === "amount_toman") { setErr(k, ""); return; }
        var e = validate(values()); setErr(k, e[k]);
        if (k === "year" || k === "month") setErr("day", e.day && FIELDS.day.value.trim() ? e.day : "");
      });
    });

    /* ---------- save ---------- */
    var submitBtn = $("[data-sp-submit]", form), cancel = $("[data-sp-cancel]", form), label = submitBtn.textContent, busy = false;
    function repaint() { setTimeout(function () { amt.dispatchEvent(new Event("blur")); }, 0); }
    function setBusy(on) {
      busy = on;
      submitBtn.setAttribute("aria-disabled", String(on)); cancel.setAttribute("aria-disabled", String(on));
      if (on) { submitBtn.innerHTML = '<span class="v2-spin" aria-hidden="true"></span> در حال ثبت…'; }
      else submitBtn.textContent = label;
    }
    cancel.addEventListener("click", function (e) { if (busy) e.preventDefault(); });
    function saveFailed() {
      var old = $("[data-sp-save-error]", card); if (old) old.remove();
      var b = document.createElement("div");
      b.className = "v2-banner err"; b.setAttribute("role", "alert"); b.setAttribute("data-sp-save-error", "");
      b.innerHTML = "<div><strong>ثبت نشد</strong>اتصال برقرار نشد. چیزی که نوشتید سر جایش مانده است.</div>";
      form.before(b);
      label = "دوباره ثبت کن"; submitBtn.textContent = label;
    }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy) return;
      repaint();
      var errs = validate(values());
      if (!cs.value) errs.category_id = "زیردسته را انتخاب کنید";
      if (Object.keys(errs).length) { showErrors(errs); return; }
      showErrors({});
      var old = $("[data-sp-save-error]", card); if (old) old.remove();
      if (!window.fetch || !window.FormData) { form.submit(); return; }
      var body = new FormData(form);
      setBusy(true);
      fetch(form.action, { method: "POST", body: body, headers: { Accept: "application/json" }, credentials: "same-origin" })
        .then(function (res) { return res.json().then(function (data) { return { res: res, data: data }; }); })
        .then(function (r) {
          if (r.data && r.data.ok && r.data.redirect) {
            if (window.LeaveGuard && window.LeaveGuard.clear) window.LeaveGuard.clear();
            form.removeAttribute("data-leave-warn");
            window.location.assign(r.data.redirect); return;
          }
          setBusy(false);
          if (r.res.status === 422 && r.data && r.data.fields) { showErrors(r.data.fields); return; }
          if (r.data && r.data.redirect) { window.location.assign(r.data.redirect); return; }
          saveFailed();
        })
        .catch(function () { setBusy(false); saveFailed(); });
    });

    /* ---------- list: «نمایش بیشتر» and month switch without reload ---------- */
    function loadInto(url, withSummary) {
      var list = $("[data-sp-list]"), sum = $("[data-sp-sum]");
      var skelTimer = setTimeout(function () { skeleton(list, sum, withSummary); }, 1000);
      list.setAttribute("aria-busy", "true");
      return fetch(url, { credentials: "same-origin" })
        .then(function (res) { if (!res.ok) throw new Error("http " + res.status); return res.text(); })
        .then(function (html) {
          clearTimeout(skelTimer);
          var doc = new DOMParser().parseFromString(html, "text/html");
          var nl = $("[data-sp-list]", doc); if (!nl) throw new Error("no list");
          list.replaceWith(nl); bindRows(nl); bindMore(nl); bindOpen(nl);
          if (withSummary) { var ns = $("[data-sp-sum]", doc); sum.replaceWith(ns); bindMonth(ns);
            var nf = $("[data-sp-page]", doc); // hidden jy/jm for the form follow the month
            form.elements.jy.value = $("[name=jy]", nf).value; form.elements.jm.value = $("[name=jm]", nf).value; }
          if (history.replaceState) history.replaceState(null, "", url);
        })
        .catch(function () {
          clearTimeout(skelTimer);
          var cur = $("[data-sp-list]"); cur.removeAttribute("aria-busy");
          $$("[data-sp-days],[data-sp-count],[data-sp-more],[data-sp-empty],.sp-skel-rows,[data-sp-loadfail]", cur).forEach(function (el) { el.remove(); });
          var b = document.createElement("div");
          b.className = "v2-banner err"; b.setAttribute("role", "alert"); b.setAttribute("data-sp-loadfail", "");
          b.innerHTML = '<div><strong>فهرست خرج‌ها باز نشد</strong>اتصال را بررسی کنید و دوباره امتحان کنید.</div><button type="button" class="btn">دوباره</button>';
          $("button", b).addEventListener("click", function () { loadInto(url, withSummary); });
          cur.appendChild(b);
        });
    }
    function skeleton(list, sum, withSummary) {
      $$("[data-sp-days],[data-sp-more],[data-sp-empty]", list).forEach(function (el) { el.hidden = true; });
      var c = $("[data-sp-count]", list) || list.appendChild(document.createElement("p"));
      c.className = "sp-count"; c.setAttribute("role", "status"); c.textContent = "در حال بارگذاری خرج‌های ماه";
      var box = document.createElement("div"); box.className = "sp-skel-rows"; box.setAttribute("aria-hidden", "true");
      for (var i = 0; i < 5; i++) box.innerHTML += '<div class="sp-row"><i class="v2-skel" style="width:36px;height:36px;border-radius:50%"></i><span><i class="v2-skel" style="width:60%;height:14px"></i><i class="v2-skel" style="width:40%;height:12px;margin-top:8px"></i></span><i class="v2-skel" style="width:70px;height:16px"></i><span></span></div>';
      list.appendChild(box);
      if (withSummary) {
        $$(".sp-tile b", sum).forEach(function (b) { b.innerHTML = '<i class="v2-skel" style="width:110px;height:22px;margin-top:6px"></i>'; });
        $$(".sp-bars li", sum).forEach(function (li) { li.innerHTML = '<i class="v2-skel" style="width:40%;height:14px"></i><i></i><i class="v2-skel bar" style="height:8px"></i>'; li.setAttribute("aria-hidden", "true"); });
        sum.setAttribute("aria-busy", "true");
      }
    }
    function bindMore(root) {
      $$("[data-sp-more]", root).forEach(function (a) { a.addEventListener("click", function (e) { e.preventDefault(); loadInto(a.href, false); }); });
    }
    function bindMonth(root) {
      $$("[data-sp-month]", root).forEach(function (a) { a.addEventListener("click", function (e) { e.preventDefault(); loadInto(a.href, true); }); });
    }
    bindMore(document); bindMonth(document);
    window.__spLoad = loadInto; // used by the shot script to drive loading/loadfail
  });
})();
