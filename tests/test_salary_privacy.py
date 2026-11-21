"""Privacy mode for «حقوق ماهانه»: the amount never reaches HTML; it is fetched on demand."""
from decimal import Decimal
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

SALARY_RAW = "73519846"
SALARY_FA = "۷۳٬۵۱۹٬۸۴۶"  # as format_toman prints it
LEFT_FA = "۷۱٬۰۱۹٬۸۴۶"  # 73,519,846 − 2,500,000 expense
PAGES = ["/dashboard", "/dashboard?tab=daily", "/profile", "/profile?tab=debts",
         "/profile?section=settings", "/assets"]
STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def _salary(username="alice"):
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        return Decimal(db.query(User).filter_by(username=username).one().salary_toman)
    finally:
        db.close()


def _save_account(client, salary, username="alice"):
    return client.post("/profile/account", data={"full_name": "", "username": username, "mobile": "",
                                                 "salary_toman": salary, "current_password": "",
                                                 "new_password": "", "section": "salary", "csrf": _csrf(client)},
                       follow_redirects=False)


def _setup(client):
    _register(client)
    assert _save_account(client, SALARY_RAW).status_code == 303
    client.post("/profile/expenses", data={"title": "اجاره", "amount_toman": "2500000", "due_day": "5",
                                           "csrf": _csrf(client)})
    assert _salary() == Decimal(SALARY_RAW)


def test_no_salary_page_html_contains_the_amount(client, no_network):
    _setup(client)
    client.post("/profile", data={"btc": "1", "csrf": _csrf(client)})  # home v2: an all-empty user gets the welcome card
    for path in PAGES:
        html = client.get(path).text
        for needle in (SALARY_RAW, SALARY_FA, LEFT_FA, "73,519,846", "71019846", "۷۳۵۱۹۸۴۶"):
            assert needle not in html, (path, needle)
    debts = client.get("/profile?tab=debts").text
    assert 'data-salary-field="salary"' in debts and 'data-salary-field="left"' in debts
    assert "••••••" in debts and 'aria-label="نمایش مبلغ"' in debts
    assert 'data-salary-field="left"' in client.get("/dashboard").text


def test_edit_form_input_starts_empty(client, no_network):
    _setup(client)
    html = client.get("/profile?section=settings").text
    assert '<input id="f-salary_toman" name="salary_toman" value="" autocomplete="off" inputmode="decimal" dir="ltr" data-thousands' in html


def test_endpoint_requires_auth(client, no_network):
    r = client.get("/api/salary", follow_redirects=False)
    assert r.status_code == 401
    assert "no-store" in r.headers["cache-control"]


def test_endpoint_returns_owner_value_with_no_store(client, no_network):
    _setup(client)
    r = client.get("/api/salary")
    assert r.status_code == 200
    assert r.json() == {"salary": SALARY_FA, "left": LEFT_FA}
    cc = r.headers["cache-control"]
    assert "no-store" in cc and "private" in cc


def test_endpoint_is_same_user_only(client, no_network):
    _setup(client)
    client.post("/logout", data={"csrf": _csrf(client, "/profile")})
    _register(client, "bob")
    r = client.get("/api/salary")
    assert r.status_code == 200
    assert SALARY_FA not in r.text and r.json()["salary"] != SALARY_FA


def test_empty_edit_keeps_old_salary(client, no_network):
    _setup(client)
    assert _save_account(client, "").status_code == 303
    assert _salary() == Decimal(SALARY_RAW)
    assert _save_account(client, "   ").status_code == 303
    assert _salary() == Decimal(SALARY_RAW)


def test_new_value_saves_and_zero_still_allowed(client, no_network):
    _setup(client)
    assert _save_account(client, "۵۰٬۰۰۰٬۰۰۰").status_code == 303
    assert _salary() == Decimal("50000000")
    assert client.get("/api/salary").json()["salary"] == "۵۰٬۰۰۰٬۰۰۰"
    assert _save_account(client, "0").status_code == 303
    assert _salary() == Decimal("0")


def test_error_rerender_does_not_echo_salary(client, no_network):
    _setup(client)
    r = client.post("/profile/account", data={"full_name": "", "username": "alice", "mobile": "12",
                                              "salary_toman": "88776655", "current_password": "",
                                              "new_password": "", "csrf": _csrf(client)})
    assert "88776655" not in r.text and SALARY_FA not in r.text
    assert _salary() == Decimal(SALARY_RAW)


def test_service_worker_and_js_never_store_salary():
    sw = (STATIC / "sw.js").read_text()
    assert 'url.pathname === "/api/salary") return true' in sw
    js = (STATIC / "privacy.js").read_text()
    salary_part = js[js.index("[data-salary-reveal]"):]
    for store in ("localStorage", "sessionStorage", "document.cookie"):
        assert store not in salary_part
    assert 'cache: "no-store"' in salary_part
