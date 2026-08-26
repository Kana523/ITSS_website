# ITSS Website

ITS-S (Interstellar Systems) is my EVE Online corporation focused on small-scale industry, planetary interaction, and reactions. This repo hosts the corporation website.

## Pages

- **Home** - Landing page with core corporate info and select merchandise highlights
- **Shop** - Marketplace for in-game item transactions
- **Trade** - Trade-related tooling and listings
- **Industry** - Multi-product manufacturing and reaction planner with ME/TE, production profiles, cached market estimates, and shopping-list export
- **About** - Extended overview of the corporation and its goals
- **Legal** - Disclaimers and compliance documentation

## Project Structure

```
ITSS_Website/
├── index.html
├── shop/
├── trade/
├── industry/
├── about/
├── legal/
└── assets/
    ├── images/
    │   ├── backgrounds/
    │   ├── icons/
    │   └── items/
    ├── js/
    └── styling/
        ├── css/        # Per-page stylesheets + base.css (CSS variables)
        └── fonts/
```

## Tech Stack

- Plain HTML, CSS, and JavaScript — no framework, no build step
- CSS custom properties defined in `assets/styling/css/base.css`

## Getting Started

Serve the site over HTTP, for example:

```powershell
python -m http.server 5500 --bind 127.0.0.1
```

The Industry page also needs PostgreSQL, imported SDE data, and the API. From
the repository root, start PostgreSQL:

```powershell
docker compose up -d --wait postgres
```

Before the first run, copy `backend/.env.example` to `backend/.env`, choose a
local database password, and replace the example `ESI_USER_AGENT` contact with
a real email address or repository URL. Then prepare the backend:

```powershell
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.sde C:\path\to\eve-online-static-data-latest-jsonl.zip
uv run python -m app.market refresh --resource all
uv run --locked pip-audit --local --progress-spinner off
uv run fastapi dev app/main.py
```

Market refreshes are intentionally server-only. The public API exposes cached
Jita status but has no refresh endpoint; run the `app.market` command manually or
from a server-side scheduler.

Then open `http://127.0.0.1:5500/industry/`.

### Using the industry planner

Search for one or more products, edit their quantities in the build list, and
select **Calculate**. The production-profile panel accepts character skill
levels plus exact facility and rig reductions. Rig category/group scopes are
optional; an empty scope applies that rig modifier to every product in the
selected activity.

Choose ME and TE values on any manufacturing job and select **Apply** to
recalculate the full dependency chain. Enable market pricing to value purchases,
job installation, requested outputs, surplus inventory, and estimated profit
from the cached Jita snapshot. Inputs use the best sell level; immediate-sale
values use the best unrestricted buy level. The cache does not walk the full
order book: when the cached best-price volume cannot fill a quantity, the value
is shown as incomplete rather than extrapolated or treated as zero. The
aggregated shopping list can be copied or downloaded as CSV.

Manufacturing and reaction jobs can use separate system IDs and fee assumptions.
Enter a low-security reaction system when a selected route contains reactions;
the page does not silently reuse the manufacturing system.

Material calculations account for jobs split by blueprint-copy run limits and a
maximum of 30 days of modified craft time per job, with at least one run per job.
The API also accepts manufacturing implants, blueprint-required specialist
skills, and owned-material deductions. The current UI exposes the implant and
one scoped rig rule per activity; the other inputs and multiple scoped rig rules
remain API-only.
