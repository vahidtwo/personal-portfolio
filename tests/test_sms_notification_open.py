"""Tapping an SMS spend notification opens the app on the daily spend page (signed in, after login, open app)."""
import re
from pathlib import Path

from tests.test_holdings import _register, no_network  # noqa: F401
from tests.test_offline_privacy import _sw

ROOT = Path(__file__).resolve().parents[1]
KT = ROOT / "android" / "app" / "src" / "main" / "java" / "app" / "myinventory"


def _kt(name):
    return (KT / name).read_text(encoding="utf-8")


def test_every_sms_notification_has_a_tap_target():
    src = _kt("SmsReceiver.kt")
    for fn in ("notifySaved", "notifyError"):
        body = src[src.index(f"private fun {fn}("):]
        body = body[:body.index(".build()")]
        assert ".setContentIntent(tapIntent(context, tapPath))" in body and ".setAutoCancel(true)" in body, fn
    assert "HomeActivity::class.java)\n" not in src.split("internal fun tapIntent")[0]
    tap = src[src.index("internal fun tapIntent"):src.index("internal fun notify(")]
    assert "HomeActivity::class.java" in tap and "NotificationTarget.FLAGS" in tap and "NotificationTarget.EXTRA" in tap
    assert "path.hashCode()" in tap and "FLAG_IMMUTABLE" in tap
    assert not re.search(r"notify\(\w+, [^\n]*, null\)", src)


def test_home_activity_opens_the_target_in_all_three_cases():
    home = _kt("HomeActivity.kt")
    oncreate = home[home.index("override fun onCreate"):home.index("override fun onSaveInstanceState")]
    assert "NotificationTarget.safePath(intent?.getStringExtra(NotificationTarget.EXTRA))" in oncreate
    assert oncreate.index("showLogin()\n        openPendingTarget()") > 0
    assert "override fun onNewIntent(intent: Intent)" in home
    newintent = home[home.index("override fun onNewIntent"):home.index("private fun openPendingTarget")]
    assert "openPendingTarget()" in newintent and "setIntent(intent)" in newintent
    login_ok = home[home.index('"ok" -> {'):home.index('"stepb" ->')]
    assert "openPendingTarget()" in login_ok
    assert 'outState.putString("pending_target", pendingTarget)' in home


def test_main_activity_loads_a_new_path_on_new_intent():
    main = _kt("MainActivity.kt")
    block = main[main.index("override fun onNewIntent"):main.index("private fun openAdvancedSetup")]
    assert "loadRemote(NativeSession.BASE" in block and "NotificationTarget.safePath" in block


def test_add_param_opens_the_spend_form(client, no_network):
    _register(client)
    plain = client.get("/dashboard?tab=daily").text
    opened = client.get("/dashboard?tab=daily&add=1&src=notification").text
    assert re.search(r'<div class="sp-page" data-sp-page>', plain)
    assert re.search(r'<div class="sp-page" data-sp-page data-sp-open>', opened)


def _cached_daily_then_new():
    return [
        {"online": "ok", "body": "<p>old spends</p>", "go": "/dashboard?tab=daily"},
        {"advance": 120_000, "online": "ok", "body": "<p>spend from sms</p>"},
    ]


def test_sw_serves_notification_url_from_network_and_never_stores_it():
    for path in ("/dashboard?tab=daily&src=notification", "/dashboard?tab=daily&add=1&src=notification"):
        r = _sw(_cached_daily_then_new() + [{"go": path}], maxAgeMs=10_000_000)
        assert "spend from sms" in r[1]["body"], path
        assert r[1]["pages"] == ["https://app.test/dashboard?tab=daily"], path
        assert r[1]["messages"] == []


def test_sw_notification_url_offline_falls_back_to_cached_daily():
    r = _sw(_cached_daily_then_new() + [{"online": False, "go": "/dashboard?tab=daily&src=notification"}],
            maxAgeMs=10_000_000)
    assert "old spends" in r[1]["body"]


def test_sw_plain_daily_tab_still_cache_first():
    r = _sw(_cached_daily_then_new() + [{"go": "/dashboard?tab=daily"}], maxAgeMs=10_000_000)
    assert "old spends" in r[1]["body"]
