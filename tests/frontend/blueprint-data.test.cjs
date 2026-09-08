const assert = require("node:assert/strict");
const { test } = require("node:test");
const data = require("../../assets/js/industry-blueprint-data.js");
const projectData = require("../../assets/js/industry-project-data.js");
const entry = () => ({ id: "lot-1", label: "Weekend copies", blueprint_type_id: 2002,
  blueprint_name: "Final Product Blueprint", product_type_id: 1003, product_name: "Final Product",
  sde_build_number: 9000001, kind: "bpc", quantity: 2, remaining_runs: 3, material_efficiency: 10, time_efficiency: 20 });

test("copy stock and originals produce exact planner inputs", () => {
  const request = data.toRequest([entry()])[0];
  assert.deepEqual(request.recipe_key, { blueprint_type_id: 2002, activity_id: 1 });
  assert.equal(request.remaining_runs, 3);
  assert.equal(request.quantity, 2);
  assert.equal(data.normalizeEntry({ ...entry(), kind: "bpo", remaining_runs: null }).remaining_runs, null);
  assert.equal(data.normalizeEntry({ ...entry(), remaining_runs: 0 }).remaining_runs, 0);
  for (const invalid of [{ quantity: 0 }, { quantity: "2" }, { remaining_runs: -1 }, { time_efficiency: 3 },
    { quantity: Number.MAX_SAFE_INTEGER, remaining_runs: 2 }, { kind: "bpo" }, { blueprint_type_id: -1 }]) {
    assert.throws(() => data.normalizeEntry({ ...entry(), ...invalid }));
  }
});

test("separate stock lots are supported but only one selected lot per recipe", () => {
  const lots = [entry(), { ...entry(), id: "lot-2", material_efficiency: 5 }];
  assert.equal(data.normalizeEntries(lots).length, 2);
  assert.throws(() => data.normalizeEntries(lots, { selections: true }));
  assert.throws(() => data.normalizeEntries([entry(), entry()]));
  assert.throws(() => data.normalizeEntries(Array(501).fill(entry())));
});

test("old project files migrate and selected blueprint snapshots round-trip without shared references", () => {
  const old = { sde_build_number: 9000001, demands: [], owned_materials: [], choices: [], blueprint_efficiencies: [], inventory_valuation: "replacement_cost" };
  assert.deepEqual(projectData.normalizeWorkspace(old).blueprint_selections, []);
  const snapshot = projectData.normalizeWorkspace({ ...old, blueprint_selections: [entry()], require_owned_blueprints: true });
  const restored = projectData.normalizeWorkspace(JSON.parse(JSON.stringify(snapshot)));
  assert.deepEqual(restored, snapshot);
  restored.blueprint_selections[0].remaining_runs = 0;
  assert.equal(snapshot.blueprint_selections[0].remaining_runs, 3);
  assert.throws(() => projectData.normalizeWorkspace({ ...old, require_owned_blueprints: "yes" }));
});
