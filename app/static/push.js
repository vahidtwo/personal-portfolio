(function () {
  var configEl = document.getElementById("firebase-config");
  if (!configEl || !configEl.textContent) return;

  var firebaseConfig;
  try {
    firebaseConfig = JSON.parse(configEl.textContent);
  } catch (e) {
    return;
  }

  var currentToken = null;

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[src="' + src + '"]');
      if (existing) {
        resolve();
        return;
      }
      var script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
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

  function registerToken(token) {
    return fetch("/api/push/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ token: token, platform: "web" }),
    }).then(function (response) {
      return response.json();
    });
  }

  function initMessaging() {
    return loadScript("https://www.gstatic.com/firebasejs/11.6.0/firebase-app-compat.js")
      .then(function () {
        return loadScript("https://www.gstatic.com/firebasejs/11.6.0/firebase-messaging-compat.js");
      })
      .then(function () {
        if (!window.firebase) throw new Error("firebase");
        if (!firebase.apps.length) {
          firebase.initializeApp(firebaseConfig);
        }
        return fetch("/api/push/config")
          .then(function (r) {
            return r.json();
          })
          .then(function (cfg) {
            if (!cfg.enabled) return null;
            var messaging = firebase.messaging();
            messaging.onMessage(function (payload) {
              var title = (payload.notification && payload.notification.title) || "موجودی من";
              var body = (payload.notification && payload.notification.body) || "";
              if (typeof Notification !== "undefined" && Notification.permission === "granted") {
                new Notification(title, { body: body, icon: "/static/icons/icon-192.png" });
              }
              setStatus(body || title, false);
            });
            return navigator.serviceWorker
              .register("/sw.js")
              .then(function (registration) {
                var options = { serviceWorkerRegistration: registration };
                if (cfg.vapidKey) options.vapidKey = cfg.vapidKey;
                return messaging.getToken(options);
              })
              .then(function (token) {
                if (!token) return null;
                currentToken = token;
                return registerToken(token).then(function () {
                  setStatus("اعلان‌ها فعال شد.", false);
                  return token;
                });
              });
          });
      });
  }

  var enableBtn = document.getElementById("push-enable");
  if (enableBtn) {
    enableBtn.addEventListener("click", function () {
      if (!("Notification" in window)) {
        setStatus("مرورگر از اعلان پشتیبانی نمی‌کند.", true);
        return;
      }
      Notification.requestPermission().then(function (perm) {
        if (perm !== "granted") {
          setStatus("اجازه اعلان داده نشد.", true);
          return;
        }
        initMessaging().catch(function () {
          setStatus("فعال‌سازی اعلان ممکن نشد.", true);
        });
      });
    });
  }

  if (Notification.permission === "granted") {
    initMessaging().catch(function () {});
  }
})();
