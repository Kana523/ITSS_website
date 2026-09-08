const assert = require("node:assert/strict");
const { test } = require("node:test");
const { parsePaste, mergeRows, normalizeWorkspace } = require("../../assets/js/industry-project-data.js");
const item = { type_id: 34, name: "Tritanium" };
const workspace = () => ({ sde_build_number: 9000001, demands: [], owned_materials: [],
  choices: [], blueprint_efficiencies: [], inventory_valuation: "replacement_cost" });

test("inventory columns, multibuy, fitting hull, charges, drones and empty slots", () => {
  const rows = parsePaste("Tritanium\t1,000\tMineral\n2 Rifter\nWarrior II x5\n[Merlin, Fit]\n125mm Railgun I, Antimatter Charge S\n[Empty Low slot]");
  assert.deepEqual(rows.filter(row => !row.ignored).map(({ query, quantity }) => [query, quantity]), [
    ["Tritanium", 1000], ["Rifter", 2], ["Warrior II", 5], ["Merlin", 1], ["125mm Railgun I", 1], ["Antimatter Charge S", 1],
  ]);
  assert.equal(rows.at(-1).ignored, "Empty fitting slot");
  assert.ok(parsePaste("Tritanium\t1,5")[0].error);
  assert.ok(parsePaste("Tritanium x0")[0].error);
  assert.ok(parsePaste("Tritanium x9007199254740992")[0].error);
  assert.throws(() => parsePaste("Tritanium\n".repeat(501)), /500/);
});

test("merges combine duplicates, retain exact costs, replace only pasted IDs and reject overflow atomically", () => {
  const existing = [{ item, quantity: 10, unitCost: "9007199254740991.12345678" }, { item: { ...item, type_id: 35 }, quantity: 9 }];
  const additions = [{ item, quantity: 2 }, { item, quantity: 3 }];
  const merged = mergeRows(existing, additions, 500, "add");
  assert.equal(merged[0].quantity, 15);
  assert.equal(merged[0].unitCost, existing[0].unitCost);
  assert.equal(mergeRows(existing, additions, 500, "replace")[0].quantity, 5);
  assert.equal(merged[1].quantity, 9);
  assert.throws(() => mergeRows(existing, [{ item, quantity: Number.MAX_SAFE_INTEGER }], 500, "add"));
  assert.throws(() => mergeRows(existing, [{ item: { ...item, type_id: 36 }, quantity: 1 }], 2, "add"), /limit/);
  assert.equal(existing[0].quantity, 10);
  assert.throws(() => mergeRows([{ item, quantity: "" }], additions, 500, "add"), /Quantities/);
});

test("project normalization rejects invalid IDs, duplicate rows, bad efficiencies, and unsupported inventory modes", () => {
  const raw = workspace();
  raw.owned_materials = [{ item, quantity: 5, unitCost: "123456789012345678901234.12345678" }];
  assert.equal(normalizeWorkspace(raw).owned_materials[0].unitCost, raw.owned_materials[0].unitCost);
  assert.throws(() => normalizeWorkspace({ ...raw, demands: [{ item, quantity: 1 }, { item, quantity: 2 }] }), /Duplicate/);
  assert.throws(() => normalizeWorkspace({ ...raw, inventory_valuation: "free" }));
  assert.throws(() => normalizeWorkspace({ ...raw, demands: [{ item: { ...item, type_id: -1 }, quantity: 1 }] }));
  assert.throws(() => normalizeWorkspace({ ...raw, blueprint_efficiencies: [{ recipe_key: { blueprint_type_id: 1, activity_id: 1 }, product_type_id: 34, material_efficiency: 10, time_efficiency: 3 }] }));
});
