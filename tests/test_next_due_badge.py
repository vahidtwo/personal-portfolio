import re
from pathlib import Path

from tests.test_holdings import _csrf, _register, no_network  # noqa: F401

CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "style.css"


def test_danger_bg_is_never_redefined_solid():
    # The next-due chip uses background var(--danger-bg) with color var(--danger); a solid
    # --danger-bg makes its label invisible. Every definition must stay a translucent tint.
    defs = re.findall(r"--danger-bg\s*:\s*([^;}]+)", CSS.read_text(encoding="utf-8"))
    assert defs and all(d.strip().startswith("rgba(") for d in defs), defs


def test_next_due_badge_label_rendered(client, no_network):
    import jdatetime
    _register(client)
    due = jdatetime.date.today() + jdatetime.timedelta(days=2)
    r = client.post("/profile/debts", data={"title": "رسالت", "monthly_toman": "30000000", "months_left": "10",
        "due_year": str(due.year), "due_month": str(due.month), "due_day": str(due.day),
        "csrf": _csrf(client, "/profile?tab=debts")})
    assert r.status_code in (200, 303), r.text[:300]
    html = client.get("/dashboard").text
    m = re.search(r'<span class="badge badge-due is-soon">([^<]+)</span>', html)
    assert m and m.group(1).strip() == "۲ روز دیگر"
