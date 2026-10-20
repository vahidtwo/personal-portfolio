"""The debts tab must not render settings-only sections (settings APK row with version; the side-menu link is separate, push, MCP, logout row)."""
from tests.test_holdings import _register, no_network  # noqa: F401


def test_debts_tab_has_no_settings_sections(client, no_network):
    _register(client, "debtview1")
    debts = client.get("/profile?tab=debts").text
    for marker in ("settings-row apk-download", 'id="android-app-settings"', 'id="advanced"', 'id="settings-account-actions"', 'id="push-settings"'):
        assert marker not in debts, marker
    assert 'id="debt-form"' in debts
    settings = client.get("/profile").text
    assert 'id="settings-account-actions"' in settings and 'id="advanced"' in settings
