"""Landing screenshots: every file in the manifest exists, stays under the size cap, and the generator signs in via /auth."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "app" / "static" / "landing"


def test_manifest_files_exist_and_fit_budget():
    m = json.loads((LANDING / "manifest.json").read_text(encoding="utf-8"))
    names = {f["file"] for f in m["files"]}
    assert len(names) == 10
    for f in m["files"]:
        p = LANDING / f["file"]
        assert p.exists() and p.stat().st_size == f["bytes"] <= 150 * 1024, f["file"]
    assert {p.name for p in LANDING.glob("*.webp")} == names


def test_landing_page_references_only_existing_images(client):
    import re
    html = client.get("/").text
    for rel in set(re.findall(r"/static/landing/([\w.-]+\.webp)", html)):
        assert (LANDING / rel).exists(), rel


def test_generator_uses_unified_auth_and_spending_v2_selectors():
    src = (ROOT / "scripts" / "landing_shots.py").read_text(encoding="utf-8")
    assert '"/auth/continue"' in src and 'post("/login"' not in src
    assert "data-sp-open-form" in src and "#sp-amount_toman" in src
