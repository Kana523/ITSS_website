(() => {
  "use strict";
  const integer = (value, min = 0, max = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(value) && value >= min && value <= max;
  const text = (value, max) => typeof value === "string" && value.trim() && value.length <= max;
  function normalizeEntry(raw) {
    if (!raw || !text(raw.id, 100) || !text(raw.label, 60) || !text(raw.blueprint_name, 255)
      || !text(raw.product_name, 255) || !integer(raw.blueprint_type_id, 1, 2147483647)
      || !integer(raw.product_type_id, 1, 2147483647) || !integer(raw.sde_build_number, 1)
      || !["bpo", "bpc"].includes(raw.kind) || !integer(raw.quantity, 1)
      || !integer(raw.material_efficiency, 0, 10) || !integer(raw.time_efficiency, 0, 20)
      || raw.time_efficiency % 2) throw new Error("Invalid blueprint lot, quantity or ME/TE.");
    if (raw.kind === "bpo" && raw.remaining_runs !== null) throw new Error("Original blueprints have unlimited runs.");
    if (raw.kind === "bpc" && (!integer(raw.remaining_runs) || !integer(raw.remaining_runs * raw.quantity))) {
      throw new Error("Copy runs must be non-negative whole numbers with a total within the calculator limit.");
    }
    return { id: raw.id, label: raw.label.trim(), blueprint_type_id: raw.blueprint_type_id,
      blueprint_name: raw.blueprint_name, product_type_id: raw.product_type_id, product_name: raw.product_name,
      sde_build_number: raw.sde_build_number, kind: raw.kind, quantity: raw.quantity, remaining_runs: raw.remaining_runs,
      material_efficiency: raw.material_efficiency, time_efficiency: raw.time_efficiency };
  }
  function normalizeEntries(raw, { selections = false, multiple = false } = {}) {
    if (!Array.isArray(raw) || raw.length > 500) throw new Error("A library supports at most 500 blueprint lots.");
    const ids = new Set();
    const recipes = new Set();
    return raw.map(value => {
      const entry = normalizeEntry(value);
      if (ids.has(entry.id) || (selections && !multiple && recipes.has(entry.blueprint_type_id))) throw new Error("Duplicate blueprint lot or project recipe selection.");
      ids.add(entry.id); recipes.add(entry.blueprint_type_id);
      return entry;
    });
  }
  const toRequest = (entries, multiple = false) => normalizeEntries(entries, { selections: true, multiple }).map(entry => ({
    recipe_key: { blueprint_type_id: entry.blueprint_type_id, activity_id: 1 }, kind: entry.kind,
    quantity: entry.quantity, remaining_runs: entry.remaining_runs,
    material_efficiency: entry.material_efficiency, time_efficiency: entry.time_efficiency,
    ...(multiple ? { lot_id: entry.id } : {}),
  }));
  const api = Object.freeze({ normalizeEntry, normalizeEntries, toRequest });
  globalThis.industryBlueprintData = api;
  if (typeof module !== "undefined") module.exports = api;
})();
