"""Web push: SDK first in the served worker, one display owner, webpush notification + link, every tap opens."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_holdings import _register

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "push_sw_harness.js"
WEB_CFG = {
    "FIREBASE_API_KEY": "AIzaFakeFakeFakeFakeFakeFakeFakeFake000",
    "FIREBASE_AUTH_DOMAIN": "fake-project.firebaseapp.com",
    "FIREBASE_PROJECT_ID": "fake-project",
    "FIREBASE_MESSAGING_SENDER_ID": "123456789012",
    "FIREBASE_APP_ID": "1:123456789012:web:abcdef0123456789",
}


@pytest.fixture()
def web_push(client, monkeypatch):
    import app.config as config

    for k, v in WEB_CFG.items():
        monkeypatch.setattr(config, k, v)
    return client


def _served(client, tmp_path) -> Path:
    path = tmp_path / "served-sw.js"
    path.write_text(client.get("/sw.js").text, encoding="utf-8")
    return path


def _run(sw: Path, scenario: dict) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    out = subprocess.run(["node", str(HARNESS), str(sw), json.dumps(scenario)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


# ---- served worker order ----------------------------------------------------------------------------

def test_click_owner_then_sdk_import_and_init_come_first(web_push):
    sw = web_push.get("/sw.js").text
    order = [
        'self.addEventListener("notificationclick", onPushNotificationClick);',
        'importScripts("https://www.gstatic.com/firebasejs/11.6.0/firebase-app-compat.js");',
        'importScripts("https://www.gstatic.com/firebasejs/11.6.0/firebase-messaging-compat.js");',
        "firebase.initializeApp(",
        "firebaseMessaging.onBackgroundMessage(",
        'const VERSION = "inventory-v',
        'self.addEventListener("install"',
        'self.addEventListener("fetch"',
    ]
    positions = [sw.index(s) for s in order]
    assert positions == sorted(positions)
    assert sw.count("importScripts(") == 2
    assert 'const PUSH_APP_HOSTS = "daraiito.ir,portfolio.vahidtwo.ir".split(",")' in sw


def test_worker_without_firebase_config_still_owns_taps(client):
    sw = client.get("/sw.js").text
    assert sw.startswith("// Registered before the Firebase SDK")
    assert 'self.addEventListener("notificationclick", onPushNotificationClick);' in sw
    assert "importScripts(" not in sw


# ---- server message shape ---------------------------------------------------------------------------

def test_web_message_has_webpush_notification_and_absolute_link(monkeypatch):
    import app.config as config
    from app.firebase_push import build_message
    from app.push_routes import TEST_BODY, TEST_TITLE

    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")
    m = build_message("fake-web", "web", title=TEST_TITLE, body=TEST_BODY,
                      data={"type": "test", "url": "/profile#push-settings"})
    assert m.notification is None and m.android is None
    note = m.webpush.notification
    assert note.title == TEST_TITLE and note.body == TEST_BODY and note.icon == "/static/icons/icon-192.png"
    assert note.tag == "test"
    assert m.webpush.fcm_options.link == "https://daraiito.ir/profile#push-settings"
    assert m.data["url"] == "/profile#push-settings" and m.data["title"] == TEST_TITLE
    for text in (note.title, note.body):
        assert not re.search(r"[0-9۰-۹٠-٩]", text)


def test_web_link_uses_public_base_and_rejects_foreign_paths(monkeypatch):
    import app.config as config
    from app.firebase_push import build_message, push_link

    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://portfolio.vahidtwo.ir")
    assert push_link("/dashboard?tab=debts") == "https://portfolio.vahidtwo.ir/dashboard?tab=debts"
    for bad in ("https://evil.example/x", "//evil.example", "/\\evil", "/a b", "", None):
        assert push_link(bad) == "https://portfolio.vahidtwo.ir/dashboard"
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "http://insecure.example")
    assert push_link("/x") == "https://daraiito.ir/x"
    m = build_message("t", "web", title="یادآوری قسط", body="متن", data={"url": "https://evil.example"})
    assert m.webpush.fcm_options.link == "https://daraiito.ir/dashboard"


def test_android_message_stays_data_only():
    from app.firebase_push import build_message

    m = build_message("fake-android", "android", title="یادآوری قسط", body="متن", data={"type": "debt_upcoming", "url": "/dashboard?tab=debts"})
    assert m.notification is None and m.webpush is None
    assert m.android.priority == "high" and m.android.notification is None
    assert m.data == {"type": "debt_upcoming", "url": "/dashboard?tab=debts", "title": "یادآوری قسط", "body": "متن"}


def test_due_reminder_text_carries_no_amount():
    import jdatetime

    from app.due_reminders import overdue_text, upcoming_text
    from app.formatting import persian_digits
    from app.models import Debt

    debt = Debt(title="وام فیک", monthly_toman=12345678, months_left=5, due_year=1405, due_month=8, due_day=20)
    due = jdatetime.date(1405, 8, 20)
    for title, body in (upcoming_text(debt, due, 3), overdue_text(debt, due)):
        for amount in ("12345678", "12,345,678", persian_digits("12345678"), persian_digits("12,345,678")):
            assert amount not in title and amount not in body
        assert not re.search(r"[0-9۰-۹]", title)


# ---- display owner and taps (Node) ------------------------------------------------------------------

NOTE_MSG = {"notification": {"title": "یادآوری قسط", "body": "متن"},
            "data": {"title": "یادآوری قسط", "body": "متن", "url": "/dashboard?tab=debts", "type": "debt_upcoming"},
            "fcmOptions": {"link": "https://daraiito.ir/dashboard?tab=debts"}}
DATA_MSG = {"data": {"title": "اعلان", "body": "متن", "url": "/profile", "type": "test"}}


def test_one_display_owner_with_and_without_the_sdk(web_push, tmp_path):
    sw = _served(web_push, tmp_path)
    with_sdk = _run(sw, {"origin": "https://daraiito.ir", "sdk": True, "steps": [
        {"kind": "background", "payload": NOTE_MSG}, {"kind": "background", "payload": DATA_MSG}]})
    assert with_sdk["hasBackground"] and "push" not in with_sdk["listeners"]
    assert with_sdk["results"][0]["shown"] == []
    assert [s["title"] for s in with_sdk["results"][1]["shown"]] == ["اعلان"]

    blocked = _run(sw, {"origin": "https://daraiito.ir", "sdk": False, "steps": [
        {"kind": "push", "payload": NOTE_MSG}, {"kind": "push", "payload": DATA_MSG}]})
    assert not blocked["hasBackground"] and blocked["listeners"]["push"] == 1
    first, second = blocked["results"]
    assert len(first["shown"]) == 1 and first["shown"][0]["data"]["url"] == "/dashboard?tab=debts"
    assert len(second["shown"]) == 1 and second["shown"][0]["data"]["url"] == "/profile"


def _click(sw, origin, data, windows=()):
    res = _run(sw, {"origin": origin, "sdk": True,
                    "steps": [{"kind": "click", "data": data, "windows": list(windows)}]})
    assert res["listeners"]["notificationclick"] == 2  # ours first, then the SDK's
    step = res["results"][0]
    assert step["waited"] == 1
    assert {"how": "sdk-click"} not in step["opened"]  # ours stopped the SDK's handler
    assert step["opened"], "a tap must always open or focus something"
    return step["opened"]


def test_tap_on_sdk_notification_opens_its_link_on_this_host(web_push, tmp_path):
    sw = _served(web_push, tmp_path)
    fcm = {"FCM_MSG": NOTE_MSG}
    assert _click(sw, "https://daraiito.ir", fcm) == [{"how": "open", "url": "https://daraiito.ir/dashboard?tab=debts"}]
    assert _click(sw, "https://portfolio.vahidtwo.ir", fcm) == [
        {"how": "open", "url": "https://portfolio.vahidtwo.ir/dashboard?tab=debts"}]


def test_tap_with_foreign_link_falls_back_to_data_url_then_dashboard(web_push, tmp_path):
    sw = _served(web_push, tmp_path)
    foreign = {"FCM_MSG": {**NOTE_MSG, "fcmOptions": {"link": "https://evil.example/x"}}}
    assert _click(sw, "https://daraiito.ir", foreign) == [{"how": "open", "url": "https://daraiito.ir/dashboard?tab=debts"}]
    bare = {"FCM_MSG": {"notification": {"title": "t"}, "fcmOptions": {"link": "https://evil.example/x"}}}
    assert _click(sw, "https://daraiito.ir", bare) == [{"how": "open", "url": "https://daraiito.ir/dashboard"}]


def test_tap_on_own_notification_uses_data_url_and_rejects_foreign(web_push, tmp_path):
    sw = _served(web_push, tmp_path)
    assert _click(sw, "https://daraiito.ir", {"url": "/profile#push-settings"}) == [
        {"how": "open", "url": "https://daraiito.ir/profile#push-settings"}]
    assert _click(sw, "https://daraiito.ir", {"url": "https://evil.example/x"}) == [
        {"how": "open", "url": "https://daraiito.ir/dashboard"}]
    assert _click(sw, "https://daraiito.ir", {}) == [{"how": "open", "url": "https://daraiito.ir/dashboard"}]


def test_tap_focuses_an_open_window_and_navigates_or_opens(web_push, tmp_path):
    sw = _served(web_push, tmp_path)
    data = {"url": "/dashboard?tab=debts"}
    controlled = [{"url": "https://daraiito.ir/profile", "controlled": True}]
    assert _click(sw, "https://daraiito.ir", data, controlled) == [
        {"how": "focus", "url": "https://daraiito.ir/profile"},
        {"how": "navigate", "url": "https://daraiito.ir/dashboard?tab=debts"}]
    uncontrolled = [{"url": "https://daraiito.ir/profile", "controlled": False}]
    assert _click(sw, "https://daraiito.ir", data, uncontrolled)[-1] == {
        "how": "open", "url": "https://daraiito.ir/dashboard?tab=debts"}
    foreign_window = [{"url": "https://evil.example/", "controlled": True}]
    assert _click(sw, "https://daraiito.ir", data, foreign_window) == [
        {"how": "open", "url": "https://daraiito.ir/dashboard?tab=debts"}]
