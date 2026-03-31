document.addEventListener("DOMContentLoaded", () => {
  // Only filter cards in the product display area
  const cards = Array.from(document.querySelectorAll(".display .item-card"));
  const display = document.querySelector(".display");
  const stockEndpoint = (document.body?.dataset.stockEndpoint || "").trim();
  const STOCK_CACHE_KEY = "itss_shop_stock_cache_v1";
  const STOCK_CACHE_MAX_AGE_MS = 15 * 60 * 1000;

  const parentCbs = Array.from(document.querySelectorAll(".filter input[data-parent]"));
  const childCbs  = Array.from(document.querySelectorAll(".filter input[data-child]"));

  const clearBtn = document.getElementById("filter-clear");
  const searchInput = document.getElementById("filter-search");
  const sortSelect = document.getElementById("display-sort");
  const resultsCountEl = document.getElementById("results-count");
  const originalOrder = new Map(cards.map((card, index) => [card, index]));

  function stockCountFor(card) {
    const explicitCount = card.querySelector(".stock-state-count")?.textContent || "";
    const parsedExplicit = Number.parseInt(explicitCount, 10);
    if (Number.isFinite(parsedExplicit)) return parsedExplicit;

    const ariaLabel = card.querySelector(".stock-state")?.getAttribute("aria-label") || "";
    const parsedFromLabel = Number.parseInt(ariaLabel.replace(/[^\d-]/g, ""), 10);
    return Number.isFinite(parsedFromLabel) ? parsedFromLabel : 0;
  }

  function normalizeSku(value) {
    return String(value || "").trim().toLowerCase();
  }

  function parseStockValue(value) {
    const parsed = Number.parseInt(String(value ?? "").trim(), 10);
    if (!Number.isFinite(parsed)) return null;
    return Math.max(0, parsed);
  }

  function parsePriceValue(value) {
    const parsed = Number(String(value ?? "").trim().replace(/,/g, ""));
    if (!Number.isFinite(parsed)) return null;
    return Math.max(0, parsed);
  }

  function formatPrice(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) return "0 ISK";

    function formatUnit(divisor, suffix) {
      const unitValue = amount / divisor;
      const trimmed = unitValue
        .toFixed(3)
        .replace(/(\.\d*?[1-9])0+$/, "$1")
        .replace(/\.0+$/, "");
      return `${trimmed} ${suffix} ISK`;
    }

    if (amount >= 1000000000000) {
      return formatUnit(1000000000000, "tril");
    }
    if (amount >= 1000000000) {
      return formatUnit(1000000000, "bil");
    }
    if (amount >= 1000000) {
      return formatUnit(1000000, "mil");
    }
    if (amount >= 1000) {
      return formatUnit(1000, "k");
    }
    return `${Math.round(amount)} ISK`;
  }

  function stockRecordFromValue(rawValue, fallbackSku = "") {
    const fallbackStock = typeof rawValue === "number" || typeof rawValue === "string"
      ? parseStockValue(rawValue)
      : null;

    if (fallbackStock !== null) {
      return {
        sku: normalizeSku(fallbackSku),
        stock: fallbackStock,
        nextStock: "",
        price: null
      };
    }

    if (!rawValue || typeof rawValue !== "object") {
      return null;
    }

    const sku = normalizeSku(rawValue.sku || fallbackSku);
    const stock = parseStockValue(
      rawValue.stock
      ?? rawValue.qty
      ?? rawValue.quantity
      ?? rawValue.in_stock
      ?? rawValue.inStock
    );

    if (!sku || stock === null) {
      return null;
    }

    const nextStock = String(
      rawValue.next_stock
      ?? rawValue.nextStock
      ?? rawValue.restock
      ?? rawValue.restock_eta
      ?? rawValue.restockEta
      ?? ""
    ).trim();

    const price = parsePriceValue(
      rawValue.price
      ?? rawValue.price_isk
      ?? rawValue.priceIsk
      ?? rawValue.isk_price
      ?? rawValue.iskPrice
    );

    return { sku, stock, nextStock, price };
  }

  function normalizeStockFeed(payload) {
    const normalized = new Map();

    if (Array.isArray(payload)) {
      payload.forEach((entry) => {
        const record = stockRecordFromValue(entry);
        if (record) normalized.set(record.sku, record);
      });
      return normalized;
    }

    if (!payload || typeof payload !== "object") {
      return normalized;
    }

    const listPayload = payload.items || payload.data || payload.rows || payload.stock;
    if (Array.isArray(listPayload)) {
      listPayload.forEach((entry) => {
        const record = stockRecordFromValue(entry);
        if (record) normalized.set(record.sku, record);
      });
      return normalized;
    }

    Object.entries(payload).forEach(([sku, value]) => {
      const record = stockRecordFromValue(value, sku);
      if (record) normalized.set(record.sku, record);
    });

    return normalized;
  }

  function serializeStockMap(stockMap) {
    return Array.from(stockMap.values()).map((record) => ({
      sku: record.sku,
      stock: record.stock,
      nextStock: record.nextStock || "",
      price: record.price
    }));
  }

  function loadCachedStockMap() {
    try {
      const rawCache = localStorage.getItem(STOCK_CACHE_KEY);
      if (!rawCache) return null;

      const parsedCache = JSON.parse(rawCache);
      if (!parsedCache || typeof parsedCache !== "object") return null;

      const cachedAt = Number(parsedCache.cachedAt);
      if (!Number.isFinite(cachedAt)) return null;

      if (Date.now() - cachedAt > STOCK_CACHE_MAX_AGE_MS) {
        return null;
      }

      const normalized = normalizeStockFeed(parsedCache.records);
      return normalized.size > 0 ? normalized : null;
    } catch {
      return null;
    }
  }

  function saveCachedStockMap(stockMap) {
    if (!(stockMap instanceof Map) || stockMap.size === 0) return;

    try {
      localStorage.setItem(STOCK_CACHE_KEY, JSON.stringify({
        cachedAt: Date.now(),
        records: serializeStockMap(stockMap)
      }));
    } catch {
      // Ignore storage failures so the live feed still works normally.
    }
  }

  function applyStockMapToCards(stockMap) {
    cards.forEach((card) => {
      const sku = normalizeSku(card.dataset.sku);
      const record = stockMap.get(sku);

      if (record) {
        applyRemoteStock(card, record);
        return;
      }

      syncStockState(card);
    });
  }

  function applyRemoteStock(card, record) {
    if (!card || !record) return;

    const stockCountEl = card.querySelector(".stock-state-count");
    const stockState = card.querySelector(".stock-state");
    const priceEl = card.querySelector(".item-price") || card.querySelector(".item-card-footer p");

    if (stockCountEl) {
      stockCountEl.textContent = String(record.stock);
    }

    if (stockState) {
      stockState.setAttribute("aria-label", `In stock: ${record.stock}`);

      if (record.nextStock) {
        stockState.dataset.nextStock = record.nextStock;
      } else {
        delete stockState.dataset.nextStock;
      }
    }

    if (record.price !== null) {
      card.dataset.price = String(record.price);

      if (priceEl?.querySelector("strong")) {
        priceEl.innerHTML = `<strong>Price:</strong> ${formatPrice(record.price)}`;
      } else if (priceEl?.querySelector("b")) {
        priceEl.innerHTML = `<b>Price:</b> ${formatPrice(record.price)}`;
      } else if (priceEl) {
        priceEl.textContent = `Price: ${formatPrice(record.price)}`;
      }
    }

    syncStockState(card);
  }

  async function loadRemoteStock() {
    const cachedStockMap = loadCachedStockMap();
    const hasCachedStock = cachedStockMap instanceof Map && cachedStockMap.size > 0;

    if (hasCachedStock) {
      applyStockMapToCards(cachedStockMap);
      document.dispatchEvent(new CustomEvent("shop:product-data-updated"));
      applyFilters();
    }

    if (!stockEndpoint || stockEndpoint.includes("PASTE_YOUR_GOOGLE_APPS_SCRIPT")) {
      if (!hasCachedStock) {
        cards.forEach(syncStockState);
        applyFilters();
      }
      return;
    }

    try {
      const response = await fetch(stockEndpoint, {
        headers: {
          Accept: "application/json"
        }
      });

      if (!response.ok) {
        throw new Error(`Stock request failed with ${response.status}`);
      }

      const payload = await response.json();
      const stockMap = normalizeStockFeed(payload);

      if (stockMap.size === 0) {
        console.warn("Stock feed loaded but did not contain any usable rows.");
      }

      saveCachedStockMap(stockMap);
      applyStockMapToCards(stockMap);

      document.dispatchEvent(new CustomEvent("shop:product-data-updated"));
    } catch (error) {
      console.error("Unable to load remote stock feed.", error);
      if (!hasCachedStock) {
        cards.forEach(syncStockState);
      }
    }

    applyFilters();
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

  function nameFor(card) {
    return String(card.querySelector("h2, h3")?.textContent || "").trim();
  }

  function typeLabelFor(card) {
    const explicitLabel = String(card.querySelector(":scope > p")?.textContent || "").trim();
    if (explicitLabel) return explicitLabel;

    const category = inferCategory(card);
    const sub = inferSub(card);
    return sub ? `${category} ${sub}` : category;
  }

  function priceFor(card) {
    const parsed = Number(String(card.dataset.price || "").replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function compareText(left, right) {
    return left.localeCompare(right, undefined, {
      sensitivity: "base",
      numeric: true
    });
  }

  function sortVisibleCards(visibleCards) {
    const sortMode = sortSelect?.value || "default";

    visibleCards.sort((a, b) => {
      const nameComparison = compareText(nameFor(a), nameFor(b));

      if (sortMode === "stock-desc") {
        return stockCountFor(b) - stockCountFor(a) || nameComparison;
      }

      if (sortMode === "stock-asc") {
        return stockCountFor(a) - stockCountFor(b) || nameComparison;
      }

      if (sortMode === "type-asc") {
        return compareText(typeLabelFor(a), typeLabelFor(b)) || nameComparison;
      }

      if (sortMode === "name-asc") {
        return nameComparison;
      }

      if (sortMode === "price-desc") {
        return priceFor(b) - priceFor(a) || nameComparison;
      }

      if (sortMode === "price-asc") {
        return priceFor(a) - priceFor(b) || nameComparison;
      }

      return (originalOrder.get(a) || 0) - (originalOrder.get(b) || 0);
    });

    return visibleCards;
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
    if (sortSelect) sortSelect.value = "default";
    parentCbs.forEach(cb => (cb.checked = false));
    childCbs.forEach(cb => (cb.checked = false));
    applyFilters();
  });

  searchInput?.addEventListener("input", applyFilters);
  sortSelect?.addEventListener("change", applyFilters);

  function applyFilters() {
    const query = (searchInput?.value || "").trim().toLowerCase();
    const activeParentBoxes = parentCbs.filter(c => c.checked);
    const activeChildBoxes = childCbs.filter(c => c.checked);

    const activeParents = new Set(
      activeParentBoxes.map(c => (c.value || "").toLowerCase())
    );

    const categoryParents = new Set(
      [...activeParents].filter(value => value !== "instock")
    );

    const activeChildren = new Set(
      activeChildBoxes.map(c => (c.value || "").toLowerCase())
    );

    const nothingSelected = categoryParents.size === 0 && activeChildren.size === 0;
    let shownCount = 0;
    const visibleCards = [];
    const hiddenCards = [];

    cards.forEach(card => {
      syncStockState(card);

      const cat = inferCategory(card);
      const sub = inferSub(card);
      const childKey = sub ? `${cat}:${sub}` : "";
      const stockCount = stockCountFor(card);
      const matchesSearch = !query || searchTextFor(card).includes(query);
      const matchesStock = !activeParents.has("instock") || stockCount > 0;
      const matchesCategory =
        nothingSelected ||
        categoryParents.has(cat) ||
        (childKey && activeChildren.has(childKey));

      const show =
        matchesSearch &&
        matchesStock &&
        matchesCategory;

      card.style.display = show ? "" : "none";
      if (show) {
        shownCount += 1;
        visibleCards.push(card);
        return;
      }

      hiddenCards.push(card);
    });

    if (display) {
      const sortedVisibleCards = sortVisibleCards(visibleCards);
      const hiddenInOriginalOrder = hiddenCards.sort(
        (a, b) => (originalOrder.get(a) || 0) - (originalOrder.get(b) || 0)
      );

      [...sortedVisibleCards, ...hiddenInOriginalOrder].forEach((card) => {
        display.appendChild(card);
      });
    }

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

  void loadRemoteStock();
});
