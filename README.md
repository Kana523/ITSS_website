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
levels and facility/rig choices. Manufacturing and reaction security is derived
from the selected solar system, including category setup overrides. Select the
system in the pricing panel; its security cannot be changed independently.
Pending or unavailable security data blocks calculation, and highsec systems
cannot be selected for reactions.

When choosing Tech I or Tech II rigs, explicitly select their product categories
or groups in **Rig coverage**. The selected coverage is a union: choosing an
entire category includes all its groups. The tier represents both material and
time bonuses for that coverage; category setup overrides specify their own
coverage. A newly enabled category override starts without rigs. Saved profiles
retain coverage and re-resolve system security when loaded. Older profiles with
unscoped rigs must have coverage selected before they can calculate again.

The exact-modifier API continues to accept caller-supplied final reductions and
optional category/group scopes, including unscoped custom rules. The website
always supplies explicit coverage for its general rig selections.

### Updating existing installations for system security

Apply migration `0007` and re-import the existing SDE archive (the same build is
supported):

```powershell
cd backend
uv run alembic upgrade head
uv run python -m app.sde C:\path\to\eve-online-static-data-latest-jsonl.zip
```

This fills `security_status` from `mapSolarSystems.jsonl`; existing rows remain
unknown until the import. `/api/industry/systems` now returns `security_status`
and `security_space`. `/api/industry/rig-scopes?activity=manufacturing` (or
`reaction`) supplies the named product categories/groups available for coverage.
Security classification follows the [EVE system-security guide](https://developers.eveonline.com/docs/guides/system-security/)
and [system ID ranges](https://developers.eveonline.com/docs/guides/id-ranges/).

### Calculation details

Choose ME and TE values on any manufacturing job and select **Apply** to
recalculate the full dependency chain. Market pricing values purchases,
job installation, requested outputs, surplus inventory, and estimated profit
from the cached Jita snapshot. Inputs use volume-weighted sell-order fills;
immediate-sale values use unrestricted buy orders. When cached depth cannot
cover a quantity, its value is incomplete rather than extrapolated or treated
as zero. The aggregated shopping list can be copied as EVE multibuy text.

Manufacturing and reaction jobs can use separate system IDs and fee assumptions.
Enter a low-security reaction system when a selected route contains reactions;
the page does not silently reuse the manufacturing system.

Material calculations account for jobs split by blueprint-copy run limits and a
maximum of 30 days of modified craft time per job, with at least one run per job.
Manufacturing implants, blueprint-required specialist skills, and owned-material
deductions are available in the UI. Each required specialist skill with a
manufacturing time bonus contributes its own multiplicative factor before job
splitting. The production route shows the applied skills and reductions. The
rates are verified against CCP's public ESI skill descriptions (including the
2% per level Mutagenic Stabilization exception). Skill eligibility is checked
only for jobs remaining after owned inventory is deducted. Omitted specialist
skills retain the API's existing opt-out behavior; an explicit empty list
validates eligibility with no specialist levels.

In **Owned materials**, choose **Market replacement cost** (the default) or
**Recorded unit costs**. Recorded costs are average acquisition ISK per unit;
blank means unknown and an explicit zero means zero acquisition cost. Only
units consumed by the plan are valued, including owned intermediate or final
products. Unused stock is excluded. Replacement valuation uses cached sell
depth after reserving the shopping quantities, avoiding reuse of cheap orders.

- **Cash required** = shopping purchases + installation costs, before selling.
- **Net cash proceeds** = requested net sales - cash required.
- **Economic profit** = net cash proceeds - consumed inventory value.
- **Total cost incl. sale fees** includes cash required, inventory value, and
  the requested output's transaction fees. Surplus-inclusive profit uses the
  same inventory cost with the combined output/surplus sale valuation.

Missing recorded costs or insufficient replacement quotes leave economic
profit incomplete while cash estimates remain available when their own inputs
are complete. Expand **Consumed inventory details** to find affected items.

The API reports `consumed_inventory`, `consumed_inventory_value`,
`cash_required_isk`, and `cash_surplus_isk`; existing profit and total-cost
fields now include consumed inventory. Set `pricing.inventory_valuation_method`
to `replacement_cost` or `recorded_cost`, with recorded entries such as
`"recorded_inventory_costs": [{"type_id": 34, "unit_cost_isk": "4.25"}]`.
Send costs as decimal strings (up to 24 integer digits and 8 decimal places).
Blueprint-copy run limits and multiple scoped rig rules remain API-only.
