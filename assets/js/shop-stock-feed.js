// Encapsulates all interaction with the remote stock data source (Google Sheets via Apps Script)
// and the local cache used as a fallback. Exposed as window.ShopStockFeed for shop-filter.js.
(function () {
  const STOCK_CACHE_KEY = "itss_shop_stock_cache_v1";
  const STOCK_CACHE_FRESH_AGE_MS = 15 * 60 * 1000;
  const STOCK_CACHE_FALLBACK_AGE_MS = 30 * 24 * 60 * 60 * 1000;

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

  function loadCachedSnapshot(options = {}) {
    const allowStale = options.allowStale !== false;

    try {
      const rawCache = localStorage.getItem(STOCK_CACHE_KEY);
      if (!rawCache) return null;

      const parsedCache = JSON.parse(rawCache);
      if (!parsedCache || typeof parsedCache !== "object") return null;

      const cachedAt = Number(parsedCache.cachedAt);
      if (!Number.isFinite(cachedAt)) return null;

      const ageMs = Date.now() - cachedAt;
      if (ageMs > STOCK_CACHE_FALLBACK_AGE_MS) {
        return null;
      }

      const isFresh = ageMs <= STOCK_CACHE_FRESH_AGE_MS;
      if (!allowStale && !isFresh) return null;

      const normalized = normalizeStockFeed(parsedCache.records);
      if (normalized.size === 0) return null;

      return {
        cachedAt,
        isFresh,
        records: normalized
      };
    } catch {
      return null;
    }
  }

  function saveCache(stockMap) {
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

  function isEndpointConfigured(endpoint) {
    const value = String(endpoint || "").trim();
    if (!value) return false;
    if (value.includes("PASTE_YOUR_GOOGLE_APPS_SCRIPT")) return false;
    return true;
  }

  async function fetchRemote(endpoint) {
    const response = await fetch(endpoint, {
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

    return stockMap;
  }

  // Apps Script web apps reject custom Content-Type from browsers (CORS preflight),
  // so the body is sent as text/plain and the script JSON.parses it server-side.
  async function submitOrder(endpoint, { orderId = "", charName = "", items, turnstileToken }) {
    if (!isEndpointConfigured(endpoint)) {
      throw new Error("Order endpoint is not configured.");
    }

    const requestBody = { action: "order", items, turnstileToken };
    if (orderId) requestBody.orderId = orderId;
    if (charName) requestBody.charName = charName;

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=utf-8" },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      throw new Error(`Order request failed with ${response.status}`);
    }

    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error("Server returned an invalid response.");
    }

    if (!payload || payload.ok !== true) {
      throw new Error(payload?.error || "Server rejected the order.");
    }

    return payload;
  }

  window.ShopStockFeed = {
    loadCachedSnapshot,
    saveCache,
    fetchRemote,
    submitOrder,
    isEndpointConfigured
  };
})();
