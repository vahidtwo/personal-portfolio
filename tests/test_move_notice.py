"""Domain move (portfolio.vahidtwo.ir -> daraiito.ir): the one-time old-host notice and the #hide=1 handoff.
Text/behaviour only: no redirects, no migration. Browser JS runs under node with tiny DOM stubs (skipped without node)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_holdings import _register, no_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
OLD, NEW = "portfolio.vahidtwo.ir", "daraiito.ir"
need_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

REHIDE = "نمایش مبلغ‌ها را دوباره پنهان کنید"


def _page(client, host, path="/dashboard"):
    return client.get(path, headers={"host": host}).text


# ---- server: where the notice is rendered ----

def test_notice_only_on_the_old_host_for_signed_in_users(client, no_network):
    _register(client)
    html = _page(client, OLD)
    assert 'id="move-notice"' in html and 'data-new-url="https://daraiito.ir"' in html
    assert 'src="/static/move-notice.js?v=' in html and "hidden>" in html  # starts hidden; JS reveals it
    assert REHIDE in html and "فقط یک بار باید دوباره وارد شوید" in html
    assert 'href="https://daraiito.ir/"' in html  # the JS adds #hide=1 only when amounts are hidden
    assert "#hide=1" not in re.search(r'<section class="move-notice.*?</section>', html, re.S).group(0)


def test_no_notice_on_the_new_host_or_other_hosts(client, no_network):
    _register(client)
    for host in (NEW, "www.daraiito.ir", "testserver", "portfolio.vahidtwo.ir.evil.example", "evil-portfolio.vahidtwo.ir"):
        html = _page(client, host)
        assert "move-notice" not in html, host
    assert "move-notice" not in _page(client, f"{NEW}:443")
    assert 'id="move-notice"' in _page(client, f"{OLD}:443")  # port in the Host header is fine


def test_no_notice_for_signed_out_visitors_on_the_old_host(client, no_network):
    for path in ("/auth", "/"):
        assert "move-notice" not in _page(client, OLD, path)


def test_notice_is_not_rendered_on_the_other_logged_in_pages_of_the_new_host(client, no_network):
    _register(client)
    for path in ("/assets", "/profile"):
        assert "move-notice" not in _page(client, NEW, path)
        assert 'id="move-notice"' in _page(client, OLD, path)


def test_handoff_script_is_on_every_entry_page_before_the_privacy_check(client, no_network):
    landing = client.get("/").text
    assert 'location.hash!=="#hide=1"' in landing
    _register(client)
    base = client.get("/dashboard").text
    assert base.index('location.hash!=="#hide=1"') < base.index('localStorage.getItem("privacy-portfolio")')


def test_protected_keys_unchanged_and_no_redirects(client, no_network):
    assert 'getItem("privacy-portfolio")' in (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    assert 'portfolio: "privacy-portfolio"' in (STATIC / "privacy.js").read_text(encoding="utf-8")
    r = client.get("/health", headers={"host": OLD}, follow_redirects=False)
    assert r.status_code == 200
    r = client.get("/auth", headers={"host": OLD}, follow_redirects=False)
    assert r.status_code == 200  # no server redirect to the new host


# ---- client JS under node ----

def _node(code: str):
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


HARNESS = r"""
const vm = require("vm"), fs = require("fs");
function run(file, o) {
  const store = Object.assign({}, o.storage || {});
  const el = {hidden: true, attrs: {"data-new-url": "https://daraiito.ir"}, handlers: {}};
  const go = {attrs: {href: "https://daraiito.ir/"}, setAttribute(k, v) { this.attrs[k] = v; }};
  const dismiss = {addEventListener(t, f) { el.handlers[t] = f; }};
  el.getAttribute = (k) => el.attrs[k];
  el.querySelector = () => dismiss;
  const replaced = [];
  const ctx = {
    window: {},
    location: Object.assign({hostname: "portfolio.vahidtwo.ir", hash: "", pathname: "/dashboard", search: "?tab=x"}, o.location || {}),
    history: {state: null, replaceState(s, t, u) { replaced.push(u); }},
    document: {
      documentElement: {classList: {contains: (c) => !!o.inApp && c === "in-android-app"}},
      getElementById: (id) => (id === "move-notice" ? (o.noBox ? null : el) : id === "move-notice-go" ? go : null),
    },
    localStorage: {
      getItem(k) { if (o.storageThrows) throw new Error("denied"); return k in store ? store[k] : null; },
      setItem(k, v) { if (o.storageThrows) throw new Error("denied"); store[k] = String(v); },
    },
  };
  if (o.bridge) ctx.window.AndroidBridge = {};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(file, "utf8"), ctx);
  return {store, el, go, replaced, click: () => el.handlers.click && el.handlers.click()};
}
"""


def _notice(opts: dict, then: str = "") -> dict:
    code = HARNESS + f"""
const r = run({json.dumps(str(STATIC / 'move-notice.js'))}, {json.dumps(opts)});
{then}
console.log(JSON.stringify({{hidden: r.el.hidden, href: r.go.attrs.href, store: r.store}}));
"""
    return _node(code)


@need_node
def test_notice_shows_once_on_the_old_host_and_dismissal_is_remembered():
    first = _notice({})
    assert first["hidden"] is False and first["href"] == "https://daraiito.ir/"
    dismissed = _notice({}, "r.click();")
    assert dismissed["hidden"] is True and dismissed["store"] == {"move-notice-seen": "1"}
    again = _notice({"storage": {"move-notice-seen": "1"}})
    assert again["hidden"] is True  # one-time: never again on this device
    # the dismissal does not touch the privacy key
    assert "privacy-portfolio" not in dismissed["store"]


@need_node
def test_notice_link_carries_hide_only_when_amounts_are_hidden():
    assert _notice({"storage": {"privacy-portfolio": "1"}})["href"] == "https://daraiito.ir/#hide=1"
    for v in ("0", "", "2", "true"):
        assert _notice({"storage": {"privacy-portfolio": v}})["href"] == "https://daraiito.ir/", v
    shown = _notice({"storage": {"privacy-portfolio": "1"}})
    assert shown["store"] == {"privacy-portfolio": "1"}  # read only, never written by the notice


@need_node
def test_notice_never_shows_on_the_new_host_or_in_the_android_app():
    assert _notice({"location": {"hostname": "daraiito.ir"}})["hidden"] is True
    assert _notice({"location": {"hostname": "testserver"}})["hidden"] is True
    assert _notice({"location": {"hostname": "portfolio.vahidtwo.ir.evil.example"}})["hidden"] is True
    assert _notice({"bridge": True})["hidden"] is True      # WebView with the JS bridge (installed app)
    assert _notice({"inApp": True})["hidden"] is True       # .in-android-app class
    assert _notice({"noBox": True})["hidden"] is True       # element absent (new host render): no crash
    assert _notice({"storageThrows": True})["hidden"] is True  # can't remember a dismissal -> don't nag


def _handoff(hash_: str, storage: dict | None = None, throws: bool = False) -> dict:
    partial = (ROOT / "app/templates/partials/hide_handoff.html").read_text(encoding="utf-8")
    js = re.search(r"<script>(.*?)</script>", partial, re.S).group(1)
    code = HARNESS + f"""
const os = require("os"), path = require("path");
const f = path.join(os.tmpdir(), "handoff-" + process.pid + ".js"); fs.writeFileSync(f, {json.dumps(js)});
const r = run(f, {json.dumps({"location": {"hostname": "daraiito.ir", "hash": hash_}, "storage": storage or {}, "storageThrows": throws})});
fs.unlinkSync(f);
console.log(JSON.stringify({{store: r.store, replaced: r.replaced}}));
"""
    return _node(code)


@need_node
def test_hide_handoff_sets_hidden_then_strips_the_hash():
    out = _handoff("#hide=1")
    assert out["store"] == {"privacy-portfolio": "1"}
    assert out["replaced"] == ["/dashboard?tab=x"]  # hash gone, path and query kept


@need_node
def test_hide_handoff_ignores_every_other_value_and_can_never_reveal():
    for h in ("", "#", "#hide=0", "#hide=2", "#hide=", "#hide", "#hide=true", "#hide=1&x=1", "#x=hide=1", "#HIDE=1", "#show=1", "#hide=1 "):
        assert _handoff(h) == {"store": {}, "replaced": []}, h
    # a stored "hidden" choice stays hidden, a "shown" choice is never written by the handoff
    assert _handoff("#hide=0", {"privacy-portfolio": "1"})["store"] == {"privacy-portfolio": "1"}
    assert _handoff("#hide=1", {"privacy-portfolio": "0"})["store"] == {"privacy-portfolio": "1"}  # hide only
    assert _handoff("#hide=1", throws=True) == {"store": {}, "replaced": []}  # storage blocked: no crash


def test_copy_has_the_required_phrases():
    html = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    for needle in (REHIDE, "آدرس دارایی‌تو عوض می‌شود", "فقط یک بار باید دوباره وارد شوید", "فهمیدم"):
        assert needle in html
    js = (STATIC / "move-notice.js").read_text(encoding="utf-8")
    assert "setItem(\"privacy-portfolio\"" not in js and 'removeItem' not in js
