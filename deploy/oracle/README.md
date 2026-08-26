# Oracle VM deployment

This deployment runs the ITS-S industry backend and PostgreSQL on one Oracle VM.
PostgreSQL is private to the Docker network. FastAPI is published only on
`127.0.0.1:8000` so a host reverse proxy such as Caddy or Nginx can expose it
over HTTPS later.

## Prerequisites

- Git
- Docker Engine
- Docker Compose plugin (`docker compose`)
- A clone of this repository on the VM

A typical production checkout is:

```bash
git clone --branch main --single-branch https://github.com/Kana523/ITSS_website.git /opt/itss-industry
cd /opt/itss-industry
```

## First deployment

Create the untracked production environment file:

```bash
cp backend/.env.production.example backend/.env.production
nano backend/.env.production
```

At minimum, replace the PostgreSQL password and confirm the ESI user agent and
CORS origin. The password in `POSTGRES_PASSWORD` must match the password embedded
in `DATABASE_URL`.

The `CALCULATION_*` settings bound calculation body size, request rate, and
concurrency. Rate and concurrency limits are enforced per API worker; the
production image currently runs two workers.

Then deploy:

```bash
bash deploy/oracle/deploy.sh
```

The script performs these operations in order:

1. validates `compose.production.yaml`;
2. builds the backend image before touching the running API;
3. starts or verifies PostgreSQL;
4. runs `alembic upgrade head` as a one-shot migration;
5. recreates the FastAPI container only after migrations succeed;
6. waits for `/api/health` to report healthy.

Verify locally on the VM:

```bash
curl http://127.0.0.1:8000/api/health
```

Expected result:

```json
{"api":"ok","database":"ok"}
```

## Updating an existing deployment

Develop and test changes normally, then merge or push the production-ready code
to the `main` branch on GitHub. On the Oracle VM run:

```bash
cd /opt/itss-industry
bash deploy/oracle/update.sh
```

`update.sh` refuses to run if the VM checkout contains local tracked/untracked
changes, pulls `main` with `--ff-only`, then calls `deploy.sh`. The production
secret file is ignored by Git and is not replaced by pulls.

The PostgreSQL data is stored in the Compose named volume `postgres_data`; normal
updates, container recreation, and image rebuilds do not delete it.

Do not use this unless you intentionally want to destroy the database:

```bash
docker compose -f compose.production.yaml down -v
```

## Useful commands

```bash
# Current container state
docker compose -f compose.production.yaml ps

# API logs
docker compose -f compose.production.yaml logs -f --tail=200 api

# PostgreSQL logs
docker compose -f compose.production.yaml logs -f --tail=200 postgres

# Run migrations manually
docker compose -f compose.production.yaml --profile maintenance run --rm migrate

# Refresh private market caches from the server
docker compose -f compose.production.yaml exec -T api python -m app.market refresh --resource all

# Restart only the API
docker compose -f compose.production.yaml restart api
```

The public API exposes cache status only and cannot start refresh work. Install
the included systemd timer once to run the private CLI approximately every five
minutes:

```bash
sudo install -m 0644 deploy/oracle/systemd/itss-market-refresh.service /etc/systemd/system/
sudo install -m 0644 deploy/oracle/systemd/itss-market-refresh.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now itss-market-refresh.timer
sudo systemctl list-timers itss-market-refresh.timer
```

The unit assumes the documented checkout path, `/opt/itss-industry`, and gives a
refresh at most 15 minutes to finish. Its calendar schedule catches up after host
downtime, and the refresher's database lock prevents
overlapping refresh work. Inspect its last result with:

```bash
sudo systemctl status itss-market-refresh.service
sudo journalctl -u itss-market-refresh.service -n 100
```

## Branch override

Production defaults to `main`. If you intentionally need to deploy another
branch temporarily, set `INDUSTRY_BRANCH` when running the update script, for
example:

```bash
INDUSTRY_BRANCH=indy-calc bash deploy/oracle/update.sh
```

The checkout must already be on that branch. For normal production updates, keep
the VM on `main`.

## Reverse proxy

The API is intentionally not reachable from the public network yet. The next
step is to put Caddy or Nginx in front of `127.0.0.1:8000`, configure HTTPS, and
point the static website's API base at that public HTTPS endpoint.
