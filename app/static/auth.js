// /auth: show/hide password, and a loading state that blocks a double submit (spec state d).
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
