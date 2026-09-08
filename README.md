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

Sales tax defaults to **From Accounting skill**: 7.5% at level 0 through 3.375%
at level V, preserved exactly in backend arithmetic. **Manual rate** keeps a
user-entered percentage, including an explicit zero. Profiles saved before this
mode was introduced retain their manual rate. Broker fees default to zero
because output valuation represents immediate sales into buy orders; the field
can still represent an explicit additional fee assumption. Broker Relations
and Advanced Broker Relations apply to order creation/relisting, which this
valuation does not simulate. Science and PI fee controls are labelled as
excluded previews and disabled. See [CCP's fee reference](https://support.eveonline.com/hc/en-us/articles/203218962-Broker-Fee-and-Sales-Tax).

API clients can set `pricing.accounting_level` (0–5) to use Accounting-based
sales tax; this takes precedence over `sales_tax_basis_points`. Omitting it
preserves the existing manual basis-point contract. Responses include
`accounting_level` and the exact `effective_sales_tax_rate` as a decimal string.
The result summary displays **Production steps**, since each step can split into
multiple installable jobs.

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
Multiple scoped rig rules remain API-only; blueprint-copy stock and run limits
are now available through the Blueprints tab.

### Projects and bulk paste

The **Projects** panel saves complete plans automatically in this browser,
including requested quantities, owned inventory and exact recorded costs,
build/buy decisions, blueprint ME/TE, skills, implants, facilities, category
overrides and pricing assumptions. Rename the working draft or create and
duplicate projects; up to 25 are supported. New projects keep the current
production settings and start with empty lists. Profiles remain reusable sets
of character/facility settings that you can apply to any project.

Use **Export JSON** for backups or another device, and **Import JSON** to add
a project without replacing an existing one. Imports are versioned, validated,
and limited to 5 MB. Browser storage is local to this website and browser;
clearing site data removes saved projects. Invalid fields pause saving until
corrected, and storage failures appear beside the project controls. Concurrent
changes in another tab pause saving to avoid overwriting its work; export your
current plan before reloading. Loading a project requires a new calculation
for current routes and market prices. Recipe settings are revalidated against
the SDE version through the existing calculation recovery flow.

On **Build**, expand **Paste an inventory, multibuy list or fitting**. Choose
the build list or owned inventory, paste exact English item names or type IDs,
and preview before adding. Supported examples:

```text
Tritanium\t1,000
Rifter x2
2 Merlin
```

In the first example, `\t` represents a real tab copied from inventory, rather
than a literal backslash and letter. Additional inventory columns are ignored.
EFT fitting headers add the hull, empty slots are identified, and repeated
items combine. A loaded charge counts as one per module; enter your intended
ammunition quantity explicitly. Unknown or ambiguous names and items without
production recipes are shown in the preview; only matched entries are applied.
Choose whether pasted quantities add to existing stock or replace quantities
for the pasted items. Unlisted items and existing recorded costs are retained.
Pastes allow 500 entries; the destination limits remain 50 products and 500
owned item types. Quantity overflow rejects the entire merge.

The batch lookup endpoint is `POST /api/industry/types/resolve` with
`{"queries":["Tritanium","587"]}`. It returns exact published matches,
producible type IDs, and the SDE build number, and shares calculation request
body, concurrency and rate limits. No database migration is needed for projects.

### Blueprint library

Open **Blueprints** to search manufacturing blueprints by blueprint name,
product name, or either type ID. Record an original (BPO) or a copy lot (BPC),
with quantity, ME and TE. Copies in a lot must have identical efficiencies and
the same remaining runs per copy. Zero remaining runs records an exhausted lot;
originals have unlimited runs. The shared browser library supports 500 lots,
filtering, editing, duplication and JSON backups up to 5 MB. Imports add new lots, skip
identical IDs, and reject conflicting IDs without overwriting stock.

Click **Use in project** to save a snapshot of a lot with the active project.
With scheduling disabled, one lot can be selected per recipe; the UI replaces
a previous selection for the same product. Enable **Schedule** to allocate
across several lots of the same blueprint. Library ME/TE replaces manual efficiency controls for that
recipe. BPC run capacity is `number of copies × remaining runs per copy`.
Insufficient selected stock blocks calculation with a link back to the library.
Scheduled originals can run in parallel up to the owned quantity and available
slots. Total craft time remains the sum of job durations; the schedule shows
the elapsed calendar time separately.

Enable **Require owned blueprints for every manufacturing step** to block
untracked manufacturing recipes too. Ownership is checked after inventory
deductions; jobs eliminated by owned materials need no blueprint runs. Reaction
formulas are outside this manufacturing library. Unused selections remain saved
without forcing their recipes into an unrelated route. Buying a product still
takes precedence over its blueprint selection.

Library edits do not silently change project snapshots: use **Refresh from
library** on a changed selection. Project JSON includes selected snapshots and
works without importing the shared library; older projects load with no
selections and ownership checks disabled. Calculations neither consume nor
reserve stock across projects. Update actual remaining runs manually after
running jobs. Blueprint acquisition costs remain a later roadmap stage.

`GET /api/industry/blueprints?search=Rifter` returns the manufacturing catalog.
The calculation API accepts `blueprint_selections`, for example:

```json
{
  "recipe_key": {"blueprint_type_id": 688, "activity_id": 1},
  "kind": "bpc",
  "quantity": 2,
  "remaining_runs": 10,
  "material_efficiency": 10,
  "time_efficiency": 20
}
```

Supply that object inside the `blueprint_selections` array. BPO entries use
`kind: "bpo"` and `remaining_runs: null`. Do not also send manual efficiency or
copy-limit entries for a selected recipe. `require_owned_blueprints` defaults
to false. Both copy boundaries and the existing job-time limit preserve each
job's independent material rounding. No database migration is required.

### Production scheduling

Open **Schedule** and enable scheduling for the active project. Set a local
start time, maximum runs per job, character slot counts and availability, and
facilities. Each facility has an activity, EVE system ID, and a concurrency
allowance for this plan. Its system must match Config (including category
overrides). The allowance represents the capacity you want to use, not a
game-imposed structure slot limit.

Click **Calculate schedule** to generate the timeline and job table. Recipe
assignments then let you choose a specific character or facility; **Automatic**
uses the earliest available eligible slot. **Apply settings** saves edits
without recalculating. Applied settings and assignments are included in project
autosave, duplication and JSON backups. New projects retain scheduling resources
but clear recipe assignments. **Export jobs CSV** includes exact UTC timestamps,
type IDs, lot IDs, blueprint instances, resources, runs, ME/TE and dependencies.
The page displays dates in your browser's local timezone.

On **Blueprints**, scheduling allows multiple selected lots per recipe. Runs
are allocated in selection order; **Use first** changes that order. An original
has unlimited capacity, so a BPO placed first supplies all the recipe's runs.
Every BPC retains its individual remaining-run boundary, and jobs sharing one
physical blueprint cannot overlap. Multiple originals/copies can use parallel
slots. Each job uses its own lot's ME/TE and material rounding, so scheduling
can change upstream quantities and costs. Remove extra lots before disabling
scheduling; stock is never silently discarded.

This is a deterministic, conservative schedule, not a shortest-time optimizer.
All batches of a predecessor finish before dependent production starts. Purchased
materials and owned inventory are available at the start; hauling, downtime and
already-running EVE jobs are not imported. Each character uses the project's skill
and implant profile, and facilities use its configured activity/category bonuses
and fees. Untracked manufacturing assumes one original; reaction formulas are
assumed available. Stock and slots are not reserved across projects or in EVE.

The calculation API accepts an optional `schedule` object:

```json
{
  "start_at": "2026-09-08T12:00:00Z",
  "max_runs_per_job": 100,
  "workers": [
    {"id": "pilot-1", "name": "Pilot 1", "manufacturing_slots": 2, "reaction_slots": 0, "available_from": null}
  ],
  "facilities": [
    {"id": "factory", "name": "Factory", "activity": "manufacturing", "solar_system_id": 30000142, "slots": 2}
  ],
  "assignments": []
}
```

Add a distinct `lot_id` to every selected blueprint lot when using multiple
lots. An assignment contains `recipe_key` and optional `worker_id` / `facility_id`.
Dates must include a timezone. Limits are 20 characters, 50 facilities, 500
assignments and 2,000 generated jobs per calculation. Character slots are 0–11
per activity; facility concurrency is 1–100. Jobs also respect the existing
job-time limit. Unsupported constraints return `invalid_schedule` (422) with
a corrective message; insufficient selected copy capacity remains a 409.
Omitting `schedule` keeps the previous aggregate calculation behavior. No
database migration is required.

### Validation and roadmap

Run backend and DOM regression tests from `backend` with `uv run pytest`.
Browser tests exercise the real page with deterministic API fixtures:

```powershell
npm ci
npx playwright install chromium
npm run test:browser
```

To use an installed Chrome without downloading a browser on Windows:

```powershell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
npm run test:browser
```

CI runs these journeys for frontend changes and retains failure traces and
screenshots. Production readiness is exposed at `/api/ready`; `/api/health`
only checks basic API/database availability. The frontend uses explicit ES
module imports, and the calculation request includes the selected implant
directly. Serve the website over HTTP rather than opening files directly.

The full staged implementation checklist is in [the industry roadmap](docs/industry-roadmap.md).
