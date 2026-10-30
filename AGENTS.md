# AGENTS.md

## Commands
```bash
source ~/pp/my-inventory-speed/.venv/bin/activate   # or: pip install -r requirements-dev.txt
PYTHONPATH=$PWD pytest -n auto                       # full suite, must finish in ≤ 1 min
PYTHONPATH=$PWD pytest --testmon                     # only tests affected by your change
PYTHONPATH=$PWD pytest tests/test_assets_v2.py -q    # one file
scripts/build-android-apk.sh                         # Android APK (Docker) -> app/static/my-inventory.apk
```

## Stack
- Python 3.12, FastAPI, SQLAlchemy, Jinja2, vanilla JS, Chart.js. SQLite + alembic (`app/migrations/versions/`, runs `upgrade head` on startup).
- Single uvicorn worker (in-process hourly scheduler). Deploys automatically on merge to `main`.
- Android WebView app in `android/` (Kotlin), package `app.myinventory`.

## Layout
- `app/` routes and logic · `app/templates/` Jinja · `app/static/` JS/CSS, `sw.js`, `offline.html`
- `app/config.py` settings, `STATIC_ASSET_VERSION` · `app/android_release.json` published APK version
- `tests/` pytest (`tests/js/` JS tests) · `scripts/` build and seed tools

## Code style
- Follow the surrounding code; small functions, no new dependencies without need.
- UI is Persian and RTL, font Vazirmatn, amounts in Toman, Jalali dates, Persian digits for display.
- Tap targets ≥ 44×44 px; never truncate asset names or quantities.
- Comments say *why*, briefly. No names, PR numbers, review notes or dates in code.
- Every change ships with a test.

## Always
- Bump `STATIC_ASSET_VERSION` in `app/config.py` when any file in `app/static/` or `sw.js` changes.
- Add an alembic migration that carries existing data for any schema or data change.
- Mark every on-screen amount with `data-mask="portfolio"` (shown only under `html[data-show-portfolio="1"]`).
- Keep `<meta name="x-offline" content="1">` in `app/static/offline.html`.
- Work on a branch and open a PR; update it by merging `main` in.
- Run the full suite before pushing and report only real results.

## Ask first
- Any migration or data change on production (back up the DB first).
- Changes to cookies, auth, the service worker or the Android update flow.
- Anything you are not sure about.

## Never
- Push or merge to `main`, rebase, or force-push.
- Break existing data, sessions or installed Android versions.
- Commit secrets, keystores, `keystore.properties` or `google-services.json`.
- Use real user data in screenshots or fixtures (use `scripts/seed_demo.py`).
- Enable navigation preload in `sw.js`.
- Change the value of cookie `inventory_signed_in` (must stay `1`); use `inventory_page_key` for per-user caching; keep `inventory_session` as the session cookie.
- Rename the localStorage key `privacy-portfolio`.
- Change the package id `app.myinventory`, the APK filename or its URL, or publish a debug-signed APK.
