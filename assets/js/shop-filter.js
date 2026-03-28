document.addEventListener("DOMContentLoaded", () => {
  // Only filter cards in the product display area
  const cards = Array.from(document.querySelectorAll(".display .item-card"));

  const parentCbs = Array.from(document.querySelectorAll(".filter input[data-parent]"));
  const childCbs  = Array.from(document.querySelectorAll(".filter input[data-child]"));

  const clearBtn = document.getElementById("filter-clear");
  const searchInput = document.getElementById("filter-search");
  const resultsCountEl = document.getElementById("results-count");

  function stockCountFor(card) {
    const explicitCount = card.querySelector(".stock-state-count")?.textContent || "";
    const parsedExplicit = Number.parseInt(explicitCount, 10);
    if (Number.isFinite(parsedExplicit)) return parsedExplicit;

    const ariaLabel = card.querySelector(".stock-state")?.getAttribute("aria-label") || "";
    const parsedFromLabel = Number.parseInt(ariaLabel.replace(/[^\d-]/g, ""), 10);
    return Number.isFinite(parsedFromLabel) ? parsedFromLabel : 0;
  }

  function syncStockState(card) {
    const stockCount = stockCountFor(card);
    const stockState = card.querySelector(".stock-state");
    const actionButton = card.querySelector("[data-cart-add]");
    const outOfStock = stockCount <= 0;

    card.classList.toggle("item-card--out-of-stock", stockCount <= 0);

    if (!stockState) return;

    stockState.setAttribute("aria-label", `In stock: ${stockCount}`);
    stockState.tabIndex = outOfStock ? 0 : -1;

    if (outOfStock && !stockState.dataset.nextStock) {
      stockState.dataset.nextStock = "Next stock date not set yet.";
    }

    if (actionButton) {
      actionButton.textContent = outOfStock ? "RESERVE" : "BUY";
    }
  }

  function inferCategory(card) {
    const explicit = (card.dataset.category || "").trim().toLowerCase();
    if (explicit) return explicit;

    // Fallback (helps if you forget data-category while prototyping)
    const typeText = (card.querySelector(".type")?.textContent || "").toLowerCase();
    if (typeText.includes("blueprint")) return "blueprints";

    const imgSrc = (card.querySelector("img")?.getAttribute("src") || "").toLowerCase();
    if (imgSrc.includes("/ships/")) return "boats";
    if (imgSrc.includes("/modules/")) return "modules";
    if (imgSrc.includes("/materials/")) return "materials";
    if (imgSrc.includes("/blueprints/")) return "blueprints";
    return "other";
  }

  function inferSub(card) {
    const explicit = (card.dataset.sub || "").trim().toLowerCase();
    return explicit || ""; // only needed for sub-filters (moon/ore/planetary)
  }

  function childrenFor(parentValue) {
    const prefix = parentValue + ":";
    return childCbs.filter(cb => (cb.value || "").toLowerCase().startsWith(prefix));
  }

  function searchTextFor(card) {
    const name = (card.querySelector("h2, h3")?.textContent || "").toLowerCase();
    const subtitle = (card.querySelector("p")?.textContent || "").toLowerCase();
    const sku = (card.dataset.sku || "").toLowerCase();
    const category = inferCategory(card);
    const sub = inferSub(card);
    return `${name} ${subtitle} ${sku} ${category} ${sub}`.trim();
  }

  // Parent checked => show whole category, so clear its children
  parentCbs.forEach(parent => {
    parent.addEventListener("change", () => {
      if (parent.checked) {
        childrenFor((parent.value || "").toLowerCase()).forEach(ch => { ch.checked = false; });
      }
      applyFilters();
    });
  });

  // Any child checked => narrow within parent, so uncheck the parent
  childCbs.forEach(child => {
    child.addEventListener("change", () => {
      const v = (child.value || "").toLowerCase();
      const parentValue = v.split(":")[0];
      if (child.checked) {
        const parentBox = parentCbs.find(p => (p.value || "").toLowerCase() === parentValue);
        if (parentBox) parentBox.checked = false;
      }
      applyFilters();
    });
  });

  clearBtn?.addEventListener("click", () => {
    if (searchInput) searchInput.value = "";
    parentCbs.forEach(cb => (cb.checked = false));
    childCbs.forEach(cb => (cb.checked = false));
    applyFilters();
  });

  searchInput?.addEventListener("input", applyFilters);

  function applyFilters() {
    const query = (searchInput?.value || "").trim().toLowerCase();
    const activeParentBoxes = parentCbs.filter(c => c.checked);
    const activeChildBoxes = childCbs.filter(c => c.checked);

    const activeParents = new Set(
      activeParentBoxes.map(c => (c.value || "").toLowerCase())
    );

    const activeChildren = new Set(
      activeChildBoxes.map(c => (c.value || "").toLowerCase())
    );

    const nothingSelected = activeParents.size === 0 && activeChildren.size === 0;
    let shownCount = 0;

    cards.forEach(card => {
      syncStockState(card);

      const cat = inferCategory(card);
      const sub = inferSub(card);
      const childKey = sub ? `${cat}:${sub}` : "";
      const matchesSearch = !query || searchTextFor(card).includes(query);

      const show =
        matchesSearch &&
        (
          nothingSelected ||
          activeParents.has(cat) ||
          (childKey && activeChildren.has(childKey))
        );

      card.style.display = show ? "" : "none";
      if (show) shownCount += 1;
    });

    if (resultsCountEl) {
      const noun = shownCount === 1 ? "item" : "items";
      resultsCountEl.textContent = `Showing ${shownCount} ${noun}`;
    }

  }

  // --- Filter dropdown toggles (arrow only) ---
  const toggleBtns = Array.from(document.querySelectorAll(".filter-toggle"));
  toggleBtns.forEach((toggleBtn) => {
    const controlsId = toggleBtn.getAttribute("aria-controls");
    const subMenu = controlsId ? document.getElementById(controlsId) : null;
    if (!subMenu) return;

    const setOpen = (open) => {
      subMenu.hidden = !open;
      toggleBtn.classList.toggle("open", open);
      toggleBtn.setAttribute("aria-expanded", String(open));
    };

    setOpen(false);

    toggleBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      setOpen(subMenu.hidden); // hidden -> open, open -> hidden
    });
  });

  applyFilters();
});
