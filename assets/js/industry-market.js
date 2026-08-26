(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const pricingDetails = app.querySelector("[data-pricing-details]");
  const pricingBody = pricingDetails?.querySelector(".planner-details-body");
  const pricingToggle = pricingDetails?.querySelector(".pricing-toggle");
  if (!pricingDetails || !pricingBody) return;

  function resolveApiBase() {
    const configured = document.body.dataset.industryApiBase?.trim();
    if (configured) return configured.replace(/\/$/, "");
    if (["127.0.0.1", "localhost"].includes(window.location.hostname)) {
      return "http://127.0.0.1:8000";
    }
    return "";
  }

  const apiBase = resolveApiBase();
  const panel = document.createElement("div");
  panel.dataset.marketStatus = "jita";

  const age = document.createElement("span");
  age.dataset.marketAge = "jita";
  age.setAttribute("role", "status");
  age.setAttribute("aria-live", "polite");
  age.textContent = "Jita prices: checking...";

  panel.append(age);
  if (pricingToggle) {
    pricingToggle.insertAdjacentElement("afterend", panel);
  } else {
    pricingBody.prepend(panel);
  }

  function ageLabel(snapshot) {
    if (!snapshot || snapshot.status === "unavailable" || snapshot.age_minutes === null) {
      return "Jita prices: unavailable";
    }
    const minutes = Number(snapshot.age_minutes);
    const unit = minutes === 1 ? "minute" : "minutes";
    const freshness = snapshot.status === "fresh" ? "current" : "stale";
    return `Jita prices: ${minutes} ${unit} old - ${freshness}`;
  }

  async function getStatus() {
    const response = await fetch(`${apiBase}/api/market/jita/status`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`Market status failed (${response.status})`);
    return response.json();
  }

  async function loadStatus() {
    try {
      age.textContent = ageLabel(await getStatus());
    } catch (_error) {
      age.textContent = "Jita prices: unavailable";
    }
  }

  loadStatus();
})();
