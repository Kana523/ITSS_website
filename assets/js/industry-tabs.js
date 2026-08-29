(() => {
  "use strict";

  const app = document.querySelector("[data-industry-app]");
  if (!app) return;

  const STORAGE_KEY = "itss_industry_active_tab_v1";
  const DEFAULT_TAB = "build";
  const tabList = app.querySelector('[role="tablist"]');
  const tabs = [...app.querySelectorAll("[data-industry-tab]")];
  const panels = [...app.querySelectorAll("[data-industry-panel]")];
  const validTabs = new Set(tabs.map((tab) => tab.dataset.industryTab));
  if (!tabs.length || tabs.length !== panels.length || !validTabs.has(DEFAULT_TAB)) return;

  function storedTab() {
    try {
      const value = window.localStorage.getItem(STORAGE_KEY);
      return validTabs.has(value) ? value : DEFAULT_TAB;
    } catch (_error) {
      return DEFAULT_TAB;
    }
  }

  function persistTab(name) {
    try {
      window.localStorage.setItem(STORAGE_KEY, name);
    } catch (_error) {
      // Tab selection still works when browser storage is unavailable.
    }
  }

  function activate(name, { focus = false, persist = true } = {}) {
    const selectedName = validTabs.has(name) ? name : DEFAULT_TAB;
    const selectedTab = tabs.find((tab) => tab.dataset.industryTab === selectedName);

    tabs.forEach((tab) => {
      const selected = tab === selectedTab;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.industryPanel !== selectedName;
    });

    if (persist) persistTab(selectedName);
    if (focus) selectedTab?.focus();
    app.dispatchEvent(new CustomEvent("industry:tab-changed", {
      detail: { tab: selectedName },
    }));
  }

  const compactLayout = window.matchMedia("(max-width: 820px)");
  function syncOrientation() {
    tabList?.setAttribute("aria-orientation", compactLayout.matches ? "horizontal" : "vertical");
  }
  compactLayout.addEventListener?.("change", syncOrientation);
  syncOrientation();

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab.dataset.industryTab));
    tab.addEventListener("keydown", (event) => {
      const directionalKeys = compactLayout.matches
        ? ["ArrowRight", "ArrowLeft"]
        : ["ArrowDown", "ArrowUp"];
      if (!directionalKeys.includes(event.key) && !["Home", "End"].includes(event.key)) return;
      event.preventDefault();

      let nextIndex;
      if (event.key === "Home") nextIndex = 0;
      else if (event.key === "End") nextIndex = tabs.length - 1;
      else {
        const delta = ["ArrowDown", "ArrowRight"].includes(event.key) ? 1 : -1;
        nextIndex = (index + delta + tabs.length) % tabs.length;
      }
      activate(tabs[nextIndex].dataset.industryTab, { focus: true });
    });
  });

  app.addEventListener("industry:show-tab", (event) => {
    activate(event.detail?.tab, { focus: Boolean(event.detail?.focusTab) });
  });

  window.addEventListener("storage", (event) => {
    if (event.key === STORAGE_KEY) activate(storedTab(), { persist: false });
  });

  window.industryTabs = Object.freeze({ activate });
  activate(storedTab(), { persist: false });
})();
