"""Brand guard: no old or non-daraiito name in user-visible copy or strings (web + Android).

Identifiers that must keep their old names are allow-listed below and stripped before the scan.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "android/app/src/main"

OLD_BRANDS = re.compile(
    r"موجودی\s*من|مای\s*اینونتوری|(?i:my[\s_-]?inventory)|(?i:vahidtwo)|(?i:personal[\s_-]?portfolio)"
)

# Kept on purpose: package id, APK file name/URL, localStorage key, cookies, old-host fallback, internal
# class/theme names. None of these is shown to users as a name.
ALLOWED = [
    r"app\.myinventory",
    r"app/myinventory",
    r"my-inventory(?:-\$\{[^}]+\})?\.apk(?:\.part|\.sha256)?",
    r"privacy-portfolio",
    r"portfolio\.vahidtwo\.ir",
    r"Theme[._]MyInventory[\w.]*",
    r"InventoryMessagingService",
]
_ALLOWED_RE = re.compile("|".join(ALLOWED))


def _files():
    yield from (ROOT / "app/templates").rglob("*.html")
    for ext in ("*.html", "*.js", "*.webmanifest"):
        yield from (ROOT / "app/static").glob(ext)
    yield from (SRC / "res").rglob("*.xml")
    yield from (SRC / "assets/www").rglob("*.html")
    yield SRC / "AndroidManifest.xml"


_PY_STR = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'")
_KT_STR = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"")


def _string_literals():
    for p in (ROOT / "app").glob("*.py"):
        for m in _PY_STR.finditer(p.read_text(encoding="utf-8")):
            yield p, m.group(0)
    for p in (SRC / "java").rglob("*.kt"):
        for m in _KT_STR.finditer(p.read_text(encoding="utf-8")):
            yield p, m.group(0)


def _hits(text):
    return OLD_BRANDS.findall(_ALLOWED_RE.sub("", text))


def test_guard_catches_old_names_and_spares_identifiers():
    for bad in ("موجودی من", "My Inventory", "my-inventory/1.0", "MyInventory", "vahidtwo", "personal-portfolio"):
        assert _hits(bad), bad
    for ok in ("app.myinventory", "/download/my-inventory.apk", "privacy-portfolio", "https://portfolio.vahidtwo.ir",
               "Theme.MyInventory.Starting", "inventory_signed_in", "دارایی‌تو", "daraiito"):
        assert not _hits(ok), ok


@pytest.mark.parametrize("path", sorted(_files()), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_old_brand_in_visible_copy(path):
    assert not _hits(path.read_text(encoding="utf-8")), path


def test_no_old_brand_in_code_string_literals():
    bad = [(str(p.relative_to(ROOT)), s) for p, s in _string_literals() if _hits(s)]
    assert not bad, bad


def test_android_app_name_and_only_domain():
    strings = (SRC / "res/values/strings.xml").read_text(encoding="utf-8")
    assert '<string name="app_name">دارایی\u200cتو</string>' in strings
    hosts = set(re.findall(r"https?://([a-z0-9.-]+)", strings + (ROOT / "app/static/manifest.webmanifest").read_text()))
    assert hosts <= {"daraiito.ir"}
