document.addEventListener("DOMContentLoaded", () => {
  const cartCountEl      = document.getElementById("cart-count");
  const cartItemCountEl  = document.getElementById("cart-item-count");
  const cartItemsEl      = document.getElementById("cart-items");
  const cartTotalEl      = document.getElementById("cart-total");
  const cartTotalCompactEl = document.getElementById("cart-total-compact");
  const cartPreorderSummaryEl     = document.getElementById("cart-preorder-summary");
  const cartPreorderSummaryTextEl = document.getElementById("cart-preorder-summary-text");
  const cartClearBtn     = document.getElementById("cart-clear");
  const cartClearNameBtn = document.getElementById("cart-clear-name");
  const cartToggleBtn    = document.getElementById("cart-toggle");
  const cartDrawer       = document.getElementById("cart-drawer");
  const cartBackdrop     = document.getElementById("cart-backdrop");
  const cartDrawerClose  = document.getElementById("cart-drawer-close");
  const cartCheckoutBtn  = document.getElementById("cart-checkout");
  const cartCheckoutNameBtn = document.getElementById("cart-checkout-name");
  const orderIdGeneratedEl    = document.getElementById("cart-orderid-generated");
  const orderIdCopyBtn        = document.getElementById("cart-orderid-copy");
  const nameErrorEl           = document.getElementById("cart-name-error");
  const orderIdErrorEl        = document.getElementById("cart-orderid-error");
  const orderEndpoint = (document.body?.dataset.stockEndpoint || "").trim();

  if (!cartItemsEl || !cartTotalEl) return;

  if (!window.ShopUtils) {
    console.error("shop-cart.js: window.ShopUtils missing — shop-utils.js failed to load.");
    return;
  }
  if (!window.ShopAPI) {
    console.error("shop-cart.js: window.ShopAPI missing — shop-api.js failed to load.");
    return;
  }
  if (!window.ShopCatalog) {
    console.error("shop-cart.js: window.ShopCatalog missing — shop-catalog.js failed to load.");
    return;
  }
  const { formatPrice, formatPriceLong, formatPriceCompact, parsePriceToIsk, normalizeName, isLocalHost } = window.ShopUtils;
  // Per-item fitting lists + by-name lookup live in the catalog (boats/structures).
  const { fittingsFor, fittingByName } = window.ShopCatalog;
  const CART_STORAGE_KEY = "itss_shop_cart_v1";
  const ORDER_ID_LENGTH = 20;
  const ORDER_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

  function generateOrderId() {
    const buf = new Uint32Array(ORDER_ID_LENGTH);
    crypto.getRandomValues(buf);
    let out = "";
    for (let i = 0; i < ORDER_ID_LENGTH; i++) {
      out += ORDER_ID_ALPHABET[buf[i] % ORDER_ID_ALPHABET.length];
    }
    return out;
  }

  let cart = loadCart();

  // ── Persistence ─────────────────────────────────────────────────────────────

  function loadCart() {
    try {
      const stored = localStorage.getItem(CART_STORAGE_KEY);
      if (!stored) return {};
      const parsed = JSON.parse(stored);
      if (!parsed || typeof parsed !== "object") return {};

      const normalized = {};
      Object.entries(parsed).forEach(([rawKey, item]) => {
        if (!item || typeof item !== "object") return;
        const safeName  = String(item.name || "").trim();
        const safeKey   = normalizeName(safeName || rawKey);
        const safeQty   = Number(item.qty);
        const safePrice = parsePriceToIsk(item.price, item.priceLabel);
        if (!safeKey || !safeName || !Number.isFinite(safeQty) || safeQty < 1) return;

        const category = String(item.category || "").trim();

        // blueprints: restore runs + maxRuns, clamping runs into [1, maxRuns]
        let bp = {};
        if (category.toLowerCase() === "blueprints") {
          const m   = Math.floor(Number(item.maxRuns));
          const max = Number.isFinite(m) && m >= 1 ? m : 1;
          const r   = Math.floor(Number(item.runs));
          const runs = Number.isFinite(r) && r >= 1 ? Math.min(r, max) : max;
          bp = { maxRuns: max, runs };
        }

        normalized[safeKey] = {
          key:        safeKey,
          name:       safeName,
          qty:        Math.floor(safeQty),
          price:      Number.isFinite(safePrice) ? safePrice : 0,
          priceLabel: formatPrice(Number.isFinite(safePrice) ? safePrice : 0),
          category,
          img:        String(item.img       || "").trim(),
          extras:     Array.isArray(item.extras) ? item.extras : [],
          ...bp,
        };
      });
      return normalized;
    } catch {
      return {};
    }
  }

  function saveCart() {
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
  }

  // ── Product data helpers ─────────────────────────────────────────────────────

  function getProductData(card) {
    if (!card) return null;
    const key = String(card.dataset.name || "").trim();
    if (!key) return null;
    const name     = String(card.querySelector("h2, h3")?.textContent || "Unnamed item").trim();
    const price    = parsePriceToIsk(card.dataset.price);
    const category = String(card.dataset.category || "").trim();
    const imgEl    = card.querySelector("img");
    const img      = imgEl ? imgEl.src : "";
    const maxRunsRaw = Number.parseInt(card.dataset.maxRuns || "", 10);
    const maxRuns  = Number.isFinite(maxRunsRaw) ? maxRunsRaw : null;
    return { key, name, price, category, img, maxRuns };
  }

  const MAX_QTY = 999999999;

  function parseQtyDigits(str) {
    return String(str ?? "").replace(/[^\d]/g, "");
  }

  function formatQty(n) {
    const num = Number(n);
    if (!Number.isFinite(num)) return "0";
    return num.toLocaleString("en-US");
  }

  function clampQty(rawQty) {
    const digits = parseQtyDigits(rawQty);
    const parsed = Number.parseInt(digits, 10);
    if (!Number.isFinite(parsed) || parsed < 1) return 1;
    return Math.min(parsed, MAX_QTY);
  }

  function resizeQtyInput(input) {
    if (!input) return;
    const digits = Math.max(1, String(input.value || "").length);
    input.style.width = `${Math.min(14, digits + 1)}ch`;
  }

  // Clamp a runs value into [1, max] (digits-only input tolerated).
  function clampRunsTo(raw, max) {
    const m = Math.max(1, Number(max) || 1);
    const n = Number.parseInt(parseQtyDigits(raw) || "0", 10);
    if (!Number.isFinite(n) || n < 1) return 1;
    return Math.min(n, m);
  }

  // per-unit price × runs for blueprints; just price otherwise
  function effectivePrice(item) {
    const runs = item.category === "blueprints" ? Math.max(1, Number(item.runs) || 1) : 1;
    return item.price * runs;
  }

  // ── Drawer open / close ──────────────────────────────────────────────────────

  function prewarmCheckout() {
    if (ShopAPI.isEndpointConfigured(orderEndpoint)) {
      fetch(orderEndpoint).catch(() => {});
    }
    ShopAPI.prewarmTurnstile();
  }

  function openCart() {
    if (!cartDrawer) return;
    cartDrawer.hidden  = false;
    if (cartBackdrop) cartBackdrop.hidden = false;
    // double-rAF so CSS transition fires after display change
    requestAnimationFrame(() => requestAnimationFrame(() => {
      cartDrawer.classList.add("cart-drawer--open");
      cartBackdrop?.classList.add("cart-backdrop--visible");
    }));
    cartToggleBtn?.setAttribute("aria-expanded", "true");
    prewarmCheckout();
  }

  function closeCart() {
    if (!cartDrawer) return;
    cartDrawer.classList.remove("cart-drawer--open");
    cartBackdrop?.classList.remove("cart-backdrop--visible");
    cartToggleBtn?.setAttribute("aria-expanded", "false");
    setTimeout(() => {
      cartDrawer.hidden = true;
      if (cartBackdrop) cartBackdrop.hidden = true;
    }, 300);
  }

  // ── Add-to-cart toast ───────────────────────────────────────────────────────
  const TOAST_HOLD_MS    = 1700;
  const TOAST_VANISH_MS  = 450;
  const activeToasts = new Map();

  function ensureToastContainer() {
    let container = document.getElementById("cart-toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "cart-toast-container";
      container.className = "cart-toast-container";
      container.setAttribute("aria-live", "polite");
      container.setAttribute("aria-atomic", "false");
      document.body.appendChild(container);
    }
    positionToastContainer(container);
    return container;
  }

  function positionToastContainer(container) {
    if (!container || !cartToggleBtn) return;
    const rect = cartToggleBtn.getBoundingClientRect();
    container.style.top   = `${Math.max(8, rect.bottom + 8)}px`;
    container.style.right = `${Math.max(8, window.innerWidth - rect.right - 2)}px`;
  }

  window.addEventListener("resize", () => {
    const c = document.getElementById("cart-toast-container");
    if (c) positionToastContainer(c);
  });

  function buildToastEl(product) {
    const el = document.createElement("div");
    el.className = "cart-toast";
    el.setAttribute("role", "status");

    const imgWrap = document.createElement("div");
    imgWrap.className = "cart-toast-img";
    if (product.img) {
      const img = document.createElement("img");
      img.src = product.img;
      img.alt = "";
      img.width = 56;
      img.height = 56;
      imgWrap.appendChild(img);
    }

    const info = document.createElement("div");
    info.className = "cart-toast-info";
    const nameEl = document.createElement("span");
    nameEl.className = "cart-toast-name";
    nameEl.textContent = product.name;
    const qtyEl = document.createElement("span");
    qtyEl.className = "cart-toast-qty";
    info.appendChild(nameEl);
    info.appendChild(qtyEl);

    const NS = "http://www.w3.org/2000/svg";
    const check = document.createElementNS(NS, "svg");
    check.setAttribute("class", "cart-toast-check");
    check.setAttribute("viewBox", "0 0 24 24");
    check.setAttribute("fill", "none");
    check.setAttribute("stroke", "currentColor");
    check.setAttribute("stroke-width", "2.6");
    check.setAttribute("stroke-linecap", "round");
    check.setAttribute("stroke-linejoin", "round");
    check.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", "M5 13l4 4L19 7");
    check.appendChild(path);

    el.appendChild(imgWrap);
    el.appendChild(info);
    el.appendChild(check);
    return { el, qtyEl };
  }

  function scheduleToastVanish(entry, key) {
    entry.vanishTimeout = setTimeout(() => {
      if (cartToggleBtn) {
        const fromRect = entry.el.getBoundingClientRect();
        const cartRect = cartToggleBtn.getBoundingClientRect();
        const dx = (cartRect.left + cartRect.width  / 2) - (fromRect.left + fromRect.width  / 2);
        const dy = (cartRect.top  + cartRect.height / 2) - (fromRect.top  + fromRect.height / 2);
        entry.el.style.setProperty("--toast-tx", `${dx}px`);
        entry.el.style.setProperty("--toast-ty", `${dy}px`);
      }
      entry.el.classList.remove("cart-toast--bump");
      entry.el.classList.add("cart-toast--vanishing");
      entry.removeTimeout = setTimeout(() => {
        entry.el.remove();
        if (activeToasts.get(key) === entry) activeToasts.delete(key);
      }, TOAST_VANISH_MS);
    }, TOAST_HOLD_MS);
  }

  function showAddToCartToast(product) {
    if (!product?.key) return;
    const container = ensureToastContainer();
    const totalQty  = cart[product.key]?.qty ?? 0;
    const qtyText   = `×${formatQty(totalQty)} in cart`;

    const existing = activeToasts.get(product.key);
    if (existing) {
      clearTimeout(existing.vanishTimeout);
      clearTimeout(existing.removeTimeout);
      const wasVanishing = existing.el.classList.contains("cart-toast--vanishing");
      existing.el.classList.remove("cart-toast--vanishing");
      existing.el.style.removeProperty("--toast-tx");
      existing.el.style.removeProperty("--toast-ty");
      existing.el.classList.add("cart-toast--visible");
      existing.qtyEl.textContent = qtyText;
      if (!wasVanishing) {
        existing.el.classList.remove("cart-toast--bump");
        void existing.el.offsetWidth;
        existing.el.classList.add("cart-toast--bump");
      }
      scheduleToastVanish(existing, product.key);
      return;
    }

    const built = buildToastEl(product);
    built.qtyEl.textContent = qtyText;
    container.appendChild(built.el);

    const entry = { el: built.el, qtyEl: built.qtyEl };
    activeToasts.set(product.key, entry);

    requestAnimationFrame(() => requestAnimationFrame(() => {
      built.el.classList.add("cart-toast--visible");
    }));

    scheduleToastVanish(entry, product.key);
  }

  // ── Cart mutations ───────────────────────────────────────────────────────────

  // opts (from configurator): runs (blueprints, default maxRuns), maxRuns (cap),
  // fitting ({name, price} extra for boats/structures)
  function addToCart(product, qtyToAdd = 1, opts = {}) {
    if (!product) return;
    const { key } = product;
    if (!cart[key]) {
      cart[key] = { ...product, qty: 0, extras: [] };
    }
    cart[key].price    = product.price;
    cart[key].category = product.category || cart[key].category;
    cart[key].img      = product.img      || cart[key].img;

    if (cart[key].category === "blueprints") {
      const max = Math.max(1, Number(opts.maxRuns ?? product.maxRuns ?? cart[key].maxRuns) || 1);
      let runs = Number(opts.runs);
      if (!Number.isFinite(runs) || runs < 1) runs = max;   // default to the cap
      cart[key].maxRuns = max;
      cart[key].runs = Math.min(Math.max(1, Math.floor(runs)), max);
    }

    const desired = cart[key].qty + clampQty(qtyToAdd);
    const next = clampQtyToStock(key, desired);
    cart[key].qty = next > 0 ? next : 0;
    if (cart[key].qty === 0) {
      delete cart[key];
      saveCart();
      renderCart();
      return;
    }

    // Selected fitting rides along as an extra (the cart drawer can adjust it).
    if (opts.fitting && opts.fitting.name) {
      if (!cart[key].extras) cart[key].extras = [];
      const existing = cart[key].extras.find((e) => e.name === opts.fitting.name);
      if (existing) {
        existing.qty += 1;
        if (Number.isFinite(opts.fitting.price)) existing.price = opts.fitting.price;
      } else {
        cart[key].extras.push({ name: opts.fitting.name, price: opts.fitting.price, qty: 1 });
      }
    }

    saveCart();
    renderCart();
  }

  function syncCartPricesFromProducts() {
    let changed = false;
    document.querySelectorAll(".item-card").forEach((card) => {
      const product = getProductData(card);
      if (!product || !cart[product.key]) return;
      const entry = cart[product.key];
      if (entry.price !== product.price) {
        entry.price      = product.price;
        entry.priceLabel = formatPrice(product.price);
        changed = true;
      }
      if (product.img && entry.img !== product.img) {
        entry.img = product.img;
        changed = true;
      }
      if (product.category && entry.category !== product.category) {
        entry.category = product.category;
        changed = true;
      }
    });
    if (changed) saveCart();
    renderCart();
  }

  function cardForKey(key) {
    return document.querySelector(`.item-card[data-name="${CSS.escape(key)}"]`);
  }

  // reads off the product card; caller resolves it once (cardForKey) per render
  function getPreorderInfo(card) {
    if (!card || !card.classList.contains("item-card--out-of-stock")) return null;
    const weeks = Number.parseInt(card.dataset.weeks || "", 10);
    return { weeks: Number.isFinite(weeks) && weeks > 0 ? weeks : null };
  }

  // Reads displayed stock from the product card (kept in sync by shop-filter).
  function getCardStock(card) {
    const raw  = card?.querySelector(".stock-state-count")?.dataset.stockRaw;
    const n    = Number.parseInt(raw || "", 10);
    return Number.isFinite(n) ? n : null;
  }

  function isMaterial(card) {
    return (card?.dataset.category || "").trim().toLowerCase() === "materials";
  }

  // materials can't exceed displayed stock; non-materials are unrestricted
  function clampQtyToStock(key, qty) {
    const card = cardForKey(key);
    if (!isMaterial(card)) return qty;
    const stock = getCardStock(card);
    if (stock === null) return qty;
    return Math.max(0, Math.min(qty, stock));
  }

  function changeQty(key, delta) {
    if (!cart[key]) return;
    const next = clampQtyToStock(key, cart[key].qty + delta);
    cart[key].qty = next;
    if (cart[key].qty <= 0) delete cart[key];
    saveCart();
    renderCart();
  }

  function setQty(key, qty) {
    if (!cart[key]) return;
    cart[key].qty = clampQtyToStock(key, clampQty(qty));
    if (cart[key].qty <= 0) delete cart[key];
    saveCart();
    renderCart();
  }

  // Runs-per-BPC adjustment (blueprints), clamped to the item's cap.
  function changeRuns(key, delta) {
    if (!cart[key]) return;
    const max = Math.max(1, Number(cart[key].maxRuns) || 1);
    cart[key].runs = Math.min(max, Math.max(1, (Number(cart[key].runs) || 1) + delta));
    saveCart();
    renderCart();
  }

  function setRuns(key, raw) {
    if (!cart[key]) return;
    cart[key].runs = clampRunsTo(raw, cart[key].maxRuns);
    saveCart();
    renderCart();
  }

  function removeItem(key) {
    delete cart[key];
    saveCart();
    renderCart();
  }

  function clearCart() {
    cart = {};
    saveCart();
    renderCart();
  }

  function addExtra(key, fitting) {
    if (!cart[key] || !fitting?.name) return;
    if (!cart[key].extras) cart[key].extras = [];
    const existing = cart[key].extras.find((e) => e.name === fitting.name);
    if (existing) {
      existing.qty += 1;
      if (Number.isFinite(fitting.price)) existing.price = fitting.price;
    } else {
      cart[key].extras.push({ name: fitting.name, price: fitting.price, qty: 1 });
    }
    saveCart();
    renderCart();
  }

  function changeExtraQty(key, idx, delta) {
    const ex = cart[key]?.extras?.[idx];
    if (!ex) return;
    ex.qty += delta;
    if (ex.qty <= 0) cart[key].extras.splice(idx, 1);
    saveCart();
    renderCart();
  }

  function setExtraQty(key, idx, qty) {
    const ex = cart[key]?.extras?.[idx];
    if (!ex) return;
    ex.qty = clampQty(qty);
    saveCart();
    renderCart();
  }

  function removeExtra(key, idx) {
    if (!cart[key]?.extras) return;
    cart[key].extras.splice(idx, 1);
    saveCart();
    renderCart();
  }

  // ── DOM helpers ──────────────────────────────────────────────────────────────

  const X_ICON_SVG = '<svg class="cart-x-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>';

  function makeBtn(text, dataMap, cls) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = cls;
    btn.textContent = text;
    Object.entries(dataMap).forEach(([k, v]) => { btn.dataset[k] = v; });
    return btn;
  }

  function makeXBtn(dataMap, cls) {
    const btn = makeBtn("", dataMap, cls);
    btn.innerHTML = X_ICON_SVG;
    return btn;
  }

  function makeQtyWrap(qty, size, minusData, plusData, inputData) {
    const wrap = document.createElement("div");
    wrap.className = `cart-qty-wrap${size === "sm" ? " cart-qty-wrap--sm" : ""}`;

    const minus = makeBtn("−", minusData, `cart-action-btn${size === "sm" ? " cart-action-btn--sm" : ""}`);
    const input = document.createElement("input");
    input.type = "text";
    input.inputMode = "numeric";
    input.className = `cart-item-qty${size === "sm" ? " cart-item-qty--sm" : ""}`;
    input.value = formatQty(qty);
    input.setAttribute("aria-label", "Quantity");
    Object.entries(inputData).forEach(([k, v]) => { input.dataset[k] = v; });
    const plus = makeBtn("+", plusData, `cart-action-btn${size === "sm" ? " cart-action-btn--sm" : ""}`);

    wrap.appendChild(minus);
    wrap.appendChild(input);
    wrap.appendChild(plus);
    return wrap;
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  function renderCart() {
    const items = Object.values(cart);
    let totalItems = 0;
    let totalValue = 0;
    for (const item of items) {
      totalItems += item.qty;
      totalValue += effectivePrice(item) * item.qty;
      item.extras?.forEach((ex) => {
        if (Number.isFinite(ex.price)) totalValue += ex.price * ex.qty;
      });
    }

    // badge + aria
    const badgeLabel = totalItems > 99 ? "99+" : formatQty(totalItems);
    if (cartCountEl) cartCountEl.textContent = badgeLabel;
    if (cartItemCountEl) cartItemCountEl.textContent = `${formatQty(totalItems)} item${totalItems !== 1 ? "s" : ""}`;
    cartToggleBtn?.setAttribute("aria-label", `Cart, ${formatQty(totalItems)} item${totalItems !== 1 ? "s" : ""}`);
    cartTotalEl.textContent = formatPriceLong(totalValue);
    if (cartTotalCompactEl) cartTotalCompactEl.textContent = formatPriceCompact(totalValue);
    cartItemsEl.innerHTML = "";

    if (items.length === 0) {
      const empty = document.createElement("li");
      empty.className = "cart-empty";
      empty.textContent = "Your cart is empty.";
      cartItemsEl.appendChild(empty);
      if (cartPreorderSummaryEl) cartPreorderSummaryEl.hidden = true;
      if (cartClearBtn) cartClearBtn.disabled = true;
      if (cartClearNameBtn) cartClearNameBtn.disabled = true;
      return;
    }

    items.sort((a, b) => a.name.localeCompare(b.name));

    // pre-order tiering: >2 pre-order items suppress per-item notices for one
    // consolidated box above the total (quotes the longest estimate).
    // Resolve each item's card once for the whole render (one DOM query/item).
    const cardByKey = new Map(items.map((item) => [item.key, cardForKey(item.key)]));

    const preorderInfoByKey = new Map();
    items.forEach((item) => {
      const info = getPreorderInfo(cardByKey.get(item.key));
      if (info) preorderInfoByKey.set(item.key, info);
    });
    const consolidatePreorders = preorderInfoByKey.size > 2;

    items.forEach((item) => {
      const itemFittings = fittingsFor(item.name);
      const supportsFittings = itemFittings.length > 0;   // boats + structures
      const isBlueprint = item.category === "blueprints";
      const li = document.createElement("li");
      li.className = `cart-item${supportsFittings ? " cart-item--boat" : ""}`;

      // ── Image ──
      const imgWrap = document.createElement("div");
      imgWrap.className = "cart-item-img";
      if (item.img) {
        const img = document.createElement("img");
        img.src = item.img;
        img.alt = item.name;
        img.width = 64;
        img.height = 64;
        imgWrap.appendChild(img);
      }

      // ── Content ──
      const content = document.createElement("div");
      content.className = "cart-item-content";

      // Header: name + remove
      const header = document.createElement("div");
      header.className = "cart-item-header";
      const nameEl = document.createElement("span");
      nameEl.className = "cart-item-name";
      nameEl.textContent = item.name;
      const removeBtn = makeXBtn({ cartAction: "remove", name: item.key }, "cart-x-btn");
      removeBtn.setAttribute("aria-label", `Remove ${item.name}`);
      header.appendChild(nameEl);
      header.appendChild(removeBtn);
      content.appendChild(header);

      // Controls stack
      const stack = document.createElement("div");
      stack.className = "cart-controls-stack";

      // Main price + qty row
      const mainRow = document.createElement("div");
      mainRow.className = "cart-controls-row";
      const priceEl = document.createElement("span");
      priceEl.className = "cart-item-price";
      // Blueprint price already folds in the runs multiplier (price per copy).
      const unitLabel = isBlueprint ? " / copy" : " / item";
      priceEl.innerHTML = `${formatPrice(effectivePrice(item))}<span class="cart-price-label">${unitLabel}</span>`;
      const qtyWrap = makeQtyWrap(
        item.qty,
        "lg",
        { cartAction: "decrease", name: item.key },
        { cartAction: "increase", name: item.key },
        { cartQtyInput: item.key }
      );
      mainRow.appendChild(priceEl);
      mainRow.appendChild(qtyWrap);
      stack.appendChild(mainRow);

      // Runs-per-BPC control (blueprints). Changing it rescales the price above.
      if (isBlueprint) {
        const runsRow = document.createElement("div");
        runsRow.className = "cart-controls-row cart-runs-row";
        const runsLabel = document.createElement("span");
        runsLabel.className = "cart-runs-label";
        runsLabel.textContent = "Runs / BPC";
        const runsWrap = makeQtyWrap(
          Math.max(1, Number(item.runs) || 1),
          "sm",
          { cartAction: "runs-decrease", name: item.key },
          { cartAction: "runs-increase", name: item.key },
          { cartRunsInput: item.key }
        );
        runsRow.appendChild(runsLabel);
        runsRow.appendChild(runsWrap);
        stack.appendChild(runsRow);
      }

      // Extras + fitting picker (boats + structures)
      if (supportsFittings) {
        if (item.extras?.length > 0) {
          const extrasWrap = document.createElement("div");
          extrasWrap.className = "cart-extras";

          item.extras.forEach((ex, j) => {
            const exRow = document.createElement("div");
            exRow.className = "cart-extra-row";

            const exInfo = document.createElement("div");
            exInfo.className = "cart-extra-info";
            const exName = document.createElement("span");
            exName.className = "cart-extra-name";
            exName.textContent = `+ ${ex.name}`;
            exInfo.appendChild(exName);
            if (Number.isFinite(ex.price)) {
              const exPrice = document.createElement("span");
              exPrice.className = "cart-extra-price";
              const exPriceValue = document.createElement("span");
              exPriceValue.className = "cart-extra-price-value";
              exPriceValue.textContent = formatPrice(ex.price);
              const exPriceLabel = document.createElement("span");
              exPriceLabel.className = "cart-extra-price-label";
              exPriceLabel.textContent = " / fitting";
              exPrice.appendChild(exPriceValue);
              exPrice.appendChild(exPriceLabel);
              exInfo.appendChild(exPrice);
            }

            const exControls = document.createElement("div");
            exControls.className = "cart-extra-controls";
            exControls.appendChild(makeBtn("−", { cartAction: "extra-decrease", name: item.key, extraIdx: j }, "cart-action-btn cart-action-btn--sm"));
            const exInput = document.createElement("input");
            exInput.type = "text";
            exInput.inputMode = "numeric";
            exInput.className = "cart-item-qty cart-item-qty--sm";
            exInput.value = formatQty(ex.qty);
            exInput.setAttribute("aria-label", `Quantity of ${ex.name}`);
            exInput.dataset.cartExtraQtyInput = item.key;
            exInput.dataset.extraIdx = j;
            exControls.appendChild(exInput);
            exControls.appendChild(makeBtn("+", { cartAction: "extra-increase", name: item.key, extraIdx: j }, "cart-action-btn cart-action-btn--sm"));
            exControls.appendChild(makeXBtn({ cartAction: "extra-remove", name: item.key, extraIdx: j }, "cart-x-btn cart-x-btn--sm"));

            exRow.appendChild(exInfo);
            exRow.appendChild(exControls);
            extrasWrap.appendChild(exRow);
          });

          stack.appendChild(extrasWrap);
        }

        // Fitting dropdown — picking an option adds it to the list
        const fitWrap = document.createElement("div");
        fitWrap.className = "cart-add-fit-wrap";

        const fitSelect = document.createElement("select");
        fitSelect.className = "cart-fitting-select";
        fitSelect.dataset.fittingSelect = item.key;
        fitSelect.setAttribute("aria-label", `Add fitting to ${item.name}`);

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "+ fitting";
        placeholder.selected = true;
        fitSelect.appendChild(placeholder);

        itemFittings.forEach((f) => {
          const opt = document.createElement("option");
          opt.value = f.name;
          opt.textContent = `${f.name} — ${formatPrice(f.price)} ISK`;
          fitSelect.appendChild(opt);
        });

        fitWrap.appendChild(fitSelect);
        stack.appendChild(fitWrap);
      }

      // Total row (all items)
      const totalRow = document.createElement("div");
      totalRow.className = "cart-item-total-row";
      const totalLabel = document.createElement("span");
      totalLabel.className = "cart-item-total-label";
      totalLabel.textContent = "Total";
      const totalVal = document.createElement("span");
      totalVal.className = "cart-item-total-value";
      let itemLineTotal = effectivePrice(item) * item.qty;
      item.extras?.forEach((ex) => {
        if (Number.isFinite(ex.price)) itemLineTotal += ex.price * ex.qty;
      });
      totalVal.textContent = formatPriceLong(itemLineTotal);
      totalRow.appendChild(totalLabel);
      totalRow.appendChild(totalVal);
      stack.appendChild(totalRow);

      const preorder = preorderInfoByKey.get(item.key) || null;
      const itemCard = cardByKey.get(item.key);
      const cardStock = getCardStock(itemCard);
      const overStock = cardStock !== null && item.qty > cardStock && cardStock > 0;
      if (preorder) {
        // Suppressed per-item when consolidating — see the box above the total.
        if (!consolidatePreorders) {
          const preorderRow = document.createElement("div");
          preorderRow.className = "cart-warning cart-warning--preorder";
          const preorderIcon = document.createElement("span");
          preorderIcon.className = "cart-warning-icon";
          preorderIcon.setAttribute("aria-hidden", "true");
          preorderIcon.textContent = "!";
          const preorderText = document.createElement("p");
          const preorderLead = document.createElement("strong");
          preorderLead.textContent = "Pre-order!";
          preorderText.appendChild(preorderLead);
          preorderText.appendChild(document.createTextNode(
            preorder.weeks
              ? ` Estimated delivery: ${preorder.weeks} week${preorder.weeks !== 1 ? "s" : ""}.`
              : " Delivery estimate unavailable. We'll get started on it!"
          ));
          preorderRow.appendChild(preorderIcon);
          preorderRow.appendChild(preorderText);
          stack.appendChild(preorderRow);
        }
      } else if (overStock) {
        const warnRow = document.createElement("div");
        warnRow.className = "cart-warning cart-warning--preorder";
        const icon = document.createElement("span");
        icon.className = "cart-warning-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = "!";
        const text = document.createElement("p");
        const lead = document.createElement("strong");
        if (isMaterial(itemCard)) {
          lead.textContent = `Only ${formatQty(cardStock)} available.`;
          text.appendChild(lead);
          text.appendChild(document.createTextNode(" Preorder not available for this item."));
        } else {
          lead.textContent = `${formatQty(cardStock)} available.`;
          text.appendChild(lead);
          text.appendChild(document.createTextNode(` Remaining ${formatQty(item.qty - cardStock)} might take longer.`));
        }
        warnRow.appendChild(icon);
        warnRow.appendChild(text);
        stack.appendChild(warnRow);
      }

      content.appendChild(stack);
      li.appendChild(imgWrap);
      li.appendChild(content);
      cartItemsEl.appendChild(li);
    });

    cartItemsEl.querySelectorAll(".cart-item-qty").forEach(resizeQtyInput);

    // consolidated pre-order box (above total); quotes the longest estimate
    if (cartPreorderSummaryEl) {
      if (consolidatePreorders) {
        const weeks = [...preorderInfoByKey.values()]
          .map((info) => info.weeks)
          .filter((w) => Number.isFinite(w) && w > 0);
        const maxWeeks = weeks.length ? Math.max(...weeks) : null;
        if (cartPreorderSummaryTextEl) {
          cartPreorderSummaryTextEl.textContent = "";
          const lead = document.createElement("strong");
          lead.textContent = "Multiple Pre-Orders in cart!";
          cartPreorderSummaryTextEl.appendChild(lead);
          cartPreorderSummaryTextEl.appendChild(document.createTextNode(
            maxWeeks
              ? ` Expected delivery around ${maxWeeks} week${maxWeeks !== 1 ? "s" : ""}.`
              : " Delivery estimate unavailable. We'll get started on it!"
          ));
        }
        cartPreorderSummaryEl.hidden = false;
      } else {
        cartPreorderSummaryEl.hidden = true;
      }
    }

    if (cartClearBtn) cartClearBtn.disabled = false;
    if (cartClearNameBtn) cartClearNameBtn.disabled = false;
  }

  // ── Event delegation ─────────────────────────────────────────────────────────

  cartToggleBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    cartDrawer?.hidden !== false ? openCart() : closeCart();
  });

  cartDrawerClose?.addEventListener("click", closeCart);
  cartBackdrop?.addEventListener("click", closeCart);

  // ── Card-flip configurator (store/home) ──────────────────────────────────────
  // `flip` cards carry a back face (qty/fitting/runs); Config flips to it (→ Close),
  // the shared ADD button adds with chosen options when flipped, defaults when not.

  function openFlip(card) {
    if (!card) return;
    // One open configurator at a time.
    document.querySelectorAll(".item-card.is-flipped").forEach((c) => { if (c !== card) flipCardBack(c); });
    card.querySelector(".item-card-face--front")?.setAttribute("aria-hidden", "true");
    card.querySelector(".item-card-face--back")?.setAttribute("aria-hidden", "false");
    const toggle = card.querySelector("[data-flip-toggle]");
    if (toggle) toggle.textContent = "Close";
    card.classList.add("is-flipped");
    (card.querySelector(".item-card-face--back select, .item-card-face--back input") || toggle)?.focus();
  }

  function flipCardBack(card) {
    if (!card || !card.classList.contains("is-flipped")) return;
    card.classList.remove("is-flipped");
    card.querySelector(".item-card-face--front")?.setAttribute("aria-hidden", "false");
    card.querySelector(".item-card-face--back")?.setAttribute("aria-hidden", "true");
    const toggle = card.querySelector("[data-flip-toggle]");
    if (toggle) toggle.textContent = "Config";
    resetFlipControls(card);
  }

  function resetFlipControls(card) {
    const qty = card.querySelector("[data-flip-qty-input]");
    if (qty) qty.value = "1";
    const runs = card.querySelector("[data-flip-runs-input]");
    if (runs) runs.value = card.dataset.maxRuns || runs.dataset.flipMax || "1";
    const fit = card.querySelector("[data-flip-fitting]");
    if (fit) { fit.value = ""; updateFlipFitPrice(fit); }
  }

  function readFlipControls(card) {
    const qtyInput = card.querySelector("[data-flip-qty-input]");
    const qty = qtyInput ? clampQty(qtyInput.value) : 1;

    let runs = null, maxRuns = null;
    if ((card.dataset.category || "") === "blueprints") {
      maxRuns = Math.max(1, Number.parseInt(card.dataset.maxRuns || "1", 10) || 1);
      const runsInput = card.querySelector("[data-flip-runs-input]");
      runs = runsInput ? clampRunsTo(runsInput.value, maxRuns) : maxRuns;
    }

    let fitting = null;
    const fitSelect = card.querySelector("[data-flip-fitting]");
    if (fitSelect && fitSelect.value) {
      const opt = fitSelect.selectedOptions[0];
      const price = Number(opt?.dataset.price);
      fitting = { name: fitSelect.value, price: Number.isFinite(price) ? price : 0 };
    }
    return { qty, runs, maxRuns, fitting };
  }

  function stepFlipInput(btn) {
    const card = btn.closest(".item-card");
    if (!card) return;
    const dir = Number(btn.dataset.flipDir) || 0;
    if (btn.dataset.flipTarget === "runs") {
      const input = card.querySelector("[data-flip-runs-input]");
      if (!input) return;
      const max = Math.max(1, Number.parseInt(card.dataset.maxRuns || "1", 10) || 1);
      input.value = String(Math.min(max, Math.max(1, clampRunsTo(input.value, max) + dir)));
    } else {
      const input = card.querySelector("[data-flip-qty-input]");
      if (!input) return;
      input.value = formatQty(Math.max(1, clampQty(input.value) + dir));
    }
  }

  function updateFlipFitPrice(select) {
    const priceEl = select.closest(".flip-field")?.querySelector("[data-flip-fit-price]");
    if (!priceEl) return;
    const price = Number(select.selectedOptions[0]?.dataset.price) || 0;
    priceEl.textContent = price > 0 ? `+${formatPrice(price)} ISK` : "+0 ISK";
  }

  document.addEventListener("click", (e) => {
    // Shared ADD: add with configurator values (defaults on front face, picks when
    // flipped), reset fields but leave the face as-is (closed via Config/click-out/Esc).
    // readFlipControls defaults for cards without a back face.
    const addBtn = e.target.closest("[data-cart-add]");
    if (addBtn) {
      const card = addBtn.closest(".item-card");
      const product = getProductData(card);
      if (product) {
        const sel = readFlipControls(card);
        addToCart(product, sel.qty, { runs: sel.runs, maxRuns: sel.maxRuns, fitting: sel.fitting });
        showAddToCartToast(product);
      }
      resetFlipControls(card);
      return;
    }

    // Config / Close: toggle the configurator open or shut.
    const flipToggle = e.target.closest("[data-flip-toggle]");
    if (flipToggle) {
      const card = flipToggle.closest(".item-card");
      if (card?.classList.contains("is-flipped")) flipCardBack(card);
      else openFlip(card);
      return;
    }

    // +/- steppers inside the configurator (qty / runs).
    const flipStepBtn = e.target.closest("[data-flip-step]");
    if (flipStepBtn) { stepFlipInput(flipStepBtn); return; }

    // Cart drawer action buttons.
    const actionBtn = e.target.closest("[data-cart-action]");
    if (actionBtn) {
      const action = actionBtn.dataset.cartAction;
      const key    = String(actionBtn.dataset.name || "").trim();

      if (action === "decrease"       && key) changeQty(key, -1);
      if (action === "increase"       && key) changeQty(key,  1);
      if (action === "remove"         && key) removeItem(key);

      if (action === "runs-decrease"  && key) changeRuns(key, -1);
      if (action === "runs-increase"  && key) changeRuns(key,  1);

      if (action === "extra-decrease" && key) changeExtraQty(key, Number(actionBtn.dataset.extraIdx), -1);
      if (action === "extra-increase" && key) changeExtraQty(key, Number(actionBtn.dataset.extraIdx),  1);
      if (action === "extra-remove"   && key) removeExtra(key, Number(actionBtn.dataset.extraIdx));
      return;
    }

    // A click anywhere outside an open configurator returns it to the front.
    document.querySelectorAll(".item-card.is-flipped").forEach((card) => {
      if (!card.contains(e.target)) flipCardBack(card);
    });
  });

  // Escape returns any open configurator to its front.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".item-card.is-flipped").forEach((card) => flipCardBack(card));
  });

  document.addEventListener("input", (e) => {
    const t = e.target;
    if (t.dataset.cartQtyInput !== undefined || t.dataset.cartExtraQtyInput !== undefined) {
      const digits = parseQtyDigits(t.value).slice(0, 9);
      t.value = digits ? formatQty(Number.parseInt(digits, 10)) : "";
      resizeQtyInput(t);
      return;
    }
    if (t.dataset.cartRunsInput !== undefined) {
      t.value = parseQtyDigits(t.value).slice(0, 4);
      resizeQtyInput(t);
      return;
    }
    if (t.hasAttribute("data-flip-qty-input")) {
      const digits = parseQtyDigits(t.value).slice(0, 9);
      t.value = digits ? formatQty(Number.parseInt(digits, 10)) : "";
      return;
    }
    if (t.hasAttribute("data-flip-runs-input")) {
      t.value = parseQtyDigits(t.value).slice(0, 4);
    }
  });

  document.addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.cartQtyInput !== undefined) {
      setQty(t.dataset.cartQtyInput, t.value);
      return;
    }
    if (t.dataset.cartExtraQtyInput !== undefined) {
      setExtraQty(t.dataset.cartExtraQtyInput, Number(t.dataset.extraIdx), t.value);
      return;
    }
    if (t.dataset.cartRunsInput !== undefined) {
      setRuns(t.dataset.cartRunsInput, t.value);
      return;
    }
    if (t.hasAttribute("data-flip-qty-input")) {
      t.value = formatQty(clampQty(t.value));
      return;
    }
    if (t.hasAttribute("data-flip-runs-input")) {
      const card = t.closest(".item-card");
      const max = Math.max(1, Number.parseInt(card?.dataset.maxRuns || "1", 10) || 1);
      t.value = String(clampRunsTo(t.value, max));
      return;
    }
    if (t.hasAttribute("data-flip-fitting")) {
      updateFlipFitPrice(t);
      return;
    }
    if (t.dataset.fittingSelect) {
      const key = t.dataset.fittingSelect;
      const fittingName = t.value;
      t.value = "";
      if (!fittingName) return;
      const fitting = fittingByName(fittingName);
      if (fitting) addExtra(key, fitting);
    }
  });

  // ── Identity tabs ─────────────────────────────────────────────────────────────

  function activeIdentityTab() {
    return document.querySelector(".cart-identity-tab--active")?.dataset.tab || "name";
  }

  function syncCheckoutButtonLabel() {
    if (cartCheckoutNameBtn) cartCheckoutNameBtn.textContent = "Place Order";
  }

  function resetOrderIdPanel() {
    if (orderIdGeneratedEl) {
      orderIdGeneratedEl.textContent = "";
      orderIdGeneratedEl.hidden = true;
    }
    if (orderIdCopyBtn) {
      orderIdCopyBtn.hidden = true;
      orderIdCopyBtn.classList.remove("cart-orderid-copy--copied");
    }
    if (orderIdErrorEl) {
      orderIdErrorEl.textContent = "";
      orderIdErrorEl.hidden = true;
    }
    if (nameErrorEl) {
      nameErrorEl.textContent = "";
      nameErrorEl.hidden = true;
    }
  }

  document.querySelectorAll(".cart-identity-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".cart-identity-tab").forEach(t => t.classList.remove("cart-identity-tab--active"));
      tab.classList.add("cart-identity-tab--active");
      const target = tab.dataset.tab;
      document.querySelectorAll(".cart-identity-panel").forEach(p => { p.hidden = p.dataset.panel !== target; });
      resetOrderIdPanel();
      syncCheckoutButtonLabel();
    });
  });

  syncCheckoutButtonLabel();

  if (orderIdCopyBtn) {
    orderIdCopyBtn.addEventListener("click", async () => {
      const value = orderIdGeneratedEl?.textContent?.trim();
      if (!value) return;
      try {
        await navigator.clipboard.writeText(value);
        orderIdCopyBtn.classList.add("cart-orderid-copy--copied");
        setTimeout(() => orderIdCopyBtn.classList.remove("cart-orderid-copy--copied"), 1400);
      } catch (err) {
        console.error("Order ID copy failed", err);
      }
    });
  }

  // ── Checkout ──────────────────────────────────────────────────────────────────

  function buildOrderItems() {
    return Object.values(cart).map((item) => ({
      name: item.name,
      category: item.category || "",
      qty: item.qty,
      price: item.price,   // per-copy base; runs multiplier applied server-side
      ...(item.category === "blueprints" ? { runs: Math.max(1, Number(item.runs) || 1) } : {}),
      extras: (item.extras || []).map((ex) => ({
        name: ex.name,
        price: Number.isFinite(ex.price) ? ex.price : 0,
        qty: ex.qty
      }))
    }));
  }

  // post-submit: drop displayed card stock by acceptedQty for instant feedback,
  // then a silent background refresh reconciles with the sheet's value
  function applyOrderSideEffects(response, submittedItems) {
    const adjustedByName = new Map((response?.adjusted || []).map(a => [normalizeName(a.name), a]));
    for (const item of submittedItems) {
      const key = normalizeName(item.name);
      const adj = adjustedByName.get(key);
      const acceptedQty = adj && typeof adj.acceptedQty === "number" ? adj.acceptedQty : item.qty;
      if (acceptedQty <= 0) continue;
      const card = document.querySelector(`.item-card[data-name="${CSS.escape(key)}"]`);
      const stockEl = card?.querySelector(".stock-state-count");
      if (!stockEl) continue;
      const current = Number.parseInt(stockEl.dataset.stockRaw || "0", 10);
      const next = Math.max(0, (Number.isFinite(current) ? current : 0) - acceptedQty);
      stockEl.dataset.stockRaw = String(next);
      stockEl.textContent = formatQty(next);
      if (next <= 0) card?.classList.add("item-card--out-of-stock");
    }
    // Silent re-fetch ~2s later (gives the sheet time to flush + reservations to settle).
    setTimeout(() => {
      if (!ShopAPI.refreshNow) return;
      ShopAPI.refreshNow(orderEndpoint).then((map) => {
        if (map && map.size > 0) {
          document.dispatchEvent(new CustomEvent("shop:stock-refresh", { detail: { stockMap: map } }));
        }
      }).catch(() => {});
    }, 2000);
  }

  function showOrderIdError(message) {
    if (!orderIdErrorEl) return;
    orderIdErrorEl.textContent = message;
    orderIdErrorEl.hidden = false;
  }

  function showGeneratedOrderId(orderId) {
    if (orderIdGeneratedEl) {
      orderIdGeneratedEl.textContent = orderId;
      orderIdGeneratedEl.hidden = false;
    }
    if (orderIdCopyBtn) {
      orderIdCopyBtn.hidden = false;
      orderIdCopyBtn.classList.remove("cart-orderid-copy--copied");
    }
    if (orderIdErrorEl) {
      orderIdErrorEl.textContent = "";
      orderIdErrorEl.hidden = true;
    }
  }

  async function handleOrderIdCheckout() {
    if (!cartCheckoutBtn) return;
    if (orderIdErrorEl) {
      orderIdErrorEl.textContent = "";
      orderIdErrorEl.hidden = true;
    }

    const items = buildOrderItems();
    if (!items.length) {
      showOrderIdError("Cart is empty, please add items");
      return;
    }

    const isDevHost = isLocalHost();

    const orderId = generateOrderId();

    cartCheckoutBtn.disabled = true;
    cartCheckoutBtn.textContent = "Verifying…";

    try {
      if (isDevHost) {
        console.info("[dev] Skipping Turnstile + server submit. Order ID:", orderId);
      } else {
        let turnstileToken;
        try {
          turnstileToken = await ShopAPI.getTurnstileToken();
        } catch (verifyErr) {
          console.error("Turnstile verification failed.", verifyErr);
          showOrderIdError("Verification failed. Please try again.");
          cartCheckoutBtn.textContent = "Place Order";
          return;
        }
        cartCheckoutBtn.textContent = "Sending…";
        const response = await ShopAPI.submitOrder(orderEndpoint, { orderId, items, turnstileToken });
        applyOrderSideEffects(response, items);
      }
      showGeneratedOrderId(orderId);
      cartCheckoutBtn.textContent = "Place Order";
    } catch (error) {
      console.error("Order submission failed.", error);
      showOrderIdError("Couldn't reach the order server. Please retry.");
      cartCheckoutBtn.textContent = "Retry";
    } finally {
      cartCheckoutBtn.disabled = false;
    }
  }

  async function handleNameCheckout() {
    if (!cartCheckoutNameBtn) return;
    if (nameErrorEl) {
      nameErrorEl.textContent = "";
      nameErrorEl.hidden = true;
    }

    const items = buildOrderItems();
    if (!items.length) {
      if (nameErrorEl) {
        nameErrorEl.textContent = "Cart is empty, please add items";
        nameErrorEl.hidden = false;
      }
      return;
    }

    const charNameInput = document.getElementById("cart-char-name");
    const charName = charNameInput?.value.trim() || "";
    if (!charName) {
      if (nameErrorEl) {
        nameErrorEl.textContent = "Please type your character name";
        nameErrorEl.hidden = false;
      }
      charNameInput?.focus();
      return;
    }

    const isDevHost = isLocalHost();

    cartCheckoutNameBtn.disabled = true;
    cartCheckoutNameBtn.textContent = "Verifying…";

    try {
      if (isDevHost) {
        console.info("[dev] Skipping Turnstile + server submit. Name order:", charName);
      } else {
        let turnstileToken;
        try {
          turnstileToken = await ShopAPI.getTurnstileToken();
        } catch (verifyErr) {
          console.error("Turnstile verification failed.", verifyErr);
          if (nameErrorEl) {
            nameErrorEl.textContent = "Verification failed. Please try again.";
            nameErrorEl.hidden = false;
          }
          syncCheckoutButtonLabel();
          return;
        }
        cartCheckoutNameBtn.textContent = "Sending…";
        const response = await ShopAPI.submitOrder(orderEndpoint, { charName, items, turnstileToken });
        applyOrderSideEffects(response, items);
      }
      cartCheckoutNameBtn.textContent = "Placed!";
      setTimeout(syncCheckoutButtonLabel, 2200);
    } catch (error) {
      console.error("Order submission failed.", error);
      if (nameErrorEl) {
        nameErrorEl.textContent = "Couldn't reach the order server. Please retry.";
        nameErrorEl.hidden = false;
      }
      cartCheckoutNameBtn.textContent = "Retry";
    } finally {
      cartCheckoutNameBtn.disabled = false;
    }
  }

  cartCheckoutBtn?.addEventListener("click", handleOrderIdCheckout);
  cartCheckoutNameBtn?.addEventListener("click", handleNameCheckout);

  // ── Clear ─────────────────────────────────────────────────────────────────────

  cartClearBtn?.addEventListener("click", clearCart);
  cartClearNameBtn?.addEventListener("click", clearCart);
  document.addEventListener("shop:product-data-updated", syncCartPricesFromProducts);

  // ── Incoming add intent (?add=<item key>) ──────────────────────────────────────
  // <page>/?add=<key> adds that item + opens the drawer (cross-page "add" links);
  // needs a matching card. Skips the toast (the drawer is feedback enough).
  function handleIncomingAdd() {
    const params = new URLSearchParams(location.search);
    const addKey = normalizeName(params.get("add") || "");
    if (!addKey) return;

    // Strip the param so a refresh doesn't re-add the item.
    params.delete("add");
    const query = params.toString();
    history.replaceState(null, "", location.pathname + (query ? `?${query}` : "") + location.hash);

    const card = cardForKey(addKey);
    if (!card) return;
    const product = getProductData(card);
    if (!product) return;

    addToCart(product, 1);
    openCart();
  }

  // ── Init ──────────────────────────────────────────────────────────────────────

  syncCartPricesFromProducts();
  renderCart();
  handleIncomingAdd();
});
