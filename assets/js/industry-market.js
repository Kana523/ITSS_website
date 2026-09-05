(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const panel = app.querySelector("[data-price-state]");
  const label = panel?.querySelector("[data-price-label]");
  const age = panel?.querySelector("[data-market-age]");
  if (!panel || !label || !age) return;

  function resolveApiBase() {
    const configured = document.body.dataset.industryApiBase?.trim();
    if (configured) return configured.replace(/\/$/, "");
    if (["127.0.0.1", "localhost"].includes(window.location.hostname)) {
      return "http://127.0.0.1:8000";
    }
    return "";
  }

  const apiBase = resolveApiBase();

  function freshnessState(snapshot) {
    if (!snapshot || snapshot.status === "unavailable" || snapshot.age_minutes === null) {
      return "unavailable";
    }
    const minutes = Number(snapshot.age_minutes);
    if (!Number.isFinite(minutes) || minutes < 0) return "unavailable";
    if (minutes <= 5) return "fresh";
    if (minutes < 15) return "aging";
    return "stale";
  }

  function ageLabel(minutes) {
    if (minutes === 0) return "Jita · less than a minute old";
    const unit = minutes === 1 ? "minute" : "minutes";
    return `Jita · ${minutes} ${unit} old`;
  }

  function renderStatus(snapshot) {
    const status = freshnessState(snapshot);
    panel.dataset.state = status;
    if (status === "unavailable") {
      label.textContent = "Prices unavailable";
      age.textContent = "Jita cache is unavailable";
      return;
    }

    const minutes = Number(snapshot.age_minutes);
    label.textContent = status === "fresh"
      ? "Prices fresh"
      : status === "aging" ? "Prices aging" : "Prices stale";
    age.textContent = ageLabel(minutes);
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
      renderStatus(await getStatus());
    } catch (_error) {
      renderStatus(null);
    }
  }

  loadStatus();
})();
