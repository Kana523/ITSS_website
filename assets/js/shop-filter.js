// Shared price utilities — exposed as window.ShopUtils for shop-cart.js (which loads after this script)
function formatPrice(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return "0";

  function formatUnit(divisor, suffix) {
    const unitValue = amount / divisor;
    const trimmed = unitValue
      .toFixed(1)
      .replace(/(\.\d*?[1-9])0+$/, "$1")
      .replace(/\.0+$/, "");
    return `${trimmed}${suffix}`;
  }

  if (amount >= 1000000000000) return formatUnit(1000000000000, "t");
  if (amount >= 1000000000) return formatUnit(1000000000, "b");
  if (amount >= 1000000) return formatUnit(1000000, "m");
  if (amount >= 1000) return formatUnit(1000, "k");
  return `${Math.round(amount)}`;
}

function parsePriceToIsk(rawValue, fallbackLabel = "") {
  const multipliers = {
    k: 1000,
    thousand: 1000,
    m: 1000000,
    mil: 1000000,
    million: 1000000,
    b: 1000000000,
    bil: 1000000000,
    billion: 1000000000,
    t: 1000000000000,
    tril: 1000000000000,
    trillion: 1000000000000
  };

  const candidates = [rawValue, fallbackLabel];
  for (const candidate of candidates) {
    const text = String(candidate || "").trim();
    if (!text) continue;

    const direct = Number(text.replace(/,/g, ""));
    if (Number.isFinite(direct) && direct > 0) return direct;

    const match = text.match(/^([\d.,]+)\s*([a-zA-Z]+)?\s*(?:isk)?$/i);
    if (!match) continue;

    const numericValue = Number(match[1].replace(/,/g, ""));
    if (!Number.isFinite(numericValue) || numericValue <= 0) continue;

    const unit = String(match[2] || "").toLowerCase();
    const multiplier = unit ? (multipliers[unit] || 1) : 1;
    return numericValue * multiplier;
  }

  return 0;
}

window.ShopUtils = { formatPrice, parsePriceToIsk };

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
  const cardMeta = new Map();

  function stockCountFor(card) {
    const meta = cardMeta.get(card);
    if (meta && Number.isFinite(meta.stock)) return meta.stock;

    const rawCount = meta?.stockCountEl?.dataset.stockRaw || "";
    const parsedRaw = Number.parseInt(rawCount, 10);
    if (Number.isFinite(parsedRaw)) {
      if (meta) meta.stock = parsedRaw;
      return parsedRaw;
    }

    const explicitCount = meta?.stockCountEl?.textContent || "";
    const parsedExplicit = Number.parseInt(explicitCount, 10);
    if (Number.isFinite(parsedExplicit)) {
      if (meta) meta.stock = parsedExplicit;
      return parsedExplicit;
    }

    const ariaLabel = meta?.stockStateEl?.getAttribute("aria-label") || "";
    const parsedFromLabel = Number.parseInt(ariaLabel.replace(/[^\d-]/g, ""), 10);
    const stock = Number.isFinite(parsedFromLabel) ? parsedFromLabel : 0;
    if (meta) meta.stock = stock;
    return stock;
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

  function formatStockCount(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) return "0";

    function formatUnit(divisor, suffix) {
      const unitValue = amount / divisor;
      const trimmed = unitValue
        .toFixed(1)
        .replace(/(\.\d*?[1-9])0+$/, "$1")
        .replace(/\.0+$/, "");
      return `${trimmed}${suffix}`;
    }

    if (amount >= 1000000000000) return formatUnit(1000000000000, "t");
    if (amount >= 1000000000) return formatUnit(1000000000, "b");
    if (amount >= 1000000) return formatUnit(1000000, "m");
    if (amount >= 1000) return formatUnit(1000, "k");
    return String(Math.round(amount));
  }

  function updatePriceEl(el, price) {
    if (!el) return;
    const label = formatPrice(price);
    if (el.querySelector("strong")) {
      el.innerHTML = `<strong>Price:</strong> ${label}`;
    } else if (el.querySelector("b")) {
      el.innerHTML = `<b>Price:</b> ${label}`;
    } else {
      el.textContent = `Price: ${label}`;
    }
  }

  function normalizeStockFeed(payload) {
    const normalized = new Map();
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return normalized;
    }

    Object.entries(payload).forEach(([sku, value]) => {
      if (!value || typeof value !== "object") {
        console.warn(`Stock feed: skipping entry "${sku}" — expected object, got ${typeof value}`);
        return;
      }

      const normalizedSku = normalizeSku(sku);
      const stock = parseStockValue(value.stock);
      if (!normalizedSku || stock === null) {
        console.warn(`Stock feed: skipping entry "${sku}" — missing or invalid sku/stock`);
        return;
      }

      normalized.set(normalizedSku, {
        sku: normalizedSku,
        stock,
        price: parsePriceValue(value.price),
        nextStock: String(value.next_stock || "").trim()
      });
    });

    return normalized;
  }

  function serializeStockMap(stockMap) {
    const serialized = {};

    stockMap.forEach((record, sku) => {
      serialized[sku] = {
        stock: record.stock,
        price: record.price,
        next_stock: record.nextStock || ""
      };
    });

    return serialized;
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
      const record = stockMap.get(cardMeta.get(card)?.sku || "");

      if (record) {
        applyRemoteStock(card, record);
        return;
      }

      syncStockState(card);
    });
  }

  function applyRemoteStock(card, record) {
    if (!card || !record) return;

    const meta = cardMeta.get(card);
    const stockCountEl = meta?.stockCountEl;
    const stockState = meta?.stockStateEl;

    if (stockCountEl) {
      stockCountEl.dataset.stockRaw = String(record.stock);
    }
    if (meta) meta.stock = record.stock;

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
      if (meta) meta.price = record.price;
      updatePriceEl(meta?.priceEl, record.price);
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
    const meta = cardMeta.get(card);
    const stockCount = stockCountFor(card);
    const stockState = meta?.stockStateEl;
    const actionButton = meta?.actionButtonEl;
    const stockCountEl = meta?.stockCountEl;
    const outOfStock = stockCount <= 0;

    card.classList.toggle("item-card--out-of-stock", stockCount <= 0);

    if (!stockState) return;

    if (stockCountEl) {
      stockCountEl.dataset.stockRaw = String(stockCount);
      stockCountEl.textContent = formatStockCount(stockCount);
    }

    stockState.setAttribute("aria-label", `In stock: ${stockCount}`);
    stockState.tabIndex = outOfStock ? 0 : -1;

    if (outOfStock && !stockState.dataset.nextStock) {
      stockState.dataset.nextStock = "Restock Pending";
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

  function createCardMeta(card, index) {
    const name = String(card.querySelector("h2, h3")?.textContent || "").trim();
    const subtitle = String(card.querySelector(":scope > p")?.textContent || "").trim();
    const category = inferCategory(card);
    const sub = inferSub(card);
    const sku = normalizeSku(card.dataset.sku);

    const priceEl = card.querySelector(".item-price") || card.querySelector(".item-card-footer p");

    // Use parsePriceToIsk so formatted strings like "1.5 mil ISK" in HTML are handled correctly.
    // Normalize the attribute to a plain number so subsequent reads (cart, sorting) are consistent.
    const price = parsePriceToIsk(card.dataset.price);
    card.dataset.price = String(price);
    updatePriceEl(priceEl, price);

    return {
      index,
      sku,
      name,
      typeLabel: subtitle || (sub ? `${category} ${sub}` : category),
      category,
      sub,
      searchText: `${name.toLowerCase()} ${subtitle.toLowerCase()} ${sku} ${category} ${sub}`.trim(),
      stockStateEl: card.querySelector(".stock-state"),
      stockCountEl: card.querySelector(".stock-state-count"),
      actionButtonEl: card.querySelector("[data-cart-add]"),
      priceEl,
      stock: null,
      price
    };
  }

  cards.forEach((card, index) => {
    cardMeta.set(card, createCardMeta(card, index));
  });

  function childrenFor(parentValue) {
    const prefix = parentValue + ":";
    return childCbs.filter(cb => (cb.value || "").toLowerCase().startsWith(prefix));
  }

  function searchTextFor(card) {
    return cardMeta.get(card)?.searchText || "";
  }

  function nameFor(card) {
    return cardMeta.get(card)?.name || "";
  }

  function typeLabelFor(card) {
    return cardMeta.get(card)?.typeLabel || "";
  }

  function priceFor(card) {
    return cardMeta.get(card)?.price || 0;
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

      return (cardMeta.get(a)?.index || 0) - (cardMeta.get(b)?.index || 0);
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
      const meta = cardMeta.get(card);
      const cat = meta?.category || "";
      const sub = meta?.sub || "";
      const childKey = sub ? `${cat}:${sub}` : "";
      const stockCount = meta?.stock ?? stockCountFor(card);
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
        (a, b) => (cardMeta.get(a)?.index || 0) - (cardMeta.get(b)?.index || 0)
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
