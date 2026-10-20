"""Assets v2 (mockups/app-v2/assets): per-field server errors, row visibility after an error, welcome, copy."""
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
JSON = {"Accept": "application/json"}


def _user():
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    return db, db.query(User).filter_by(username="alice").one()


@pytest.mark.parametrize("raw,reason", [
    ("۱٫۲٫۳", "decimal_point"), ("1.234,5", "decimal_point"), ("abc", "not_number"), ("-۵", "negative"),
    ("−2", "negative"), ("1.123456789", "too_many_decimals"), ("", None), ("۰", None), ("-0", None),
    ("۱٬۲۳۴٫۵", None), ("0.12345678", None),
])
def test_quantity_error_reasons(raw, reason):
    from app.number_input import quantity_error

    assert quantity_error(raw) == reason


def test_json_save_returns_field_map_with_422_and_saves_nothing(client, no_network):
    _register(client)
    client.post("/profile", data={"btc": "2", "csrf": _csrf(client, "/assets")})
    r = client.post("/profile", headers=JSON, data={"btc": "2", "eth": "۱٫۲٫۳", "gold_grams": "-۵", "next": "/assets",
                                                     "csrf": _csrf(client, "/assets")})
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False and body["error"] == "یکی از مقادیر وارد شده نامعتبر است"  # old message kept
    assert body["fields"] == {"eth": "فقط یک ممیز (٫) بگذارید؛ مثلاً ۱٫۲۵", "gold_grams": "مقدار نمی‌تواند منفی باشد"}
    assert body["reasons"] == {"eth": "decimal_point", "gold_grams": "negative"}
    db, u = _user()
    assert u.btc == Decimal("2") and u.eth == 0 and u.gold_grams == 0
    db.close()


def test_json_save_ok(client, no_network):
    _register(client)
    r = client.post("/profile", headers=JSON, data={"btc": "۰٫۵", "next": "/assets", "csrf": _csrf(client, "/assets")})
    assert r.status_code == 200 and r.json() == {"ok": True, "redirect": "/assets"}
    db, u = _user()
    assert u.btc == Decimal("0.5")
    db.close()


def test_form_post_error_renders_inline_errors_summary_and_keeps_row_visibility(client, no_network):
    _register(client)
    client.post("/profile", data={"btc": "2", "csrf": _csrf(client, "/assets")})
    # btc (held) is unchanged, eth (not held) gets a bad value, gold not posted at all
    r = client.post("/profile", data={"btc": "2", "eth": "abc", "next": "/assets", "csrf": _csrf(client, "/assets")})
    html = r.text
    assert r.status_code == 200
    assert 'id="err-asset-eth"' in html and "فقط عدد وارد کنید" in html
    assert 'aria-describedby="err-asset-eth worth-eth"' in html and 'aria-invalid="true"' in html
    assert 'role="alert"' in html and 'href="#asset-eth">اتریوم: عدد نامعتبر</a>' in html
    import re
    rows = dict(re.findall(r'data-asset-row="(\w+)"[^>]*?( hidden)?>', html))
    assert rows["btc"] == "" and rows["eth"] == ""  # held + the invalid one are shown
    assert rows["gold"] == " hidden" and rows["usd"] == " hidden"  # untouched rows keep their original hidden state
    assert 'name="gold_grams" value=""' in html  # no Latin «0» in an untouched field


def test_too_many_decimals_cash_is_two(client, no_network):
    _register(client)
    r = client.post("/profile", headers=JSON, data={"cash_toman": "10.123", "csrf": _csrf(client, "/assets")})
    assert r.status_code == 422 and r.json()["fields"] == {"cash_toman": "حداکثر ۲ رقم اعشار"}


def test_new_user_gets_welcome_with_quick_adds_and_no_zero_cards(client, no_network):
    _register(client)
    html = client.get("/assets").text
    assert "اولین دارایی‌تان را اضافه کنید" in html and "همهٔ دارایی‌ها" in html
    for key in ("gold", "coin_emami", "usd", "cash"):
        assert f'data-v2-quick="{key}"' in html
    for sub in ("به گرم", "به عدد", "به دلار", "به تومان"):
        assert sub in html
    assert 'class="asset-group v2-hide"' in html and 'data-asset-group="car"' in html  # car/Sanjeh stays


def test_holder_gets_rows_menu_count_and_add_button(client, no_network):
    _register(client)
    client.post("/profile", data={"btc": "2", "eth": "1", "csrf": _csrf(client, "/assets")})
    html = client.get("/assets").text
    assert "اولین دارایی‌تان را اضافه کنید" not in html
    assert 'aria-label="گزینه‌های بیت‌کوین"' in html and 'aria-haspopup="menu"' in html
    assert "۲ دارایی" in html and "data-v2-add-open" in html
    assert "دارایی‌های خالی در خانه نمایش داده نمی‌شوند" not in html  # shortened intro
    assert " · " not in html.split("<main", 1)[-1].split("</main>", 1)[0]


def test_missing_price_banner_names_the_asset(client, no_network):
    _register(client)
    client.post("/profile", data={"sol": "3", "csrf": _csrf(client, "/assets")})
    html = client.get("/assets").text
    assert 'role="status"' in html and "قیمت روز سولانا در دسترس نیست" in html
    assert "مقدارش محفوظ است" in html


def test_static_contract_js_css():
    js = (STATIC / "assets-v2.js").read_text(encoding="utf-8")
    for needle in ('role", opts.role || "dialog"', '"alertdialog"', "aria-modal", "Escape", "حذف می‌شود", "برگردان",
                   "ذخیره…", "ذخیره نشد", "دوباره", "ارزش تقریبی", 'Accept: "application/json"', "if (busy) return",
                   'focus: "[data-v2-close]"'):
        assert needle in js, needle
    page = (STATIC / "assets-page.js").read_text(encoding="utf-8")
    assert "حذف ذخیره نشده" in page
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".help-link{min-height:44px" in css and ".v2-more{width:44px;height:46px" in css
    assert "flex-wrap: nowrap; overflow-x: auto" not in css  # chips wrap on mobile


def test_js_rules_match_server(tmp_path):
    """Run the client validator in node against the server's cases (skipped if node is missing)."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    from app.number_input import quantity_error

    cases = ["۱٫۲٫۳", "1.234,5", "abc", "-۵", "−2", "1.123456789", "", "۰", "-0", "۱٬۲۳۴٫۵", "0.12345678", "۲"]
    src = (STATIC / "number-format.js").read_text(encoding="utf-8")
    v2 = (STATIC / "assets-v2.js").read_text(encoding="utf-8")
    body = v2[v2.index("  function reason("):v2.index("  function message(")]
    script = tmp_path / "t.js"
    script.write_text("var window=globalThis;" + src + "\nvar NF=globalThis.NumberFa||module.exports;\n" + body +
                      "\nconsole.log(JSON.stringify(" + __import__("json").dumps(cases) + ".map(function(c){return reason(c,8)})));",
                      encoding="utf-8")
    out = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    assert __import__("json").loads(out.stdout) == [quantity_error(c) for c in cases]
