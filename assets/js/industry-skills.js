(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const skill = (typeId, name) => Object.freeze({ typeId, name });
  const group = (groupId, key, name, skills) => Object.freeze({
    groupId,
    key,
    name,
    skills: Object.freeze(skills),
  });

  // Published Tranquility skills fetched from CCP ESI on 2026-08-29.
  // Numeric type IDs are the stable join key used by the ESI character-skills route.
  const SKILL_GROUPS = Object.freeze([
    group(268, "production", "Production", [
      skill(77725, "Advanced Capital Ship Construction"),
      skill(3396, "Advanced Industrial Ship Construction"),
      skill(3388, "Advanced Industry"),
      skill(3398, "Advanced Large Ship Construction"),
      skill(24625, "Advanced Mass Production"),
      skill(3397, "Advanced Medium Ship Construction"),
      skill(3395, "Advanced Small Ship Construction"),
      skill(22242, "Capital Ship Construction"),
      skill(26224, "Drug Manufacturing"),
      skill(3380, "Industry"),
      skill(3387, "Mass Production"),
      skill(3400, "Outpost Construction"),
      skill(24268, "Supply Chain Management"),
    ]),
    group(270, "science", "Science", [
      skill(24624, "Advanced Laboratory Operation"),
      skill(23087, "Amarr Encryption Methods"),
      skill(11444, "Amarr Starship Engineering"),
      skill(11487, "Astronautic Engineering"),
      skill(21790, "Caldari Encryption Methods"),
      skill(11454, "Caldari Starship Engineering"),
      skill(30325, "Core Subsystem Technology"),
      skill(30324, "Defensive Subsystem Technology"),
      skill(11448, "Electromagnetic Physics"),
      skill(11453, "Electronic Engineering"),
      skill(23121, "Gallente Encryption Methods"),
      skill(11450, "Gallente Starship Engineering"),
      skill(11446, "Graviton Physics"),
      skill(11433, "High Energy Physics"),
      skill(11443, "Hydromagnetic Physics"),
      skill(3406, "Laboratory Operation"),
      skill(11447, "Laser Physics"),
      skill(11452, "Mechanical Engineering"),
      skill(3409, "Metallurgy"),
      skill(21791, "Minmatar Encryption Methods"),
      skill(11445, "Minmatar Starship Engineering"),
      skill(11529, "Molecular Engineering"),
      skill(81896, "Mutagenic Stabilization"),
      skill(11442, "Nanite Engineering"),
      skill(11451, "Nuclear Physics"),
      skill(30327, "Offensive Subsystem Technology"),
      skill(11441, "Plasma Physics"),
      skill(30788, "Propulsion Subsystem Technology"),
      skill(11455, "Quantum Physics"),
      skill(3403, "Research"),
      skill(12179, "Research Project Management"),
      skill(11449, "Rocket Science"),
      skill(3402, "Science"),
      skill(24270, "Scientific Networking"),
      skill(3408, "Sleeper Encryption Methods"),
      skill(21789, "Sleeper Technology"),
      skill(23123, "Takmahl Technology"),
      skill(20433, "Talocan Technology"),
      skill(52308, "Triglavian Encryption Methods"),
      skill(52307, "Triglavian Quantum Engineering"),
      skill(55025, "Upwell Encryption Methods"),
      skill(81050, "Upwell Starship Engineering"),
      skill(23124, "Yan Jung Technology"),
    ]),
    group(1218, "processing", "Processing", [
      skill(60381, "Abyssal Ore Processing"),
      skill(45749, "Advanced Mass Reactions"),
      skill(3410, "Astrogeology"),
      skill(28585, "Capital Industrial Reconfiguration"),
      skill(62451, "Capital Shipboard Compression Technology"),
      skill(60378, "Coherent Ore Processing"),
      skill(46153, "Common Moon Ore Processing"),
      skill(60380, "Complex Ore Processing"),
      skill(11395, "Deep Core Mining"),
      skill(90040, "Erratic Ore Processing"),
      skill(46156, "Exceptional Moon Ore Processing"),
      skill(25544, "Gas Cloud Harvesting"),
      skill(62452, "Gas Decompression Efficiency"),
      skill(16281, "Ice Harvesting"),
      skill(18025, "Ice Processing"),
      skill(58956, "Industrial Reconfiguration"),
      skill(45748, "Mass Reactions"),
      skill(12189, "Mercoxit Ore Processing"),
      skill(3386, "Mining"),
      skill(90728, "Mining Exploitation"),
      skill(90727, "Mining Precision"),
      skill(22578, "Mining Upgrades"),
      skill(46155, "Rare Moon Ore Processing"),
      skill(45746, "Reactions"),
      skill(45750, "Remote Reactions"),
      skill(3385, "Reprocessing"),
      skill(3389, "Reprocessing Efficiency"),
      skill(25863, "Salvaging"),
      skill(12196, "Scrapmetal Processing"),
      skill(62450, "Shipboard Compression Technology"),
      skill(60377, "Simple Ore Processing"),
      skill(46152, "Ubiquitous Moon Ore Processing"),
      skill(46154, "Uncommon Moon Ore Processing"),
      skill(90398, "Unrefined Minerals Processing"),
      skill(60379, "Variegated Ore Processing"),
    ]),
  ]);

  const TRADE_GROUP = group(274, "trade", "Trade skills", [
    skill(16622, "Accounting"),
    skill(3446, "Broker Relations"),
    skill(16597, "Advanced Broker Relations"),
  ]);

  const PROFILE_FIELDS = Object.freeze({
    3380: "industry_level",
    3388: "advanced_industry_level",
    45746: "reactions_level",
  });

  function levelSelect(item, category, role) {
    const select = document.createElement("select");
    select.dataset.profileSkill = String(item.typeId);
    select.dataset.skillTypeId = String(item.typeId);
    select.dataset.skillCategory = category;
    select.dataset.skillRole = role;
    select.setAttribute("aria-label", `${item.name} skill level`);
    const profileField = PROFILE_FIELDS[item.typeId];
    if (profileField) select.dataset.productionProfileField = profileField;
    for (let level = 0; level <= 5; level += 1) {
      select.append(new Option(String(level), String(level)));
    }
    return select;
  }

  function renderGroup(item, mount, { open = false, role = "industry" } = {}) {
    const details = document.createElement("details");
    details.className = "skill-dropdown";
    details.dataset.skillGroupId = String(item.groupId);
    details.open = open;

    const summary = document.createElement("summary");
    const title = document.createElement("span");
    title.textContent = item.name;
    const count = document.createElement("small");
    count.dataset.skillGroupCount = "";
    summary.append(title, count);

    const grid = document.createElement("div");
    grid.className = "skill-select-grid";
    if (item.key === "production") grid.dataset.productionSkillExtras = "";
    item.skills.forEach((entry) => {
      const label = document.createElement("label");
      const caption = document.createElement("span");
      caption.textContent = entry.name;
      label.append(caption, levelSelect(entry, item.key, role));
      grid.append(label);
    });

    details.append(summary, grid);
    mount.append(details);
  }

  const industryMount = app.querySelector("[data-industry-skill-groups]");
  if (industryMount) {
    SKILL_GROUPS.forEach((item, index) => {
      renderGroup(item, industryMount, { open: index === 0 });
    });
  }

  const tradeMount = app.querySelector("[data-trade-skill-groups]");
  if (tradeMount) renderGroup(TRADE_GROUP, tradeMount, { role: "trade" });

  function updateCounts() {
    app.querySelectorAll("[data-skill-group-id]").forEach((details) => {
      const selects = [...details.querySelectorAll("[data-skill-type-id]")];
      const trained = selects.filter((select) => Number(select.value) > 0).length;
      const count = details.querySelector("[data-skill-group-count]");
      if (count) count.textContent = `${trained} / ${selects.length} trained`;
    });
  }

  function skillLevelsByTypeId() {
    return Object.fromEntries(
      [...app.querySelectorAll("[data-skill-type-id]")]
        .map((select) => [select.dataset.skillTypeId, Number(select.value)]),
    );
  }

  function applyEsiSkills(payload, { levelField = "active_skill_level" } = {}) {
    if (!payload || !Array.isArray(payload.skills)) return false;
    const imported = new Map();
    for (const entry of payload.skills) {
      const typeId = Number(entry?.skill_id);
      const requestedLevel = entry?.[levelField] ?? entry?.trained_skill_level;
      const level = Number(requestedLevel);
      if (Number.isInteger(typeId) && typeId > 0 && Number.isInteger(level) && level >= 0 && level <= 5) {
        imported.set(typeId, level);
      }
    }

    const inputs = [...app.querySelectorAll("[data-skill-type-id]")];
    inputs.forEach((select) => {
      select.value = String(imported.get(Number(select.dataset.skillTypeId)) ?? 0);
    });
    updateCounts();
    inputs[0]?.dispatchEvent(new Event("input", { bubbles: true }));
    inputs[0]?.dispatchEvent(new Event("change", { bubbles: true }));
    app.dispatchEvent(new CustomEvent("industry:skills-imported", {
      detail: { importedSkillCount: imported.size, levelField },
    }));
    return true;
  }

  app.addEventListener("input", (event) => {
    if (event.target.matches?.("[data-skill-type-id]")) updateCounts();
  });
  app.addEventListener("change", (event) => {
    if (event.target.matches?.("[data-skill-type-id]")) updateCounts();
  });

  window.industrySkills = Object.freeze({
    groups: SKILL_GROUPS,
    tradeGroup: TRADE_GROUP,
    skillLevelsByTypeId,
    applyEsiSkills,
    sso: Object.freeze({
      scope: "esi-skills.read_skills.v1",
      endpoint: "/characters/{character_id}/skills",
      idField: "skill_id",
      defaultLevelField: "active_skill_level",
    }),
  });
  updateCounts();
})();
