"""One Tehran "today" for every page (prod container runs in UTC)."""
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import jdatetime
import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

TEHRAN = ZoneInfo("Asia/Tehran")


@pytest.fixture()
def freeze(monkeypatch):
    def _freeze(moment: datetime):
        import app.formatting as formatting

        monkeypatch.setattr(formatting, "_utcnow", lambda: moment.astimezone(timezone.utc))
    return _freeze


def _tehran(*args):
    return datetime(*args, tzinfo=TEHRAN)


def _month_line(client, query=""):
    html = client.get("/dashboard?tab=daily" + query).text
    # Spending v2 tiles: «امروز» + «این ماه», or a single «جمع {ماه}» for a past month (no «امروز» there).
    today = re.search(r'<span>امروز</span><b class="num">([^<]+)</b>', html)
    month = re.search(r'<span>(?:این ماه|جمع [^<]+)</span><b class="num">([^<]+)</b>', html)
    title = re.search(r"data-sp-title>([^<]+ [۰-۹]{4})</strong>", html).group(1)
    return title, today.group(1) if today else None, month.group(1)


def test_tehran_today_ignores_server_timezone(client, freeze):
    from app.formatting import tehran_today

    freeze(datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc))  # 00:30 Tehran on 18 Oct
    assert tehran_today() == jdatetime.date(1405, 7, 26)
    freeze(datetime(2026, 10, 17, 20, 29, tzinfo=timezone.utc))  # 23:59 Tehran on 17 Oct
    assert tehran_today() == jdatetime.date(1405, 7, 25)


def test_spend_logged_0030_tehran_on_the_1st_counts_in_new_month(client, freeze, no_network):
    _register(client)
    client.post("/profile", data={"btc": "1", "csrf": _csrf(client)})  # home v2: an all-empty user gets the welcome card
    freeze(_tehran(2026, 10, 23, 0, 30))  # 1405/08/01 00:30 Tehran = 2026-10-22 21:00 UTC
    assert client.post("/api/sms-spend", json={"amount_toman": "70000", "note": "sms"}).json()["ok"]
    from app.db import SessionLocal
    from app.models import DailySpend

    db = SessionLocal()
    assert [s.spent_on for s in db.query(DailySpend).all()] == [jdatetime.date(1405, 8, 1).togregorian()]
    db.close()
    title, today_total, month_total = _month_line(client)
    assert title == "آبان ۱۴۰۵" and today_total == "۷۰٬۰۰۰" and month_total == "۷۰٬۰۰۰"
    # The form's default date is the Tehran date too.
    html = client.get("/dashboard?tab=daily").text
    assert 'name="month" value="۸"' in html and 'name="day" value="۱"' in html
    tile = client.get("/dashboard").text
    tile = tile[tile.index('id="tile-month-spend"'):]
    assert "آبان ۱۴۰۵" in tile[:800] and "۷۰٬۰۰۰" in tile[:800]


def test_spend_logged_2330_on_last_day_stays_in_old_month(client, freeze, no_network):
    _register(client)
    freeze(_tehran(2026, 10, 22, 23, 30))  # 1405/07/30 23:30 Tehran (last day of Mehr)
    assert client.post("/api/sms-spend", json={"amount_toman": "50000", "note": "sms"}).json()["ok"]
    title, today_total, month_total = _month_line(client)
    assert title == "مهر ۱۴۰۵" and today_total == "۵۰٬۰۰۰" and month_total == "۵۰٬۰۰۰"
    freeze(_tehran(2026, 10, 23, 0, 30))  # next morning, new month: nothing yet
    assert _month_line(client)[1:] == ("۰", "۰")
    assert _month_line(client, "&jy=1405&jm=7")[2] == "۵۰٬۰۰۰"


def test_past_month_totals_unchanged(client, freeze, no_network):
    from app.daily_spend import categories_for_user, ensure_spend_categories
    from app.db import SessionLocal
    from app.models import DailySpend, User

    _register(client)
    db = SessionLocal()
    user = db.query(User).filter(User.username == "alice").one()
    ensure_spend_categories(db, user)
    _parents, children = categories_for_user(db, user)
    for jd, amount in (((1405, 6, 1), 1000), ((1405, 6, 31), 2000), ((1405, 7, 1), 4000)):
        db.add(DailySpend(user_id=user.id, category_id=children[0].id, amount_toman=Decimal(amount),
                          spent_on=jdatetime.date(*jd).togregorian(), note=""))
    db.commit()
    db.close()
    totals = []
    for moment in (datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc), datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc),
                   datetime(2026, 10, 22, 21, 0, tzinfo=timezone.utc)):
        freeze(moment)
        totals.append((_month_line(client, "&jy=1405&jm=6")[2], _month_line(client, "&jy=1405&jm=7")[2]))
    assert totals == [("۳٬۰۰۰", "۴٬۰۰۰")] * 3


def test_instalment_due_today_in_the_0000_0330_window(client, freeze, no_network):
    _register(client)
    client.post("/profile/debts", data={"title": "وام", "monthly_toman": "250000", "months_left": "6",
                                        "due_year": "1405", "due_month": "7", "due_day": "26",
                                        "csrf": _csrf(client, "/profile?tab=debts")})
    freeze(datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc))  # 00:30 Tehran, 1405/07/26 (UTC date is still the 25th)
    html = client.get("/dashboard").text
    tile = html[html.index('id="tile-next-debt"'):html.index('id="tile-month-spend"')]
    assert re.search(r'badge-due[^"]*">امروز<', tile) and "۲۶ مهر" in tile
    debts = client.get("/profile?tab=debts").text
    assert "قسط بعدی: <b>۲۶ مهر</b>" in debts and "امروز" in debts  # same date on the debts page
    freeze(datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc))  # 23:30 Tehran on the 25th
    tile = client.get("/dashboard").text
    tile = tile[tile.index('id="tile-next-debt"'):tile.index('id="tile-month-spend"')]
    assert re.search(r'badge-due[^"]*">فردا<', tile)
