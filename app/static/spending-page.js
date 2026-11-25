/* Spending v2 + quick category sheet, merchant memory, instant delete + 8s undo toast,
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
  var SHORT = { amount_toman: "مبلغ", category_id: "دسته", year: "سال", month: "ماه", day: "روز" };
  var ORDER = ["amount_toman", "category_id", "year", "month", "day"];
  var CAT_STORAGE_KEY = "daraiito:last-spend-cat";

  function intOf(raw) {
    var t = N().normalize(raw);
    return t && /^\d+$/.test(t) ? Number(t) : null;
  }
  function isLeap(y) { return [1, 5, 9, 13, 17, 22, 26, 30].indexOf(y % 33) !== -1; } // jdatetime's rule
  function monthLength(y, m) { return m <= 6 ? 31 : m <= 11 ? 30 : (isLeap(y) ? 30 : 29); }

  /* {field: message} for every bad field; mirrors spend_validation.validate_spend. */
  function validate(v) {
    // v.orig: the stored amount when editing; an unchanged legacy fraction may be saved again.
    var e = {};
    var t = N().normalize(v.amount);
    if (t === null) e.amount_toman = MSG.amountFormat;
    else if (/^-/.test(t) && /[1-9]/.test(t)) e.amount_toman = MSG.amountPositive;
    else if (t.indexOf(".") !== -1 && !(v.orig && Number(t) === Number(v.orig))) e.amount_toman = MSG.amountFormat;
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
    var wrap = amt.closest(".sp-amt");
    var amtErr = $("#err-amount_toman"), slot = document.createElement("div");
    slot.className = "sp-amt-msg"; amtErr.before(slot); slot.appendChild(amtErr);
    var words = $(".amount-words", wrap), sugg = $(".amount-suggest", wrap);
    if (words) slot.appendChild(words);
    if (sugg) slot.after(sugg);

    function fitTileAmounts() {
      $$(".sp-tile b").forEach(function (b) {
        b.style.fontSize = "";
        var box = b.parentElement, csStyle = getComputedStyle(box);
        var avail = box.clientWidth - parseFloat(csStyle.paddingLeft) - parseFloat(csStyle.paddingRight);
        var f = parseFloat(getComputedStyle(b).fontSize);
        while (avail > 0 && b.scrollWidth > avail && f > 13) {
          f -= 0.5;
          b.style.setProperty("font-size", f + "px", "important");
        }
      });
    }
    fitTileAmounts();

    function csrfToken() { return (form.elements.csrf && form.elements.csrf.value) || ""; }

    function readLastCategory() {
      try {
        var raw = window.localStorage.getItem(CAT_STORAGE_KEY);
        if (!raw) return null;
        var parsed = JSON.parse(raw);
        if (!parsed || !parsed.parent_id || !parsed.category_id) return null;
        var pOpt = $$("option", ps).find(function (o) { return o.value === String(parsed.parent_id) && o.getAttribute("data-slug") !== "sms"; });
        var cOpt = $$("option", cs).find(function (o) { return o.value === String(parsed.category_id) && o.getAttribute("data-parent") === String(parsed.parent_id); });
        return (pOpt && cOpt) ? { parent_id: pOpt.value, category_id: cOpt.value } : null;
      } catch (_e) {
        return null;
      }
    }
    function writeLastCategory(pid, cid) {
      if (!pid || !cid) return;
      var pOpt = $$("option", ps).find(function (o) { return o.value === String(pid); });
      if (pOpt && pOpt.getAttribute("data-slug") === "sms") return;
      try { window.localStorage.setItem(CAT_STORAGE_KEY, JSON.stringify({ parent_id: String(pid), category_id: String(cid) })); } catch (_e) {}
    }

    /* ---------- chips (no silent auto-pick on first use) ---------- */
    var pChips = $("[data-sp-pchips]"), cChips = $("[data-sp-cchips]"), cLabel = $("#sp-cl");
    if (!page.hasAttribute("data-sp-editing") && !ps.value && !cs.value && !$("[data-sp-summary]", card)) {
      var lastCat = readLastCategory();
      if (lastCat) { ps.value = lastCat.parent_id; cs.value = lastCat.category_id; }
    }
    function drawKids() {
      cChips.innerHTML = "";
      var kids = ps.value ? $$("option", cs).filter(function (o) { return o.value && o.getAttribute("data-parent") === ps.value; }) : [];
      var show = kids.length > 0;
      if (cLabel) cLabel.hidden = !show;
      cChips.hidden = !show;
      if (!kids.some(function (o) { return o.value === cs.value; })) cs.value = "";
      kids.forEach(function (o) {
        var b = document.createElement("button");
        b.type = "button"; b.textContent = o.textContent;
        b.setAttribute("aria-pressed", String(o.value === cs.value));
        b.addEventListener("click", function () {
          cs.value = o.value;
          setErr("category_id", "");
          drawKids();
        });
        cChips.appendChild(b);
      });
    }
    function drawParents() {
      pChips.innerHTML = "";
      $$("option", ps).forEach(function (o) {
        if (!o.value) return;
        if (o.getAttribute("data-slug") === "sms" && o.value !== ps.value) return;
        var b = document.createElement("button");
        b.type = "button";
        var sw = document.createElement("span"); sw.className = "sw"; sw.setAttribute("aria-hidden", "true");
        sw.style.background = o.getAttribute("data-color") || "#475569";
        b.appendChild(sw); b.appendChild(document.createTextNode(o.textContent.trim()));
        b.setAttribute("aria-pressed", String(o.value === ps.value));
        b.addEventListener("click", function () {
          ps.value = o.value;
          cs.value = "";
          setErr("category_id", "");
          drawParents();
          drawKids();
        });
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

    /* ---------- dialogs (add/edit sheet, quick category sheet) ---------- */
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
      var scrim = document.createElement("div"); scrim.className = opts.scrimClass || "sp-scrim"; scrim.addEventListener("click", closeDialog);
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
    function bindRestToggle(root) {
      var rest = $("[data-sp-rest-toggle]", root || document);
      if (rest) rest.addEventListener("click", function () {
        var open = rest.getAttribute("aria-expanded") !== "true";
        $$("[data-sp-rest]").forEach(function (li) { li.hidden = !open; });
        rest.setAttribute("aria-expanded", String(open));
      });
    }
    bindRestToggle(document);

    /* ---------- toast (8s undo + offline warn) ---------- */
    var activeToast = null;
    function dismissToast() {
      if (!activeToast) return;
      clearTimeout(activeToast.timer);
      if (activeToast.raf) cancelAnimationFrame(activeToast.raf);
      activeToast.el.remove();
      activeToast = null;
    }
    function showUndoToast(text, actionLabel, onAction) {
      dismissToast();
      var el = document.createElement("div");
      el.className = "p6-toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      var C = 69;
      el.innerHTML = '<svg class="p6-timer" viewBox="0 0 28 28" aria-hidden="true">' +
        '<circle cx="14" cy="14" r="11" fill="none" stroke="currentColor" stroke-opacity=".25" stroke-width="2.5"/>' +
        '<circle cx="14" cy="14" r="11" fill="none" stroke="currentColor" stroke-width="2.5" stroke-dasharray="' + C + '" stroke-dashoffset="0" transform="rotate(-90 14 14)" stroke-linecap="round"/>' +
        '</svg><span></span><button type="button"></button>';
      $("span", el).textContent = text;
      var btn = $("button", el);
      btn.textContent = actionLabel;
      var arc = $$("circle", el)[1];
      var started = Date.now(), duration = 8000, acting = false;
      var state = { el: el, timer: null, raf: null };
      function tick() {
        var pct = Math.min(1, (Date.now() - started) / duration);
        arc.setAttribute("stroke-dashoffset", (C * pct).toFixed(1));
        if (pct < 1 && activeToast === state) state.raf = requestAnimationFrame(tick);
      }
      if (typeof requestAnimationFrame === "function") state.raf = requestAnimationFrame(tick);
      state.timer = setTimeout(function () { if (activeToast === state) dismissToast(); }, duration);
      btn.addEventListener("click", function () {
        if (acting) return;
        acting = true;
        btn.disabled = true;
        Promise.resolve(onAction()).then(function (ok) {
          if (ok !== false && activeToast === state) dismissToast();
          else { acting = false; btn.disabled = false; }
        });
      });
      document.body.appendChild(el);
      activeToast = state;
    }
    function showWarnToast(text) {
      dismissToast();
      var el = document.createElement("div");
      el.className = "p6-toast warn";
      el.setAttribute("role", "alert");
      el.setAttribute("aria-live", "polite");
      var span = document.createElement("span");
      span.textContent = text || "ذخیره نشد؛ دوباره بزنید";
      el.appendChild(span);
      document.body.appendChild(el);
      var state = { el: el, timer: null, raf: null };
      state.timer = setTimeout(function () { if (activeToast === state) dismissToast(); }, 5000);
      activeToast = state;
    }

    function refreshSummary() {
      var url = window.location.href;
      return fetch(url, { credentials: "same-origin" })
        .then(function (res) { if (!res.ok) throw new Error("http " + res.status); return res.text(); })
        .then(function (html) {
          var doc = new DOMParser().parseFromString(html, "text/html");
          var curSum = $("[data-sp-sum]"), newSum = $("[data-sp-sum]", doc);
          if (curSum && newSum) {
            curSum.replaceWith(newSum);
            bindMonth(newSum);
            bindRestToggle(newSum);
            fitTileAmounts();
          }
          var curCount = $("[data-sp-count]"), newCount = $("[data-sp-count]", doc);
          if (curCount && newCount) curCount.textContent = newCount.textContent;
          $$(".sp-day", doc).forEach(function (nd) {
            var label = nd.getAttribute("aria-label");
            var od = $$(".sp-day").find(function (x) { return x.getAttribute("aria-label") === label; });
            if (od) {
              var oh = $(".sp-dayh", od), nh = $(".sp-dayh", nd);
              if (oh && nh) oh.replaceWith(nh);
            }
          });
          if (window.Amounts) window.Amounts.refresh(url);
        })
        .catch(function () {});
    }

    /* ---------- row category update + quick category sheet ---------- */
    function applyRowCategory(row, data) {
      row.setAttribute("data-sp-parent-id", String(data.parent_id || ""));
      row.setAttribute("data-sp-category-id", String(data.category_id || ""));
      row.setAttribute("data-sp-name", data.child_name || "");
      row.setAttribute("data-sp-source", data.category_source || "");
      row.setAttribute("data-sp-sms-bank", data.is_sms_bank ? "1" : "0");
      var ic = $(".sp-ic", row);
      if (ic) { ic.style.background = data.color || "#475569"; ic.textContent = data.initial || ""; }
      var titleEl = $(".t b", row);
      if (titleEl) titleEl.textContent = data.child_name || "";
      var small = $(".t small", row);
      if (small) {
        small.innerHTML = "";
        if (data.from_sms) {
          var smsTag = document.createElement("span");
          smsTag.className = "tag tag-sms sp-tag";
          smsTag.title = "ثبت خودکار از پیامک";
          smsTag.textContent = "از پیامک";
          small.appendChild(smsTag);
        }
        if (data.category_source === "learned") {
          var lTag = document.createElement("span");
          lTag.className = "p6-learned";
          lTag.textContent = "دستهٔ یادگرفته";
          small.appendChild(lTag);
        }
        var noteText = data.note_display || row.getAttribute("data-sp-note") || "";
        small.appendChild(document.createTextNode((data.parent_name || "") + (noteText ? "، " + noteText : "")));
      }
      var existingQ = $("[data-sp-catq]", row);
      if (data.is_sms_bank) {
        row.classList.add("p6-has-q");
        if (!existingQ) {
          var qBtn = document.createElement("button");
          qBtn.type = "button"; qBtn.className = "p6-catq";
          qBtn.setAttribute("aria-haspopup", "dialog");
          qBtn.setAttribute("data-sp-catq", "");
          var lblNote = row.getAttribute("data-sp-note") || data.child_name || "";
          qBtn.setAttribute("aria-label", "انتخاب دسته برای خرج " + lblNote);
          qBtn.textContent = "دسته؟";
          qBtn.addEventListener("click", function () { openCatSheet(row, qBtn); });
          $(".t", row).appendChild(qBtn);
        }
      } else {
        row.classList.remove("p6-has-q");
        if (existingQ) existingQ.remove();
      }
      var dots = $("[data-sp-dots]", row);
      if (dots) dots.setAttribute("aria-label", "گزینه‌های خرج " + (data.child_name || "") + "، " + (row.getAttribute("data-sp-rel") || ""));
      row.classList.add("p6-flash");
      setTimeout(function () { row.classList.remove("p6-flash"); }, 1800);
    }

    function openCatSheet(row, back) {
      var spendId = row.getAttribute("data-sp-row");
      var merchant = (row.getAttribute("data-sp-merchant") || "").trim();
      var note = (row.getAttribute("data-sp-note") || "").trim();
      var rel = (row.getAttribute("data-sp-rel") || "").trim();
      var fromSms = row.getAttribute("data-sp-from-sms") === "1";
      var shown = document.documentElement.getAttribute("data-show-portfolio") === "1";
      var amtEl = shown ? $(".a [data-amount]", row) : null;

      var sheet = document.createElement("section");
      sheet.className = "p6-sheet";
      sheet.setAttribute("role", "dialog");
      sheet.setAttribute("aria-labelledby", "p6-cat-h");
      sheet.innerHTML = '<div class="p6-handle" aria-hidden="true"></div>' +
        '<div class="p6-shead"><h2 id="p6-cat-h">دستهٔ این خرج</h2><button type="button" class="sp-x" aria-label="بستن" style="display:grid">✕</button></div>' +
        '<p class="p6-spend"></p>';

      var spendLine = $(".p6-spend", sheet);
      if (amtEl) {
        var b = document.createElement("b");
        var bdi = document.createElement("bdi");
        bdi.setAttribute("dir", "ltr"); bdi.className = "num"; bdi.style.unicodeBidi = "isolate";
        bdi.textContent = amtEl.textContent.trim();
        b.appendChild(bdi); b.appendChild(document.createTextNode(" تومان"));
        spendLine.appendChild(b);
      }
      var metaParts = [];
      if (fromSms) metaParts.push("از پیامک");
      if (note) metaParts.push(note);
      if (rel) metaParts.push(rel);
      var metaSpan = document.createElement("span");
      metaSpan.textContent = metaParts.join("، ");
      spendLine.appendChild(metaSpan);

      var rememberInput = null;
      if (merchant) {
        var chkLabel = document.createElement("label");
        chkLabel.className = "p6-check";
        rememberInput = document.createElement("input");
        rememberInput.type = "checkbox";
        var txt = document.createElement("span");
        txt.textContent = "برای «" + merchant + "» همیشه همین دسته";
        var helper = document.createElement("small");
        helper.textContent = "فقط پیامک‌های بعدی؛ خرج‌های قبلی عوض نمی‌شوند.";
        txt.appendChild(helper);
        chkLabel.appendChild(rememberInput); chkLabel.appendChild(txt);
        rememberInput.addEventListener("change", function () { chkLabel.classList.toggle("on", rememberInput.checked); });
        sheet.appendChild(chkLabel);
      }

      var catsBox = document.createElement("div");
      catsBox.className = "sp-cats"; catsBox.style.display = "block";
      var pLab = document.createElement("span"); pLab.className = "sp-flabel"; pLab.id = "p6-pl"; pLab.textContent = "دسته";
      var pGroup = document.createElement("div"); pGroup.className = "sp-chips"; pGroup.setAttribute("role", "group"); pGroup.setAttribute("aria-labelledby", "p6-pl");
      var cLab = document.createElement("span"); cLab.className = "sp-flabel"; cLab.id = "p6-cl"; cLab.style.marginTop = "14px"; cLab.textContent = "زیردسته"; cLab.hidden = true;
      var cNote = document.createElement("span"); cNote.className = "p6-fieldnote"; cNote.textContent = "با زدن زیردسته ذخیره می‌شود."; cNote.hidden = true;
      var cGroup = document.createElement("div"); cGroup.className = "sp-chips"; cGroup.setAttribute("role", "group"); cGroup.setAttribute("aria-labelledby", "p6-cl"); cGroup.hidden = true;
      catsBox.appendChild(pLab); catsBox.appendChild(pGroup);
      catsBox.appendChild(cLab); catsBox.appendChild(cNote); catsBox.appendChild(cGroup);
      sheet.appendChild(catsBox);

      var currentPid = row.getAttribute("data-sp-parent-id") || "";
      var currentOpt = $$("option", ps).find(function (o) { return o.value === currentPid; });
      var pickedPid = (currentOpt && currentOpt.getAttribute("data-slug") !== "sms") ? currentPid : "";
      var saving = false;

      function renderSheetChildren() {
        cGroup.innerHTML = "";
        var kids = pickedPid ? $$("option", cs).filter(function (o) { return o.value && o.getAttribute("data-parent") === pickedPid; }) : [];
        var show = kids.length > 0;
        cLab.hidden = !show; cNote.hidden = !show; cGroup.hidden = !show;
        kids.forEach(function (o) {
          var b = document.createElement("button");
          b.type = "button"; b.textContent = o.textContent;
          b.setAttribute("aria-pressed", "false");
          b.addEventListener("click", function () {
            if (saving) return;
            saving = true;
            var remember = !!(rememberInput && rememberInput.checked);
            fetch("/profile/spends/" + spendId + "/category", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrfToken() },
              body: JSON.stringify({ category_id: Number(o.value), remember_merchant: remember }),
            })
              .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
              .then(function (r) {
                if (!r.ok || !r.d || !r.d.ok) throw new Error("save");
                var d = r.d;
                closeDialog();
                applyRowCategory(row, d);
                refreshSummary();
                showUndoToast("دسته عوض شد", "بازگرداندن", function () {
                  return fetch("/profile/spends/" + spendId + "/category", {
                    method: "PATCH",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrfToken() },
                    body: JSON.stringify({
                      category_id: d.prev_category_id,
                      category_source: d.prev_category_source,
                      undo: true,
                      undo_memory_id: d.undo_memory_id,
                      restore_memory_id: d.restore_memory_id,
                      restore_memory_category_id: d.restore_memory_category_id,
                    }),
                  })
                    .then(function (res2) { return res2.json().then(function (u) { return { ok: res2.ok, d: u }; }); })
                    .then(function (r2) {
                      if (!r2.ok || !r2.d || !r2.d.ok) throw new Error("undo");
                      applyRowCategory(row, r2.d);
                      refreshSummary();
                      return true;
                    })
                    .catch(function () {
                      showWarnToast("ذخیره نشد؛ دوباره بزنید");
                      return false;
                    });
                });
              })
              .catch(function () {
                saving = false;
                closeDialog();
                showWarnToast("ذخیره نشد؛ دوباره بزنید");
              });
          });
          cGroup.appendChild(b);
        });
      }

      function renderSheetParents() {
        pGroup.innerHTML = "";
        $$("option", ps).forEach(function (o) {
          if (!o.value || o.getAttribute("data-slug") === "sms") return;
          var b = document.createElement("button");
          b.type = "button";
          var sw = document.createElement("span"); sw.className = "sw"; sw.setAttribute("aria-hidden", "true");
          sw.style.background = o.getAttribute("data-color") || "#475569";
          b.appendChild(sw); b.appendChild(document.createTextNode(o.textContent.trim()));
          b.setAttribute("aria-pressed", String(o.value === pickedPid));
          b.addEventListener("click", function () {
            pickedPid = o.value;
            renderSheetParents();
            renderSheetChildren();
          });
          pGroup.appendChild(b);
        });
      }

      renderSheetParents();
      renderSheetChildren();
      document.body.appendChild(sheet);
      $(".sp-x", sheet).addEventListener("click", closeDialog);
      openDialog(sheet, { back: back, focus: $(".sp-x", sheet), scrimClass: "p6-scrim", onClose: function () { sheet.remove(); } });
    }

    /* ---------- row menu + instant delete with 8s undo (no confirm dialog) ---------- */
    var menuOpen = null;
    function closeMenu(focusBack) {
      if (!menuOpen) return;
      menuOpen.menu.hidden = true; menuOpen.btn.setAttribute("aria-expanded", "false");
      if (focusBack) menuOpen.btn.focus();
      menuOpen = null;
    }
    function instantDelete(row) {
      var spendId = row.getAttribute("data-sp-row");
      var parentList = row.parentNode;
      var nextSib = row.nextSibling;
      var daySec = row.closest(".sp-day");
      row.hidden = true;
      var remainingVisible = $$(".sp-row", parentList).some(function (r) { return !r.hidden; });
      if (daySec && !remainingVisible) daySec.hidden = true;

      fetch("/profile/spends/" + spendId + "/delete", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Accept": "application/json", "X-CSRF-Token": csrfToken() },
      })
        .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
        .then(function (r) {
          if (!r.ok || !r.d || !r.d.ok) throw new Error("del");
          row.remove();
          refreshSummary();
          showUndoToast("خرج حذف شد", "بازگرداندن", function () {
            return fetch("/profile/spends/" + spendId + "/restore", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Accept": "application/json", "X-CSRF-Token": csrfToken() },
            })
              .then(function (res2) { return res2.json().then(function (u) { return { ok: res2.ok, d: u }; }); })
              .then(function (r2) {
                if (!r2.ok || !r2.d || !r2.d.ok) throw new Error("restore");
                row.hidden = false;
                if (nextSib && nextSib.parentNode === parentList) parentList.insertBefore(row, nextSib);
                else parentList.appendChild(row);
                if (daySec) daySec.hidden = false;
                refreshSummary();
                return true;
              })
              .catch(function () {
                showWarnToast("ذخیره نشد؛ دوباره بزنید");
                return false;
              });
          });
        })
        .catch(function () {
          row.hidden = false;
          if (daySec) daySec.hidden = false;
          showWarnToast("ذخیره نشد؛ دوباره بزنید");
        });
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
        $("[data-sp-del]", menu).addEventListener("click", function () { closeMenu(false); instantDelete(row); });
      });
      $$("[data-sp-catq]", root).forEach(function (btn) {
        var row = btn.closest("[data-sp-row]");
        btn.addEventListener("click", function () { openCatSheet(row, btn); });
      });
    }
    document.addEventListener("click", function (e) { if (menuOpen && !menuOpen.menu.contains(e.target)) closeMenu(false); });
    bindRows(document);

    /* ---------- validation ---------- */
    var FIELDS = { amount_toman: amt, year: form.elements.year, month: form.elements.month, day: form.elements.day };
    function values() { return { amount: amt.value, orig: amt.getAttribute("data-sp-orig") || "", year: FIELDS.year.value, month: FIELDS.month.value, day: FIELDS.day.value }; }
    function setErr(name, msg) {
      var input = FIELDS[name];
      var err = name === "category_id" ? $("#sp-category_id") : $("#err-" + name);
      if (err) err.textContent = msg || "";
      if (name === "category_id") {
        var catsWrap = $(".sp-cats", form);
        if (catsWrap) catsWrap.classList.toggle("sp-invalid", !!msg);
        pChips.classList.toggle("p6-err", !!msg && !ps.value);
        cChips.classList.toggle("p6-err", !!msg && !!ps.value && !cs.value);
        return;
      }
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
      if (!cs.value) errs.category_id = "دسته را انتخاب کنید";
      if (Object.keys(errs).length) { showErrors(errs); return; }
      showErrors({});
      var old = $("[data-sp-save-error]", card); if (old) old.remove();
      writeLastCategory(ps.value, cs.value);
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
          if (withSummary) { var ns = $("[data-sp-sum]", doc); sum.replaceWith(ns); bindMonth(ns); bindRestToggle(ns); fitTileAmounts();
            var nf = $("[data-sp-page]", doc);
            form.elements.jy.value = $("[name=jy]", nf).value; form.elements.jm.value = $("[name=jm]", nf).value; }
          if (history.replaceState) history.replaceState(null, "", url);
          if (window.Amounts) window.Amounts.refresh(url);
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
      if (withSummary && sum) {
        $$(".sp-tile b", sum).forEach(function (b) { b.innerHTML = '<i class="v2-skel" style="width:110px;height:22px;margin-top:6px"></i>'; });
        $$(".sp-bars li", sum).forEach(function (li) { li.innerHTML = '<i class="v2-skel" style="width:40%;height:14px"></i><i></i><i class="v2-skel bar" style="height:8px"></i>'; li.setAttribute("aria-hidden", "true"); });
        $$(".sp-tile small, [data-sp-rest-toggle]", sum).forEach(function (el) { el.hidden = true; });
        sum.setAttribute("aria-busy", "true");
      }
    }
    function bindMore(root) {
      var m = $("[data-sp-more]", root);
      if (!m || !window.fetch) return;
      m.addEventListener("click", function (e) {
        e.preventDefault();
        m.setAttribute("aria-disabled", "true");
        m.innerHTML = '<span class="v2-spin" aria-hidden="true"></span> در حال بارگذاری…';
        loadInto(m.getAttribute("href"), false);
      });
    }
    function bindMonth(root) {
      $$("[data-sp-month]", root).forEach(function (a) {
        if (!window.fetch) return;
        a.addEventListener("click", function (e) { e.preventDefault(); loadInto(a.getAttribute("href"), true); });
      });
    }
    bindMore(document); bindMonth(document);
    window.__spLoad = loadInto;
  });
})();
