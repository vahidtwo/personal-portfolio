// /auth: show/hide password, a loading state that blocks a double submit, a Persian-keyboard hint, and the
// wait countdown after a rate limit (app-v2 spec). Nothing typed is sent anywhere or logged by this file.
(function () {
  "use strict";
  document.querySelectorAll("[data-eye]").forEach(function (btn) {
    var input = btn.parentElement.querySelector("input");
    btn.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "پنهان کردن" : "نمایش";
      btn.setAttribute("aria-label", show ? "پنهان کردن رمز" : "نمایش رمز");
      btn.setAttribute("aria-pressed", show ? "true" : "false");
    });
  });
  // Persian-keyboard hint: only a warning while typing, never blocks submit.
  var FA = /[\u0600-\u06FF]/;
  document.querySelectorAll("input[type=password]").forEach(function (input) {
    if (input.id !== "password" && input.id !== "password_confirm") return;
    var hint = document.getElementById(input.id === "password" ? "password-hint" : "confirm-hint");
    if (!hint) return;
    var original = hint.textContent, originalClass = hint.className;
    hint.setAttribute("aria-live", "polite");
    input.addEventListener("input", function () {
      if (FA.test(input.value)) {
        hint.textContent = "صفحه‌کلید فارسی است. رمز را با صفحه‌کلید انگلیسی بنویسید.";
        hint.className = "hint warn";
      } else {
        hint.textContent = original;
        hint.className = originalClass;
      }
    });
  });
  // Rate limit: the server already disabled the button; re-enable it when the wait is over, or as soon as the
  // username is edited to a different name (the lock is per name; the server still decides on submit).
  var wait = document.querySelector("button[data-retry-seconds]");
  if (wait) {
    var digits = "۰۱۲۳۴۵۶۷۸۹", fa = function (n) { return String(n).replace(/\d/g, function (d) { return digits[d]; }); };
    var until = Date.now() + (parseInt(wait.dataset.retrySeconds, 10) || 0) * 1000;
    var lockedClass = wait.className, timer = null;
    // the lock alert says "closed for N minutes"; hide it while the button is usable so the page never contradicts itself
    var lockAlert = wait.form ? wait.form.querySelector(".alert") : null;
    var unlock = function () {
      if (lockAlert) lockAlert.hidden = true;
      wait.disabled = false;
      wait.removeAttribute("aria-disabled");
      wait.textContent = wait.dataset.readyLabel || "ادامه";
      wait.className = "btn btn-primary btn-block";
    };
    var tick = function () {
      var left = Math.ceil((until - Date.now()) / 1000);
      if (left <= 0) {
        unlock();
        clearInterval(timer);
        timer = null;
        return;
      }
      var label = (wait.dataset.waitLabel || "").replace("{n}", fa(Math.max(1, Math.ceil(left / 60))));
      if (wait.textContent !== label) wait.textContent = label;
    };
    timer = setInterval(tick, 5000);
    var uname = document.getElementById("username");
    if (uname && !uname.readOnly) {
      var norm = function (v) { return v.trim().toLowerCase(); };
      var lockedName = norm(uname.value);
      uname.addEventListener("input", function () {
        if (until - Date.now() <= 0) return;
        if (norm(uname.value) !== lockedName) {
          if (timer) { clearInterval(timer); timer = null; }
          unlock();
        } else if (!timer) {
          // back to the locked name: lock again with the remaining time
          if (lockAlert) lockAlert.hidden = false;
          wait.disabled = true;
          wait.setAttribute("aria-disabled", "true");
          wait.className = lockedClass;
          tick();
          timer = setInterval(tick, 5000);
        }
      });
    }
  }
  // Field errors while typing (the server still validates on submit; the copy matches unified_auth.py).
  var USERNAME_RE = /^[a-zA-Z][a-zA-Z0-9_]{2,31}$/;
  var USERNAME_PARTIAL = /^[a-zA-Z][a-zA-Z0-9_]{0,31}$/;
  var USERNAME_ERROR = "نام کاربری باید با حرف انگلیسی شروع شود و ۳ تا ۳۲ حرف باشد.";
  var PASSWORD_ERROR = "دست‌کم ۸ حرف";
  var IDLE = { "username-hint": "۳ تا ۳۲ حرف انگلیسی یا عدد، بدون فاصله", "password-hint": PASSWORD_ERROR };
  function fieldState(input, hint, text, kind) {
    var box = input.closest(".inp");
    if (kind) {
      hint.textContent = text;
      hint.className = "hint " + kind;
    } else {
      hint.textContent = IDLE[hint.id] || hint.textContent;
      hint.className = "hint";
    }
    if (box) box.classList.toggle("err", kind === "bad");
    if (kind === "bad") input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
  }
  var userIn = document.getElementById("username"), userHint = document.getElementById("username-hint");
  var passIn = document.getElementById("password"), passHint = document.getElementById("password-hint");
  if (userHint) userHint.setAttribute("aria-live", "polite");
  function checkUser(final) {
    if (!userIn || !userHint || userIn.readOnly) return true;
    var v = userIn.value.trim();
    var ok = final ? USERNAME_RE.test(v) : (v === "" || USERNAME_PARTIAL.test(v));
    if (!ok) fieldState(userIn, userHint, USERNAME_ERROR, "bad");
    else if (userIn.getAttribute("aria-invalid") === "true" && (USERNAME_RE.test(v) || !final)) fieldState(userIn, userHint, "", null);
    return ok;
  }
  function checkPass(final) {
    if (!passIn || !passHint || FA.test(passIn.value)) return true;
    var n = passIn.value.length;
    if (n === 0 && final) { fieldState(passIn, passHint, PASSWORD_ERROR, "bad"); return false; }
    if (n > 0 && n < 8) fieldState(passIn, passHint, PASSWORD_ERROR, final ? "bad" : "warn");
    else fieldState(passIn, passHint, "", null);
    return true;
  }
  if (userIn && userHint) {
    userIn.addEventListener("input", function () { checkUser(false); });
    userIn.addEventListener("blur", function () { if (userIn.value.trim()) checkUser(true); });
  }
  if (passIn && passHint) {
    passIn.addEventListener("input", function () { checkPass(false); });
    passIn.addEventListener("blur", function () { if (passIn.value) checkPass(true); });
  }
  var first = document.querySelector("[data-autofocus]");
  if (first) first.focus({ preventScroll: true });
  var form = document.querySelector("[data-auth-form]");
  if (!form) return;
  form.addEventListener("submit", function (event) {
    if (form.dataset.busy === "1") { event.preventDefault(); return; }
    if (userIn && passIn && !userIn.readOnly) {
      var userOk = checkUser(true), passOk = checkPass(true);
      if (!userOk || !passOk) {
        event.preventDefault();
        (userOk ? passIn : userIn).focus();
        return;
      }
    }
    form.dataset.busy = "1";
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll("input:not([type=hidden])").forEach(function (i) { i.readOnly = true; });
    var btn = form.querySelector("button[type=submit]");
    if (btn) {
      btn.setAttribute("aria-disabled", "true");
      btn.innerHTML = '<span class="spin" aria-hidden="true"></span><span>' + (btn.dataset.busyLabel || "") + "</span>";
    }
  });
})();
