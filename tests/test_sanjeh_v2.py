"""Car (Sanjeh) card v2: /assets/car/connect|refresh|disconnect|undo. Sanjeh is always faked."""
from datetime import timedelta
from decimal import Decimal

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

JSON = {"Accept": "application/json"}


@pytest.fixture()
def fake_sanjeh(monkeypatch):
    import app.car_routes as cr
    import app.jobs as jobs
    from app.sanjeh import SanjehAuthError, SanjehError, SanjehPortfolio

    calls = []

    async def fake(token):
        calls.append(token)
        if token.startswith("BAD"):
            raise SanjehAuthError("rejected")
        if token.startswith("DOWN") or fake.down:
            raise SanjehError("down")
        return SanjehPortfolio(total_toman=Decimal("2850000000"), car_count=2)

    fake.down = False
    fake.calls = calls
    monkeypatch.setattr(cr, "fetch_sanjeh_portfolio", fake)
    monkeypatch.setattr(jobs, "fetch_sanjeh_portfolio", fake)
    cr._next_refresh_at.clear(); cr._retry_after_failure.clear()
    cr._pending_undo.clear()
    return fake


def _user():
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    return db, db.query(User).filter_by(username="alice").one()


def _connect(client, token="FAKE-OK", **kw):
    return client.post("/assets/car/connect", data={"token": token, "csrf": _csrf(client, "/assets")}, **kw)


def test_get_assets_never_calls_sanjeh_and_shows_empty_state(client, no_network, fake_sanjeh):
    _register(client)
    html = client.get("/assets").text
    assert 'data-car-state="none"' in html and "اتصال به سنجه" in html and "ارزش خودرو را از سنجه بگیرید" in html
    db, u = _user(); u.sanjeh_token = "FAKE"; u.car_fetched_at = None; db.commit(); db.close()
    client.get("/assets")
    assert fake_sanjeh.calls == []


def test_connect_validates_before_saving_and_rejected_keeps_old_token(client, no_network, fake_sanjeh):
    _register(client)
    r = _connect(client, headers=JSON)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["state"] == "connected"
    db, u = _user()
    assert (u.sanjeh_token, u.sanjeh_status, u.car_count, u.car_toman) == ("FAKE-OK", "ok", 2, Decimal("2850000000"))
    db.close()
    r = _connect(client, "BAD-1", headers=JSON)
    assert r.status_code == 422 and r.json()["error"] == "rejected"
    assert r.json()["message"] == "سنجه این توکن را نپذیرفت. دوباره از سنجه کپی کنید."
    r = _connect(client, "DOWN-1", headers=JSON)
    assert r.status_code == 502 and r.json()["error"] == "failed"
    r = _connect(client, "  ", headers=JSON)
    assert r.status_code == 422 and r.json()["error"] == "empty"
    db, u = _user()
    assert u.sanjeh_token == "FAKE-OK" and u.sanjeh_status == "ok"
    db.close()
    html = client.get("/assets").text
    assert "FAKE-OK" not in html  # the token is never rendered


def test_connect_no_js_fallback_redirects(client, no_network, fake_sanjeh):
    _register(client)
    r = _connect(client, "BAD-1", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/assets?car=connect&err=rejected")
    page = client.get("/assets?car=connect&err=rejected").text
    assert 'aria-invalid="true"' in page and "سنجه این توکن را نپذیرفت" in page
    r = _connect(client, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/assets#group-car"


def test_csrf_required_on_every_car_route(client, no_network, fake_sanjeh):
    _register(client)
    for path in ("connect", "refresh", "disconnect", "undo"):
        assert client.post(f"/assets/car/{path}", data={"token": "FAKE"}).status_code == 400, path
    assert fake_sanjeh.calls == []


def test_refresh_states_and_cooldown(client, no_network, fake_sanjeh):
    import app.car_routes as cr

    _register(client)
    _connect(client, headers=JSON)
    csrf = _csrf(client, "/assets")
    r = client.post("/assets/car/refresh", data={"csrf": csrf}, headers=JSON)
    assert r.status_code == 429 and r.json()["error"] == "too_soon"
    cr._next_refresh_at.clear(); cr._retry_after_failure.clear()
    fake_sanjeh.down = True
    r = client.post("/assets/car/refresh", data={"csrf": csrf}, headers=JSON)
    assert r.json()["state"] == "fetchfail" and "سنجه فعلاً پاسخ نمی‌دهد" in r.json()["html"]
    db, u = _user()
    assert u.sanjeh_status == "failed" and u.car_toman == Decimal("2850000000")  # old value still counted
    u.sanjeh_token = "BAD-NOW"; db.commit(); db.close()
    fake_sanjeh.down = False
    cr._next_refresh_at.clear(); cr._retry_after_failure.clear()
    r = client.post("/assets/car/refresh", data={"csrf": csrf}, headers=JSON)
    assert r.json()["state"] == "rejected" and "گذاشتن توکن تازه" in r.json()["html"]
    html = client.get("/assets").text
    assert 'data-car-state="rejected"' in html and "سنجه دیگر این توکن را نمی‌پذیرد" in html
    db, u = _user()
    assert u.car_toman == Decimal("2850000000") and u.sanjeh_token == "BAD-NOW"
    db.close()
    # rejected → a new good token fixes it
    r = _connect(client, "FAKE-NEW", headers=JSON)
    assert r.json()["state"] == "connected"


def test_disconnect_clears_and_undo_restores_within_window(client, no_network, fake_sanjeh):
    import app.car_routes as cr

    _register(client)
    _connect(client, headers=JSON)
    csrf = _csrf(client, "/assets")
    r = client.post("/assets/car/disconnect", data={"csrf": csrf}, headers=JSON)
    assert r.json()["state"] == "none" and r.json()["message"] == "اتصال سنجه قطع شد."
    db, u = _user()
    assert (u.sanjeh_token, u.car_toman, u.car_count, u.car_fetched_at, u.sanjeh_status) == (None, 0, 0, None, None)
    db.close()
    page = client.get("/assets").text
    assert "برگرداندن" in page and 'data-car-toast hidden' not in page
    r = client.post("/assets/car/undo", data={"csrf": csrf}, headers=JSON)
    assert r.json()["ok"] and r.json()["state"] == "connected"
    db, u = _user()
    assert u.sanjeh_token == "FAKE-OK" and u.car_count == 2 and u.car_fetched_at is not None
    db.close()
    # expired undo does nothing
    client.post("/assets/car/disconnect", data={"csrf": csrf}, headers=JSON)
    uid, (_, snap) = next(iter(cr._pending_undo.items()))
    cr._pending_undo[uid] = (0.0, snap)
    r = client.post("/assets/car/undo", data={"csrf": csrf}, headers=JSON)
    assert r.status_code == 410
    db, u = _user()
    assert u.sanjeh_token is None
    db.close()


def test_job_refresh_sets_status_and_never_drops_value(client, no_network, fake_sanjeh):
    import asyncio

    from app.jobs import refresh_all_sanjeh_cars

    _register(client)
    _connect(client, headers=JSON)
    db, u = _user(); u.sanjeh_token = "BAD-X"; db.commit(); db.close()
    asyncio.run(refresh_all_sanjeh_cars())
    db, u = _user()
    assert u.sanjeh_status == "rejected" and u.car_toman == Decimal("2850000000")
    db.close()


def test_dashboard_does_not_retry_rejected_token(client, no_network, fake_sanjeh):
    from app.models import utcnow

    _register(client)
    _connect(client, headers=JSON)
    db, u = _user()
    u.sanjeh_token = "BAD-X"; u.sanjeh_status = "rejected"; u.car_fetched_at = utcnow() - timedelta(days=9)
    db.commit(); db.close()
    fake_sanjeh.calls.clear()
    client.get("/dashboard")
    assert fake_sanjeh.calls == []


def test_card_markup_contract(client, no_network, fake_sanjeh):
    _register(client)
    _connect(client, headers=JSON)
    html = client.get("/assets").text
    card = html.split("data-car-card")[1].split("</section>")[0]
    assert "<input" not in card  # nothing of the car ends up in the holdings form
    assert 'aria-label="گزینه‌های سنجه"' in card and "تعویض توکن" in card and "قطع اتصال" in card
    assert "متصل" in card and "به‌روز شده" in card and "۲٬۸۵۰٬۰۰۰٬۰۰۰" in card and "۲ خودرو" in card
    assert 'id="car-sheet"' in html and 'id="car-confirm"' in html and "/static/car-card.js" in html
    assert 'action="/assets/car/disconnect"' in html.split("</form>", 1)[1]  # outside the holdings form


def test_failed_refresh_uses_short_cooldown_and_success_starts_five_minutes(client, no_network, fake_sanjeh):
    """Review fix: «دوباره امتحان کنید» must not be blocked for 5 minutes after a failure."""
    import time

    import app.car_routes as cr

    _register(client)
    _connect(client, headers=JSON)
    cr._next_refresh_at.clear(); cr._retry_after_failure.clear()
    csrf = _csrf(client, "/assets")
    fake_sanjeh.down = True
    r = client.post("/assets/car/refresh", data={"csrf": csrf}, headers=JSON)
    assert r.json()["state"] == "fetchfail"
    (uid, until), = cr._next_refresh_at.items()
    assert until - time.monotonic() <= cr.RETRY_COOLDOWN_S <= 60  # short, not 5 minutes
    # right away: still guarded (no hammering), with the same «too soon» answer
    r = client.post("/assets/car/refresh", data={"csrf": csrf}, headers=JSON)
    assert r.status_code == 429 and r.json()["message"] == "چند لحظه صبر کنید و دوباره امتحان کنید."
    # after the short cooldown Sanjeh is back: the retry goes through and fixes the state
    cr._next_refresh_at[uid] = time.monotonic() - 1
    fake_sanjeh.down = False
    r = client.post("/assets/car/refresh", data={"csrf": csrf}, headers=JSON)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["state"] == "connected"
    # success starts the full 5-minute cooldown
    assert cr._next_refresh_at[uid] - time.monotonic() > cr.RETRY_COOLDOWN_S
    r = client.post("/assets/car/refresh", data={"csrf": csrf}, headers=JSON)
    assert r.status_code == 429 and r.json()["message"] == cr.ERR_TOO_SOON


def test_unknown_fetch_time_reads_nashkhas(client, no_network, fake_sanjeh):
    _register(client)
    db, u = _user(); u.sanjeh_token = "FAKE"; u.sanjeh_status = "failed"; u.car_fetched_at = None; db.commit(); db.close()
    assert "آخرین قیمت: نامشخص" in client.get("/assets").text
