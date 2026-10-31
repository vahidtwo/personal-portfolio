"""Quick UX: one-line SMS banner, list padding under the sticky add bar, 44px landing links, every amount masked."""
import re
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

from tests.test_debts_v2 import _seed, clock  # noqa: F401
from tests.test_holdings import _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
DIGIT = re.compile(r"[0-9۰-۹]")
UNIT = ("تومان", "دلار")


class _AmountScan(HTMLParser):
    """Collects every visible text run with a digit that is followed (within the same run of page text)
    by a currency unit, and whether it sits inside a [data-mask] element."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # (tag, masked, skip)
        self.chunks = []  # (text, masked, skip)

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        a = dict(attrs)
        masked = (self.stack[-1][1] if self.stack else False) or "data-mask" in a
        skip = (self.stack[-1][2] if self.stack else False) or tag in ("script", "style", "template", "label", "select", "textarea") \
            or "hidden" in a or a.get("aria-hidden") == "true"
        self.stack.append((tag, masked, skip))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        top = self.stack[-1] if self.stack else ("", False, False)
        self.chunks.append((data, top[1], top[2]))

    def unmasked_amounts(self):
        bad = []
        for i, (text, masked, skip) in enumerate(self.chunks):
            if skip or masked or not DIGIT.search(text):
                continue
            after = text + "".join(c[0] for c in self.chunks[i + 1:i + 4])
            m = re.search(r"[0-9۰-۹][0-9۰-۹٬,٫.]*\s*(<[^>]*>)?\s*(تومان|دلار)", after)
            if m and m.start() < len(text):
                bad.append(text.strip())
        return bad


def _main(html):
    return html.split('<main', 1)[1].split("</main>", 1)[0]


def _seed_spends(username="alice"):
    import jdatetime
    from app.daily_spend import categories_for_user, ensure_spend_categories
    from app.db import SessionLocal
    from app.models import DailySpend, User

    db = SessionLocal()
    user = db.query(User).filter_by(username=username).one()
    ensure_spend_categories(db, user)
    parents, children = categories_for_user(db, user)
    for amount, day in ((450000, 28), (1250000, 27), (99000, 3)):
        db.add(DailySpend(user_id=user.id, category_id=parents[0].id, amount_toman=Decimal(amount),
                          spent_on=jdatetime.date(1405, 7, day).togregorian(), note=""))
    db.commit()
    db.close()


def _scan(html):
    p = _AmountScan()
    p.feed(_main(html))
    return p


def test_every_amount_on_home_spends_and_debts_is_masked(client, no_network, clock):
    _register(client)
    _seed([("وام نمونه", 2350000, 12, 1405, 8, 5)], expenses=[("اجاره نمونه", 7100000, 1)])
    _seed_spends()
    pages = {
        "home": client.get("/dashboard").text,
        "spends": client.get("/dashboard?tab=daily").text,
        "debts": client.get("/profile?tab=debts").text,
    }
    for name, html in pages.items():
        assert _scan(html).unmasked_amounts() == [], name
    home = pages["home"]
    # the two home tiles that used to leak
    for tile in ("tile-next-debt", "tile-month-spend"):
        chunk = home.split(f'id="{tile}"', 1)[1].split("</a>", 1)[0]
        assert chunk.count('data-mask="portfolio"') >= 1, tile
    assert "۲٬۳۵۰٬۰۰۰" in home.split('id="tile-next-debt"', 1)[1].split("</a>", 1)[0]
    # the scan really sees amounts: unmasking everything makes it fail
    assert _scan(home.replace("data-mask=", "data-x=")).unmasked_amounts()
    assert _scan(pages["spends"].replace("data-mask=", "data-x=")).unmasked_amounts()


def test_small_masks_use_small_stars():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".mask-sm[data-mask]::after { font-size: 13px;" in css


def test_sms_offer_is_a_one_line_banner_and_dismiss_persists(client, no_network):
    _register(client)
    html = client.get("/dashboard?tab=daily").text
    banner = html.split('id="sms-offer"', 1)[1].split("</aside>", 1)[0]
    assert "<h2" not in banner and "<p" not in banner and "card-desc" not in banner
    assert "data-sms-offer-enable" in banner and "data-sms-offer-dismiss" in banner
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".sms-offer-text { flex: 1; min-width: 0; white-space: nowrap;" in css
    assert re.search(r"\.sms-offer-enable, \.sms-offer-close \{[^}]*min-width: 44px; min-height: 44px;", css)
    js = (STATIC / "sms-offer.js").read_text(encoding="utf-8")
    assert 'localStorage.getItem(KEY) === "1"' in js and 'localStorage.setItem(KEY, "1")' in js


def test_list_has_room_under_sticky_add_bar():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "@media (max-width:899px){\n  .sp-page{padding-bottom:140px}" in css


def test_landing_inline_links_get_44px_tap_targets(client):
    html = client.get("/").text
    main = _main(html)
    assert re.search(r"<p>[^<]*<a href=\"https://chande.net/\"", main)
    css = (STATIC / "landing-v2.css").read_text(encoding="utf-8")
    rule = re.search(r"main p a:not\(\.btn\)[^{]*\{([^}]*)\}", css)
    assert rule and "padding:10px 6px" in rule[1] and "min-height:44px" in rule[1] and "margin:-10px -6px" in rule[1]


def test_static_asset_version_bumped():
    from app.config import STATIC_ASSET_VERSION

    assert STATIC_ASSET_VERSION > "20261031a"
