(() => {
  const STORAGE_KEY = "itss:a11y-mode";
  const ROOT_ATTR = "data-a11y";
  const ON = "on";
  const OFF = "off";

  function supportsStorage() {
    try {
      const probeKey = "__itss_a11y_probe__";
      localStorage.setItem(probeKey, "1");
      localStorage.removeItem(probeKey);
      return true;
    } catch (error) {
      return false;
    }
  }

  const hasStorage = supportsStorage();

  function readMode() {
    if (!hasStorage) return null;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved === ON || saved === OFF ? saved : null;
    } catch (error) {
      return null;
    }
  }

  function persistMode(mode) {
    if (!hasStorage) return;
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch (error) {
      // Ignore write errors (private mode, locked storage, etc.)
    }
  }

  function getCurrentMode() {
    return document.documentElement.getAttribute(ROOT_ATTR) === ON ? ON : OFF;
  }

  function syncToggleVisuals(isOn) {
    const text = isOn ? "A11Y ON" : "A11Y OFF";
    const label = isOn ? "Turn accessibility mode off" : "Turn accessibility mode on";

    document.querySelectorAll("[data-a11y-toggle], #a11y-toggle").forEach((toggle) => {
      toggle.setAttribute("aria-pressed", String(isOn));
      toggle.setAttribute("aria-label", label);
      toggle.dataset.state = isOn ? ON : OFF;

      const textNode = toggle.querySelector(".a11y-toggle-text");
      if (textNode) textNode.textContent = text;
    });
  }

  function setMode(mode, options = {}) {
    const nextMode = mode === ON ? ON : OFF;
    const isOn = nextMode === ON;
    document.documentElement.setAttribute(ROOT_ATTR, nextMode);
    syncToggleVisuals(isOn);

    if (options.persist) {
      persistMode(nextMode);
    }
  }

  // Apply early so mode survives reload without waiting for user interaction.
  const startupMode = readMode();
  document.documentElement.setAttribute(ROOT_ATTR, startupMode === ON ? ON : OFF);

  document.addEventListener("DOMContentLoaded", () => {
    const toggles = Array.from(document.querySelectorAll("[data-a11y-toggle], #a11y-toggle"));

    toggles.forEach((toggle) => {
      if (toggle.dataset.a11yBound === "true") return;
      toggle.dataset.a11yBound = "true";
      toggle.type = "button";
      toggle.setAttribute("data-a11y-toggle", "");

      toggle.addEventListener("click", () => {
        const nextMode = getCurrentMode() === ON ? OFF : ON;
        setMode(nextMode, { persist: true });
      });
    });

    setMode(getCurrentMode(), { persist: false });
  });

  // Keep tabs in sync.
  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY) return;
    if (event.newValue !== ON && event.newValue !== OFF) return;
    setMode(event.newValue, { persist: false });
  });
})();
