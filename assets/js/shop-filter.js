document.addEventListener("DOMContentLoaded", () => {
  // Only filter cards in the product display area
  const cards = Array.from(document.querySelectorAll(".display .item-card"));

  const parentCbs = Array.from(document.querySelectorAll(".filter input[data-parent]"));
  const childCbs  = Array.from(document.querySelectorAll(".filter input[data-child]"));

  const clearBtn = document.getElementById("filter-clear");
  const activeFiltersEl = document.getElementById("active-filters");
  const resultsCountEl = document.getElementById("results-count");

  function labelForCheckbox(cb) {
    const id = cb.id || "";
    if (id) {
      const linkedLabel = document.querySelector(`label[for="${id}"]`);
      if (linkedLabel) return linkedLabel.textContent.trim();
    }

    const wrappingLabel = cb.closest("label");
    if (wrappingLabel) {
      return wrappingLabel.textContent.replace(/\s+/g, " ").trim();
    }

    return (cb.value || "").replace(/[:\-]+/g, " ").trim();
  }

  function renderActiveFilterChips(activeParentBoxes, activeChildBoxes) {
    if (!activeFiltersEl) return;
    activeFiltersEl.innerHTML = "";

    const activeBoxes = [...activeParentBoxes, ...activeChildBoxes];
    if (activeBoxes.length === 0) {
      const empty = document.createElement("span");
      empty.className = "active-filters-empty";
      empty.textContent = "None";
      activeFiltersEl.appendChild(empty);
      return;
    }

    activeBoxes.forEach((cb) => {
      const label = labelForCheckbox(cb);
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "filter-chip";
      chip.textContent = `${label} x`;
      chip.setAttribute("aria-label", `Remove filter ${label}`);
      chip.addEventListener("click", () => {
        cb.checked = false;
        applyFilters();
      });
      activeFiltersEl.appendChild(chip);
    });
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
    parentCbs.forEach(cb => (cb.checked = false));
    childCbs.forEach(cb => (cb.checked = false));
    applyFilters();
  });

  function applyFilters() {
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
      const cat = inferCategory(card);
      const sub = inferSub(card);
      const childKey = sub ? `${cat}:${sub}` : "";

      const show =
        nothingSelected ||
        activeParents.has(cat) ||
        (childKey && activeChildren.has(childKey));

      card.style.display = show ? "" : "none";
      if (show) shownCount += 1;
    });

    if (resultsCountEl) {
      const noun = shownCount === 1 ? "item" : "items";
      resultsCountEl.textContent = `Showing ${shownCount} ${noun}`;
    }

    renderActiveFilterChips(activeParentBoxes, activeChildBoxes);
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
