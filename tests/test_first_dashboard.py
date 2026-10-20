"""First save after sign-up must not wait on chande.net before redirecting to the dashboard."""
import httpx
import pytest
from starlette.background import BackgroundTasks

from tests.test_holdings import _csrf, _register


@pytest.fixture()
def no_http(monkeypatch):
    async def _boom(self, *a, **k):
        raise AssertionError("network call during the request")

    monkeypatch.setattr(httpx.AsyncClient, "send", _boom)


def test_save_schedules_price_fetch_after_response(client, monkeypatch, no_http):
    import app.profile as profile

    order = []

    async def _fake(user_id):
        order.append(("fetch", user_id))

    monkeypatch.setattr(profile, "refresh_prices_and_snapshot_user", _fake)
    real_add = BackgroundTasks.add_task

    def _add(self, func, *a, **k):
        order.append(("scheduled", func))
        return real_add(self, func, *a, **k)

    monkeypatch.setattr(BackgroundTasks, "add_task", _add)
    _register(client, "fastsave")
    r = client.post("/profile", data={"csrf": _csrf(client, "/assets"), "gold_grams": "2"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    # Scheduled as a background task (runs after the response), never awaited inside the handler.
    assert order[0] == ("scheduled", _fake)
    assert order[1][0] == "fetch"


def test_first_dashboard_renders_without_network(client, monkeypatch, no_http):
    import app.profile as profile

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(profile, "refresh_prices_and_snapshot_user", _noop)
    _register(client, "fastdash")
    client.post("/profile", data={"csrf": _csrf(client, "/assets"), "gold_grams": "2"})
    r = client.get("/dashboard")  # no stored prices at all: still renders (waiting/stale UI), no HTTP
    assert r.status_code == 200
