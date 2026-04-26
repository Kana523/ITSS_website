document.addEventListener("DOMContentLoaded", () => {
  const cartCountEl      = document.getElementById("cart-count");
  const cartItemCountEl  = document.getElementById("cart-item-count");
  const cartItemsEl      = document.getElementById("cart-items");
  const cartTotalEl      = document.getElementById("cart-total");
  const cartClearBtn     = document.getElementById("cart-clear");
  const cartToggleBtn    = document.getElementById("cart-toggle");
  const cartDrawer       = document.getElementById("cart-drawer");
  const cartBackdrop     = document.getElementById("cart-backdrop");
  const cartDrawerClose  = document.getElementById("cart-drawer-close");
  const cartCheckoutBtn  = document.getElementById("cart-checkout");

  if (!cartItemsEl || !cartTotalEl) return;

  const { formatPrice, parsePriceToIsk } = window.ShopUtils;
  const CART_STORAGE_KEY = "itss_shop_cart_v1";

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
    cartTotalEl.textContent = formatPrice(totalValue);
    cartItemsEl.innerHTML = "";

    if (items.length === 0) {
      const empty = document.createElement("li");
      empty.className = "cart-empty";
      empty.textContent = "Your cart is empty.";
      cartItemsEl.appendChild(empty);
      if (cartClearBtn) cartClearBtn.disabled = true;
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
      totalVal.textContent = formatPrice(itemLineTotal);
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
  }

  // ── Event delegation ─────────────────────────────────────────────────────────

  cartToggleBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    cartDrawer?.hidden !== false ? openCart() : closeCart();
  });

  cartDrawerClose?.addEventListener("click", closeCart);
  cartBackdrop?.addEventListener("click", closeCart);

  document.addEventListener("click", (e) => {
    // Product card qty pickers
    const qtyBtn = e.target.closest("[data-qty-action]");
    if (qtyBtn) {
      const input = qtyBtn.closest(".qty-picker")?.querySelector("[data-cart-qty]");
      if (!input) return;
      const cur = clampQty(input.value);
      input.value = String(qtyBtn.dataset.qtyAction === "decrease" ? Math.max(1, cur - 1) : cur + 1);
      resizeQtyInput(input);
      return;
    }

    // Add to cart buttons on product cards
    const addBtn = e.target.closest("[data-cart-add]");
    if (addBtn) {
      const card     = addBtn.closest(".item-card");
      const qtyInput = card?.querySelector("[data-cart-qty]");
      const qty      = clampQty(qtyInput?.value ?? 1);
      if (qtyInput) { qtyInput.value = String(qty); resizeQtyInput(qtyInput); }
      addToCart(getProductData(card), qty);
      openCart();
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
    const cardQty = e.target.closest("[data-cart-qty]");
    if (cardQty) { cardQty.value = parseQtyDigits(cardQty.value); resizeQtyInput(cardQty); return; }
    if (e.target.dataset.cartQtyInput !== undefined) {
      const digits = parseQtyDigits(e.target.value).slice(0, 8);
      e.target.value = digits ? formatQty(Number.parseInt(digits, 10)) : "";
      resizeQtyInput(e.target);
    }
  });

  document.addEventListener("change", (e) => {
    const cardQty = e.target.closest("[data-cart-qty]");
    if (cardQty) { cardQty.value = String(clampQty(cardQty.value)); resizeQtyInput(cardQty); return; }
    if (e.target.dataset.cartQtyInput !== undefined) {
      setQty(e.target.dataset.cartQtyInput, e.target.value);
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

  document.querySelectorAll(".cart-identity-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".cart-identity-tab").forEach(t => t.classList.remove("cart-identity-tab--active"));
      tab.classList.add("cart-identity-tab--active");
      const target = tab.dataset.tab;
      document.querySelectorAll(".cart-identity-panel").forEach(p => { p.hidden = p.dataset.panel !== target; });
    });
  });

  // ── Checkout ──────────────────────────────────────────────────────────────────

  cartCheckoutBtn?.addEventListener("click", () => {
    const items = Object.values(cart);
    if (!items.length) return;

    const activeTab = document.querySelector(".cart-identity-tab--active")?.dataset.tab;
    let header = "";

    if (activeTab === "name") {
      const charName = document.getElementById("cart-char-name")?.value.trim();
      if (!charName) { document.getElementById("cart-char-name")?.focus(); return; }
      header = `Order for: ${charName}`;
    } else {
      const orderId = `ITSS-${Date.now().toString(36).toUpperCase()}`;
      header = `Order ID: ${orderId}`;
    }

    const lines = items.map((item) => {
      let line = `${item.qty}x ${item.name} @ ${formatPrice(item.price)} ISK`;
      item.extras?.forEach((ex) => {
        const priceStr = Number.isFinite(ex.price) ? ` @ ${formatPrice(ex.price)} ISK` : "";
        line += `\n  + ${ex.name} ×${ex.qty}${priceStr}`;
      });
      return line;
    });

    const totalValue = items.reduce((s, i) => {
      let sum = s + i.price * i.qty;
      i.extras?.forEach((ex) => {
        if (Number.isFinite(ex.price)) sum += ex.price * ex.qty;
      });
      return sum;
    }, 0);
    const text = `${header}\n\n${lines.join("\n")}\n\nTotal: ${formatPrice(totalValue)} ISK`;

    navigator.clipboard?.writeText(text).catch(() => {});
    cartCheckoutBtn.textContent = "Copied!";
    setTimeout(() => { cartCheckoutBtn.textContent = "Checkout"; }, 2200);
  });

  // ── Clear ─────────────────────────────────────────────────────────────────────

  cartClearBtn?.addEventListener("click", clearCart);
  document.addEventListener("shop:product-data-updated", syncCartPricesFromProducts);

  // ── Init ──────────────────────────────────────────────────────────────────────

  document.querySelectorAll("[data-cart-qty]").forEach((input) => {
    input.value = String(clampQty(input.value));
    resizeQtyInput(input);
  });

  syncCartPricesFromProducts();
  renderCart();
});
