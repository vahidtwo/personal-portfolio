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

    assert STATIC_ASSET_VERSION > "20261031b"


class _SvgText(HTMLParser):
    """Every text run inside an <svg> (title, text, tspan, desc) and whether it sits inside a [data-mask]."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # (tag, masked, in_svg)
        self.runs = []

    def handle_starttag(self, tag, attrs):
        if tag in _AmountScan.VOID:
            return
        top = self.stack[-1] if self.stack else ("", False, False)
        self.stack.append((tag, top[1] or "data-mask" in dict(attrs), top[2] or tag == "svg"))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        top = self.stack[-1] if self.stack else ("", False, False)
        if top[2] and data.strip():
            self.runs.append((data.strip(), top[1]))


def test_chart_text_is_masked_axis_footer_and_svg(client, no_network, clock):
    _register(client)
    _seed([("وام نمونه", 2350000, 12, 1405, 8, 5)])
    home = client.get("/dashboard").text
    # footer: max, min and the change for the range all sit inside a small mask
    foot = home.split('id="chart-foot"', 1)[1].split("</div>", 1)[0]
    for el in ("chart-max", "chart-min", "chart-change"):
        tag = re.search(rf'<b id="{el}"[^>]*>', foot)[0]
        assert 'data-mask="portfolio"' in tag and "mask-sm" in tag, el
    # with the footer filled the way the chart script fills it, the scan finds nothing unmasked...
    filled = home.replace('id="chart-foot" hidden', 'id="chart-foot"')
    for el in ("chart-max", "chart-min"):
        filled = re.sub(rf'(<b id="{el}"[^>]*>)</b>', r"\g<1>۱٬۲۳۴٫۵ میلیون تومان</b>", filled)
    assert _scan(filled).unmasked_amounts() == []
    # ...and does find the numbers once the masks are taken off
    assert len(_scan(filled.replace("data-mask=", "data-x=")).unmasked_amounts()) >= 2
    # SVG text: any digit in an svg is masked or a percentage, never an amount
    p = _SvgText()
    p.feed(_main(home))
    for text, masked in p.runs:
        if DIGIT.search(text) and not masked:
            assert "٪" in text or "%" in text, text
            assert not re.search(r"(تومان|دلار|هزار|میلیون|میلیارد)", text), text


def test_chart_canvas_drops_axis_values_and_tooltip_while_hidden():
    js = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    assert 'return document.documentElement.getAttribute("data-show-portfolio") !== "1";' in js
    opts = js.split("function chartOptions(view, opts) {", 1)[1].split("\n  }\n", 1)[0]
    assert "const hideValues = amountsHidden();" in opts
    assert "enabled: !rangeSelect && !hideValues," in opts
    y = opts.split("        y: {", 1)[1]
    assert "display: !hideValues," in y.split("grid:", 1)[0]
    # the line itself is untouched and the toggle redraws it
    assert 'attributeFilter: ["data-show-portfolio"]' in js
    assert "new MutationObserver(() => renderChart())" in js


AMOUNT_ATTR = re.compile(r"[0-9۰-۹][0-9۰-۹٬,٫.]*\s*(تومان|دلار|هزار|میلیون|میلیارد)")


def _attrs(html):
    """Every (tag, name, value) attribute in the page body."""
    out = []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            out.extend((tag, k, v or "") for k, v in attrs)

    P(convert_charrefs=True).feed(_main(html))
    return out


def test_no_amount_in_aria_labels_titles_or_data_attributes(client, no_network, clock):
    _register(client)
    _seed([("وام نمونه", 2350000, 12, 1405, 8, 5)], expenses=[("اجاره نمونه", 7100000, 1)])
    _seed_spends()
    for url in ("/dashboard", "/dashboard?tab=daily", "/profile?tab=debts"):
        html = client.get(url).text
        for tag, name, value in _attrs(html):
            if name in ("aria-label", "title", "alt", "placeholder") or name.startswith("data-"):
                assert not AMOUNT_ATTR.search(value), (url, tag, name, value)
        assert "data-sp-amount" not in html
    # the row menu is named by the spend and day, not its amount
    daily = client.get("/dashboard?tab=daily").text
    assert re.search(r'aria-label="گزینه‌های خرج [^"]+"', daily)
    assert not re.search(r'aria-label="گزینه‌های خرج [^"]*[0-9۰-۹]{2}[^"]*تومان', daily)


def test_category_share_percent_is_masked(client, no_network, clock):
    _register(client)
    _seed_spends()
    html = _main(client.get("/dashboard?tab=daily").text)
    p = _AmountScan()
    p.feed(html)
    percents = [(t, m) for t, m, skip in p.chunks if not skip and "٪" in t and DIGIT.search(t)]
    assert percents, "the category list shows shares"
    assert all(m for _, m in percents), [t for t, m in percents if not m]
    # and the check sees them once masks are off
    q = _AmountScan()
    q.feed(html.replace("data-mask=", "data-x="))
    assert any(not m for t, m, skip in q.chunks if not skip and "٪" in t and DIGIT.search(t))


def test_delete_confirm_prints_amount_only_when_shown():
    js = (STATIC / "spending-page.js").read_text(encoding="utf-8")
    fn = js.split("function confirmDelete(row, back) {", 1)[1].split("document.body.appendChild(d);", 1)[0]
    assert "data-sp-amount" not in js
    assert 'var shown = document.documentElement.getAttribute("data-show-portfolio") === "1";' in fn
    assert 'var amt = shown ? $(".a [data-amount]", row) : null;' in fn
    assert 'var desc = (amt ? amt.textContent.trim() + " تومان، " : "") + row.getAttribute("data-sp-name")' in fn


def test_debt_delete_confirm_fills_amounts_only_when_shown():
    js = (STATIC / "debts-page.js").read_text(encoding="utf-8")
    fn = js.split("function deleteBody(btn, row) {", 1)[1].split("\n  }\n", 1)[0]
    assert 'if (!shown || !row) return btn.getAttribute("data-body-masked");' in fn
    assert '.replace("{monthly}", amt(".a [data-amount]"))' in fn
    assert "textContent = deleteBody(t, btnRow);" in js
