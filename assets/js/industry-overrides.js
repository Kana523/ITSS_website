(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const list = app.querySelector("[data-category-overrides-list]");
  if (!list) return;

  const CATEGORIES = Object.freeze([
    Object.freeze({ category: "advanced_components", label: "Advanced components" }),
    Object.freeze({ category: "t1_small_ships", label: "T1 small ships" }),
    Object.freeze({ category: "t1_medium_ships", label: "T1 medium ships" }),
    Object.freeze({
      category: "t1_large_ships",
      label: "T1 large ships",
      note: "Includes Freighters",
    }),
    Object.freeze({ category: "t2_small_ships", label: "T2 small ships" }),
    Object.freeze({ category: "t2_medium_ships", label: "T2 medium ships" }),
    Object.freeze({
      category: "t2_large_ships",
      label: "T2 large ships",
      note: "Includes Jump Freighters",
    }),
    Object.freeze({ category: "structures", label: "Structures" }),
    Object.freeze({ category: "fighters_drones", label: "Fighters and drones" }),
    Object.freeze({ category: "equipment", label: "Equipment" }),
    Object.freeze({ category: "ammunition", label: "Ammunition" }),
    Object.freeze({ category: "capital_components", label: "Capital components" }),
    Object.freeze({ category: "capital_ships", label: "Capital ships" }),
    Object.freeze({ category: "supercapital_ships", label: "Supercapital ships" }),
  ]);

  const STRUCTURE_PROFILES = Object.freeze({
    manufacturing: Object.freeze({
      unbonused: Object.freeze({ material: 0, time: 0, cost: 0 }),
      raitaru: Object.freeze({ material: 100, time: 1500, cost: 300 }),
      azbel: Object.freeze({ material: 100, time: 2000, cost: 400 }),
      sotiyo: Object.freeze({ material: 100, time: 3000, cost: 500 }),
    }),
    reaction: Object.freeze({
      athanor: Object.freeze({ material: 0, time: 0, cost: 0 }),
      tatara: Object.freeze({ material: 0, time: 2500, cost: 0 }),
    }),
  });

  // These are exact final basis-point reductions. Reaction rigs use a
  // different security multiplier from manufacturing rigs in EVE dogma data.
  const RIG_PROFILES = Object.freeze({
    manufacturing: Object.freeze({
      none: Object.freeze({
        highsec: Object.freeze({ material: 0, time: 0 }),
        lowsec: Object.freeze({ material: 0, time: 0 }),
        nullsec: Object.freeze({ material: 0, time: 0 }),
        wormhole: Object.freeze({ material: 0, time: 0 }),
      }),
      t1: Object.freeze({
        highsec: Object.freeze({ material: 200, time: 2000 }),
        lowsec: Object.freeze({ material: 380, time: 3800 }),
        nullsec: Object.freeze({ material: 420, time: 4200 }),
        wormhole: Object.freeze({ material: 420, time: 4200 }),
      }),
      t2: Object.freeze({
        highsec: Object.freeze({ material: 240, time: 2400 }),
        lowsec: Object.freeze({ material: 456, time: 4560 }),
        nullsec: Object.freeze({ material: 504, time: 5040 }),
        wormhole: Object.freeze({ material: 504, time: 5040 }),
      }),
    }),
    reaction: Object.freeze({
      none: Object.freeze({
        lowsec: Object.freeze({ material: 0, time: 0 }),
        nullsec: Object.freeze({ material: 0, time: 0 }),
        wormhole: Object.freeze({ material: 0, time: 0 }),
      }),
      t1: Object.freeze({
        lowsec: Object.freeze({ material: 200, time: 2000 }),
        nullsec: Object.freeze({ material: 220, time: 2200 }),
        wormhole: Object.freeze({ material: 220, time: 2200 }),
      }),
      t2: Object.freeze({
        lowsec: Object.freeze({ material: 240, time: 2400 }),
        nullsec: Object.freeze({ material: 264, time: 2640 }),
        wormhole: Object.freeze({ material: 264, time: 2640 }),
      }),
    }),
  });

  const STRUCTURE_OPTIONS = Object.freeze([
    Object.freeze({ value: "unbonused", label: "No structure bonus" }),
    Object.freeze({ value: "raitaru", label: "Raitaru" }),
    Object.freeze({ value: "azbel", label: "Azbel" }),
    Object.freeze({ value: "sotiyo", label: "Sotiyo" }),
  ]);
  const SECURITY_OPTIONS = Object.freeze([
    Object.freeze({ value: "highsec", label: "Highsec" }),
    Object.freeze({ value: "lowsec", label: "Lowsec" }),
    Object.freeze({ value: "nullsec", label: "Nullsec" }),
    Object.freeze({ value: "wormhole", label: "Wormhole" }),
  ]);
  const RIG_OPTIONS = Object.freeze([
    Object.freeze({ value: "none", label: "None" }),
    Object.freeze({ value: "t1", label: "Tech I" }),
    Object.freeze({ value: "t2", label: "Tech II" }),
  ]);
  const CATEGORY_SET = new Set(CATEGORIES.map(({ category }) => category));

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function createElement(tagName, className = "", text = "") {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  function appendOptions(select, options) {
    options.forEach(({ value, label }) => select.add(new Option(label, value)));
  }

  function labelledSelect(category, key, labelText, options) {
    const label = createElement("label");
    const select = createElement("select");
    const id = `setup-override-${category}-${key}`;
    label.htmlFor = id;
    label.append(document.createTextNode(labelText));
    select.id = id;
    select.dataset[`setupOverride${key[0].toUpperCase()}${key.slice(1)}`] = "";
    appendOptions(select, options);
    label.append(select);
    return label;
  }

  function createSystemPicker(definition) {
    const wrapper = createElement("div", "system-index-row category-override-system");
    wrapper.dataset.systemPicker = "";
    wrapper.dataset.systemActivity = "manufacturing";

    const label = createElement("label");
    const searchControl = createElement("div", "system-search-control");
    const search = createElement("input");
    const systemId = createElement("input");
    const results = createElement("ul", "system-search-results");
    const indexPanel = createElement("div", "system-index");
    const indexLabel = createElement("span", "", "Index");
    const index = createElement("strong", "", "—");
    const searchId = `setup-override-${definition.category}-system-search`;
    const resultsId = `setup-override-${definition.category}-system-results`;

    label.htmlFor = searchId;
    label.append(document.createTextNode("Solar system"));
    search.id = searchId;
    search.type = "text";
    search.autocomplete = "off";
    search.spellcheck = false;
    search.placeholder = "Search systems";
    search.setAttribute("role", "combobox");
    search.setAttribute("aria-autocomplete", "list");
    search.setAttribute("aria-expanded", "false");
    search.setAttribute("aria-controls", resultsId);
    search.dataset.systemSearch = "";
    search.dataset.setupOverrideSystemSearch = "";

    systemId.type = "hidden";
    systemId.dataset.systemId = "";
    systemId.dataset.setupOverrideSystemId = "";

    results.id = resultsId;
    results.hidden = true;
    results.dataset.systemResults = "";
    results.setAttribute("role", "listbox");
    results.setAttribute("aria-label", `${definition.label} solar systems`);

    indexPanel.dataset.state = "empty";
    index.dataset.systemIndex = "";
    index.setAttribute("role", "status");
    index.setAttribute("aria-live", "polite");

    searchControl.append(search, systemId, results);
    label.append(searchControl);
    indexPanel.append(indexLabel, index);
    wrapper.append(label, indexPanel);
    return wrapper;
  }

  function createOverrideRow(definition) {
    const details = createElement("details", "category-override");
    const summary = createElement("summary", "category-override-summary");
    const name = createElement("span", "category-override-name");
    const status = createElement("span", "category-override-status", "Uses general setup");
    const body = createElement("div", "category-override-body");
    const toggle = createElement("label", "category-override-toggle");
    const checkbox = createElement("input");
    const fields = createElement("fieldset", "category-override-fields");
    const legend = createElement(
      "legend",
      "visually-hidden",
      `${definition.label} manufacturing setup`,
    );
    const grid = createElement("div", "category-override-grid");
    const checkboxId = `setup-override-${definition.category}-enabled`;

    details.dataset.setupOverride = definition.category;
    details.dataset.enabled = "false";
    details.dataset.initialized = "false";
    name.append(createElement("strong", "", definition.label));
    if (definition.note) name.append(createElement("small", "", definition.note));
    status.dataset.setupOverrideStatus = "";
    status.dataset.state = "inherited";
    summary.append(name, status);

    checkbox.id = checkboxId;
    checkbox.type = "checkbox";
    checkbox.dataset.setupOverrideEnabled = "";
    toggle.htmlFor = checkboxId;
    toggle.append(checkbox, createElement("span", "", "Override general setup"));

    fields.disabled = true;
    fields.dataset.setupOverrideFields = "";
    grid.append(
      labelledSelect(definition.category, "structure", "Structure", STRUCTURE_OPTIONS),
      labelledSelect(definition.category, "security", "Security", SECURITY_OPTIONS),
      labelledSelect(definition.category, "rig", "Rig", RIG_OPTIONS),
      createSystemPicker(definition),
    );
    fields.append(legend, grid);
    body.append(toggle, fields);
    details.append(summary, body);
    return details;
  }

  const fragment = document.createDocumentFragment();
  CATEGORIES.forEach((definition) => fragment.append(createOverrideRow(definition)));
  list.replaceChildren(fragment);

  const rows = [...list.querySelectorAll("[data-setup-override]")];
  const count = app.querySelector("[data-category-overrides-count]");

  function controlsFor(row) {
    return {
      enabled: row.querySelector("[data-setup-override-enabled]"),
      fields: row.querySelector("[data-setup-override-fields]"),
      structure: row.querySelector("[data-setup-override-structure]"),
      security: row.querySelector("[data-setup-override-security]"),
      rig: row.querySelector("[data-setup-override-rig]"),
      picker: row.querySelector("[data-system-picker]"),
      systemSearch: row.querySelector("[data-setup-override-system-search]"),
      systemId: row.querySelector("[data-setup-override-system-id]"),
      status: row.querySelector("[data-setup-override-status]"),
    };
  }

  function structureProfile(activity, structure) {
    return STRUCTURE_PROFILES[activity]?.[structure] || null;
  }

  function rigProfile(activity, rig, security) {
    return RIG_PROFILES[activity]?.[rig]?.[security] || null;
  }

  function selectedLabel(select) {
    return select.selectedOptions[0]?.textContent || select.value;
  }

  function validSystemId(value) {
    if (!/^[1-9]\d*$/.test(String(value))) return false;
    const number = Number(value);
    return Number.isSafeInteger(number) && number <= 2_147_483_647;
  }

  function updateCount() {
    if (!count) return;
    const active = rows.filter((row) => controlsFor(row).enabled.checked).length;
    count.textContent = `${active} active`;
  }

  function updateSummary(row) {
    const controls = controlsFor(row);
    if (!controls.enabled.checked) {
      controls.status.textContent = "Uses general setup";
      controls.status.dataset.state = "inherited";
      return;
    }
    const systemName = validSystemId(controls.systemId.value)
      ? controls.systemSearch.value.trim() || `System ${controls.systemId.value}`
      : "Choose a solar system";
    controls.status.textContent = [
      selectedLabel(controls.structure),
      selectedLabel(controls.rig),
      systemName,
    ].join(" · ");
    controls.status.dataset.state = validSystemId(controls.systemId.value)
      ? "active"
      : "incomplete";
  }

  function copyGeneralSetup(row) {
    const controls = controlsFor(row);
    const facility = app.querySelector('[data-facility-config="manufacturing"]');
    const pricingPicker = app.querySelector(
      '[data-pricing-details] [data-system-picker][data-system-activity="manufacturing"]',
    );
    const generalSearch = pricingPicker?.querySelector("[data-system-search]");
    const generalSystemId = pricingPicker?.querySelector("[data-system-id]");
    if (facility) {
      controls.structure.value = facility.querySelector("[data-structure-select]").value;
      controls.security.value = facility.querySelector("[data-security-select]").value;
      controls.rig.value = facility.querySelector("[data-rig-tier-select]").value;
    }
    controls.systemId.value = generalSystemId?.value || "";
    controls.systemSearch.value = generalSearch?.value || "";
    if (controls.systemId.value) {
      controls.systemSearch.dataset.solarSystemId = controls.systemId.value;
    } else {
      delete controls.systemSearch.dataset.solarSystemId;
    }
    controls.systemSearch.setCustomValidity("");
    app.dispatchEvent(new CustomEvent("industry:system-picker-refresh", {
      detail: { picker: controls.picker },
    }));
  }

  function setEnabled(row, enabled, { copyDefaults = false } = {}) {
    const controls = controlsFor(row);
    controls.enabled.checked = enabled;
    controls.fields.disabled = !enabled;
    row.dataset.enabled = enabled ? "true" : "false";
    if (enabled && copyDefaults && row.dataset.initialized !== "true") {
      copyGeneralSetup(row);
      row.dataset.initialized = "true";
    }
    if (!enabled) controls.systemSearch.setCustomValidity("");
    updateSummary(row);
    updateCount();
  }

  function capture() {
    return rows.flatMap((row) => {
      const controls = controlsFor(row);
      if (!controls.enabled.checked) return [];
      return [{
        category: row.dataset.setupOverride,
        structure: controls.structure.value,
        security: controls.security.value,
        rig: controls.rig.value,
        solar_system_id: controls.systemId.value.trim(),
      }];
    });
  }

  function normalize(raw) {
    if (raw === undefined || raw === null) return [];
    if (!Array.isArray(raw) || raw.length > CATEGORIES.length) return null;
    const seen = new Set();
    const normalized = [];
    for (const entry of raw) {
      if (!isRecord(entry)) return null;
      const category = String(entry.category ?? "");
      const structure = String(entry.structure ?? "");
      const security = String(entry.security ?? "");
      const rig = String(entry.rig ?? "");
      const solarSystemId = String(entry.solar_system_id ?? "");
      if (!CATEGORY_SET.has(category) || seen.has(category)
        || !structureProfile("manufacturing", structure)
        || !rigProfile("manufacturing", rig, security)
        || !validSystemId(solarSystemId)) {
        return null;
      }
      seen.add(category);
      normalized.push({
        category,
        structure,
        security,
        rig,
        solar_system_id: solarSystemId,
      });
    }
    return normalized.sort(
      (left, right) => CATEGORIES.findIndex(({ category }) => category === left.category)
        - CATEGORIES.findIndex(({ category }) => category === right.category),
    );
  }

  function apply(raw) {
    const normalized = normalize(raw);
    if (normalized === null) return false;
    const byCategory = new Map(normalized.map((entry) => [entry.category, entry]));
    rows.forEach((row) => {
      const controls = controlsFor(row);
      const stored = byCategory.get(row.dataset.setupOverride);
      controls.structure.value = stored?.structure || "unbonused";
      controls.security.value = stored?.security || "highsec";
      controls.rig.value = stored?.rig || "none";
      controls.systemId.value = stored?.solar_system_id || "";
      controls.systemSearch.value = "";
      delete controls.systemSearch.dataset.solarSystemId;
      controls.systemSearch.setCustomValidity("");
      row.dataset.initialized = stored ? "true" : "false";
      setEnabled(row, Boolean(stored));
    });
    return true;
  }

  function sourceControls() {
    return [...list.querySelectorAll([
      "[data-setup-override-enabled]",
      "[data-setup-override-structure]",
      "[data-setup-override-security]",
      "[data-setup-override-rig]",
      "[data-setup-override-system-id]",
    ].join(", "))];
  }

  function validate({ report = false } = {}) {
    let invalid = null;
    rows.forEach((row) => {
      const controls = controlsFor(row);
      const valid = !controls.enabled.checked || validSystemId(controls.systemId.value);
      controls.systemSearch.setCustomValidity(
        valid ? "" : "Select a solar system from the results.",
      );
      if (!valid && !invalid) {
        invalid = controls.systemSearch;
        row.open = true;
      }
    });
    if (invalid && report) {
      invalid.reportValidity();
      invalid.focus();
    }
    return { ok: !invalid, invalid };
  }

  function readRequest() {
    const validation = validate();
    if (!validation.ok) return { ok: false, value: null, invalid: validation.invalid };
    return {
      ok: true,
      value: capture().map((entry) => {
        const structure = structureProfile("manufacturing", entry.structure);
        const rig = rigProfile("manufacturing", entry.rig, entry.security);
        return {
          category: entry.category,
          solar_system_id: Number(entry.solar_system_id),
          facility_material_reduction_basis_points: structure.material,
          facility_time_reduction_basis_points: structure.time,
          rig_material_reduction_basis_points: rig.material,
          rig_time_reduction_basis_points: rig.time,
          job_cost_reduction_basis_points: structure.cost,
        };
      }),
    };
  }

  list.addEventListener("change", (event) => {
    const row = event.target.closest?.("[data-setup-override]");
    if (!row) return;
    if (event.target.matches("[data-setup-override-enabled]")) {
      setEnabled(row, event.target.checked, { copyDefaults: event.target.checked });
    } else {
      updateSummary(row);
    }
    if (event.target.matches([
      "[data-setup-override-enabled]",
      "[data-setup-override-structure]",
      "[data-setup-override-security]",
      "[data-setup-override-rig]",
      "[data-setup-override-system-id]",
    ].join(", "))) {
      app.dispatchEvent(new CustomEvent("industry:setup-overrides-changed"));
    }
  });
  list.addEventListener("input", (event) => {
    const row = event.target.closest?.("[data-setup-override]");
    if (row) updateSummary(row);
  });
  app.addEventListener("industry:system-picker-resolved", (event) => {
    const row = event.detail?.picker?.closest?.("[data-setup-override]");
    if (row && list.contains(row)) updateSummary(row);
  });

  rows.forEach((row) => setEnabled(row, false));

  globalThis.industrySetupOverrides = Object.freeze({
    categories: CATEGORIES,
    structureProfile,
    rigProfile,
    capture,
    normalize,
    apply,
    sourceControls,
    validate,
    readRequest,
  });
})();
