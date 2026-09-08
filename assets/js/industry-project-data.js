(() => {
  "use strict";
  const record = value => value && typeof value === "object" && !Array.isArray(value);
  const id = value => Number.isInteger(value) && value > 0 && value <= 2147483647;
  function fail(message) { throw new Error(message); }
  function quantity(value) {
    if (!/^[0-9]+$/.test(String(value)) || !Number.isSafeInteger(Number(value)) || Number(value) < 1) {
      fail("Quantities must be positive whole numbers within the calculator limit.");
    }
    return Number(value);
  }
  function recipe(raw) {
    if (!record(raw) || !id(raw.blueprint_type_id) || !id(raw.activity_id)) fail("Invalid recipe key.");
    return { blueprint_type_id: raw.blueprint_type_id, activity_id: raw.activity_id };
  }
  function item(raw) {
    if (!record(raw) || !id(raw.type_id) || typeof raw.name !== "string" || !raw.name.trim()
      || raw.name.length > 255) fail("Invalid EVE item.");
    // Imported labels are display hints only. Calculations always resolve IDs against the current SDE.
    return { type_id: raw.type_id, name: raw.name, published: true,
      group_id: id(raw.group_id) ? raw.group_id : 1,
      category_id: id(raw.category_id) ? raw.category_id : 1,
      group_name: typeof raw.group_name === "string" ? raw.group_name.slice(0, 255) : "",
      category_name: typeof raw.category_name === "string" ? raw.category_name.slice(0, 255) : "" };
  }
  function rows(raw, limit, owned) {
    if (!Array.isArray(raw) || raw.length > limit) fail(`List exceeds ${limit} items or is invalid.`);
    const seen = new Set();
    return raw.map(entry => {
      if (!record(entry)) fail("Invalid item entry.");
      const normalized = { item: item(entry.item), quantity: quantity(entry.quantity) };
      if (seen.has(normalized.item.type_id)) fail("Duplicate item IDs in project.");
      seen.add(normalized.item.type_id);
      if (owned) {
        const cost = entry.unitCost ?? "";
        if (typeof cost !== "string" || cost.length > 33 || (cost && !/^\d{1,24}(?:\.\d{1,8})?$/.test(cost))) {
          fail("Invalid inventory unit cost (up to 24 integer digits and eight decimal places).");
        }
        normalized.unitCost = cost;
      }
      return normalized;
    });
  }
  function normalizeWorkspace(raw) {
    if (!record(raw)) fail("Invalid project workspace.");
    if (raw.require_owned_blueprints !== undefined && typeof raw.require_owned_blueprints !== "boolean") fail("Invalid blueprint ownership mode.");
    if (raw.sde_build_number !== null && (!Number.isSafeInteger(raw.sde_build_number) || raw.sde_build_number < 1)) {
      fail("Invalid industry data version.");
    }
    if (!["replacement_cost", "recorded_cost"].includes(raw.inventory_valuation)) fail("Invalid inventory valuation.");
    if (!Array.isArray(raw.choices) || raw.choices.length > 500
      || !Array.isArray(raw.blueprint_efficiencies) || raw.blueprint_efficiencies.length > 500) fail("Invalid route settings.");
    const choices = new Set();
    const efficiencies = new Set();
    return {
      sde_build_number: raw.sde_build_number,
      demands: rows(raw.demands, 50, false), owned_materials: rows(raw.owned_materials, 500, true),
      inventory_valuation: raw.inventory_valuation,
      blueprint_selections: raw.blueprint_selections === undefined ? []
        : globalThis.industryBlueprintData.normalizeEntries(raw.blueprint_selections, { selections: true, multiple: Boolean(raw.schedule) }),
      require_owned_blueprints: raw.require_owned_blueprints === true,
      schedule: raw.schedule == null ? null : globalThis.industryScheduleData.normalize(raw.schedule),
      choices: raw.choices.map(entry => {
        if (!record(entry) || !id(entry.type_id) || choices.has(entry.type_id)
          || !["buy", "build"].includes(entry.decision)) fail("Invalid or duplicate build choice.");
        choices.add(entry.type_id);
        return { type_id: entry.type_id, decision: entry.decision,
          ...(entry.decision === "build" ? { recipe_key: recipe(entry.recipe_key) } : {}) };
      }),
      blueprint_efficiencies: raw.blueprint_efficiencies.map(entry => {
        if (!record(entry)) fail("Invalid blueprint settings.");
        const key = recipe(entry.recipe_key);
        const token = `${key.blueprint_type_id}:${key.activity_id}`;
        if (efficiencies.has(token) || !id(entry.product_type_id)
          || !Number.isInteger(entry.material_efficiency) || entry.material_efficiency < 0 || entry.material_efficiency > 10
          || !Number.isInteger(entry.time_efficiency) || entry.time_efficiency < 0 || entry.time_efficiency > 20
          || entry.time_efficiency % 2) fail("Invalid or duplicate blueprint efficiency.");
        efficiencies.add(token);
        return { recipe_key: key, product_type_id: entry.product_type_id,
          material_efficiency: entry.material_efficiency, time_efficiency: entry.time_efficiency };
      }),
    };
  }
  function parsePaste(text) {
    if (text.length > 200000) fail("Paste is limited to 200,000 characters.");
    const lines = text.split(/\r?\n/);
    if (lines.length > 1000) fail("Paste is limited to 1,000 lines.");
    const result = [];
    const push = (line, query, count = "1") => {
      try {
        if (!query || query.length > 255) fail("Invalid item name.");
        // Commas may group thousands, but must never turn a decimal quantity into an integer.
        if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)$/.test(count)) fail("Invalid quantity.");
        result.push({ line, query, quantity: quantity(count.replaceAll(",", "")) });
      } catch (error) { result.push({ line, query, error: error.message }); }
    };
    lines.forEach((raw, index) => {
      const line = index + 1;
      const value = raw.trim();
      if (!value) return;
      if (/^\[empty .+ slot\]$/i.test(value)) {
        result.push({ line, query: value, ignored: "Empty fitting slot" }); return;
      }
      if (value.startsWith("[")) {
        const header = value.match(/^\[([^,\]]+),.*\]$/);
        if (header) push(line, header[1].trim());
        else result.push({ line, query: value, error: "Unrecognized fitting header." });
        return;
      }
      if (value.includes("\t")) {
        const fields = value.split("\t");
        push(line, fields[0].trim(), fields[1]?.trim() || "1"); return;
      }
      const suffix = value.match(/^(.+?)\s+[xX]([\d,]+)$/) || value.match(/^(.+?)\s+([\d,]+)$/);
      if (suffix) { push(line, suffix[1].trim(), suffix[2]); return; }
      const prefix = value.match(/^([\d,]+)\s+[xX]?\s*(.+)$/);
      if (prefix) { push(line, prefix[2].trim(), prefix[1]); return; }
      // EFT charges describe loaded ammunition, not a cargo quantity: one per fitted module.
      const loaded = value.split(/,\s+/);
      loaded.forEach(name => push(line, name.trim()));
    });
    if (result.filter(row => !row.ignored && !row.error).length > 500) fail("Paste is limited to 500 item entries.");
    return result;
  }
  function mergeRows(existing, additions, limit, mode) {
    const result = new Map(existing.map(row => [row.item.type_id, { ...row }]));
    const incoming = new Map();
    for (const row of additions) {
      const previous = incoming.get(row.item.type_id);
      incoming.set(row.item.type_id, { item: item(row.item), quantity: quantity((previous?.quantity || 0) + quantity(row.quantity)) });
    }
    for (const [typeId, row] of incoming) {
      const previous = result.get(typeId);
      result.set(typeId, { ...previous, ...row, quantity: quantity(row.quantity + (mode === "add" && previous ? quantity(previous.quantity) : 0)) });
    }
    if (result.size > limit) fail(`This would exceed the ${limit}-item limit. No items were changed.`);
    return [...result.values()];
  }
  const api = Object.freeze({ normalizeWorkspace, parsePaste, mergeRows });
  globalThis.industryProjectData = api;
  if (typeof module !== "undefined") module.exports = api;
})();
