"""Phase 6 item 14: unit price on phone cards and asset rows, live auth field errors, no bare «API», header CTA."""
import re
import shutil
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def _price(symbol, price):
    from app.db import SessionLocal
    from app.models import MarketPrice

    db = SessionLocal()
    row = db.get(MarketPrice, symbol) or MarketPrice(symbol=symbol)
    row.price_toman = Decimal(price)
    row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.merge(row)
    db.commit()
    db.close()


def _seed(client):
    _register(client)
    client.post("/profile", data={"gold_grams": "2", "btc": "0.5", "usd": "10", "cash_toman": "5000000",
                                  "csrf": _csrf(client)})
    _price("gold", "7400000")
    _price("btc", "6000000000")
    _price("usd", "90000")


def test_unit_price_parts_skip_cash_car_and_missing_prices():
    from app.portfolio import unit_price_parts

    assert unit_price_parts("gold", Decimal("7400000")) == {"amount": "۷٬۴۰۰٬۰۰۰", "unit": "گرم", "unit_latin": False}
    assert unit_price_parts("usd", Decimal("90000"))["unit"] == "دلار"
    assert unit_price_parts("btc", Decimal("6000000000"))["unit_latin"] is True
    assert unit_price_parts("cash", Decimal("1")) is None
    assert unit_price_parts("car", Decimal("900000000")) is None
    assert unit_price_parts("gold", None) is None


def test_phone_cards_show_unmasked_unit_price(client, no_network):
    _seed(client)
    html = client.get("/dashboard").text
    cards = html[html.index('id="asset-cards"'):html.index('class="table-wrap only-desk"')]
    assert 'class="acard-price">قیمت روز: <span class="up-v"><bdi dir="ltr">۷٬۴۰۰٬۰۰۰</bdi> تومان/گرم</span></span>' in cards
    assert 'قیمت روز: <span class="up-v"><bdi dir="ltr">۹۰٬۰۰۰</bdi> تومان/دلار' in cards
    assert 'تومان/<bdi dir="ltr">BTC</bdi>' in cards
    assert cards.count("acard-price") == 3  # cash has no unit price
    assert ".acard-price .up-v, .arow-price .up-v { white-space: nowrap; }" in (STATIC / "style.css").read_text(encoding="utf-8")
    for line in re.findall(r'<span class="acard-price"[^>]*>', cards):
        assert "data-mask" not in line  # a market price is not private


def test_assets_rows_show_unit_price(client, no_network):
    _seed(client)
    html = client.get("/assets").text
    assert 'class="arow-price">قیمت روز: <span class="up-v"><bdi dir="ltr">۷٬۴۰۰٬۰۰۰</bdi> تومان/گرم</span></span>' in html
    row = re.search(r'data-asset-row="cash".*?</div>\s*</div>', html, re.S).group(0)
    assert "arow-price" not in row


def test_api_home_rows_carry_unit_price(client, no_network):
    _seed(client)
    rows = {r["key"]: r for r in client.get("/api/home").json()["rows"]}
    assert rows["gold"]["unit_price"] == {"amount": "۷٬۴۰۰٬۰۰۰", "unit": "گرم", "unit_latin": False}
    assert rows["cash"]["unit_price"] is None


def test_no_bare_api_in_user_facing_copy(client):
    html = client.get("/").text
    assert "API عمومی" not in html and "رابط عمومی ارزبان" in html
    for path in ("app/templates/landing.html", "app/templates/partials/price_sources.html"):
        assert "API عمومی" not in (ROOT / path).read_text(encoding="utf-8")


def test_landing_header_cta_says_login_or_signup(client):
    html = client.get("/").text
    top = re.search(r'<nav class="top-actions"[^>]*>(.*?)</nav>', html, re.S).group(1)
    assert '<a class="top-link" href="/auth">ورود / ثبت‌نام</a>' in top
    assert "<h1>ورود یا ساخت حساب</h1>" in client.get("/auth").text


def test_auth_js_checks_fields_while_typing():
    js = (STATIC / "auth.js").read_text(encoding="utf-8")
    from app import unified_auth

    assert unified_auth.USERNAME_ERROR in js  # same copy as the server
    assert 'userIn.addEventListener("input"' in js and 'passIn.addEventListener("input"' in js
    assert "event.preventDefault();" in js


def test_asset_inputs_validate_on_input():
    js = (STATIC / "assets-v2.js").read_text(encoding="utf-8")
    assert 'input.addEventListener("input", function () { check(input); });' in js


HARNESS = r"""
const fs = require("fs");
function El(id, extra) {
  const e = Object.assign({ id, value: "", textContent: "", className: "", readOnly: false, attrs: {}, listeners: {},
    classList: { s: new Set(), toggle(c, on) { on ? this.s.add(c) : this.s.delete(c); }, contains(c) { return this.s.has(c); } },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    removeAttribute(k) { delete this.attrs[k]; }, addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    fire(t, ev) { (this.listeners[t] || []).forEach(f => f(ev || {})); }, focus() { focused = this.id; } }, extra || {});
  return e;
}
let focused = null;
const box = { classList: { s: new Set(), toggle(c, on) { on ? this.s.add(c) : this.s.delete(c); } } };
const user = El("username", { type: "text", closest: () => box });
const pass = El("password", { type: "password", closest: () => ({ classList: { toggle() {} } }), parentElement: null });
const uh = El("username-hint", { textContent: "idle", className: "hint" });
const ph = El("password-hint", { textContent: "دست‌کم ۸ حرف", className: "hint" });
const form = El("form", { dataset: {}, querySelectorAll: () => [], querySelector: () => null });
const byId = { username: user, password: pass, "username-hint": uh, "password-hint": ph };
global.document = {
  getElementById: id => byId[id] || null,
  querySelectorAll: sel => sel === "input[type=password]" ? [pass] : [],
  querySelector: sel => sel === "[data-auth-form]" ? form : null,
};
eval(fs.readFileSync(process.argv[2], "utf8"));
const out = {};
user.value = "1ab"; user.fire("input"); out.badStart = [uh.className, uh.textContent, box.classList.s.has("err")];
user.value = "ab"; user.fire("input"); out.partialOk = [uh.className, user.getAttribute("aria-invalid")];
user.fire("blur"); out.shortOnBlur = uh.className;
user.value = "alice"; user.fire("input"); out.fixed = uh.className;
pass.value = "abc"; pass.fire("input"); out.shortPass = [ph.className, ph.textContent];
pass.value = ""; let prevented = false; form.fire("submit", { preventDefault() { prevented = true; } });
out.emptySubmit = [prevented, ph.className, focused];
pass.value = "short1"; prevented = false; form.fire("submit", { preventDefault() { prevented = true; } });
out.shortSubmitAllowed = !prevented;
console.log(JSON.stringify(out));
"""


def test_auth_live_errors_in_node(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    script = tmp_path / "harness.js"
    script.write_text(HARNESS, encoding="utf-8")
    import json

    res = subprocess.run([node, str(script), str(STATIC / "auth.js")], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    from app import unified_auth

    assert out["badStart"] == ["hint bad", unified_auth.USERNAME_ERROR, True]
    assert out["partialOk"] == ["hint", None]
    assert out["shortOnBlur"] == "hint bad"
    assert out["fixed"] == "hint"
    assert out["shortPass"] == ["hint warn", "دست‌کم ۸ حرف"]
    assert out["emptySubmit"] == [True, "hint bad", "password"]
    assert out["shortSubmitAllowed"] is True  # old accounts may have shorter passwords; the server decides
