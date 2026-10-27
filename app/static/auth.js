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
  // Rate limit: the server already disabled the button; re-enable it when the wait is over.
  var wait = document.querySelector("button[data-retry-seconds]");
  if (wait) {
    var digits = "۰۱۲۳۴۵۶۷۸۹", fa = function (n) { return String(n).replace(/\d/g, function (d) { return digits[d]; }); };
    var until = Date.now() + (parseInt(wait.dataset.retrySeconds, 10) || 0) * 1000;
    var tick = function () {
      var left = Math.ceil((until - Date.now()) / 1000);
      if (left <= 0) {
        wait.disabled = false;
        wait.textContent = wait.dataset.readyLabel || "ادامه";
        wait.className = "btn btn-primary btn-block";
        clearInterval(timer);
        return;
      }
      var label = (wait.dataset.waitLabel || "").replace("{n}", fa(Math.max(1, Math.ceil(left / 60))));
      if (wait.textContent !== label) wait.textContent = label;
    };
    var timer = setInterval(tick, 5000);
  }
  var first = document.querySelector("[data-autofocus]");
  if (first) first.focus({ preventScroll: true });
  var form = document.querySelector("[data-auth-form]");
  if (!form) return;
  form.addEventListener("submit", function (event) {
    if (form.dataset.busy === "1") { event.preventDefault(); return; }
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
