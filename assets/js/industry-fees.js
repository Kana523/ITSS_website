(() => {
  "use strict";
  const app = document.querySelector("[data-industry-app]");
  if (!app) return;
  const mode = app.querySelector('[data-config-choice="sales_tax_mode"]');
  const manual = app.querySelector('[data-pricing-percent="sales_tax_basis_points"]');
  const readout = app.querySelector("[data-effective-sales-tax]");
  if (!mode || !manual || !readout) return;

  function accountingLevel() {
    return Number(app.querySelector('[data-skill-type-id="16622"]')?.value || 0);
  }

  function updateFees({ notify = false } = {}) {
    const automatic = mode.value === "accounting";
    manual.disabled = automatic;
    if (automatic) manual.setCustomValidity("");
    // Thousandths of a percent preserve the exact Accounting V rate, 3.375%.
    const percent = automatic ? (7500 - 825 * accountingLevel()) / 1000 : Number(manual.value);
    readout.textContent = Number.isFinite(percent)
      ? `${percent.toFixed(3).replace(/\.?0+$/, "")}% sales tax${automatic ? ` · Accounting ${accountingLevel()}` : " · manual rate"}`
      : "Enter a valid sales tax rate";
    if (notify) manual.dispatchEvent(new Event("input", { bubbles: true }));
  }

  for (const eventName of ["input", "change"]) {
    app.addEventListener(eventName, (event) => {
      if (event.target === mode || event.target.matches?.('[data-skill-type-id="16622"]')) {
        updateFees({ notify: true });
      } else if (event.target === manual) updateFees();
    });
  }
  app.addEventListener("industry:configuration-applied", () => updateFees({ notify: true }));
  globalThis.industryFees = Object.freeze({
    readOptions: () => mode.value === "accounting" ? { accounting_level: accountingLevel() } : {},
    usesAccounting: () => mode.value === "accounting",
  });
  updateFees();
})();
