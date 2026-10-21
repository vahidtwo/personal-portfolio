/* Debts v2 (/profile?tab=debts): sheets, row menus, in-app delete, «پرداخت شد» and per-field validation.
   Validation mirrors app/debt_validation.py (tests/test_debts_v2.py runs both on the same cases). */
(function () {
  var W = typeof window !== "undefined" ? window : {};
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  var MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  function N() { return W.NumberFa || (typeof require === "function" ? require("./number-format.js") : null); }
  function fa(n) { return String(n).replace(/\d/g, function (d) { return FA[Number(d)]; }); }
  var MSG = {
    amountFormat: "مبلغ را بدون ممیز بنویسید؛ مثلاً ۲٬۵۰۰٬۰۰۰",
    amountPositive: "مبلغ باید بیشتر از صفر باشد",
    months: "دست‌کم ۱ قسط باید مانده باشد",
    year: "سال را چهاررقمی بنویسید",
    month: "ماه بین ۱ تا ۱۲ است",
    expDay: "روز بین ۱ تا ۳۱ است",
    day: function (n) { return "این ماه " + fa(n) + " روز دارد"; },
  };
  var SHORT = { monthly_toman: "مبلغ هر قسط", months_left: "تعداد قسط مانده", due_year: "سال", due_month: "ماه", due_day: "روز", amount_toman: "مبلغ" };
  var DEBT_ORDER = ["monthly_toman", "months_left", "due_year", "due_month", "due_day"];

  function norm(raw) { try { return N().normalize(raw); } catch (e) { return null; } }
  function intOf(raw) { var t = norm(raw); return t && /^\d+$/.test(t) ? Number(t) : null; }
  function isLeap(y) { return [1, 5, 9, 13, 17, 22, 26, 30].indexOf(y % 33) !== -1; } // jdatetime's rule
  function monthLength(y, m) { return m <= 6 ? 31 : m <= 11 ? 30 : (isLeap(y) ? 30 : 29); }
  function amountError(raw, orig) {
    var t = norm(raw);
    if (t === null) return MSG.amountFormat;
    if (/^-/.test(t) && /[1-9]/.test(t)) return MSG.amountPositive;
    if (t.indexOf(".") !== -1 && !(orig && Number(t) === Number(orig))) return MSG.amountFormat;
    if (!(Number(t || "0") > 0)) return MSG.amountPositive;
    return null;
  }
  function validateDebt(v) {
    var e = {}, a = amountError(v.monthly_toman, v.orig);
    if (a) e.monthly_toman = a;
    var n = intOf(v.months_left);
    if (n === null || n < 1) e.months_left = MSG.months;
    var y = intOf(v.due_year), m = intOf(v.due_month), d = intOf(v.due_day);
    if (y === null || y < 1000 || y > 9999) e.due_year = MSG.year;
    if (m === null || m < 1 || m > 12) e.due_month = MSG.month;
    if (!e.due_year && !e.due_month) {
      var len = monthLength(y, m);
      if (d === null || d < 1 || d > len) e.due_day = MSG.day(len);
    } else if (d === null || d < 1 || d > 31) e.due_day = MSG.day(31);
    var out = {};
    DEBT_ORDER.forEach(function (k) { if (e[k]) out[k] = e[k]; });
    return out;
  }
  function validateExpense(v) {
    var e = {}, a = amountError(v.amount_toman, v.orig);
    if (a) e.amount_toman = a;
    var d = intOf(v.due_day);
    if (d === null || d < 1 || d > 31) e.due_day = MSG.expDay;
    return e;
  }
  function groupFa(n) { return fa(String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",")).replace(/,/g, "٬"); }
  /* «جمع مانده: … تومان، آخرین قسط: ۱۰ تیر ۱۴۰۶» or "" while the form is incomplete/invalid. */
  function preview(v) {
    if (Object.keys(validateDebt(v)).length) return "";
    var amount = Number(norm(v.monthly_toman)), n = intOf(v.months_left), y = intOf(v.due_year), m = intOf(v.due_month), d = intOf(v.due_day);
    var idx = y * 12 + (m - 1) + (n - 1), ey = Math.floor(idx / 12), em = idx % 12 + 1;
    var ed = Math.min(d, monthLength(ey, em));
    return "جمع مانده: " + groupFa(amount * n) + " تومان، آخرین قسط: " + fa(ed) + " " + MONTHS[em - 1] + " " + fa(ey);
  }
  W.DebtsValidate = { validateDebt: validateDebt, validateExpense: validateExpense, preview: preview, monthLength: monthLength };
  if (typeof module !== "undefined" && module.exports) module.exports = W.DebtsValidate;
  if (typeof document === "undefined" || !document.querySelector) return;

  var URL_ = "/profile?tab=debts";
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  var page, scrim, openSheet = null, opener = null, openMenu = null;

  function focusables(el) {
    return $$('a[href],button:not([disabled]),input:not([type=hidden]):not([disabled]),[tabindex]:not([tabindex="-1"])', el)
      .filter(function (x) { return x.getClientRects().length; });
  }
  function closeMenu() {
    if (!openMenu) return;
    openMenu.menu.hidden = true;
    openMenu.btn.setAttribute("aria-expanded", "false");
    openMenu = null;
  }
  function show(sheet, from, initial) {
    closeMenu();
    if (openSheet && openSheet !== sheet) openSheet.hidden = true;
    opener = from || document.activeElement;
    sheet.hidden = false; scrim.hidden = false; openSheet = sheet;
    document.documentElement.classList.add("dv-locked");
    var f = initial || $("[data-dv-initial]", sheet) || $("input:not([type=hidden])", sheet) || focusables(sheet)[0];
    if (f) setTimeout(function () { f.focus(); }, 0);
  }
  function hide() {
    if (!openSheet) return;
    if ($("[data-dv-submit][aria-disabled=true]", openSheet)) return; // saving: «انصراف» is disabled
    openSheet.hidden = true; scrim.hidden = true; openSheet = null;
    document.documentElement.classList.remove("dv-locked");
    if (opener && document.contains(opener)) opener.focus();
  }
  function formValues(form) {
    var v = {};
    $$("input", form).forEach(function (i) { if (i.name) v[i.name] = i.value; });
    var orig = $("[data-dv-orig]", form);
    v.orig = orig ? orig.getAttribute("data-dv-orig") : "";
    return v;
  }
  function prefix(form) { return form.getAttribute("data-dv-form") === "expense" ? "dvx-" : "dv-"; }
  function setErr(form, field, msg) {
    var p = prefix(form), input = $("#" + p + field, form), slot = $("#" + p + "err-" + field, form);
    if (slot) slot.textContent = msg || "";
    if (input) { if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid"); }
  }
  function errorsFor(form) {
    var v = formValues(form);
    return form.getAttribute("data-dv-form") === "expense" ? validateExpense(v) : validateDebt(v);
  }
  function fields(form) { return form.getAttribute("data-dv-form") === "expense" ? ["amount_toman", "due_day"] : DEBT_ORDER; }
  function showErrors(form, errs) {
    var sheet = form.closest("[data-dv-sheet]"), sum = $("[data-dv-summary]", sheet), p = prefix(form);
    fields(form).forEach(function (k) { setErr(form, k, errs[k]); });
    var keys = Object.keys(errs);
    if (!keys.length) { sum.hidden = true; sum.innerHTML = ""; return; }
    sum.innerHTML = "";
    var strong = document.createElement("strong");
    strong.textContent = fa(keys.length) + " مورد نیاز به اصلاح دارد";
    sum.appendChild(strong);
    keys.forEach(function (k) {
      var a = document.createElement("a"); a.href = "#" + p + k; a.textContent = SHORT[k] || k; sum.appendChild(a);
    });
    sum.hidden = false;
    sum.setAttribute("tabindex", "-1");
    sum.focus();
  }
  function repaint(form) {
    // amount-input.js strips [data-thousands] to Latin on submit; paint Persian digits back.
    setTimeout(function () {
      $$("[data-thousands]", form).forEach(function (i) { i.dispatchEvent(new Event("blur")); });
      $$("input[inputmode=numeric]:not([data-thousands])", form).forEach(function (i) { i.value = fa(i.value); });
    }, 0);
  }
  function updatePreview(form) {
    var box = $("[data-dv-preview]", form);
    if (!box) return;
    var text = preview(formValues(form));
    box.textContent = text; box.hidden = !text;
  }
  function fillForm(kind, data, id) {
    var sheet = $('[data-dv-sheet="' + kind + '"]'), form = $("form", sheet), title = $("h2", sheet), submit = $("[data-dv-submit]", form);
    var editing = !!data;
    form.action = editing ? (kind === "debt" ? "/profile/debts/" : "/profile/expenses/") + id : form.getAttribute("data-action-add");
    title.textContent = title.getAttribute(editing ? "data-title-edit" : "data-title-add");
    submit.textContent = submit.getAttribute(editing ? "data-label-edit" : "data-label-add");
    $$("input:not([type=hidden])", form).forEach(function (i) {
      var val = data ? (data[i.name] == null ? "" : String(data[i.name])) : "";
      i.value = i.hasAttribute("data-thousands") ? val : fa(val);
      if (i.hasAttribute("data-thousands")) {
        if (data && data.orig) i.setAttribute("data-dv-orig", data.orig); else i.removeAttribute("data-dv-orig");
        i.dispatchEvent(new Event("blur"));
      }
    });
    showErrors(form, {});
    $("[data-dv-fail]", form).hidden = true;
    updatePreview(form);
    return sheet;
  }
  function busy(form, on) {
    var submit = $("[data-dv-submit]", form), cancel = $(".form-actions [data-dv-close]", form);
    if (on) {
      submit.setAttribute("data-idle", submit.textContent);
      submit.innerHTML = '<span class="dv-spin" aria-hidden="true"></span><span>در حال ذخیره…</span>';
      submit.setAttribute("aria-disabled", "true"); cancel.setAttribute("aria-disabled", "true"); cancel.disabled = true;
    } else {
      submit.textContent = submit.getAttribute("data-idle") || submit.textContent;
      submit.removeAttribute("aria-disabled"); cancel.removeAttribute("aria-disabled"); cancel.disabled = false;
    }
  }

  /* Re-read the page and swap the data regions (summary numbers, lists, banners). */
  var loadTimer = null;
  function setLoading(on) {
    $$("[data-dv-list]").forEach(function (l) { l.classList.toggle("dv-loading", on); if (on) l.setAttribute("aria-busy", "true"); else l.removeAttribute("aria-busy"); });
    page.classList.toggle("dv-loading-page", on);
  }
  function refresh() {
    var fail = $("[data-dv-loadfail]");
    clearTimeout(loadTimer);
    loadTimer = setTimeout(function () { setLoading(true); }, 1000); // skeletons only after 1s
    return fetch(URL_, { credentials: "same-origin", cache: "no-store", headers: { Accept: "text/html" } })
      .then(function (r) { if (!r.ok) throw new Error("load " + r.status); return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var fresh = doc.querySelector("[data-dv-page]");
        if (!fresh) throw new Error("no page");
        $$("[data-dv-swap]").forEach(function (el) {
          var n = fresh.querySelector('[data-dv-swap="' + el.getAttribute("data-dv-swap") + '"]');
          if (n) el.innerHTML = n.innerHTML;
        });
        var nums = $$("[data-dv-num]", fresh), mine = $$("[data-dv-num]");
        if (nums.length !== mine.length || !!fresh.querySelector("#dv-sum-h") !== !!$("#dv-sum-h") ||
            (fresh.querySelector("#dv-sum-h") || {}).textContent !== ($("#dv-sum-h") || {}).textContent ||
            !!fresh.querySelector('[data-dv-list="debts"] .dv-chead .btn') !== !!$('[data-dv-list="debts"] .dv-chead .btn') ||
            !!fresh.querySelector('[data-dv-list="expenses"] .dv-chead .btn') !== !!$('[data-dv-list="expenses"] .dv-chead .btn')) {
          location.replace(URL_); // empty <-> filled: the page shape changed, load it whole
          return;
        }
        mine.forEach(function (el, i) { el.innerHTML = nums[i].innerHTML; });
        var reveal = $('[data-salary-reveal][aria-pressed="false"]');
        if (reveal) reveal.click(); // مانده changed: mask again (privacy.js re-fetches on the next tap)
        fail.hidden = true;
      })
      .catch(function () {
        $$("[data-dv-num]").forEach(function (el) { el.textContent = "—"; });
        fail.hidden = false;
      })
      .then(function () { clearTimeout(loadTimer); setLoading(false); });
  }
  W.DebtsRefresh = refresh;

  function postForm(form, accept) {
    return fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin", headers: { Accept: accept || "application/json" } });
  }

  function onSubmit(ev) {
    var form = ev.target;
    if (form.matches("[data-dv-form]")) {
      ev.preventDefault();
      var submit = $("[data-dv-submit]", form);
      if (submit.getAttribute("aria-disabled") === "true") return;
      var errs = errorsFor(form);
      if (Object.keys(errs).length) { showErrors(form, errs); repaint(form); return; }
      showErrors(form, {});
      $("[data-dv-fail]", form).hidden = true;
      busy(form, true);
      var body = new FormData(form);
      repaint(form); // keep Persian digits on screen while saving (amount-input.js stripped them for the POST)
      fetch(form.action, { method: "POST", body: body, credentials: "same-origin", headers: { Accept: "application/json" } }).then(function (r) {
        return r.json().then(function (body) { return { status: r.status, body: body }; });
      }).then(function (res) {
        busy(form, false);
        if (res.body && res.body.ok) { hide(); refresh(); return; }
        if (res.status === 422 && res.body && res.body.fields) { showErrors(form, res.body.fields); repaint(form); return; }
        throw new Error("save");
      }).catch(function () {
        busy(form, false);
        var f = $("[data-dv-fail]", form); f.hidden = false;
        $("[data-dv-submit]", form).textContent = "دوباره ذخیره کن";
        repaint(form);
      });
      return;
    }
    if (form.matches("[data-dv-action]")) {
      ev.preventDefault();
      var btn = $("button[type=submit]", form);
      if (btn) btn.setAttribute("aria-disabled", "true");
      postForm(form).then(function () {
        if (openSheet) { openSheet.hidden = true; scrim.hidden = true; openSheet = null; document.documentElement.classList.remove("dv-locked"); }
        closeMenu();
        return refresh();
      }).catch(function () { $("[data-dv-loadfail]").hidden = false; })
        .then(function () { if (btn) btn.removeAttribute("aria-disabled"); });
    }
  }

  function onClick(ev) {
    var t = ev.target.closest("button,a,[data-dv-scrim]");
    if (openMenu && (!t || !openMenu.menu.contains(t)) && t !== openMenu.btn) closeMenu();
    if (!t) return;
    if (t.matches("[data-dv-add]")) {
      show(fillForm(t.getAttribute("data-dv-add"), null), t);
    } else if (t.matches("[data-dv-edit]")) {
      ev.preventDefault();
      var data = JSON.parse(t.getAttribute("data-form"));
      var kind = t.getAttribute("data-dv-edit");
      var row = t.closest("[data-dv-row]");
      show(fillForm(kind, data, t.getAttribute("data-id")), row ? $("[data-dv-dots]", row) : t);
    } else if (t.matches("[data-dv-close]") || t.matches("[data-dv-scrim]")) {
      if (t.disabled) return;
      hide();
    } else if (t.matches("[data-dv-dots]")) {
      var menu = $("[data-dv-menu]", t.closest("[data-dv-row]"));
      if (openMenu && openMenu.menu === menu) { closeMenu(); return; }
      closeMenu();
      menu.hidden = false; t.setAttribute("aria-expanded", "true"); openMenu = { menu: menu, btn: t };
      var first = $("[role=menuitem]", menu); if (first) first.focus();
    } else if (t.matches("[data-dv-del]")) {
      var sheet = $('[data-dv-sheet="delete"]'), btnRow = t.closest("[data-dv-row]");
      $("[data-dv-del-title]", sheet).textContent = "«" + t.getAttribute("data-title") + "» حذف شود؟";
      $("[data-dv-del-body]", sheet).textContent = t.getAttribute("data-body");
      var hint = $("[data-dv-del-hint]", sheet); hint.textContent = t.getAttribute("data-hint"); hint.hidden = !t.getAttribute("data-hint");
      $("[data-dv-del-form]", sheet).action = t.getAttribute("data-action");
      show(sheet, btnRow ? $("[data-dv-dots]", btnRow) : t);
    } else if (t.matches("[data-dv-retry]")) {
      refresh();
    }
  }

  function onKey(ev) {
    if (openMenu) {
      var items = $$("[role=menuitem]", openMenu.menu), i = items.indexOf(document.activeElement);
      if (ev.key === "Escape") { var b = openMenu.btn; closeMenu(); b.focus(); ev.preventDefault(); return; }
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        var n = (i + (ev.key === "ArrowDown" ? 1 : -1) + items.length) % items.length; items[n].focus(); return;
      }
    }
    if (!openSheet) return;
    if (ev.key === "Escape") { ev.preventDefault(); hide(); return; }
    if (ev.key === "Tab") {
      var f = focusables(openSheet); if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
  }

  function init() {
    page = $("[data-dv-page]");
    if (!page) return;
    scrim = $("[data-dv-scrim]");
    document.addEventListener("submit", onSubmit);
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    $$("[data-dv-form]").forEach(function (form) {
      form.addEventListener("focusout", function (ev) {
        var input = ev.target;
        if (!input.name || !input.matches("input")) return;
        var k = input.name, errs = errorsFor(form);
        if (fields(form).indexOf(k) !== -1 && (input.value.trim() || input.getAttribute("aria-invalid"))) setErr(form, k, errs[k]);
        if (input.matches("input[inputmode=numeric]:not([data-thousands])")) input.value = fa(input.value);
      });
      form.addEventListener("input", function () { updatePreview(form); });
      updatePreview(form);
    });
    var open = page.getAttribute("data-dv-open");
    if (open) {
      var sheet = $('[data-dv-sheet="' + open + '"]');
      var bad = $("[aria-invalid=true]", sheet);
      show(sheet, $('[data-dv-add="' + open + '"]'), bad || undefined);
      var sum = $("[data-dv-summary]:not([hidden])", sheet);
      if (sum) { sum.setAttribute("tabindex", "-1"); setTimeout(function () { sum.focus(); }, 0); }
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
