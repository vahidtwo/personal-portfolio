"""Landing screenshots: every file in the manifest exists, stays under the size cap, and the generator signs in via /auth."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "app" / "static" / "landing"


def test_manifest_files_exist_and_fit_budget():
    m = json.loads((LANDING / "manifest.json").read_text(encoding="utf-8"))
    names = {f["file"] for f in m["files"]}
    assert len(names) == 6
    for f in m["files"]:
        p = LANDING / f["file"]
        assert p.exists() and p.stat().st_size == f["bytes"] <= 150 * 1024, f["file"]
    assert {p.name for p in LANDING.glob("*.webp")} == names
    assert re.fullmatch(r"[0-9a-f]{40}", m["git_sha"]), "git_sha must be a commit SHA, not a label"


def test_every_shipped_landing_image_is_used_by_the_template():
    tpl = (ROOT / "app" / "templates" / "landing.html").read_text(encoding="utf-8")
    for p in LANDING.glob("*.webp"):
        assert p.name in tpl, f"{p.name} is shipped but not referenced"


def test_landing_page_references_only_existing_images(client):
    import re
    html = client.get("/").text
    for rel in set(re.findall(r"/static/landing/([\w.-]+\.webp)", html)):
        assert (LANDING / rel).exists(), rel


def test_generator_uses_unified_auth_and_spending_v2_selectors():
    src = (ROOT / "scripts" / "landing_shots.py").read_text(encoding="utf-8")
    assert '"/auth/continue"' in src and 'post("/login"' not in src
    assert "data-sp-open-form" in src and "#sp-amount_toman" in src
