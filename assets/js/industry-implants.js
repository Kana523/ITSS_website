(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const profileDetails = app.querySelector("[data-profile-details]");
  const profileSummary = app.querySelector("[data-profile-summary]");
  const reactionsSelect = app.querySelector('[data-profile-skill="reactions_level"]');
  const skillGrid = reactionsSelect?.closest(".profile-field-grid");
  if (!profileDetails || !profileSummary || !reactionsSelect || !skillGrid) return;

  const label = document.createElement("label");
  const caption = document.createElement("span");
  caption.textContent = "Manufacturing implant";

  const select = document.createElement("select");
  select.dataset.profileImplant = "manufacturing_time_implant";
  select.setAttribute("aria-label", "Manufacturing time implant");
  [
    ["", "None"],
    ["27170", "BX-801 · 1%"],
    ["27167", "BX-802 · 2%"],
    ["27171", "BX-804 · 4%"],
  ].forEach(([value, text]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    select.append(option);
  });
  label.append(caption, select);
  skillGrid.append(label);

  const help = document.createElement("p");
  help.className = "field-help";
  help.textContent = "Zainou Beancounter BX hardwirings use implant slot 8 and reduce manufacturing job time only.";
  skillGrid.insertAdjacentElement("afterend", help);

  const note = app.querySelector(".calculation-note p:last-child");
  if (note) {
    note.textContent = "Blueprint, skill, implant, facility, and rig modifiers are applied to each combined job with exact arithmetic. Cached market prices are estimates.";
  }

  function profileHasCustomValue() {
    const hasSkill = [...app.querySelectorAll("[data-profile-skill]")]
      .some((input) => Number(input.value) > 0);
    const hasImplant = select.value !== "";
    const hasModifier = [...app.querySelectorAll("[data-profile-modifier]")]
      .some((input) => Number(input.value) > 0);
    const hasScope = [...app.querySelectorAll("[data-rig-scope]")]
      .some((input) => input.value.trim().length > 0);
    return hasSkill || hasImplant || hasModifier || hasScope;
  }

  function updateSummary() {
    profileSummary.textContent = profileHasCustomValue() ? "Custom" : "Unbonused";
  }

  select.addEventListener("change", () => {
    // Reuse the core profile-change handler to invalidate any displayed result.
    reactionsSelect.dispatchEvent(new Event("input", { bubbles: true }));
    updateSummary();
  });

  app.querySelectorAll("[data-profile-skill], [data-profile-modifier], [data-rig-scope]")
    .forEach((input) => input.addEventListener("input", updateSummary));

  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url = typeof input === "string" ? input : input?.url || "";
    const method = String(init.method || "GET").toUpperCase();
    if (
      method === "POST"
      && /\/api\/industry\/calculate(?:\?|$)/.test(url)
      && typeof init.body === "string"
    ) {
      try {
        const body = JSON.parse(init.body);
        if (select.value) {
          body.production_profile = body.production_profile || {};
          body.production_profile.manufacturing_time_implant = Number(select.value);
        } else if (body.production_profile?.manufacturing_time_implant !== undefined) {
          delete body.production_profile.manufacturing_time_implant;
        }
        init = { ...init, body: JSON.stringify(body) };
      } catch (_error) {
        // Preserve the original request if another caller supplied non-JSON data.
      }
    }
    return originalFetch(input, init);
  };

  updateSummary();
})();
