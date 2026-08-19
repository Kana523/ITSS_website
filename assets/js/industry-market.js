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
  panel.dataset.marketRefresh = "jita";

  const age = document.createElement("span");
  age.dataset.marketAge = "jita";
  age.setAttribute("role", "status");
  age.setAttribute("aria-live", "polite");
  age.textContent = "Jita prices: checking…";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "text-button";
  button.dataset.marketRefreshButton = "jita";
  button.textContent = "Fetch new prices";

  panel.append(age, document.createTextNode(" "), button);
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
    return `Jita prices: ${minutes} ${unit} old · ${freshness}`;
  }

  async function getStatus() {
    const response = await fetch(`${apiBase}/api/market/jita/status`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`Market status failed (${response.status})`);
    return response.json();
  }

  async function refreshPrices({ manual = false } = {}) {
    button.disabled = true;
    age.textContent = manual ? "Jita prices: fetching…" : "Jita prices: checking…";
    try {
      const response = await fetch(`${apiBase}/api/market/jita/refresh`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`Market refresh failed (${response.status})`);
      const payload = await response.json();
      age.textContent = ageLabel(payload.snapshot);
      if (manual && payload.refresh_status === "fresh") {
        age.textContent += " · already up to date";
      } else if (manual && payload.refresh_status === "updated") {
        age.textContent += " · updated; recalculate to apply";
      } else if (manual && payload.refresh_status === "not_modified") {
        age.textContent += " · no newer ESI data";
      }
    } catch (_error) {
      try {
        const snapshot = await getStatus();
        age.textContent = `${ageLabel(snapshot)} · refresh failed`;
      } catch (_statusError) {
        age.textContent = "Jita prices: unavailable · refresh failed";
      }
    } finally {
      button.disabled = false;
    }
  }

  button.addEventListener("click", () => refreshPrices({ manual: true }));

  // Exactly one automatic attempt per page load. There is intentionally no
  // polling timer or heartbeat; another refresh only happens on reload or click.
  refreshPrices();
})();
