const assert = require("node:assert/strict");
const { test } = require("node:test");
const data = require("../../assets/js/industry-schedule-data.js");
const blueprints = require("../../assets/js/industry-blueprint-data.js");
const projects = require("../../assets/js/industry-project-data.js");
const schedule = () => ({ start_at: "2026-09-08T02:00:00+02:00", max_runs_per_job: 10,
  workers: [{ id: "w", name: " Pilot ", manufacturing_slots: 2, reaction_slots: 1, available_from: null }],
  facilities: [{ id: "f", name: "Factory", activity: "manufacturing", solar_system_id: 30000142, slots: 2 }],
  assignments: [{ recipe_key: { blueprint_type_id: 2002, activity_id: 1 }, worker_id: "w", facility_id: "f" }] });
const lot = id => ({ id, label: id, blueprint_type_id: 2002, blueprint_name: "Blueprint", product_type_id: 1003,
  product_name: "Product", sde_build_number: 9000001, kind: "bpc", quantity: 1, remaining_runs: 3, material_efficiency: 10, time_efficiency: 20 });

test("schedule normalizes timezones, retains assignments and isolates imported data", () => {
  const raw = schedule(); const normalized = data.normalize(raw);
  assert.equal(normalized.start_at, "2026-09-08T00:00:00.000Z");
  assert.equal(normalized.workers[0].name, "Pilot");
  normalized.workers[0].name = "Another pilot";
  assert.equal(raw.workers[0].name, " Pilot ");
  assert.equal(data.normalize(null), null);
});

test("invalid dates, capacities, duplicate resources and dangling assignments are rejected", () => {
  for (const changes of [{ start_at: "2026-09-08" }, { max_runs_per_job: 0 }, { max_runs_per_job: "10" },
    { workers: [] }, { facilities: [] }, { workers: [schedule().workers[0], schedule().workers[0]] },
    { workers: [{ ...schedule().workers[0], manufacturing_slots: 12 }] },
    { facilities: [{ ...schedule().facilities[0], slots: 0 }] },
    { assignments: [{ ...schedule().assignments[0], worker_id: "missing" }] },
    { assignments: [schedule().assignments[0], schedule().assignments[0]] }]) {
    assert.throws(() => data.normalize({ ...schedule(), ...changes }));
  }
});

test("multiple selected lots and schedules round-trip in projects; old projects stay unscheduled", () => {
  const old = { sde_build_number: 9000001, demands: [], owned_materials: [], choices: [], blueprint_efficiencies: [], inventory_valuation: "replacement_cost" };
  assert.equal(projects.normalizeWorkspace(old).schedule, null);
  const raw = { ...old, schedule: schedule(), blueprint_selections: [lot("first"), lot("second")] };
  const normalized = projects.normalizeWorkspace(raw);
  assert.deepEqual(projects.normalizeWorkspace(JSON.parse(JSON.stringify(normalized))), normalized);
  assert.deepEqual(blueprints.toRequest(normalized.blueprint_selections, true).map(row => row.lot_id), ["first", "second"]);
  assert.throws(() => projects.normalizeWorkspace({ ...raw, schedule: null }));
  assert.throws(() => projects.normalizeWorkspace({ ...raw, blueprint_selections: [lot("same"), lot("same")] }));
});
