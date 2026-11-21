"""Store flavor (Iranian app store): no in-app installer; direct flavor unchanged."""
import glob
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "app"
A = "{http://schemas.android.com/apk/res/android}"
INSTALL = "android.permission.REQUEST_INSTALL_PACKAGES"


def _merged(variant):
    hits = glob.glob(str(APP / "build/intermediates/merged_manifests" / variant / "*" / "AndroidManifest.xml"))
    if not hits:
        pytest.skip(f"no merged manifest for {variant}; run the Android build first")
    return ET.parse(hits[0]).getroot()


def _perms(root):
    return {e.get(A + "name") for e in root.iter("uses-permission")}


def _providers(root):
    return {e.get(A + "authorities") for e in root.iter("provider")}


def test_store_merged_manifest_has_no_installer():
    m = _merged("storeRelease")
    assert m.get("package") == "app.myinventory"
    assert INSTALL not in _perms(m)
    assert "android.permission.RECEIVE_SMS" in _perms(m)
    assert "app.myinventory.updates" not in _providers(m)


@pytest.mark.parametrize("variant", ["directRelease", "directQa"])
def test_direct_merged_manifest_unchanged(variant):
    m = _merged(variant)
    assert m.get("package") == "app.myinventory"
    assert {INSTALL, "android.permission.RECEIVE_SMS", "android.permission.INTERNET"} <= _perms(m)
    assert "app.myinventory.updates" in _providers(m)


def test_flavors_declared_and_store_manifest_removes_installer():
    gradle = (APP / "build.gradle.kts").read_text()
    assert re.search(r'create\("direct"\)\s*\{[^}]*isDefault = true[^}]*IN_APP_UPDATES", "true"', gradle)
    assert re.search(r'create\("store"\)\s*\{[^}]*IN_APP_UPDATES", "false"', gradle)
    assert 'applicationIdSuffix' not in gradle and 'versionNameSuffix' not in gradle
    store = (APP / "src/store/AndroidManifest.xml").read_text()
    assert INSTALL in store and 'tools:node="remove"' in store


def test_update_flow_gated_on_flavor():
    src = (APP / "src/main/java/app/myinventory/UpdateNotifier.kt").read_text()
    assert src.count("if (!UpdateCheck.inAppUpdatesEnabled) return") == 3
    assert "BuildConfig.IN_APP_UPDATES" in (APP / "src/main/java/app/myinventory/UpdateCheck.kt").read_text()


def test_direct_apk_path_unchanged():
    docker = (ROOT / "android/Dockerfile").read_text()
    assert "apk/direct/release/app-release.apk /src/out/my-inventory.apk" in docker
    assert "/src/out/my-inventory-store.apk" in docker


def test_sms_is_opt_in_with_persian_explanation():
    d = APP / "src/main/java/app/myinventory"
    prefs = (d / "SmsPrefs.kt").read_text()
    assert "getBoolean(KEY_ENABLED, false)" in prefs
    assert "fun isActive(c: Context): Boolean = isEnabledPref(c) && permissionGranted(c)" in prefs
    assert "SmsPrefs.isActive(context)" in (d / "SmsReceiver.kt").read_text()
    main = (d / "MainActivity.kt").read_text()
    assert "RECEIVE_SMS" not in main
    settings = (d / "SmsSettingsActivity.kt").read_text()
    assert "if (!wantOn) { SmsPrefs.setEnabled(this, false)" in settings
    assert settings.count("Manifest.permission.RECEIVE_SMS), REQ_SMS") == 1
    sheet = settings.split("private fun showPrePermissionSheet")[1].split("override fun")[0]
    assert "خودکار ثبت" in sheet and "اجازه" in sheet and "فعلاً نه" in sheet
    assert sheet.index("requestPermissions") > sheet.index("به سایت فرستاده")
