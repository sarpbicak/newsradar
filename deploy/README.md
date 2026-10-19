# Docker deployment (API)

Target: the API at `api.newsradarapp.com`, served by Docker on an ARM (t4g) EC2 instance. The frontend (`newsradarapp.com`, with `www` redirecting to it) is a static build on CloudFront and is not part of this stack.

```
internet ──80/443──▶ caddy (172.28.0.10) ──8000──▶ backend (uvicorn, 1 worker)
                     automatic HTTPS            SQLite on the "data" volume (/data)
```

- Only Caddy publishes ports (80, 443, 443/udp). The backend has no published port.
- Client IP: Caddy discards any client-sent `X-Forwarded-For` and writes the address it actually sees. uvicorn only trusts that header from Caddy's fixed IP (`--forwarded-allow-ips`), and the app runs with `NEWSRADAR_TRUSTED_PROXY=caddy`. A spoofed header cannot move the rate limiter to another IP.
- One worker only: APScheduler and SQLite both need a single process.

## Run locally

```bash
cd deploy
cp .env.example .env      # fill in the secrets; keep DOMAIN=localhost
docker compose up -d --build
./smoke-test.sh           # https://api.localhost through Caddy (local CA, so -k)
```

For local runs, leave `NEWSRADAR_COOKIE_DOMAIN` empty. Browsers reject a `.newsradarapp.com` cookie sent from `api.localhost`. `NEWSRADAR_SCHEDULER=off` keeps the scheduler from triggering unplanned LLM spend.

Useful commands:

```bash
docker compose logs -f backend
docker compose exec backend python -m app.cli status
docker compose down          # the data volume is kept; `down -v` deletes the database
```

## Secrets and backups (EC2)

```bash
./load-secrets.sh                 # SSM /newsradar/prod/* → deploy/.env (mode 600); list: PARAMETERS.md
./backup.sh                       # sqlite3 .backup → integrity_check → s3://$BACKUP_BUCKET/backups/
./restore.sh                      # latest backup (asks for confirmation); or: ./restore.sh newsradar-YYYYMMDD-HHMM.db.gz
sudo cp systemd/newsradar-backup.* /etc/systemd/system/ && sudo systemctl enable --now newsradar-backup.timer
```

The systemd units assume the repo is checked out at `/opt/newsradar`. `--dry-run DIR` replaces S3 with a local folder.

Local tests, which need no AWS access: `tests/aws` is a fake AWS CLI.

```bash
tests/test-backup-restore.sh      # needs the running stack; restores the DB and returns it to its starting state
tests/test-load-secrets.sh
python3 tests/check-parameters.py # every env var read in code is listed in PARAMETERS.md
```

## Build for ARM

```bash
docker buildx build --platform linux/arm64 -t newsradar-api:arm64 ../backend
```

The image is `python:3.14-slim`, the same 3.14 series as Render's default runtime. It is multi-stage, runs as a non-root user (uid 10001), and has a healthcheck on `/health`.

## Settings that differ from Render

| Variable | Render (default) | Docker / AWS |
|---|---|---|
| `NEWSRADAR_TRUSTED_PROXY` | `render` (first XFF entry) | `caddy` (set in compose) |
| `NEWSRADAR_COOKIE_SAMESITE` | `none` (different sites) | `lax` (same site) |
| `NEWSRADAR_COOKIE_DOMAIN` | empty (host-only) | `.newsradarapp.com` |
| `NEWSRADAR_CORS_ORIGINS` | `FRONTEND_URL` is used | `https://newsradarapp.com,https://www.newsradarapp.com` |
| `NEWSRADAR_DB` | `newsradar.db` | `/data/newsradar.db` (set in compose) |

Leaving these unset keeps the Render behaviour unchanged.
