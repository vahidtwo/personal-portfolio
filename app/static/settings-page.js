/* Settings v2 (/profile): theme radios, salary eye (fetch on tap, re-mask on pagehide), per-section
   validation at the field with a linked summary, and fetch saves with saving / failed states.
   Without JS every section is a plain form post to /profile/account and still works. */
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const page = $("#settings-v2");
  if (!page) return;
  const fa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
  const latin = (t) => String(t || "").replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d));

  /* ---- theme ---- */
  const T = window.inventoryTheme;
  const status = $("#v2-th-s");
  function paintTheme(justPicked) {
    if (!T) return;
    const c = T.choice(), now = T.NAME[T.effective()];
    $$("input[name=theme_choice]", page).forEach((r) => { r.checked = r.value === c; });
    if (c === "auto") status.textContent = "خودکار: الان " + now + "، مثل دستگاه.";
    else if (justPicked) status.textContent = "پوسته " + now + " شد. فقط روی همین دستگاه ذخیره می‌شود.";
    else status.textContent = "پوستهٔ فعلی: " + now + ". فقط روی همین دستگاه ذخیره می‌شود.";
  }
  if (T) {
    $$("input[name=theme_choice]", page).forEach((r) => r.addEventListener("change", () => { T.set(r.value); paintTheme(true); }));
    T.onChange(() => paintTheme(false));
    paintTheme(false);
  }

  /* ---- salary: masked by default, revealed per view only ---- */
  const eye = $("#v2-eye"), salv = $("#v2-salv"), salFail = $("#v2-sal-fail");
  function mask() {
    if (!eye) return;
    salv.textContent = "••••••";
    eye.setAttribute("aria-pressed", "false");
    eye.textContent = "نمایش";
  }
  if (eye) {
    eye.addEventListener("click", async () => {
      if (eye.getAttribute("aria-pressed") === "true") return mask();
      eye.setAttribute("aria-busy", "true");
      salFail.classList.add("v2-hide");
      try {
        const r = await fetch("/api/salary", { credentials: "same-origin", cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const data = await r.json();
        salv.textContent = data.salary;
        eye.setAttribute("aria-pressed", "true");
        eye.textContent = "پنهان کردن";
      } catch (e) {
        salFail.classList.remove("v2-hide");
      } finally {
        eye.removeAttribute("aria-busy");
      }
    });
    window.addEventListener("pagehide", mask);
    window.addEventListener("pageshow", mask); // back/forward cache: never come back revealed
  }
  const salEdit = $("#v2-saledit"), salForm = $("#v2-salform"), salCancel = $("#v2-salcancel");
  if (salEdit && salForm) {
    salEdit.addEventListener("click", () => {
      salForm.classList.remove("v2-hide");
      salEdit.setAttribute("aria-expanded", "true");
      $("#f-salary_toman").focus();
    });
  }
  if (salCancel) {
    salCancel.addEventListener("click", () => {
      $("#f-salary_toman").value = "";
      clearErrors(salForm);
      salForm.classList.add("v2-hide");
      salEdit.setAttribute("aria-expanded", "false");
      salEdit.focus();
    });
  }

  /* ---- «رمز فعلی» only when the username changes ---- */
  const uname = $("#f-username"), cpw = $("#v2-cpw");
  function syncCpw() {
    const changed = uname.value.trim().toLowerCase() !== (uname.dataset.original || "");
    cpw.classList.toggle("v2-hide", !changed && !$("#f-current_password").getAttribute("aria-invalid"));
    if (!changed) $("#f-current_password").value = "";
  }
  if (uname && cpw) uname.addEventListener("input", syncCpw);

  /* ---- validation (same rules and copy as the server) ---- */
  const LABEL = { full_name: "نام", username: "نام کاربری", mobile: "موبایل", current_password: "رمز فعلی", new_password: "رمز جدید", salary_toman: "حقوق جدید" };
  function rules(section, f) {
    const e = {};
    const get = (n) => { const i = f.querySelector('[name="' + n + '"]:not([type=hidden])'); return i ? i.value : null; };
    if (section === "account") {
      const u = (get("username") || "").trim().toLowerCase();
      if (!/^[a-z][a-z0-9_]{2,31}$/.test(u)) e.username = "نام کاربری باید با حرف انگلیسی شروع شود و ۳ تا ۳۲ نویسه باشد";
      const m = latin(get("mobile")).replace(/\D/g, "");
      if (m && (m.length < 10 || m.length > 15)) e.mobile = "شماره موبایل ۱۰ تا ۱۵ رقم است؛ مثلاً ۰۹۱۲۳۴۵۶۷۸۹";
      if (!e.username && u !== (uname.dataset.original || "") && !get("current_password")) e.current_password = "برای تغییر نام کاربری، رمز فعلی را وارد کنید";
    } else if (section === "password") {
      if (!get("current_password")) e.current_password = "برای تغییر رمز، رمز فعلی را وارد کنید";
      if ((get("new_password") || "").length < 8) e.new_password = "رمز جدید دست‌کم ۸ نویسه باشد";
    } else if (section === "salary") {
      const raw = latin(get("salary_toman")).replace(/[٬,،\s]/g, "").replace("٫", ".");
      if (!raw) e.salary_toman = "مبلغ حقوق را بنویسید";
      else if (/^\d+\.\d*$/.test(raw)) e.salary_toman = "حقوق را بدون ممیز و به تومان کامل بنویسید؛ مثلاً ۴۵٬۰۰۰٬۰۰۰";
      else if (!/^\d+$/.test(raw)) e.salary_toman = "حقوق ماهانه نامعتبر است";
    }
    return e;
  }
  function fieldFor(f, name) {
    return f.querySelector('[name="' + name + '"]:not([type=hidden])');
  }
  function clearErrors(f) {
    $$(".v2-err[data-js]", f).forEach((n) => n.remove());
    $$("[aria-invalid]", f).forEach((i) => {
      i.removeAttribute("aria-invalid");
      const h = i.parentElement.querySelector(".v2-hint");
      if (h) { h.classList.remove("v2-hide"); i.setAttribute("aria-describedby", h.id); } else i.removeAttribute("aria-describedby");
    });
    $$(".v2-err:not([data-js])", f).forEach((n) => n.remove());
    const card = f.closest(".v2-card");
    $$("[data-v2-summary],[data-v2-banner]", card).forEach((n) => n.remove());
  }
  function showErrors(f, errors, focusSummary) {
    clearErrors(f);
    const names = Object.keys(errors);
    if (!names.length) return;
    names.forEach((n) => {
      const i = fieldFor(f, n);
      if (!i) return;
      if (!i.id) i.id = "f-" + n;
      const msg = document.createElement("span");
      msg.className = "v2-err"; msg.dataset.js = "1"; msg.id = "e-" + i.id; msg.textContent = errors[n];
      const h = i.parentElement.querySelector(".v2-hint");
      if (h) h.classList.add("v2-hide");
      i.parentElement.classList.remove("v2-hide");
      i.after(msg);
      i.setAttribute("aria-invalid", "true");
      i.setAttribute("aria-describedby", msg.id);
    });
    const box = document.createElement("div");
    box.className = "v2-banner"; box.setAttribute("role", "alert"); box.tabIndex = -1; box.dataset.v2Summary = "1";
    box.innerHTML = "<div><strong></strong><ul></ul></div>";
    box.querySelector("strong").textContent = fa(names.length) + " مورد نیاز به اصلاح دارد";
    names.forEach((n) => {
      const i = fieldFor(f, n);
      const li = document.createElement("li"), a = document.createElement("a");
      a.href = "#" + (i ? i.id : ""); a.textContent = LABEL[n] || n;
      a.addEventListener("click", (ev) => { ev.preventDefault(); if (i) i.focus(); });
      li.append(a); box.querySelector("ul").append(li);
    });
    f.before(box);
    if (focusSummary) box.focus();
  }
  function banner(f, ok, title, detail, retry) {
    const card = f.closest(".v2-card");
    $$("[data-v2-banner]", card).forEach((n) => n.remove());
    const b = document.createElement("div");
    b.className = "v2-banner" + (ok ? " ok" : ""); b.dataset.v2Banner = "1";
    b.setAttribute("role", ok ? "status" : "alert");
    b.innerHTML = "<div><strong></strong><span></span></div>";
    b.querySelector("strong").textContent = title;
    b.querySelector("span").textContent = detail;
    if (retry) {
      const r = document.createElement("button");
      r.type = "button"; r.className = "btn btn-sm v2-ghost"; r.textContent = "دوباره";
      r.addEventListener("click", retry); b.append(r);
    }
    f.before(b);
  }

  $$("form[data-v2-section]", page).forEach((f) => {
    const section = f.dataset.v2Section;
    const btn = f.querySelector("button[type=submit]");
    const label = btn.innerHTML;
    // blur: re-check only fields already marked, so errors clear as they are fixed
    f.addEventListener("focusout", (ev) => {
      // moving between fields of this form: re-check marked fields; leaving it (e.g. to the summary) keeps the list
      if (!f.querySelector("[aria-invalid]") || !ev.relatedTarget || !f.contains(ev.relatedTarget)) return;
      showErrors(f, rules(section, f), false);
    });
    async function send() {
      btn.setAttribute("aria-disabled", "true");
      btn.innerHTML = '<span class="v2-spin" aria-hidden="true"></span>در حال ذخیره…';
      try {
        const r = await fetch(f.action, { method: "POST", body: new FormData(f), credentials: "same-origin", headers: { Accept: "application/json" } });
        if (r.status === 422) {
          const data = await r.json();
          showErrors(f, data.errors || {}, true);
        } else if (r.ok) {
          window.location.assign("/profile#" + f.closest(".v2-card").id); // flash shows the saved banner
          window.location.reload();
          return;
        } else {
          throw new Error(String(r.status));
        }
      } catch (e) {
        banner(f, false, "ذخیره نشد", "اتصال برقرار نشد. چیزی که نوشتید سر جایش مانده است.", () => f.requestSubmit());
      }
      btn.removeAttribute("aria-disabled");
      btn.innerHTML = label;
    }
    f.addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (btn.getAttribute("aria-disabled") === "true") return;
      const errors = rules(section, f);
      if (Object.keys(errors).length) { showErrors(f, errors, true); return; }
      clearErrors(f);
      send();
    });
  });
  const summary = $("[data-v2-summary]", page);
  if (summary) summary.focus();
})();
