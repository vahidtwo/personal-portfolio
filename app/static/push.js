(function () {
  var configEl = document.getElementById("firebase-config");
  if (!configEl) return;

  // A broken config must not stop the buttons from working: they report it instead.
  var firebaseConfig = null;
  var configError = "";
  try {
    firebaseConfig = JSON.parse(configEl.textContent || "");
    if (!firebaseConfig || typeof firebaseConfig !== "object" || !firebaseConfig.apiKey) configError = "config-missing";
  } catch (e) {
    configError = "config-parse";
  }

  var DEFAULT_TITLE = "دارایی‌تو";
  var DEFAULT_PATH = "/dashboard";

  // Same rule as sw.js: only this site's own paths; anything else opens the dashboard.
  function pushTargetPath(raw) {
    var p = typeof raw === "string" ? raw.trim() : "";
    if (p.indexOf("/") !== 0 || p.indexOf("//") === 0 || p.indexOf("\\") >= 0 || /\s/.test(p)) return DEFAULT_PATH;
    return p;
  }

  var SDK = "https://www.gstatic.com/firebasejs/11.6.0/";
  var bridge = window.AndroidBridge;
  var inApp = !!(bridge && typeof bridge.isAndroidApp === "function");

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      if (document.querySelector('script[src="' + src + '"]')) {
        resolve();
        return;
      }
      var script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = function () { reject(new Error("sdk-load")); };
      document.head.appendChild(script);
    });
  }

  function setStatus(text, isError, code) {
    var el = document.getElementById("push-status");
    if (!el) return;
    el.textContent = text;
    if (code) {
      el.appendChild(document.createTextNode(" "));
      var small = document.createElement("small");
      small.className = "push-code";
      small.dir = "ltr";
      small.textContent = code;
      el.appendChild(small);
    }
    el.hidden = !text;
    el.classList.toggle("toast-warn", !!isError);
    el.classList.toggle("toast-ok", !isError && !!text);
  }

  function stepError(step, detail) {
    var err = new Error(step);
    err.step = step;
    err.detail = String(detail || "");
    return err;
  }

  function errDetail(err) {
    if (!err) return "";
    var code = String(err.code || err.name || "");
    var msg = String(err.message || "");
    return code && msg && code !== msg ? code + ": " + msg : code || msg;
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).then(function (response) {
      return response.json().then(
        function (data) {
          if (data && typeof data === "object" && !data.ok && !data.status) data.status = response.status;
          return data;
        },
        function () { return { ok: false, error: "http-" + response.status, status: response.status }; }
      );
    });
  }

  function getStatus() {
    return fetch("/api/push/status", { credentials: "same-origin", cache: "no-store" }).then(function (r) {
      return r.json();
    });
  }

  function fa(n) {
    return String(n).replace(/[0-9]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }

  var REGISTER_ERROR_TEXT = {
    origin: "سرور درخواست ثبت را از این آدرس نپذیرفت. سایت را از آدرس اصلی باز کنید.",
    login: "نشست شما تمام شده است. دوباره وارد شوید.",
    invalid: "سرور درخواست ثبت را نفهمید. صفحه را تازه کنید.",
    token: "توکن اعلان نامعتبر بود. دوباره امتحان کنید.",
  };

  function webErrorText(err) {
    var step = (err && err.step) || "";
    var detail = (err && err.detail) || errDetail(err);
    if (step === "config-parse" || step === "config-missing") {
      return ["پیکربندی اعلان در این صفحه خراب است. صفحه را تازه کنید.", step];
    }
    if (step === "unsupported") return ["این مرورگر از اعلان پشتیبانی نمی‌کند.", "push-unsupported"];
    if (step === "insecure") return ["اعلان مرورگر فقط روی HTTPS کار می‌کند.", "insecure-context"];
    if (step === "permission") {
      return ["اجازهٔ اعلان داده نشد. از تنظیمات سایت در مرورگر آن را باز کنید.", "permission-" + detail];
    }
    if (step === "sdk-load") {
      return ["کتابخانهٔ اعلان (gstatic.com) بار نشد. اتصال اینترنت یا فیلترشکن را بررسی کنید.", "sdk-load " + detail];
    }
    if (step === "config-fetch") return ["تنظیمات اعلان از سرور گرفته نشد.", "config-fetch " + detail];
    if (step === "config-disabled") return ["اعلان مرورگر روی سرور تنظیم نشده است.", "config-disabled"];
    if (step === "sw-register") return ["سرویس‌ورکر سایت ثبت نشد. صفحه را تازه کنید.", "sw-register " + detail];
    if (step === "sw-ready") return ["سرویس‌ورکر سایت فعال نشد. صفحه را تازه کنید.", "sw-ready " + detail];
    if (step === "token") {
      if (/permission-blocked|permission-default/.test(detail)) {
        return ["اجازهٔ اعلان در مرورگر بسته است. از تنظیمات سایت در مرورگر آن را باز کنید.", "token " + detail];
      }
      if (/AbortError|push service|token-subscribe|installations|token-unsubscribe/i.test(detail)) {
        return ["سرویس اعلان گوگل توکن نداد. با فیلترشکن یا شبکهٔ دیگر دوباره امتحان کنید.", "token " + detail];
      }
      return ["توکن اعلان از گوگل گرفته نشد.", "token " + detail];
    }
    if (step === "token-empty") return ["گوگل توکن خالی برگرداند. دوباره امتحان کنید.", "token-empty"];
    if (step === "register-network") return ["اتصال به سرور برای ثبت دستگاه قطع شد.", "register " + detail];
    if (step === "register") {
      var code = detail.split(" ")[0];
      return [REGISTER_ERROR_TEXT[code] || "ثبت این مرورگر روی سرور ناموفق بود.", "register " + detail];
    }
    return ["فعال‌سازی اعلان ممکن نشد.", detail || "unknown"];
  }

  function withTimeout(promise, ms, step) {
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () { reject(stepError(step, "timeout")); }, ms);
      promise.then(
        function (v) { clearTimeout(timer); resolve(v); },
        function (e) { clearTimeout(timer); reject(e); }
      );
    });
  }

  function initMessaging() {
    if (configError) return Promise.reject(stepError(configError));
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return Promise.reject(stepError("unsupported"));
    }
    if (window.isSecureContext === false) return Promise.reject(stepError("insecure"));
    var messaging;
    var cfg;
    return loadScript(SDK + "firebase-app-compat.js")
      .then(function () { return loadScript(SDK + "firebase-messaging-compat.js"); })
      .then(null, function () { throw stepError("sdk-load", "gstatic"); })
      .then(function () {
        if (!window.firebase || typeof firebase.messaging !== "function") throw stepError("sdk-load", "no-firebase");
        if (!firebase.apps.length) firebase.initializeApp(firebaseConfig);
        return fetch("/api/push/config", { credentials: "same-origin", cache: "no-store" }).then(
          function (r) {
            if (!r.ok) throw stepError("config-fetch", "http-" + r.status);
            return r.json();
          },
          function (e) { throw stepError("config-fetch", errDetail(e)); }
        );
      })
      .then(function (c) {
        cfg = c || {};
        if (!cfg.enabled) throw stepError("config-disabled");
        messaging = firebase.messaging();
        messaging.onMessage(function (payload) {
          var data = payload.data || {};
          var note = payload.notification || {};
          var title = note.title || data.title || DEFAULT_TITLE;
          var body = note.body || data.body || "";
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            var url = pushTargetPath(data.url);
            try {
              var shown = new Notification(title, { body: body, icon: "/static/icons/icon-192.png", data: { url: url } });
              shown.onclick = function () {
                shown.close();
                window.focus();
                window.location.assign(new URL(url, window.location.origin).href);
              };
            } catch (e) {}
          }
          setStatus(body || title, false);
        });
        return navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).then(null, function (e) {
          throw stepError("sw-register", errDetail(e));
        });
      })
      .then(function () { return withTimeout(navigator.serviceWorker.ready, 15000, "sw-ready"); })
      .then(function (registration) {
        var options = { serviceWorkerRegistration: registration };
        if (cfg.vapidKey) options.vapidKey = cfg.vapidKey;
        return messaging.getToken(options).then(null, function (e) { throw stepError("token", errDetail(e)); });
      })
      .then(function (token) {
        if (!token) throw stepError("token-empty");
        return postJson("/api/push/register", { token: token, platform: "web" }).then(
          function (res) {
            if (!res || !res.ok) {
              throw stepError("register", ((res && res.error) || "failed") + " " + ((res && res.status) || ""));
            }
            return token;
          },
          function (e) {
            if (e && e.step) throw e;
            throw stepError("register-network", errDetail(e));
          }
        );
      });
  }

  function showWebError(err) {
    if (window.console) console.error("push enable failed", (err && err.step) || "", (err && err.detail) || err);
    var t = webErrorText(err);
    setStatus(t[0], true, t[1].trim());
  }

  function enableWeb() {
    if (configError) {
      showWebError(stepError(configError));
      return;
    }
    if (!("Notification" in window)) {
      showWebError(stepError("unsupported"));
      return;
    }
    setStatus("در حال فعال‌سازی…", false);
    var asked;
    try {
      asked = Promise.resolve(Notification.requestPermission());
    } catch (e) {
      asked = Promise.reject(e);
    }
    asked
      .then(function (perm) {
        if (perm !== "granted") throw stepError("permission", perm || "default");
        return initMessaging();
      }, function (e) { throw stepError("permission", errDetail(e)); })
      .then(function () {
        setStatus("اعلان‌های این مرورگر فعال شد. «ارسال اعلان آزمایشی» را بزنید.", false);
      })
      .catch(showWebError);
  }

  var APP_STATE_TEXT = {
    ok: ["اعلان‌های اپ فعال شد. «ارسال اعلان آزمایشی» را بزنید.", false],
    unconfigured: ["اعلان اپ روی سرور تنظیم نشده است.", true],
    login: ["برای فعال‌سازی اعلان دوباره وارد شوید.", true],
    "token-failed": ["توکن اعلان از گوگل گرفته نشد. اینترنت، فیلترشکن یا Google Play Services را بررسی کنید.", true],
    "register-failed": ["ثبت دستگاه روی سرور ناموفق بود. دوباره امتحان کنید.", true],
  };

  function readAppState() {
    try {
      return JSON.parse(bridge.pushState()) || {};
    } catch (e) {
      return {};
    }
  }

  function enableApp() {
    if (typeof bridge.enablePush !== "function") {
      setStatus("برای اعلان در اپ، اپ را به آخرین نسخه به‌روز کنید.", true);
      return;
    }
    setStatus("در حال فعال‌سازی…", false);
    try { bridge.enablePush(); } catch (e) {}
    var tries = 0;
    var timer = setInterval(function () {
      tries += 1;
      var st = readAppState();
      var known = APP_STATE_TEXT[st.state];
      if (known) {
        clearInterval(timer);
        if (st.state === "ok" && st.permission !== "granted") {
          setStatus("دستگاه ثبت شد، ولی اعلان‌های این اپ در تنظیمات اندروید خاموش است.", true);
          return;
        }
        setStatus(known[0] + (st.detail ? " (" + st.detail + ")" : ""), known[1]);
        return;
      }
      if (tries >= 30) {
        clearInterval(timer);
        setStatus("پاسخی از سرویس اعلان نیامد. اینترنت را بررسی کنید و دوباره امتحان کنید.", true);
      }
    }, 1000);
  }

  var TEST_ERROR_TEXT = {
    "no-devices": "هنوز دستگاهی ثبت نشده. اول «فعال‌سازی اعلان» را بزنید.",
    unconfigured: "ارسال اعلان روی سرور تنظیم نشده است.",
    "send-failed": "سرور نتوانست به سرویس اعلان گوگل وصل شود.",
    "not-delivered": "سرویس اعلان، دستگاه‌های ثبت‌شده را نپذیرفت. دوباره «فعال‌سازی اعلان» را بزنید.",
    login: "دوباره وارد شوید.",
    csrf: "صفحه را تازه کنید و دوباره امتحان کنید.",
  };

  function sendTest(csrf) {
    setStatus("در حال ارسال…", false);
    postJson("/api/push/test", { csrf: csrf })
      .then(function (res) {
        if (res && res.ok) {
          var sent = res.sent || {};
          setStatus("اعلان آزمایشی فرستاده شد: وب " + fa(sent.web || 0) + "، اندروید " + fa(sent.android || 0) + ".", false);
          return;
        }
        if (res && res.error === "rate") {
          setStatus("چند ثانیه دیگر دوباره امتحان کنید (" + fa(res.retry_after || 60) + " ثانیه).", true);
          return;
        }
        var code = (res && res.error) || "unknown";
        setStatus(TEST_ERROR_TEXT[code] || "ارسال ناموفق بود (" + code + ").", true);
      })
      .catch(function () {
        setStatus("ارسال ناموفق بود. اتصال را بررسی کنید.", true);
      });
  }

  var enableBtn = document.getElementById("push-enable");
  if (enableBtn) {
    enableBtn.addEventListener("click", function () {
      if (inApp) enableApp();
      else enableWeb();
    });
  }

  var testForm = document.getElementById("push-test-form");
  if (testForm) {
    testForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var input = testForm.querySelector('input[name="csrf"]');
      sendTest(input ? input.value : "");
    });
  }

  if (document.getElementById("push-settings")) {
    getStatus()
      .then(function (st) {
        if (!st || !st.ok) return;
        var d = st.devices || {};
        var total = (d.web || 0) + (d.android || 0);
        if (!st.server) setStatus("ارسال اعلان روی سرور تنظیم نشده است.", true);
        else if (inApp && !st.android) setStatus("اعلان اپ روی سرور تنظیم نشده است.", true);
        else if (total) setStatus(fa(total) + " دستگاه برای اعلان ثبت شده است.", false);
      })
      .catch(function () {});
  }

  if (!inApp && !configError && typeof Notification !== "undefined" && Notification.permission === "granted" && "serviceWorker" in navigator) {
    initMessaging().catch(function (err) {
      if (window.console) console.warn("push refresh failed", (err && err.step) || "", (err && err.detail) || err);
      if (document.getElementById("push-settings")) showWebError(err);
    });
  }
})();
