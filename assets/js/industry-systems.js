(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const pickers = [...app.querySelectorAll("[data-system-picker]")];
  if (!pickers.length) return;

  function resolveApiBase() {
    const configured = document.body.dataset.industryApiBase?.trim();
    if (configured) return configured.replace(/\/$/, "");
    if (["127.0.0.1", "localhost"].includes(window.location.hostname)) {
      return "http://127.0.0.1:8000";
    }
    return "";
  }

  const apiBase = resolveApiBase();
  const controls = new WeakMap();

  function pickerControls(picker) {
    let state = controls.get(picker);
    if (state) return state;
    state = {
      search: picker.querySelector("[data-system-search]"),
      systemId: picker.querySelector("[data-system-id]"),
      results: picker.querySelector("[data-system-results]"),
      index: picker.querySelector("[data-system-index]"),
      indexPanel: picker.querySelector(".system-index"),
      matches: [],
      activeIndex: -1,
      searchTimer: null,
      searchRequest: null,
      indexRequest: null,
    };
    controls.set(picker, state);
    return state;
  }

  function activityFor(picker) {
    return picker.closest(".pricing-section")
      ?.querySelector("[data-system-activity-select]")?.value
      || picker.dataset.systemActivity;
  }

  function hideResults(picker) {
    const state = pickerControls(picker);
    state.results.hidden = true;
    state.search.setAttribute("aria-expanded", "false");
    state.search.removeAttribute("aria-activedescendant");
    state.activeIndex = -1;
  }

  function setIndex(picker, stateName, text) {
    const state = pickerControls(picker);
    state.indexPanel.dataset.state = stateName;
    state.index.textContent = text;
  }

  function notifyPickerResolved(picker) {
    app.dispatchEvent(new CustomEvent("industry:system-picker-resolved", {
      detail: { picker },
    }));
  }

  function freshnessState(snapshot) {
    if (!snapshot || snapshot.status === "unavailable" || snapshot.cost_index === null) {
      return "unavailable";
    }
    return snapshot.status === "fresh" ? "fresh" : "stale";
  }

  function formatIndex(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) return null;
    const percent = (numeric * 100).toFixed(4)
      .replace(/\.0+$/, "")
      .replace(/(\.\d*?)0+$/, "$1");
    return `${percent}%`;
  }

  async function loadIndex(picker) {
    const state = pickerControls(picker);
    const solarSystemId = Number(state.systemId.value);
    const activity = activityFor(picker);
    state.indexRequest?.abort();
    if (!Number.isInteger(solarSystemId) || solarSystemId <= 0 || !activity) {
      setIndex(picker, "empty", "—");
      return;
    }

    const request = new AbortController();
    state.indexRequest = request;
    setIndex(picker, "loading", "…");
    try {
      const query = new URLSearchParams({
        solar_system_id: String(solarSystemId),
        activity,
      });
      const response = await fetch(`${apiBase}/api/market/industry-index?${query}`, {
        headers: { Accept: "application/json" },
        signal: request.signal,
      });
      if (!response.ok) throw new Error(`Industry index failed (${response.status})`);
      const snapshot = await response.json();
      if (state.indexRequest !== request
        || Number(state.systemId.value) !== solarSystemId
        || activityFor(picker) !== activity) return;
      const formatted = formatIndex(snapshot.cost_index);
      const status = freshnessState(snapshot);
      setIndex(picker, formatted ? status : "unavailable", formatted || "—");
      state.index.setAttribute(
        "aria-label",
        formatted ? `${formatted} ${activity.replaceAll("_", " ")} index` : "Index unavailable",
      );
    } catch (error) {
      if (error.name !== "AbortError") setIndex(picker, "unavailable", "—");
    } finally {
      if (state.indexRequest === request) state.indexRequest = null;
    }
  }

  function setActiveResult(picker, index) {
    const state = pickerControls(picker);
    const buttons = [...state.results.querySelectorAll("[data-system-result]")];
    if (!buttons.length) return;
    state.activeIndex = (index + buttons.length) % buttons.length;
    buttons.forEach((button, buttonIndex) => {
      const active = buttonIndex === state.activeIndex;
      button.dataset.active = active ? "true" : "false";
      if (active) {
        state.search.setAttribute("aria-activedescendant", button.id);
        button.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function selectSystem(picker, system) {
    const state = pickerControls(picker);
    state.search.value = system.name;
    state.search.dataset.solarSystemId = String(system.solar_system_id);
    state.search.setCustomValidity("");
    state.systemId.value = String(system.solar_system_id);
    hideResults(picker);
    state.systemId.dispatchEvent(new Event("input", { bubbles: true }));
    state.systemId.dispatchEvent(new Event("change", { bubbles: true }));
    loadIndex(picker);
  }

  function renderResults(picker, systems, message = "") {
    const state = pickerControls(picker);
    state.matches = systems;
    state.results.replaceChildren();
    if (!systems.length) {
      const item = document.createElement("li");
      item.className = "system-search-empty";
      item.textContent = message || "No systems found";
      state.results.append(item);
    } else {
      systems.forEach((system, index) => {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.id = `${state.results.id}-option-${index}`;
        button.dataset.systemResult = String(index);
        const name = document.createElement("span");
        name.textContent = system.name;
        button.append(name);
        item.append(button);
        state.results.append(item);
      });
    }
    state.results.hidden = false;
    state.search.setAttribute("aria-expanded", "true");
    state.activeIndex = -1;
  }

  async function searchSystems(picker, query) {
    const state = pickerControls(picker);
    state.searchRequest?.abort();
    const request = new AbortController();
    state.searchRequest = request;
    try {
      const params = new URLSearchParams({ search: query, limit: "8" });
      const response = await fetch(`${apiBase}/api/industry/systems?${params}`, {
        headers: { Accept: "application/json" },
        signal: request.signal,
      });
      if (!response.ok) throw new Error(`System search failed (${response.status})`);
      const payload = await response.json();
      if (state.searchRequest !== request || state.search.value.trim() !== query) return;
      renderResults(picker, Array.isArray(payload.systems) ? payload.systems : []);
    } catch (error) {
      if (error.name !== "AbortError") renderResults(picker, [], "System search unavailable");
    } finally {
      if (state.searchRequest === request) state.searchRequest = null;
    }
  }

  function queueSearch(picker) {
    const state = pickerControls(picker);
    window.clearTimeout(state.searchTimer);
    const query = state.search.value.trim();
    state.systemId.value = "";
    delete state.search.dataset.solarSystemId;
    state.search.setCustomValidity("");
    setIndex(picker, "empty", "—");
    state.systemId.dispatchEvent(new Event("change", { bubbles: true }));
    if (!query) {
      hideResults(picker);
      return;
    }
    state.searchTimer = window.setTimeout(() => searchSystems(picker, query), 180);
  }

  async function resolveStoredSystem(picker) {
    const state = pickerControls(picker);
    window.clearTimeout(state.searchTimer);
    state.searchRequest?.abort();
    hideResults(picker);
    state.search.setCustomValidity("");
    const solarSystemId = Number(state.systemId.value);
    if (!Number.isInteger(solarSystemId) || solarSystemId <= 0) {
      state.search.value = "";
      delete state.search.dataset.solarSystemId;
      setIndex(picker, "empty", "—");
      notifyPickerResolved(picker);
      return;
    }
    if (state.search.dataset.solarSystemId !== String(solarSystemId)) {
      state.search.value = "";
    }
    try {
      const params = new URLSearchParams({
        search: String(solarSystemId),
        limit: "1",
      });
      const response = await fetch(`${apiBase}/api/industry/systems?${params}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`System lookup failed (${response.status})`);
      const payload = await response.json();
      const system = payload.systems?.find(
        (candidate) => Number(candidate.solar_system_id) === solarSystemId,
      );
      if (Number(state.systemId.value) === solarSystemId) {
        state.search.value = system?.name || `System ${solarSystemId}`;
        state.search.dataset.solarSystemId = String(solarSystemId);
        if (system) state.search.setCustomValidity("");
      }
    } catch (_error) {
      if (Number(state.systemId.value) === solarSystemId) {
        state.search.value = `System ${solarSystemId}`;
        state.search.dataset.solarSystemId = String(solarSystemId);
      }
    }
    notifyPickerResolved(picker);
    loadIndex(picker);
  }

  pickers.forEach((picker) => {
    const state = pickerControls(picker);
    state.search.addEventListener("input", () => queueSearch(picker));
    state.search.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        if (state.results.hidden) return;
        event.preventDefault();
        setActiveResult(
          picker,
          state.activeIndex + (event.key === "ArrowDown" ? 1 : -1),
        );
      } else if (event.key === "Enter" && state.activeIndex >= 0) {
        event.preventDefault();
        selectSystem(picker, state.matches[state.activeIndex]);
      } else if (event.key === "Escape") {
        hideResults(picker);
      }
    });
    state.search.addEventListener("blur", () => {
      window.setTimeout(() => hideResults(picker), 120);
    });
    state.results.addEventListener("mousedown", (event) => event.preventDefault());
    state.results.addEventListener("click", (event) => {
      const button = event.target.closest("[data-system-result]");
      if (!button) return;
      selectSystem(picker, state.matches[Number(button.dataset.systemResult)]);
    });
  });

  app.addEventListener("change", (event) => {
    if (!event.target.matches?.("[data-system-activity-select]")) return;
    const picker = event.target.closest(".pricing-section")?.querySelector("[data-system-picker]");
    if (picker) loadIndex(picker);
  });
  app.addEventListener("industry:configuration-applied", () => {
    pickers.forEach(resolveStoredSystem);
  });
  app.addEventListener("industry:system-picker-refresh", (event) => {
    const picker = event.detail?.picker;
    if (pickers.includes(picker)) resolveStoredSystem(picker);
  });

  pickers.forEach(resolveStoredSystem);
})();
