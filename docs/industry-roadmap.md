# Industry calculator implementation roadmap

Tracks the September 2026 review. Completed means implemented and validated;
deployment and external service connections are separate actions.

## Accuracy

- [x] Apply recipe-specific specialist time bonuses.
- [x] Separate cash requirements, consumed inventory value, and economic profit.
- [x] Validate skills after inventory removes unnecessary jobs.
- [x] Derive facility security from selected systems and require rig coverage.
- [x] Connect sale fees to Accounting and show effective assumptions; identify settings that do not affect the current calculator.
- [x] Rename the production-step count; show actual split jobs separately in Schedule.

## Reliability

- [x] Install production dependencies from the lockfile.
- [x] Check usable SDE data and system security before declaring the calculator ready; document first import.
- [x] Include frontend changes in CI and add browser journeys.
- [x] Replace the nested loader and global fetch interception with explicit loading and request construction.
- [x] Update user and deployment documentation for stage 1.

Stage 1 also corrects configuration columns that became too narrow alongside
the sidebar. Browser checks cover fee/implant/rig request construction, result
rendering, saved manual-fee profiles, and highsec reaction rejection. The Docker
Compose file validates, but an image build could not be checked locally because
the Docker daemon did not respond. CI remains the production image-build gate.

## Production workflow

- [x] Complete projects: draft recovery, named projects, duplication, JSON import/export, products, inventory, choices, ME/TE, and production settings.
- [x] Bulk paste with a preview for inventory, fittings, and multibuy text.
- [x] Blueprint library: BPO/BPC ownership, efficiencies, quantities, and remaining runs.
- [x] Production schedules: split batches, dependencies, characters/facilities, slots, and completion dates.
- [ ] Whole-plan cost optimization accounting for shared materials, inventory, surplus, and market depth.
- [ ] Blueprint acquisition costs, then invention/copying, expected attempts, and decryptors.
- [ ] Corporation stock and build quotes connected through stable EVE type IDs.

Stage 2 delivers browser-local projects and bulk paste. Nine browser journeys
pass, including recovery, exact inventory costs, import/export, stale previews,
cross-tab conflicts, storage failures and a 390px mobile viewport. All 362
non-database pytest checks pass, including the batch API contract and parser /
merge behavior. The 16 PostgreSQL integration checks could not run: the local
server timed out both inside and outside the sandbox. The PostgreSQL CI service
must pass those checks before deployment. No database migration is required.

Stage 3 adds a shared browser blueprint library, portable project selections,
copy-stock limits, optional manufacturing ownership enforcement, and correct
material rounding when copy boundaries and time-limited batches overlap.
Stage 3 supported one selected lot per recipe; stage 4 adds allocation across
lots and parallel slots. Calculations do not consume or reserve stock.
All 382 non-database checks and 15 browser journeys pass, including catalog SQL,
API stock validation, rounding, project compatibility, library backups, edit
conflicts and mobile layout. PostgreSQL integration was pending at that stage;
it now passes locally with Docker Desktop running. No migration is required.

Stage 4 adds the Schedule workspace: physical batches with independent ME/TE
and material rounding, allocation across selected lots, character and facility
capacity, availability dates, recipe assignments, dependency ordering, finish
dates, timeline and CSV export. Applied settings travel with project backups.
The existing local PostgreSQL container was started and all 16 previously
pending integration checks passed before implementation. The full backend
suite and browser journeys, including desktop/mobile scheduling, are validated
as part of this stage.

Scheduling is conservative: predecessors finish in full before dependent steps
begin. It assumes purchases/inventory are available at the start and excludes
hauling, downtime and live EVE job imports. All characters share the project's
skill/implant profile; facilities use its configured activity/category bonuses.
Untracked manufacturing assumes one original; reaction formulas are available.
Stock and slots are not reserved across projects. The plan is capped at 2,000
jobs and does not claim to minimize elapsed time. No migration is required.

Next stage: whole-plan cost optimization, including shared materials,
inventory, surplus and market depth.

## Website design

- [ ] Refine navy/gold into a readable industrial workspace with neutral body text and restrained accents.
- [ ] Quiet the calculator background and simplify navigation to give results more space.
- [ ] Add a compact expandable table for production chains.
- [ ] Lead the summary with cash required, net sales, and economic profit; keep assumptions and incomplete-data explanations adjacent.
- [ ] Improve homepage entry points and replace repeated placeholder trade content with real flows.

## Product decisions

The full roadmap was approved for staged delivery. Account-backed sharing, corporation stock
ownership, and external write actions need concrete requirements before connecting
to live services. Browser-local project storage is the default for the first stage.
