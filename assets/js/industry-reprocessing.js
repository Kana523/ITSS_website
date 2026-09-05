(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  const panel = app?.querySelector('[data-facility-config="reprocessing"]');
  if (!app || !panel) return;

  const structureSelect = panel.querySelector("[data-structure-select]");
  const securitySelect = panel.querySelector("[data-security-select]");
  const rigSelect = panel.querySelector("[data-rig-tier-select]");
  const materialSkillSelect = panel.querySelector("[data-reprocessing-material-skill]");
  const efficiencyReadout = panel.querySelector("[data-reprocessing-efficiency]");
  const implantSelect = panel.querySelector(
    '[data-profile-implant="reprocessing_yield_implant"]',
  );
  if (!structureSelect || !securitySelect || !rigSelect
    || !materialSkillSelect || !efficiencyReadout || !implantSelect) return;

  const STRUCTURE_BONUSES = Object.freeze({
    unbonused: 0,
    athanor: 0.02,
    tatara: 0.055,
  });
  const RIG_BASE_PERCENTAGE_POINTS = Object.freeze({ none: 0, t1: 1, t2: 3 });
  const RIG_SECURITY_MULTIPLIERS = Object.freeze({
    highsec: 1,
    lowsec: 1.06,
    nullsec: 1.12,
    wormhole: 1.12,
  });
  const IMPLANT_BONUSES = Object.freeze({
    "": 0,
    27175: 0.01,
    27169: 0.02,
    27174: 0.04,
  });

  function skillLevel(typeId) {
    const select = app.querySelector(`[data-skill-type-id="${typeId}"]`);
    const level = Number(select?.value || 0);
    return Number.isInteger(level) && level >= 0 && level <= 5 ? level : 0;
  }

  // CCP's skill formula is multiplicative. Upwell refinery role, rig, and
  // security modifiers are applied to the 50% equipment yield before skills.
  function calculateEfficiency({
    structure,
    security,
    rig,
    reprocessingLevel,
    efficiencyLevel,
    materialLevel,
    implant,
  }) {
    const structureBonus = STRUCTURE_BONUSES[structure] ?? 0;
    const rigPoints = RIG_BASE_PERCENTAGE_POINTS[rig] ?? 0;
    const securityMultiplier = rig === "none"
      ? 1
      : RIG_SECURITY_MULTIPLIERS[security] ?? 1;
    const implantBonus = IMPLANT_BONUSES[String(implant)] ?? 0;
    const facilityYield = ((50 + rigPoints) / 100)
      * (1 + structureBonus)
      * securityMultiplier;
    const characterYield = (1 + (reprocessingLevel * 0.03))
      * (1 + (efficiencyLevel * 0.02))
      * (1 + (materialLevel * 0.02))
      * (1 + implantBonus);
    return Math.min(1, Math.max(0, facilityYield * characterYield));
  }

  function formatEfficiency(value) {
    const percent = (value * 100).toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
    return `${percent}%`;
  }

  function updateEfficiency() {
    const materialSkillTypeId = Number(materialSkillSelect.value);
    const efficiency = calculateEfficiency({
      structure: structureSelect.value,
      security: securitySelect.value,
      rig: rigSelect.value,
      reprocessingLevel: skillLevel(3385),
      efficiencyLevel: skillLevel(3389),
      materialLevel: skillLevel(materialSkillTypeId),
      implant: implantSelect.value,
    });
    const selectedSkill = materialSkillSelect.selectedOptions[0]?.textContent || "material skill";
    efficiencyReadout.textContent = formatEfficiency(efficiency);
    efficiencyReadout.setAttribute(
      "aria-label",
      `${formatEfficiency(efficiency)} using ${selectedSkill}`,
    );
  }

  app.addEventListener("input", (event) => {
    if (event.target.matches?.("[data-skill-type-id]")) updateEfficiency();
  });
  app.addEventListener("change", (event) => {
    if (event.target.matches?.(
      '[data-facility-config="reprocessing"] select, [data-skill-type-id]',
    )) {
      updateEfficiency();
    }
  });
  app.addEventListener("industry:skills-imported", updateEfficiency);

  window.industryReprocessing = Object.freeze({ calculateEfficiency });
  updateEfficiency();
})();
