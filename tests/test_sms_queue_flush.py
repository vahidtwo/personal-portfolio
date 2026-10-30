"""12.0.1: SMS spends queued on the phone while logged out are flushed after login with the same idempotency_key."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.models import DailySpend
from app.spends import sms_spent_on
from tests.test_ownership_and_data import _logout, _register


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_flush_retry_is_deduped_by_idempotency_key(client: TestClient):
    _register(client, "queueuser")
    body = {"amount_toman": "250000", "note": "خرید ****1234", "idempotency_key": "q" * 64,
            "sms_at": _ms(datetime.now(timezone.utc))}
    first = client.post("/api/sms-spend", json=body).json()
    # The app retries the whole queue after a lost response: same key -> same row, no second spend.
    again = client.post("/api/sms-spend", json=body).json()
    assert first["ok"] and again["ok"] and again["duplicate"] is True and again["id"] == first["id"]
    from app.db import SessionLocal

    with SessionLocal() as db:
        assert db.query(DailySpend).filter(DailySpend.note.like(f"[{'q' * 64}]%")).count() == 1


def test_logged_out_post_is_401_so_the_app_keeps_the_queue(client: TestClient):
    _register(client, "queueout")
    _logout(client)
    r = client.post("/api/sms-spend", json={"amount_toman": "1000", "idempotency_key": "k1"})
    assert r.status_code == 401 and r.json()["error"] == "login"


def test_queued_spend_keeps_the_sms_date(client: TestClient):
    _register(client, "queuedate")
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    r = client.post("/api/sms-spend", json={"amount_toman": "7000", "note": "x", "idempotency_key": "d1",
                                             "sms_at": _ms(two_days_ago)}).json()
    from app.db import SessionLocal

    with SessionLocal() as db:
        row = db.get(DailySpend, r["id"])
        today = datetime.now(timezone.utc).date()
        assert (today - row.spent_on).days in (1, 2, 3)


def test_sms_spent_on_bounds():
    today = date(2026, 10, 30)
    noon = lambda d: _ms(datetime(d.year, d.month, d.day, 9, 0, tzinfo=timezone.utc))  # 12:30 Tehran
    assert sms_spent_on(None, today) == today
    assert sms_spent_on("junk", today) == today
    assert sms_spent_on(noon(date(2026, 10, 28)), today) == date(2026, 10, 28)
    assert sms_spent_on(noon(date(2026, 11, 2)), today) == today  # future
    assert sms_spent_on(noon(date(2026, 9, 1)), today) == today  # older than 30 days


def test_android_queue_is_private_and_flushed_after_login():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "android/app/src/main/java/app/myinventory"
    q = (src / "SmsQueue.kt").read_text(encoding="utf-8")
    assert "AndroidKeyStore" in q and "AES/GCM/NoPadding" in q and "context.filesDir" in q
    assert '.put("sms_at", e.at)' in q
    r = (src / "SmsReceiver.kt").read_text(encoding="utf-8")
    assert "بعد از ورود ذخیره می‌شود" in r and "HomeActivity::class.java" in r
    home = (src / "HomeActivity.kt").read_text(encoding="utf-8")
    assert home.count("SmsReceiver.flushQueued(this)") >= 2
    assert "SmsReceiver.flushQueued(this)" in (src / "MainActivity.kt").read_text(encoding="utf-8")
