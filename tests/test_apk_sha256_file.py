"""app/static/my-inventory.apk.sha256 (linked from the landing footer) must match the committed APK."""
import hashlib
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_apk_sha256_file_matches_apk():
    line = (STATIC / "my-inventory.apk.sha256").read_text(encoding="utf-8").strip()
    digest, name = line.split()
    assert name == "my-inventory.apk"
    assert digest == hashlib.sha256((STATIC / "my-inventory.apk").read_bytes()).hexdigest()


def test_apk_sha256_file_is_served(client):
    r = client.get("/static/my-inventory.apk.sha256")
    assert r.status_code == 200 and r.text.split()[0] == hashlib.sha256((STATIC / "my-inventory.apk").read_bytes()).hexdigest()
