"""Signed amounts read «−۸۸۸» in RTL pages: the minus sits before the digits, never at the right end."""
from pathlib import Path
import re

from app.formatting import format_number, format_toman
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app/static/style.css").read_text(encoding="utf-8")


def _compact(s: str) -> str:
    return re.sub(r"\s+", "", s)


def test_negative_numbers_use_the_minus_sign():
    assert format_toman(-888) == "−۸۸۸" and format_number(-1234.5, 1) == "−۱٬۲۳۴٫۵"


def test_hero_net_is_a_left_to_right_island():
    rule = re.search(r"^\.total-num > \[data-amt\] \{([^{}]*)\}", CSS, re.M)
    assert rule and "unicode-bidi:isolate" in _compact(rule.group(1)) and "direction:ltr" in _compact(rule.group(1))
    box = re.search(r"^\.total-num \{([^{}]*)\}", CSS, re.M).group(1)
    assert "direction:rtl" in _compact(box)  # why the island is needed: the hero box itself is RTL


def test_other_signed_amounts_sit_in_ltr_bdi():
    templates = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "app/templates").rglob("*.html"))
    fields = re.findall(r'<bdi[^>]*data-salary-field="left"[^>]*>', templates)
    assert fields and all('dir="ltr"' in f for f in fields)


def test_hidden_page_html_has_no_net_amount(client, no_network):
    _register(client)
    client.post("/profile", data={"cash_toman": "1000", "csrf": _csrf(client)})
    from decimal import Decimal
    from app.db import SessionLocal
    from app.models import Debt, User
    db = SessionLocal()
    uid = db.query(User).filter(User.username == "alice").one().id
    db.add(Debt(user_id=uid, title="x", monthly_toman=Decimal("5000"), months_left=1, due_year=1405, due_month=12, due_day=1))
    db.commit(); db.close()
    from tests.amounts_helper import amounts_for
    assert amounts_for(client, "/dashboard")["net"] == "−۴٬۰۰۰"
    html = client.get("/dashboard").text
    hero = re.search(r'<span class="total-num"[^>]*>(.*?)</span><span class="total-suffix">', html, re.S)
    assert hero and hero.group(1) == '<span data-amt="net"></span>'
    assert not re.search(r"−[۰-۹]", html)
