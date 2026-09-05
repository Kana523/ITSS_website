(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const MAX_SAFE_INTEGER = 9_007_199_254_740_991;
  const MAX_DEMANDS = 50;
  const MAX_OWNED_MATERIALS = 500;
  const SEARCH_DELAY_MS = 260;
  const MAX_RECOVERY_ATTEMPTS = 4;
  const numberFormatter = new Intl.NumberFormat("en-US");

  const elements = {
    apiState: document.querySelector("[data-api-state]"),
    apiLabel: document.querySelector("[data-api-label]"),
    form: app.querySelector("[data-planner-form]"),
    searchInput: app.querySelector("[data-search-input]"),
    searchStatus: app.querySelector("[data-search-status]"),
    searchResults: app.querySelector("[data-search-results]"),
    demandEditor: app.querySelector("[data-demand-editor]"),
    demandList: app.querySelector("[data-demand-list]"),
    demandStatus: app.querySelector("[data-demand-status]"),
    clearDemands: app.querySelector("[data-clear-demands]"),
    ownedDetails: app.querySelector("[data-owned-details]"),
    ownedSummary: app.querySelector("[data-owned-summary]"),
    ownedSearchInput: app.querySelector("[data-owned-search-input]"),
    ownedSearchStatus: app.querySelector("[data-owned-search-status]"),
    ownedSearchResults: app.querySelector("[data-owned-search-results]"),
    ownedEditor: app.querySelector("[data-owned-editor]"),
    ownedList: app.querySelector("[data-owned-list]"),
    clearOwned: app.querySelector("[data-clear-owned]"),
    calculateButton: app.querySelector("[data-calculate-button]"),
    overridesPanel: app.querySelector("[data-overrides-panel]"),
    overridesList: app.querySelector("[data-overrides-list]"),
    clearOverrides: app.querySelector("[data-clear-overrides]"),
    output: app.querySelector("[data-output]"),
    outputStatus: app.querySelector("[data-output-status]"),
    placeholder: app.querySelector("[data-output-placeholder]"),
    loading: app.querySelector("[data-output-loading]"),
    error: app.querySelector("[data-output-error]"),
    errorTitle: app.querySelector("[data-error-title]"),
    errorMessage: app.querySelector("[data-error-message]"),
    errorActions: app.querySelector("[data-error-actions]"),
    planOutput: app.querySelector("[data-plan-output]"),
    summaryTitle: app.querySelector("[data-summary-title]"),
    requestedOutputs: app.querySelector("[data-requested-outputs]"),
    stepCount: app.querySelector("[data-step-count]"),
    purchaseCount: app.querySelector("[data-purchase-count]"),
    productionPanel: app.querySelector("[data-production-panel]"),
    buildSteps: app.querySelector("[data-build-steps]"),
    purchases: app.querySelector("[data-purchases]"),
    valuationPanel: app.querySelector("[data-valuation-panel]"),
    marketStamp: app.querySelector("[data-market-stamp]"),
    marketLocation: app.querySelector("[data-market-location]"),
    marketStatus: app.querySelector("[data-market-status]"),
    marketDetail: app.querySelector("[data-market-detail]"),
    economicsShopping: app.querySelector("[data-economics-shopping]"),
    economicsInstallation: app.querySelector("[data-economics-installation]"),
    economicsCost: app.querySelector("[data-economics-cost]"),
    economicsOutput: app.querySelector("[data-economics-output]"),
    economicsProfit: app.querySelector("[data-economics-profit]"),
    economicsMargin: app.querySelector("[data-economics-margin]"),
    economicsSurplus: app.querySelector("[data-economics-surplus]"),
    economicsProfitSurplus: app.querySelector("[data-economics-profit-surplus]"),
    economicsMarginSurplus: app.querySelector("[data-economics-margin-surplus]"),
    valuationNote: app.querySelector("[data-valuation-note]"),
    copyShopping: app.querySelector("[data-copy-shopping]"),
    exportStatus: app.querySelector("[data-export-status]"),
    shoppingCount: app.querySelector("[data-shopping-count]"),
    shoppingPlaceholder: app.querySelector("[data-shopping-placeholder]"),
    shoppingOutput: app.querySelector("[data-shopping-output]"),
  };

  const state = {
    demands: new Map(),
    ownedMaterials: new Map(),
    sdeBuildNumber: null,
    choices: new Map(),
    blueprintEfficiencies: new Map(),
    typeNames: new Map(),
    latestPlan: null,
    searchTimer: null,
    searchController: null,
    calculationController: null,
    searchRequestId: 0,
    ownedSearchTimer: null,
    ownedSearchController: null,
    ownedSearchRequestId: 0,
    calculationRequestId: 0,
    pendingNotice: "",
    pendingEfficiencyFocusKey: null,
    pendingChoiceFocusTypeId: null,
    pendingChoiceOriginTab: null,
    inputRevision: 0,
  };

  class ApiRequestError extends Error {
    constructor(status, code, message, details = null, sdeBuildNumber = null) {
      super(message);
      this.name = "ApiRequestError";
      this.status = status;
      this.code = code;
      this.details = details;
      this.sdeBuildNumber = sdeBuildNumber;
    }
  }

  function resolveApiBase() {
    const configured = document.body.dataset.industryApiBase?.trim();
    if (configured) return configured.replace(/\/$/, "");

    if (["127.0.0.1", "localhost"].includes(window.location.hostname)) {
      return "http://127.0.0.1:8000";
    }
    return "";
  }

  const apiBase = resolveApiBase();

  function apiUrl(path) {
    return `${apiBase}${path}`;
  }

  function createElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function formatNumber(value) {
    return numberFormatter.format(value);
  }

  function groupIntegerDigits(value) {
    return value.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function decimalToScaledInteger(value, fractionDigits = 2) {
    if (typeof value !== "string" || !/^-?\d+(?:\.\d+)?$/.test(value)) return null;
    const negative = value.startsWith("-");
    const unsigned = negative ? value.slice(1) : value;
    const [integerPart, rawFraction = ""] = unsigned.split(".");
    const kept = rawFraction.slice(0, fractionDigits).padEnd(fractionDigits, "0");
    let scaled = BigInt(integerPart) * (10n ** BigInt(fractionDigits)) + BigInt(kept || "0");
    if (rawFraction.length > fractionDigits && rawFraction[fractionDigits] >= "5") scaled += 1n;
    return negative ? -scaled : scaled;
  }

  function formatIsk(value) {
    if (value === null || value === undefined) return "—";
    const scaled = decimalToScaledInteger(String(value), 2);
    if (scaled === null) return "—";
    const negative = scaled < 0n;
    const absolute = negative ? -scaled : scaled;
    const integerPart = absolute / 100n;
    const fractionalPart = String(absolute % 100n).padStart(2, "0");
    return `${negative ? "-" : ""}${groupIntegerDigits(String(integerPart))}.${fractionalPart} ISK`;
  }

  function decimalFraction(value) {
    if (typeof value !== "string" || !/^-?\d+(?:\.\d+)?$/.test(value)) return null;
    const negative = value.startsWith("-");
    const unsigned = negative ? value.slice(1) : value;
    const [integerPart, fractionPart = ""] = unsigned.split(".");
    const numerator = BigInt(`${integerPart}${fractionPart}` || "0") * (negative ? -1n : 1n);
    return { numerator, denominator: 10n ** BigInt(fractionPart.length) };
  }

  function formatProfitMargin(ratio) {
    if (!ratio) return "—";
    const numerator = decimalFraction(String(ratio.numerator));
    const denominator = decimalFraction(String(ratio.denominator));
    if (!numerator || !denominator || denominator.numerator === 0n) return "—";
    const dividend = numerator.numerator * denominator.denominator * 10_000n;
    const divisor = numerator.denominator * denominator.numerator;
    const negative = (dividend < 0n) !== (divisor < 0n);
    const absoluteDividend = dividend < 0n ? -dividend : dividend;
    const absoluteDivisor = divisor < 0n ? -divisor : divisor;
    let hundredths = absoluteDividend / absoluteDivisor;
    if ((absoluteDividend % absoluteDivisor) * 2n >= absoluteDivisor) hundredths += 1n;
    const whole = hundredths / 100n;
    const fraction = String(hundredths % 100n).padStart(2, "0");
    return `${negative ? "-" : ""}${whole}.${fraction}%`;
  }

  function formatDurationCentiseconds(totalCentiseconds) {
    let exactCentiseconds;
    try {
      if (typeof totalCentiseconds === "number" && !Number.isSafeInteger(totalCentiseconds)) {
        throw new RangeError("Unsafe centisecond value");
      }
      exactCentiseconds = BigInt(totalCentiseconds);
    } catch (_error) {
      return `${totalCentiseconds} centiseconds`;
    }

    if (exactCentiseconds < 0n) return `${totalCentiseconds} centiseconds`;

    const wholeSeconds = exactCentiseconds / 100n;
    const fractionalCentiseconds = exactCentiseconds % 100n;
    const days = wholeSeconds / 86_400n;
    const hours = (wholeSeconds % 86_400n) / 3_600n;
    const minutes = (wholeSeconds % 3_600n) / 60n;
    const seconds = wholeSeconds % 60n;
    const parts = [];

    if (days) parts.push(`${days}d`);
    if (hours) parts.push(`${hours}h`);
    if (minutes) parts.push(`${minutes}m`);
    if (seconds || fractionalCentiseconds || parts.length === 0) {
      const fraction = fractionalCentiseconds
        ? `.${String(fractionalCentiseconds).padStart(2, "0").replace(/0$/, "")}`
        : "";
      parts.push(`${seconds}${fraction}s`);
    }
    return parts.join(" ");
  }

  function formatDurationFraction(fraction, centiseconds = null) {
    if (centiseconds !== null && centiseconds !== undefined) {
      return formatDurationCentiseconds(centiseconds);
    }
    try {
      const numerator = BigInt(fraction.numerator);
      const denominator = BigInt(fraction.denominator);
      if (numerator < 0n || denominator <= 0n) throw new RangeError("Invalid duration");
      const isApproximate = (numerator * 10_000n) % denominator !== 0n;
      const scaled = (numerator * 10_000n + denominator / 2n) / denominator;
      const wholeSeconds = scaled / 10_000n;
      const fractional = String(scaled % 10_000n).padStart(4, "0").replace(/0+$/, "");
      const days = wholeSeconds / 86_400n;
      const hours = (wholeSeconds % 86_400n) / 3_600n;
      const minutes = (wholeSeconds % 3_600n) / 60n;
      const seconds = wholeSeconds % 60n;
      const parts = [];
      if (days) parts.push(`${days}d`);
      if (hours) parts.push(`${hours}h`);
      if (minutes) parts.push(`${minutes}m`);
      if (seconds || fractional || parts.length === 0) {
        parts.push(`${seconds}${fractional ? `.${fractional}` : ""}s`);
      }
      return `${parts.join(" ")}${isApproximate ? " approx." : ""}`;
    } catch (_error) {
      return "Exact time unavailable";
    }
  }

  function recipeKeyId(recipeKey) {
    return `${recipeKey.blueprint_type_id}:${recipeKey.activity_id}`;
  }

  function clearEfficienciesForProduct(typeId) {
    [...state.blueprintEfficiencies.entries()].forEach(([key, setting]) => {
      if (setting.product_type_id === typeId) {
        state.blueprintEfficiencies.delete(key);
      }
    });
  }

  function setApiState(status, label) {
    elements.apiState.dataset.state = status;
    elements.apiLabel.textContent = label;
  }

  function showConfigTab() {
    window.industryTabs?.activate("config");
  }

  function acceptIndustryDataVersion(buildNumber) {
    if (state.sdeBuildNumber && state.sdeBuildNumber !== buildNumber) {
      state.choices.clear();
      state.blueprintEfficiencies.clear();
      state.pendingNotice = "Industry data changed; recipe-specific settings were reset.";
    }
    state.sdeBuildNumber = buildNumber;
  }

  async function requestJson(path, options = {}) {
    let response;
    try {
      response = await fetch(apiUrl(path), {
        ...options,
        headers: {
          Accept: "application/json",
          ...(options.headers || {}),
        },
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new ApiRequestError(
        0,
        "network_error",
        "The calculator API could not be reached. Start FastAPI and serve this website over HTTP.",
      );
    }

    const responseText = await response.text();
    let payload = null;
    if (responseText) {
      try {
        payload = JSON.parse(responseText);
      } catch (_error) {
        throw new ApiRequestError(
          response.status,
          "invalid_api_response",
          "The calculator returned an unreadable response.",
        );
      }
    }

    if (!response.ok) {
      const errorBody = payload?.error;
      throw new ApiRequestError(
        response.status,
        errorBody?.code || "api_error",
        errorBody?.message || `The calculator request failed (${response.status}).`,
        errorBody?.details || null,
        payload?.sde_build_number || null,
      );
    }
    return payload;
  }

  async function checkApiHealth() {
    try {
      const response = await fetch(apiUrl("/api/health"), {
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (response.ok && payload.api === "ok" && payload.database === "ok") {
        setApiState("online", "Calculator online");
        return;
      }
      setApiState("offline", "Calculator unavailable");
    } catch (_error) {
      setApiState("offline", "Calculator unavailable");
    }
  }

  function invalidateSearch() {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = null;
    state.searchController?.abort();
    state.searchController = null;
    state.searchRequestId += 1;
    elements.searchInput.removeAttribute("aria-busy");
  }

  function restoreCalculationControls() {
    elements.output.removeAttribute("aria-busy");
    updateCalculateButton();
  }

  function invalidateCalculation() {
    state.calculationController?.abort();
    state.calculationController = null;
    state.calculationRequestId += 1;
    restoreCalculationControls();
  }

  function hideSearchResults() {
    elements.searchResults.hidden = true;
    elements.searchResults.replaceChildren();
  }

  function renderSearchResults(items, buildNumber) {
    elements.searchResults.replaceChildren();
    if (!items.length) {
      hideSearchResults();
      elements.searchStatus.textContent = "No producible items matched that search.";
      return;
    }

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const listItem = createElement("li");
      const button = createElement("button", "search-result-button");
      button.type = "button";
      button.append(
        createElement("span", "search-result-name", item.name),
        createElement("span", "search-result-id", `ID ${item.type_id}`),
        createElement(
          "span",
          "search-result-context",
          `${item.group_name} · ${item.category_name}`,
        ),
      );
      button.setAttribute("aria-label", `Add ${item.name} to the build list`);
      button.addEventListener("click", () => addDemand(item, buildNumber));
      listItem.append(button);
      fragment.append(listItem);
    });

    elements.searchResults.append(fragment);
    elements.searchResults.hidden = false;
    elements.searchStatus.textContent = `${items.length} matching item${items.length === 1 ? "" : "s"}.`;
  }

  async function runSearch(query) {
    state.searchController?.abort();
    state.searchController = new AbortController();
    const requestId = ++state.searchRequestId;
    elements.searchInput.setAttribute("aria-busy", "true");
    elements.searchStatus.textContent = "Searching EVE types...";

    const params = new URLSearchParams({
      search: query,
      producible_only: "true",
      limit: "10",
    });

    try {
      const result = await requestJson(`/api/industry/types?${params}`, {
        signal: state.searchController.signal,
      });
      if (requestId !== state.searchRequestId) return;
      result.items.forEach((item) => state.typeNames.set(item.type_id, item.name));
      renderSearchResults(result.items, result.sde_build_number);
      setApiState("online", "Calculator online");
    } catch (error) {
      if (error.name === "AbortError" || requestId !== state.searchRequestId) return;
      hideSearchResults();
      elements.searchStatus.textContent = error.message;
      if (error.code === "network_error" || error.status === 503) {
        setApiState("offline", "Calculator unavailable");
      }
    } finally {
      if (requestId === state.searchRequestId) {
        elements.searchInput.removeAttribute("aria-busy");
      }
    }
  }

  function invalidateOwnedSearch() {
    window.clearTimeout(state.ownedSearchTimer);
    state.ownedSearchTimer = null;
    state.ownedSearchController?.abort();
    state.ownedSearchController = null;
    state.ownedSearchRequestId += 1;
    elements.ownedSearchInput.removeAttribute("aria-busy");
  }

  function hideOwnedSearchResults() {
    elements.ownedSearchResults.hidden = true;
    elements.ownedSearchResults.replaceChildren();
  }

  function renderOwnedSearchResults(items, buildNumber) {
    elements.ownedSearchResults.replaceChildren();
    if (!items.length) {
      hideOwnedSearchResults();
      elements.ownedSearchStatus.textContent = "No items matched that search.";
      return;
    }

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const listItem = createElement("li");
      const button = createElement("button", "search-result-button");
      button.type = "button";
      button.append(
        createElement("span", "search-result-name", item.name),
        createElement("span", "search-result-id", `ID ${item.type_id}`),
        createElement("span", "search-result-context", `${item.group_name} · ${item.category_name}`),
      );
      button.setAttribute("aria-label", `Add owned ${item.name}`);
      button.addEventListener("click", () => addOwnedMaterial(item, buildNumber));
      listItem.append(button);
      fragment.append(listItem);
    });

    elements.ownedSearchResults.append(fragment);
    elements.ownedSearchResults.hidden = false;
    elements.ownedSearchStatus.textContent = `${items.length} matching item${items.length === 1 ? "" : "s"}.`;
  }

  async function runOwnedSearch(query) {
    state.ownedSearchController?.abort();
    state.ownedSearchController = new AbortController();
    const requestId = ++state.ownedSearchRequestId;
    elements.ownedSearchInput.setAttribute("aria-busy", "true");
    elements.ownedSearchStatus.textContent = "Searching EVE types...";

    const params = new URLSearchParams({ search: query, limit: "10" });
    try {
      const result = await requestJson(`/api/industry/types?${params}`, {
        signal: state.ownedSearchController.signal,
      });
      if (requestId !== state.ownedSearchRequestId) return;
      result.items.forEach((item) => state.typeNames.set(item.type_id, item.name));
      renderOwnedSearchResults(result.items, result.sde_build_number);
      setApiState("online", "Calculator online");
    } catch (error) {
      if (error.name === "AbortError" || requestId !== state.ownedSearchRequestId) return;
      hideOwnedSearchResults();
      elements.ownedSearchStatus.textContent = error.message;
      if (error.code === "network_error" || error.status === 503) {
        setApiState("offline", "Calculator unavailable");
      }
    } finally {
      if (requestId === state.ownedSearchRequestId) {
        elements.ownedSearchInput.removeAttribute("aria-busy");
      }
    }
  }

  function resetShopping() {
    elements.purchases.replaceChildren();
    elements.shoppingPlaceholder.hidden = false;
    elements.shoppingOutput.hidden = true;
    elements.shoppingCount.textContent = "0 items";
    elements.exportStatus.textContent = "";
  }

  function resetOutput() {
    elements.placeholder.hidden = false;
    elements.loading.hidden = true;
    elements.error.hidden = true;
    elements.planOutput.hidden = true;
    elements.output.removeAttribute("aria-busy");
    elements.outputStatus.textContent = "No calculation is currently displayed.";
    state.latestPlan = null;
    resetShopping();
    updateExportActions();
  }

  function markCalculationDirty(message = "Inputs changed. Calculate a new production route.") {
    const hadVisibleResult = state.latestPlan || !elements.loading.hidden || !elements.error.hidden;
    state.inputRevision += 1;
    invalidateCalculation();
    if (hadVisibleResult) {
      resetOutput();
      elements.outputStatus.textContent = message;
    }
    updateExportActions();
  }

  function updateCalculateButton() {
    const count = state.demands.size;
    elements.calculateButton.disabled = count === 0 || Boolean(state.calculationController);
    if (state.calculationController) {
      elements.calculateButton.textContent = "Calculating...";
    } else if (count === 0) {
      elements.calculateButton.textContent = "Add an item to calculate";
    } else {
      elements.calculateButton.textContent = `Calculate ${count} product${count === 1 ? "" : "s"}`;
    }
  }

  function renderDemandList({ focusTypeId = null } = {}) {
    elements.demandList.replaceChildren();
    const fragment = document.createDocumentFragment();
    state.demands.forEach((demand, typeId) => {
      const item = createElement("li", "demand-item");
      item.dataset.demandTypeId = String(typeId);
      const copy = createElement("div", "demand-item-copy");
      copy.append(
        createElement("strong", "", demand.item.name),
        createElement("span", "", `${demand.item.group_name} · Type ID ${typeId}`),
      );

      const quantityLabel = createElement("label", "demand-quantity");
      quantityLabel.append(createElement("span", "visually-hidden", `Quantity for ${demand.item.name}`));
      const quantity = document.createElement("input");
      quantity.type = "number";
      quantity.value = String(demand.quantity);
      quantity.min = "1";
      quantity.max = String(MAX_SAFE_INTEGER);
      quantity.step = "1";
      quantity.inputMode = "numeric";
      quantity.dataset.demandQuantity = String(typeId);
      quantity.setAttribute("aria-label", `Quantity for ${demand.item.name}`);
      quantityLabel.append(quantity);

      const remove = createElement("button", "demand-remove", "Remove");
      remove.type = "button";
      remove.dataset.removeDemand = String(typeId);
      remove.setAttribute("aria-label", `Remove ${demand.item.name} from the build list`);
      item.append(copy, quantityLabel, remove);
      fragment.append(item);
    });
    elements.demandList.append(fragment);
    elements.demandEditor.hidden = state.demands.size === 0;
    elements.demandStatus.textContent = state.demands.size
      ? `${state.demands.size} of ${MAX_DEMANDS} output${state.demands.size === 1 ? "" : "s"} selected.`
      : "";
    updateCalculateButton();
    if (focusTypeId !== null) {
      elements.demandList.querySelector(`[data-demand-quantity="${focusTypeId}"]`)?.focus();
    }
  }

  function renderOwnedList({ focusTypeId = null } = {}) {
    elements.ownedList.replaceChildren();
    const fragment = document.createDocumentFragment();
    state.ownedMaterials.forEach((owned, typeId) => {
      const item = createElement("li", "demand-item owned-item");
      const copy = createElement("div", "demand-item-copy");
      copy.append(
        createElement("strong", "", owned.item.name),
        createElement("span", "", `${owned.item.group_name} · Type ID ${typeId}`),
      );

      const quantityLabel = createElement("label", "demand-quantity");
      quantityLabel.append(createElement("span", "visually-hidden", `Owned quantity of ${owned.item.name}`));
      const quantity = document.createElement("input");
      quantity.type = "number";
      quantity.value = String(owned.quantity);
      quantity.min = "1";
      quantity.max = String(MAX_SAFE_INTEGER);
      quantity.step = "1";
      quantity.inputMode = "numeric";
      quantity.dataset.ownedQuantity = String(typeId);
      quantity.setAttribute("aria-label", `Owned quantity of ${owned.item.name}`);
      quantityLabel.append(quantity);

      const remove = createElement("button", "demand-remove", "Remove");
      remove.type = "button";
      remove.dataset.removeOwned = String(typeId);
      remove.setAttribute("aria-label", `Remove owned ${owned.item.name}`);
      item.append(copy, quantityLabel, remove);
      fragment.append(item);
    });
    elements.ownedList.append(fragment);

    const count = state.ownedMaterials.size;
    elements.ownedEditor.hidden = count === 0;
    elements.ownedSummary.textContent = count
      ? `${count} item${count === 1 ? "" : "s"}`
      : "None";
    if (focusTypeId !== null) {
      elements.ownedList.querySelector(`[data-owned-quantity="${focusTypeId}"]`)?.focus();
    }
  }

  function addOwnedMaterial(item, buildNumber) {
    invalidateOwnedSearch();
    if (state.ownedMaterials.has(item.type_id)) {
      hideOwnedSearchResults();
      elements.ownedSearchInput.value = "";
      elements.ownedSearchStatus.textContent = `${item.name} is already in owned materials.`;
      elements.ownedDetails.open = true;
      renderOwnedList({ focusTypeId: item.type_id });
      return;
    }
    if (state.ownedMaterials.size >= MAX_OWNED_MATERIALS) {
      hideOwnedSearchResults();
      elements.ownedSearchStatus.textContent = `Owned materials can contain at most ${MAX_OWNED_MATERIALS} items.`;
      return;
    }

    acceptIndustryDataVersion(buildNumber);
    state.typeNames.set(item.type_id, item.name);
    state.ownedMaterials.set(item.type_id, { item, quantity: 1 });
    elements.ownedSearchInput.value = "";
    elements.ownedSearchStatus.textContent = `${item.name} added to owned materials.`;
    hideOwnedSearchResults();
    elements.ownedDetails.open = true;
    markCalculationDirty("Owned materials changed. Calculate a new production route.");
    renderOverrides();
    renderOwnedList({ focusTypeId: item.type_id });
  }

  function addDemand(item, buildNumber) {
    invalidateSearch();
    if (state.demands.has(item.type_id)) {
      hideSearchResults();
      elements.searchInput.value = "";
      elements.searchStatus.textContent = `${item.name} is already in the build list.`;
      renderDemandList({ focusTypeId: item.type_id });
      return;
    }
    if (state.demands.size >= MAX_DEMANDS) {
      hideSearchResults();
      elements.searchStatus.textContent = `The build list can contain at most ${MAX_DEMANDS} products.`;
      return;
    }
    acceptIndustryDataVersion(buildNumber);
    state.typeNames.set(item.type_id, item.name);
    state.demands.set(item.type_id, { item, quantity: 1 });
    elements.searchInput.value = "";
    elements.searchStatus.textContent = `${item.name} added to the build list.`;
    hideSearchResults();
    renderOverrides();
    markCalculationDirty();
    renderDemandList({ focusTypeId: item.type_id });
  }

  function clearDemands({ preserveQuery = false } = {}) {
    state.demands.clear();
    state.choices.clear();
    state.blueprintEfficiencies.clear();
    if (!preserveQuery) elements.searchInput.value = "";
    hideSearchResults();
    renderOverrides();
    markCalculationDirty();
    renderDemandList();
  }

  function readDemands() {
    const demands = [];
    for (const input of elements.demandList.querySelectorAll("[data-demand-quantity]")) {
      const value = input.value.trim();
      const quantity = /^\d+$/.test(value) ? Number(value) : null;
      if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > MAX_SAFE_INTEGER) {
        input.setCustomValidity("Enter a whole quantity from 1 to 9,007,199,254,740,991.");
        input.reportValidity();
        input.focus();
        return null;
      }
      input.setCustomValidity("");
      const typeId = Number(input.dataset.demandQuantity);
      const demand = state.demands.get(typeId);
      demand.quantity = quantity;
      demands.push({ type_id: typeId, quantity });
    }
    return demands;
  }

  function readOwnedMaterials() {
    const ownedMaterials = [];
    for (const input of elements.ownedList.querySelectorAll("[data-owned-quantity]")) {
      const value = input.value.trim();
      const quantity = /^\d+$/.test(value) ? Number(value) : null;
      if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > MAX_SAFE_INTEGER) {
        input.setCustomValidity("Enter a whole quantity from 1 to 9,007,199,254,740,991.");
        elements.ownedDetails.open = true;
        input.reportValidity();
        input.focus();
        return null;
      }
      input.setCustomValidity("");
      const typeId = Number(input.dataset.ownedQuantity);
      state.ownedMaterials.get(typeId).quantity = quantity;
      ownedMaterials.push({ type_id: typeId, quantity });
    }
    return ownedMaterials;
  }

  function percentToBasisPoints(input, maximum = 9_999) {
    const value = input.value.trim();
    if (!/^\d+(?:\.\d{1,2})?$/.test(value)) {
      input.setCustomValidity("Enter a percentage with no more than two decimal places.");
      return null;
    }
    const [whole, fraction = ""] = value.split(".");
    const basisPoints = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
    if (!Number.isSafeInteger(basisPoints) || basisPoints < 0 || basisPoints > maximum) {
      input.setCustomValidity(`Enter a percentage from 0 to ${(maximum / 100).toFixed(2)}.`);
      return null;
    }
    input.setCustomValidity("");
    return basisPoints;
  }

  function parseIdList(input) {
    const value = input.value.trim();
    if (!value) {
      input.setCustomValidity("");
      return [];
    }
    if (!/^\d+(?:\s*,\s*\d+)*$/.test(value)) {
      input.setCustomValidity("Enter positive IDs separated by commas.");
      return null;
    }
    const ids = value.split(",").map((part) => Number(part.trim()));
    if (
      ids.some((id) => !Number.isSafeInteger(id) || id < 1 || id > 2_147_483_647)
      || new Set(ids).size !== ids.length
      || ids.length > 100
    ) {
      input.setCustomValidity("Use up to 100 unique positive IDs.");
      return null;
    }
    input.setCustomValidity("");
    return ids;
  }

  function modifierInput(kind, activity, effect) {
    return app.querySelector(
      `[data-profile-modifier="${kind}"][data-profile-activity="${activity}"][data-profile-effect="${effect}"]`,
    );
  }

  function scopeInput(activity, scope) {
    return app.querySelector(`[data-rig-scope="${scope}"][data-profile-activity="${activity}"]`);
  }

  function productionSkillLevel(field) {
    const input = app.querySelector(`[data-production-profile-field="${field}"]`);
    return Number(input?.value || 0);
  }

  function readProductionProfile() {
    const profile = {
      industry_level: productionSkillLevel("industry_level"),
      advanced_industry_level: productionSkillLevel("advanced_industry_level"),
      reactions_level: productionSkillLevel("reactions_level"),
      facility_modifiers: [],
      rig_modifiers: [],
      setup_overrides: [],
    };

    for (const activity of ["manufacturing", "reaction"]) {
      const facilityMaterialInput = modifierInput("facility", activity, "material");
      const facilityTimeInput = modifierInput("facility", activity, "time");
      const rigMaterialInput = modifierInput("rig", activity, "material");
      const rigTimeInput = modifierInput("rig", activity, "time");
      const categoryInput = scopeInput(activity, "category_ids");
      const groupInput = scopeInput(activity, "group_ids");
      const facilityMaterial = percentToBasisPoints(facilityMaterialInput);
      const facilityTime = percentToBasisPoints(facilityTimeInput);
      const rigMaterial = percentToBasisPoints(rigMaterialInput);
      const rigTime = percentToBasisPoints(rigTimeInput);
      const categoryIds = parseIdList(categoryInput);
      const groupIds = parseIdList(groupInput);
      const inputs = [
        facilityMaterialInput,
        facilityTimeInput,
        rigMaterialInput,
        rigTimeInput,
        categoryInput,
        groupInput,
      ];
      if ([facilityMaterial, facilityTime, rigMaterial, rigTime, categoryIds, groupIds]
        .some((value) => value === null)) {
        const invalid = inputs.find((input) => !input.validity.valid);
        showConfigTab();
        invalid?.reportValidity();
        invalid?.focus();
        return { ok: false, value: null };
      }
      if (facilityMaterial > 0 || facilityTime > 0) {
        profile.facility_modifiers.push({
          activity,
          material_reduction_basis_points: facilityMaterial,
          time_reduction_basis_points: facilityTime,
        });
      }
      if (rigMaterial > 0 || rigTime > 0) {
        profile.rig_modifiers.push({
          activity,
          material_reduction_basis_points: rigMaterial,
          time_reduction_basis_points: rigTime,
          category_ids: categoryIds,
          group_ids: groupIds,
        });
      } else if (categoryIds.length || groupIds.length) {
        rigMaterialInput.setCustomValidity("Enter a rig material or time reduction for this scope.");
        showConfigTab();
        rigMaterialInput.reportValidity();
        rigMaterialInput.focus();
        return { ok: false, value: null };
      }
    }

    const setupOverrideResult = globalThis.industrySetupOverrides?.readRequest()
      || { ok: true, value: [] };
    if (!setupOverrideResult.ok) {
      showConfigTab();
      setupOverrideResult.invalid?.closest("details")?.setAttribute("open", "");
      setupOverrideResult.invalid?.reportValidity();
      setupOverrideResult.invalid?.focus();
      return { ok: false, value: null };
    }
    profile.setup_overrides = setupOverrideResult.value;

    const hasEffect = profile.industry_level > 0
      || profile.advanced_industry_level > 0
      || profile.reactions_level > 0
      || profile.facility_modifiers.length > 0
      || profile.rig_modifiers.length > 0
      || profile.setup_overrides.length > 0;
    return { ok: true, value: hasEffect ? profile : null };
  }

  function readSpecialistSkills() {
    const inputs = [...app.querySelectorAll(
      '[data-skill-role="industry"][data-skill-type-id]',
    )];
    const hasSpecialistLevel = inputs.some(
      (input) => !input.dataset.productionProfileField && Number(input.value) > 0,
    );
    if (!hasSpecialistLevel) return null;
    return inputs
      .map((input) => ({
        type_id: Number(input.dataset.skillTypeId),
        level: Number(input.value),
      }))
      .filter(({ level }) => level > 0)
      .sort((left, right) => left.type_id - right.type_id);
  }

  function readPricing() {
    const pricing = {};
    for (const input of app.querySelectorAll("[data-pricing-integer]")) {
      const rawValue = input.value.trim();
      if (!rawValue && input.hasAttribute("data-pricing-optional")) {
        input.setCustomValidity("");
        continue;
      }
      const value = /^\d+$/.test(rawValue) ? Number(rawValue) : null;
      if (!Number.isSafeInteger(value) || value < 1 || value > 2_147_483_647) {
        const systemSearch = input.closest("[data-system-picker]")
          ?.querySelector("[data-system-search]");
        const validationTarget = systemSearch || input;
        validationTarget.setCustomValidity("Select a solar system from the results.");
        showConfigTab();
        validationTarget.reportValidity();
        validationTarget.focus();
        return { ok: false, value: null };
      }
      input.setCustomValidity("");
      input.closest("[data-system-picker]")
        ?.querySelector("[data-system-search]")
        ?.setCustomValidity("");
      pricing[input.dataset.pricingInteger] = value;
    }
    for (const input of app.querySelectorAll("[data-pricing-percent]")) {
      const basisPoints = percentToBasisPoints(input, 10_000);
      if (basisPoints === null) {
        showConfigTab();
        input.reportValidity();
        input.focus();
        return { ok: false, value: null };
      }
      pricing[input.dataset.pricingPercent] = basisPoints;
    }
    pricing.reaction_scc_surcharge_basis_points = pricing.scc_surcharge_basis_points;
    return { ok: true, value: pricing };
  }

  function choiceLabel(typeId, choice) {
    const name = state.typeNames.get(typeId) || `Type ${typeId}`;
    if (choice.decision === "buy") return { name, detail: "Buy instead of build" };
    if (choice.recipe_key) {
      return {
        name,
        detail: `Blueprint ${choice.recipe_key.blueprint_type_id} · Activity ${choice.recipe_key.activity_id}`,
      };
    }
    return { name, detail: "Build with the available recipe" };
  }

  function renderOverrides() {
    elements.overridesList.replaceChildren();
    const sortedChoices = [...state.choices.entries()].sort(([left], [right]) => left - right);
    const sortedEfficiencies = [...state.blueprintEfficiencies.entries()].sort(
      ([left], [right]) => left.localeCompare(right),
    );
    elements.overridesPanel.hidden = sortedChoices.length === 0 && sortedEfficiencies.length === 0;

    const fragment = document.createDocumentFragment();
    sortedChoices.forEach(([typeId, choice]) => {
      const label = choiceLabel(typeId, choice);
      const item = createElement("li", "override-item");
      const copy = createElement("span", "override-item-copy");
      copy.append(
        createElement("strong", "", label.name),
        createElement("span", "", label.detail),
      );
      const remove = createElement("button", "override-remove", "Remove");
      remove.type = "button";
      remove.dataset.removeChoice = String(typeId);
      remove.setAttribute("aria-label", `Remove build choice for ${label.name}`);
      item.append(copy, remove);
      fragment.append(item);
    });
    sortedEfficiencies.forEach(([key, setting]) => {
      const blueprintName = state.typeNames.get(setting.recipe_key.blueprint_type_id)
        || `Blueprint ${setting.recipe_key.blueprint_type_id}`;
      const item = createElement("li", "override-item override-item--efficiency");
      const copy = createElement("span", "override-item-copy");
      copy.append(
        createElement("strong", "", blueprintName),
        createElement(
          "span",
          "",
          `ME ${setting.material_efficiency}% / TE ${setting.time_efficiency}%`,
        ),
      );
      const remove = createElement("button", "override-remove", "Reset");
      remove.type = "button";
      remove.dataset.removeEfficiency = key;
      remove.setAttribute("aria-label", `Reset blueprint efficiency for ${blueprintName}`);
      item.append(copy, remove);
      fragment.append(item);
    });
    elements.overridesList.append(fragment);
  }

  function showLoading() {
    elements.placeholder.hidden = true;
    elements.error.hidden = true;
    elements.planOutput.hidden = true;
    elements.loading.hidden = false;
    elements.output.setAttribute("aria-busy", "true");
    elements.outputStatus.textContent = "Calculating the production route.";
    elements.calculateButton.disabled = true;
    elements.calculateButton.textContent = "Calculating...";
    resetShopping();
  }

  function finishLoading(requestId) {
    if (requestId !== state.calculationRequestId) return;
    state.calculationController = null;
    restoreCalculationControls();
    updateExportActions();
  }

  function addMetric(list, label, value) {
    const wrapper = createElement("div");
    wrapper.append(
      createElement("dt", "", label),
      createElement("dd", "", value),
    );
    list.append(wrapper);
    return wrapper;
  }

  function efficiencySelect(labelText, field, values, selectedValue, ariaLabel) {
    const label = createElement("label", "efficiency-field");
    const labelCopy = createElement("span", "", labelText);
    const select = createElement("select");
    select.dataset.efficiencyField = field;
    select.setAttribute("aria-label", ariaLabel);
    values.forEach((value) => {
      const option = createElement("option", "", `${value}%`);
      option.value = String(value);
      option.selected = value === selectedValue;
      select.append(option);
    });
    label.append(labelCopy, select);
    return label;
  }

  function renderEfficiencyControls(step) {
    if (step.activity !== "manufacturing") return null;

    const efficiency = step.blueprint_efficiency || {
      material_efficiency: 0,
      time_efficiency: 0,
    };
    const controls = createElement("fieldset", "route-efficiency");
    controls.dataset.blueprintTypeId = String(step.recipe_key.blueprint_type_id);
    controls.dataset.activityId = String(step.recipe_key.activity_id);
    controls.dataset.productTypeId = String(step.product.type_id);
    controls.dataset.appliedMaterialEfficiency = String(efficiency.material_efficiency);
    controls.dataset.appliedTimeEfficiency = String(efficiency.time_efficiency);
    controls.append(createElement("legend", "", "Blueprint efficiency"));

    const fields = createElement("div", "efficiency-fields");
    fields.append(
      efficiencySelect(
        "ME",
        "material_efficiency",
        Array.from({ length: 11 }, (_item, value) => value),
        efficiency.material_efficiency,
        `Material efficiency for ${step.product.name}`,
      ),
      efficiencySelect(
        "TE",
        "time_efficiency",
        Array.from({ length: 11 }, (_item, value) => value * 2),
        efficiency.time_efficiency,
        `Time efficiency for ${step.product.name}`,
      ),
    );

    const actions = createElement("div", "efficiency-actions");
    const apply = createElement("button", "buy-button buy-button--secondary efficiency-apply", "Apply");
    apply.type = "button";
    apply.dataset.efficiencyAction = "apply";
    apply.setAttribute("aria-label", `Apply blueprint efficiency for ${step.product.name}`);
    const reset = createElement("button", "buy-button buy-button--secondary efficiency-reset", "Reset");
    reset.type = "button";
    reset.dataset.efficiencyAction = "reset";
    reset.setAttribute("aria-label", `Reset blueprint efficiency for ${step.product.name}`);
    reset.disabled = efficiency.material_efficiency === 0 && efficiency.time_efficiency === 0;
    actions.append(apply, reset);

    controls.append(fields, actions);
    return controls;
  }

  function renderCostComparison(comparison) {
    if (!comparison) return null;
    const wrapper = createElement("section", "route-cost-comparison");
    wrapper.setAttribute("aria-label", "Direct build and market buy comparison");
    const figures = createElement("dl");
    addMetric(figures, "Batch build", formatIsk(comparison.direct_build_cost_isk));
    if (comparison.surplus_quantity > 0) {
      addMetric(
        figures,
        "Net surplus credit",
        formatIsk(comparison.surplus_net_value_isk),
      );
    }
    addMetric(
      figures,
      "Effective build",
      formatIsk(comparison.effective_build_cost_isk),
    );
    addMetric(figures, "Market buy", formatIsk(comparison.direct_buy_cost_isk));
    const note = createElement("p", "route-cost-note");
    if (comparison.lower_cost_option === "build" && comparison.savings_if_built_isk !== null) {
      note.textContent = `Building saves ${formatIsk(comparison.savings_if_built_isk)} on direct cost.`;
      wrapper.dataset.decision = "build";
    } else if (comparison.lower_cost_option === "buy" && comparison.savings_if_built_isk !== null) {
      note.textContent = `Buying saves ${formatIsk(String(comparison.savings_if_built_isk).replace(/^-/, ""))} on direct cost.`;
      wrapper.dataset.decision = "buy";
    } else if (comparison.lower_cost_option === "equal") {
      note.textContent = "Direct build and market buy costs are equal.";
      wrapper.dataset.decision = "equal";
    } else {
      const missing = new Set([
        ...(comparison.missing_sell_quote_type_ids || []),
        ...(comparison.insufficient_sell_liquidity_type_ids || []),
      ]).size
        + Number(comparison.missing_surplus_buy_quote)
        + Number(comparison.insufficient_surplus_buy_liquidity);
      note.textContent = missing
        ? `Comparison incomplete for ${missing} market item${missing === 1 ? "" : "s"}.`
        : "Direct cost comparison is unavailable.";
      wrapper.dataset.decision = "incomplete";
    }
    wrapper.append(figures, note);
    return wrapper;
  }

  function renderBuildStep(step, index, comparison = null) {
    const listItem = createElement("li", "route-step");
    const marker = createElement("span", "route-marker", String(index + 1).padStart(2, "0"));
    marker.setAttribute("aria-hidden", "true");

    const card = createElement("article", "route-card");
    const header = createElement("div", "route-card-header");
    const title = createElement("div", "route-card-title");
    const badge = createElement(
      "span",
      `activity-badge activity-badge--${step.activity}`,
      step.activity,
    );
    title.append(badge, createElement("h3", "", step.product.name));

    const buyButton = createElement("button", "buy-button buy-button--secondary route-action", "Buy instead");
    buyButton.type = "button";
    buyButton.dataset.choiceAction = "buy";
    buyButton.dataset.typeId = String(step.product.type_id);
    buyButton.setAttribute("aria-label", `Buy ${step.product.name} instead of building it`);
    header.append(title, buyButton);

    const metrics = createElement("dl", "route-metrics");
    addMetric(metrics, "Required", formatNumber(step.required_quantity));
    addMetric(metrics, "Per run", formatNumber(step.output_per_run));
    addMetric(metrics, "Runs", formatNumber(step.runs));
    addMetric(metrics, "Produced", formatNumber(step.produced_quantity));
    addMetric(metrics, "Surplus", formatNumber(step.surplus_quantity));
    const exactJobTime = formatDurationFraction(
      step.exact_job_time_seconds,
      step.total_job_time_centiseconds,
    );
    addMetric(metrics, "Job time", exactJobTime);

    const inputs = createElement("div", "route-inputs");
    if (step.inputs.length) {
      inputs.append(createElement("p", "", "Inputs for all runs"));
      const inputList = createElement("ul");
      step.inputs.forEach((input) => {
        state.typeNames.set(input.item.type_id, input.item.name);
        const inputItem = createElement("li");
        const inputName = createElement("span", "", input.item.name);
        const inputTotal = createElement("span", "route-input-total");
        inputTotal.append(createElement("strong", "", formatNumber(input.total_quantity)));
        inputItem.append(inputName, inputTotal);
        inputList.append(inputItem);
      });
      inputs.append(inputList);
    } else {
      inputs.append(createElement("p", "route-zero-inputs", "This job has no material inputs."));
    }

    const cardParts = [header];
    const efficiencyControls = renderEfficiencyControls(step);
    const costComparison = renderCostComparison(comparison);
    if (efficiencyControls) cardParts.push(efficiencyControls);
    cardParts.push(metrics);
    if (costComparison) cardParts.push(costComparison);
    cardParts.push(inputs);
    card.append(...cardParts);
    listItem.append(marker, card);
    return listItem;
  }

  function renderPurchase(purchase, valuedItem = null) {
    state.typeNames.set(purchase.item.type_id, purchase.item.name);
    const item = createElement("li", "purchase-item");
    const copy = createElement("div", "purchase-item-copy");
    const reason = purchase.reason === "buy_override" ? "Buy choice" : "No recipe";
    copy.append(
      createElement("strong", "", purchase.item.name),
      createElement("span", "purchase-reason", reason),
    );
    const numbers = createElement("div", "purchase-numbers");
    numbers.append(createElement("strong", "purchase-quantity", formatNumber(purchase.quantity)));
    if (valuedItem) {
      numbers.append(
        createElement(
          "span",
          "purchase-unit-price",
          valuedItem.unit_price_isk === null
            ? "Price unavailable"
            : `${formatIsk(valuedItem.unit_price_isk)} each`,
        ),
        createElement("span", "purchase-total-price", formatIsk(valuedItem.total_isk)),
      );
    }
    item.append(copy, numbers);
    if (valuedItem?.has_sufficient_liquidity === false) {
      item.append(createElement("p", "liquidity-warning", "Cached sell volume does not cover this quantity."));
    }

    if (purchase.reason === "buy_override") {
      const action = createElement("button", "buy-button buy-button--secondary purchase-action", "Build instead");
      action.type = "button";
      action.dataset.choiceAction = "auto";
      action.dataset.typeId = String(purchase.item.type_id);
      action.setAttribute("aria-label", `Return ${purchase.item.name} to automatic planning`);
      item.append(action);
    }
    return item;
  }

  function formatEveTimestamp(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "time unavailable";
    return `${new Intl.DateTimeFormat("en-GB", {
      timeZone: "UTC",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date)} EVE`;
  }

  function renderValuation(valuation) {
    elements.valuationPanel.hidden = !valuation;
    if (!valuation) return;
    const { market_snapshot: snapshot, pricing_options: options, economics } = valuation;
    elements.marketStamp.dataset.state = snapshot.status;
    elements.marketLocation.textContent = "Jita";
    elements.marketStatus.textContent = snapshot.status === "fresh"
      ? "Fresh snapshot"
      : snapshot.status === "stale" ? "Stale snapshot" : "Snapshot unavailable";
    const resourceDates = snapshot.resources
      .map((resource) => new Date(resource.fetched_at))
      .filter((date) => !Number.isNaN(date.getTime()));
    const oldestFetch = resourceDates.length
      ? new Date(Math.min(...resourceDates.map((date) => date.getTime())))
      : null;
    elements.marketDetail.textContent = [
      "best sell inputs · best unrestricted buy outputs",
      oldestFetch ? `oldest fetch ${formatEveTimestamp(oldestFetch.toISOString())}` : "no cached resources",
      `manufacturing system ${options.solar_system_id}`,
      options.reaction_solar_system_id
        ? `reaction system ${options.reaction_solar_system_id}`
        : null,
    ].filter(Boolean).join(" · ");

    elements.economicsShopping.textContent = formatIsk(economics.shopping_list_cost.amount_isk);
    elements.economicsInstallation.textContent = formatIsk(economics.installation_cost_total_isk);
    elements.economicsCost.textContent = formatIsk(economics.total_cost_isk);
    elements.economicsOutput.textContent = formatIsk(economics.net_output_value_isk);
    elements.economicsProfit.textContent = formatIsk(economics.profit_isk);
    elements.economicsMargin.textContent = formatProfitMargin(economics.profit_margin);
    elements.economicsSurplus.textContent = formatIsk(
      economics.surplus_inventory_value.amount_isk,
    );
    elements.economicsProfitSurplus.textContent = formatIsk(
      economics.profit_including_surplus_isk,
    );
    elements.economicsMarginSurplus.textContent = formatProfitMargin(
      economics.profit_margin_including_surplus,
    );
    const profitContainer = elements.economicsProfit.closest("div");
    const profitValue = economics.profit_isk === null
      ? null
      : decimalToScaledInteger(String(economics.profit_isk), 2);
    profitContainer.dataset.profitState = profitValue === null
      ? "neutral"
      : profitValue > 0n ? "positive" : profitValue < 0n ? "negative" : "neutral";
    const surplusProfitContainer = elements.economicsProfitSurplus.closest("div");
    const surplusProfitValue = economics.profit_including_surplus_isk === null
      ? null
      : decimalToScaledInteger(String(economics.profit_including_surplus_isk), 2);
    surplusProfitContainer.dataset.profitState = surplusProfitValue === null
      ? "neutral"
      : surplusProfitValue > 0n
        ? "positive"
        : surplusProfitValue < 0n ? "negative" : "neutral";

    const missingTypes = new Set([
      ...economics.missing_data.shopping_sell_quote_type_ids,
      ...economics.missing_data.output_buy_quote_type_ids,
      ...economics.missing_data.adjusted_price_type_ids,
    ]);
    const liquidityTypes = new Set([
      ...economics.missing_data.shopping_sell_liquidity_type_ids,
      ...economics.missing_data.output_buy_liquidity_type_ids,
    ]);
    const noteParts = [];
    noteParts.push(economics.complete ? "Estimate complete." : "Estimate incomplete.");
    if (economics.surplus_inventory.length) {
      noteParts.push(
        economics.profit_including_surplus_isk === null
          ? "Surplus-inclusive profit is incomplete at the cached unrestricted buy level."
          : "Surplus-inclusive profit assumes every leftover unit sells at the cached unrestricted buy price.",
      );
    }
    if (missingTypes.size) {
      noteParts.push(`${missingTypes.size} item price${missingTypes.size === 1 ? " is" : "s are"} missing.`);
    }
    if (liquidityTypes.size) {
      noteParts.push(`${liquidityTypes.size} item${liquidityTypes.size === 1 ? " has" : "s have"} insufficient cached liquidity.`);
    }
    if (economics.missing_data.system_cost_indices.length) {
      noteParts.push(`${economics.missing_data.system_cost_indices.length} system cost index${economics.missing_data.system_cost_indices.length === 1 ? " is" : "es are"} missing.`);
    }
    elements.valuationNote.textContent = noteParts.join(" ");
  }

  function renderPlan(plan) {
    state.latestPlan = plan;
    state.sdeBuildNumber = plan.sde_build_number;
    plan.requested.forEach((item) => state.typeNames.set(item.item.type_id, item.item.name));
    plan.build_steps.forEach((step) => {
      state.typeNames.set(step.product.type_id, step.product.name);
      state.typeNames.set(step.blueprint.type_id, step.blueprint.name);
      if (
        step.blueprint_efficiency
        && (step.blueprint_efficiency.material_efficiency > 0
          || step.blueprint_efficiency.time_efficiency > 0)
      ) {
        state.blueprintEfficiencies.set(recipeKeyId(step.recipe_key), {
          recipe_key: step.recipe_key,
          material_efficiency: step.blueprint_efficiency.material_efficiency,
          time_efficiency: step.blueprint_efficiency.time_efficiency,
          product_type_id: step.product.type_id,
        });
      }
    });

    if (plan.requested.length === 1) {
      const requested = plan.requested[0];
      elements.summaryTitle.textContent = `${formatNumber(requested.quantity)} × ${requested.item.name}`;
    } else {
      elements.summaryTitle.textContent = `${formatNumber(plan.requested.length)} requested products`;
    }
    elements.requestedOutputs.replaceChildren();
    plan.requested.forEach((requested) => {
      elements.requestedOutputs.append(
        createElement("li", "", `${formatNumber(requested.quantity)} × ${requested.item.name}`),
      );
    });
    elements.stepCount.textContent = formatNumber(plan.build_steps.length);
    elements.purchaseCount.textContent = formatNumber(plan.purchases.length);

    const comparisonByRecipe = new Map(
      (plan.valuation?.economics.step_comparisons || [])
        .map((comparison) => [recipeKeyId(comparison.recipe_key), comparison]),
    );
    elements.buildSteps.replaceChildren();
    if (plan.build_steps.length) {
      const stepFragment = document.createDocumentFragment();
      plan.build_steps.forEach((step, index) => stepFragment.append(
        renderBuildStep(step, index, comparisonByRecipe.get(recipeKeyId(step.recipe_key))),
      ));
      elements.buildSteps.append(stepFragment);
    } else {
      elements.buildSteps.append(
        createElement("li", "empty-result", "No build jobs are required for this route."),
      );
    }

    const valuedPurchaseByType = new Map(
      (plan.valuation?.economics.shopping_list || [])
        .map((valuedItem) => [valuedItem.item.type_id, valuedItem]),
    );
    elements.purchases.replaceChildren();
    if (plan.purchases.length) {
      const purchaseFragment = document.createDocumentFragment();
      plan.purchases.forEach((purchase) => purchaseFragment.append(
        renderPurchase(purchase, valuedPurchaseByType.get(purchase.item.type_id)),
      ));
      elements.purchases.append(purchaseFragment);
    } else {
      elements.purchases.append(
        createElement("li", "empty-result", "No material purchases are required."),
      );
    }
    const purchaseCount = plan.purchases.length;
    elements.shoppingCount.textContent = `${formatNumber(purchaseCount)} item${purchaseCount === 1 ? "" : "s"}`;
    elements.shoppingPlaceholder.hidden = true;
    elements.shoppingOutput.hidden = false;
    renderValuation(plan.valuation);

    elements.placeholder.hidden = true;
    elements.loading.hidden = true;
    elements.error.hidden = true;
    elements.planOutput.hidden = false;
    if (state.pendingEfficiencyFocusKey) {
      const focusControls = [...elements.planOutput.querySelectorAll("[data-blueprint-type-id]")]
        .find((controls) => recipeKeyId({
          blueprint_type_id: Number(controls.dataset.blueprintTypeId),
          activity_id: Number(controls.dataset.activityId),
        }) === state.pendingEfficiencyFocusKey);
      focusControls
        ?.querySelector('[data-efficiency-field="material_efficiency"]')
        ?.focus();
      state.pendingEfficiencyFocusKey = null;
    } else if (state.pendingChoiceFocusTypeId !== null) {
      const typeId = state.pendingChoiceFocusTypeId;
      if (state.pendingChoiceOriginTab === "shopping") {
        const shoppingIsActive = app.querySelector(
          '[data-industry-tab="shopping"][aria-selected="true"]',
        );
        if (shoppingIsActive) {
          (elements.copyShopping.disabled ? shoppingIsActive : elements.copyShopping).focus();
        }
      } else {
        const nextAction = elements.planOutput.querySelector(
          `[data-choice-action][data-type-id="${typeId}"]`,
        ) || elements.overridesList.querySelector(`[data-remove-choice="${typeId}"]`);
        nextAction?.focus();
      }
      state.pendingChoiceFocusTypeId = null;
      state.pendingChoiceOriginTab = null;
    }
    const pricingIncomplete = plan.valuation && !plan.valuation.economics.complete;
    elements.outputStatus.textContent = state.pendingNotice
      || (pricingIncomplete
        ? "Production route calculated. The market estimate is incomplete."
        : "Production route calculated.");
    state.pendingNotice = "";
    renderOverrides();
    updateExportActions();
    setApiState("online", "Calculator online");
  }

  function updateExportActions() {
    const enabled = Boolean(
      state.latestPlan
      && state.latestPlan.purchases.length
      && !state.calculationController,
    );
    elements.copyShopping.disabled = !enabled;
  }

  function shoppingListText(plan) {
    return plan.purchases
      .map((purchase) => `${purchase.item.name} ${purchase.quantity}`)
      .join("\n");
  }

  async function copyShoppingList() {
    const plan = state.latestPlan;
    if (!plan?.purchases.length) return;
    const count = plan.purchases.length;
    const value = shoppingListText(plan);
    let fallback = null;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        fallback = document.createElement("textarea");
        fallback.value = value;
        fallback.style.position = "fixed";
        fallback.style.opacity = "0";
        document.body.append(fallback);
        fallback.select();
        if (!document.execCommand("copy")) throw new Error("Copy command failed");
      }
      if (state.latestPlan === plan) {
        elements.exportStatus.textContent = `${count} item${count === 1 ? "" : "s"} copied for EVE Multibuy.`;
      }
    } catch (_error) {
      if (state.latestPlan === plan) {
        elements.exportStatus.textContent = "Copy failed. Allow clipboard access and try again.";
      }
    } finally {
      fallback?.remove();
    }
  }

  function addErrorAction(label, action, data = {}) {
    const button = createElement("button", "buy-button buy-button--secondary error-action", label);
    button.type = "button";
    button.dataset.errorAction = action;
    Object.entries(data).forEach(([key, value]) => {
      button.dataset[key] = String(value);
    });
    elements.errorActions.append(button);
  }

  function showCalculationError(error) {
    state.pendingEfficiencyFocusKey = null;
    state.pendingChoiceFocusTypeId = null;
    state.pendingChoiceOriginTab = null;
    elements.placeholder.hidden = true;
    elements.loading.hidden = true;
    elements.planOutput.hidden = true;
    elements.error.hidden = false;
    elements.errorActions.replaceChildren();
    elements.errorTitle.textContent = "Build route unavailable";
    const message = error.code === "sde_version_mismatch"
      ? "Industry data changed. Calculate the route again."
      : error.message;
    elements.errorMessage.textContent = message;
    elements.outputStatus.textContent = `Calculation failed: ${message}`;
    resetShopping();
    window.industryTabs?.activate("build");

    if (error.code === "recipe_cycle" && Array.isArray(error.details?.type_path)) {
      elements.errorTitle.textContent = "Production cycle found";
      const cycleTypes = [...new Set(error.details.type_path)];
      cycleTypes.forEach((typeId) => {
        const typeName = state.typeNames.get(typeId) || `type ${typeId}`;
        addErrorAction(`Buy ${typeName}`, "buy", { typeId });
      });
    } else if (error.code === "ambiguous_recipe" && Array.isArray(error.details?.candidates)) {
      elements.errorTitle.textContent = "Choose a production recipe";
      error.details.candidates.forEach((candidate) => {
        addErrorAction(
          `Use blueprint ${candidate.blueprint_type_id}`,
          "recipe",
          {
            typeId: error.details.product_type_id,
            blueprintTypeId: candidate.blueprint_type_id,
            activityId: candidate.activity_id,
          },
        );
      });
    } else if (
      error.code === "unused_build_choices"
      || error.code === "unused_blueprint_efficiencies"
      || error.code === "blueprint_efficiency_not_applicable"
    ) {
      addErrorAction("Reset planning overrides", "reset");
    } else if (error.code === "missing_activity_pricing") {
      elements.errorTitle.textContent = "Reaction job location required";
      showConfigTab();
      addErrorAction("Enter reaction costs", "pricing");
    } else if (error.code === "unknown_type") {
      addErrorAction("Choose another item", "change");
    } else {
      addErrorAction("Try calculation again", "retry");
    }

    if (error.code === "network_error" || error.status === 503) {
      setApiState("offline", "Calculator unavailable");
    }
  }

  async function calculate({ recoveryAttempts = MAX_RECOVERY_ATTEMPTS } = {}) {
    if (!state.demands.size) {
      elements.searchStatus.textContent = "Add at least one item before calculating.";
      elements.searchInput.focus();
      return;
    }

    const demands = readDemands();
    if (demands === null) return;
    const ownedMaterials = readOwnedMaterials();
    if (ownedMaterials === null) return;
    const productionProfile = readProductionProfile();
    if (!productionProfile.ok) {
      showConfigTab();
      return;
    }
    const specialistSkills = readSpecialistSkills();
    const pricing = readPricing();
    if (!pricing.ok) {
      showConfigTab();
      return;
    }

    state.calculationController?.abort();
    state.calculationController = new AbortController();
    const requestId = ++state.calculationRequestId;
    const inputRevision = state.inputRevision;
    state.latestPlan = null;
    updateExportActions();
    showLoading();

    const body = {
      demands,
      choices: [...state.choices.entries()].map(([typeId, choice]) => ({
        type_id: typeId,
        ...choice,
      })),
      blueprint_efficiencies: [...state.blueprintEfficiencies.values()].map((setting) => ({
        recipe_key: setting.recipe_key,
        material_efficiency: setting.material_efficiency,
        time_efficiency: setting.time_efficiency,
      })),
    };
    if (ownedMaterials.length) body.owned_materials = ownedMaterials;
    if (productionProfile.value) body.production_profile = productionProfile.value;
    if (specialistSkills) body.specialist_skills = specialistSkills;
    body.pricing = pricing.value;
    if (state.sdeBuildNumber) {
      body.expected_sde_build_number = state.sdeBuildNumber;
    }

    try {
      const plan = await requestJson("/api/industry/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: state.calculationController.signal,
      });
      if (requestId !== state.calculationRequestId || inputRevision !== state.inputRevision) return;
      renderPlan(plan);
    } catch (error) {
      if (
        error.name === "AbortError"
        || requestId !== state.calculationRequestId
        || inputRevision !== state.inputRevision
      ) return;

      if (recoveryAttempts > 0 && error.code === "unused_build_choices") {
        const unusedTypeIds = error.details?.type_ids || [];
        unusedTypeIds.forEach((typeId) => state.choices.delete(typeId));
        state.pendingNotice = "Choices outside the new route were removed.";
        renderOverrides();
        return calculate({ recoveryAttempts: recoveryAttempts - 1 });
      }

      if (recoveryAttempts > 0 && error.code === "unused_blueprint_efficiencies") {
        const unusedRecipeKeys = error.details?.recipe_keys || [];
        unusedRecipeKeys.forEach((recipeKey) => {
          state.blueprintEfficiencies.delete(recipeKeyId(recipeKey));
        });
        state.pendingNotice = "Blueprint settings outside the new route were removed.";
        renderOverrides();
        return calculate({ recoveryAttempts: recoveryAttempts - 1 });
      }

      if (recoveryAttempts > 0 && error.code === "sde_version_mismatch") {
        const currentBuild = error.details?.current_sde_build_number;
        if (currentBuild) state.sdeBuildNumber = currentBuild;
        [...state.choices.entries()].forEach(([typeId, choice]) => {
          if (choice.recipe_key) state.choices.delete(typeId);
        });
        state.blueprintEfficiencies.clear();
        state.pendingNotice = "Industry data changed; recipe-specific settings were reset.";
        renderOverrides();
        return calculate({ recoveryAttempts: recoveryAttempts - 1 });
      }

      showCalculationError(error);
    } finally {
      finishLoading(requestId);
    }
  }

  elements.searchInput.addEventListener("input", () => {
    const query = elements.searchInput.value.trim();
    invalidateSearch();
    hideSearchResults();
    if (query.length < 2) {
      elements.searchStatus.textContent = query ? "Enter at least two characters." : "";
      return;
    }
    state.searchTimer = window.setTimeout(() => runSearch(query), SEARCH_DELAY_MS);
  });

  elements.searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideSearchResults();
    if (event.key === "ArrowDown" && !elements.searchResults.hidden) {
      const firstResult = elements.searchResults.querySelector("button");
      if (firstResult) {
        event.preventDefault();
        firstResult.focus();
      }
    }
  });

  elements.searchResults.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      hideSearchResults();
      elements.searchInput.focus();
      return;
    }
    if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
    const buttons = [...elements.searchResults.querySelectorAll("button")];
    const currentIndex = buttons.indexOf(document.activeElement);
    if (currentIndex === -1) return;
    event.preventDefault();
    const delta = event.key === "ArrowDown" ? 1 : -1;
    const nextIndex = (currentIndex + delta + buttons.length) % buttons.length;
    buttons[nextIndex].focus();
  });

  elements.ownedSearchInput.addEventListener("input", () => {
    const query = elements.ownedSearchInput.value.trim();
    invalidateOwnedSearch();
    hideOwnedSearchResults();
    if (query.length < 2) {
      elements.ownedSearchStatus.textContent = query ? "Enter at least two characters." : "";
      return;
    }
    state.ownedSearchTimer = window.setTimeout(() => runOwnedSearch(query), SEARCH_DELAY_MS);
  });

  elements.ownedSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideOwnedSearchResults();
    if (event.key === "ArrowDown" && !elements.ownedSearchResults.hidden) {
      const firstResult = elements.ownedSearchResults.querySelector("button");
      if (firstResult) {
        event.preventDefault();
        firstResult.focus();
      }
    }
  });

  elements.ownedSearchResults.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      hideOwnedSearchResults();
      elements.ownedSearchInput.focus();
      return;
    }
    if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
    const buttons = [...elements.ownedSearchResults.querySelectorAll("button")];
    const currentIndex = buttons.indexOf(document.activeElement);
    if (currentIndex === -1) return;
    event.preventDefault();
    const delta = event.key === "ArrowDown" ? 1 : -1;
    const nextIndex = (currentIndex + delta + buttons.length) % buttons.length;
    buttons[nextIndex].focus();
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".build-search-field")) hideSearchResults();
    if (!event.target.closest(".owned-search-field")) hideOwnedSearchResults();
  });

  elements.demandList.addEventListener("input", (event) => {
    const quantityInput = event.target.closest("[data-demand-quantity]");
    if (!quantityInput) return;
    const demand = state.demands.get(Number(quantityInput.dataset.demandQuantity));
    if (demand) demand.quantity = quantityInput.value;
    quantityInput.setCustomValidity("");
    markCalculationDirty("Quantity changed. Calculate a new production route.");
  });

  elements.demandList.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-demand]");
    if (!removeButton) return;
    const typeId = Number(removeButton.dataset.removeDemand);
    const keys = [...state.demands.keys()];
    const removedIndex = keys.indexOf(typeId);
    const removedName = state.demands.get(typeId)?.item.name || `Type ${typeId}`;
    state.demands.delete(typeId);
    markCalculationDirty(`${removedName} removed. Calculate a new production route.`);
    const remainingKeys = [...state.demands.keys()];
    const focusTypeId = remainingKeys[Math.min(removedIndex, remainingKeys.length - 1)] ?? null;
    renderDemandList({ focusTypeId });
    elements.demandStatus.textContent = `${removedName} removed from the build list.`;
    if (focusTypeId === null) elements.searchInput.focus();
  });

  elements.clearDemands.addEventListener("click", () => {
    clearDemands();
    elements.searchStatus.textContent = "Build list cleared.";
    elements.searchInput.focus();
  });

  elements.ownedList.addEventListener("input", (event) => {
    const quantityInput = event.target.closest("[data-owned-quantity]");
    if (!quantityInput) return;
    const owned = state.ownedMaterials.get(Number(quantityInput.dataset.ownedQuantity));
    if (owned) owned.quantity = quantityInput.value;
    quantityInput.setCustomValidity("");
    markCalculationDirty("Owned materials changed. Calculate a new production route.");
  });

  elements.ownedList.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-owned]");
    if (!removeButton) return;
    const typeId = Number(removeButton.dataset.removeOwned);
    const keys = [...state.ownedMaterials.keys()];
    const removedIndex = keys.indexOf(typeId);
    const removedName = state.ownedMaterials.get(typeId)?.item.name || `Type ${typeId}`;
    state.ownedMaterials.delete(typeId);
    markCalculationDirty("Owned materials changed. Calculate a new production route.");
    const remainingKeys = [...state.ownedMaterials.keys()];
    const focusTypeId = remainingKeys[Math.min(removedIndex, remainingKeys.length - 1)] ?? null;
    renderOwnedList({ focusTypeId });
    elements.ownedSearchStatus.textContent = `${removedName} removed from owned materials.`;
    if (focusTypeId === null) elements.ownedSearchInput.focus();
  });

  elements.clearOwned.addEventListener("click", () => {
    state.ownedMaterials.clear();
    markCalculationDirty("Owned materials cleared. Calculate a new production route.");
    renderOwnedList();
    elements.ownedSearchStatus.textContent = "Owned materials cleared.";
    elements.ownedSearchInput.focus();
  });

  app.querySelectorAll("[data-profile-skill], [data-profile-modifier], [data-rig-scope]")
    .forEach((input) => input.addEventListener("input", () => {
      input.setCustomValidity("");
      markCalculationDirty("Production profile changed. Calculate a new production route.");
    }));

  app.addEventListener("industry:setup-overrides-changed", () => {
    markCalculationDirty("Category setup changed. Calculate a new production route.");
  });

  app.querySelectorAll(
    "[data-pricing-integer], [data-pricing-percent], [data-config-integer], [data-config-percent]",
  )
    .forEach((input) => input.addEventListener("input", () => {
      input.setCustomValidity("");
      markCalculationDirty("Pricing settings changed. Calculate a new production route.");
    }));

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    calculate();
  });

  elements.overridesPanel.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-choice]");
    const resetEfficiencyButton = event.target.closest("[data-remove-efficiency]");
    if (!removeButton && !resetEfficiencyButton) return;
    const shouldRecalculate = Boolean(state.latestPlan);
    if (removeButton) {
      const typeId = Number(removeButton.dataset.removeChoice);
      state.pendingChoiceFocusTypeId = typeId;
      state.choices.delete(typeId);
    } else {
      state.blueprintEfficiencies.delete(resetEfficiencyButton.dataset.removeEfficiency);
    }
    state.inputRevision += 1;
    renderOverrides();
    if (shouldRecalculate) calculate();
  });

  elements.clearOverrides.addEventListener("click", () => {
    const shouldRecalculate = Boolean(state.latestPlan);
    state.choices.clear();
    state.blueprintEfficiencies.clear();
    state.inputRevision += 1;
    renderOverrides();
    if (shouldRecalculate) calculate();
  });

  app.addEventListener("click", (event) => {
    const efficiencyButton = event.target.closest("[data-efficiency-action]");
    if (efficiencyButton) {
      const controls = efficiencyButton.closest("[data-blueprint-type-id]");
      const recipeKey = {
        blueprint_type_id: Number(controls.dataset.blueprintTypeId),
        activity_id: Number(controls.dataset.activityId),
      };
      const key = recipeKeyId(recipeKey);
      state.pendingEfficiencyFocusKey = key;
      if (efficiencyButton.dataset.efficiencyAction === "reset") {
        state.blueprintEfficiencies.delete(key);
      } else {
        const materialEfficiency = Number(
          controls.querySelector('[data-efficiency-field="material_efficiency"]').value,
        );
        const timeEfficiency = Number(
          controls.querySelector('[data-efficiency-field="time_efficiency"]').value,
        );
        if (materialEfficiency === 0 && timeEfficiency === 0) {
          state.blueprintEfficiencies.delete(key);
        } else {
          state.blueprintEfficiencies.set(key, {
            recipe_key: recipeKey,
            material_efficiency: materialEfficiency,
            time_efficiency: timeEfficiency,
            product_type_id: Number(controls.dataset.productTypeId),
          });
        }
      }
      state.inputRevision += 1;
      renderOverrides();
      calculate();
      return;
    }

    const choiceButton = event.target.closest("[data-choice-action]");
    if (!choiceButton) return;
    const typeId = Number(choiceButton.dataset.typeId);
    state.pendingChoiceFocusTypeId = typeId;
    state.pendingChoiceOriginTab = choiceButton.closest("[data-industry-panel]")
      ?.dataset.industryPanel || "build";
    if (choiceButton.dataset.choiceAction === "buy") {
      clearEfficienciesForProduct(typeId);
      state.choices.set(typeId, { decision: "buy" });
    } else {
      state.choices.delete(typeId);
    }
    state.inputRevision += 1;
    renderOverrides();
    calculate();
  });

  elements.planOutput.addEventListener("change", (event) => {
    const efficiencyField = event.target.closest("[data-efficiency-field]");
    if (!efficiencyField) return;

    const controls = efficiencyField.closest("[data-blueprint-type-id]");
    const materialEfficiency = Number(
      controls.querySelector('[data-efficiency-field="material_efficiency"]').value,
    );
    const timeEfficiency = Number(
      controls.querySelector('[data-efficiency-field="time_efficiency"]').value,
    );
    const hasAppliedEfficiency = Number(controls.dataset.appliedMaterialEfficiency) !== 0
      || Number(controls.dataset.appliedTimeEfficiency) !== 0;
    const hasDraftEfficiency = materialEfficiency !== 0 || timeEfficiency !== 0;
    controls.querySelector('[data-efficiency-action="reset"]').disabled = !hasAppliedEfficiency
      && !hasDraftEfficiency;
  });

  elements.errorActions.addEventListener("click", (event) => {
    const actionButton = event.target.closest("[data-error-action]");
    if (!actionButton) return;
    const action = actionButton.dataset.errorAction;
    const typeId = Number(actionButton.dataset.typeId);

    if (action === "buy") {
      clearEfficienciesForProduct(typeId);
      state.choices.set(typeId, { decision: "buy" });
      state.inputRevision += 1;
      renderOverrides();
      calculate();
    } else if (action === "recipe") {
      clearEfficienciesForProduct(typeId);
      state.choices.set(typeId, {
        decision: "build",
        recipe_key: {
          blueprint_type_id: Number(actionButton.dataset.blueprintTypeId),
          activity_id: Number(actionButton.dataset.activityId),
        },
      });
      state.inputRevision += 1;
      renderOverrides();
      calculate();
    } else if (action === "reset") {
      state.choices.clear();
      state.blueprintEfficiencies.clear();
      state.inputRevision += 1;
      renderOverrides();
      calculate();
    } else if (action === "change") {
      elements.searchInput.focus();
    } else if (action === "pricing") {
      showConfigTab();
      app.querySelector(
        '[data-pricing-integer="reaction_solar_system_id"]',
      )?.closest("[data-system-picker]")
        ?.querySelector("[data-system-search]")
        ?.focus();
    } else {
      calculate();
    }
  });

  elements.copyShopping.addEventListener("click", copyShoppingList);

  renderDemandList();
  renderOwnedList();
  resetShopping();
  updateExportActions();
  checkApiHealth();
})();
