document.addEventListener("DOMContentLoaded", () => {
  const cartCountEl      = document.getElementById("cart-count");
  const cartItemCountEl  = document.getElementById("cart-item-count");
  const cartItemsEl      = document.getElementById("cart-items");
  const cartTotalEl      = document.getElementById("cart-total");
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

  const TURNSTILE_CONTAINER = "#cart-turnstile";
  const TURNSTILE_SITEKEY = document.getElementById("cart-turnstile")?.dataset.sitekey || "";
  let turnstileWidgetId = null;
  let turnstilePending = null;

  function ensureTurnstileRendered() {
    if (turnstileWidgetId !== null) return Promise.resolve();
    if (!document.getElementById("cart-turnstile") || !TURNSTILE_SITEKEY) {
      return Promise.reject(new Error("Turnstile container missing"));
    }
    return new Promise((resolve, reject) => {
      const start = Date.now();
      const tick = () => {
        if (window.turnstile?.render) {
          try {
            turnstileWidgetId = window.turnstile.render(TURNSTILE_CONTAINER, {
              sitekey: TURNSTILE_SITEKEY,
              size: "invisible",
              theme: "dark",
              callback: (token) => {
                if (turnstilePending) {
                  turnstilePending.resolve(token);
                  turnstilePending = null;
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

  if (!cartItemsEl || !cartTotalEl) return;

  if (!window.ShopUtils) {
    console.error("shop-cart.js: window.ShopUtils missing — shop-filter.js failed to load.");
    return;
  }
  if (!window.ShopStockFeed) {
    console.error("shop-cart.js: window.ShopStockFeed missing — shop-stock-feed.js failed to load.");
    return;
  }
  const { formatPrice, formatPriceLong, parsePriceToIsk } = window.ShopUtils;
  const CART_STORAGE_KEY = "itss_shop_cart_v1";
  const ORDER_ID_LENGTH = 20;
  const ORDER_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

  function generateOrderId() {
    const out = new Array(ORDER_ID_LENGTH);
    const cryptoObj = window.crypto || window.msCrypto;
    if (cryptoObj?.getRandomValues) {
      const buf = new Uint32Array(ORDER_ID_LENGTH);
      cryptoObj.getRandomValues(buf);
      for (let i = 0; i < ORDER_ID_LENGTH; i++) {
        out[i] = ORDER_ID_ALPHABET[buf[i] % ORDER_ID_ALPHABET.length];
      }
    } else {
      for (let i = 0; i < ORDER_ID_LENGTH; i++) {
        out[i] = ORDER_ID_ALPHABET[Math.floor(Math.random() * ORDER_ID_ALPHABET.length)];
      }
    }
    return out.join("");
  }

  const FITTINGS = [
    { name: "Bork 1", price:  50000000 },
    { name: "Bork 2", price: 120000000 },
    { name: "Bork 3", price: 275000000 },
  ];

  let cart = loadCart();

  // ── Persistence ─────────────────────────────────────────────────────────────

  function loadCart() {
    try {
      const stored = localStorage.getItem(CART_STORAGE_KEY);
      if (!stored) return {};
      const parsed = JSON.parse(stored);
      if (!parsed || typeof parsed !== "object") return {};

      const normalized = {};
      Object.entries(parsed).forEach(([sku, item]) => {
        if (!item || typeof item !== "object") return;
        const safeSku   = String(item.sku  || sku || "").trim();
        const safeName  = String(item.name || "").trim();
        const safeQty   = Number(item.qty);
        const safePrice = parsePriceToIsk(item.price, item.priceLabel);
        if (!safeSku || !safeName || !Number.isFinite(safeQty) || safeQty < 1) return;

        normalized[safeSku] = {
          sku:        safeSku,
          name:       safeName,
          qty:        Math.floor(safeQty),
          price:      Number.isFinite(safePrice) ? safePrice : 0,
          priceLabel: formatPrice(Number.isFinite(safePrice) ? safePrice : 0),
          category:   String(item.category || "").trim(),
          img:        String(item.img       || "").trim(),
          extras:     Array.isArray(item.extras) ? item.extras : [],
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
    const sku = String(card.dataset.sku || "").trim();
    if (!sku) return null;
    const name     = String(card.querySelector("h2, h3")?.textContent || "Unnamed item").trim();
    const price    = parsePriceToIsk(card.dataset.price);
    const category = String(card.dataset.category || "").trim();
    const imgEl    = card.querySelector("img");
    const img      = imgEl ? imgEl.src : "";
    return { sku, name, price, category, img };
  }

  const MAX_QTY = 99000000;

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

  function scheduleToastVanish(entry, sku) {
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
        if (activeToasts.get(sku) === entry) activeToasts.delete(sku);
      }, TOAST_VANISH_MS);
    }, TOAST_HOLD_MS);
  }

  function showAddToCartToast(product) {
    if (!product?.sku) return;
    const container = ensureToastContainer();
    const totalQty  = cart[product.sku]?.qty ?? 0;
    const qtyText   = `×${formatQty(totalQty)} in cart`;

    const existing = activeToasts.get(product.sku);
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
      scheduleToastVanish(existing, product.sku);
      return;
    }

    const built = buildToastEl(product);
    built.qtyEl.textContent = qtyText;
    container.appendChild(built.el);

    const entry = { el: built.el, qtyEl: built.qtyEl };
    activeToasts.set(product.sku, entry);

    requestAnimationFrame(() => requestAnimationFrame(() => {
      built.el.classList.add("cart-toast--visible");
    }));

    scheduleToastVanish(entry, product.sku);
  }

  // ── Cart mutations ───────────────────────────────────────────────────────────

  function addToCart(product, qtyToAdd = 1) {
    if (!product) return;
    if (!cart[product.sku]) {
      cart[product.sku] = { ...product, qty: 0, extras: [] };
    }
    cart[product.sku].price    = product.price;
    cart[product.sku].category = product.category || cart[product.sku].category;
    cart[product.sku].img      = product.img      || cart[product.sku].img;
    cart[product.sku].qty     += clampQty(qtyToAdd);
    saveCart();
    renderCart();
  }

  function syncCartPricesFromProducts() {
    let changed = false;
    document.querySelectorAll(".display .item-card").forEach((card) => {
      const product = getProductData(card);
      if (!product || !cart[product.sku]) return;
      const entry = cart[product.sku];
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
    if (!changed) return;
    saveCart();
    renderCart();
  }

  function changeQty(sku, delta) {
    if (!cart[sku]) return;
    cart[sku].qty += delta;
    if (cart[sku].qty <= 0) delete cart[sku];
    saveCart();
    renderCart();
  }

  function setQty(sku, qty) {
    if (!cart[sku]) return;
    cart[sku].qty = clampQty(qty);
    saveCart();
    renderCart();
  }

  function removeItem(sku) {
    delete cart[sku];
    saveCart();
    renderCart();
  }

  function clearCart() {
    cart = {};
    saveCart();
    renderCart();
  }

  function addExtra(sku, fitting) {
    if (!cart[sku] || !fitting?.name) return;
    if (!cart[sku].extras) cart[sku].extras = [];
    const existing = cart[sku].extras.find((e) => e.name === fitting.name);
    if (existing) {
      existing.qty += 1;
      if (Number.isFinite(fitting.price)) existing.price = fitting.price;
    } else {
      cart[sku].extras.push({ name: fitting.name, price: fitting.price, qty: 1 });
    }
    saveCart();
    renderCart();
  }

  function changeExtraQty(sku, idx, delta) {
    const ex = cart[sku]?.extras?.[idx];
    if (!ex) return;
    ex.qty += delta;
    if (ex.qty <= 0) cart[sku].extras.splice(idx, 1);
    saveCart();
    renderCart();
  }

  function setExtraQty(sku, idx, qty) {
    const ex = cart[sku]?.extras?.[idx];
    if (!ex) return;
    ex.qty = clampQty(qty);
    saveCart();
    renderCart();
  }

  function removeExtra(sku, idx) {
    if (!cart[sku]?.extras) return;
    cart[sku].extras.splice(idx, 1);
    saveCart();
    renderCart();
  }

  // ── DOM helpers ──────────────────────────────────────────────────────────────

  function makeBtn(text, dataMap, cls) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = cls;
    btn.textContent = text;
    Object.entries(dataMap).forEach(([k, v]) => { btn.dataset[k] = v; });
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
      totalValue += item.price * item.qty;
      item.extras?.forEach((ex) => {
        if (Number.isFinite(ex.price)) totalValue += ex.price * ex.qty;
      });
    }

    // badge + aria
    if (cartCountEl) cartCountEl.textContent = formatQty(totalItems);
    if (cartItemCountEl) cartItemCountEl.textContent = `${formatQty(totalItems)} item${totalItems !== 1 ? "s" : ""}`;
    cartToggleBtn?.setAttribute("aria-label", `Cart, ${formatQty(totalItems)} item${totalItems !== 1 ? "s" : ""}`);
    cartTotalEl.textContent = formatPriceLong(totalValue);
    cartItemsEl.innerHTML = "";

    if (items.length === 0) {
      const empty = document.createElement("li");
      empty.className = "cart-empty";
      empty.textContent = "Your cart is empty.";
      cartItemsEl.appendChild(empty);
      if (cartClearBtn) cartClearBtn.disabled = true;
      if (cartClearNameBtn) cartClearNameBtn.disabled = true;
      return;
    }

    items.sort((a, b) => a.name.localeCompare(b.name));

    items.forEach((item) => {
      const isShip = item.category === "ship";
      const li = document.createElement("li");
      li.className = `cart-item${isShip ? " cart-item--ship" : ""}`;

      // ── Image ──
      const imgWrap = document.createElement("div");
      imgWrap.className = "cart-item-img";
      if (item.img) {
        const img = document.createElement("img");
        img.src = item.img;
        img.alt = item.name;
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
      const removeBtn = makeBtn("✕", { cartAction: "remove", sku: item.sku }, "cart-remove-btn");
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
      priceEl.innerHTML = `${formatPrice(item.price)}<span class="cart-price-label"> / item</span>`;
      const qtyWrap = makeQtyWrap(
        item.qty,
        isShip ? "lg" : "sm",
        { cartAction: "decrease", sku: item.sku },
        { cartAction: "increase", sku: item.sku },
        { cartQtyInput: item.sku }
      );
      mainRow.appendChild(priceEl);
      mainRow.appendChild(qtyWrap);
      stack.appendChild(mainRow);

      // Extras (ships only)
      if (isShip) {
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
            exControls.appendChild(makeBtn("−", { cartAction: "extra-decrease", sku: item.sku, extraIdx: j }, "cart-action-btn cart-action-btn--sm"));
            const exInput = document.createElement("input");
            exInput.type = "text";
            exInput.inputMode = "numeric";
            exInput.className = "cart-item-qty cart-item-qty--sm";
            exInput.value = formatQty(ex.qty);
            exInput.setAttribute("aria-label", `Quantity of ${ex.name}`);
            exInput.dataset.cartExtraQtyInput = item.sku;
            exInput.dataset.extraIdx = j;
            exControls.appendChild(exInput);
            exControls.appendChild(makeBtn("+", { cartAction: "extra-increase", sku: item.sku, extraIdx: j }, "cart-action-btn cart-action-btn--sm"));
            exControls.appendChild(makeBtn("✕", { cartAction: "extra-remove", sku: item.sku, extraIdx: j }, "cart-extra-remove"));

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
        fitSelect.dataset.fittingSelect = item.sku;
        fitSelect.setAttribute("aria-label", `Add fitting to ${item.name}`);

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "+ fitting";
        placeholder.selected = true;
        fitSelect.appendChild(placeholder);

        FITTINGS.forEach((f) => {
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
      let itemLineTotal = item.price * item.qty;
      item.extras?.forEach((ex) => {
        if (Number.isFinite(ex.price)) itemLineTotal += ex.price * ex.qty;
      });
      totalVal.textContent = formatPriceLong(itemLineTotal);
      totalRow.appendChild(totalLabel);
      totalRow.appendChild(totalVal);
      stack.appendChild(totalRow);

      content.appendChild(stack);
      li.appendChild(imgWrap);
      li.appendChild(content);
      cartItemsEl.appendChild(li);
    });

    cartItemsEl.querySelectorAll(".cart-item-qty").forEach(resizeQtyInput);

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

  document.addEventListener("click", (e) => {
    // Add to cart buttons on product cards
    const addBtn = e.target.closest("[data-cart-add]");
    if (addBtn) {
      const card = addBtn.closest(".item-card");
      const product = getProductData(card);
      if (product) {
        addToCart(product, 1);
        showAddToCartToast(product);
      }
      return;
    }

    // Cart action buttons
    const actionBtn = e.target.closest("[data-cart-action]");
    if (!actionBtn) return;
    const action = actionBtn.dataset.cartAction;
    const sku    = String(actionBtn.dataset.sku || "").trim();

    if (action === "decrease"       && sku) changeQty(sku, -1);
    if (action === "increase"       && sku) changeQty(sku,  1);
    if (action === "remove"         && sku) removeItem(sku);

    if (action === "extra-decrease" && sku) changeExtraQty(sku, Number(actionBtn.dataset.extraIdx), -1);
    if (action === "extra-increase" && sku) changeExtraQty(sku, Number(actionBtn.dataset.extraIdx),  1);
    if (action === "extra-remove"   && sku) removeExtra(sku, Number(actionBtn.dataset.extraIdx));
  });

  document.addEventListener("input", (e) => {
    if (e.target.dataset.cartQtyInput !== undefined || e.target.dataset.cartExtraQtyInput !== undefined) {
      const digits = parseQtyDigits(e.target.value).slice(0, 8);
      e.target.value = digits ? formatQty(Number.parseInt(digits, 10)) : "";
      resizeQtyInput(e.target);
    }
  });

  document.addEventListener("change", (e) => {
    if (e.target.dataset.cartQtyInput !== undefined) {
      setQty(e.target.dataset.cartQtyInput, e.target.value);
      return;
    }
    if (e.target.dataset.cartExtraQtyInput !== undefined) {
      setExtraQty(e.target.dataset.cartExtraQtyInput, Number(e.target.dataset.extraIdx), e.target.value);
      return;
    }
    if (e.target.dataset.fittingSelect) {
      const sku = e.target.dataset.fittingSelect;
      const fittingName = e.target.value;
      e.target.value = "";
      if (!fittingName) return;
      const fitting = FITTINGS.find((f) => f.name === fittingName);
      if (fitting) addExtra(sku, fitting);
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
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(value);
        } else {
          const ta = document.createElement("textarea");
          ta.value = value;
          ta.setAttribute("readonly", "");
          ta.style.position = "absolute";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
        }
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
      sku: item.sku,
      name: item.name,
      category: item.category || "",
      qty: item.qty,
      price: item.price,
      extras: (item.extras || []).map((ex) => ({
        name: ex.name,
        price: Number.isFinite(ex.price) ? ex.price : 0,
        qty: ex.qty
      }))
    }));
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

    const isDevHost =
      location.protocol === "file:" ||
      ["localhost", "127.0.0.1", "0.0.0.0", "::1"].includes(location.hostname) ||
      location.hostname.endsWith(".local");

    const orderId = generateOrderId();

    cartCheckoutBtn.disabled = true;
    cartCheckoutBtn.textContent = "Verifying…";

    try {
      if (isDevHost) {
        console.info("[dev] Skipping Turnstile + server submit. Order ID:", orderId);
      } else {
        let turnstileToken;
        try {
          turnstileToken = await getTurnstileToken();
        } catch (verifyErr) {
          console.error("Turnstile verification failed.", verifyErr);
          showOrderIdError("Verification failed. Please try again.");
          cartCheckoutBtn.textContent = "Place Order";
          return;
        }
        cartCheckoutBtn.textContent = "Sending…";
        await ShopStockFeed.submitOrder(orderEndpoint, { orderId, items, turnstileToken });
      }
      showGeneratedOrderId(orderId);
      cartCheckoutBtn.textContent = "Place Order";
    } catch (error) {
      console.error("Order submission failed.", error);
      showOrderIdError("Couldn't reach the order server. Please retry.");
      cartCheckoutBtn.textContent = "Retry";
    } finally {
      try { if (turnstileWidgetId !== null) window.turnstile?.reset?.(turnstileWidgetId); } catch (_) {}
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

    const isDevHost =
      location.protocol === "file:" ||
      ["localhost", "127.0.0.1", "0.0.0.0", "::1"].includes(location.hostname) ||
      location.hostname.endsWith(".local");

    cartCheckoutNameBtn.disabled = true;
    cartCheckoutNameBtn.textContent = "Verifying…";

    try {
      if (isDevHost) {
        console.info("[dev] Skipping Turnstile + server submit. Name order:", charName);
      } else {
        let turnstileToken;
        try {
          turnstileToken = await getTurnstileToken();
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
        await ShopStockFeed.submitOrder(orderEndpoint, { charName, items, turnstileToken });
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
      try { if (turnstileWidgetId !== null) window.turnstile?.reset?.(turnstileWidgetId); } catch (_) {}
      cartCheckoutNameBtn.disabled = false;
    }
  }

  cartCheckoutBtn?.addEventListener("click", handleOrderIdCheckout);
  cartCheckoutNameBtn?.addEventListener("click", handleNameCheckout);

  // ── Clear ─────────────────────────────────────────────────────────────────────

  cartClearBtn?.addEventListener("click", clearCart);
  cartClearNameBtn?.addEventListener("click", clearCart);
  document.addEventListener("shop:product-data-updated", syncCartPricesFromProducts);

  // ── Init ──────────────────────────────────────────────────────────────────────

  syncCartPricesFromProducts();
  renderCart();
});
