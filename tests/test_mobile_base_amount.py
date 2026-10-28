import re
from pathlib import Path

from app.config import STATIC_ASSET_VERSION
from tests.test_holdings import _csrf, _register, no_network  # noqa: F401
from tests.test_phase0_ui import _set_price

CSS = (Path(__file__).resolve().parents[1] / "app" / "static" / "style.css").read_text(encoding="utf-8")


def _cards(client):
    _register(client)
    _set_price("gold", "7400000")
    _set_price("coin_emami", "82000000")
    _set_price("usd", "100000")
    client.post("/profile", data={"gold_grams": "4", "coin_emami": "2", "usd": "300", "csrf": _csrf(client)})
    html = client.get("/dashboard").text
    return html, html[html.index('id="asset-cards"'):html.index('class="table-wrap only-desk"')]


def test_mobile_card_shows_base_amount_masked(client, no_network):
    html, cards = _cards(client)
    for qty, unit in (("۴", "گرم"), ("۲", "عدد"), ("۳۰۰٫۰۰", "دلار")):
        m = re.search(r'<span class="acard-qty" data-mask="portfolio" data-base-amount><bdi dir="ltr">' + qty + r"</bdi> " + unit + "</span>", cards)
        assert m, (qty, unit)
    # every base amount in the mobile cards carries the privacy mask
    assert cards.count("data-base-amount") == cards.count('data-mask="portfolio" data-base-amount') == 3
    # desktop table unchanged: plain muted cell, no new mask
    table = html[html.index('id="portfolio-table"'):html.index("</table>")]
    assert "data-base-amount" not in table and '<td class="muted"><bdi dir="ltr">۴</bdi> گرم</td>' in table


def test_base_amount_css_and_version():
    assert ".acard .nm .acard-qty { white-space: nowrap; }" in CSS
    assert ".acard .nm .acard-qty[data-mask]::after {" in CSS
    assert STATIC_ASSET_VERSION > "20261028e"


def test_row_toman_values_masked_mobile_and_desktop(client, no_network):
    html, cards = _cards(client)
    # mobile: every card value sits inside a portfolio mask
    assert cards.count('class="acard"') == cards.count('<div class="row-val" data-mask="portfolio" data-row-value><b>') == 3
    table = html[html.index('id="portfolio-table"'):html.index("</table>")]
    tbody = table[table.index("<tbody>"):table.index("</tbody>")]
    assert tbody.count("<tr") == tbody.count('<span class="row-val" data-mask="portfolio" data-row-value><b>') == 3
    tpl = (Path(__file__).resolve().parents[1] / "app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert '<div class="usd-equiv row-val" data-mask="portfolio">' in tpl  # crypto ≈ USD line in the table
    tfoot = table[table.index("<tfoot>"):]
    assert '<td class="num n num-strong"><span class="row-val" data-mask="portfolio" data-row-value>' in tfoot
    assert ".row-val[data-mask]::after { font-size: 15px;" in CSS
    assert 'html:not([data-show-portfolio="1"]) .row-val[data-mask="portfolio"] > * { display: none; }' in CSS


def test_share_percent_masked_unit_price_not(client, no_network):
    html, cards = _cards(client)
    assert cards.count('class="acard"') == cards.count('<span class="share-val" data-mask="portfolio" data-share>') == 3
    table = html[html.index('id="portfolio-table"'):html.index("</table>")]
    tbody = table[table.index("<tbody>"):table.index("</tbody>")]
    assert tbody.count("<tr") == tbody.count('<span class="share-pct share-val" data-mask="portfolio" data-share>') == 3
    # «قیمت واحد» stays visible: its cell has no mask
    assert re.search(r'<td class="num muted">[^<]+</td>', tbody)
    assert ".share-val[data-mask]::after {" in CSS
