(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const STORAGE_KEY = "itss_industry_configurations_v1";
  const DRAFT_KEY = "itss_industry_configuration_draft_v1";
  const SCHEMA_VERSION = 1;
  const MAX_CONFIGURATIONS = 25;
  const DRAFT_SAVE_DELAY_MS = 250;
  const setupOverrides = globalThis.industrySetupOverrides;
  if (!setupOverrides) return;

  const activityPanels = [...app.querySelectorAll("[data-activity-config]")];
  const facilityPanels = [...app.querySelectorAll("[data-facility-config]")];
  const elements = {
    name: app.querySelector("[data-config-name]"),
    select: app.querySelector("[data-config-select]"),
    save: app.querySelector("[data-config-save]"),
    createNew: app.querySelector("[data-config-new]"),
    delete: app.querySelector("[data-config-delete]"),
    count: app.querySelector("[data-config-count]"),
    status: app.querySelector("[data-config-status]"),
    activeProfile: app.querySelector("[data-active-profile-name]"),
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

  function coverageInput(panel, scope) {
    return panel.querySelector(`[data-rig-scope="${scope}"]`);
  }

  function coverageIds(value) {
    if (value === "") return [];
    if (typeof value !== "string" || !/^\d+(?:,\d+)*$/.test(value)) return null;
    const ids = value.split(",").map(Number);
    return ids.length <= 100 && new Set(ids).size === ids.length
      && ids.every((id) => Number.isSafeInteger(id) && id > 0 && id <= 2_147_483_647)
      ? ids : null;
  }

  function restoreCoverageSelection(panel) {
    const select = panel.querySelector("[data-rig-coverage]");
    if (!select) return;
    const categories = coverageIds(coverageInput(panel, "category_ids").value) || [];
    const groups = coverageIds(coverageInput(panel, "group_ids").value) || [];
    for (const option of select.options) {
      const [kind, id] = option.value.split(":");
      option.selected = (kind === "category" ? categories : groups).includes(Number(id));
    }
  }

  async function loadCoverage(panel) {
    const select = panel.querySelector("[data-rig-coverage]");
    if (!select) return;
    const status = panel.querySelector("[data-rig-coverage-status]");
    select.dataset.loaded = "false";
    const configured = document.body.dataset.industryApiBase?.trim();
    const base = configured ? configured.replace(/\/$/, "")
      : ["127.0.0.1", "localhost"].includes(window.location.hostname) ? "http://127.0.0.1:8000" : "";
    try {
      const response = await fetch(`${base}/api/industry/rig-scopes?activity=${panel.dataset.activityConfig}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Coverage unavailable");
      const groups = await response.json();
      if (!Array.isArray(groups)) throw new Error("Invalid coverage");
      select.replaceChildren();
      const categories = new Map(groups.map((group) => [group.category_id, group.category_name]));
      for (const [id, name] of categories) {
        const section = document.createElement("optgroup");
        section.label = name;
        section.append(new Option(`All ${name}`, `category:${id}`));
        for (const group of groups.filter((entry) => entry.category_id === id)) {
          section.append(new Option(group.group_name, `group:${group.group_id}`));
        }
        select.append(section);
      }
      select.dataset.loaded = "true";
      restoreCoverageSelection(panel);
      status.textContent = "Bonuses apply to the selected categories and groups only.";
    } catch (_error) {
      status.textContent = "Product coverage unavailable. Reload to retry before using rigs.";
    }
    updateActivity(panel, { notify: true });
  }

  function validateFacilities() {
    const systems = globalThis.industrySystems?.validate();
    if (!systems?.ok) return systems || { ok: false, invalid: null };
    for (const panel of activityPanels) {
      const select = panel.querySelector("[data-rig-coverage]");
      const rig = panel.querySelector("[data-rig-tier-select]");
      select.setCustomValidity("");
      if (rig.value === "none") continue;
      const categories = coverageIds(coverageInput(panel, "category_ids").value);
      const groups = coverageIds(coverageInput(panel, "group_ids").value);
      const options = new Set([...select.options].map((option) => option.value));
      const valid = select.dataset.loaded === "true" && categories && groups
        && categories.length + groups.length > 0
        && categories.every((id) => options.has(`category:${id}`))
        && groups.every((id) => options.has(`group:${id}`));
      if (!valid) {
        select.setCustomValidity("Select the product coverage of your installed rigs. Saved coverage must be available for this activity.");
        return { ok: false, invalid: select };
      }
    }
    return { ok: true, invalid: null };
  }

  function updateActivity(panel, { notify = false } = {}) {
    const activity = panel.dataset.activityConfig;
    const structureSelect = panel.querySelector("[data-structure-select]");
    const securitySelect = panel.querySelector("[data-security-select]");
    const rigSelect = panel.querySelector("[data-rig-tier-select]");
    const structure = setupOverrides.structureProfile(activity, structureSelect?.value);
    const picker = app.querySelector(`[data-pricing-details] [data-system-picker][data-system-activity="${activity}"]`);
    const security = picker?.dataset.securitySpace || "";
    securitySelect.value = security;
    const rig = setupOverrides.rigProfile(activity, rigSelect?.value, security) || { material: 0, time: 0 };
    if (!structure) return false;
    const coverage = panel.querySelector("[data-rig-coverage]");
    coverage.disabled = rigSelect.value === "none";
    if (coverage.disabled) coverage.setCustomValidity("");

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

  function skillStorageKey(input) {
    return input.dataset.skillTypeId || input.dataset.profileSkill;
  }

  function sourcePricingPercentInputs() {
    return [...app.querySelectorAll(
      "[data-pricing-percent]:not([data-derived-job-cost]), [data-config-percent]",
    )];
  }

  function sourcePricingIntegerInputs() {
    return [...app.querySelectorAll("[data-pricing-integer], [data-config-integer]")];
  }

  function sourceChoiceInputs() {
    return [...app.querySelectorAll("[data-config-choice]")];
  }

  function pricingStorageKey(input) {
    return input.dataset.pricingInteger
      || input.dataset.pricingPercent
      || input.dataset.configInteger
      || input.dataset.configPercent
      || input.dataset.configChoice;
  }

  function sourceControls() {
    return [
      ...profileSkillInputs(),
      ...app.querySelectorAll("[data-profile-implant]"),
      ...app.querySelectorAll(
        "[data-structure-select], [data-security-select], [data-rig-tier-select], "
        + "[data-reprocessing-material-skill]",
      ),
      ...sourcePricingIntegerInputs(),
      ...sourcePricingPercentInputs(),
      ...sourceChoiceInputs(),
      ...app.querySelectorAll("[data-rig-coverage]"),
      ...setupOverrides.sourceControls(),
    ].filter(Boolean);
  }

  function captureConfiguration() {
    const skills = {};
    profileSkillInputs().forEach((input) => {
      skills[skillStorageKey(input)] = Number(input.value);
    });

    const activities = {};
    facilityPanels.forEach((panel) => {
      const activity = panel.dataset.facilityConfig;
      activities[activity] = {
        structure: panel.querySelector("[data-structure-select]").value,
        security: panel.querySelector("[data-security-select]").value,
        rig: panel.querySelector("[data-rig-tier-select]").value,
      };
      if (panel.querySelector("[data-rig-coverage]")) {
        activities[activity].category_ids = coverageInput(panel, "category_ids").value;
        activities[activity].group_ids = coverageInput(panel, "group_ids").value;
      }
      const materialSkillSelect = panel.querySelector("[data-reprocessing-material-skill]");
      if (materialSkillSelect) {
        activities[activity].material_skill_type_id = materialSkillSelect.value;
      }
    });

    const integers = {};
    sourcePricingIntegerInputs().forEach((input) => {
      integers[pricingStorageKey(input)] = input.value.trim();
    });
    const percents = {};
    sourcePricingPercentInputs().forEach((input) => {
      percents[pricingStorageKey(input)] = input.value.trim();
    });
    const choices = {};
    sourceChoiceInputs().forEach((input) => {
      choices[pricingStorageKey(input)] = input.value;
    });

    return {
      skills,
      manufacturing_time_implant: app.querySelector(
        '[data-profile-implant="manufacturing_time_implant"]',
      )?.value || "",
      reprocessing_yield_implant: app.querySelector(
        '[data-profile-implant="reprocessing_yield_implant"]',
      )?.value || "",
      activities,
      setup_overrides: setupOverrides.capture(),
      pricing: {
        integers,
        percents,
        choices,
      },
    };
  }

  function normalizedFieldValue(input, rawValue) {
    if (typeof rawValue !== "string" && typeof rawValue !== "number") return null;
    const value = String(rawValue);
    if (!value) return input.hasAttribute("data-pricing-optional") ? "" : null;
    if (input.matches("[data-pricing-integer], [data-config-integer]")) {
      if (!/^\d+$/.test(value)) return null;
      const number = Number(value);
      if (!Number.isSafeInteger(number) || number < 1 || number > 2_147_483_647) {
        return null;
      }
    }
    if (input.matches("[data-pricing-percent], [data-config-percent]")
      && !/^\d+(?:\.\d{1,2})?$/.test(value)) {
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
      || !isRecord(raw.pricing.percents)) {
      return null;
    }

    const normalized = {
      skills: {},
      manufacturing_time_implant: "",
      reprocessing_yield_implant: "",
      activities: {},
      setup_overrides: [],
      pricing: { integers: {}, percents: {}, choices: {} },
    };

    const normalizedOverrides = setupOverrides.normalize(raw.setup_overrides);
    if (normalizedOverrides === null) return null;
    normalized.setup_overrides = normalizedOverrides;

    for (const input of profileSkillInputs()) {
      const key = skillStorageKey(input);
      const legacyKey = input.dataset.productionProfileField;
      const rawValue = raw.skills[key] ?? (legacyKey ? raw.skills[legacyKey] : undefined) ?? 0;
      const value = String(rawValue);
      if (!selectOptionExists(input, value)) return null;
      normalized.skills[key] = Number(value);
    }

    const manufacturingImplant = app.querySelector(
      '[data-profile-implant="manufacturing_time_implant"]',
    );
    const manufacturingImplantValue = String(raw.manufacturing_time_implant ?? "");
    if (manufacturingImplant
      && !selectOptionExists(manufacturingImplant, manufacturingImplantValue)) return null;
    normalized.manufacturing_time_implant = manufacturingImplantValue;

    const reprocessingImplant = app.querySelector(
      '[data-profile-implant="reprocessing_yield_implant"]',
    );
    const reprocessingImplantValue = String(raw.reprocessing_yield_implant ?? "");
    if (reprocessingImplant
      && !selectOptionExists(reprocessingImplant, reprocessingImplantValue)) return null;
    normalized.reprocessing_yield_implant = reprocessingImplantValue;

    for (const panel of facilityPanels) {
      const activity = panel.dataset.facilityConfig;
      const storedActivity = raw.activities[activity];
      const rawActivity = isRecord(storedActivity)
        ? storedActivity
        : activity === "reprocessing" ? {} : null;
      if (!rawActivity) return null;
      const structureSelect = panel.querySelector("[data-structure-select]");
      const securitySelect = panel.querySelector("[data-security-select]");
      const rigSelect = panel.querySelector("[data-rig-tier-select]");
      const materialSkillSelect = panel.querySelector("[data-reprocessing-material-skill]");
      const structure = String(rawActivity.structure ?? structureSelect.value);
      const security = String(rawActivity.security ?? securitySelect.value);
      const rig = String(rawActivity.rig ?? rigSelect.value);
      const materialSkillTypeId = String(
        rawActivity.material_skill_type_id ?? materialSkillSelect?.value ?? "",
      );
      if (!selectOptionExists(structureSelect, structure)
        || !selectOptionExists(securitySelect, security)
        || !selectOptionExists(rigSelect, rig)
        || (materialSkillSelect
          && !selectOptionExists(materialSkillSelect, materialSkillTypeId))) {
        return null;
      }
      normalized.activities[activity] = { structure, security, rig };
      if (panel.querySelector("[data-rig-coverage]")) {
        for (const scope of ["category_ids", "group_ids"]) {
          const value = rawActivity[scope] ?? "";
          if (coverageIds(value) === null) return null;
          normalized.activities[activity][scope] = value;
        }
      }
      if (materialSkillSelect) {
        normalized.activities[activity].material_skill_type_id = materialSkillTypeId;
      }
    }

    for (const input of sourcePricingIntegerInputs()) {
      const key = pricingStorageKey(input);
      const rawValue = raw.pricing.integers[key] ?? input.defaultValue;
      const value = normalizedFieldValue(input, rawValue);
      if (value === null) return null;
      normalized.pricing.integers[key] = value;
    }
    for (const input of sourcePricingPercentInputs()) {
      const key = pricingStorageKey(input);
      const rawValue = raw.pricing.percents[key] ?? input.defaultValue;
      const value = normalizedFieldValue(input, rawValue);
      if (value === null) return null;
      normalized.pricing.percents[key] = value;
    }
    const rawChoices = isRecord(raw.pricing.choices) ? raw.pricing.choices : {};
    for (const input of sourceChoiceInputs()) {
      const key = pricingStorageKey(input);
      const value = String(rawChoices[key] ?? input.value);
      if (!selectOptionExists(input, value)) return null;
      normalized.pricing.choices[key] = value;
    }
    return normalized;
  }

  function applyConfiguration(raw) {
    const configuration = normalizeConfiguration(raw);
    if (!configuration) return false;

    profileSkillInputs().forEach((input) => {
      input.value = String(configuration.skills[skillStorageKey(input)]);
    });
    const manufacturingImplant = app.querySelector(
      '[data-profile-implant="manufacturing_time_implant"]',
    );
    if (manufacturingImplant) {
      manufacturingImplant.value = configuration.manufacturing_time_implant;
    }
    const reprocessingImplant = app.querySelector(
      '[data-profile-implant="reprocessing_yield_implant"]',
    );
    if (reprocessingImplant) {
      reprocessingImplant.value = configuration.reprocessing_yield_implant;
    }

    facilityPanels.forEach((panel) => {
      const values = configuration.activities[panel.dataset.facilityConfig];
      panel.querySelector("[data-structure-select]").value = values.structure;
      panel.querySelector("[data-security-select]").value = values.security;
      panel.querySelector("[data-rig-tier-select]").value = values.rig;
      if (panel.querySelector("[data-rig-coverage]")) {
        for (const scope of ["category_ids", "group_ids"]) coverageInput(panel, scope).value = values[scope];
        restoreCoverageSelection(panel);
      }
      const materialSkillSelect = panel.querySelector("[data-reprocessing-material-skill]");
      if (materialSkillSelect) {
        materialSkillSelect.value = values.material_skill_type_id;
      }
    });

    sourcePricingIntegerInputs().forEach((input) => {
      input.value = configuration.pricing.integers[pricingStorageKey(input)];
      input.setCustomValidity("");
    });
    sourcePricingPercentInputs().forEach((input) => {
      input.value = configuration.pricing.percents[pricingStorageKey(input)];
      input.setCustomValidity("");
    });
    sourceChoiceInputs().forEach((input) => {
      input.value = configuration.pricing.choices[pricingStorageKey(input)];
    });
    if (!setupOverrides.apply(configuration.setup_overrides)) return false;

    updateAllActivities({ notify: false });
    profileSkillInputs()[0]?.dispatchEvent(new Event("input", { bubbles: true }));
    app.dispatchEvent(new CustomEvent("industry:configuration-applied"));
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

  function setProfileNameEntry(active) {
    if (elements.select) elements.select.hidden = active;
    if (elements.name) elements.name.hidden = !active;
  }

  function setActiveProfile(configuration = null) {
    const name = configuration?.name || "Default";
    if (elements.activeProfile) elements.activeProfile.textContent = name;
  }

  const defaultConfiguration = normalizeConfiguration(captureConfiguration());
  let storeResult = readStore();
  let store = storeResult.store;
  let draftTimer = null;

  function renderSavedConfigurations(selectedId = store.active_configuration_id) {
    if (!elements.select) return;
    elements.select.replaceChildren(new Option("Default", ""));
    [...store.configurations]
      .sort((left, right) => left.name.localeCompare(right.name))
      .forEach((configuration) => {
        elements.select.append(new Option(configuration.name, configuration.id));
      });
    elements.select.value = selectedId && store.configurations.some(({ id }) => id === selectedId)
      ? selectedId
      : "";
    if (elements.delete) elements.delete.disabled = !elements.select.value;
    if (elements.count) {
      const count = store.configurations.length;
      elements.count.textContent = `${count} saved`;
    }
  }

  function saveDraft() {
    draftTimer = null;
    if (!writeStorage(DRAFT_KEY, {
      schema_version: SCHEMA_VERSION,
      active_configuration_id: store.active_configuration_id,
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
      if (!store.active_configuration_id
        || raw.active_configuration_id !== store.active_configuration_id) return false;
      return applyConfiguration(raw.configuration);
    } catch (_error) {
      return false;
    }
  }

  function activateProfile(profileId, { announce = true } = {}) {
    const selected = store.configurations.find(({ id }) => id === profileId) || null;
    const configuration = selected?.configuration || defaultConfiguration;
    if (!configuration || !applyConfiguration(configuration)) {
      setStatus(selected
        ? `${selected.name} is no longer compatible with this calculator.`
        : "Default settings could not be restored.");
      return false;
    }

    const nextStore = { ...store, active_configuration_id: selected?.id || null };
    const persisted = writeStorage(STORAGE_KEY, nextStore);
    store = nextStore;
    renderSavedConfigurations(selected?.id || "");
    if (elements.name) elements.name.value = selected?.name || "";
    setProfileNameEntry(false);
    setActiveProfile(selected);
    queueDraftSave();
    if (announce) {
      setStatus(selected ? `Loaded ${selected.name}.` : "Using Default.");
    } else if (!persisted) {
      setStatus("Browser storage is unavailable; the active profile will not persist.");
    }
    return true;
  }

  activityPanels.forEach((panel) => {
    panel.querySelector("[data-rig-coverage]").addEventListener("change", (event) => {
      const selected = [...event.target.selectedOptions].map((option) => option.value);
      for (const [scope, kind] of [["category_ids", "category"], ["group_ids", "group"]]) {
        coverageInput(panel, scope).value = selected.filter((value) => value.startsWith(`${kind}:`))
          .map((value) => value.split(":")[1]).join(",");
      }
      event.target.setCustomValidity("");
      updateActivity(panel, { notify: true });
      queueDraftSave();
    });
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
    activateProfile(elements.select.value);
  });

  elements.createNew?.addEventListener("click", () => {
    if (!activateProfile("", { announce: false })) return;
    setProfileNameEntry(true);
    elements.name?.focus();
    setStatus("Enter a name for the new profile.");
  });

  elements.save?.addEventListener("click", () => {
    const name = elements.name.value.trim();
    if (!name) {
      setProfileNameEntry(true);
      setStatus("Enter a profile name before saving.");
      elements.name.focus();
      return;
    }

    const facilityValidation = validateFacilities();
    const overrideValidation = setupOverrides.validate();
    const invalid = facilityValidation.invalid || overrideValidation.invalid
      || sourceControls().find((input) => !input.checkValidity());
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
      setStatus(`You can save up to ${MAX_CONFIGURATIONS} profiles.`);
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
      setStatus("The profile could not be written to browser storage.");
      return;
    }
    store = nextStore;
    renderSavedConfigurations(saved.id);
    elements.name.value = saved.name;
    setProfileNameEntry(false);
    setActiveProfile(saved);
    queueDraftSave();
    setStatus(existing ? `Updated ${saved.name}.` : `Saved ${saved.name}.`);
  });

  elements.delete?.addEventListener("click", () => {
    const selected = store.configurations.find(({ id }) => id === elements.select.value);
    if (!selected || !window.confirm(`Delete the local profile "${selected.name}"?`)) return;
    const nextStore = {
      schema_version: SCHEMA_VERSION,
      active_configuration_id: null,
      configurations: store.configurations.filter(({ id }) => id !== selected.id),
    };
    if (!writeStorage(STORAGE_KEY, nextStore)) {
      setStatus("The profile could not be removed from browser storage.");
      return;
    }
    store = nextStore;
    if (defaultConfiguration) applyConfiguration(defaultConfiguration);
    renderSavedConfigurations();
    if (elements.name) elements.name.value = "";
    setProfileNameEntry(false);
    setActiveProfile();
    queueDraftSave();
    setStatus(`Deleted ${selected.name}.`);
  });

  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY) return;
    storeResult = readStore();
    store = storeResult.store;
    renderSavedConfigurations();
    const active = store.configurations.find(({ id }) => id === store.active_configuration_id) || null;
    if (active) applyConfiguration(active.configuration);
    else if (defaultConfiguration) applyConfiguration(defaultConfiguration);
    if (elements.name) elements.name.value = active?.name || "";
    setProfileNameEntry(false);
    setActiveProfile(active);
    setStatus("The profile list changed in another tab.");
  });

  updateAllActivities({ notify: false });
  app.addEventListener("industry:system-picker-resolved", () => {
    updateAllActivities({ notify: true });
  });
  globalThis.industryFacilityConfig = Object.freeze({ validate: validateFacilities });
  activityPanels.forEach(loadCoverage);
  renderSavedConfigurations();
  const active = store.configurations.find(({ id }) => id === store.active_configuration_id) || null;
  const restoredDraft = active ? restoreDraft() : false;
  if (active && !restoredDraft) applyConfiguration(active.configuration);
  if (!active && defaultConfiguration) applyConfiguration(defaultConfiguration);
  if (elements.name) elements.name.value = active?.name || "";
  setProfileNameEntry(false);
  setActiveProfile(active);
  if (storeResult.warning) setStatus(storeResult.warning);
  else if (restoredDraft) setStatus("Restored your last local settings.");

})();
