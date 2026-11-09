"""Push: device registration, status, the settings test button (mocked Firebase), web worker and app wiring."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_holdings import _csrf, _register

ROOT = Path(__file__).resolve().parent.parent
KT = ROOT / "android" / "app" / "src" / "main" / "java" / "app" / "myinventory"

WEB_CFG = {
    "FIREBASE_API_KEY": "AIzaFakeFakeFakeFakeFakeFakeFakeFake000",
    "FIREBASE_AUTH_DOMAIN": "fake-project.firebaseapp.com",
    "FIREBASE_PROJECT_ID": "fake-project",
    "FIREBASE_MESSAGING_SENDER_ID": "123456789012",
    "FIREBASE_APP_ID": "1:123456789012:web:abcdef0123456789",
}
ANDROID_APP_ID = "1:123456789012:android:abcdef0123456789"


@pytest.fixture()
def web_push(client, monkeypatch):
    import app.config as config

    for k, v in WEB_CFG.items():
        monkeypatch.setattr(config, k, v)
    return client


class FakeFirebase:
    """Stands in for firebase_admin.messaging.send_each: records messages, answers per token."""

    def __init__(self, monkeypatch, fail_tokens=()):
        from firebase_admin import messaging

        import app.firebase_push as fp

        self.messages, self.fail_tokens = [], set(fail_tokens)
        monkeypatch.setattr(fp, "firebase_admin_ready", lambda: True)
        monkeypatch.setattr(messaging, "send_each", self.send_each)

    def send_each(self, messages, dry_run=False):
        from firebase_admin import messaging

        self.messages.extend(messages)
        out = []
        for m in messages:
            if m.token in self.fail_tokens:
                out.append(SimpleNamespace(success=False, exception=messaging.UnregisteredError("gone")))
            else:
                out.append(SimpleNamespace(success=True, exception=None))
        return SimpleNamespace(responses=out, success_count=sum(r.success for r in out))


def _tokens():
    from app.db import SessionLocal
    from app.models import PushDeviceToken

    with SessionLocal() as db:
        return sorted((r.token, r.platform) for r in db.query(PushDeviceToken).all())


def _test(client, **headers):
    return client.post("/api/push/test", json={"csrf": _csrf(client)}, headers=headers)


# ---- registration -----------------------------------------------------------------------------------

def test_register_android_and_web_tokens(client):
    _register(client, "fake_push_a")
    assert client.post("/api/push/register", json={"token": "fake-android-1", "platform": "android"}).json()["ok"]
    assert client.post("/api/push/register", json={"token": "fake-web-1", "platform": "web"}).json()["ok"]
    assert client.post("/api/push/register", json={"token": "fake-odd-1", "platform": "ios"}).json()["ok"]
    assert _tokens() == [("fake-android-1", "android"), ("fake-odd-1", "web"), ("fake-web-1", "web")]
    r = client.post("/api/push/register", json={"token": "fake-android-1", "platform": "android"})
    assert r.json()["ok"] and len(_tokens()) == 3
    assert "no-store" in r.headers["cache-control"]


def test_register_rejects_cross_site_bad_input_and_logged_out(client):
    _register(client, "fake_push_b")
    evil = client.post("/api/push/register", json={"token": "fake-x"}, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    site = client.post("/api/push/register", json={"token": "fake-x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert site.status_code == 403
    assert client.post("/api/push/register", json={"token": ""}).status_code == 400
    assert client.post("/api/push/register", json={"token": "x" * 5000}).status_code == 400
    assert client.post("/api/push/register", content=b"not json").status_code == 400
    assert _tokens() == []
    client.post("/logout", data={"csrf": _csrf(client)})
    assert client.post("/api/push/register", json={"token": "fake-x"}).status_code == 401


def test_unregister_removes_only_own_token(client):
    _register(client, "fake_push_c")
    client.post("/api/push/register", json={"token": "fake-c", "platform": "android"})
    assert client.post("/api/push/unregister", json={"token": "fake-c"}).json()["ok"]
    assert _tokens() == []


# ---- status and config ------------------------------------------------------------------------------

def test_status_counts_devices_without_tokens(client):
    _register(client, "fake_push_d")
    client.post("/api/push/register", json={"token": "fake-d-secret", "platform": "android"})
    r = client.get("/api/push/status")
    body = r.json()
    assert body["ok"] and body["devices"] == {"web": 0, "android": 1}
    assert "fake-d-secret" not in r.text and "no-store" in r.headers["cache-control"]
    client.post("/logout", data={"csrf": _csrf(client)})
    assert client.get("/api/push/status").status_code == 401


def test_config_serves_android_options_only_when_valid(web_push, monkeypatch):
    import app.config as config

    assert web_push.get("/api/push/config").json()["android"] is None
    monkeypatch.setattr(config, "FIREBASE_ANDROID_APP_ID", ANDROID_APP_ID)
    android = web_push.get("/api/push/config").json()["android"]
    assert android == {"appId": ANDROID_APP_ID, "apiKey": WEB_CFG["FIREBASE_API_KEY"],
                       "projectId": "fake-project", "senderId": "123456789012"}
    monkeypatch.setattr(config, "FIREBASE_ANDROID_API_KEY", "AIzaAndroidFakeFakeFakeFakeFakeFake000")
    assert web_push.get("/api/push/config").json()["android"]["apiKey"].startswith("AIzaAndroid")
    monkeypatch.setattr(config, "FIREBASE_ANDROID_APP_ID", "1:999999999999:android:abcdef")
    assert web_push.get("/api/push/config").json()["android"] is None
    monkeypatch.setattr(config, "FIREBASE_ANDROID_APP_ID", WEB_CFG["FIREBASE_APP_ID"])
    assert web_push.get("/api/push/config").json()["android"] is None


def test_config_never_exposes_server_credentials(web_push, monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "FIREBASE_CLIENT_EMAIL", "fake-sa@fake-project.iam.gserviceaccount.com")
    monkeypatch.setattr(config, "FIREBASE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\\nfake\\n-----END PRIVATE KEY-----")
    monkeypatch.setattr(config, "FIREBASE_ANDROID_APP_ID", ANDROID_APP_ID)
    text = web_push.get("/api/push/config").text
    assert "PRIVATE KEY" not in text and "gserviceaccount" not in text


# ---- test notification ------------------------------------------------------------------------------

def test_test_send_reaches_own_web_and_android_devices(client, monkeypatch):
    fake = FakeFirebase(monkeypatch)
    _register(client, "fake_push_e")
    client.post("/api/push/register", json={"token": "fake-e-web", "platform": "web"})
    client.post("/api/push/register", json={"token": "fake-e-android", "platform": "android"})
    body = _test(client).json()
    assert body["ok"] and body["sent"] == {"web": 1, "android": 1} and body["error"] is None
    by_token = {m.token: m for m in fake.messages}
    assert set(by_token) == {"fake-e-web", "fake-e-android"}
    for m in fake.messages:
        assert m.notification is None
        assert m.data["title"] and m.data["body"] and m.data["url"].startswith("/")
        assert not re.search(r"[0-9۰-۹]", m.data["body"])
    assert by_token["fake-e-android"].android.priority == "high"
    assert by_token["fake-e-web"].webpush is not None


def test_test_send_only_targets_the_signed_in_user(client, monkeypatch):
    fake = FakeFirebase(monkeypatch)
    _register(client, "fake_push_other")
    client.post("/api/push/register", json={"token": "fake-other", "platform": "android"})
    client.post("/logout", data={"csrf": _csrf(client)})
    _register(client, "fake_push_me")
    client.post("/api/push/register", json={"token": "fake-me", "platform": "web"})
    assert _test(client).json()["sent"] == {"web": 1, "android": 0}
    assert [m.token for m in fake.messages] == ["fake-me"]


def test_test_send_drops_unregistered_tokens_and_reports(client, monkeypatch):
    FakeFirebase(monkeypatch, fail_tokens={"fake-f-old"})
    _register(client, "fake_push_f")
    client.post("/api/push/register", json={"token": "fake-f-old", "platform": "android"})
    body = _test(client).json()
    assert not body["ok"] and body["error"] == "not-delivered" and body["removed"] == 1
    assert _tokens() == []
    assert _test(client).json()["error"] == "no-devices"


def test_test_send_errors_are_clear(client, monkeypatch):
    import app.firebase_push as fp

    _register(client, "fake_push_g")
    monkeypatch.setattr(fp, "firebase_admin_ready", lambda: True)
    assert _test(client).json()["error"] == "no-devices"
    client.post("/api/push/register", json={"token": "fake-g", "platform": "web"})
    monkeypatch.setattr(fp, "firebase_admin_ready", lambda: False)
    assert _test(client).json()["error"] == "unconfigured"
    from firebase_admin import messaging

    def boom(messages, dry_run=False):
        raise RuntimeError("network down")

    monkeypatch.setattr(fp, "firebase_admin_ready", lambda: True)
    monkeypatch.setattr(messaging, "send_each", boom)
    assert _test(client).json()["error"] == "send-failed"
    assert _tokens() == [("fake-g", "web")]


def test_test_send_needs_session_csrf_same_origin_and_is_rate_limited(client, monkeypatch):
    FakeFirebase(monkeypatch)
    assert client.post("/api/push/test", json={"csrf": "x"}).status_code == 401
    _register(client, "fake_push_h")
    client.post("/api/push/register", json={"token": "fake-h", "platform": "web"})
    assert client.post("/api/push/test", json={"csrf": "wrong"}).json()["error"] == "csrf"
    assert _test(client, Origin="https://evil.example").status_code == 403
    for _ in range(3):
        assert _test(client).json()["ok"]
    limited = _test(client)
    assert limited.status_code == 429 and limited.json()["error"] == "rate"
    assert int(limited.headers["retry-after"]) > 0


def test_settings_page_has_enable_and_test_buttons(web_push):
    _register(web_push, "fake_push_i")
    html = web_push.get("/profile").text
    assert 'id="push-enable"' in html and 'id="push-test-form"' in html and 'id="push-test"' in html
    assert "/static/push.js" in html


def test_due_reminder_sender_still_returns_a_count(client, monkeypatch):
    FakeFirebase(monkeypatch)
    from app.db import SessionLocal
    from app.firebase_push import send_push_to_user

    _register(client, "fake_push_j")
    client.post("/api/push/register", json={"token": "fake-j", "platform": "android"})
    with SessionLocal() as db:
        from app.models import User

        uid = db.query(User).filter_by(username="fake_push_j").one().id
        assert send_push_to_user(db, uid, title="یادآوری قسط", body="قسط فیک فردا سررسید می‌شود.") == 1


# ---- web worker and Android wiring ------------------------------------------------------------------

def test_service_worker_shows_data_messages_and_opens_same_origin_path(web_push):
    sw = web_push.get("/sw.js").text
    assert 'addEventListener("notificationclick"' in sw
    assert "function showPushNotification" in sw and "pushTargetPath" in sw
    assert "if (payload.notification) return;" in sw
    assert 'if (!firebaseMessaging) self.addEventListener("push"' in sw


def test_android_reads_firebase_options_at_runtime():
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert "google-services" not in gradle
    assert "google-services" not in (ROOT / "android" / "build.gradle.kts").read_text(encoding="utf-8")
    manifest = (ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:name=".InventoryApp"' in manifest
    assert "android.permission.POST_NOTIFICATIONS" in manifest
    reg = (KT / "PushRegistrar.kt").read_text(encoding="utf-8")
    assert "/api/push/config" in reg and "/api/push/register" in reg and "FirebaseOptions.Builder()" in reg
    bridge = (KT / "AndroidBridge.kt").read_text(encoding="utf-8")
    assert "fun enablePush()" in bridge and "fun pushState()" in bridge
    service = (KT / "InventoryMessagingService.kt").read_text(encoding="utf-8")
    assert 'message.data["title"]' in service and "NotificationTarget.safePath" in service
    assert "POST_NOTIFICATIONS" in service
    assert "PushRegistrar.registerFcmToken(this)" in (KT / "HomeActivity.kt").read_text(encoding="utf-8")


def test_release_json_matches_gradle_version():
    rel = json.loads((ROOT / "app" / "android_release.json").read_text(encoding="utf-8"))
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert f'?.toInt() ?: {rel["versionCode"]}' in gradle and f'?: "{rel["versionName"]}"' in gradle


def _js_function(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    depth, i = 0, src.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        i += 1
        if depth == 0:
            return src[start:i]


def test_foreground_notification_opens_its_own_path_on_click():
    js = (ROOT / "app" / "static" / "push.js").read_text(encoding="utf-8")
    on_message = js[js.index("messaging.onMessage("):js.index("return navigator.serviceWorker")]
    assert "var url = pushTargetPath(data.url);" in on_message
    assert "data: { url: url }" in on_message
    assert "shown.onclick = function" in on_message
    assert "window.location.assign(new URL(url, window.location.origin).href)" in on_message


def test_foreground_and_worker_use_the_same_path_rule():
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node not installed")
    page = _js_function((ROOT / "app" / "static" / "push.js").read_text(encoding="utf-8"), "pushTargetPath")
    worker = _js_function((ROOT / "app" / "static" / "sw.js").read_text(encoding="utf-8"), "pushTargetPath")
    cases = ["/dashboard?tab=debts", "/profile#push-settings", "https://evil.example/x", "//evil.example/x",
             "/\\\\evil.example", "javascript:alert(1)", "/a b", "", None, 42]
    code = (
        "const cases = JSON.parse(process.argv[1]);"
        "const page = (function(){ var DEFAULT_PATH = '/dashboard';" + page + " return pushTargetPath; })();"
        "const worker = (function(){ const PUSH_DEFAULT_PATH = '/dashboard';" + worker + " return pushTargetPath; })();"
        "console.log(JSON.stringify([cases.map(page), cases.map(worker)]));"
    )
    out = subprocess.run(["node", "-e", code, json.dumps(cases)], capture_output=True, text=True, check=True).stdout
    page_out, worker_out = json.loads(out)
    assert page_out == worker_out
    assert page_out == ["/dashboard?tab=debts", "/profile#push-settings"] + ["/dashboard"] * 8


def test_register_endpoints_explain_why_no_csrf():
    src = (ROOT / "app" / "push_routes.py").read_text(encoding="utf-8")
    assert src.count("# No CSRF token: the Android app posts JSON without one; the same-origin check guards") == 2
