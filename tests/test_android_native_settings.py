"""Native settings tab: static checks on the app source (salary privacy, fallback flag, logout order)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "android" / "app"
KT = APP / "src" / "main" / "java" / "app" / "myinventory"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_flag_keeps_web_fallback():
    g = _read(APP / "build.gradle.kts")
    assert 'buildConfigField("boolean", "NATIVE_SETTINGS", "true")' in g
    home = _read(KT / "HomeActivity.kt")
    assert 'item.key == "settings" && BuildConfig.NATIVE_SETTINGS' in home and "else openWeb(item.href)" in home


def test_activity_registered_not_exported():
    m = _read(APP / "src" / "main" / "AndroidManifest.xml")
    block = m[m.index('android:name=".SettingsActivity"'):]
    assert 'android:exported="false"' in block[: block.index("/>")]


def test_salary_is_never_saved_or_logged():
    src = _read(KT / "SettingsActivity.kt")
    assert "Log." not in src and "println" not in src
    assert "putString" not in src and "getSharedPreferences" not in src and "HomeCache(this).write" not in src
    salary = src[src.index("private fun SalaryPage"):src.index("// ---------- actions")]
    assert "rememberSaveable" not in salary
    assert "LifecycleEventEffect(Lifecycle.Event.ON_STOP)" in salary and "shown = null" in salary


def test_logout_unregisters_push_before_ending_session():
    src = _read(KT / "SettingsActivity.kt")
    body = src[src.index("private fun logoutRemote"):src.index("private fun finishLogout")]
    assert body.index("/api/push/unregister") < body.index("forgetRegistration") < body.index("/api/auth/logout")
    fin = src[src.index("private fun finishLogout"):src.index("private fun goToLogin")]
    assert "HomeCache(this).clear()" in fin and "NativeSession.clearLocal()" in fin


def test_salary_row_never_tells_if_one_is_saved():
    src = _read(KT / "SettingsActivity.kt")
    assert "ثبت نشده" not in src and "hasSalary" not in src
    assert "hasSalary" not in _read(KT / "settings" / "SettingsModel.kt")


def test_no_recovery_code_row():
    assert "کد بازیابی" not in _read(KT / "SettingsActivity.kt")


def test_compose_sources_have_no_handoff_notes():
    for f in (KT / "ui").rglob("*.kt"):
        text = _read(f)
        assert "DESIGN HANDOFF" not in text and "TODO()" not in text and not re.search(r"#\d{2,3}(?![0-9A-Za-z])", text), f.name
