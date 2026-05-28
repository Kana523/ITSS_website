// Outside-API integrations for the shop: Google Apps Script (stock + orders)
// and Cloudflare Turnstile (bot verification). Exposed as window.ShopAPI.
(function () {
  // ── Stock cache ──────────────────────────────────────────────────────────────
  const STOCK_CACHE_KEY = "itss_shop_stock_cache_v1";
  const STOCK_CACHE_FRESH_AGE_MS = 15 * 60 * 1000;
  const STOCK_CACHE_FALLBACK_AGE_MS = 30 * 24 * 60 * 60 * 1000;

  const normalizeName = window.ShopUtils?.normalizeName
    || ((value) => String(value || "").trim().toLowerCase().replace(/\s+/g, " "));

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

    Object.entries(payload).forEach(([rawName, value]) => {
      if (!value || typeof value !== "object") {
        console.warn(`Stock feed: skipping entry "${rawName}" — expected object, got ${typeof value}`);
        return;
      }

      const key = normalizeName(rawName);
      const stock = parseStockValue(value.stock);
      if (!key || stock === null) {
        console.warn(`Stock feed: skipping entry "${rawName}" — missing or invalid name/stock`);
        return;
      }

      const parsedWeeks = Number.parseInt(String(value.weeks ?? "").trim(), 10);
      normalized.set(key, {
        key,
        stock,
        price: parsePriceValue(value.price),
        nextStock: String(value.next_stock || "").trim(),
        weeks: Number.isFinite(parsedWeeks) && parsedWeeks > 0 ? parsedWeeks : null
      });
    });

    return normalized;
  }

  function serializeStockMap(stockMap) {
    const serialized = {};

    stockMap.forEach((record, key) => {
      serialized[key] = {
        stock: record.stock,
        price: record.price,
        next_stock: record.nextStock || "",
        weeks: record.weeks ?? ""
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
    const sep = endpoint.includes("?") ? "&" : "?";
    const response = await fetch(`${endpoint}${sep}_=${Date.now()}`, {
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

  async function refreshNow(endpoint) {
    if (!isEndpointConfigured(endpoint)) return null;
    const stockMap = await fetchRemote(endpoint);
    if (stockMap.size > 0) saveCache(stockMap);
    return stockMap;
  }

  // ── Cloudflare Turnstile ─────────────────────────────────────────────────────
  const TURNSTILE_CONTAINER_SELECTOR = "#cart-turnstile";
  const TURNSTILE_TOKEN_MAX_AGE_MS = 4 * 60 * 1000;
  let turnstileWidgetId = null;
  let turnstilePending = null;
  let cachedTurnstileToken = null;
  let cachedTurnstileTokenAt = 0;

  function turnstileSitekey() {
    return document.querySelector(TURNSTILE_CONTAINER_SELECTOR)?.dataset.sitekey || "";
  }

  function ensureTurnstileRendered() {
    if (turnstileWidgetId !== null) return Promise.resolve();
    if (!document.querySelector(TURNSTILE_CONTAINER_SELECTOR) || !turnstileSitekey()) {
      return Promise.reject(new Error("Turnstile container missing"));
    }
    return new Promise((resolve, reject) => {
      const start = Date.now();
      const tick = () => {
        if (window.turnstile?.render) {
          try {
            turnstileWidgetId = window.turnstile.render(TURNSTILE_CONTAINER_SELECTOR, {
              sitekey: turnstileSitekey(),
              size: "invisible",
              theme: "dark",
              callback: (token) => {
                if (turnstilePending) {
                  turnstilePending.resolve(token);
                  turnstilePending = null;
                } else {
                  cachedTurnstileToken = token;
                  cachedTurnstileTokenAt = Date.now();
                }
              },
              "error-callback": () => {
                if (turnstilePending) {
                  turnstilePending.reject(new Error("Turnstile challenge failed"));
                  turnstilePending = null;
                }
              },
              "timeout-callback": () => {
                if (turnstilePending) {
                  turnstilePending.reject(new Error("Turnstile timed out"));
                  turnstilePending = null;
                }
              },
            });
            resolve();
          } catch (e) {
            reject(e);
          }
          return;
        }
        if (Date.now() - start > 8000) {
          reject(new Error("Turnstile script never loaded"));
          return;
        }
        setTimeout(tick, 120);
      };
      tick();
    });
  }

  async function getTurnstileToken() {
    if (cachedTurnstileToken && Date.now() - cachedTurnstileTokenAt < TURNSTILE_TOKEN_MAX_AGE_MS) {
      const token = cachedTurnstileToken;
      cachedTurnstileToken = null;
      return token;
    }
    await ensureTurnstileRendered();
    if (turnstilePending) {
      turnstilePending.reject(new Error("Turnstile superseded"));
      turnstilePending = null;
    }
    return new Promise((resolve, reject) => {
      turnstilePending = { resolve, reject };
      try {
        window.turnstile.reset(turnstileWidgetId);
        window.turnstile.execute(turnstileWidgetId);
      } catch (e) {
        turnstilePending = null;
        reject(e);
      }
    });
  }

  // Render + fire the invisible challenge before checkout so a token is ready
  // when the user actually clicks Place Order. No-op if a fresh token exists.
  function prewarmTurnstile() {
    if (!turnstileSitekey()) return;
    const tokenFresh = cachedTurnstileToken && Date.now() - cachedTurnstileTokenAt < TURNSTILE_TOKEN_MAX_AGE_MS;
    if (turnstilePending || tokenFresh) return;
    ensureTurnstileRendered().then(() => {
      if (turnstilePending) return;
      try { window.turnstile.execute(turnstileWidgetId); } catch (_) {}
    }).catch(() => {});
  }

  window.ShopAPI = {
    loadCachedSnapshot,
    saveCache,
    fetchRemote,
    submitOrder,
    isEndpointConfigured,
    refreshNow,
    getTurnstileToken,
    prewarmTurnstile,
  };
})();
