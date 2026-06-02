// Home "Highlights" row — random capital boats into .container-items, reusing
// the shop catalog (ShopCatalog) + stock feed (ShopAPI). In-stock first, rest
// as pre-order fillers. Full add-to-cart cards (same as the store).
document.addEventListener("DOMContentLoaded", () => {
  const container = document.querySelector("[data-highlights]");
  if (!container) return;

  if (!window.ShopCatalog || !window.ShopUtils) {
    console.error("home-highlights.js: ShopCatalog/ShopUtils missing — shop-catalog.js / shop-utils.js failed to load.");
    return;
  }

  const { CATALOG, createCard } = window.ShopCatalog;
  const { formatPrice, normalizeName, isLocalHost } = window.ShopUtils;
  const endpoint = (document.body?.dataset.stockEndpoint || "").trim();

  const HIGHLIGHT_COUNT = 3;
  const IMG_ROOT = "assets/images/items/";

  // capital boats = the "boats" category
  const capitals = CATALOG.filter((item) => item.category === "boats");
  if (capitals.length === 0) return;

  const storeMoreCard = container.querySelector(".store-more-card");

  function shuffle(list) {
    const arr = list.slice();
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  function describe(item, stockMap) {
    const record = stockMap.get(normalizeName(item.name));
    const stock  = record ? record.stock : 0;
    const price  = record && record.price !== null ? record.price : item.price;
    return { item, stock, price, outOfStock: stock <= 0 };
  }

  // In-stock capitals first (random among them), then random out-of-stock fillers.
  function pickHighlights(stockMap) {
    const described = capitals.map((item) => describe(item, stockMap));
    const inStock = shuffle(described.filter((c) => !c.outOfStock));
    const fillers = shuffle(described.filter((c) => c.outOfStock));
    return [...inStock, ...fillers].slice(0, HIGHLIGHT_COUNT);
  }

  // shared catalog builder; category colours but never the muted OOS state
  // (always bright; OOS items still add, labelled ORDER)
  function renderCard(entry) {
    const { item, stock, price, outOfStock } = entry;
    return createCard(item, {
      imageRoot: IMG_ROOT,
      categorized: true,
      action: "button",
      actionLabel: outOfStock ? "ORDER" : "ADD TO CART",
      priceText: formatPrice(price),
      stockText: formatPrice(stock),
      stockValue: stock,
      outOfStock: false,
      extraClass: "highlight-card",
      flip: true,
    });
  }

  function render(entries) {
    container.querySelectorAll(".highlight-card").forEach((el) => el.remove());
    const frag = document.createDocumentFragment();
    entries.forEach((entry) => frag.appendChild(renderCard(entry)));
    container.insertBefore(frag, storeMoreCard || null);
    // Let the cart re-sync prices of any in-cart item after a live-feed refresh.
    document.dispatchEvent(new CustomEvent("shop:product-data-updated"));
  }

  function cachedSnapshot() {
    return window.ShopAPI?.loadCachedSnapshot?.({ allowStale: true }) || null;
  }

  function stockMapFrom(snapshot) {
    return snapshot?.records instanceof Map ? snapshot.records : new Map();
  }

  // first paint from cache (unknown stock → pre-order); items locked here so a
  // later live-feed refresh never swaps them out
  const snapshot = cachedSnapshot();
  let highlighted = pickHighlights(stockMapFrom(snapshot));
  render(highlighted);

  // Refresh from the live feed when the cache is missing/stale, then re-tier.
  const REFRESH_MIN_INTERVAL_MS = 5 * 60 * 1000;
  const cachedAt = Number(snapshot?.cachedAt);
  const cacheFresh =
    !isLocalHost() && Number.isFinite(cachedAt) && Date.now() - cachedAt < REFRESH_MIN_INTERVAL_MS;

  if (!cacheFresh && window.ShopAPI?.isEndpointConfigured?.(endpoint)) {
    window.ShopAPI.fetchRemote(endpoint)
      .then((stockMap) => {
        if (!(stockMap instanceof Map) || stockMap.size === 0) return;
        window.ShopAPI.saveCache(stockMap);
        // Keep the items picked on first paint; only refresh their stock/price.
        highlighted = highlighted.map((entry) => describe(entry.item, stockMap));
        render(highlighted);
      })
      .catch((error) => console.error("home-highlights.js: stock refresh failed.", error));
  }
});
