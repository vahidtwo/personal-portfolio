"""Regenerate the landing page screenshots from a FAKE demo account (spec /workspace/mockups/landing-shots/spec.md).

Run on every release that changes a pictured screen:
    pip install playwright pillow && python -m playwright install chromium   # once
    python scripts/landing_shots.py            # writes app/static/landing/*.webp + manifest.json
Options: --chrome /usr/bin/google-chrome  --raw-dir DIR (also keep the PNG captures)  --out DIR

Safety: a fresh temporary SQLite under mktemp, the hourly price job off, no network, a fixed clock
(2026-10-20 12:00 Tehran). Never touches data/inventory.db or the live site. The demo password is random
per run (or DEMO_PASSWORD), never stored.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 150 * 1024
BG = {"dark": (5, 6, 8), "light": (238, 241, 248)}
FROZEN_ISO = "2026-10-20T08:30:00Z"


# ---------------------------------------------------------------- server (child process, frozen clock)
def serve(port: int) -> None:
    sys.path.insert(0, str(ROOT))
    from datetime import datetime, timezone

    frozen = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)
    import app.formatting as fmt
    import app.models as models

    fmt._utcnow = lambda: frozen
    models.utcnow = lambda: frozen
    import app.main as main  # noqa: E402

    for name, mod in list(sys.modules.items()):
        if name.startswith("app.") and getattr(mod, "utcnow", None) is not None and name != "app.models":
            setattr(mod, "utcnow", lambda: frozen)

    async def _noop(*a, **k):
        return None

    main.run_hourly_job = _noop
    import app.profile as profile

    profile.refresh_prices_and_snapshot_user = _noop
    import uvicorn

    uvicorn.run(main.app, host="127.0.0.1", port=port, log_level="warning")


# ---------------------------------------------------------------- image helpers
def _rounded(img, radius):
    from PIL import Image, ImageDraw

    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def phone_frame(shot, scale=2):
    """Simple rounded device frame (no brand), 36px outer radius at 1x."""
    from PIL import Image, ImageDraw

    bezel = 10 * scale
    w, h = shot.size[0] + 2 * bezel, shot.size[1] + 2 * bezel
    frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rounded_rectangle((0, 0, w - 1, h - 1), 36 * scale, fill=(22, 25, 34, 255))
    frame.alpha_composite(_rounded(shot, 27 * scale), (bezel, bezel))
    return frame


def shadowed(canvas, img, xy, blur=24, alpha=150):
    from PIL import Image, ImageFilter

    pad = blur * 3
    sh = Image.new("RGBA", (img.size[0] + 2 * pad, img.size[1] + 2 * pad), (0, 0, 0, 0))
    a = img.split()[-1].point(lambda v: alpha if v else 0)
    sh.paste((0, 0, 0, 255), (pad, pad + blur // 2), a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(sh, (xy[0] - pad, xy[1] - pad))
    canvas.alpha_composite(img, xy)


def webp_bytes(img, max_bytes=MAX_BYTES):
    for q in (78, 74, 70, 64, 58):
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=q, method=6)
        if buf.tell() <= max_bytes:
            return buf.getvalue(), q
    raise SystemExit(f"cannot fit {img.size} under {max_bytes} bytes")


# ---------------------------------------------------------------- capture
HIDE_USER_JS = """(u)=>{const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
while((n=w.nextNode())){if(n.nodeValue.includes(u))n.nodeValue=n.nodeValue.split(u).join('');}
document.querySelectorAll('[aria-label*="'+u+'"],[title*="'+u+'"]').forEach(e=>{e.removeAttribute('title');e.setAttribute('aria-label','');});
return document.documentElement.outerHTML.includes(u);}"""


def capture(base, password, chrome, raw_dir):
    import httpx
    from PIL import Image
    from playwright.sync_api import sync_playwright

    shots = {}
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch()
        for theme in ("dark", "light"):
            def ctx(w, h, dpr):
                c = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, color_scheme=theme,
                                   locale="fa-IR", timezone_id="Asia/Tehran")
                c.add_init_script(f"localStorage.setItem('inventory-theme','{theme}')")
                hc = httpx.Client(base_url=base)
                import re as _re
                t = _re.search(r'name="csrf" value="([^"]+)"', hc.get("/auth").text).group(1)
                r = hc.post("/auth/continue", data={"username": "demo_nemoone", "password": password, "csrf": t})
                assert r.status_code in (200, 303) and "/dashboard" in str(r.url) or r.status_code == 303, "demo login failed"
                c.add_cookies([{"name": k, "value": v, "url": base} for k, v in hc.cookies.items()])
                pg = c.new_page()
                pg.clock.set_fixed_time(FROZEN_ISO)
                return c, pg

            def load(pg, path):
                pg.goto(base + path, wait_until="networkidle")
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(500)
                leaked = pg.evaluate(HIDE_USER_JS, "demo_nemoone")
                assert not leaked, "demo username still in the page"

            def grab(pg, **kw):
                return Image.open(io.BytesIO(pg.screenshot(**kw))).convert("RGB")

            # slot 1: desktop dashboard, first viewport
            c, pg = ctx(1280, 800, 1)
            load(pg, "/dashboard")
            shots[("desktop", theme)] = grab(pg)
            # slot 3: chart card, range «سال»
            pg.click('#chart-range [data-range="365"]')
            pg.wait_for_timeout(700)
            shots[("chart", theme)] = Image.open(io.BytesIO(pg.locator(".dash-chart").screenshot())).convert("RGB")
            c.close()
            # slot 2: phone dashboard, first viewport incl. bottom nav
            c, pg = ctx(390, 844, 2)
            load(pg, "/dashboard")
            shots[("phone", theme)] = grab(pg)
            # slot 4: add-spend form, pre-filled (not saved) + the first recent spends
            load(pg, "/dashboard?tab=daily")
            pg.fill('#daily-spend-form input[name="amount_toman"]', "350000")
            pg.evaluate("""()=>{const f=document.getElementById('daily-spend-form');
              const s=[...f.querySelectorAll('select')];const p=s[0];if(p){const o=[...p.options].find(o=>o.textContent.trim()==='خوراک');
              if(o){p.value=o.value;p.dispatchEvent(new Event('change',{bubbles:true}));}}}""")
            pg.fill('#daily-spend-form input[name="note"]', "ناهار")
            pg.locator("#daily-spend-form input[name=note]").blur()
            top = pg.evaluate("document.querySelector('.daily-add').getBoundingClientRect().top + scrollY")
            pg.evaluate(f"scrollTo(0,{max(0, top - 76)})")
            pg.wait_for_timeout(300)
            shots[("spend", theme)] = grab(pg)
            c.close()
        br.close()
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)
        for (slot, theme), img in shots.items():
            img.save(raw_dir / f"{slot}-{theme}.png")
    return shots


def build(shots, out: Path):
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.webp"):
        old.unlink()
    files, slots = [], {}

    def save(img, name, slot=None, theme=None):
        data, q = webp_bytes(img)
        (out / name).write_bytes(data)
        files.append({"file": name, "slot": slot, "theme": theme, "width": img.size[0], "height": img.size[1],
                      "bytes": len(data), "quality": q})
        if slot:
            slots.setdefault(slot, {}).setdefault(theme, []).append({"file": name, "w": img.size[0], "h": img.size[1]})

    def sized(img, w):
        return img.resize((w, round(img.size[1] * w / img.size[0])), Image.LANCZOS)

    for theme in ("dark", "light"):
        desk, phone = shots[("desktop", theme)], shots[("phone", theme)]
        framed = phone_frame(phone)  # 2x
        # hero composite 3:2: desktop with the framed phone over its bottom-left (RTL inline-start) corner
        W, H, m = 1680, 1120, 40
        D = 1400
        canvas = Image.new("RGBA", (W, H), BG[theme] + (255,))
        d = _rounded(sized(desk, D), 16 * D // 1280)
        shadowed(canvas, d, (W - m - D, m))
        pw = int(D * 0.34)
        ph_img = sized(framed, pw)
        shadowed(canvas, ph_img, (m, H - m - ph_img.size[1]))
        hero = canvas.convert("RGB")
        for w in (1680, 1120):
            save(sized(hero, w), f"hero-{theme}-{w}.webp")
        # phone-only hero, 360 × 779 / 720 × 1558
        ph = Image.new("RGBA", framed.size, BG[theme] + (255,))
        ph.alpha_composite(framed)
        ph = ph.convert("RGB").resize((720, 1558), Image.LANCZOS)
        for w in (720, 360):
            save(sized(ph, w), f"hero-phone-{theme}-{w}.webp")
        # slot 1 desktop, slot 2 phone, slot 3 chart, slot 4 spend
        for w in (1280, 640):
            save(sized(desk, w), f"dashboard-desktop-{theme}-{w}.webp", "desktop", theme)
        for w in (780, 390):
            pf = Image.new("RGBA", framed.size, BG[theme] + (255,)); pf.alpha_composite(framed)
            save(sized(pf.convert("RGB"), w), f"dashboard-phone-{theme}-{w}.webp", "phone", theme)
        chart = shots[("chart", theme)]
        for w in (chart.size[0], chart.size[0] // 2):
            save(sized(chart, w), f"chart-{theme}-{w}.webp", "chart", theme)
        sf = phone_frame(shots[("spend", theme)])
        sp = Image.new("RGBA", sf.size, BG[theme] + (255,)); sp.alpha_composite(sf)
        for w in (780, 390):
            save(sized(sp.convert("RGB"), w), f"spend-phone-{theme}-{w}.webp", "spend-phone", theme)
    for s in slots.values():  # largest first; the template uses [0] for width/height
        for lst in s.values():
            lst.sort(key=lambda f: -f["w"])
    sha = os.environ.get("GIT_SHA") or subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                                      capture_output=True, text=True).stdout.strip()
    from seed_demo import EXPECTED_NET, EXPECTED_TOTAL, SPENDS  # noqa: E402

    dataset = hashlib.sha256(json.dumps([EXPECTED_TOTAL, EXPECTED_NET, SPENDS], ensure_ascii=False).encode()).hexdigest()
    manifest = {"git_sha": sha, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "frozen_clock": FROZEN_ISO, "dataset_sha256": dataset, "net_worth_toman": EXPECTED_NET,
                "files": files, "slots": slots}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    ap.add_argument("--raw-dir", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "app" / "static" / "landing")
    args = ap.parse_args()
    if args.serve:
        serve(args.serve)
        return
    if any(os.environ.get(k) for k in ("PROD", "DOKPLOY", "DOKPLOY_APP_NAME")):
        sys.exit("refusing: PROD/DOKPLOY environment")
    tmp = Path(tempfile.mkdtemp(prefix="landing-shots-"))
    env = dict(os.environ, DATA_DIR=str(tmp), DATABASE_URL=f"sqlite:///{tmp}/demo.db", ENABLE_INTERNAL_SCHEDULER="0",
               SECRET_KEY=secrets.token_hex(16), HTTPS_ONLY="0",
               DEMO_PASSWORD=os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(18),
               PYTHONPATH=str(ROOT), TMPDIR=str(tmp.parent))
    server = None
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_demo.py")], env=env, check=True)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        server = subprocess.Popen([sys.executable, __file__, "--serve", str(port)], env=env)
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.5)
        shots = capture(base, env["DEMO_PASSWORD"], args.chrome, args.raw_dir)
        sys.path.insert(0, str(ROOT / "scripts"))
        manifest = build(shots, args.out)
        big = [f for f in manifest["files"] if f["bytes"] > MAX_BYTES]
        assert not big, big
        print(json.dumps({"files": len(manifest["files"]), "max_bytes": max(f["bytes"] for f in manifest["files"]),
                          "out": str(args.out)}))
    finally:
        if server:
            server.terminate()
            server.wait(10)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
