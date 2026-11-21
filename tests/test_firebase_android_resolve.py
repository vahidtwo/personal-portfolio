"""Android Firebase app ID found with the service account (Management API mocked), cached, never blocking."""
from __future__ import annotations

import base64
import json
import logging
import threading
import time

import pytest

SENDER = "123456789012"
PROJECT = "fake-project"
APP_ID = f"1:{SENDER}:android:abcdef0123456789"
NEW_APP_ID = f"1:{SENDER}:android:0123456789abcdef"
WEB_KEY = "AIzaWebFakeFakeFakeFakeFakeFakeFake0000"
ANDROID_KEY = "AIzaAndroidFakeFakeFakeFakeFakeFake000"


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _gs_config(app_id, key=ANDROID_KEY):
    data = {"project_info": {"project_number": SENDER, "project_id": PROJECT},
            "client": [{"client_info": {"mobilesdk_app_id": app_id,
                                        "android_client_info": {"package_name": "app.myinventory"}},
                        "api_key": [{"current_key": key}]}]}
    return {"configFilename": "google-services.json",
            "configFileContents": base64.b64encode(json.dumps(data).encode()).decode()}


class FakeSession:
    """Answers the Management API URLs the resolver uses; records every call."""

    def __init__(self, apps=(), list_status=200, config_status=200, create_polls=1, list_error=None):
        self.apps, self.list_status, self.config_status = list(apps), list_status, config_status
        self.create_polls, self.list_error = create_polls, list_error
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url))
        if url.endswith(f"/projects/{PROJECT}/androidApps"):
            if self.list_status != 200:
                return Resp(self.list_status, {"error": self.list_error})
            return Resp(200, {"apps": self.apps})
        if url.endswith("/config"):
            if self.config_status != 200:
                return Resp(self.config_status, {"error": {"code": 403, "status": "PERMISSION_DENIED"}})
            return Resp(200, _gs_config(url.split("/androidApps/")[1].split("/")[0]))
        if "/operations/" in url:
            self.create_polls -= 1
            if self.create_polls > 0:
                return Resp(200, {"name": "operations/fake-op", "done": False})
            return Resp(200, {"name": "operations/fake-op", "done": True,
                              "response": {"appId": NEW_APP_ID, "packageName": "app.myinventory"}})
        raise AssertionError(url)

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        assert url.endswith(f"/projects/{PROJECT}/androidApps")
        return Resp(200, {"name": "operations/fake-op", "done": False})


@pytest.fixture()
def fa(client, monkeypatch, tmp_path):
    import app.config as config
    import app.firebase_android as fa

    for k, v in {"FIREBASE_API_KEY": WEB_KEY, "FIREBASE_AUTH_DOMAIN": f"{PROJECT}.firebaseapp.com",
                 "FIREBASE_PROJECT_ID": PROJECT, "FIREBASE_MESSAGING_SENDER_ID": SENDER,
                 "FIREBASE_APP_ID": f"1:{SENDER}:web:abcdef", "FIREBASE_ANDROID_APP_ID": "",
                 "FIREBASE_ANDROID_API_KEY": "", "FIREBASE_CLIENT_EMAIL": "fake@fake-project.iam.gserviceaccount.com",
                 "FIREBASE_PRIVATE_KEY": "fake"}.items():
        monkeypatch.setattr(config, k, v)
    fa.reset_for_tests()
    yield fa
    fa.reset_for_tests()


def _cache(tmp_path):
    return json.loads((tmp_path / "firebase_android.json").read_text())


def test_existing_app_is_found_by_package_and_key_comes_from_get_config(fa, tmp_path):
    s = FakeSession(apps=[{"packageName": "other.app", "appId": f"1:{SENDER}:android:ffff", "state": "ACTIVE"},
                          {"packageName": "app.myinventory", "appId": APP_ID, "state": "ACTIVE"}])
    out = fa.resolve_once(lambda: s)
    assert out == {"appId": APP_ID, "apiKey": ANDROID_KEY, "projectId": PROJECT, "senderId": SENDER}
    assert not [c for c in s.calls if c[0] == "POST"]
    assert fa.android_push_config() == out
    saved = _cache(tmp_path)
    assert saved["appId"] == APP_ID and saved["keySource"] == "androidApps.getConfig"


def test_missing_app_is_created_and_operation_polled(fa):
    s = FakeSession(apps=[], create_polls=3)
    slept = []
    out = fa.resolve_once(lambda: s, sleep=slept.append)
    assert out["appId"] == NEW_APP_ID
    posts = [c for c in s.calls if c[0] == "POST"]
    assert posts == [("POST", f"{fa.API}/projects/{PROJECT}/androidApps",
                      {"packageName": "app.myinventory", "displayName": "daraiito"})]
    assert len([c for c in s.calls if "/operations/" in c[1]]) == 3 and len(slept) == 3


def test_web_key_fallback_is_logged_when_get_config_is_denied(fa, caplog):
    s = FakeSession(apps=[{"packageName": "app.myinventory", "appId": APP_ID}], config_status=403)
    with caplog.at_level(logging.WARNING, logger="app.firebase_android"):
        out = fa.resolve_once(lambda: s)
    assert out["apiKey"] == WEB_KEY
    assert "androidApps.getConfig: HTTP 403" in caplog.text and "web API key" in caplog.text


def test_android_api_key_env_wins_without_get_config(fa, monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "FIREBASE_ANDROID_API_KEY", "AIzaEnvKeyFakeFakeFakeFakeFakeFake0000")
    s = FakeSession(apps=[{"packageName": "app.myinventory", "appId": APP_ID}])
    assert fa.resolve_once(lambda: s)["apiKey"] == "AIzaEnvKeyFakeFakeFakeFakeFakeFake0000"
    assert not [c for c in s.calls if c[1].endswith("/config")]


def test_env_app_id_override_needs_no_api_call(fa, monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "FIREBASE_ANDROID_APP_ID", APP_ID)
    assert fa.android_push_config()["appId"] == APP_ID
    assert fa.start_background_resolution(lambda: pytest.fail("no API call with the override")) is False


def test_permission_error_is_logged_exactly_and_retried_without_crash(fa, caplog):
    err = {"code": 403, "message": "The caller does not have permission", "status": "PERMISSION_DENIED"}
    s = FakeSession(list_status=403, list_error=err)
    with caplog.at_level(logging.ERROR, logger="app.firebase_android"):
        assert fa.start_background_resolution(lambda: s, first_retry=0.01, retry=0.01) is True
        assert fa.start_background_resolution(lambda: s, first_retry=0.01, retry=0.01) is False
        deadline = time.monotonic() + 3
        while len([c for c in s.calls if c[0] == "GET"]) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        fa.stop_background_resolution()
    assert len(s.calls) >= 2
    assert "androidApps.list: HTTP 403" in caplog.text and "PERMISSION_DENIED" in caplog.text
    assert "The caller does not have permission" in caplog.text
    assert fa.android_push_config() is None


def test_background_thread_resolves_and_stops(fa):
    s = FakeSession(apps=[{"packageName": "app.myinventory", "appId": APP_ID}])
    assert fa.start_background_resolution(lambda: s, first_retry=0.01, retry=0.01)
    deadline = time.monotonic() + 3
    while fa.android_push_config() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert fa.android_push_config()["appId"] == APP_ID
    assert fa.start_background_resolution(lambda: pytest.fail("already resolved")) is False


def test_cache_file_is_read_after_restart(fa, tmp_path):
    fa.resolve_once(lambda: FakeSession(apps=[{"packageName": "app.myinventory", "appId": APP_ID}]))
    fa.reset_for_tests()
    assert fa.android_push_config()["appId"] == APP_ID
    assert fa.start_background_resolution(lambda: pytest.fail("cache hit, no API call")) is False


def test_cache_for_another_project_is_ignored(fa, tmp_path):
    (tmp_path / "firebase_android.json").write_text(json.dumps(
        {"appId": "1:999:android:abc", "apiKey": ANDROID_KEY, "projectId": "other", "senderId": "999"}))
    assert fa.android_push_config() is None
    (tmp_path / "firebase_android.json").write_text("not json")
    fa.reset_for_tests()
    assert fa.android_push_config() is None


def test_config_endpoint_does_not_wait_for_resolution(fa, client):
    gate = threading.Event()

    class SlowSession(FakeSession):
        def get(self, url, params=None, timeout=None):
            gate.wait(5)
            return super().get(url, params, timeout)

    s = SlowSession(apps=[{"packageName": "app.myinventory", "appId": APP_ID}])
    assert fa.start_background_resolution(lambda: s, first_retry=0.01, retry=0.01)
    started = time.monotonic()
    body = client.get("/api/push/config").json()
    assert time.monotonic() - started < 1
    assert body["enabled"] is True and body["android"] is None
    gate.set()
    deadline = time.monotonic() + 3
    while client.get("/api/push/config").json()["android"] is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert client.get("/api/push/config").json()["android"]["appId"] == APP_ID


def test_startup_skips_resolution_without_service_account(fa, monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "FIREBASE_PRIVATE_KEY", "")
    assert fa.start_background_resolution(lambda: pytest.fail("no credentials")) is False
