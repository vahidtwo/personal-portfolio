# AGENTS.md — daraiito (my-inventory)

Self-hosted portfolio tracker for Iran. Brand: **daraiito** (UI title «دارایی‌تو»). Live at `daraiito.ir` (old host `portfolio.vahidtwo.ir` still served).

## Stack
- Python 3.12, FastAPI, SQLAlchemy, httpx, Jinja2 templates, vanilla JS, Chart.js (`app/static/vendor/`).
- SQLite at `DATA_DIR/inventory.db`; schema via alembic (`alembic.ini`, `app/migrations/versions/`). `app/db.py` runs `alembic upgrade head` on startup.
- Docker (`Dockerfile`, `docker-compose.yml`), single uvicorn worker (the in-process hourly scheduler must not run twice). Health check: `/health`.
- Deploy: Dokploy + Traefik, automatic on merge to `main`.
- Android WebView app in `android/` (Kotlin, Gradle KTS).

## Layout
- `app/` — routes and logic (`main.py`, `web.py`, `auth_routes.py`, `dashboard.py`, `pwa.py`, `session_marker.py`, `config.py`, …).
- `app/templates/` — Jinja pages and `partials/`.
- `app/static/` — JS/CSS, `sw.js`, `offline.html`, fonts, icons, `my-inventory.apk` (+ `.sha256`).
- `app/android_release.json` — published APK version, notes, cert SHA-256.
- `app/migrations/` — alembic env and versions.
- `tests/` — pytest suite (`tests/js/` for JS tests).
- `scripts/` — APK build, demo seed, landing screenshots, snapshot/restore tools.
- `tools/qa_update_server.py` — local QA update server.

## Tests
```bash
source ~/pp/my-inventory-speed/.venv/bin/activate   # deps: requirements-dev.txt
PYTHONPATH=$PWD pytest -n auto                       # pytest.ini already adds -n auto
PYTHONPATH=$PWD pytest --testmon                     # fast loop: only affected tests
```
- Full suite must finish in **≤ 1 minute**. Keep tests fast; each test uses its own SQLite under `tmp_path`.
- Never claim tests passed unless you ran them and they passed.
- New behaviour needs a test.

## Android
- Package id `app.myinventory` — never change.
- Build: `scripts/build-android-apk.sh` (Docker). Output **must stay** `app/static/my-inventory.apk`; keep the filename and download URL.
- Release key lives outside the repo (`$MY_INVENTORY_RELEASE_DIR`, default `~/.my-inventory-release`), passed as BuildKit secrets. Without it the APK gets a debug key — never publish that.
- Release cert SHA-256 is in `app/android_release.json` (`cert_sha256`); bump `versionCode`/`versionName`/`notes` there with each release and update `my-inventory.apk.sha256`.
- Never commit `google-services.json`, keystores, or `keystore.properties` (already gitignored).

## Static assets and service worker
- Bump `STATIC_ASSET_VERSION` in `app/config.py` on **every** change to static files or `sw.js`. It is the SW cache name and the `static_v` query string.
- No navigation preload in `sw.js`. It makes the Android WebView report a main-frame error offline.
- `offline.html` must keep `<meta name="x-offline" content="1">`. The app uses it to tell the offline page from a real page.

## Cookies (do not change semantics)
- `inventory_session` — session cookie (`SESSION_COOKIE_NAME`), can be anonymous.
- `inventory_signed_in` — marker, value must stay exactly `1`. The native SMS sender checks it.
- `inventory_page_key` — per-user page cache key. Use this, not the marker, for cache separation.

## Privacy masking
- Hidden amounts use `data-mask="portfolio"`. They show only under `html[data-show-portfolio="1"]` (`style.css`).
- State lives in localStorage key `privacy-portfolio` (`base.html`, `partials/hide_handoff.html`). Never rename it.
- `#hide=1` hash hands off the hidden state. Any new amount on screen must carry `data-mask="portfolio"`.

## UI
- Persian, RTL, font Vazirmatn. Persian digits for display; Jalali dates (`jdatetime`); amounts in Toman.
- Tap targets at least 44×44 px. Do not truncate asset names or quantities.

## Rules
- Every change goes through a PR. Never push or merge to `main` directly.
- Update branches by merging `main` in. No rebase, no force-push.
- Any schema or data change needs an alembic migration that migrates existing data.
- Nothing may break existing data, sessions, or features (web or installed Android versions).
- Back up the prod DB before any migration or data change. No prod commands without explicit owner approval.
- Never commit secrets, credentials, or real user data. Screenshots use fake data only (`scripts/seed_demo.py`).
- Ask the owner when less than 95% sure.

## Code style
- Comments explain *why*, briefly. No names of people or agents, no PR numbers, review history, or dates in comments — put those in the PR description.
