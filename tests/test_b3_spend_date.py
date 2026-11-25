"""Spend form date follows the viewed month: today, last day, or no future add."""
from app.models import DailySpend

from tests.amounts_helper import with_amounts
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401
from tests.test_spending_v2 import DAILY, _add, _form, _user_cats, mehr28  # noqa: F401


def _input_value(html, name):
    marker = f'id="sp-{name}" name="{name}" value="'
    start = html.index(marker) + len(marker)
    return html[start:html.index('"', start)]


def test_current_month_preselects_today(client, no_network, mehr28):
    _register(client)
    html = with_amounts(client, DAILY)
    assert 'data-sp-month-kind="current"' in html
    assert _input_value(html, "year") == "۱۴۰۵"
    assert _input_value(html, "month") == "۷"
    assert _input_value(html, "day") == "۲۸"
    assert 'aria-pressed="true" data-sp-day="today"' in html
    assert 'aria-pressed="true" data-sp-day="other"' not in html
    assert "خرج آینده ثبت نمی‌شود" not in html


def test_past_month_preselects_other_and_last_day(client, no_network, mehr28):
    _register(client)
    db, user, _, children = _user_cats()
    _add(db, user, children[0], 1000, 28)
    db.commit()
    db.close()
    html = with_amounts(client, DAILY + "&jy=1405&jm=6")
    assert 'data-sp-month-kind="past"' in html
    assert 'data-sp-last-day="1405-6-31"' in html
    assert _input_value(html, "year") == "۱۴۰۵"
    assert _input_value(html, "month") == "۶"
    assert _input_value(html, "day") == "۳۱"
    assert 'aria-pressed="true" aria-expanded="true"' in html and 'data-sp-day="other"' in html
    assert 'sp-custom open' in html
    assert "ثبت خرج در شهریور" in html and "data-sp-open-form" in html
    assert "خرج آینده ثبت نمی‌شود" not in html


def test_future_month_disables_add(client, no_network, mehr28):
    _register(client)
    db, user, _, children = _user_cats()
    _add(db, user, children[0], 1000, 28)
    db.commit()
    db.close()
    html = with_amounts(client, DAILY + "&jy=1405&jm=8")
    assert 'data-sp-month-kind="future"' in html
    assert "خرج آینده ثبت نمی‌شود" in html
    assert "در آبان خرجی ثبت نشده است" in html
    assert "data-sp-open-form" not in html
    assert "disabled" in html
    opened = with_amounts(client, DAILY + "&jy=1405&jm=8&add=1")
    page = opened[opened.index("data-sp-page"): opened.index("</footer>") if "</footer>" in opened else None]
    assert "data-sp-open" not in page.split(">", 1)[0]


def test_future_date_is_rejected(client, no_network, mehr28):
    _register(client)
    db, user, _, children = _user_cats()
    cat = children[0]
    db.close()
    data = {**_form(cat), "month": "۸", "day": "۱", "csrf": _csrf(client, DAILY)}
    html = client.post("/profile/spends", data=data).text
    assert "خرج آینده ثبت نمی‌شود" in html
    db, user, _, _ = _user_cats()
    assert db.query(DailySpend).filter_by(user_id=user.id).count() == 0
    db.close()


def test_today_still_saves(client, no_network, mehr28):
    _register(client)
    db, user, _, children = _user_cats()
    cat = children[0]
    db.close()
    ok = client.post("/profile/spends", data={**_form(cat), "csrf": _csrf(client, DAILY)})
    assert ok.status_code in (200, 303, 302)
    db, user, _, _ = _user_cats()
    assert db.query(DailySpend).filter_by(user_id=user.id).count() == 1
    db.close()
