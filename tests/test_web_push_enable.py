"""Web push enable flow: the page config parses, every step reports its own Persian error and code, register accepts the page."""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_holdings import _register
from tests.test_web_push_hardening import WEB_CFG

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "push_page_harness.js"
PUSH_JS = ROOT / "app" / "static" / "push.js"
PERSIAN = re.compile(r"[\u0600-\u06FF]")


@pytest.fixture()
def web_push(client, monkeypatch):
    import app.config as config

    for k, v in WEB_CFG.items():
        monkeypatch.setattr(config, k, v)
    return client


def _page_config(page: str) -> str:
    m = re.search(r'<script id="firebase-config" type="application/json">(.*?)</script>', page, re.S)
    assert m, "firebase-config script missing"
    return m.group(1)


def _enable(scenario: dict) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    out = subprocess.run(["node", str(HARNESS), str(PUSH_JS), json.dumps(scenario)],
                         capture_output=True, text=True, check=True, timeout=20).stdout
    return json.loads(out)


# ---- the page config is real JSON -------------------------------------------------------------------

def test_page_config_is_parseable_json_not_html_entities(web_push):
    _register(web_push)
    raw = _page_config(web_push.get("/profile").text)
    assert "&#34;" not in raw and "&quot;" not in raw
    cfg = json.loads(raw)
    assert cfg["apiKey"] == WEB_CFG["FIREBASE_API_KEY"]
    assert cfg["messagingSenderId"] == WEB_CFG["FIREBASE_MESSAGING_SENDER_ID"]


def test_page_config_cannot_break_out_of_its_script(web_push, monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "FIREBASE_AUTH_DOMAIN", "fake.example</script><b>x</b>'&")
    _register(web_push)
    page = web_push.get("/profile").text
    raw = _page_config(page)
    assert "</script>" not in raw and "<b>" not in raw
    assert json.loads(raw)["authDomain"] == "fake.example</script><b>x</b>'&"


def test_entity_escaped_config_now_reports_instead_of_dead_button():
    escaped = html.escape(json.dumps({"apiKey": "AIzaFake"}), quote=True)
    out = _enable({"configText": escaped})
    assert out["clickBound"] == 1
    assert out["error"] and out["code"] == "config-parse" and PERSIAN.search(out["status"])


# ---- every step's failure is shown, in Persian, with its code ---------------------------------------

FAILURES = [
    ({"configText": ""}, "config-parse"),
    ({"configText": "{}"}, "config-missing"),
    ({"noPushManager": True}, "push-unsupported"),
    ({"noServiceWorker": True}, "push-unsupported"),
    ({"insecure": True}, "insecure-context"),
    ({"permission": "denied"}, "permission-denied"),
    ({"permission": "default"}, "permission-default"),
    ({"permission": "throw"}, "permission-Error: not allowed"),
    ({"sdk": "fail"}, "sdk-load gstatic"),
    ({"sdk": "nofirebase"}, "sdk-load no-firebase"),
    ({"configFetch": "network"}, "config-fetch TypeError: Failed to fetch"),
    ({"configFetch": "http500"}, "config-fetch http-500"),
    ({"configFetch": "disabled"}, "config-disabled"),
    ({"swRegister": "fail"}, "sw-register SecurityError"),
    ({"swReady": "hang"}, "sw-ready timeout"),
    ({"token": {"code": "messaging/permission-blocked", "message": "blocked"}}, "token messaging/permission-blocked"),
    ({"token": {"code": "messaging/token-subscribe-failed", "message": "Requested entity was not found."}},
     "token messaging/token-subscribe-failed"),
    ({"token": {"name": "AbortError", "message": "Registration failed - push service error"}}, "token AbortError"),
    ({"token": {"code": "installations/request-failed", "message": "403 PERMISSION_DENIED"}},
     "token installations/request-failed"),
    ({"token": {"code": "messaging/unknown", "message": "x"}}, "token messaging/unknown"),
    ({"token": "empty"}, "token-empty"),
    ({"register": {"status": 403, "body": {"ok": False, "error": "origin"}}}, "register origin 403"),
    ({"register": {"status": 401, "body": {"ok": False, "error": "login"}}}, "register login 401"),
    ({"register": {"status": 400, "body": {"ok": False, "error": "invalid"}}}, "register invalid 400"),
    ({"register": "html500"}, "register http-500 500"),
    ({"register": "network"}, "register TypeError: Failed to fetch"),
]


@pytest.mark.parametrize("scenario,code", FAILURES, ids=[c for _, c in FAILURES])
def test_each_failing_step_shows_persian_text_and_code(scenario, code):
    out = _enable(scenario)
    assert out["error"] is True and out["hidden"] is False
    assert PERSIAN.search(out["status"]), out
    assert out["status"] != "در حال فعال‌سازی…"
    assert out["code"] and out["code"].startswith(code), out
    assert out["codeDir"] == "ltr"


def test_distinct_steps_get_distinct_messages():
    texts = {_enable(s)["status"] for s, _ in FAILURES}
    assert len(texts) >= 15


def test_success_registers_web_token_same_origin_json():
    out = _enable({})
    assert out["error"] is False and out["code"] is None and PERSIAN.search(out["status"])
    assert out["tokenOptions"] == {"hasRegistration": True, "vapidKey": "BFakeVapidKey"}
    reg = [r for r in out["requests"] if r["url"] == "/api/push/register"]
    assert reg == [{"url": "/api/push/register", "method": "POST", "credentials": "same-origin",
                    "contentType": "application/json", "body": {"token": "fake-web-token", "platform": "web"}}]
    assert any(r["url"] == "sw:/sw.js" and r["updateViaCache"] == "none" for r in out["requests"])


def test_success_without_vapid_key_still_passes_registration():
    out = _enable({"noVapid": True})
    assert out["error"] is False
    assert out["tokenOptions"] == {"hasRegistration": True, "vapidKey": None}


# ---- the register endpoint accepts what the page sends ----------------------------------------------

def _web_count(client) -> int:
    return client.get("/api/push/status").json()["devices"]["web"]


def test_register_needs_no_csrf_and_accepts_the_page_request(web_push):
    _register(web_push)
    r = web_push.post("/api/push/register", json={"token": "fake-web-a", "platform": "web"},
                      headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200 and r.json()["ok"]
    assert _web_count(web_push) == 1


@pytest.mark.parametrize("host", ["daraiito.ir", "portfolio.vahidtwo.ir"])
def test_register_same_origin_on_both_hosts(web_push, host):
    _register(web_push)
    r = web_push.post("/api/push/register", json={"token": "fake-web-" + host, "platform": "web"},
                      headers={"Host": host, "Origin": "https://" + host, "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200 and r.json()["ok"]


def test_register_rejects_a_different_host_origin(web_push):
    _register(web_push)
    r = web_push.post("/api/push/register", json={"token": "fake-web-www"},
                      headers={"Host": "daraiito.ir", "Origin": "https://www.daraiito.ir"})
    assert r.status_code == 403 and r.json()["error"] == "origin"


def test_register_without_origin_header_is_accepted(web_push):
    _register(web_push)
    r = web_push.post("/api/push/register", json={"token": "fake-web-noorigin", "platform": "web"})
    assert r.status_code == 200 and r.json()["ok"]


def test_register_reads_json_whatever_the_content_type(web_push):
    _register(web_push)
    r = web_push.post("/api/push/register", content=json.dumps({"token": "fake-web-ct", "platform": "web"}),
                      headers={"Content-Type": "text/plain"})
    assert r.status_code == 200 and r.json()["ok"]


def test_register_without_session_cookie_is_login(web_push):
    r = web_push.post("/api/push/register", json={"token": "fake-web-anon", "platform": "web"})
    assert r.status_code == 401 and r.json()["error"] == "login"
