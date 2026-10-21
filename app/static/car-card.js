/* Car (Sanjeh) card v2: menu, connect/replace sheet, disconnect dialog, undo toast.
   Works without this file (server-rendered ?car=… states + plain POSTs); this only adds in-place updates. */
(function () {
  var section = document.querySelector('[data-asset-group="car"]');
  var sheet = document.querySelector("[data-car-sheet]");
  var confirmBox = document.querySelector("[data-car-confirm]");
  var toast = document.querySelector("[data-car-toast]");
  if (!section || !sheet || !confirmBox) return;
  var returnFocus = null;
  var toastTimer = null;

  function saveBarDirty() {
    var bar = document.querySelector("[data-save-bar]");
    return bar && !bar.hidden;
  }

  function initCard() {
    var card = section.querySelector("[data-car-card]");
    var menu = card && card.querySelector("[data-car-menu]");
    var toggle = card && card.querySelector("[data-car-menu-toggle]");
    if (menu && toggle) {
      menu.hidden = true;
      toggle.hidden = false;
      toggle.addEventListener("click", function () {
        var open = menu.hidden;
        menu.hidden = !open;
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) { var first = menu.querySelector("a"); if (first) first.focus(); }
      });
    }
  }

  function closeAll() {
    [sheet, confirmBox].forEach(function (el) { el.hidden = true; });
    if (returnFocus && document.contains(returnFocus)) returnFocus.focus();
    returnFocus = null;
  }

  function setErr(msg) {
    var input = sheet.querySelector("#car-token");
    var err = sheet.querySelector("[data-car-err]");
    err.textContent = msg || "";
    err.hidden = !msg;
    if (msg) { input.setAttribute("aria-invalid", "true"); input.focus(); } else { input.removeAttribute("aria-invalid"); }
  }

  function openBox(kind, opener) {
    returnFocus = opener || document.activeElement;
    var menu = section.querySelector("[data-car-menu]");
    var toggle = section.querySelector("[data-car-menu-toggle]");
    if (menu && toggle && !toggle.hidden) { menu.hidden = true; toggle.setAttribute("aria-expanded", "false"); returnFocus = toggle; }
    if (kind === "confirm") {
      var val = section.querySelector(".val .num");
      var target = confirmBox.querySelector(".num");
      if (val && target) target.textContent = val.textContent;
      confirmBox.hidden = false;
      confirmBox.querySelector("[data-car-close]").focus();
      return;
    }
    var title = sheet.querySelector("#car-sheet-title");
    title.textContent = title.getAttribute("data-title-" + kind);
    var submit = sheet.querySelector('button[type="submit"]');
    submit.textContent = submit.getAttribute("data-label-" + kind);
    sheet.querySelector("#car-token").value = "";
    setErr("");
    sheet.hidden = false;
    sheet.querySelector("#car-token").focus();
  }

  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-car-open]");
    if (opener) { e.preventDefault(); openBox(opener.getAttribute("data-car-open"), opener); return; }
    var closer = e.target.closest("[data-car-close]");
    if (closer) { e.preventDefault(); closeAll(); return; }
    if (e.target === sheet || e.target === confirmBox) closeAll();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && (!sheet.hidden || !confirmBox.hidden)) { e.preventDefault(); closeAll(); }
  });

  function showToast() {
    if (!toast) return;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.hidden = true; }, 10000);
  }

  function busy(btn, on) {
    if (!btn) return;
    if (on) {
      btn.dataset.idle = btn.innerHTML;
      btn.disabled = true;
      btn.classList.add("car-busy");
      btn.innerHTML = '<span class="spin" aria-hidden="true"></span>' + (btn.getAttribute("data-busy") || "");
    } else if (btn.dataset.idle !== undefined) {
      btn.disabled = false;
      btn.classList.remove("car-busy");
      btn.innerHTML = btn.dataset.idle;
    }
  }

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.hasAttribute("data-car-form")) return;
    e.preventDefault();
    var btn = e.submitter || form.querySelector('button[type="submit"]');
    if (form.id === "car-refresh-form") btn = section.querySelector("[data-car-refresh]");
    if (form.hasAttribute("data-car-connect") && !form.querySelector("#car-token").value.trim()) {
      setErr("توکن API سنجه را بچسبانید."); return;
    }
    busy(btn, true);
    fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().catch(function () { return { ok: false, message: "خطا؛ دوباره امتحان کنید." }; }); })
      .then(function (data) {
        busy(btn, false);
        var connect = form.hasAttribute("data-car-connect");
        if (connect && !data.ok) { setErr(data.message); return; }
        var isDisconnect = /\/disconnect$/.test(form.action);
        var isUndo = /\/undo$/.test(form.action);
        if ((data.ok && (connect || isDisconnect || isUndo)) && !saveBarDirty()) {
          // value moved in or out of the totals: reload so totals/charts are right (toast is server-rendered)
          var hf = document.querySelector("[data-assets-form]");
          if (hf) hf.dispatchEvent(new Event("assets:saved")); // nothing unsaved: no leave warning on this reload
          if (window.location.pathname === "/assets" && !window.location.search) {
            history.replaceState(null, "", "/assets#group-car");
            window.location.reload();
          } else {
            window.location.assign("/assets#group-car"); // e.g. from /assets?car=… : a real navigation
          }
          return;
        }
        if (data.html) {
          var holder = document.createElement("div");
          holder.innerHTML = data.html;
          var card = section.querySelector("[data-car-card]");
          card.replaceWith(holder.firstElementChild);
          initCard();
        }
        closeAll();
        if (isDisconnect && data.ok) showToast();
        if (isUndo && toast) toast.hidden = true;
      })
      .catch(function () { busy(btn, false); form.submit(); });
  });

  initCard();
  if (toast && !toast.hidden) showToast();
  if (!sheet.hidden) sheet.querySelector("#car-token").focus();
  else if (!confirmBox.hidden) confirmBox.querySelector("[data-car-close]").focus();
})();
