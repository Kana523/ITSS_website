(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const STORAGE_KEY = "itss_industry_configurations_v1";
  const DRAFT_KEY = "itss_industry_configuration_draft_v1";
  const SCHEMA_VERSION = 1;
  const MAX_CONFIGURATIONS = 25;
  const DRAFT_SAVE_DELAY_MS = 250;

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

  // Exact final basis-point reductions. Reaction rigs deliberately use different
  // security scaling from manufacturing rigs in current EVE dogma data.
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

  const activityPanels = [...app.querySelectorAll("[data-activity-config]")];
  const elements = {
    name: app.querySelector("[data-config-name]"),
    select: app.querySelector("[data-config-select]"),
    save: app.querySelector("[data-config-save]"),
    load: app.querySelector("[data-config-load]"),
    createNew: app.querySelector("[data-config-new]"),
    delete: app.querySelector("[data-config-delete]"),
    count: app.querySelector("[data-config-count]"),
    status: app.querySelector("[data-config-status]"),
    pricingEnabled: app.querySelector("[data-pricing-enabled]"),
  };

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function selectOptionExists(select, value) {
    return Boolean(select && [...select.options].some((option) => option.value === String(value)));
  }

  function basisPointsToInputValue(basisPoints) {
    const whole = Math.floor(basisPoints / 100);
    const fraction = String(basisPoints % 100).padStart(2, "0").replace(/0+$/, "");
    return fraction ? `${whole}.${fraction}` : String(whole);
  }

  function formatCombinedReduction(facilityBasisPoints, rigBasisPoints) {
    const remaining = (10_000 - facilityBasisPoints) * (10_000 - rigBasisPoints);
    const scaledPercent = 100_000_000 - remaining;
    const whole = Math.floor(scaledPercent / 1_000_000);
    const fraction = String(scaledPercent % 1_000_000)
      .padStart(6, "0")
      .replace(/0+$/, "");
    return `${fraction ? `${whole}.${fraction}` : whole}%`;
  }

  function formatBasisPoints(basisPoints) {
    return `${basisPointsToInputValue(basisPoints)}%`;
  }

  function derivedInput(kind, activity, effect) {
    return app.querySelector(
      `[data-profile-modifier="${kind}"][data-profile-activity="${activity}"][data-profile-effect="${effect}"]`,
    );
  }

  function updateActivity(panel, { notify = false } = {}) {
    const activity = panel.dataset.activityConfig;
    const structureSelect = panel.querySelector("[data-structure-select]");
    const securitySelect = panel.querySelector("[data-security-select]");
    const rigSelect = panel.querySelector("[data-rig-tier-select]");
    const structure = STRUCTURE_PROFILES[activity]?.[structureSelect?.value];
    const rig = RIG_PROFILES[activity]?.[rigSelect?.value]?.[securitySelect?.value];
    if (!structure || !rig) return false;

    const facilityMaterial = derivedInput("facility", activity, "material");
    const facilityTime = derivedInput("facility", activity, "time");
    const rigMaterial = derivedInput("rig", activity, "material");
    const rigTime = derivedInput("rig", activity, "time");
    if (!facilityMaterial || !facilityTime || !rigMaterial || !rigTime) return false;

    facilityMaterial.value = basisPointsToInputValue(structure.material);
    facilityTime.value = basisPointsToInputValue(structure.time);
    rigMaterial.value = basisPointsToInputValue(rig.material);
    rigTime.value = basisPointsToInputValue(rig.time);

    const materialReadout = panel.querySelector('[data-effective-modifier="material"]');
    const timeReadout = panel.querySelector('[data-effective-modifier="time"]');
    const costReadout = panel.querySelector('[data-effective-modifier="cost"]');
    if (materialReadout) {
      materialReadout.textContent = formatCombinedReduction(structure.material, rig.material);
    }
    if (timeReadout) {
      timeReadout.textContent = formatCombinedReduction(structure.time, rig.time);
    }
    if (costReadout) costReadout.textContent = formatBasisPoints(structure.cost);

    const jobCostInput = app.querySelector(`[data-derived-job-cost="${activity}"]`);
    if (jobCostInput) jobCostInput.value = basisPointsToInputValue(structure.cost);

    if (notify) {
      facilityMaterial.dispatchEvent(new Event("input", { bubbles: true }));
      jobCostInput?.dispatchEvent(new Event("input", { bubbles: true }));
    }
    return true;
  }

  function updateAllActivities(options) {
    activityPanels.forEach((panel) => updateActivity(panel, options));
  }

  function profileSkillInputs() {
    return [...app.querySelectorAll("[data-profile-skill]")];
  }

  function sourcePricingPercentInputs() {
    return [...app.querySelectorAll("[data-pricing-percent]:not([data-derived-job-cost])")];
  }

  function pricingIntegerInputs() {
    return [...app.querySelectorAll("[data-pricing-integer]")];
  }

  function sourceControls() {
    return [
      ...profileSkillInputs(),
      ...app.querySelectorAll("[data-profile-implant]"),
      ...app.querySelectorAll(
        "[data-structure-select], [data-security-select], [data-rig-tier-select]",
      ),
      ...pricingIntegerInputs(),
      ...sourcePricingPercentInputs(),
      elements.pricingEnabled,
    ].filter(Boolean);
  }

  function captureConfiguration() {
    const skills = {};
    profileSkillInputs().forEach((input) => {
      skills[input.dataset.profileSkill] = Number(input.value);
    });

    const activities = {};
    activityPanels.forEach((panel) => {
      const activity = panel.dataset.activityConfig;
      activities[activity] = {
        structure: panel.querySelector("[data-structure-select]").value,
        security: panel.querySelector("[data-security-select]").value,
        rig: panel.querySelector("[data-rig-tier-select]").value,
      };
    });

    const integers = {};
    pricingIntegerInputs().forEach((input) => {
      integers[input.dataset.pricingInteger] = input.value.trim();
    });
    const percents = {};
    sourcePricingPercentInputs().forEach((input) => {
      percents[input.dataset.pricingPercent] = input.value.trim();
    });

    return {
      skills,
      manufacturing_time_implant: app.querySelector("[data-profile-implant]")?.value || "",
      activities,
      pricing: {
        enabled: Boolean(elements.pricingEnabled?.checked),
        integers,
        percents,
      },
    };
  }

  function normalizedFieldValue(input, rawValue) {
    if (typeof rawValue !== "string" && typeof rawValue !== "number") return null;
    const value = String(rawValue);
    if (!value) return input.hasAttribute("data-pricing-optional") ? "" : null;
    if (input.hasAttribute("data-pricing-integer") && !/^\d+$/.test(value)) return null;
    if (input.hasAttribute("data-pricing-percent") && !/^\d+(?:\.\d{1,2})?$/.test(value)) {
      return null;
    }
    if (input.type === "number") {
      const number = Number(value);
      const minimum = input.min === "" ? Number.NEGATIVE_INFINITY : Number(input.min);
      const maximum = input.max === "" ? Number.POSITIVE_INFINITY : Number(input.max);
      if (!Number.isFinite(number) || number < minimum || number > maximum) return null;
    }
    const previous = input.value;
    input.value = value;
    const valid = input.checkValidity();
    input.value = previous;
    return valid ? value : null;
  }

  function normalizeConfiguration(raw) {
    if (!isRecord(raw) || !isRecord(raw.skills) || !isRecord(raw.activities)) return null;
    if (!isRecord(raw.pricing) || !isRecord(raw.pricing.integers)
      || !isRecord(raw.pricing.percents) || typeof raw.pricing.enabled !== "boolean") {
      return null;
    }

    const normalized = {
      skills: {},
      manufacturing_time_implant: "",
      activities: {},
      pricing: { enabled: raw.pricing.enabled, integers: {}, percents: {} },
    };

    for (const input of profileSkillInputs()) {
      const value = String(raw.skills[input.dataset.profileSkill]);
      if (!selectOptionExists(input, value)) return null;
      normalized.skills[input.dataset.profileSkill] = Number(value);
    }

    const implant = app.querySelector("[data-profile-implant]");
    const implantValue = String(raw.manufacturing_time_implant ?? "");
    if (implant && !selectOptionExists(implant, implantValue)) return null;
    normalized.manufacturing_time_implant = implantValue;

    for (const panel of activityPanels) {
      const activity = panel.dataset.activityConfig;
      const rawActivity = raw.activities[activity];
      if (!isRecord(rawActivity)) return null;
      const structure = String(rawActivity.structure ?? "");
      const security = String(rawActivity.security ?? "");
      const rig = String(rawActivity.rig ?? "");
      if (!selectOptionExists(panel.querySelector("[data-structure-select]"), structure)
        || !selectOptionExists(panel.querySelector("[data-security-select]"), security)
        || !selectOptionExists(panel.querySelector("[data-rig-tier-select]"), rig)) {
        return null;
      }
      normalized.activities[activity] = { structure, security, rig };
    }

    for (const input of pricingIntegerInputs()) {
      const key = input.dataset.pricingInteger;
      const value = normalizedFieldValue(input, raw.pricing.integers[key]);
      if (value === null) return null;
      normalized.pricing.integers[key] = value;
    }
    for (const input of sourcePricingPercentInputs()) {
      const key = input.dataset.pricingPercent;
      const value = normalizedFieldValue(input, raw.pricing.percents[key]);
      if (value === null) return null;
      normalized.pricing.percents[key] = value;
    }
    return normalized;
  }

  function applyConfiguration(raw) {
    const configuration = normalizeConfiguration(raw);
    if (!configuration) return false;

    profileSkillInputs().forEach((input) => {
      input.value = String(configuration.skills[input.dataset.profileSkill]);
    });
    const implant = app.querySelector("[data-profile-implant]");
    if (implant) implant.value = configuration.manufacturing_time_implant;

    activityPanels.forEach((panel) => {
      const values = configuration.activities[panel.dataset.activityConfig];
      panel.querySelector("[data-structure-select]").value = values.structure;
      panel.querySelector("[data-security-select]").value = values.security;
      panel.querySelector("[data-rig-tier-select]").value = values.rig;
    });

    if (elements.pricingEnabled) elements.pricingEnabled.checked = configuration.pricing.enabled;
    pricingIntegerInputs().forEach((input) => {
      input.value = configuration.pricing.integers[input.dataset.pricingInteger];
      input.setCustomValidity("");
    });
    sourcePricingPercentInputs().forEach((input) => {
      input.value = configuration.pricing.percents[input.dataset.pricingPercent];
      input.setCustomValidity("");
    });

    updateAllActivities({ notify: false });
    profileSkillInputs()[0]?.dispatchEvent(new Event("input", { bubbles: true }));
    elements.pricingEnabled?.dispatchEvent(new Event("change", { bubbles: true }));
    queueDraftSave();
    return true;
  }

  function emptyStore() {
    return { schema_version: SCHEMA_VERSION, active_configuration_id: null, configurations: [] };
  }

  function normalizeStoredEntry(raw) {
    if (!isRecord(raw) || typeof raw.id !== "string" || !raw.id || raw.id.length > 100) return null;
    if (typeof raw.name !== "string") return null;
    const name = raw.name.trim();
    if (!name || name.length > 60) return null;
    const configuration = normalizeConfiguration(raw.configuration);
    if (!configuration) return null;
    return {
      id: raw.id,
      name,
      created_at: typeof raw.created_at === "string" ? raw.created_at : "",
      updated_at: typeof raw.updated_at === "string" ? raw.updated_at : "",
      configuration,
    };
  }

  function readStore() {
    try {
      const serialized = window.localStorage.getItem(STORAGE_KEY);
      if (!serialized) return { store: emptyStore(), warning: "" };
      const raw = JSON.parse(serialized);
      if (!isRecord(raw) || raw.schema_version !== SCHEMA_VERSION
        || !Array.isArray(raw.configurations)) {
        return { store: emptyStore(), warning: "Saved configurations use an unsupported format." };
      }
      const configurations = [];
      const ids = new Set();
      let skipped = 0;
      raw.configurations.slice(0, MAX_CONFIGURATIONS).forEach((entry) => {
        const normalized = normalizeStoredEntry(entry);
        if (!normalized || ids.has(normalized.id)) {
          skipped += 1;
          return;
        }
        ids.add(normalized.id);
        configurations.push(normalized);
      });
      const activeId = typeof raw.active_configuration_id === "string"
        && ids.has(raw.active_configuration_id)
        ? raw.active_configuration_id
        : null;
      return {
        store: {
          schema_version: SCHEMA_VERSION,
          active_configuration_id: activeId,
          configurations,
        },
        warning: skipped ? `${skipped} invalid saved configuration${skipped === 1 ? " was" : "s were"} skipped.` : "",
      };
    } catch (_error) {
      return { store: emptyStore(), warning: "Saved configurations could not be read in this browser." };
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (_error) {
      return false;
    }
  }

  function configurationId() {
    if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
    return `config-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function setStatus(message) {
    if (elements.status) elements.status.textContent = message;
  }

  let storeResult = readStore();
  let store = storeResult.store;
  let draftTimer = null;

  function renderSavedConfigurations(selectedId = store.active_configuration_id) {
    if (!elements.select) return;
    elements.select.replaceChildren(new Option("Choose a configuration", ""));
    [...store.configurations]
      .sort((left, right) => left.name.localeCompare(right.name))
      .forEach((configuration) => {
        elements.select.append(new Option(configuration.name, configuration.id));
      });
    elements.select.value = selectedId && store.configurations.some(({ id }) => id === selectedId)
      ? selectedId
      : "";
    const hasSelection = Boolean(elements.select.value);
    if (elements.load) elements.load.disabled = !hasSelection;
    if (elements.delete) elements.delete.disabled = !hasSelection;
    if (elements.count) {
      const count = store.configurations.length;
      elements.count.textContent = `${count} saved`;
    }
  }

  function saveDraft() {
    draftTimer = null;
    if (!writeStorage(DRAFT_KEY, {
      schema_version: SCHEMA_VERSION,
      configuration: captureConfiguration(),
    })) {
      setStatus("Browser storage is unavailable; changes will last only for this tab.");
    }
  }

  function queueDraftSave() {
    window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(saveDraft, DRAFT_SAVE_DELAY_MS);
  }

  function restoreDraft() {
    try {
      const serialized = window.localStorage.getItem(DRAFT_KEY);
      if (!serialized) return false;
      const raw = JSON.parse(serialized);
      if (!isRecord(raw) || raw.schema_version !== SCHEMA_VERSION) return false;
      return applyConfiguration(raw.configuration);
    } catch (_error) {
      return false;
    }
  }

  activityPanels.forEach((panel) => {
    panel.querySelectorAll("[data-structure-select], [data-security-select], [data-rig-tier-select]")
      .forEach((select) => select.addEventListener("change", () => {
        updateActivity(panel, { notify: true });
        queueDraftSave();
      }));
  });

  sourceControls().forEach((input) => {
    const eventName = input.matches('input[type="number"], input[type="text"]') ? "input" : "change";
    input.addEventListener(eventName, queueDraftSave);
  });

  elements.select?.addEventListener("change", () => {
    const selected = store.configurations.find(({ id }) => id === elements.select.value);
    const hasSelection = Boolean(selected);
    if (elements.load) elements.load.disabled = !hasSelection;
    if (elements.delete) elements.delete.disabled = !hasSelection;
    if (selected && elements.name) elements.name.value = selected.name;
  });

  elements.createNew?.addEventListener("click", () => {
    elements.select.value = "";
    elements.name.value = "";
    elements.load.disabled = true;
    elements.delete.disabled = true;
    elements.name.focus();
    setStatus("Enter a name to save the current settings as a new configuration.");
  });

  elements.save?.addEventListener("click", () => {
    const name = elements.name.value.trim();
    if (!name) {
      setStatus("Enter a configuration name before saving.");
      elements.name.focus();
      return;
    }

    const invalid = sourceControls().find((input) => !input.checkValidity());
    if (invalid) {
      setStatus("Fix the highlighted setting before saving.");
      invalid.reportValidity();
      invalid.focus();
      return;
    }

    const configuration = normalizeConfiguration(captureConfiguration());
    if (!configuration) {
      setStatus("The current settings could not be saved.");
      return;
    }

    const selectedId = elements.select.value;
    const matchingName = store.configurations.find(
      (entry) => entry.name.localeCompare(name, undefined, { sensitivity: "accent" }) === 0,
    );
    const existing = store.configurations.find(({ id }) => id === selectedId) || matchingName;
    if (!existing && store.configurations.length >= MAX_CONFIGURATIONS) {
      setStatus(`You can save up to ${MAX_CONFIGURATIONS} configurations.`);
      return;
    }

    const now = new Date().toISOString();
    const saved = {
      id: existing?.id || configurationId(),
      name,
      created_at: existing?.created_at || now,
      updated_at: now,
      configuration,
    };
    const configurations = existing
      ? store.configurations.map((entry) => (entry.id === existing.id ? saved : entry))
      : [...store.configurations, saved];
    const nextStore = {
      schema_version: SCHEMA_VERSION,
      active_configuration_id: saved.id,
      configurations,
    };
    if (!writeStorage(STORAGE_KEY, nextStore)) {
      setStatus("The configuration could not be written to browser storage.");
      return;
    }
    store = nextStore;
    renderSavedConfigurations(saved.id);
    elements.name.value = saved.name;
    queueDraftSave();
    setStatus(existing ? `Updated ${saved.name}.` : `Saved ${saved.name}.`);
  });

  elements.load?.addEventListener("click", () => {
    const selected = store.configurations.find(({ id }) => id === elements.select.value);
    if (!selected) return;
    if (!applyConfiguration(selected.configuration)) {
      setStatus(`${selected.name} is no longer compatible with this calculator.`);
      return;
    }
    const nextStore = { ...store, active_configuration_id: selected.id };
    if (writeStorage(STORAGE_KEY, nextStore)) store = nextStore;
    elements.name.value = selected.name;
    setStatus(`Loaded ${selected.name}. Calculate to refresh the route.`);
  });

  elements.delete?.addEventListener("click", () => {
    const selected = store.configurations.find(({ id }) => id === elements.select.value);
    if (!selected || !window.confirm(`Delete the local configuration "${selected.name}"?`)) return;
    const nextStore = {
      schema_version: SCHEMA_VERSION,
      active_configuration_id: null,
      configurations: store.configurations.filter(({ id }) => id !== selected.id),
    };
    if (!writeStorage(STORAGE_KEY, nextStore)) {
      setStatus("The configuration could not be removed from browser storage.");
      return;
    }
    store = nextStore;
    renderSavedConfigurations("");
    elements.name.value = "";
    setStatus(`Deleted ${selected.name}.`);
  });

  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY) return;
    storeResult = readStore();
    store = storeResult.store;
    renderSavedConfigurations();
    setStatus("The saved configuration list changed in another tab.");
  });

  updateAllActivities({ notify: false });
  renderSavedConfigurations();
  const restoredDraft = restoreDraft();
  if (store.active_configuration_id) {
    const active = store.configurations.find(({ id }) => id === store.active_configuration_id);
    if (active && elements.name) elements.name.value = active.name;
  }
  if (storeResult.warning) setStatus(storeResult.warning);
  else if (restoredDraft) setStatus("Restored your last local settings.");

})();
