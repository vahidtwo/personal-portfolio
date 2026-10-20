"""Spending v2 (mockups/app-v2/spending): per-field errors, parent fallback, month tiles, day groups, bars."""
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import jdatetime
import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

DAILY = "/dashboard?tab=daily"
TEHRAN_NOON_28_MEHR = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)  # 1405/07/28 12:00 Tehran


@pytest.fixture()
def mehr28(monkeypatch):
    import app.formatting as formatting

    monkeypatch.setattr(formatting, "_utcnow", lambda: TEHRAN_NOON_28_MEHR)


def _user_cats(username="alice"):
    from app.daily_spend import categories_for_user, ensure_spend_categories
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    user = db.query(User).filter_by(username=username).one()
    ensure_spend_categories(db, user)
    parents, children = categories_for_user(db, user)
    return db, user, parents, children


def _add(db, user, cat, amount, day, month=7, note=""):
    from app.models import DailySpend

    db.add(DailySpend(user_id=user.id, category_id=cat.id, amount_toman=Decimal(amount),
                      spent_on=jdatetime.date(1405, month, day).togregorian(), note=note))


def _form(cat):
    return {"amount_toman": "۱۲۰٬۰۰۰", "year": "۱۴۰۵", "month": "۷", "day": "۲۸",
            "parent_id": str(cat.parent_id), "category_id": str(cat.id), "note": "", "jy": "1405", "jm": "7"}


# ---------- validation ----------
@pytest.mark.parametrize("amount,year,month,day,want", [
    ("۱۲۰٬۰۰۰", "۱۴۰۵", "۷", "۲۸", {}),
    ("120,000", "1405", "7", "28", {}),
    ("۱۲۰٫۰۰۰٫۵", "۱۴۰۵", "۱۳", "۲۸", {"amount_toman": "مبلغ را بدون ممیز بنویسید؛ مثلاً ۱۲۰٬۰۰۰", "month": "ماه بین ۱ تا ۱۲ است"}),
    ("۱۲۰٫۵", "۱۴۰۵", "۷", "۲۸", {"amount_toman": "مبلغ را بدون ممیز بنویسید؛ مثلاً ۱۲۰٬۰۰۰"}),
    ("۰", "۱۴۰۵", "۷", "۲۸", {"amount_toman": "مبلغ باید بیشتر از صفر باشد"}),
    ("", "۱۴۰۵", "۷", "۲۸", {"amount_toman": "مبلغ باید بیشتر از صفر باشد"}),
    ("-۵", "۱۴۰۵", "۷", "۲۸", {"amount_toman": "مبلغ باید بیشتر از صفر باشد"}),
    ("abc", "۱۴۰۵", "۷", "۲۸", {"amount_toman": "مبلغ را بدون ممیز بنویسید؛ مثلاً ۱۲۰٬۰۰۰"}),
    ("۵۰۰", "۱۴۰۵", "۷", "۳۱", {"day": "این ماه ۳۰ روز دارد"}),
    ("۵۰۰", "۱۴۰۴", "۱۲", "۳۰", {"day": "این ماه ۲۹ روز دارد"}),
    ("۵۰۰", "۱۴۰۳", "۱۲", "۳۰", {}),  # 1403 is a leap year
    ("۵۰۰", "۰۵", "۷", "۲۸", {"year": "سال را چهاررقمی بنویسید"}),
])
def test_validate_spend_reports_every_field(amount, year, month, day, want):
    from app.spend_validation import validate_spend

    errors, value, spent = validate_spend(amount, year, month, day)
    assert errors == want
    if not want:
        assert value > 0 and spent is not None


def test_js_validation_matches_server():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    from app.spend_validation import validate_spend

    cases = [("۱۲۰٫۰۰۰٫۵", "۱۴۰۵", "۱۳", "۲۸"), ("۱۲۰٬۰۰۰", "۱۴۰۵", "۷", "۲۸"), ("۰", "۱۴۰۵", "۷", "۳۱"),
             ("-۵", "1404", "12", "30"), ("۵۰۰", "۱۴۰۳", "۱۲", "۳۰"), ("1.5", "99", "0", "40"), ("", "۱۴۰۵", "۱", "۳۱"),
             ("۱٬۲۰۰", "۱۴۰۵", "۶", "۳۱"), ("x", "", "", "")]
    static = Path(__file__).resolve().parents[1] / "app" / "static"
    script = (f"const v=require({str(static / 'spending-page.js')!r});"
              f"const cases={json.dumps(cases, ensure_ascii=False)};"
              "console.log(JSON.stringify(cases.map(c=>v.validate({amount:c[0],year:c[1],month:c[2],day:c[3]}))));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=20, cwd=static)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [validate_spend(*c)[0] for c in cases]


def test_form_post_shows_all_errors_at_their_fields(client, no_network, mehr28):
    from app.models import DailySpend

    _register(client)
    db, user, _, children = _user_cats()
    cat = children[0]
    db.close()
    data = {**_form(cat), "amount_toman": "۱۲۰٫۰۰۰٫۵", "month": "۱۳", "csrf": _csrf(client, DAILY)}
    html = client.post("/profile/spends", data=data).text
    assert "۲ مورد نیاز به اصلاح دارد" in html
    assert '<span class="sp-err" id="err-amount_toman" data-sp-err>مبلغ را بدون ممیز بنویسید؛ مثلاً ۱۲۰٬۰۰۰</span>' in html
    assert '<span class="sp-err" id="err-month" data-sp-err>ماه بین ۱ تا ۱۲ است</span>' in html
    assert 'id="sp-month" name="month" value="۱۳"' in html  # typed values kept
    assert html.count('aria-invalid="true"') == 2 and "data-sp-open" in html
    db, user, _, _ = _user_cats()
    assert db.query(DailySpend).filter_by(user_id=user.id).count() == 0
    db.close()


def test_json_save_422_fields_and_ok_redirect(client, no_network, mehr28):
    _register(client)
    db, user, _, children = _user_cats()
    cat = children[0]
    db.close()
    bad = client.post("/profile/spends", data={**_form(cat), "amount_toman": "۱٫۵", "day": "۴۰", "csrf": _csrf(client, DAILY)},
                      headers={"Accept": "application/json"})
    assert bad.status_code == 422
    body = bad.json()
    assert body["ok"] is False and list(body["fields"]) == ["amount_toman", "day"]
    assert body["error"] == body["fields"]["amount_toman"]  # old single-message field still there
    ok = client.post("/profile/spends", data={**_form(cat), "csrf": _csrf(client, DAILY)}, headers={"Accept": "application/json"})
    assert ok.status_code == 200 and ok.json() == {"ok": True, "redirect": "/dashboard?tab=daily&jy=1405&jm=7"}
    plain = client.post("/profile/spends", data={**_form(cat), "csrf": _csrf(client, DAILY)}, follow_redirects=False)
    assert plain.status_code == 303  # no-JS path unchanged


# ---------- list ----------
def test_parent_category_spend_shows_parent_name(client, no_network, mehr28):
    _register(client)
    db, user, parents, _ = _user_cats()
    name = parents[0].name
    _add(db, user, parents[0], 45000, 28, note="ناهار")
    db.commit()
    db.close()
    html = client.get(DAILY).text
    rows = html.split("data-sp-days")[1].split("</section>\n    \n  </div>")[0]
    assert f"<b>{name}</b>" in rows and "—" not in rows


def test_day_groups_totals_cover_the_whole_month(client, no_network, mehr28):
    _register(client)
    db, user, _, children = _user_cats()
    for i in range(20):  # 20 spends on one day: page 1 shows 15 of them, the day total counts all 20
        _add(db, user, children[0], 1000, 28)
    _add(db, user, children[1], 5000, 27)
    db.commit()
    db.close()
    html = client.get(DAILY).text
    assert "<b>امروز، ۲۸ مهر</b><span><span class=\"num\">۲۰٬۰۰۰</span> تومان</span>" in html
    assert "۱۵ از ۲۱ خرج در مهر" in html and "نمایش ۶ خرج بیشتر" in html
    more = client.get(DAILY + "&jy=1405&jm=7&page=2").text  # «نمایش بیشتر» grows the list
    assert "۲۱ از ۲۱ خرج در مهر" in more and "<b>دیروز، ۲۷ مهر</b>" in more and "data-sp-more" not in more


def test_bars_sorted_top_four_with_share_and_more(client, no_network, mehr28):
    _register(client)
    db, user, parents, children = _user_cats()
    by_parent = {}
    for c in children:
        by_parent.setdefault(c.parent_id, c)
    cats = list(by_parent.values())[:6]
    for i, c in enumerate(cats):
        _add(db, user, c, (i + 1) * 10000, 20)  # 10k..60k, total 210k
    db.commit()
    db.close()
    html = client.get(DAILY).text
    bars = re.findall(r'<span class="v"><b>([^<]+)</b> تومان، ([^<]+)</span>', html)
    assert [b[0] for b in bars] == ["۶۰٬۰۰۰", "۵۰٬۰۰۰", "۴۰٬۰۰۰", "۳۰٬۰۰۰", "۲۰٬۰۰۰", "۱۰٬۰۰۰"]
    assert bars[0][1] == "۲۹٪"
    assert html.count("data-sp-rest>") == 2 and html.count("<li hidden data-sp-rest>") == 2
    assert "۲ دستهٔ دیگر" in html


def test_past_month_drops_today_tile(client, no_network, mehr28):
    _register(client)
    db, user, _, children = _user_cats()
    _add(db, user, children[0], 9000, 3, month=6)
    _add(db, user, children[0], 1000, 28)
    db.commit()
    db.close()
    past = client.get(DAILY + "&jy=1405&jm=6").text
    assert "<span>امروز</span>" not in past and '<span>جمع شهریور</span><b class="num">۹٬۰۰۰</b>' in past
    now = client.get(DAILY).text
    assert '<span>امروز</span><b class="num">۱٬۰۰۰</b>' in now and "<span>این ماه</span>" in now


def test_empty_states(client, no_network, mehr28):
    _register(client)
    first = client.get(DAILY).text
    assert "اولین خرجتان را ثبت کنید" in first and "ثبت اولین خرج" in first
    assert "sp-tile" not in first and "data-sp-addbar" not in first
    db, user, _, children = _user_cats()
    _add(db, user, children[0], 1000, 28)
    db.commit()
    db.close()
    month = client.get(DAILY + "&jy=1405&jm=6").text
    assert "در شهریور خرجی ثبت نشده است" in month and "ثبت خرج در شهریور" in month
    assert '<span>جمع شهریور</span><b class="num">۰</b>' in month and "data-sp-addbar" in month


def test_page_contract(client, no_network, mehr28):
    _register(client)
    db, user, _, children = _user_cats()
    _add(db, user, children[0], 45000, 28, note="ناهار با همکارها")
    db.commit()
    db.close()
    full = client.get(DAILY).text
    assert "chart.umd" not in full  # the doughnut is gone from this tab
    html = full[full.index("data-sp-page"):full.index("</footer>") if "</footer>" in full else None]
    assert "confirm(" not in html and " · " not in html.split("<footer")[0]
    assert re.search(r'aria-label="گزینه‌های خرج ۴۵٬۰۰۰ تومان، [^"]+"', html)
    assert 'role="menu"' in html and "حذف…" in html and 'id="sp-del-form"' in html
    assert 'id="daily-spend-form"' in html and 'name="parent_id" id="spend-parent"' in html  # same POST fields
    assert "<h1 id=\"sp-h\">خرج‌ها</h1>" in html and "فهرست خرج‌ها" in html
    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "spending-page.js").read_text(encoding="utf-8")
    for needle in ("alertdialog", "در حال ثبت…", "دوباره ثبت کن", "ثبت نشد", "فهرست خرج‌ها باز نشد",
                   "در حال بارگذاری خرج‌های ماه", "aria-pressed", "1000"):
        assert needle in js
    assert "confirm(" not in js


def _contrast(hex_bg):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    return 1.05 / (lum(hex_bg) + 0.05)


def test_category_colours_reach_aa_with_white_and_bills_differs_from_sms():
    from app.daily_spend import PARENT_COLORS

    assert all(_contrast(c) >= 4.5 for c in PARENT_COLORS.values()), {k: round(_contrast(c), 2) for k, c in PARENT_COLORS.items()}
    assert PARENT_COLORS["bills"] != PARENT_COLORS["sms"]
