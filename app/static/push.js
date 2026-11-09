(function () {
  var configEl = document.getElementById("firebase-config");
  if (!configEl || !configEl.textContent) return;

  var firebaseConfig;
  try {
    firebaseConfig = JSON.parse(configEl.textContent);
  } catch (e) {
    return;
  }

  var DEFAULT_TITLE = "دارایی‌تو";
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

  function setStatus(text, isError) {
    var el = document.getElementById("push-status");
    if (!el) return;
    el.textContent = text;
    el.hidden = !text;
    el.classList.toggle("toast-warn", !!isError);
    el.classList.toggle("toast-ok", !isError && !!text);
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).then(function (response) {
      return response.json().catch(function () { return { ok: false, error: "http-" + response.status }; });
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

  function webErrorText(err) {
    var code = String((err && (err.code || err.name)) || "");
    var msg = String((err && err.message) || "");
    if (code.indexOf("permission-blocked") >= 0 || code.indexOf("permission-default") >= 0) {
      return "اجازهٔ اعلان در مرورگر بسته است. از تنظیمات سایت در مرورگر آن را باز کنید.";
    }
    if (msg === "sdk-load") return "کتابخانهٔ اعلان (gstatic.com) بار نشد. اتصال اینترنت یا فیلترشکن را بررسی کنید.";
    if (msg === "push-unsupported") return "این مرورگر از اعلان پشتیبانی نمی‌کند.";
    if (code === "AbortError" || /push service|token-subscribe|installations/i.test(code + " " + msg)) {
      return "سرویس اعلان گوگل در دسترس نیست (" + (code || msg) + "). با فیلترشکن یا شبکهٔ دیگر دوباره امتحان کنید.";
    }
    return "فعال‌سازی اعلان ممکن نشد (" + (code || msg || "unknown") + ")";
  }

  function initMessaging() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return Promise.reject(new Error("push-unsupported"));
    }
    return loadScript(SDK + "firebase-app-compat.js")
      .then(function () { return loadScript(SDK + "firebase-messaging-compat.js"); })
      .then(function () {
        if (!window.firebase) throw new Error("sdk-load");
        if (!firebase.apps.length) firebase.initializeApp(firebaseConfig);
        return fetch("/api/push/config").then(function (r) { return r.json(); });
      })
      .then(function (cfg) {
        if (!cfg.enabled) return null;
        var messaging = firebase.messaging();
        messaging.onMessage(function (payload) {
          var data = payload.data || {};
          var note = payload.notification || {};
          var title = note.title || data.title || DEFAULT_TITLE;
          var body = note.body || data.body || "";
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            try { new Notification(title, { body: body, icon: "/static/icons/icon-192.png" }); } catch (e) {}
          }
          setStatus(body || title, false);
        });
        return navigator.serviceWorker
          .register("/sw.js", { updateViaCache: "none" })
          .then(function () { return navigator.serviceWorker.ready; })
          .then(function (registration) {
            var options = { serviceWorkerRegistration: registration };
            if (cfg.vapidKey) options.vapidKey = cfg.vapidKey;
            return messaging.getToken(options);
          })
          .then(function (token) {
            if (!token) return null;
            return postJson("/api/push/register", { token: token, platform: "web" }).then(function (res) {
              if (!res || !res.ok) throw new Error("register-" + ((res && res.error) || "failed"));
              return token;
            });
          });
      });
  }

  function enableWeb() {
    if (!("Notification" in window)) {
      setStatus("این مرورگر از اعلان پشتیبانی نمی‌کند.", true);
      return;
    }
    setStatus("در حال فعال‌سازی…", false);
    Notification.requestPermission().then(function (perm) {
      if (perm !== "granted") {
        setStatus("اجازهٔ اعلان داده نشد. از تنظیمات سایت در مرورگر آن را باز کنید.", true);
        return;
      }
      initMessaging()
        .then(function (token) {
          if (token) setStatus("اعلان‌های این مرورگر فعال شد. «ارسال اعلان آزمایشی» را بزنید.", false);
          else setStatus("توکن اعلان دریافت نشد. دوباره امتحان کنید.", true);
        })
        .catch(function (err) {
          if (window.console) console.error("push init failed", err);
          setStatus(webErrorText(err), true);
        });
    });
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

  if (!inApp && typeof Notification !== "undefined" && Notification.permission === "granted" && "serviceWorker" in navigator) {
    initMessaging().catch(function (err) {
      if (window.console) console.warn("push refresh failed", err);
    });
  }
})();
