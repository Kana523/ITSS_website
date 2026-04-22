document.addEventListener("DOMContentLoaded", () => {
  const cartCountEl = document.getElementById("cart-count");
  const cartItemsEl = document.getElementById("cart-items");
  const cartTotalEl = document.getElementById("cart-total");
  const cartClearBtn = document.getElementById("cart-clear");
  const cartToggleBtn = document.getElementById("cart-toggle");
  const cartDropdown = document.getElementById("cart-dropdown");

  if (!cartItemsEl || !cartTotalEl) {
    return;
  }

  const { formatPrice, parsePriceToIsk } = window.ShopUtils;
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

  function getProductData(card) {
    if (!card) return null;

    const sku = String(card.dataset.sku || "").trim();
    if (!sku) return null;

    const name = String(card.querySelector("h2, h3")?.textContent || "Unnamed item").trim();
    const safePrice = parsePriceToIsk(card.dataset.price);

    return { sku, name, price: safePrice };
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

  function openCart() {
    if (!cartDropdown) return;
    cartDropdown.hidden = false;
    cartToggleBtn?.setAttribute("aria-expanded", "true");
  }

  function closeCart() {
    if (!cartDropdown) return;
    cartDropdown.hidden = true;
    cartToggleBtn?.setAttribute("aria-expanded", "false");
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

  function changeQty(sku, delta) {
    if (!cart[sku]) return;
    cart[sku].qty += delta;
    if (cart[sku].qty <= 0) delete cart[sku];
    saveCart();
    renderCart();
  }

  function setQty(sku, qty) {
    if (!cart[sku]) return;
    const clamped = clampQty(qty);
    cart[sku].qty = clamped;
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
    let totalItems = 0;
    let totalValue = 0;
    for (const item of items) {
      totalItems += item.qty;
      totalValue += item.price * item.qty;
    }

    if (cartCountEl) {
      cartCountEl.textContent = String(totalItems);
    }

    if (cartToggleBtn) {
      cartToggleBtn.setAttribute("aria-label", `Cart, ${totalItems} item${totalItems !== 1 ? "s" : ""}`);
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

      const qtyInput = document.createElement("input");
      qtyInput.type = "number";
      qtyInput.className = "cart-item-qty";
      qtyInput.min = "1";
      qtyInput.max = "999999";
      qtyInput.value = String(item.qty);
      qtyInput.dataset.cartQtyInput = item.sku;
      qtyInput.setAttribute("aria-label", `Quantity of ${item.name}`);

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
      removeBtn.setAttribute("aria-label", `Remove ${item.name} from cart`);
      removeBtn.textContent = "Remove";

      controls.appendChild(minusBtn);
      controls.appendChild(qtyInput);
      controls.appendChild(plusBtn);
      controls.appendChild(removeBtn);

      row.appendChild(info);
      row.appendChild(controls);
      cartItemsEl.appendChild(row);
    });

    if (cartClearBtn) cartClearBtn.disabled = false;
  }

  cartToggleBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    if (cartDropdown?.hidden) openCart(); else closeCart();
  });

  document.addEventListener("click", (event) => {
    // Close dropdown when clicking outside the cart widget
    if (cartDropdown && !cartDropdown.hidden) {
      const cartNav = document.getElementById("cart-nav");
      if (cartNav && !cartNav.contains(event.target)) {
        closeCart();
      }
    }

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

    if (action === "decrease") changeQty(sku, -1);
    if (action === "increase") changeQty(sku, 1);
    if (action === "remove") removeItem(sku);
  });

  document.addEventListener("input", (event) => {
    // Product card qty pickers
    const cardQtyInput = event.target.closest("[data-cart-qty]");
    if (cardQtyInput) {
      cardQtyInput.value = cardQtyInput.value.replace(/[^\d]/g, "");
      resizeQtyInput(cardQtyInput);
      return;
    }

    // Cart item qty inputs — sanitize to digits only
    if (event.target.dataset.cartQtyInput !== undefined) {
      event.target.value = event.target.value.replace(/[^\d]/g, "");
    }
  });

  document.addEventListener("change", (event) => {
    // Product card qty pickers
    const cardQtyInput = event.target.closest("[data-cart-qty]");
    if (cardQtyInput) {
      cardQtyInput.value = String(clampQty(cardQtyInput.value));
      resizeQtyInput(cardQtyInput);
      return;
    }

    // Cart item qty direct input
    if (event.target.dataset.cartQtyInput !== undefined) {
      const sku = event.target.dataset.cartQtyInput;
      setQty(sku, event.target.value);
    }
  });

  document.querySelectorAll("[data-cart-qty]").forEach((qtyInput) => {
    qtyInput.value = String(clampQty(qtyInput.value));
    resizeQtyInput(qtyInput);
  });

  cartClearBtn?.addEventListener("click", clearCart);
  document.addEventListener("shop:product-data-updated", syncCartPricesFromProducts);

  renderCart();
});
