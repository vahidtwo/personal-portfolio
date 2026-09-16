# Toman Portfolio

**Self-hosted personal portfolio tracker for Iran — values in Toman, Persian UI, live market prices.**

Track gold, silver, crypto, USD, cash, and car value (via [Sanjeh](https://sanjeh.app/)) in one dashboard. Prices come from [chande.net](https://chande.net/); history is stored as hourly snapshots so you can chart portfolio value over time.

> UI language: **Persian (RTL)** · App title in the interface: **موجودی من**

---

## Features

- **Multi-user** registration and login (username + password, bcrypt, session cookies, CSRF)
- **Holdings**: 18k gold (grams), silver (grams), BTC, ADA, ETH, SOL, DOGE, MATIC, USD, Toman cash, and cars linked through Sanjeh
- **Market prices** from chande.net (silver normalized from troy ounce to per gram)
- **Sanjeh integration**: optional API token on your profile to pull car portfolio value from Khodro45
- **Dashboard**: total value, sortable asset table, Chart.js timeline (total + per-asset), zoom, range select, fullscreen
- **Snapshots**: automatic hourly price refresh + portfolio snapshots; manual refresh on the dashboard (5-minute cooldown)
- **Themes**: dark / light
- **Admin dashboard** (`/admin`): all users, portfolio values per asset, snapshot counts, stored market prices (env `ADMIN_USERNAMES`)
- **Deploy-friendly**: Docker, SQLite on a volume, health check, single-worker uvicorn (safe for in-process scheduler)

---

## Stack

| Layer | Choice |
|--------|--------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, httpx |
| Data | SQLite (`DATA_DIR/inventory.db`) |
| Frontend | Jinja2 templates, vanilla JS, Chart.js + zoom plugin |
| Dates | Jalali labels on charts (`jdatetime`) |

---

## Quick start (Docker)

```bash
git clone https://github.com/YOUR_USER/toman-portfolio.git
cd toman-portfolio
cp .env.example .env
# Edit .env — set SECRET_KEY to a long random string
docker compose up -d --build
```

Open **http://localhost:8000** → register → set holdings on **Profile** → view **Dashboard**.

Data persists in the `inventory-data` Docker volume (`/app/data` inside the container).

---

## Local development

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
export SECRET_KEY=dev-secret-change-me
export DATA_DIR=./data
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(generated in `DATA_DIR` if empty)* | Session signing key — **set in production** |
| `DATA_DIR` | `./data` | SQLite DB and optional auto-generated secret |
| `HTTPS_ONLY` | `0` | Set `1` behind HTTPS (secure cookies) |
| `CHANDE_URL` | chande.net current prices API | Override only if the endpoint changes |
| `PRICE_REFRESH_HOURS` | `1` | In-app scheduler interval for prices + snapshots |
| `PRICE_MANUAL_REFRESH_MINUTES` | `5` | Minimum time between dashboard price refreshes |
| `ENABLE_INTERNAL_SCHEDULER` | `1` | Set `0` if you run `scripts/create_snapshot.py` via cron instead |
| `ADMIN_USERNAMES` | *(empty)* | Comma-separated usernames that can open `/admin` (user list + market prices) |

---

## Manual / cron jobs

Inside the container or with `DATA_DIR` pointing at your data directory:

```bash
# Fetch prices, refresh Sanjeh cars, snapshot all users (same as hourly job)
python scripts/create_snapshot.py

# Only update market prices
python scripts/create_snapshot.py --fetch-only

# Snapshot using prices already in the database
python scripts/create_snapshot.py --skip-fetch
```

If `ENABLE_INTERNAL_SCHEDULER=0`, use cron or a sidecar (see commented service in `docker-compose.yml`).

---

## Sanjeh (car value)

1. Complete your profile on [sanjeh.app](https://sanjeh.app/).
2. Copy your API token into **Profile** in this app.
3. Car total uses Khodro45 portfolio API (`latest_price_sum.price` in Toman).

Tokens are stored **per user in your database**. Treat them like passwords; rotate if leaked.

---

## Production notes

- Run **one** uvicorn worker (`--workers 1` in the Dockerfile) so the hourly job does not run twice.
- Mount a persistent volume on `DATA_DIR`.
- Set a strong `SECRET_KEY` and `HTTPS_ONLY=1` when served over TLS.
- This project is aimed at **self-hosting** for you and people you trust. Open registration is convenient for a private instance; for a public internet deployment, consider restricting signups or adding extra hardening.

Works well on [Dokploy](https://dokploy.com/) or any Docker host: build from repo, map port 8000, attach env + volume.

---

## Project layout

```
app/           FastAPI app, models, chande/sanjeh clients, scheduler
app/static/    CSS, dashboard chart, table sort, theme
app/templates/ Persian HTML pages
scripts/       create_snapshot.py CLI
data/          SQLite (gitignored; created at runtime)
```

---

## Data sources & attribution

- Market quotes: [chande.net](https://chande.net/)
- Car portfolio: [Sanjeh](https://sanjeh.app/) / Khodro45 API (user-provided token)

This app is not affiliated with chande.net or Sanjeh.

---

## License

Add a `LICENSE` file before publishing if you want others to reuse the code (e.g. MIT). Until then, all rights reserved by the repository owner.

---

## Suggested GitHub repository names

If you rename from `my-inventory`, these fit the project:

| Name | Notes |
|------|--------|
| **`toman-portfolio`** | Clear, searchable, matches this README title |
| **`mojoodi`** | Short; aligns with UI brand «موجودی من» |
| **`iran-portfolio-tracker`** | Descriptive for English search |
| **`porrfolio-tehran`** | Avoid — typo |

Recommended: **`toman-portfolio`** for GitHub; keep **موجودی من** as the product name in the UI.
