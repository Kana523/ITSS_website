// Shared cart markup injector. Builds the header cart button, the backdrop and
// the drawer so any page that loads it gets a working cart without duplicating
// the markup. Runs as a deferred IIFE (DOM is parsed by the time it executes,
// before DOMContentLoaded), so it must be loaded *before* shop-cart.js, which
// then wires behaviour to these elements by id. Idempotent: no-op if a drawer
// is already present (e.g. a page that still ships the markup inline).
(function () {
  if (document.getElementById("cart-drawer")) return;

  const TURNSTILE_SITEKEY = "0x4AAAAAADFK_LmTLxebflbr";

  // ── Header cart button ──────────────────────────────────────────────────────
  // Header is `display:flex; justify-content:space-between`; the logo's
  // `margin-right:auto` (base.css) groups nav + this button on the right.
  const header = document.querySelector("header");
  if (header && !document.getElementById("cart-toggle")) {
    const nav = document.createElement("div");
    nav.className = "cart-nav";
    nav.id = "cart-nav";
    nav.innerHTML = `
      <button
        type="button"
        class="cart-nav-btn"
        id="cart-toggle"
        aria-expanded="false"
        aria-controls="cart-drawer"
        aria-label="Cart, 0 items"
      >
        <svg class="cart-nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
          <circle cx="9" cy="21" r="1"></circle>
          <circle cx="20" cy="21" r="1"></circle>
          <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path>
        </svg>
        <span class="cart-nav-badge" id="cart-count">0</span>
      </button>`;
    header.appendChild(nav);
  }

  // ── Backdrop ────────────────────────────────────────────────────────────────
  const backdrop = document.createElement("div");
  backdrop.className = "cart-backdrop";
  backdrop.id = "cart-backdrop";
  backdrop.hidden = true;
  document.body.appendChild(backdrop);

  // ── Drawer ──────────────────────────────────────────────────────────────────
  const drawer = document.createElement("aside");
  drawer.className = "cart-drawer";
  drawer.id = "cart-drawer";
  drawer.hidden = true;
  drawer.setAttribute("aria-label", "Shopping cart");
  drawer.innerHTML = `
    <div class="cart-drawer-header">
      <button type="button" class="cart-drawer-close" id="cart-drawer-close" aria-label="Close cart">×</button>
      <span class="cart-drawer-title text-gradient-gold">Your Cart</span>
      <span class="cart-drawer-count" id="cart-item-count">0 items</span>
    </div>

    <ul class="cart-items" id="cart-items" aria-live="polite" aria-label="Cart items"></ul>

    <div class="cart-drawer-footer">
      <div class="cart-warning cart-preorder-summary" id="cart-preorder-summary" aria-live="polite" hidden>
        <span class="cart-warning-icon" aria-hidden="true">!</span>
        <p id="cart-preorder-summary-text"></p>
      </div>

      <div class="cart-total-row">
        <span class="cart-total-label">Total ISK</span>
        <div class="cart-total-amounts">
          <span class="cart-total-value text-gradient-gold" id="cart-total">0</span>
          <span class="cart-total-compact" id="cart-total-compact"></span>
        </div>
      </div>

      <div class="cart-identity">
        <div class="cart-identity-tabs">
          <button type="button" class="cart-identity-tab cart-identity-tab--active" data-tab="name">Character Name</button>
          <button type="button" class="cart-identity-tab" data-tab="orderid">Order ID</button>
        </div>

        <div class="cart-identity-panels">
        <div class="cart-identity-panel" data-panel="name">
          <div class="cart-orderid-box">
            <svg class="cart-orderid-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
            <div class="cart-orderid-box-text">
              <p>We'll contact you in-game to confirm your order.</p>
              <p class="cart-orderid-expiry">Orders not confirmed within <strong>7 days</strong> will be cancelled.</p>
            </div>
          </div>
          <div class="cart-warning">
            <span class="cart-warning-icon" aria-hidden="true">!</span>
            <p>Please verify your character name. Incorrect name might prevent us from delivering your order.</p>
          </div>
          <input type="text" id="cart-char-name" class="cart-identity-input" placeholder="Your character name…" autocomplete="off">
          <p class="cart-orderid-generate-error" id="cart-name-error" hidden></p>
          <div class="cart-footer-actions">
            <button type="button" class="buy-button cart-checkout" id="cart-checkout-name">Place Order</button>
            <button type="button" class="cart-clear" id="cart-clear-name" disabled>Clear All</button>
          </div>
        </div>

        <div class="cart-identity-panel" data-panel="orderid" hidden>
          <div class="cart-orderid-box">
            <svg class="cart-orderid-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
              <rect x="3" y="5" width="18" height="14" rx="2"></rect>
              <path d="m3 7 9 6 9-6"></path>
            </svg>
            <div class="cart-orderid-box-text">
              <p>EVEmail your order ID to <strong>Neo Achasse</strong>.</p>
              <p class="cart-orderid-expiry">Orders not confirmed within <strong>7 days</strong> will be cancelled.</p>
            </div>
          </div>
          <div class="cart-orderid-generate-box" id="cart-orderid-generate-box">
            <p class="cart-orderid-generated-label">Your Order ID:</p>
            <div class="cart-orderid-generated-row">
              <p class="cart-orderid-generated-value" id="cart-orderid-generated" hidden></p>
              <button type="button" class="cart-orderid-copy" id="cart-orderid-copy" aria-label="Copy Order ID to clipboard" title="Copy to clipboard" hidden>
                <svg class="cart-orderid-copy__icon cart-orderid-copy__icon--copy" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
                  <rect x="9" y="9" width="11" height="11" rx="2"></rect>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
                <svg class="cart-orderid-copy__icon cart-orderid-copy__icon--check" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
                  <path d="M5 12.5 L10 17.5 L19 7.5"></path>
                </svg>
              </button>
            </div>
          </div>
          <p class="cart-orderid-generate-error" id="cart-orderid-error" hidden></p>
          <div class="cart-footer-actions">
            <button type="button" class="buy-button cart-checkout" id="cart-checkout">Place Order</button>
            <button type="button" class="cart-clear" id="cart-clear" disabled>Clear All</button>
          </div>
          <div id="cart-turnstile" data-sitekey="${TURNSTILE_SITEKEY}"></div>
        </div>
        </div><!-- /.cart-identity-panels -->
      </div>
    </div>`;
  document.body.appendChild(drawer);
})();
