# Daraiito

**Self-hosted personal portfolio tracker for Iran — values in Toman, Persian UI, live market prices.**

Track gold, silver, crypto, USD, cash, and car value (via [Sanjeh](https://sanjeh.app/)) in one dashboard. Prices come from [chande.net](https://chande.net/); history is stored as hourly snapshots so you can chart portfolio value over time.

> UI language: **Persian (RTL)** · App title in the interface: **دارایی‌تو**

---

## Features

- **Multi-user** registration and login (username + password, bcrypt, session cookies, CSRF)
- **Holdings**: 18k gold (grams), Emami / Bahar Azadi / half / quarter / gram coins (count), silver (grams), BTC, ADA, ETH, SOL, DOGE, MATIC, USD, Toman cash, and cars linked through Sanjeh
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
| `SECRET_KEY` | *(required)* | Session signing key. The server refuses to start if it is empty or a placeholder |
| `DATA_DIR` | `./data` | SQLite DB and optional auto-generated secret |
| `HTTPS_ONLY` | `0` | Set `1` when users reach the site over HTTPS (required behind Cloudflare + secure cookies) |
| `CHANDE_URL` | chande.net current prices API | Override only if the endpoint changes |
| `ARZBAN_PRICES_URL` | fm5.ir `/api/v1/prices` | Backup when Chande fails (Arzban public API) |
| `PRICE_REFRESH_HOURS` | `1` | In-app scheduler interval for prices + snapshots |
| `PRICE_MANUAL_REFRESH_MINUTES` | `5` | Minimum time between dashboard price refreshes |
| `ENABLE_INTERNAL_SCHEDULER` | `1` | Set `0` if you run `scripts/create_snapshot.py` via cron instead |
| `ADMIN_USERNAMES` | *(empty)* | Comma-separated usernames that can open `/admin` (user list + market prices) |
| `FIREBASE_*` (client) | *(empty)* | Web push: `FIREBASE_API_KEY`, `AUTH_DOMAIN`, `PROJECT_ID`, `MESSAGING_SENDER_ID`, `APP_ID`, `VAPID_KEY` |
| `FIREBASE_CLIENT_EMAIL` | *(empty)* | **Server only** — FCM Admin service account email |
| `FIREBASE_PRIVATE_KEY` | *(empty)* | **Server only** — PEM on one line; use `\n` for newlines |
| `FIREBASE_PRIVATE_KEY_ID` | *(empty)* | Optional service account key id |

Validate Admin credentials: `python scripts/test_firebase_admin.py` (FCM dry-run, no message delivered).

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

## Deleting users & restoring one from backup

Admins delete users from **/admin** (tick users → «حذف انتخاب‌شده‌ها…», or «حذف…» on one row).
The confirm screen lists every selected user with row counts per table and the backup file
name; you must type the number of users. On submit the app, under one SQLite write lock
(`BEGIN IMMEDIATE`): recounts (aborts if anything changed), checks free disk (≥ 2× DB size),
takes an online backup to `$DATA_DIR/backups/predelete-<UTC>-<rand>.db` (dir 0700, file 0600,
integrity-checked), deletes the users and all their rows, writes `admin_audit_log`, commits.
Any failure rolls back everything. Self and `ADMIN_USERNAMES` can never be deleted.
Backups older than 30 days are pruned, but the newest 10 are always kept.

Restore ONE user (all rows, original ids) from such a backup:

```bash
# take a fresh backup of the live DB first, then:
docker exec -it <container> python scripts/restore_user.py \
    /app/data/backups/predelete-20261013-111500-1a2b3c4d.db <user_id> --dry-run
docker exec -it <container> python scripts/restore_user.py \
    /app/data/backups/predelete-20261013-111500-1a2b3c4d.db <user_id>
```

It refuses if the user id or username already exists, copies categories parents-first and
then every table with a `user_id` column (holdings, snapshots, debts, expenses, spends,
push tokens, monthly_incomes, …) in one transaction, and checks foreign keys/integrity
before committing. The audit log (`admin_audit_log`) records who deleted whom, the row
counts and the backup filename.

## Production notes

- Run **one** uvicorn worker (`--workers 1` in the Dockerfile) so the hourly job does not run twice.
- Mount a persistent volume on `DATA_DIR`.
- Set a strong `SECRET_KEY` and `HTTPS_ONLY=1` when served over TLS.
- Behind **Cloudflare**, use SSL/TLS mode **Full (strict)** (origin also serves HTTPS). The Docker image enables uvicorn `--proxy-headers` so `X-Forwarded-Proto` is honored. Avoid **Flexible** (visitor HTTPS, origin HTTP) with `HTTPS_ONLY=1`, or session cookies may not stick.
- **Trusted proxy:** uvicorn trusts `X-Forwarded-*` only from `FORWARDED_ALLOW_IPS` (Dockerfile default `*`, the old behaviour). On Dokploy set it to Traefik's network, e.g. the subnet from `docker network inspect dokploy-network` (`172.x.0.0/16`), then redeploy and check that logins still work and `request.client` shows visitor IPs.
- **Login limits (12.0.2):** failed logins are counted per IP and per username+IP for `/auth/continue`, `/login` and `/api/auth/continue`, in `DATA_DIR/rate_limit.sqlite` (separate from the app database; survives restarts). Limits: 10 per username+IP and 30 per IP in 15 minutes; each repeat lockout doubles (15 min, 30, 60 ... max 24 h). A successful login clears both counts. Locked requests get 429 with a Persian message and `Retry-After`. The client IP is `request.client.host`; `ar-real-ip` / `CF-Connecting-IP` are trusted only when that peer is in ArvanCloud's / Cloudflare's published ranges (lists in `app/rate_limit.py`). X-Forwarded-For is never read by the app.
- **Tests:** `scripts/test-all.sh` runs the web suite (pytest-xdist) and both Android flavors' unit tests in parallel with a warm Gradle daemon.
- **Rate limits** (sign-in: 10 failures per username+IP and 30 per IP in 15 min; sign-up: 5 per IP per hour) are kept **in memory** (`app/rate_limit.py`). To reset them, for example after locking yourself out, restart the app container (Dokploy → Restart). A restart also resets them for everyone, so expect the counts to start over. When a limit is hit, the sign-in page shows the wait in minutes and sends a `Retry-After` header (seconds); the figure is computed from the same in-memory counters, so it also resets on restart.
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

[Beerware](LICENSE) (Revision 42). Keep the notice, do what you want with the code, and buy vahidtwo a beer if you meet and think it was worth it.
