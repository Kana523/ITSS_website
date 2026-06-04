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
  const CART_STORAGE_KEY = "itss_shop_cart_v2";
  const ORDER_ID_LENGTH = 20;

  // Composite cart key — each (item, fitting) pair is its own line. No fitting →
  // bare base key. baseKey = the item's card data-name (one card backs many).
  function variantKey(baseKey, fitting) {
    const fk = fitting && fitting.name ? normalizeName(fitting.name) : "";
    return fk ? `${baseKey}::${fk}` : baseKey;
  }

  // Resolve a fitting name to {name, price} from the catalog (authoritative
  // price), falling back to a supplied price. Empty → null (no fitting).
  function resolveFitting(name, fallbackPrice) {
    if (!name) return null;
    const f = fittingByName(name);
    if (f) return { name: f.name, price: f.price };
    const p = Number(fallbackPrice);
    return { name: String(name).trim(), price: Number.isFinite(p) ? p : 0 };
  }
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
      Object.values(parsed).forEach((item) => {
        if (!item || typeof item !== "object") return;
        const safeName  = String(item.name || "").trim();
        const baseKey   = normalizeName(safeName);
        const safeQty   = Number(item.qty);
        const safePrice = parsePriceToIsk(item.price);
        if (!baseKey || !safeName || !Number.isFinite(safeQty) || safeQty < 1) return;

        const category = String(item.category || "").trim();
        const fitting  = item.fitting
          ? resolveFitting(item.fitting.name, item.fitting.price)
          : null;
        const key = variantKey(baseKey, fitting);

        normalized[key] = {
          key,
          baseKey,
          name:       safeName,
          qty:        Math.floor(safeQty),
          price:      Number.isFinite(safePrice) ? safePrice : 0,
          priceLabel: formatPrice(Number.isFinite(safePrice) ? safePrice : 0),
          category,
          img:        String(item.img || "").trim(),
          fitting,
        };
      });
      // Migrated to the v2 key scheme — drop any legacy v1 cart.
      try { localStorage.removeItem("itss_shop_cart_v1"); } catch {}
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
    return { key, name, price, category, img };
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
    nameEl.textContent = product.fitting?.name ? `${product.name} · ${product.fitting.name}` : product.name;
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

  // opts.fitting: {name, price}|null (boats/structures). Each (item, fitting)
  // pair is its own line. Returns the cart entry, or null if it netted to zero.
  function addToCart(product, qtyToAdd = 1, opts = {}) {
    if (!product) return null;
    const fitting = opts.fitting && opts.fitting.name
      ? resolveFitting(opts.fitting.name, opts.fitting.price)
      : null;
    const key = variantKey(product.key, fitting);

    if (!cart[key]) {
      cart[key] = {
        key,
        baseKey:  product.key,
        name:     product.name,
        qty:      0,
        price:    product.price,
        category: product.category || "",
        img:      product.img || "",
        fitting,
      };
    }
    const entry = cart[key];
    entry.price    = product.price;
    entry.category = product.category || entry.category;
    entry.img      = product.img      || entry.img;

    const desired = entry.qty + clampQty(qtyToAdd);
    const next = clampQtyToStock(product.key, desired);
    entry.qty = next > 0 ? next : 0;
    if (entry.qty === 0) {
      delete cart[key];
      saveCart();
      renderCart();
      return null;
    }

    saveCart();
    renderCart();
    return entry;
  }

  function syncCartPricesFromProducts() {
    let changed = false;
    document.querySelectorAll(".item-card").forEach((card) => {
      const product = getProductData(card);
      if (!product) return;
      // One card backs every fitting variant of the boat — update them all.
      Object.values(cart).forEach((entry) => {
        if (entry.baseKey !== product.key) return;
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
  function clampQtyToStock(baseKey, qty) {
    const card = cardForKey(baseKey);
    if (!isMaterial(card)) return qty;
    const stock = getCardStock(card);
    if (stock === null) return qty;
    return Math.max(0, Math.min(qty, stock));
  }

  function changeQty(key, delta) {
    if (!cart[key]) return;
    const next = clampQtyToStock(cart[key].baseKey, cart[key].qty + delta);
    cart[key].qty = next;
    if (cart[key].qty <= 0) delete cart[key];
    saveCart();
    renderCart();
  }

  function setQty(key, qty) {
    if (!cart[key]) return;
    cart[key].qty = clampQtyToStock(cart[key].baseKey, clampQty(qty));
    if (cart[key].qty <= 0) delete cart[key];
    saveCart();
    renderCart();
  }

  // Coarse +/- step for materials (±100k / ±1m). Never removes — clamps to
  // [1, stock]; the X button removes.
  function stepQtyBig(key, delta) {
    if (!cart[key]) return;
    const next = clampQtyToStock(cart[key].baseKey, Math.max(1, cart[key].qty + delta));
    cart[key].qty = Math.max(1, next);
    saveCart();
    renderCart();
  }

  // Switch a line's fitting in place (boats/structures). "" → no fitting. Re-keys
  // the line; merges into the target variant if it already exists.
  function changeLineFitting(key, fittingName) {
    const entry = cart[key];
    if (!entry) return;
    const fitting = fittingName ? resolveFitting(fittingName) : null;
    const newKey = variantKey(entry.baseKey, fitting);
    if (newKey === key) return;
    if (cart[newKey]) {
      cart[newKey].qty += entry.qty;
      delete cart[key];
    } else {
      entry.key = newKey;
      entry.fitting = fitting;
      cart[newKey] = entry;
      delete cart[key];
    }
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

  function makeQtyWrap(qty, minusData, plusData, inputData) {
    const wrap = document.createElement("div");
    wrap.className = "cart-qty-wrap";

    const minus = makeBtn("−", minusData, "cart-action-btn");
    const input = document.createElement("input");
    input.type = "text";
    input.inputMode = "numeric";
    input.className = "cart-item-qty";
    input.value = formatQty(qty);
    input.setAttribute("aria-label", "Quantity");
    Object.entries(inputData).forEach(([k, v]) => { input.dataset[k] = v; });
    const plus = makeBtn("+", plusData, "cart-action-btn");

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
      const unit = item.price + (item.fitting ? (Number(item.fitting.price) || 0) : 0);
      totalValue += unit * item.qty;
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

    // Variants of the same boat sort together (bare hull first).
    items.sort((a, b) =>
      a.name.localeCompare(b.name) ||
      (a.fitting?.name || "").localeCompare(b.fitting?.name || ""));

    // One card backs many variant lines. Resolve each boat's card + aggregate
    // qty once (keyed by baseKey) for stock / pre-order math.
    const cardByBase = new Map();
    const qtyByBase  = new Map();
    items.forEach((item) => {
      if (!cardByBase.has(item.baseKey)) cardByBase.set(item.baseKey, cardForKey(item.baseKey));
      qtyByBase.set(item.baseKey, (qtyByBase.get(item.baseKey) || 0) + item.qty);
    });

    // pre-order tiering: >2 pre-order boats suppress per-item notices for one
    // consolidated box above the total (quotes the longest estimate).
    const preorderInfoByBase = new Map();
    cardByBase.forEach((card, baseKey) => {
      const info = getPreorderInfo(card);
      if (info) preorderInfoByBase.set(baseKey, info);
    });
    const consolidatePreorders = preorderInfoByBase.size > 2;
    const warnedBases = new Set();   // show pre-order / over-stock once per boat

    items.forEach((item) => {
      const itemFittings = fittingsFor(item.name);
      const supportsFittings = itemFittings.length > 0;   // boats + structures
      const isBlueprint = item.category === "blueprints";
      const isMat = item.category === "materials";
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

      // Main price + qty row. Blueprint qty == total runs; materials move their
      // qty to a dedicated big-step row below.
      const mainRow = document.createElement("div");
      mainRow.className = "cart-controls-row";
      const priceEl = document.createElement("span");
      priceEl.className = "cart-item-price";
      const unitLabel = isBlueprint ? " / run" : " / item";
      priceEl.innerHTML = `${formatPrice(item.price)}<span class="cart-price-label">${unitLabel}</span>`;
      mainRow.appendChild(priceEl);

      const qtyWrap = makeQtyWrap(
        item.qty,
        { cartAction: "decrease", name: item.key },
        { cartAction: "increase", name: item.key },
        { cartQtyInput: item.key }
      );

      if (isBlueprint) {
        const runsGroup = document.createElement("div");
        runsGroup.className = "cart-qty-group";
        const runsLabel = document.createElement("span");
        runsLabel.className = "cart-runs-label";
        runsLabel.textContent = "Total runs";
        runsGroup.appendChild(runsLabel);
        runsGroup.appendChild(qtyWrap);
        mainRow.appendChild(runsGroup);
      } else if (!isMat) {
        mainRow.appendChild(qtyWrap);
      }
      stack.appendChild(mainRow);

      // Materials: qty on its own row, flanked by ±100k / ±1m coarse steps.
      if (isMat) {
        const bigRow = document.createElement("div");
        bigRow.className = "cart-bigstep-row";
        bigRow.appendChild(makeBtn("-1m",   { cartAction: "bigstep", name: item.key, delta: "-1000000" }, "cart-bigstep-btn"));
        bigRow.appendChild(makeBtn("-100k", { cartAction: "bigstep", name: item.key, delta: "-100000" },  "cart-bigstep-btn"));
        bigRow.appendChild(qtyWrap);
        bigRow.appendChild(makeBtn("+100k", { cartAction: "bigstep", name: item.key, delta: "100000" },   "cart-bigstep-btn"));
        bigRow.appendChild(makeBtn("+1m",   { cartAction: "bigstep", name: item.key, delta: "1000000" },  "cart-bigstep-btn"));
        stack.appendChild(bigRow);
      }

      // Fitting dropdown (boats + structures) — switches the line's fitting in
      // place (re-keys / merges). Always offers "No Fitting".
      if (supportsFittings) {
        const fitRow = document.createElement("div");
        fitRow.className = "cart-fitting-row";

        const fitSelect = document.createElement("select");
        fitSelect.className = "cart-fitting-select";
        fitSelect.dataset.lineFitting = item.key;
        fitSelect.setAttribute("aria-label", `Fitting for ${item.name}`);

        const none = document.createElement("option");
        none.value = "";
        none.textContent = "No Fitting";
        if (!item.fitting) none.selected = true;
        fitSelect.appendChild(none);

        itemFittings.forEach((f) => {
          const opt = document.createElement("option");
          opt.value = f.name;
          opt.textContent = f.name;
          if (item.fitting && normalizeName(item.fitting.name) === normalizeName(f.name)) opt.selected = true;
          fitSelect.appendChild(opt);
        });

        const fitPrice = document.createElement("span");
        fitPrice.className = "cart-fitting-price";
        fitPrice.textContent = item.fitting ? `+${formatPrice(item.fitting.price)} / fitting` : "+0";

        fitRow.appendChild(fitSelect);
        fitRow.appendChild(fitPrice);
        stack.appendChild(fitRow);
      }

      // Total row (all items)
      const totalRow = document.createElement("div");
      totalRow.className = "cart-item-total-row";
      const totalLabel = document.createElement("span");
      totalLabel.className = "cart-item-total-label";
      totalLabel.textContent = "Total";
      const totalVal = document.createElement("span");
      totalVal.className = "cart-item-total-value";
      const unitCombined = item.price + (item.fitting ? (Number(item.fitting.price) || 0) : 0);
      totalVal.textContent = formatPriceLong(unitCombined * item.qty);
      totalRow.appendChild(totalLabel);
      totalRow.appendChild(totalVal);
      stack.appendChild(totalRow);

      // Pre-order / over-stock are properties of the boat (its card + aggregate
      // qty across fittings), so compute once and show on the first variant line.
      const itemCard  = cardByBase.get(item.baseKey);
      const baseQty   = qtyByBase.get(item.baseKey) || item.qty;
      const preorder  = preorderInfoByBase.get(item.baseKey) || null;
      const cardStock = getCardStock(itemCard);
      const overStock = cardStock !== null && baseQty > cardStock && cardStock > 0;
      if (!warnedBases.has(item.baseKey)) {
        if (preorder) {
          // Suppressed per-item when consolidating — see the box above the total.
          if (!consolidatePreorders) {
            warnedBases.add(item.baseKey);
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
          warnedBases.add(item.baseKey);
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
            text.appendChild(document.createTextNode(` Remaining ${formatQty(baseQty - cardStock)} might take longer.`));
          }
          warnRow.appendChild(icon);
          warnRow.appendChild(text);
          stack.appendChild(warnRow);
        }
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
        const weeks = [...preorderInfoByBase.values()]
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
  // `flip` cards carry a back face (qty/fitting/runs); Options flips to it (→ Close),
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
    if (toggle) toggle.textContent = "Options";
    resetFlipControls(card);
  }

  function resetFlipControls(card) {
    if (!card) return;
    const qty = card.querySelector("[data-flip-qty-input]");
    if (qty) qty.value = "1";
    const fit = card.querySelector("[data-flip-fitting]");
    if (fit) { fit.value = ""; updateFlipFitPrice(fit); }
  }

  function readFlipControls(card) {
    const qtyInput = card.querySelector("[data-flip-qty-input]");
    const qty = qtyInput ? clampQty(qtyInput.value) : 1;   // blueprints: total runs

    let fitting = null;
    const fitSelect = card.querySelector("[data-flip-fitting]");
    if (fitSelect && fitSelect.value) {
      const opt = fitSelect.selectedOptions[0];
      const price = Number(opt?.dataset.price);
      fitting = { name: fitSelect.value, price: Number.isFinite(price) ? price : 0 };
    }
    return { qty, fitting };
  }

  // Qty stepper (±1 or ±100k/±1m via data-flip-amount); blueprints/materials too.
  function stepFlipInput(btn) {
    const card = btn.closest(".item-card");
    if (!card) return;
    const input = card.querySelector("[data-flip-qty-input]");
    if (!input) return;
    const dir = Number(btn.dataset.flipDir) || 0;
    const amount = Number(btn.dataset.flipAmount) || 1;
    input.value = formatQty(Math.max(1, clampQty(input.value) + dir * amount));
  }

  function updateFlipFitPrice(select) {
    const priceEl = select.closest(".flip-field")?.querySelector("[data-flip-fit-price]");
    if (!priceEl) return;
    const price = Number(select.selectedOptions[0]?.dataset.price) || 0;
    priceEl.textContent = price > 0 ? `+${formatPrice(price)} ISK` : "+0 ISK";
  }

  document.addEventListener("click", (e) => {
    // Shared ADD: add with configurator values (defaults on front face, picks when
    // flipped), reset fields but leave the face as-is (closed via Options/click-out/Esc).
    // readFlipControls defaults for cards without a back face.
    const addBtn = e.target.closest("[data-cart-add]");
    if (addBtn) {
      const card = addBtn.closest(".item-card");
      const product = getProductData(card);
      if (product) {
        const sel = readFlipControls(card);
        const entry = addToCart(product, sel.qty, { fitting: sel.fitting });
        if (entry) showAddToCartToast(entry);
      }
      resetFlipControls(card);
      return;
    }

    // Options / Close: toggle the configurator open or shut.
    const flipToggle = e.target.closest("[data-flip-toggle]");
    if (flipToggle) {
      const card = flipToggle.closest(".item-card");
      if (card?.classList.contains("is-flipped")) flipCardBack(card);
      else openFlip(card);
      return;
    }

    // +/- steppers inside the configurator (qty; ±100k/±1m on materials).
    const flipStepBtn = e.target.closest("[data-flip-step]");
    if (flipStepBtn) { stepFlipInput(flipStepBtn); return; }

    // Cart drawer action buttons.
    const actionBtn = e.target.closest("[data-cart-action]");
    if (actionBtn) {
      const action = actionBtn.dataset.cartAction;
      const key    = String(actionBtn.dataset.name || "").trim();

      if (action === "decrease" && key) changeQty(key, -1);
      if (action === "increase" && key) changeQty(key,  1);
      if (action === "remove"   && key) removeItem(key);
      if (action === "bigstep"  && key) stepQtyBig(key, Number(actionBtn.dataset.delta) || 0);
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
    if (t.dataset.cartQtyInput !== undefined) {
      const digits = parseQtyDigits(t.value).slice(0, 9);
      t.value = digits ? formatQty(Number.parseInt(digits, 10)) : "";
      resizeQtyInput(t);
      return;
    }
    if (t.hasAttribute("data-flip-qty-input")) {
      const digits = parseQtyDigits(t.value).slice(0, 9);
      t.value = digits ? formatQty(Number.parseInt(digits, 10)) : "";
    }
  });

  document.addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.cartQtyInput !== undefined) {
      setQty(t.dataset.cartQtyInput, t.value);
      return;
    }
    if (t.hasAttribute("data-flip-qty-input")) {
      t.value = formatQty(clampQty(t.value));
      return;
    }
    if (t.hasAttribute("data-flip-fitting")) {
      updateFlipFitPrice(t);
      return;
    }
    if (t.dataset.lineFitting !== undefined) {
      changeLineFitting(t.dataset.lineFitting, t.value);
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
    // One line per (item, fitting). Blueprint qty == total runs. The fitting
    // rides as a single add-on priced per unit (qty == the line qty, server-side).
    return Object.values(cart).map((item) => ({
      name: item.name,
      category: item.category || "",
      qty: item.qty,
      price: item.price,
      fitting: item.fitting && item.fitting.name
        ? { name: item.fitting.name, price: Number.isFinite(item.fitting.price) ? item.fitting.price : 0 }
        : null,
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
