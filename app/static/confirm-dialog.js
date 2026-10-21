/* In-app confirm for forms with data-confirm="logout" | "revoke" (no window.confirm).
   role=alertdialog, aria-modal, focus starts on «انصراف», Tab is trapped, Esc closes, focus returns. */
(function () {
  const COPY = {
    logout: { title: "از حساب خارج شوید؟", body: "داده‌هایتان سر جایش می‌ماند؛ برای برگشتن دوباره وارد شوید.", ok: "خروج" },
    revoke: { title: "توکن MCP غیرفعال شود؟", body: "دستیارهایی که با این توکن وصل‌اند دیگر به حسابتان دسترسی ندارند. بعداً می‌توانید توکن تازه بسازید.", ok: "غیرفعال کن" },
  };
  function open(form, trigger) {
    const c = COPY[form.dataset.confirm];
    if (!c) return form.submit();
    const back = document.createElement("div");
    back.className = "v2-dlg-back";
    const d = document.createElement("div");
    d.className = "v2-dlg";
    d.setAttribute("role", "alertdialog");
    d.setAttribute("aria-modal", "true");
    d.setAttribute("aria-labelledby", "v2-dlg-t");
    d.setAttribute("aria-describedby", "v2-dlg-d");
    d.innerHTML = '<h2 id="v2-dlg-t"></h2><p id="v2-dlg-d"></p><div class="v2-actions">' +
      '<button type="button" class="btn v2-ghost" data-dlg-cancel>انصراف</button>' +
      '<button type="button" class="btn btn-danger" data-dlg-ok></button></div>';
    d.querySelector("h2").textContent = c.title;
    d.querySelector("p").textContent = c.body;
    d.querySelector("[data-dlg-ok]").textContent = c.ok;
    document.body.append(back, d);
    const cancel = d.querySelector("[data-dlg-cancel]");
    const ok = d.querySelector("[data-dlg-ok]");
    function close() {
      back.remove(); d.remove();
      document.removeEventListener("keydown", onKey, true);
      if (trigger && trigger.focus) trigger.focus();
    }
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); close(); }
      else if (e.key === "Tab") {
        const first = cancel, last = ok;
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        else if (!d.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener("keydown", onKey, true);
    back.addEventListener("click", close);
    cancel.addEventListener("click", close);
    ok.addEventListener("click", function () { ok.setAttribute("aria-disabled", "true"); form.submit(); });
    cancel.focus();
  }
  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm) return;
    e.preventDefault();
    open(form, e.submitter || form.querySelector("[type=submit]"));
  }, true);
})();
