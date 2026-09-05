(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const profileDetails = app.querySelector("[data-profile-details]");
  const reactionsSelect = app.querySelector('[data-production-profile-field="reactions_level"]');
  const manufacturingSlot = app.querySelector(
    '[data-profile-implant-slot="manufacturing_time_implant"]',
  );
  const reprocessingSlot = app.querySelector(
    '[data-profile-implant-slot="reprocessing_yield_implant"]',
  );
  if (!profileDetails || !reactionsSelect || !manufacturingSlot || !reprocessingSlot) return;

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
  manufacturingSlot.append(label);

  select.addEventListener("change", () => {
    // Reuse the core profile-change handler to invalidate any displayed result.
    reactionsSelect.dispatchEvent(new Event("input", { bubbles: true }));
  });

  const reprocessingLabel = document.createElement("label");
  const reprocessingCaption = document.createElement("span");
  reprocessingCaption.textContent = "Reprocessing implant";
  const reprocessingSelect = document.createElement("select");
  reprocessingSelect.dataset.profileImplant = "reprocessing_yield_implant";
  reprocessingSelect.setAttribute("aria-label", "Reprocessing yield implant");
  [
    ["", "None"],
    ["27175", "RX-801 · 1%"],
    ["27169", "RX-802 · 2%"],
    ["27174", "RX-804 · 4%"],
  ].forEach(([value, text]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    reprocessingSelect.append(option);
  });
  reprocessingLabel.append(reprocessingCaption, reprocessingSelect);
  reprocessingSlot.append(reprocessingLabel);
  reprocessingSelect.addEventListener("change", () => {
    reactionsSelect.dispatchEvent(new Event("input", { bubbles: true }));
  });

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
})();
