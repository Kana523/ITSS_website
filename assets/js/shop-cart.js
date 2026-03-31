document.addEventListener("DOMContentLoaded", () => {
  const cartCountEl = document.getElementById("cart-count");
  const cartItemsEl = document.getElementById("cart-items");
  const cartTotalEl = document.getElementById("cart-total");
  const cartClearBtn = document.getElementById("cart-clear");

  if (!cartItemsEl || !cartTotalEl) {
    return;
  }

  const CART_STORAGE_KEY = "itss_shop_cart_v1";
  let cart = loadCart();

  function loadCart() {
    try {
      const stored = localStorage.getItem(CART_STORAGE_KEY);
      if (!stored) return {};
      const parsed = JSON.parse(stored);
      if (!parsed || typeof parsed !== "object") return {};

      const normalized = {};
      Object.entries(parsed).forEach(([sku, item]) => {
        if (!item || typeof item !== "object") return;

        const safeSku = String(item.sku || sku || "").trim();
        const safeName = String(item.name || "").trim();
        const safeQty = Number(item.qty);
        const safePrice = parsePriceToIsk(item.price, item.priceLabel);

        if (!safeSku || !safeName || !Number.isFinite(safeQty) || safeQty < 1) {
          return;
        }

        normalized[safeSku] = {
          sku: safeSku,
          name: safeName,
          qty: Math.floor(safeQty),
          price: Number.isFinite(safePrice) ? safePrice : 0,
          priceLabel: formatPrice(Number.isFinite(safePrice) ? safePrice : 0)
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
      if (Number.isFinite(direct) && direct > 0) {
        return direct;
      }

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

  function syncProductPriceLabels() {
    const cards = Array.from(document.querySelectorAll(".display .item-card"));
    cards.forEach((card) => {
      const safePrice = parsePriceToIsk(card.dataset.price);
      const formattedPrice = formatPrice(safePrice);

      card.dataset.price = String(safePrice);

      const priceEl = card.querySelector(".item-price") || card.querySelector(".item-card-footer p");
      if (!priceEl) return;

      if (priceEl.querySelector("strong")) {
        priceEl.innerHTML = `<strong>Price:</strong> ${formattedPrice}`;
        return;
      }

      if (priceEl.querySelector("b")) {
        priceEl.innerHTML = `<b>Price:</b> ${formattedPrice}`;
        return;
      }

      priceEl.textContent = `Price: ${formattedPrice}`;
    });
  }

  function getProductData(card) {
    if (!card) return null;

    const sku = String(card.dataset.sku || "").trim();
    if (!sku) return null;

    const name = String(card.querySelector("h2, h3")?.textContent || "Unnamed item").trim();

    const safePrice = parsePriceToIsk(card.dataset.price);

    return {
      sku,
      name,
      price: safePrice
    };
  }

  function clampQty(rawQty) {
    const parsed = Number.parseInt(String(rawQty), 10);
    if (!Number.isFinite(parsed) || parsed < 1) return 1;
    return Math.min(parsed, 999999);
  }

  function resizeQtyInput(input) {
    if (!input) return;
    const digits = Math.max(1, String(input.value || "").length);
    const widthInCh = Math.min(8, digits + 1);
    input.style.width = `${widthInCh}ch`;
  }

  function addToCart(product, qtyToAdd = 1) {
    if (!product) return;

    if (!cart[product.sku]) {
      cart[product.sku] = { ...product, qty: 0 };
    }

    cart[product.sku].price = product.price;
    cart[product.sku].qty += clampQty(qtyToAdd);
    saveCart();
    renderCart();
  }

  function syncCartPricesFromProducts() {
    let changed = false;

    document.querySelectorAll(".display .item-card").forEach((card) => {
      const product = getProductData(card);
      if (!product || !cart[product.sku]) return;

      if (cart[product.sku].price !== product.price) {
        cart[product.sku].price = product.price;
        cart[product.sku].priceLabel = formatPrice(product.price);
        changed = true;
      }
    });

    if (!changed) return;

    saveCart();
    renderCart();
  }

  function decreaseQty(sku) {
    if (!cart[sku]) return;
    cart[sku].qty -= 1;
    if (cart[sku].qty <= 0) {
      delete cart[sku];
    }
    saveCart();
    renderCart();
  }

  function increaseQty(sku) {
    if (!cart[sku]) return;
    cart[sku].qty += 1;
    saveCart();
    renderCart();
  }

  function removeItem(sku) {
    if (!cart[sku]) return;
    delete cart[sku];
    saveCart();
    renderCart();
  }

  function clearCart() {
    cart = {};
    saveCart();
    renderCart();
  }

  function renderCart() {
    const items = Object.values(cart);
    const totalItems = items.reduce((sum, item) => sum + item.qty, 0);
    const totalValue = items.reduce((sum, item) => sum + item.price * item.qty, 0);

    if (cartCountEl) {
      cartCountEl.textContent = String(totalItems);
    }
    cartTotalEl.textContent = formatPrice(totalValue);

    cartItemsEl.innerHTML = "";

    if (items.length === 0) {
      const empty = document.createElement("li");
      empty.className = "cart-empty";
      empty.textContent = "Cart is empty.";
      cartItemsEl.appendChild(empty);
      if (cartClearBtn) cartClearBtn.disabled = true;
      return;
    }

    items.sort((a, b) => a.name.localeCompare(b.name));

    items.forEach((item) => {
      const row = document.createElement("li");
      row.className = "cart-item";

      const info = document.createElement("div");
      info.className = "cart-item-info";

      const name = document.createElement("span");
      name.className = "cart-item-name";
      name.textContent = item.name;

      const price = document.createElement("span");
      price.className = "cart-item-price";
      price.textContent = `${formatPrice(item.price)} each`;

      info.appendChild(name);
      info.appendChild(price);

      const controls = document.createElement("div");
      controls.className = "cart-item-controls";

      const minusBtn = document.createElement("button");
      minusBtn.type = "button";
      minusBtn.className = "cart-action-btn";
      minusBtn.dataset.cartAction = "decrease";
      minusBtn.dataset.sku = item.sku;
      minusBtn.setAttribute("aria-label", `Decrease quantity of ${item.name}`);
      minusBtn.textContent = "-";

      const qty = document.createElement("span");
      qty.className = "cart-item-qty";
      qty.textContent = String(item.qty);

      const plusBtn = document.createElement("button");
      plusBtn.type = "button";
      plusBtn.className = "cart-action-btn";
      plusBtn.dataset.cartAction = "increase";
      plusBtn.dataset.sku = item.sku;
      plusBtn.setAttribute("aria-label", `Increase quantity of ${item.name}`);
      plusBtn.textContent = "+";

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "cart-remove-btn";
      removeBtn.dataset.cartAction = "remove";
      removeBtn.dataset.sku = item.sku;
      removeBtn.textContent = "Remove";

      controls.appendChild(minusBtn);
      controls.appendChild(qty);
      controls.appendChild(plusBtn);
      controls.appendChild(removeBtn);

      row.appendChild(info);
      row.appendChild(controls);
      cartItemsEl.appendChild(row);
    });

    if (cartClearBtn) cartClearBtn.disabled = false;
  }

  document.addEventListener("click", (event) => {
    const qtyBtn = event.target.closest("[data-qty-action]");
    if (qtyBtn) {
      const picker = qtyBtn.closest(".qty-picker");
      const input = picker?.querySelector("[data-cart-qty]");
      if (!input) return;

      const current = clampQty(input.value);
      const next = qtyBtn.dataset.qtyAction === "decrease" ? Math.max(1, current - 1) : current + 1;
      input.value = String(next);
      resizeQtyInput(input);
      return;
    }

    const addBtn = event.target.closest("[data-cart-add]");
    if (addBtn) {
      const productCard = addBtn.closest(".item-card");
      const qtyInput = productCard?.querySelector("[data-cart-qty]");
      const qty = clampQty(qtyInput?.value);
      if (qtyInput) {
        qtyInput.value = String(qty);
        resizeQtyInput(qtyInput);
      }
      addToCart(getProductData(productCard), qty);
      return;
    }

    const actionBtn = event.target.closest("[data-cart-action]");
    if (!actionBtn) return;

    const action = actionBtn.dataset.cartAction;
    const sku = String(actionBtn.dataset.sku || "").trim();
    if (!sku) return;

    if (action === "decrease") decreaseQty(sku);
    if (action === "increase") increaseQty(sku);
    if (action === "remove") removeItem(sku);
  });

  document.addEventListener("input", (event) => {
    const qtyInput = event.target.closest("[data-cart-qty]");
    if (!qtyInput) return;
    qtyInput.value = qtyInput.value.replace(/[^\d]/g, "");
    resizeQtyInput(qtyInput);
  });

  document.addEventListener("change", (event) => {
    const qtyInput = event.target.closest("[data-cart-qty]");
    if (!qtyInput) return;
    qtyInput.value = String(clampQty(qtyInput.value));
    resizeQtyInput(qtyInput);
  });

  document.querySelectorAll("[data-cart-qty]").forEach((qtyInput) => {
    qtyInput.value = String(clampQty(qtyInput.value));
    resizeQtyInput(qtyInput);
  });

  syncProductPriceLabels();
  cartClearBtn?.addEventListener("click", clearCart);
  document.addEventListener("shop:product-data-updated", () => {
    syncProductPriceLabels();
    syncCartPricesFromProducts();
  });

  renderCart();
});
